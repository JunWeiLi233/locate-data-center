"""End-to-end rediscovery run on a quarantined synthetic mini model run (data_mode=synthetic).

The fixture is built in a temporary project root. It holds a 24 x 24 block of synthetic 1 km cells on the
real CONUS grid definition, a synthetic facility inventory in the IM3 layout, one synthetic county polygon
and a synthetic county Monte Carlo result. The decision policy is the repository's real regional scoring
profile. None of these values is geographic evidence.
"""
import hashlib
import json
import shutil
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import yaml
from shapely.geometry import Point, box

from dc_locator.fine_surface import CELL_SCHEMA
from dc_locator.geography.grid import make_grid_id
from dc_locator.io import _build_metadata
from dc_locator.model.fine_selection import profile_weights, score_window, summarize_window
from dc_locator.model.metrics import load_profile
from dc_locator.provenance import DataMode
from dc_rediscovery.geodesy import haversine_km
from dc_rediscovery.pipeline import run
from dc_rediscovery.surface import cell_centers

REPO = Path(__file__).resolve().parents[1]
GRID = {"crs": "EPSG:5070", "origin_x_m": -2500000.0, "origin_y_m": 3400000.0, "cell_size_m": 1000.0, "grid_scheme_version": 1,
        "id_row_col_digits": 4, "tile_size_cells": 25, "min_intersection_km2": 0.0, "study_areas": {}}
DEFINITION = "conus-epsg5070-ox-2500000-oy3400000-s1000m-v1"
EVIDENCE = {
    "potentially_suitable_land_frac": ("proxy", "usgs_annual_nlcd", "valid classes except 11,12,90,95", "frac", "2024"),
    "nlcd_coverage_frac": ("calculated", "usgs_annual_nlcd", "valid class mask", "frac", "2024"),
    "transmission_distance_km": ("proxy", "eia_energy_atlas", "transmission line geometry", "km", "2024"),
    "baseline_water_stress_score": ("observed", "wri_aqueduct40", "bws_score", "score_0_to_5", "1979-2019 baseline"),
    "baseline_water_stress_score_coverage_frac": ("calculated", "wri_aqueduct40", "valid bws_score mask", "frac", "1979-2019 baseline"),
    "grid_carbon_intensity_kg_per_mwh": ("proxy", "epa_egrid", "SRC2ERTA", "kg_CO2e_per_mwh", "2023"),
    "egrid_coverage_frac": ("calculated", "epa_egrid", "Subregion", "frac", "2023"),
}
CONSTANTS = [{"design_id": design, "scenario_id": "historical_static_2023", "e_facility_mwh": 840960.0, "w_site_m3": water,
              "e_facility_mwh_status": "calculated", "e_facility_mwh_confidence": "low", "e_facility_mwh_unit": "mwh",
              "w_site_m3_status": "calculated", "w_site_m3_confidence": "low", "w_site_m3_unit": "m3_consumed", "carbon_data_year": "2023"}
             for design, water in (("air_dry_assumed", 0.0), ("cold_plate_tower_assumed", 210240.0))]
