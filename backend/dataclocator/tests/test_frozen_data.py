"""Acceptance checks on the real downloaded cohort, skipped only when unacquired."""

import json
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
# Pure arithmetic tests still work in a fresh checkout without large downloads.
pytestmark = pytest.mark.skipif(not (ROOT / "data/processed/candidates.parquet").exists(), reason="run acquire and preprocess for real-data acceptance checks")


def test_real_county_join_coverage():
    """Check the frozen cohort joins exactly once, retaining geography strings."""
    candidates = pd.read_parquet(ROOT / "data/processed/candidates.parquet")
    selected = json.loads((ROOT / "configs/candidates.json").read_text())["county_fips"]
    assert set(candidates.county_fips) == set(selected)
    assert len(candidates) == 45
    assert not candidates.county_fips.duplicated().any()
    assert candidates.state_fips.eq(candidates.county_fips.str[:2]).all()
    assert "01089" in candidates.county_fips.tolist()
    assert candidates.valid_months.eq(12).all()
    assert candidates.climate_station_distance_km.between(0, 100).all()
    assert candidates.feasibility_status.eq("unverified").all()


def test_real_spatial_area_and_climate_evidence():
    """Coverage fractions cannot exceed whole county area beyond roundoff."""
    water = pd.read_parquet(ROOT / "data/processed/water_overlaps.parquet")
    totals = water.groupby("county_fips").county_area_fraction.sum()
    assert len(totals) == 45
    assert totals.between(0, 1 + 1e-8).all()
    assert totals.loc["10001"] < 0.8
    climate = pd.read_parquet(ROOT / "data/processed/climate_monthly.parquet")
    assert climate.groupby("county_fips").size().eq(12).all()
    assert climate.temperature_c.between(-50, 60).all()
    assert climate.cooling_degree_days_f_base65.ge(0).all()


def test_real_emissions_conversion_and_hazard_pagination():
    """Verify source-rate conversion and complete pagination on the real releases."""
    grid = pd.read_parquet(ROOT / "data/processed/grid_regions.parquet")
    assert grid.grid_co2e_kg_per_mwh.tolist() == pytest.approx((grid.grid_co2e_lb_per_mwh * 0.45359237).tolist())
    assert grid.renewable_generation_fraction.between(0, 1).all()
    hazards = pd.read_parquet(ROOT / "data/processed/hazards.parquet")
    assert len(hazards) == json.loads((ROOT / "data/raw/fema/1.20/count.json").read_text())["count"]
    assert not hazards.county_fips.duplicated().any()


def test_json_preserves_unknown_engineering_inputs():
    """Exported JSON is finite and unknown feasibility/engineering stays explicit."""
    def reject_constant(value):
        """The JSON parser must reject NaN/Infinity rather than quietly accept them."""
        raise ValueError(f"nonstandard JSON constant {value}")
    data = json.loads((ROOT / "outputs/task2/candidates.json").read_text(), parse_constant=reject_constant)
    assert data["engineering_assumptions"]["pue"] is None
    assert data["engineering_assumptions"]["wue_l_per_kwh_it"] is None
    for candidate in data["candidates"]:
        assert isinstance(candidate["county_fips"], str)
        assert all(item["status"] == "unverified" for item in candidate["feasibility"].values())
