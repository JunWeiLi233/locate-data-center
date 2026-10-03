"""The configurable national grid and development-area selection (GRID
CONTRACT; phase1.md.txt steps 5-7).

Pipeline: `generate_national_grid()` builds every grid cell whose square
intersects the CONUS boundary from a fixed national origin, attributes each
retained cell to its primary/all states and counties, and returns a
row/col-sorted GeoDataFrame matching `dc_locator.schemas.GridCell`.
`select_study_area()` then SELECTS a subset of that already-stable grid for a
named development bounding box; it never recomputes IDs or attributes, so a
cell retained in both the national and a development output is byte-for-byte
identical in every non-geometry-subsetting column.

Vectorized throughout (numpy array construction, `shapely.box` batch
construction, `geopandas.overlay`/spatial-index queries) -- no per-cell
Python loop over national-scale data except the two small, unavoidable
string-formatting passes building `grid_id`/`tile_id` (AGENTS.md section 7).
"""

from __future__ import annotations

from typing import Optional

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from dc_locator.config import GridConfig, StudyAreaBBox, grid_number_token
from dc_locator.geography.boundary import TARGET_CRS, CONUSBoundary

# Candidate-grid sanity ceiling (AGENTS.md section 7: keep any single process
# under ~4 GB). A few million simple shapely boxes plus one overlay against
# ~3,100 counties is comfortably within budget; this guards against a
# pathological cell_size_m (e.g. a few metres) silently trying to build
# billions of cells.
_MAX_CANDIDATE_CELLS = 5_000_000

# Default segment length (decimal degrees) used to densify a development
# bounding box before reprojecting EPSG:4326 -> EPSG:5070, so the projected
# shape is a good approximation of the original rectangle's curved edges
# under Albers Equal Area rather than a coarse 4-vertex approximation.
_DEFAULT_BBOX_SEGMENTIZE_DEG = 0.01

# Preserve published national v1 IDs. Other origins/schemes include their
# definition in the ID to prevent the same row/col naming different squares.
_PUBLISHED_V1_ORIGIN = (-2_500_000.0, 3_400_000.0)
_AREA_FRACTION_TOLERANCE = 1e-9


class GridOriginViolationError(RuntimeError):
    """The study-area boundary extends west of origin_x_m or north of origin_y_m (GRID CONTRACT: fail loudly)."""


class GridIdOverflowError(RuntimeError):
    """A row or col index needs more digits than grid.yaml's id_row_col_digits allows."""


class GridIntegrityError(RuntimeError):
    """A generated grid failed a basic integrity check (duplicate IDs, invalid geometry, area bookkeeping)."""


def validate_boundary_within_origin(bounds: tuple[float, float, float, float], origin_x_m: float, origin_y_m: float) -> None:
    """Fail loudly if any part of the boundary lies west of origin_x_m or
    north of origin_y_m (GRID CONTRACT) -- the fixed origin must enclose the
    study area with margin by construction, never be silently adjusted to it.
    """
    minx, _miny, _maxx, maxy = bounds
    if minx < origin_x_m:
        raise GridOriginViolationError(
            f"Study-area boundary extends west of origin_x_m ({origin_x_m} m): boundary minx={minx} m. "
            "The fixed national origin must enclose the full study area; do not move the origin to fit the data."
        )
    if maxy > origin_y_m:
        raise GridOriginViolationError(
            f"Study-area boundary extends north of origin_y_m ({origin_y_m} m): boundary maxy={maxy} m. "
            "The fixed national origin must enclose the full study area; do not move the origin to fit the data."
        )


def row_col_for_point(x_m: float, y_m: float, origin_x_m: float, origin_y_m: float, cell_size_m: float) -> tuple[int, int]:
    """row = floor((origin_y - y) / size); col = floor((x - origin_x) / size) (GRID CONTRACT)."""
    row = int(np.floor((origin_y_m - y_m) / cell_size_m))
    col = int(np.floor((x_m - origin_x_m) / cell_size_m))
    return row, col