ROW0, COL0, SIZE = 1100, 3900, 24


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _cells() -> pd.DataFrame:
    rows, cols = np.meshgrid(np.arange(ROW0, ROW0 + SIZE), np.arange(COL0, COL0 + SIZE), indexing="ij")
    rows, cols = rows.ravel(), cols.ravel()
    local_row, local_col = rows - ROW0, cols - COL0
    frame = pd.DataFrame({"grid_id": [make_grid_id(1000.0, int(r), int(c), 4) for r, c in zip(rows, cols)],
                          "parent_grid_id": [f"p{r // 50:04d}-{c // 50:04d}" for r, c in zip(rows, cols)],
                          "row": rows.astype("int32"), "col": cols.astype("int32"), "study_area_intersection_km2": 1.0,
                          "is_boundary_cell": False})
    # Synthetic gradients: carbon falls to the east, water stress rises to the south; one corner is unknown.
    frame["potentially_suitable_land_frac"] = np.where(local_row % 7 == 0, 0.6, 1.0)
    frame["nlcd_coverage_frac"] = 1.0
    frame["transmission_distance_km"] = (local_col % 5).astype(float)
    frame["baseline_water_stress_score"] = local_row / SIZE * 4.0
    frame["baseline_water_stress_score_coverage_frac"] = 1.0
    frame["grid_carbon_intensity_kg_per_mwh"] = np.where(local_col < SIZE // 2, 400.0, 150.0)
    frame["egrid_coverage_frac"] = 1.0
    unknown = (local_row >= SIZE - 3) & (local_col >= SIZE - 3)
    frame.loc[unknown, "baseline_water_stress_score"] = np.nan
    for column, (status, source, field, unit, year) in EVIDENCE.items():
        frame[column + "_status"] = status
        frame[column + "_confidence"] = "medium"
        frame[column + "_missing_reason"] = None
        frame[column + "_source_id"] = source
        frame[column + "_source_field"] = field
        frame[column + "_unit"] = unit
        frame[column + "_data_year"] = year
    frame.loc[unknown, "baseline_water_stress_score_status"] = "unknown"
    frame.loc[unknown, "baseline_water_stress_score_missing_reason"] = "synthetic gap"
    return frame


def _write_model_run(root: Path) -> None:
    (root / "configs").mkdir(parents=True)
    (root / "configs" / "grid_regional.yaml").write_text(yaml.safe_dump(GRID), encoding="utf-8")
    shutil.copy(REPO / "configs" / "scoring_profile_regional.yaml", root / "configs" / "scoring_profile_regional.yaml")
    profile = load_profile(root / "configs" / "scoring_profile_regional.yaml")
    folder = root / "runs" / "model_run"
    surface = folder / "national_fine_surface"
    surface.mkdir(parents=True)
    cells = _cells()
    metadata = _build_metadata("NationalFineSurfaceCell", "1.1.0", DataMode.SYNTHETIC, DEFINITION)
    table = pa.Table.from_pandas(cells[CELL_SCHEMA.names], schema=CELL_SCHEMA.with_metadata(metadata), preserve_index=False)
    pq.write_table(table, surface / "fine_surface_cells.parquet", row_group_size=200)
    weights = profile_weights(profile)
    constants = pd.DataFrame(CONSTANTS)
    scores = score_window(cells, profile, weights, constants)
    summaries = [summarize_window(parent, members.grid_id, scores.loc[members.index])
                 for parent, members in cells.groupby("parent_grid_id", sort=True)]
    pd.concat(summaries).to_parquet(surface / "fine_surface_parents.parquet", index=False)
    manifest = {"profile_id": profile.profile_id, "weights": weights, "design_constants": CONSTANTS, "grid_definition_id": DEFINITION,
                "data_mode": "synthetic", "stage_identity": "synthetic-test",
                "output_hashes": {name: _sha(surface / name) for name in ("fine_surface_cells.parquet", "fine_surface_parents.parquet")}}
    (surface / "fine_surface_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (folder / "profile_snapshot.json").write_text(json.dumps({"profile": profile.model_dump(mode="json")}), encoding="utf-8")
    cases = [{"case_id": "weight_land_focus", "category": "weights", "basis": "project_assumption", "rationale": "synthetic",
              "group_weights": {"energy_carbon": 0.2, "water_stewardship": 0.2, "grid_infrastructure": 0.2, "land": 0.4}}]
    (folder / "config_snapshot.json").write_text(json.dumps({"regional": {"grid_config": "configs/grid_regional.yaml"},
                                                             "run": {"validation": {"cases": cases}}}), encoding="utf-8")


def _grid():
    from dc_locator.config import GridConfig
    return GridConfig.model_validate(GRID)


def _write_facilities(root: Path, shift_deg: float = 0.0) -> Path:
    """Three synthetic facilities inside the block (one per IM3 layer) and one ~300 km away, off the surface."""
    grid = _grid()
    lat, lon = cell_centers(grid, np.array([ROW0 + 2, ROW0 + 20, ROW0 + 5, ROW0 - 300]),
                            np.array([COL0 + 20, COL0 + 3, COL0 + 22, COL0]))
    layers = ["building", "point", "building", "campus"]
    rows = []
    for index, (y, x) in enumerate(zip(lat, lon)):
        rows.append({"id": f"{index:011d}", "state": "Virginia", "state_abb": "VA", "state_id": "51", "county": "Synthetic County",
                     "county_id": "107", "operator": f"Operator {index}", "ref": None, "name": f"Synthetic DC {index}",
                     "sqft": None if layers[index] == "point" else 1000.0, "lon": float(x) + shift_deg, "lat": float(y),
                     "type": layers[index], "geometry": Point(float(x) + shift_deg, float(y))})
    path = root / "data" / "raw" / "synthetic_inventory" / f"inventory_{shift_deg:g}.gpkg"
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = gpd.GeoDataFrame(rows, crs="EPSG:4326")
    for layer in ("point", "building", "campus"):
        frame[frame["type"].eq(layer)].to_file(path, layer=layer, driver="GPKG")
    return path


def _write_counties(root: Path) -> None:
    lat, lon = cell_centers(_grid(), np.array([ROW0, ROW0 + SIZE]), np.array([COL0, COL0 + SIZE]))
    polygon = box(min(lon) - 0.5, min(lat) - 0.5, max(lon) + 0.5, max(lat) + 0.5)
    folder = root / "data" / "raw" / "synthetic_counties"
    folder.mkdir(parents=True)
    gpd.GeoDataFrame([{"GEOID": "51107", "NAME": "Synthetic", "NAMELSAD": "Synthetic County", "STUSPS": "VA",
                       "STATE_NAME": "Virginia", "geometry": polygon}], crs="EPSG:4326").to_file(folder / "counties.gpkg", driver="GPKG")
    path = folder / "counties.gpkg"
    (folder / "manifest.json").write_text(json.dumps({"counties.gpkg": {"sha256": _sha(path), "bytes": path.stat().st_size,
                                                                        "url": "synthetic://counties", "vintage": 2025}}), encoding="utf-8")


def _write_monte_carlo(root: Path) -> None:
    folder = root / "mc"
    folder.mkdir()
    scenarios = [{"scenario_id": "s1", "candidates": [{"candidate_id": "51107", "name": "Synthetic County", "state_abbr": "VA",
                                                         "pareto_frequency": 1.0, "expected_frontier": True, "robust_frontier": True}]}]
    results = folder / "results.json"
    results.write_text(json.dumps({"status": "completed", "run_id": "run_synthetic", "seed": 1, "config": {"simulation_count": 10},
                                   "scenarios": scenarios}), encoding="utf-8")
    (folder / "cache_integrity.json").write_text(json.dumps({"artifact_hashes": {"results.json": _sha(results)}}), encoding="utf-8")


def _config(root: Path, inventory: Path, *, draws: int = 20, name: str = "rediscovery_test") -> Path:
    declared = {"basis": "project_assumption", "rationale": "synthetic test assumption"}
    document = {
        "schema_version": "1.0.0", "analysis_name": name, "data_mode": "synthetic",
        "candidate_generation": {"source": "national_fine_surface", "model_run": "runs/model_run", "top_n_values": [2, 4],
                                 "min_candidate_distance_km": 5, "separation": declared, "design_selection": "best_design_per_cell",
                                 "write_evaluated_cells": True},
        "facilities": {"source_id": "im3_datacenter_atlas", "url": "synthetic://inventory", "path": inventory.relative_to(root).as_posix(),
                       "expected_bytes": inventory.stat().st_size, "expected_sha256": _sha(inventory), "version": "synthetic",
                       "doi": "10.0000/synthetic", "license": "synthetic fixture", "layers": ["point", "building", "campus"], "scope": "conus"},
        "validation": {"hit_radii_km": [2, 10], "classification": {"validated_max_km": 2, "emerging_min_km": 10, "declared": declared},
                       "hubs": {"linkage_km": 30, "min_facilities": 2, "declared": declared}},
        "baselines": {"draws": draws, "seed": 3, "area_weighted": True, "controls": [
            {"control_id": "uniform_conus", "label": "Uniform", "declared": declared},
            {"control_id": "infrastructure_plausible", "label": "Plausible", "max_transmission_distance_km": 3,
             "min_suitable_land_frac": 0.5, "declared": declared}]},
        "robustness": {"providers": [{"kind": "county_monte_carlo", "path": "mc/results.json", "label": "County MC"},
                                     {"kind": "table", "path": None, "label": "Grid MC"}], "declared_weight_cases": "from_model_run"},
        "places": {"county_boundaries": "data/raw/synthetic_counties/counties.gpkg",
                   "county_boundaries_manifest": "data/raw/synthetic_counties/manifest.json", "nearest_county_max_km": 5},
        "explanation": {"strong_normalized_min": 80, "weak_normalized_max": 50, "declared": declared},
        "surface_image": {"enabled": True, "width_px": 200},
        "tie_sensitivity": {"permutations": 5, "seed": 9},
    }
    path = root / "configs" / f"{name}_{draws}_{inventory.stem}.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


@pytest.fixture
def project(tmp_path):
    _write_model_run(tmp_path)
    _write_counties(tmp_path)
    _write_monte_carlo(tmp_path)
    return tmp_path


def test_end_to_end_blind_then_reveal(project):
    inventory = _write_facilities(project)
    manifest = run(_config(project, inventory), "runs/rediscovery_test", root=project, progress=None)
    folder = project / "runs" / "rediscovery_test"
    for name, digest in manifest["output_hashes"].items():
        assert _sha(folder / name) == digest
    timeline = manifest["timeline"]
    assert timeline["candidates_blind_written_at_utc"] < timeline["facilities_loaded_at_utc"]
    assert manifest["candidates_blind_sha256"] == _sha(folder / "candidates_blind.parquet")

    candidates = pd.read_parquet(folder / "candidates.parquet")
    assert candidates["rank"].tolist() == [1, 2, 3, 4]
    assert candidates.suitability_score.is_monotonic_decreasing
    for i in range(4):
        for j in range(i + 1, 4):
            assert haversine_km(candidates.lat[i], candidates.lon[i], candidates.lat[j], candidates.lon[j]) >= 5
    factors = pd.read_parquet(folder / "candidate_factors.parquet")
    totals = factors.groupby("rank").contribution.sum().to_numpy()
    assert totals == pytest.approx(candidates.suitability_score.to_numpy(), abs=1e-9)
    # Every reported distance is a direct haversine to the named facility; hit rates follow from them.
    direct = haversine_km(candidates.lat, candidates.lon, candidates.nearest_existing_dc_lat, candidates.nearest_existing_dc_lon)
    assert direct == pytest.approx(candidates.distance_to_nearest_existing_dc_km.to_numpy())
    summary = json.loads((folder / "validation_summary.json").read_text(encoding="utf-8"))
    for row in summary["validation"]["hit_rates"]:
        head = candidates.distance_to_nearest_existing_dc_km.to_numpy()[: row["top_n"]]
        assert row["hit_rate"] == pytest.approx(np.mean(head <= row["radius_km"]))
    expected = np.where(candidates.distance_to_nearest_existing_dc_km <= 2, "validated",
                        np.where(candidates.distance_to_nearest_existing_dc_km > 10, "emerging", "unresolved"))
    assert candidates.classification.tolist() == expected.tolist()
    # Robustness comes only from the county Monte Carlo record; explanations name unscored factors.
    assert candidates.robustness_score.eq(100.0).all() and candidates.robustness_spatial_support.eq("county").all()
    assert candidates.explanation.str.contains("not scored by this model").all()
    assert summary["candidate_generation"]["verification"]["persisted_parent_best_reproduction"]["status"] == "verified"
    assert summary["validation"]["presence_background"]["baseline"]["occupied_cells"] == 3
    assert (folder / "suitability_surface.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert pq.read_schema(folder / "candidates.parquet").metadata[b"dc_locator.data_mode"] == b"synthetic"

    # Same identity: verified reuse; a changed configuration cannot relabel the folder.
    assert run(_config(project, inventory), "runs/rediscovery_test", root=project, progress=None)["analysis_identity"] == manifest["analysis_identity"]
    with pytest.raises(ValueError, match="another rediscovery identity"):
        run(_config(project, inventory, draws=21), "runs/rediscovery_test", root=project, progress=None)


def test_blind_candidates_do_not_depend_on_the_facility_inventory(project):
    first = run(_config(project, _write_facilities(project)), "runs/first", root=project, progress=None)
    moved = _write_facilities(project, shift_deg=0.4)
    second = run(_config(project, moved, name="rediscovery_moved"), "runs/second", root=project, progress=None)
    assert first["analysis_identity"] != second["analysis_identity"]
    left = pd.read_parquet(project / "runs" / "first" / "candidates_blind.parquet").drop(columns="analysis_name")
    right = pd.read_parquet(project / "runs" / "second" / "candidates_blind.parquet").drop(columns="analysis_name")
    pd.testing.assert_frame_equal(left, right)
    revealed = pd.read_parquet(project / "runs" / "second" / "candidates.parquet")
    original = pd.read_parquet(project / "runs" / "first" / "candidates.parquet")
    assert not np.allclose(revealed.distance_to_nearest_existing_dc_km, original.distance_to_nearest_existing_dc_km)


def test_outputs_stay_inside_owned_folders(project):
    inventory = _write_facilities(project)
    with pytest.raises(ValueError):
        run(_config(project, inventory), "data/processed/rediscovery", root=project, progress=None)
    with pytest.raises(ValueError):
        run(_config(project, inventory), "runs/phase7_overwrite", root=project, progress=None)
