"""National 1 km screening features from native sources (geography: no thresholds, scores or rankings).

Regional refinement evaluates a 1 km cell with the complete adapter pipeline. This module computes only
the cell features the decision profile reads, for every CONUS cell, from the same source files and with
the same formulas, vectorized per 50 km window:

- suitable-land share and coverage: exact pixel-area weights on the prepared EPSG:5070 30 m Annual NLCD
  raster (``sources/nlcd.py`` classes). Whole cells use separable x/y pixel overlaps; coast and border
  cells clipped to the CONUS study polygon use the adapter itself;
- transmission distance: nearest mapped line to the cell's study polygon (``sources/infrastructure.py``);
- basin water stress and eGRID carbon intensity: area-weighted means and coverage over key-dissolved
  polygons (``sources/aqueduct.py``, ``sources/egrid.py``), clipped to each window first.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyproj
import rasterio
import shapely
from rasterio.windows import Window

from dc_locator.config import GridConfig
from dc_locator.geography.grid import make_grid_id
from dc_locator.geography.sources.egrid import pounds_per_mwh_to_kg_per_mwh, read_subregion_workbook
from dc_locator.geography.sources.nlcd import CLASSES, summarize_land_cover
from dc_locator.geography.features import METRICS, SOURCE_INFO

FINE_FEATURE_VERSION = 'national-fine-features-v2'
PUBLISHED_ORIGIN = (-2_500_000.0, 3_400_000.0)
UNSUITABLE_CLASSES = (11, 12, 90, 95)  # the exclusion in sources/nlcd.summarize_land_cover
FULL_CELL_TOLERANCE = 1e-9  # grid.py: a cell is a boundary cell when study_area_frac < 1 - 1e-9
MINIMUM_PIECE_AREA_M2 = 1e-8  # sources/spatial.region_intersections drops smaller slivers
FEATURE_COLUMNS = ('potentially_suitable_land_frac', 'nlcd_coverage_frac', 'transmission_distance_km',
                   'baseline_water_stress_score', 'baseline_water_stress_score_coverage_frac',
                   'grid_carbon_intensity_kg_per_mwh', 'egrid_coverage_frac')
FEATURE_SOURCES = {**dict.fromkeys(FEATURE_COLUMNS[:2], 'usgs_annual_nlcd'),
                   'transmission_distance_km': 'eia_energy_atlas',
                   **dict.fromkeys(FEATURE_COLUMNS[3:5], 'wri_aqueduct40'),
                   **dict.fromkeys(FEATURE_COLUMNS[5:], 'epa_egrid')}
EVIDENCE_FIELDS = ('status', 'confidence', 'missing_reason', 'source_id', 'source_field', 'unit', 'data_year')
EVIDENCE_COLUMNS = tuple(metric + '_' + field for metric in FEATURE_COLUMNS for field in EVIDENCE_FIELDS)
FEATURE_COVERAGE = {'potentially_suitable_land_frac': 'nlcd_coverage_frac', 'nlcd_coverage_frac': 'nlcd_coverage_frac',
                    'baseline_water_stress_score': 'baseline_water_stress_score_coverage_frac',
                    'baseline_water_stress_score_coverage_frac': 'baseline_water_stress_score_coverage_frac',
                    'grid_carbon_intensity_kg_per_mwh': 'egrid_coverage_frac', 'egrid_coverage_frac': 'egrid_coverage_frac'}


def feature_metadata(source_inputs: dict) -> dict[str, dict]:
    """Same source declarations as native geography; the score-coverage diagnostic is calculated."""
    records = {}
    for metric, source in FEATURE_SOURCES.items():
        cfg = source_inputs.get(source, {})
        unit, field, status = METRICS[source].get(metric, ('frac', 'valid bws_score mask', 'calculated'))
        info = SOURCE_INFO[source]
        records[metric] = dict(source_id=source, source_name=cfg.get('source_name', info[0]),
            source_url=cfg.get('source_url', info[1]), source_field=field, unit=unit, base_status=status,
            source_version=cfg.get('source_version', info[3]), data_year=cfg.get('data_year', info[2]),
            retrieved_at=cfg.get('retrieved_at'), spatial_resolution=cfg.get('spatial_resolution', info[4]),
            aggregation_method=cfg.get('aggregation_method', 'minimum study-intersection-polygon distance in EPSG:5070'
                if source == 'eia_energy_atlas' else 'study-intersection area-weighted zonal/overlay'),
            method=cfg.get('method', 'See docs/data_dictionary.md; raw units retained; partial coverage is not extrapolated'))
    return records


def attach_evidence(features: pd.DataFrame, source_inputs: dict) -> pd.DataFrame:
    """Explicit wide evidence companions, following geography.features._tile confidence rules."""
    columns = {}
    for metric, record in feature_metadata(source_inputs).items():
        present = np.isfinite(features[metric].to_numpy(dtype=float))
        coverage = features[FEATURE_COVERAGE[metric]].to_numpy() if metric in FEATURE_COVERAGE else np.full(len(features), np.nan)
        confidence = np.where(record['base_status'] == 'proxy', 'low', np.where(coverage == 1, 'high', 'medium'))
        confidence = np.where(coverage < .95, 'low', confidence)
        columns[metric + '_status'] = np.where(present, record['base_status'], 'unknown')
        columns[metric + '_confidence'] = np.where(present, confidence, 'unknown')
        columns[metric + '_missing_reason'] = np.where(present, None, 'source_nodata')
        for field in ('source_id', 'source_field', 'unit', 'data_year'):
            columns[metric + '_' + field] = record[field]
    return pd.concat([features, pd.DataFrame(columns, index=features.index)], axis=1)


def feature_provenance(cells: pd.DataFrame, features: pd.DataFrame, source_inputs: dict, data_mode: str) -> pd.DataFrame:
    """Long-form FeatureMetadata 1.1.0 for all seven stored metrics, bounded to one window."""
    frames = []
    for metric, metadata in feature_metadata(source_inputs).items():
        record = {key: value for key, value in metadata.items() if key != 'base_status'}
        frame = pd.DataFrame(dict(schema_version='1.1.0', grid_id=cells.grid_id.to_numpy(), metric=metric,
            value=features[metric].to_numpy(), value_text=None, data_mode=data_mode, **record))
        frame['coverage_frac'] = features[FEATURE_COVERAGE[metric]].to_numpy() if metric in FEATURE_COVERAGE else np.full(len(features), np.nan)
        for field in ('status', 'confidence', 'missing_reason'):
            frame[field] = features[metric + '_' + field].to_numpy()
        frames.append(frame)
    return pd.concat(frames, ignore_index=True).sort_values(['grid_id', 'metric'], kind='stable')


@dataclass(frozen=True)
class FineSources:
    """National-extent source geometry in EPSG:5070, read once per build."""
    land_cover: Path
    transmission: np.ndarray
    basins: np.ndarray
    basin_stress: np.ndarray
    egrid: np.ndarray
    egrid_kg_per_mwh: np.ndarray
    files: dict[str, Path]
    source_inputs: dict = field(default_factory=dict)
    egrid_lb_per_mwh: np.ndarray | None = None
    transmission_tree: shapely.STRtree = field(init=False, repr=False)
    basin_tree: shapely.STRtree = field(init=False, repr=False)
    egrid_tree: shapely.STRtree = field(init=False, repr=False)

    def __post_init__(self):
        object.__setattr__(self, 'transmission_tree', shapely.STRtree(self.transmission))
        object.__setattr__(self, 'basin_tree', shapely.STRtree(self.basins))
        object.__setattr__(self, 'egrid_tree', shapely.STRtree(self.egrid))

    def __reduce__(self):  # spatial indexes are rebuilt rather than pickled
        return FineSources, (self.land_cover, self.transmission, self.basins, self.basin_stress, self.egrid, self.egrid_kg_per_mwh,
                             self.files, self.source_inputs, self.egrid_lb_per_mwh)


def _projected(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Repair, project and repair again, as sources/spatial.read_vector does, dropping empty geometry."""
    frame = frame.copy()
    frame.geometry = shapely.make_valid(frame.geometry.values)
    frame = frame.to_crs(5070)
    frame.geometry = shapely.make_valid(frame.geometry.values)
    return frame.loc[frame.geometry.notna() & ~frame.geometry.is_empty]


