"""Unit-explicit accounting; no engineering priors or future trajectories are implied."""

import math
from collections.abc import Sequence

# International avoirdupois definition, distinct from metric tonnes.
LB_TO_KG = 0.45359237


def checked(value: float, name: str, minimum: float = 0, maximum: float = math.inf) -> float:
    """Reject missing, nonfinite, boolean and out-of-range physical inputs."""
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{name} must be a finite number")
    value = float(value)
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must lie in [{minimum}, {maximum}]")
    return value


def price_to_usd_per_mwh(cents_per_kwh: float) -> float:
    """Convert cents/kWh to USD/MWh: 1,000 kWh/MWh divided by 100 cents/USD."""
    return checked(cents_per_kwh, "cents_per_kwh") * 10


def emissions_to_kg_per_mwh(lb_per_mwh: float) -> float:
    """Convert an eGRID total-output CO2e rate from lb/MWh to kg/MWh."""
    return checked(lb_per_mwh, "lb_per_mwh") * LB_TO_KG


def annual_accounting(*, it_mw: float, utilization: float, annual_hours: float,
                      pue: float, wue_l_per_kwh: float | None,
                      price_usd_per_mwh: float | None, grid_kg_per_mwh: float | None,
                      wue_basis: str = "it", indirect_m3_per_mwh: float | None = None) -> dict:
    """Compute one year at a common workload; null factors remain null outcomes.

    WUE denotes consumption, not withdrawals. Its energy denominator is explicit.
    Indirect consumption, if supplied, remains separate to avoid double counting.
    """
    it_energy = (checked(it_mw, "it_mw") * checked(utilization, "utilization", 0, 1)
                 * checked(annual_hours, "annual_hours", 0, 8784))
    facility_energy = it_energy * checked(pue, "pue", 1)
    if wue_basis not in {"it", "facility"}:
        raise ValueError("wue_basis must be it or facility")
    # MWh->kWh and liters->m3 cancel; no extra factor of 1,000 belongs here.
    cooling_energy = it_energy if wue_basis == "it" else facility_energy
    result = {
        "it_energy_mwh": it_energy,
        "facility_energy_mwh": facility_energy,
        "electricity_cost_usd": None if price_usd_per_mwh is None else facility_energy * checked(price_usd_per_mwh, "price"),
        "operational_co2e_tonnes": None if grid_kg_per_mwh is None else facility_energy * checked(grid_kg_per_mwh, "carbon") / 1000,
        "direct_water_consumption_m3": None if wue_l_per_kwh is None else cooling_energy * checked(wue_l_per_kwh, "wue"),
        "indirect_water_consumption_m3": None if indirect_m3_per_mwh is None else facility_energy * checked(indirect_m3_per_mwh, "indirect water"),
    }
    # Large finite inputs can still overflow multiplication; never export infinity.
    if any(v is not None and not math.isfinite(v) for v in result.values()):
        raise ValueError("accounting overflow")
    return result


def lifetime_accounting(annual_rows: Sequence[dict], *, years: Sequence[int], base_year: int,
                        discount_rate: float, currency_convention: str) -> dict:
    """Sum explicit annual trajectories and discount end-of-year monetary costs.

    Years identify operating years; a payment in the base year is discounted once
    (exponent year-base_year+1). Real prices require a real rate, nominal prices a
    nominal rate. Carbon and water are never discounted. Missing annual factors
    make the associated lifetime total unknown rather than a partial sum.
    """
    rate = checked(discount_rate, "discount_rate", -0.99)
    if currency_convention not in {"real", "nominal"}:
        raise ValueError("currency_convention must be real or nominal")
    if (not annual_rows or len(annual_rows) != len(years) or isinstance(base_year, bool)
            or not isinstance(base_year, int)):
        raise ValueError("supply annual rows, integer base year and matching years")
    if any(isinstance(y, bool) or not isinstance(y, int) or y < base_year for y in years):
        raise ValueError("operating years must be integers at or after base_year")
    if list(years) != list(range(years[0], years[0] + len(years))):
        raise ValueError("operating years must be consecutive and ascending")
    expected_keys = set(annual_rows[0])
    if any(set(row) != expected_keys for row in annual_rows):
        raise ValueError("all annual rows must have identical accounting fields")
    totals = {}
    for key in annual_rows[0]:
        # Apply discounting only to monetary fields, preserving physical totals.
        values = [row[key] for row in annual_rows]
        if any(v is None for v in values):
            totals[key] = None
            continue
        values = [checked(v, key) for v in values]
        if key == "electricity_cost_usd":
            values = [v / (1 + rate) ** (y - base_year + 1) for v, y in zip(values, years)]
        total = math.fsum(values)
        if not math.isfinite(total):
            raise ValueError("lifetime accounting overflow")
        totals[key] = total
    return {"totals": totals, "discount_rate": rate, "currency_convention": currency_convention,
            "base_year": base_year, "years": list(years), "cash_flow_timing": "end of operating year"}