def cell_square_bounds(row: np.ndarray, col: np.ndarray, origin_x_m: float, origin_y_m: float, cell_size_m: float):
    """Vectorized (minx, miny, maxx, maxy) for arrays of row/col indices.

    Cell (row, col) is the square
    [ox + col*s, ox + (col+1)*s] x [oy - (row+1)*s, oy - row*s] (GRID CONTRACT).
    """
    minx = origin_x_m + col * cell_size_m
    maxx = origin_x_m + (col + 1) * cell_size_m
    maxy = origin_y_m - row * cell_size_m
    miny = origin_y_m - (row + 1) * cell_size_m
    return minx, miny, maxx, maxy


def make_grid_id(cell_size_m: float, row: int, col: int, digits: int, *, grid_definition_id: str | None = None) -> str:
    """Build a stable cell ID, optionally prefixed with its grid definition.

    Published fixed-origin v1 keeps ``g10000m-r0123-c0456``. Generation
    passes a prefix for other origins/schemes; IDs never depend on the
    development-area selection. Fractional metres are never rounded away.
    """
    size_token = grid_number_token(cell_size_m)
    if row < 0 or col < 0:
        raise ValueError(f"make_grid_id requires non-negative row/col, got row={row}, col={col}.")
    if row >= 10**digits or col >= 10**digits:
        raise GridIdOverflowError(
            f"row={row} or col={col} needs more than {digits} digits (grid.yaml:id_row_col_digits={digits}). "
            "Increase id_row_col_digits in configs/grid.yaml -- this changes grid_id formatting, so treat it "
            "as a grid-scheme change (bump grid_scheme_version) if any grid has already been published."
        )
    legacy_id = f"g{size_token}m-r{row:0{digits}d}-c{col:0{digits}d}"
    return legacy_id if grid_definition_id is None else f"{grid_definition_id}--{legacy_id}"


def make_tile_id(row: int, col: int, tile_size_cells: int) -> str:
    """tile_id from (row // tile_size_cells, col // tile_size_cells) (GRID CONTRACT)."""
    tile_row = row // tile_size_cells
    tile_col = col // tile_size_cells
    return f"t{tile_size_cells}-tr{tile_row:04d}-tc{tile_col:04d}"


def _aggregate_primary_and_all(overlay_df: pd.DataFrame, group_col: str, code_col: str, area_col: str, label_col: Optional[str] = None) -> pd.DataFrame:
    """For each group_col, return the code/label with the largest area_col
    (ties broken by the lowest code, GRID CONTRACT), the ';'-joined sorted
    set of all codes, the distinct-code count, and the primary row's area.
    """
    ordered = overlay_df.sort_values([group_col, area_col, code_col], ascending=[True, False, True])
    primary = ordered.groupby(group_col, as_index=True).first()
    all_codes = ordered.groupby(group_col)[code_col].apply(lambda s: ";".join(sorted(set(s.astype(str)))))
    n_distinct = ordered.groupby(group_col)[code_col].nunique()

    out = pd.DataFrame(
        {
            "primary_code": primary[code_col],
            "primary_area_m2": primary[area_col],
            "all_codes": all_codes,
            "n_distinct": n_distinct,
        }
    )
    if label_col is not None:
        out["primary_label"] = primary[label_col]
    return out