def _vsi(path, member=None):
    path = Path(path)
    return '/vsizip/' + path.resolve().as_posix() + (('/' + member) if member else '') if path.suffix == '.zip' else str(path)


def load_fine_sources(source_inputs: dict, study_bounds_5070) -> FineSources:
    """Read the national land-cover raster path, transmission lines, basins and eGRID subregions."""
    for source in sorted(set(FEATURE_SOURCES.values())):
        cfg = source_inputs.get(source, {})
        if cfg.get('quality_blocker'):
            raise ValueError(f'{source} has a quality blocker: {cfg["quality_blocker"]}')
    for source in sorted(set(FEATURE_SOURCES.values())):
        cfg = source_inputs.get(source, {})
        if not cfg.get('paths') or cfg.get('data_mode') != 'real':
            raise ValueError(f'{source} requires explicit real local inputs for the national fine surface')
    land_cover = Path(source_inputs['usgs_annual_nlcd']['paths']['land_cover'])
    with rasterio.open(land_cover) as raster:
        t = raster.transform
        if raster.crs is None or not pyproj.CRS(raster.crs).equals(pyproj.CRS.from_epsg(5070), ignore_axis_order=True) \
                or t.b or t.d or abs(t.a) != 30 or abs(t.e) != 30:
            raise ValueError('National fine features require the prepared north-up 30 m EPSG:5070 land-cover raster')
    eia = source_inputs['eia_energy_atlas']['paths']['transmission']
    lines = _projected(gpd.read_file(eia, columns=[]))
    native_bounds = np.array(pyproj.Transformer.from_crs(5070, 4326, always_xy=True).transform_bounds(
        *study_bounds_5070, densify_pts=101))
    aqueduct = source_inputs['wri_aqueduct40']
    basins = gpd.read_file(_vsi(aqueduct['paths']['baseline'], aqueduct.get('zip_member')), layer=aqueduct.get('layer', 'baseline_annual'),
                           columns=['pfaf_id', 'bws_score'], where='pfaf_id > 0', bbox=tuple(native_bounds + np.array([-1, -1, 1, 1])))
    basins = _projected(basins[basins.pfaf_id.notna()]).dissolve(by='pfaf_id', as_index=False, aggfunc='first')
    basins = basins[basins.bws_score.notna() & (basins.bws_score != -9999)]
    egrid = source_inputs['epa_egrid']
    regions = gpd.read_file(_vsi(egrid['paths']['regions'])).rename(columns={egrid.get('region_field', 'Subregion'): 'subregion'})
    unit = egrid.get('unit', 'lb_per_mwh')
    rates = read_subregion_workbook(egrid['paths']['workbook'], sheet=egrid.get('sheet', 'SRL23'), unit=unit)
    regions = _projected(regions[['subregion', 'geometry']]).dissolve(by='subregion', as_index=False, aggfunc='first')
    regions = regions.merge(rates, on='subregion', how='left', validate='one_to_one')
    regions = regions[regions.SRC2ERTA.notna() & (regions.SRC2ERTA >= 0)]
    if unit not in {'lb_per_mwh', 'kg_per_mwh'}:
        raise ValueError('Explicit eGRID units required')
    intensity = regions.SRC2ERTA.to_numpy(dtype=float)
    files = {'land_cover': land_cover, 'transmission': Path(eia), 'aqueduct': Path(aqueduct['paths']['baseline']),
             'egrid_regions': Path(egrid['paths']['regions']), 'egrid_workbook': Path(egrid['paths']['workbook'])}
    return FineSources(land_cover=land_cover, transmission=lines.geometry.values, basins=basins.geometry.values,
                       basin_stress=basins.bws_score.to_numpy(dtype=float), egrid=regions.geometry.values,
                       egrid_kg_per_mwh=pounds_per_mwh_to_kg_per_mwh(intensity) if unit == 'lb_per_mwh' else intensity,
                       egrid_lb_per_mwh=intensity if unit == 'lb_per_mwh' else None, files=files, source_inputs=source_inputs)


