"""Independent golden calculations and invariants for the physical accounting."""

import math
import pytest

from dataclocator.accounting import (annual_accounting, lifetime_accounting,
                                     price_to_usd_per_mwh, emissions_to_kg_per_mwh)


@pytest.fixture
def inputs():
    """Use explicit test numbers, never engineering defaults for real locations."""
    return dict(it_mw=100, utilization=0.85, annual_hours=8760, pue=1.2,
                wue_l_per_kwh=0.2, price_usd_per_mwh=50, grid_kg_per_mwh=400)


def test_hand_calculation(inputs):
    """Compare every physical unit with independently evaluated values."""
    row = annual_accounting(**inputs)
    assert row["it_energy_mwh"] == 744600
    assert row["facility_energy_mwh"] == 893520
    assert row["electricity_cost_usd"] == 44676000
    assert row["operational_co2e_tonnes"] == 357408
    assert row["direct_water_consumption_m3"] == 148920


def test_source_unit_conversions():
    """Prevent cents/dollars, pounds/kilograms and kWh/MWh factor errors."""
    assert price_to_usd_per_mwh(7.5) == 75
    assert emissions_to_kg_per_mwh(1000) == pytest.approx(453.59237)


def test_workload_scaling(inputs):
    """Doubling IT MW must double each outcome at fixed PUE and WUE."""
    a = annual_accounting(**inputs)
    b = annual_accounting(**(inputs | {"it_mw": 200}))
    for key in a:
        if a[key] is not None:
            assert b[key] == 2 * a[key]


def test_cooling_bases_and_indirect_water(inputs):
    """Facility-denominator WUE differs; indirect water remains a separate quantity."""
    row = annual_accounting(**inputs, wue_basis="facility", indirect_m3_per_mwh=0.5)
    assert row["direct_water_consumption_m3"] == 178704
    assert row["indirect_water_consumption_m3"] == 446760


def test_pue_and_water_monotonicity(inputs):
    """PUE raises facility load but not direct water defined per IT energy."""
    a = annual_accounting(**inputs)
    b = annual_accounting(**(inputs | {"pue": 1.5}))
    assert b["electricity_cost_usd"] > a["electricity_cost_usd"]
    assert b["operational_co2e_tonnes"] > a["operational_co2e_tonnes"]
    assert b["direct_water_consumption_m3"] == a["direct_water_consumption_m3"]
    c = annual_accounting(**(inputs | {"wue_l_per_kwh": 0.4}))
    assert c["direct_water_consumption_m3"] == 2 * a["direct_water_consumption_m3"]


def test_missing_is_not_zero(inputs):
    """Unknown prices, emission rates and WUE must not become zero impact."""
    row = annual_accounting(**(inputs | {"price_usd_per_mwh": None, "grid_kg_per_mwh": None, "wue_l_per_kwh": None}))
    assert row["electricity_cost_usd"] is None
    assert row["operational_co2e_tonnes"] is None
    assert row["direct_water_consumption_m3"] is None
    assert annual_accounting(**(inputs | {"wue_l_per_kwh": 0}))["direct_water_consumption_m3"] == 0


@pytest.mark.parametrize("field,value", [("pue", 0.9), ("utilization", 1.1), ("utilization", -0.1),
    ("annual_hours", 9000), ("wue_l_per_kwh", -1), ("it_mw", math.inf), ("grid_kg_per_mwh", math.nan),
    ("price_usd_per_mwh", -1), ("pue", None), ("pue", True)])
def test_invalid_inputs_rejected(inputs, field, value):
    """Invalid engineering ranges and nonfinite numbers fail before export."""
    with pytest.raises(ValueError):
        annual_accounting(**(inputs | {field: value}))


def test_end_year_discount_and_explicit_trajectories(inputs):
    """Check independently: 100/1.1 + 200/1.1^2, while physical totals remain sums."""
    a = annual_accounting(**inputs) | {"electricity_cost_usd": 100}
    b = annual_accounting(**(inputs | {"grid_kg_per_mwh": 200})) | {"electricity_cost_usd": 200}
    result = lifetime_accounting([a, b], years=[2025, 2026], base_year=2025,
                                 discount_rate=0.1, currency_convention="real")["totals"]
    assert result["electricity_cost_usd"] == pytest.approx(256.198347107438)
    assert result["operational_co2e_tonnes"] == 536112
    assert result["direct_water_consumption_m3"] == 297840


@pytest.mark.parametrize("horizon", [20, 25, 30])
def test_constant_fixture_horizon(inputs, horizon):
    """Constant synthetic fixtures validate summing; they are not future scenarios."""
    row = annual_accounting(**inputs)
    result = lifetime_accounting([row] * horizon, years=list(range(2027, 2027 + horizon)),
                                 base_year=2025, discount_rate=0, currency_convention="nominal")["totals"]
    for key in row:
        if row[key] is not None:
            assert result[key] == horizon * row[key]


def test_missing_lifetime_input_and_opening_delay(inputs):
    """A missing operating year invalidates its total; opening delay shifts discount."""
    row = annual_accounting(**inputs)
    later = lifetime_accounting([row], years=[2027], base_year=2025, discount_rate=0.1, currency_convention="real")
    assert later["totals"]["electricity_cost_usd"] == pytest.approx(44676000 / 1.1 ** 3)
    result = lifetime_accounting([row, row | {"direct_water_consumption_m3": None}],
                                 years=[2025, 2026], base_year=2025, discount_rate=0, currency_convention="real")
    assert result["totals"]["direct_water_consumption_m3"] is None


def test_bad_trajectory_and_basis(inputs):
    """Reject skipped years, duplicate years and unspecified currency conventions."""
    row = annual_accounting(**inputs)
    for years in [[2025, 2027], [2025, 2025], [2024, 2025]]:
        with pytest.raises(ValueError):
            lifetime_accounting([row, row], years=years, base_year=2025, discount_rate=0, currency_convention="real")
    with pytest.raises(ValueError):
        lifetime_accounting([row], years=[2025], base_year=2025, discount_rate=0, currency_convention="unknown")
    with pytest.raises(ValueError):
        annual_accounting(**inputs, wue_basis="unspecified")
