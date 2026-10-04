"""Independent county context transport; no technical scoring or model mutations."""
from __future__ import annotations

import math
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyarrow.parquet as pq
from shapely.geometry import mapping

from .serialization import ApiError, ArtifactReader, SCHEMA_VERSION, clean, file_digest, member_grid_ids, read_json, valid_geometry

BOUNDARY_YEARS = (2023, 2025)
DEFAULT_BOUNDARY_YEAR = 2025
SOCIOECONOMIC_YEAR = 2024
# HTTP preparation is bounded to saved evaluated geography, never the national fine surface.
MAX_CONTEXT_GRID_CELLS = 200_000
METRICS = {
    "poverty_rate_pct": ("poverty_rate", "pct"),
    "income_usd": ("median_household_income", "USD"),
    "poverty_rate_moe_pct": ("poverty_rate_moe", "percentage_points"),
    "income_moe_usd": ("median_household_income_moe", "USD"),
    "poverty_percentile": ("poverty_percentile", "percentile_0_to_100"),
    "low_income_percentile": ("low_income_percentile", "percentile_0_to_100"),
}
SUBLAYERS = {
    "poverty": ("poverty_rate_pct", "Poverty rate"),
    "income": ("income_usd", "Median household income"),
    "poverty_percentile": ("poverty_percentile", "Poverty percentile"),
    "low_income_percentile": ("low_income_percentile", "Low-income percentile"),
}
CONTEXT_NOTE = ("Independent county economic context; it does not change technical scores, ranks, screening or weights. "
                "County estimates are not facility or parcel measurements.")


def boundary_year(value=DEFAULT_BOUNDARY_YEAR) -> int:
    if type(value) is int and value in BOUNDARY_YEARS:
        return value
    if type(value) is str and value in {str(year) for year in BOUNDARY_YEARS}:
        return int(value)
    raise ApiError("boundary_year must be 2023 or 2025", 400, "invalid_boundary_year")


def _geography():
    try:
        from dc_locator.geography import socioeconomic
    except ImportError as exc:
        raise FileNotFoundError("County economic geography is unavailable") from exc
    return socioeconomic


def cached_artifacts(root: Path, grid_path: Path, year: int):
    """Prepare only a bounded saved grid from already acquired local sources."""
    if not grid_path.is_file():
        raise FileNotFoundError("Saved evaluated geography is unavailable for county context")
    rows = pq.read_metadata(grid_path).num_rows
    if rows > MAX_CONTEXT_GRID_CELLS:
        raise ApiError("Supply a bounded saved regional grid of at most 200,000 cells; the national fine surface is unsupported for county-context preparation", 422, "socioeconomic_grid_budget")
    return _available_geography(root, year).ensure_socioeconomic_geography(root, grid_path, boundary_year=year, cached_only=False, acquire=False)


def cached_counties(root: Path, year: int):
    return _available_geography(root, year).ensure_county_geography(root, boundary_year=year, cached_only=False, acquire=False)


def _available_geography(root: Path, year: int):
    module = _geography()
    if not module.source_availability(root, boundary_year=year).get("available"):
        raise FileNotFoundError("County economic context is disabled or official sources are unavailable locally; HTTP never downloads data.")
    return module


def _unavailable(year: int, reason: str) -> dict:
    return {"schema_version": SCHEMA_VERSION, "context_schema_version": "1.0.0", "available": False,
            "boundary_year": year, "socioeconomic_year": SOCIOECONOMIC_YEAR,
            "boundary_source_kind": "cartographic", "source_metadata": {},
            "warnings": [reason, CONTEXT_NOTE], "coverage_summary": {}, "region_counties": {},
            "fiscal_context": _fiscal()}


def _fiscal() -> dict:
    return {name: {"value": None, "status": "unknown", "confidence": "unknown", "missing_reason": reason}
            for name, reason in {
                "local_revenue": "SAIPE poverty and income estimates do not measure local fiscal revenue.",
                "service_pressure": "No compatible local service-pressure evidence has been acquired.",
            }.items()}