def window_cells(grid_config: GridConfig, parent_row: int, parent_col: int, ratio: int, study=None) -> pd.DataFrame:
    """1 km cells of one 50 km parent on the fixed origin; ``study`` is the CONUS polygon clipped to the parent.

    Interior parents (``study`` None) keep every whole cell. Otherwise a cell is retained when its study
    intersection area is positive, and coast/border cells keep the clipped study polygon as geometry.
    """
    if (grid_config.origin_x_m, grid_config.origin_y_m) != PUBLISHED_ORIGIN or grid_config.grid_scheme_version != 1:
        raise ValueError('National fine features require the published fixed-origin grid scheme')
    size = float(grid_config.cell_size_m)
    rows = np.repeat(np.arange(parent_row * ratio, (parent_row + 1) * ratio), ratio)
    cols = np.tile(np.arange(parent_col * ratio, (parent_col + 1) * ratio), ratio)
    x0, y0 = PUBLISHED_ORIGIN
    squares = shapely.box(x0 + cols * size, y0 - (rows + 1) * size, x0 + (cols + 1) * size, y0 - rows * size)
    # Native build_features intersects even interior squares with CONUS. Its canonical
    # clockwise ring changes last-bit overlay areas; retain that analysis ordering.
    squares = shapely.normalize(squares)
    full_area = size * size
    if study is None:
        area, geometry = np.full(len(rows), full_area), squares
    else:
        shapely.prepare(study)
        inside = shapely.contains_properly(study, squares)
        geometry = squares.copy()
        edge = ~inside
        geometry[edge] = shapely.intersection(squares[edge], study)
        area = np.where(inside, full_area, shapely.area(geometry))
    keep = area > max(grid_config.min_intersection_km2 * 1e6, 0)
    rows, cols, geometry, area = rows[keep], cols[keep], geometry[keep], area[keep]
    full = area >= full_area * (1 - FULL_CELL_TOLERANCE)
    geometry = np.where(full, squares[keep], geometry)
    digits = grid_config.id_row_col_digits
    return pd.DataFrame({'grid_id': [make_grid_id(size, int(r), int(c), digits) for r, c in zip(rows, cols)],
                         'row': rows.astype('int32'), 'col': cols.astype('int32'), 'geometry': geometry,
                         'study_area_intersection_km2': area / 1e6, 'full_cell': full})