def generate_national_grid(grid_config: GridConfig, boundary: CONUSBoundary) -> tuple[gpd.GeoDataFrame, dict]:
    """Build the full national grid: every cell whose square intersects the
    CONUS boundary with positive area above `min_intersection_km2`, with
    state/county attribution. Returns (GeoDataFrame matching GridCell, stats dict).
    """
    origin_x_m = grid_config.origin_x_m
    origin_y_m = grid_config.origin_y_m
    cell_size_m = grid_config.cell_size_m
    digits = grid_config.id_row_col_digits
    tile_size_cells = grid_config.tile_size_cells
    min_intersection_m2 = grid_config.min_intersection_km2 * 1e6
    grid_definition_id = grid_config.grid_definition_id()

    conus_bounds = boundary.boundary.bounds  # (minx, miny, maxx, maxy), EPSG:5070
    validate_boundary_within_origin(conus_bounds, origin_x_m, origin_y_m)
    minx, miny, maxx, maxy = conus_bounds

    row_min = int(np.floor((origin_y_m - maxy) / cell_size_m))
    row_max = int(np.floor((origin_y_m - miny) / cell_size_m))
    col_min = int(np.floor((minx - origin_x_m) / cell_size_m))
    col_max = int(np.floor((maxx - origin_x_m) / cell_size_m))
    assert row_min >= 0 and col_min >= 0, "validate_boundary_within_origin should guarantee non-negative row/col."

    max_abs_index = max(row_max, col_max)
    if max_abs_index >= 10**digits:
        raise GridIdOverflowError(
            f"CONUS extent at cell_size_m={cell_size_m} needs row/col indices up to {max_abs_index}, which "
            f"exceeds what id_row_col_digits={digits} (configs/grid.yaml) can represent (max {10**digits - 1}). "
            "Increase id_row_col_digits before generating this resolution."
        )

    n_candidates = (row_max - row_min + 1) * (col_max - col_min + 1)
    if n_candidates > _MAX_CANDIDATE_CELLS:
        raise RuntimeError(
            f"Candidate grid would have {n_candidates:,} cells at cell_size_m={cell_size_m} "
            f"(limit {_MAX_CANDIDATE_CELLS:,}); refusing to continue (AGENTS.md section 7 memory budget)."
        )

    rows = np.arange(row_min, row_max + 1, dtype=np.int64)
    cols = np.arange(col_min, col_max + 1, dtype=np.int64)
    row_grid, col_grid = np.meshgrid(rows, cols, indexing="ij")
    row_flat = row_grid.ravel()
    col_flat = col_grid.ravel()

    cminx, cminy, cmaxx, cmaxy = cell_square_bounds(row_flat, col_flat, origin_x_m, origin_y_m, cell_size_m)
    squares = shapely.box(cminx, cminy, cmaxx, cmaxy)
    candidates = gpd.GeoDataFrame({"row": row_flat, "col": col_flat}, geometry=squares, crs=TARGET_CRS)

    # Spatial-index prefilter (exact "intersects" predicate via the STRtree,
    # not just a bbox test) before computing exact intersection geometry/area
    # only for cells that actually touch the boundary.
    boundary_geom = boundary.boundary
    touch_idx = candidates.sindex.query(boundary_geom, predicate="intersects")
    hits = candidates.iloc[np.sort(touch_idx)].copy()
    hits["intersection_geom"] = hits.geometry.intersection(boundary_geom)
    hits["intersection_area_m2"] = hits["intersection_geom"].area

    positive = hits[hits["intersection_area_m2"] > 0.0].copy()
    retained = positive[positive["intersection_area_m2"] > min_intersection_m2].copy()
    excluded_by_threshold = positive[positive["intersection_area_m2"] <= min_intersection_m2].copy()

    if retained.empty:
        raise GridIntegrityError("generate_national_grid produced zero retained cells -- check grid.yaml / boundary data.")

    retained["cell_area_km2"] = (cell_size_m / 1000.0) ** 2
    retained["study_area_intersection_km2"] = retained["intersection_area_m2"] / 1e6
    retained["study_area_frac"] = retained["study_area_intersection_km2"] / retained["cell_area_km2"]
    retained["is_boundary_cell"] = retained["study_area_frac"] < (1.0 - 1e-9)

    retained["grid_definition_id"] = grid_definition_id
    preserve_published_id = (
        (origin_x_m, origin_y_m) == _PUBLISHED_V1_ORIGIN
        and grid_config.grid_scheme_version == 1
    )
    id_prefix = None if preserve_published_id else grid_definition_id
    retained["grid_id"] = [
        make_grid_id(cell_size_m, int(r), int(c), digits, grid_definition_id=id_prefix)
        for r, c in zip(retained["row"], retained["col"])
    ]
    retained["tile_id"] = [make_tile_id(int(r), int(c), tile_size_cells) for r, c in zip(retained["row"], retained["col"])]

    centroids = retained.geometry.centroid
    retained["centroid_x_m"] = centroids.x.to_numpy()
    retained["centroid_y_m"] = centroids.y.to_numpy()
    centroids_4326 = gpd.GeoSeries(centroids.to_numpy(), crs=TARGET_CRS).to_crs(4326)
    retained["centroid_lat"] = centroids_4326.y.to_numpy()
    retained["centroid_lon"] = centroids_4326.x.to_numpy()

    rep_points_4326 = gpd.GeoSeries(retained["intersection_geom"].to_numpy(), crs=TARGET_CRS).representative_point().to_crs(4326)
    retained["rep_point_lat"] = rep_points_4326.y.to_numpy()
    retained["rep_point_lon"] = rep_points_4326.x.to_numpy()

    # --- State / county attribution: overlay the FULL cell square against
    # states/counties (shares divide by the CONUS intersection). County and
    # state generalization may disagree; material fraction overflow is
    # detected below rather than silently altering the source geometries.
    cells_for_overlay = retained[["grid_id", "geometry"]].copy()

    state_overlay = gpd.overlay(cells_for_overlay, boundary.states[["STATEFP", "STUSPS", "geometry"]], how="intersection")
    state_overlay["area_m2"] = state_overlay.geometry.area
    state_overlay = state_overlay[state_overlay["area_m2"] > 0]
    state_agg = _aggregate_primary_and_all(state_overlay, "grid_id", "STATEFP", "area_m2", label_col="STUSPS")

    county_overlay = gpd.overlay(cells_for_overlay, boundary.counties[["GEOID", "NAME", "geometry"]], how="intersection")
    county_overlay["area_m2"] = county_overlay.geometry.area
    county_overlay = county_overlay[county_overlay["area_m2"] > 0]
    county_agg = _aggregate_primary_and_all(county_overlay, "grid_id", "GEOID", "area_m2", label_col="NAME")

    retained = retained.set_index("grid_id", drop=False)

    retained["state_fips_primary"] = state_agg["primary_code"]
    retained["state_abbr_primary"] = state_agg["primary_label"]
    retained["state_fips_all"] = state_agg["all_codes"]
    retained["n_states"] = state_agg["n_distinct"]
    retained["state_share_primary_frac"] = (state_agg["primary_area_m2"] / 1e6) / retained["study_area_intersection_km2"]

    if retained["state_fips_primary"].isna().any():
        missing = retained.loc[retained["state_fips_primary"].isna(), "grid_id"].tolist()
        raise GridIntegrityError(f"{len(missing)} retained cell(s) matched no state in the overlay (unexpected, since every cell intersects CONUS by construction): {missing[:10]}...")

    retained["county_geoid_primary"] = county_agg["primary_code"]
    retained["county_name_primary"] = county_agg["primary_label"]
    retained["county_geoid_all"] = county_agg["all_codes"]
    retained["n_counties"] = county_agg["n_distinct"]
    retained["county_share_primary_frac"] = (county_agg["primary_area_m2"] / 1e6) / retained["study_area_intersection_km2"]
    retained["n_counties"] = retained["n_counties"].fillna(0).astype("int64")
    # Nullable string/float columns: keep genuine None rather than NaN/"nan" for the rare
    # coastline-mismatch cells with zero matching county (see schemas.GridCell docstring).
    for col_name in ("county_geoid_primary", "county_name_primary", "county_geoid_all"):
        retained[col_name] = retained[col_name].where(retained[col_name].notna(), None)
    retained["county_share_primary_frac"] = retained["county_share_primary_frac"].astype(object).where(retained["county_share_primary_frac"].notna(), None)

    # Independent cartographic vintages/generalization can place a county
    # outside the state union. Detect material area inconsistencies instead
    # of silently clipping observed areas or publishing impossible fractions.
    roundoff_counts = {}
    for fraction_column in ("study_area_frac", "state_share_primary_frac", "county_share_primary_frac"):
        values = pd.to_numeric(retained[fraction_column])
        invalid = values.notna() & ((values < 0) | (values > 1 + _AREA_FRACTION_TOLERANCE))
        if invalid.any():
            raise GridIntegrityError(
                f"{fraction_column} outside [0, 1] beyond {_AREA_FRACTION_TOLERANCE} tolerance "
                f"for {int(invalid.sum())} cells; inspect boundary-layer overlap/generalization."
            )
        roundoff_counts[fraction_column] = int((values > 1).sum())

    retained = retained.reset_index(drop=True)
    retained["data_mode"] = "real"
    retained["row"] = retained["row"].astype("int32")
    retained["col"] = retained["col"].astype("int32")
    retained["n_states"] = retained["n_states"].astype("int64")

    final_columns = [
        "grid_id", "grid_definition_id", "row", "col", "tile_id", "geometry",
        "cell_area_km2", "study_area_intersection_km2", "study_area_frac", "is_boundary_cell",
        "centroid_x_m", "centroid_y_m", "centroid_lat", "centroid_lon",
        "rep_point_lat", "rep_point_lon",
        "state_fips_primary", "state_abbr_primary", "state_share_primary_frac", "state_fips_all", "n_states",
        "county_geoid_primary", "county_name_primary", "county_share_primary_frac", "county_geoid_all", "n_counties",
        "data_mode",
    ]
    result = gpd.GeoDataFrame(retained[final_columns], geometry="geometry", crs=TARGET_CRS)
    result = result.sort_values(["row", "col"]).reset_index(drop=True)

    if result["grid_id"].duplicated().any():
        dupes = result.loc[result["grid_id"].duplicated(), "grid_id"].tolist()
        raise GridIntegrityError(f"Duplicate grid_id values generated: {dupes[:10]}... (grid_id scheme bug).")
    if not result.geometry.is_valid.all():
        raise GridIntegrityError("One or more generated cell geometries are invalid.")

    stats = {
        "grid_definition_id": grid_definition_id,
        "cell_size_m": cell_size_m,
        "row_range": [row_min, row_max],
        "col_range": [col_min, col_max],
        "n_candidates_bbox": n_candidates,
        "n_touching_boundary": int(len(hits)),
        "n_zero_area_touches_excluded": int(len(hits) - len(positive)),
        "n_excluded_by_min_intersection_threshold": int(len(excluded_by_threshold)),
        "excluded_by_threshold_total_km2": float(excluded_by_threshold["intersection_area_m2"].sum() / 1e6) if len(excluded_by_threshold) else 0.0,
        "n_retained": int(len(result)),
        "area_fraction_tolerance": _AREA_FRACTION_TOLERANCE,
        "fraction_roundoff_above_one_counts": roundoff_counts,
    }
    return result, stats