def _metadata(metadata: dict, year: int) -> dict:
    binding = metadata.get("binding", {})
    county_binding = binding.get("county_binding", binding)
    inventory = county_binding.get("sources", [])
    sources = metadata.get("source_metadata") or {
        "estimate_source": {"name": "U.S. Census Bureau SAIPE", "url": inventory[1].get("url") if len(inventory) > 1 else None,
                            "year": SOCIOECONOMIC_YEAR, "observation_type": "Model-based county estimate"},
        "boundary_source": {"name": "U.S. Census Bureau Cartographic Boundary", "url": inventory[0].get("url") if inventory else None,
                            "year": year, "scale": "1:500000", "kind": metadata.get("boundary_type", "cartographic_500k")},
        "native_metadata": metadata,
    }
    warnings = list(metadata.get("warnings", []))
    if metadata.get("geometry_warning"):
        warnings.append(metadata["geometry_warning"])
    warnings.append(f"{SOCIOECONOMIC_YEAR} SAIPE estimates are joined by GEOID to {year} generalized county boundaries; vintages differ.")
    return {"boundary_year": year, "socioeconomic_year": SOCIOECONOMIC_YEAR,
            "boundary_source_kind": metadata.get("boundary_source_kind", metadata.get("boundary_type", "cartographic_500k")),
            "source_metadata": sources, "warnings": warnings + [CONTEXT_NOTE]}


def _county_record(row: dict, year: int, socioeconomic_year: int, source_metadata: dict) -> dict:
    result = {"county_geoid": str(row["county_geoid"]), "county_name": row.get("county_name"),
              "state_fips": row.get("state_fips"), "state_name": row.get("state_name"),
              "boundary_year": year, "socioeconomic_year": socioeconomic_year, "metrics": {}}
    for wire, (native, unit) in METRICS.items():
        value = clean(row.get(native))
        status = row.get(native + "_status", "unknown")
        known = type(value) in (int, float) and math.isfinite(value) and status in {"observed", "calculated", "proxy", "scenario"}
        reason = clean(row.get(native + "_missing_reason")) or (None if known else "No compatible source value or status is available.")
        result[wire] = value if known else None
        result["metrics"][wire] = {"value": result[wire], "unit": clean(row.get(native + "_unit")) or unit,
                                   "status": status if known else "unknown", "confidence": row.get(native + "_confidence", "unknown") if known else "unknown",
                                   "missing_reason": None if known else reason, "method": row.get(native + "_method"),
                                   "source_id": row.get(native + "_source_id"),
                                   "data_year": clean(row.get(native + "_data_year")) or clean(row.get("socioeconomic_year")) or socioeconomic_year,
                                   "source_field": row.get(native + "_source_field"),
                                   "source_url": clean(row.get(native + "_source_url")) or source_metadata.get("estimate_source", {}).get("url")}
    for native, wire in (("poverty_rate", "poverty_rate_pct"), ("median_household_income", "income_usd")):
        result["metrics"][wire]["lower_90"] = clean(row.get(native + "_lower_90"))
        result["metrics"][wire]["upper_90"] = clean(row.get(native + "_upper_90"))
    return clean(result)


def _counties(artifacts) -> gpd.GeoDataFrame:
    frame = gpd.read_parquet(artifacts.county_path)
    if frame.crs is None or frame.crs.to_epsg() != 5070 or "county_geoid" not in frame or frame.county_geoid.duplicated().any():
        raise ApiError("Invalid cached county geography", 422, "invalid_socioeconomic_cache")
    if len(frame) > 10_000:
        raise ApiError("County layer exceeds the browser feature bound", 422, "layer_budget")
    return frame.sort_values("county_geoid")


def _verified_file(folder: Path, name: str, *, run_folder: Path | None = None) -> Path:
    path = folder / (name + ".parquet")
    return _verified_path(run_folder or folder, path)


def _verified_path(run_folder: Path, path: Path) -> Path:
    if not path.is_file():
        raise ApiError("Completed run is missing required result artifacts: " + path.name, 422, "missing_artifact")
    relative = path.relative_to(run_folder).as_posix()
    expected = read_json(run_folder / "run_metadata.json", {}).get("output_hashes", {}).get(relative)
    if expected and file_digest(path) != expected:
        raise ApiError("Completed run checksum mismatch: " + path.name, 422, "completed_run_checksum_mismatch")
    return path