def overlaps(pixel_edges: np.ndarray, cell_edges: np.ndarray) -> np.ndarray:
    """Overlap length of each pixel interval with each cell interval; both edge arrays increase."""
    low = np.maximum(pixel_edges[:-1, None], cell_edges[None, :-1])
    high = np.minimum(pixel_edges[1:, None], cell_edges[None, 1:])
    return np.clip(high - low, 0, None)


def land_cover_shares(cells: pd.DataFrame, raster, path: Path, cell_size_m: float) -> tuple[np.ndarray, np.ndarray]:
    """Suitable-land share and valid-pixel coverage of each cell's study polygon (NaN when unobserved)."""
    share = np.full(len(cells), np.nan)
    coverage = np.zeros(len(cells))
    full = cells.full_cell.to_numpy()
    if full.any():
        t, x0, y0 = raster.transform, *PUBLISHED_ORIGIN
        rows, cols = cells.row.to_numpy()[full], cells.col.to_numpy()[full]
        r0, c0 = int(rows.min()), int(cols.min())
        r1, c1 = int(rows.max()) + 1, int(cols.max()) + 1
        x_min, x_max, y_max, y_min = x0 + c0 * cell_size_m, x0 + c1 * cell_size_m, y0 - r0 * cell_size_m, y0 - r1 * cell_size_m
        j0, j1 = max(0, int(np.floor((x_min - t.c) / t.a))), min(raster.width, int(np.ceil((x_max - t.c) / t.a)))
        i0, i1 = max(0, int(np.floor((t.f - y_max) / -t.e))), min(raster.height, int(np.ceil((t.f - y_min) / -t.e)))
        if j1 > j0 and i1 > i0:
            classes = raster.read(1, window=Window(j0, i0, j1 - j0, i1 - i0), masked=True)
            values = classes.filled(0)
            valid = ~np.ma.getmaskarray(classes) & np.isin(values, list(CLASSES))
            suitable = valid & ~np.isin(values, UNSUITABLE_CLASSES)
            wx = overlaps(t.c + t.a * np.arange(j0, j1 + 1), x0 + cell_size_m * np.arange(c0, c1 + 1))
            wy = overlaps(-(t.f + t.e * np.arange(i0, i1 + 1)), -(y0 - cell_size_m * np.arange(r0, r1 + 1)))
            valid_area = wy.T @ valid.astype(np.float64) @ wx
            suitable_area = wy.T @ suitable.astype(np.float64) @ wx
            area, good = valid_area[rows - r0, cols - c0], suitable_area[rows - r0, cols - c0]
            index = np.flatnonzero(full)
            share[index] = np.divide(good, area, out=np.full(len(area), np.nan), where=area > 0)
            coverage[index] = area / (cell_size_m * cell_size_m)
    for position in np.flatnonzero(~full):
        summary = summarize_land_cover(path, cells.geometry.iloc[position])
        share[position] = summary['potentially_suitable_land_frac']
        coverage[position] = summary['nlcd_coverage_frac']
    return share, coverage


