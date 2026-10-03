"""Regression coverage for Phase 1 identity, area and allocation defects."""

from dataclasses import replace

import geopandas as gpd
import numpy as np
import pytest
from pydantic import ValidationError
from shapely.geometry import box

from dc_locator.config import GridConfig, load_grid_config
from dc_locator.geography import grid as grid_module
from dc_locator.geography.grid import GridIntegrityError, generate_national_grid
from dc_locator.schemas import GridCell


def test_fractional_grid_definition_parameters_do_not_collide():
    original = load_grid_config()
    for parameter in ("origin_x_m", "origin_y_m", "cell_size_m"):
        changed = original.model_copy(update={parameter: getattr(original, parameter) + 0.25})
        assert changed.grid_definition_id() != original.grid_definition_id()


def test_generated_ids_include_changed_origin_or_scheme(synthetic_grid_config, synthetic_boundary):
    first, _ = generate_national_grid(synthetic_grid_config, synthetic_boundary)
    changed_origin = synthetic_grid_config.model_copy(update={"origin_x_m": -0.25})
    second, _ = generate_national_grid(changed_origin, synthetic_boundary)
    changed_scheme = synthetic_grid_config.model_copy(update={"grid_scheme_version": 2})
    third, _ = generate_national_grid(changed_scheme, synthetic_boundary)
    assert set(first.grid_id).isdisjoint(second.grid_id)
    assert set(first.grid_id).isdisjoint(third.grid_id)


def test_fractional_cell_sizes_have_distinct_ids(synthetic_grid_config, synthetic_boundary):
    first, _ = generate_national_grid(synthetic_grid_config, synthetic_boundary)
    changed = synthetic_grid_config.model_copy(update={"cell_size_m": 10.25})
    second, _ = generate_national_grid(changed, synthetic_boundary)
    assert set(first.grid_id).isdisjoint(second.grid_id)


@pytest.mark.parametrize("parameter", ["origin_x_m", "origin_y_m", "cell_size_m", "min_intersection_km2"])
def test_grid_config_rejects_nonfinite_parameters(parameter):
    values = load_grid_config().model_dump()
    values[parameter] = float("inf")
    with pytest.raises(ValidationError):
        GridConfig.model_validate(values)


def test_grid_memory_guard_runs_before_meshgrid(monkeypatch, synthetic_grid_config, synthetic_boundary):
    monkeypatch.setattr(grid_module, "_MAX_CANDIDATE_CELLS", 1)

    def reject_allocation(*args, **kwargs):
        pytest.fail("allocation attempted before candidate-count limit")

    monkeypatch.setattr(np, "meshgrid", reject_allocation)
    with pytest.raises(RuntimeError, match="Candidate grid"):
        generate_national_grid(synthetic_grid_config, synthetic_boundary)


def test_grid_schema_accepts_only_roundoff_share_excess(synthetic_grid_config, synthetic_boundary):
    frame, _ = generate_national_grid(synthetic_grid_config, synthetic_boundary)
    cell = frame.iloc[0].to_dict()
    cell["state_share_primary_frac"] = 1.0 + 4e-16
    cell["county_share_primary_frac"] = 1.0 + 4e-16
    GridCell.model_validate(cell)
    cell["county_share_primary_frac"] = 1.01
    with pytest.raises(ValidationError):
        GridCell.model_validate(cell)


def test_county_area_outside_conus_is_detected(synthetic_grid_config, synthetic_boundary):
    counties = gpd.GeoDataFrame(
        {"GEOID": ["A1000"], "NAME": ["Overhanging county"], "STATEFP": ["01"]},
        geometry=[box(0, -20, 30, 10)], crs="EPSG:5070",
    )
    mismatched = replace(synthetic_boundary, counties=counties)
    with pytest.raises(GridIntegrityError, match="county_share_primary_frac"):
        generate_national_grid(synthetic_grid_config, mismatched)