def _verified_table(folder: Path, name: str, *, columns: list[str], run_folder: Path | None = None) -> pd.DataFrame:
    return pd.read_parquet(_verified_file(folder, name, run_folder=run_folder), columns=columns)


def context(root: Path, folder: Path, run_id: str, year=DEFAULT_BOUNDARY_YEAR, *, scenario="current") -> dict:
    year = boundary_year(year)
    selected = ArtifactReader(root / "runs/frontend_service/response_cache").context(folder, scenario)
    if selected != folder:
        _verified_path(folder, selected / "external_scenario.json")
    # Check bound scientific relationships before any local context preparation.
    regions = _verified_table(selected, "candidate_regions", columns=["region_id", "member_grid_ids", "n_cells"], run_folder=folder)
    if regions.region_id.duplicated().any():
        raise ApiError("Duplicate native region IDs", 422, "invalid_region_membership")
    if regions.empty and not (selected / "region_membership.parquet").is_file():
        membership = pd.DataFrame(columns=["region_id", "grid_id"])
    else:
        membership = _verified_table(selected, "region_membership", columns=["region_id", "grid_id"], run_folder=folder)
    if membership.duplicated(["region_id", "grid_id"]).any() or not set(membership.region_id) <= set(regions.region_id):
        raise ApiError("Invalid native region membership", 422, "invalid_region_membership")
    native_members = membership.groupby("region_id").grid_id.agg(set).to_dict()
    for region in regions.itertuples(index=False):
        ids = member_grid_ids(region.member_grid_ids)
        if len(ids) != region.n_cells or len(set(ids)) != len(ids) or set(ids) != native_members.get(region.region_id, set()):
            raise ApiError("Native region member IDs do not match persisted membership", 422, "invalid_region_membership")
    grid_folder = selected if (selected / "us_grid_dataset.parquet").is_file() else folder
    grid_path = _verified_file(grid_folder, "us_grid_dataset", run_folder=folder)
    try:
        artifacts = cached_artifacts(root, grid_path, year)
    except FileNotFoundError as exc:
        return {**_unavailable(year, str(exc)), "run_id": run_id, "scenario_id": scenario}
    except ValueError as exc:
        raise ApiError(str(exc), 422, "invalid_socioeconomic_cache") from exc
    meta = _metadata(artifacts.metadata, year)
    county_rows = {str(row["county_geoid"]): _county_record(row, year, meta["socioeconomic_year"], meta["source_metadata"])
                   for row in _counties(artifacts).drop(columns="geometry").to_dict("records")}
    crosswalk = pd.read_parquet(artifacts.crosswalk_path, columns=["candidate_id", "county_geoid", "intersection_area_km2"])
    coverage = pd.read_parquet(artifacts.coverage_path, columns=["candidate_id", "candidate_area_km2"])
    if (crosswalk.duplicated(["candidate_id", "county_geoid"]).any() or coverage.candidate_id.duplicated().any()
            or not set(crosswalk.county_geoid) <= set(county_rows)
            or not set(membership.grid_id) <= set(coverage.candidate_id)):
        raise ApiError("Invalid or incomplete grid-to-county relationships", 422, "invalid_socioeconomic_cache")
    if (not pd.to_numeric(crosswalk.intersection_area_km2, errors="coerce").ge(0).all()
            or not pd.to_numeric(coverage.candidate_area_km2, errors="coerce").gt(0).all()):
        raise ApiError("Invalid county intersection areas", 422, "invalid_socioeconomic_cache")
    total = membership.merge(coverage, left_on="grid_id", right_on="candidate_id", validate="many_to_one").groupby("region_id").candidate_area_km2.sum()
    joined = membership.merge(crosswalk, left_on="grid_id", right_on="candidate_id")
    positive = joined.loc[joined.intersection_area_km2.gt(0)]
    areas = positive.groupby(["region_id", "county_geoid"]).intersection_area_km2.sum()
    relations = {str(region): [] for region in sorted(regions.region_id)}
    for (region, geoid), area in areas.items():
        fraction = float(area / total.loc[region])
        if not math.isfinite(fraction) or fraction > 1 + 1e-8:
            raise ApiError("County intersection exceeds the native region area", 422, "invalid_socioeconomic_cache")
        relations[str(region)].append({**county_rows[str(geoid)], "overlap_area_km2": float(area), "overlap_fraction": fraction})
    partial = sum(sum(row["overlap_fraction"] for row in rows) < 1 - 1e-8 for rows in relations.values())
    if any(sum(row["overlap_fraction"] for row in rows) > 1 + 1e-8 for rows in relations.values()):
        raise ApiError("Overlapping county attribution exceeds the native region area", 422, "invalid_socioeconomic_cache")
    if partial:
        meta["warnings"].append(f"{partial} regions have partial county-boundary coverage; overlap fractions retain uncovered area.")
    return clean({"schema_version": SCHEMA_VERSION, "context_schema_version": "1.0.0", "run_id": run_id, "scenario_id": scenario, "available": True,
                  **meta, "fiscal_context": _fiscal(), "region_counties": relations,
                  "coverage_summary": {"counties": len(county_rows), "regions": len(relations),
                      "regions_with_county_support": sum(bool(rows) for rows in relations.values()),
                      "regions_with_partial_county_coverage": partial, "native_member_cells": int(membership.grid_id.nunique()),
                      "overlap_denominator": "Full saved member-grid geometry area in EPSG:5070; no renormalization"}})