def select_study_area(national_grid: gpd.GeoDataFrame, bbox: StudyAreaBBox, *, segment_length_deg: float = _DEFAULT_BBOX_SEGMENTIZE_DEG) -> gpd.GeoDataFrame:
    """Select the national-grid cells whose full square intersects both CONUS
    (guaranteed already, since `national_grid` only contains such cells) and
    the given EPSG:4326 bounding box, densified before reprojection to
    EPSG:5070 so the box's edges are not coarsened into 4 straight segments
    under the Albers projection (GRID CONTRACT). Never alters any attribute
    of a retained cell -- this is a pure row selection.
    """
    box_4326 = shapely.geometry.box(bbox.lon_min, bbox.lat_min, bbox.lon_max, bbox.lat_max)
    densified_4326 = shapely.segmentize(box_4326, segment_length_deg)
    projected_box = gpd.GeoSeries([densified_4326], crs="EPSG:4326").to_crs(TARGET_CRS).iloc[0]

    mask = national_grid.geometry.intersects(projected_box)
    selected = national_grid.loc[mask].copy()
    return selected.sort_values(["row", "col"]).reset_index(drop=True)


__all__ = [
    "GridOriginViolationError",
    "GridIdOverflowError",
    "GridIntegrityError",
    "validate_boundary_within_origin",
    "row_col_for_point",
    "cell_square_bounds",
    "make_grid_id",
    "make_tile_id",
    "generate_national_grid",
    "select_study_area",
]
