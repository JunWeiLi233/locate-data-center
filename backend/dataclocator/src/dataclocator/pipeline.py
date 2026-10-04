"""Offline county joins and evidence exports; no ranking or site approval implied."""

import hashlib
import json
import tempfile
from pathlib import Path

import geopandas as gpd
import pandas as pd

from . import MODEL_VERSION
from .ingest import (read_counties, read_prices, price_baseline, read_grid,
                     read_polygons, read_water, read_hazards, assign_climate)
from .geography import normalize_water_value


def write_json(path: Path, value) -> None:
    """Atomically write strict JSON so interrupted writes cannot create cache markers."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, indent=2, allow_nan=False) + "\n"
    # Same-directory temporary files keep replacement atomic on the local filesystem.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def records(frame: pd.DataFrame) -> list[dict]:
    """Convert pandas nulls and scalar types into standards-compliant JSON values."""
    return json.loads(frame.to_json(orient="records", double_precision=15))


def verify_raw_inputs(root: Path) -> dict:
    """Verify frozen checksums before processing; changed releases cannot slip in."""
    manifest = json.loads((root / "data/source_manifest.json").read_text())
    for source in manifest["sources"]:
        path = root / source["local_path"]
        if not path.is_file():
            raise FileNotFoundError(f"missing frozen source {path}; run acquire")
        with path.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != source["sha256"]:
            raise ValueError(f"frozen input checksum mismatch: {path}")
    return manifest


def area_overlaps(counties: gpd.GeoDataFrame, regions: gpd.GeoDataFrame, identifiers: list[str]) -> pd.DataFrame:
    """Intersect in CONUS equal-area CRS; preserve each region and uncovered area.

    Shares describe county geometry, not utility consumption or withdrawal rights.
    No renormalization hides uncovered coastline or source gaps. Polygon repairs
    affect only derived geometries and are reported by the source reader.
    """
    left = counties.to_crs(5070).copy()
    right = regions[identifiers + ["geometry"]].to_crs(5070).copy()
    left.geometry = left.geometry.make_valid()
    right.geometry = right.geometry.make_valid()
    county_area = left.set_index("county_fips").geometry.area
    overlay = gpd.overlay(left, right, how="intersection", keep_geom_type=False)
    overlay["overlap_area_m2"] = overlay.geometry.area
    overlay = overlay[overlay.overlap_area_m2 > 0].copy()
    overlay["county_area_fraction"] = overlay.overlap_area_m2 / overlay.county_fips.map(county_area)
    return pd.DataFrame(overlay.drop(columns="geometry"))


def point_assignments(points: gpd.GeoDataFrame, regions: gpd.GeoDataFrame, column: str) -> dict[str, list]:
    """Retain all intersecting region IDs at border points instead of first-match wins."""
    joined = gpd.sjoin(points[["county_fips", "geometry"]], regions[[column, "geometry"]].to_crs(points.crs), how="left", predicate="intersects")
    return {key: sorted(set(group[column].dropna().tolist())) for key, group in joined.groupby("county_fips")}


def preprocess(root: Path) -> dict:
    """Build all required joins using verified local files, without network access."""
    root = root.resolve()
    manifest = verify_raw_inputs(root)
    selection = json.loads((root / "configs/candidates.json").read_text())
    counties = read_counties(root, selection)
    output = root / "outputs/task2"
    processed = root / "data/processed"
    output.mkdir(parents=True, exist_ok=True)
    processed.mkdir(parents=True, exist_ok=True)

    # Prices join by state, preserving history and an explicitly fixed full year.
    prices = read_prices(root, counties)
    baselines = price_baseline(prices)
    industrial = baselines[baselines.sector == "industrial"][["state_fips", "electricity_price_usd_per_mwh", "valid_months", "source_status"]].rename(columns={"source_status": "electricity_price_source_status"})
    commercial = baselines[baselines.sector == "commercial"][["state_fips", "electricity_price_usd_per_mwh"]].rename(columns={"electricity_price_usd_per_mwh": "commercial_price_usd_per_mwh"})
    counties = counties.merge(industrial, on="state_fips", how="left", validate="many_to_one").merge(commercial, on="state_fips", how="left", validate="many_to_one")
    counties["electricity_price_base_year"] = 2025
    grid = read_grid(root)
    polygons = read_polygons(root, counties)
    points = gpd.GeoDataFrame(counties[["county_fips"]].copy(), geometry=gpd.points_from_xy(counties.lon, counties.lat), crs=4326)
    primary = gpd.read_file("zip://" + str(root / "data/raw/egrid/2023-rev2/subregions.zip")).rename(columns={"Subregion": "grid_region"})
    multiple = gpd.read_file("zip://" + str(root / "data/raw/egrid/2023-rev2/multiple.zip"))
    point_grid = point_assignments(points, primary, "grid_region")
    grid_overlaps = area_overlaps(polygons, primary, ["grid_region"])
    ambiguity = area_overlaps(polygons, multiple, ["MultipleSu"])
    ambiguity_shares = ambiguity.groupby("county_fips").county_area_fraction.sum()
    grid_options = grid_overlaps.groupby("county_fips").grid_region.agg(lambda x: sorted(set(x)))
    counties["grid_region_options"] = counties.county_fips.map(grid_options)
    counties["grid_region"] = counties.county_fips.map(lambda f: point_grid[f][0] if len(point_grid[f]) == 1 else None)
    counties["grid_multiple_subregion_area_fraction"] = counties.county_fips.map(ambiguity_shares).fillna(0)
    counties["grid_border_or_multiple_subregions"] = counties.apply(lambda row: len(row.grid_region_options or []) > 1 or row.grid_multiple_subregion_area_fraction > 0, axis=1)
    counties["grid_assignment_method"] = "Census representative point in EPA map; utility supply unverified"
    counties = counties.merge(grid, on="grid_region", how="left", validate="many_to_one")

    # Full area distributions supplement the screening representative-point join.
    with tempfile.TemporaryDirectory(prefix="dcl-water-") as scratch:
        water, future = read_water(root, Path(scratch))
        water_repairs = water.attrs.get("invalid_geometry_count", 0)
        future_repairs = future.attrs.get("invalid_geometry_count", 0)
        water_overlaps = area_overlaps(polygons, water, [c for c in water.columns if c != "geometry"])
        future_overlaps = area_overlaps(polygons, future, [c for c in future.columns if c != "geometry"])
        point_water = point_assignments(points, water, "string_id")
    water_by_id = water.set_index("string_id")
    water_records = []
    for county in counties.itertuples():
        options = point_water[county.county_fips]
        row = water_by_id.loc[options[0]] if len(options) == 1 else None
        water_records.append({"county_fips": county.county_fips,
                              "water_region_id": options[0] if row is not None else None,
                              "water_point_region_options": options,
                              "water_stress_raw": normalize_water_value(row.bws_raw) if row is not None else None,
                              "water_stress_score": normalize_water_value(row.bws_score) if row is not None else None,
                              "water_stress_category": normalize_water_value(row.bws_cat) if row is not None else None,
                              "water_stress_label": row.bws_label if row is not None else None,
                              "water_depletion_raw": normalize_water_value(row.bwd_raw) if row is not None else None})
    counties = counties.merge(pd.DataFrame(water_records), on="county_fips", validate="one_to_one")
    counties["water_stress_scale"] = "raw demand/supply indicator; score 0-5; 9999 severe-scarcity sentinel"
    counties["water_assignment_method"] = "representative point; full county basin distributions exported separately"
    for frame in [water_overlaps, future_overlaps]:
        for col in frame:
            if col.endswith(("_raw", "_score", "_x_r", "_x_s")):
                frame[col] = frame[col].map(normalize_water_value)

    # NRI uses older geometry: exact FIPS matches remain regional context only.
    hazards = read_hazards(root)
    counties = counties.merge(hazards.drop(columns=["STATEFIPS", "COUNTYFIPS", "OBJECTID", "provenance"]), on="county_fips", how="left", validate="one_to_one")
    climate, station_metadata = assign_climate(root, counties)
    counties = counties.merge(pd.DataFrame(station_metadata), on="county_fips", validate="one_to_one")
    counties["feasibility_status"] = "unverified"

    # Export normalized, typed tables before writing the documented JSON interface.
    tables = {"candidates": counties, "electricity_prices": prices, "price_baselines": baselines,
              "grid_regions": grid, "grid_overlaps": grid_overlaps, "water_overlaps": water_overlaps,
              "water_future_overlaps": future_overlaps, "hazards": hazards, "climate_monthly": climate}
    for name, frame in tables.items():
        frame.to_parquet(processed / f"{name}.parquet", index=False)
        # Small regional evidence tables also travel directly as frontend-ready JSON.
        if name in {"grid_overlaps", "water_overlaps", "water_future_overlaps", "climate_monthly", "price_baselines"}:
            write_json(output / f"{name}.json", records(frame))
    polygons.to_parquet(processed / "candidate_polygons.parquet", index=False)
    counties.to_csv(output / "candidates.csv", index=False)
    details = records(counties)
    for candidate in details:
        # Every geographic feature names its source and approximation explicitly.
        candidate["feasibility"] = {name: {"status": "unverified", "evidence": None} for name in ["power_capacity", "water_allocation", "parcel_zoning", "fiber_redundancy"]}
        candidate["reliability_indicators"] = None
        candidate["coverage"] = {"price": "measured state retail proxy" if candidate["electricity_price_usd_per_mwh"] is not None else "missing",
                                  "carbon": "measured regional average; supplier unverified" if candidate["grid_region"] else "missing/ambiguous",
                                  "water_stress": "modeled basin screening" if candidate["water_stress_raw"] is not None else "missing/ambiguous",
                                  "climate": "station normal; elevation unverified" if candidate["climate_station_id"] else "missing",
                                  "hazards": "county context; no facility downtime model", "pue": "missing user/engineering input", "wue": "missing user/engineering input"}
        candidate["provenance"] = {"location": "census_gazetteer", "electricity_price": "eia_monthly",
                                   "grid_carbon": "egrid_data", "grid_assignment": "egrid_map",
                                   "water_stress": "aqueduct", "climate": "noaa_monthly", "hazards": "fema_counties"}
        candidate["hazard_indicators"] = {prefix: {"annualized_frequency": candidate.get(prefix + "_AFREQ"),
                                                  "expected_annual_loss_existing_assets_usd": candidate.get(prefix + "_EALT"),
                                                  "risk_score": candidate.get(prefix + "_RISKS"), "risk_rating": candidate.get(prefix + "_RISKR")}
                                          for prefix in ["IFLD", "CFLD", "WFIR", "HWAV", "HRCN", "DRGT"]}
    payload = {"schema_version": "0.1.0", "model_version": MODEL_VERSION, "scope": "45 selected contiguous-US counties; screening only",
               "selection": selection, "candidates": details, "sources": manifest["sources"],
               "boundaries": ["electricity cost only; no capex, water tariff or total ownership cost",
                              "no backup fuel, construction, IT manufacturing, heat displacement or contract carbon credit",
                              "no indirect generation water until a compatible consumption factor is supplied"],
               "engineering_assumptions": {"pue": None, "wue_l_per_kwh_it": None,
                                           "note": "No regional performance curve; climate cannot set PUE or WUE."}}
    write_json(output / "candidates.json", payload)
    coverage = {"candidate_count": len(counties), "complete_price_count": int(counties.electricity_price_usd_per_mwh.notna().sum()),
                "grid_point_assignment_count": int(counties.grid_region.notna().sum()),
                "grid_ambiguous_count": int(counties.grid_border_or_multiple_subregions.sum()),
                "water_point_assignment_count": int(counties.water_region_id.notna().sum()),
                "climate_station_count": int(counties.climate_station_id.notna().sum()),
                "climate_max_station_distance_km": float(counties.climate_station_distance_km.max()),
                "hazard_match_count": int(counties.HWAV_AFREQ.notna().sum()),
                "water_invalid_geometries_repaired": water_repairs, "future_invalid_geometries_repaired": future_repairs,
                "water_county_coverage_fractions": records(water_overlaps.groupby("county_fips", as_index=False).county_area_fraction.sum()),
                "warnings": ["all power, water allocation, zoning and fiber feasibility remain unverified",
                             "eGRID maps are approximate; border/multiple-service counties need utility confirmation",
                             "NRI v1.20 uses 2021 TIGER boundaries (CT exception); FIPS join does not prove boundary equivalence with 2025",
                             "station elevations stored; terrain suitability unverified; normals are not future variability",
                             "2025 electricity prices are preliminary EIA observations in nominal 2025 USD; demand charges are not separately modeled",
                             "NRI expected losses describe existing assets in December 2024 dollars; they are not this facility's cost",
                             "Aqueduct scenario dictionary contains an inconsistent SSP example; retain bau/opt/pes labels, no probability assignment",
                             "no PUE/WUE chosen; water stress is not a withdrawal volume or an engineering WUE"]}
    write_json(output / "coverage.json", coverage)
    return coverage