def layer(root: Path, sublayer=None) -> dict:
    metric, separator, requested_year = (sublayer or "poverty").partition("@")
    year = boundary_year(requested_year) if separator else DEFAULT_BOUNDARY_YEAR
    if metric not in SUBLAYERS:
        raise ApiError("Unknown county economic sublayer", 422, "unavailable_layer")
    try:
        artifacts = cached_counties(root, year)
    except FileNotFoundError as exc:
        raise ApiError(str(exc), 422, "unavailable_layer") from exc
    except ValueError as exc:
        raise ApiError(str(exc), 422, "invalid_socioeconomic_cache") from exc
    meta = _metadata(artifacts.metadata, year)
    wire, label = SUBLAYERS[metric]
    features = []
    for row in _counties(artifacts).to_crs(4326).to_dict("records"):
        geometry, warning = valid_geometry(mapping(row["geometry"]))
        if geometry is None:
            raise ApiError("Cached county geometry cannot be displayed", 422, "invalid_socioeconomic_cache")
        county = _county_record(row, year, meta["socioeconomic_year"], meta["source_metadata"])
        value = county["metrics"][wire]
        features.append({"type": "Feature", "id": county["county_geoid"], "geometry": geometry,
                         "properties": {**county, **value, "source_metadata": {
                             key: meta["source_metadata"].get(key) for key in ("estimate_source", "boundary_source")}}})
    units = {feature["properties"]["unit"] for feature in features if feature["properties"]["value"] is not None}
    if len(units) > 1:
        raise ApiError("County source metrics have incompatible units", 422, "invalid_socioeconomic_cache")
    unit = next(iter(units)) if units else METRICS[wire][1]
    result = ArtifactReader._layer_payload("community_economic", features,
        f"{label} ({meta['socioeconomic_year']} SAIPE; {year} county boundaries)", unit, "neutral",
        "U.S. Census Bureau SAIPE and county boundaries", "; ".join(meta["warnings"]))
    return {**result, **meta, "warning": "; ".join(meta["warnings"])}


def capability(root: Path) -> dict:
    available, reason = False, "County economic source/configuration is unavailable locally; no HTTP downloads are performed."
    try:
        module = _geography()
        available = module.source_availability(root, boundary_year=DEFAULT_BOUNDARY_YEAR).get("available", False)
    except (FileNotFoundError, AttributeError, ValueError):
        pass
    return {"id": "community_economic", "label": "County economic need (2024 SAIPE)", "available": bool(available),
            "reason": None if available else reason,
            "sublayers": [{"id": key, "label": label, "available": bool(available)} for key, (_, label) in SUBLAYERS.items()],
            "boundary_years": list(BOUNDARY_YEARS), "default_boundary_year": DEFAULT_BOUNDARY_YEAR,
            "socioeconomic_year": SOCIOECONOMIC_YEAR, "context_only": True}
