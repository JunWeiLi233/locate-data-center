"""Tests for dc_locator.config: loading/validating configs/*.yaml."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from dc_locator.config import (
    ConfigValidationError,
    GridConfig,
    StudyAreaBBox,
    config_snapshot_hash,
    load_constraints_config,
    load_cooling_designs_config,
    load_facility_config,
    load_grid_config,
    load_run_config,
    load_scenarios_config,
    load_scoring_config,
    load_sources_config,
)
from dc_locator.paths import configs_dir, project_root


# --------------------------------------------------------------------------
# The real configs/*.yaml files this phase ships -- must load and validate.
# --------------------------------------------------------------------------


def test_real_grid_yaml_loads_and_matches_grid_contract() -> None:
    cfg = load_grid_config()
    assert cfg.crs == "EPSG:5070"
    assert cfg.origin_x_m == -2_500_000.0
    assert cfg.origin_y_m == 3_400_000.0
    assert cfg.cell_size_m == 10_000.0
    assert cfg.grid_definition_id() == "conus-epsg5070-ox-2500000-oy3400000-s10000m-v1"
    assert set(cfg.study_areas) == {"dev_tiny", "dev_default"}


@pytest.mark.parametrize(
    "loader,filename",
    [
        (load_sources_config, "sources.yaml"),
        (load_facility_config, "facility.yaml"),
        (load_cooling_designs_config, "cooling_designs.yaml"),
        (load_constraints_config, "constraints.yaml"),
        (load_scoring_config, "scoring.yaml"),
        (load_scenarios_config, "scenarios.yaml"),
        (load_run_config, "run.yaml"),
    ],
)
def test_all_eight_config_files_exist_and_validate(loader, filename) -> None:
    path = configs_dir() / filename
    assert path.is_file(), f"{filename} is required by AGENTS.md section 5 but missing."
    loader()  # must not raise


def test_facility_placeholder_is_labelled_project_assumption() -> None:
    cfg = load_facility_config()
    assert len(cfg.facilities) >= 1
    for entry in cfg.facilities:
        assert entry.basis  # every numeric coefficient must cite a basis (AGENTS.md section 3.2)


@pytest.mark.parametrize("field", [
    "peak_it_power_mw", "average_it_load_factor", "target_opening_year",
    "operating_lifetime_years", "hours_in_modeled_year", "minimum_land_area_km2",
])
def test_facility_yaml_rejects_boolean_numeric_fields(tmp_path: Path, field: str) -> None:
    data=yaml.safe_load((configs_dir()/"facility.yaml").read_text("utf-8"))
    data["facilities"][0][field]=True
    path=tmp_path/"facility.yaml"
    path.write_text(yaml.safe_dump(data,sort_keys=False),encoding="utf-8")
    with pytest.raises(ConfigValidationError,match="numeric|integer"):
        load_facility_config(path)


# --------------------------------------------------------------------------
# GridConfig validation rules.
# --------------------------------------------------------------------------


def test_grid_config_rejects_wrong_crs() -> None:
    with pytest.raises(Exception):  # pydantic ValidationError wrapped inside the model_validator
        GridConfig(
            crs="EPSG:4326", origin_x_m=0.0, origin_y_m=0.0, cell_size_m=10000.0,
            grid_scheme_version=1, id_row_col_digits=4, tile_size_cells=25,
            min_intersection_km2=0.0, study_areas={},
        )


def test_grid_config_rejects_non_positive_cell_size() -> None:
    with pytest.raises(Exception):
        GridConfig(
            crs="EPSG:5070", origin_x_m=0.0, origin_y_m=0.0, cell_size_m=0.0,
            grid_scheme_version=1, id_row_col_digits=4, tile_size_cells=25,
            min_intersection_km2=0.0, study_areas={},
        )


@pytest.mark.parametrize("field", [
    "origin_x_m", "origin_y_m", "cell_size_m", "min_intersection_km2",
    "grid_scheme_version", "id_row_col_digits", "tile_size_cells",
])
def test_grid_config_rejects_boolean_numeric_fields(field: str) -> None:
    values=dict(crs="EPSG:5070",origin_x_m=-2_500_000,origin_y_m=3_400_000,
        cell_size_m=10_000,grid_scheme_version=1,id_row_col_digits=4,
        tile_size_cells=25,min_intersection_km2=0,study_areas={})
    values[field]=True
    with pytest.raises(Exception,match="numeric|integer"):
        GridConfig.model_validate(values)


@pytest.mark.parametrize("field", ["lon_min","lat_min","lon_max","lat_max"])
def test_study_area_bbox_rejects_boolean_coordinates(field: str) -> None:
    values=dict(lon_min=-100,lat_min=30,lon_max=-90,lat_max=40)
    values[field]=True
    with pytest.raises(Exception,match="numeric"):
        StudyAreaBBox.model_validate(values)


def test_grid_config_warns_on_bad_nesting() -> None:
    with pytest.warns(UserWarning, match="does not evenly divide 100000"):
        GridConfig(
            crs="EPSG:5070", origin_x_m=0.0, origin_y_m=0.0, cell_size_m=3000.0,
            grid_scheme_version=1, id_row_col_digits=4, tile_size_cells=25,
            min_intersection_km2=0.0, study_areas={},
        )


def test_grid_config_rejects_extra_key(tmp_path: Path) -> None:
    data = yaml.safe_load((configs_dir() / "grid.yaml").read_text("utf-8"))
    data["unexpected_key"] = 123
    bad_path = tmp_path / "grid.yaml"
    bad_path.write_text(yaml.dump(data), encoding="utf-8")
    with pytest.raises(ConfigValidationError):
        load_grid_config(bad_path)


def test_load_grid_config_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_grid_config(tmp_path / "does_not_exist.yaml")


def test_study_area_bbox_rejects_inverted_bounds() -> None:
    with pytest.raises(Exception):
        StudyAreaBBox(lon_min=-93.0, lat_min=29.0, lon_max=-98.0, lat_max=33.0)


# --------------------------------------------------------------------------
# config_snapshot_hash: deterministic, order-sensitive.
# --------------------------------------------------------------------------


def test_config_snapshot_hash_deterministic_and_order_sensitive() -> None:
    grid_path = configs_dir() / "grid.yaml"
    run_path = configs_dir() / "run.yaml"
    h1 = config_snapshot_hash([grid_path, run_path])
    h2 = config_snapshot_hash([grid_path, run_path])
    h3 = config_snapshot_hash([run_path, grid_path])
    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 64  # sha256 hex digest


def test_config_snapshot_hash_changes_with_content(tmp_path: Path) -> None:
    file_a = tmp_path / "a.yaml"
    file_a.write_text("x: 1\n", encoding="utf-8")
    h_before = config_snapshot_hash([file_a])
    file_a.write_text("x: 2\n", encoding="utf-8")
    h_after = config_snapshot_hash([file_a])
    assert h_before != h_after