def area_weighted(geometry: np.ndarray, polygons: np.ndarray, values: np.ndarray, tree: shapely.STRtree,
                  window) -> tuple[np.ndarray, np.ndarray]:
    """Area-weighted value and coverage share of each study polygon over key-dissolved source polygons."""
    mean = np.full(len(geometry), np.nan)
    coverage = np.zeros(len(geometry))
    candidates = tree.query(window, predicate='intersects')
    if not len(candidates):
        return mean, coverage
    pieces = shapely.intersection(polygons[candidates], window)
    keep = ~shapely.is_empty(pieces)
    pieces, piece_values = pieces[keep], values[candidates][keep]
    shapely.prepare(pieces)
    cell, piece = shapely.STRtree(pieces).query(geometry, predicate='intersects')
    whole = shapely.covers(pieces[piece], geometry[cell])
    area = np.where(whole, shapely.area(geometry[cell]), 0.0)
    area[~whole] = shapely.area(shapely.intersection(geometry[cell][~whole], pieces[piece][~whole]))
    positive = area > MINIMUM_PIECE_AREA_M2
    cell, piece, area = cell[positive], piece[positive], area[positive]
    total, weight = np.zeros(len(geometry)), np.zeros(len(geometry))
    np.add.at(total, cell, piece_values[piece] * area)
    np.add.at(weight, cell, area)
    np.divide(total, weight, out=mean, where=weight > 0)
    shares = area / shapely.area(geometry)[cell]
    np.add.at(coverage, cell, shares)  # native adapters sum piece shares, then cap; division after summation changes confidence
    coverage = np.minimum(1.0, coverage)
    return mean, coverage


def window_features(cells: pd.DataFrame, sources: FineSources, raster, window, cell_size_m: float) -> pd.DataFrame:
    """Profile-facing features for the cells of one parent window, in the geography table's column names."""
    geometry = cells.geometry.to_numpy()
    land, land_coverage = land_cover_shares(cells, raster, sources.land_cover, cell_size_m)
    (query, nearest), distance = sources.transmission_tree.query_nearest(geometry, return_distance=True, all_matches=False)
    transmission = np.full(len(cells), np.nan)
    transmission[query] = distance / 1000.0
    stress, stress_coverage = area_weighted(geometry, sources.basins, sources.basin_stress, sources.basin_tree, window)
    native_carbon = sources.egrid_kg_per_mwh if sources.egrid_lb_per_mwh is None else sources.egrid_lb_per_mwh
    carbon, carbon_coverage = area_weighted(geometry, sources.egrid, native_carbon, sources.egrid_tree, window)
    if sources.egrid_lb_per_mwh is not None:
        carbon = pounds_per_mwh_to_kg_per_mwh(carbon)  # native adapter weights before converting
    features = pd.DataFrame({'potentially_suitable_land_frac': land, 'nlcd_coverage_frac': np.minimum(1.0, land_coverage),
                         'transmission_distance_km': transmission, 'baseline_water_stress_score': stress,
                         'baseline_water_stress_score_coverage_frac': stress_coverage,
                         'grid_carbon_intensity_kg_per_mwh': carbon, 'egrid_coverage_frac': carbon_coverage}, index=cells.index)
    return attach_evidence(features, sources.source_inputs)
