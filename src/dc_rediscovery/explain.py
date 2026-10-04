"""'Why was this location recommended?': explanation text generated from a candidate's own factor scores.

The rules are deterministic, and their thresholds are declared presentation assumptions in the
configuration. A location-dependent criterion is a strength when its normalized score is at least
``strong_normalized_min`` and a weakness when it is at most ``weak_normalized_max``. Strengths are ordered
by their contribution to the score. Design-level criteria (direct site water) do not vary by location, so
they are stated as an assumption, not as a strength of the place. Criteria the model does not score are
named as not scored. They are never described as favourable or as zero.
"""
from __future__ import annotations

import pandas as pd

NOT_SCORED = {
    "fiber": "Fiber/connectivity is not scored: FCC broadband evidence is BLOCKED and availability would not prove diverse data-center fiber.",
    "climate": "Climate/cooling conditions are not scored: annual PUE/WUE are constant design scenarios with no climatic dependence.",
    "natural_hazard": "Natural hazards are not scored nationally: flood, wildfire and protected-area exposure are informational only in refined regional windows.",
    "energy_cost": "Energy cost is not scored by the grid model; tariffs exist only as context in the separate county model.",
}
USER_FACTOR_MAP = {
    "power": ["transmission_proximity"],
    "carbon": ["annual_electricity_co2e"],
    "water": ["local_baseline_water_stress", "annual_site_water_consumption"],
    "land": ["suitable_land_fraction"],
    "fiber": [], "climate": [], "natural_hazard": [], "energy_cost": [],
}


def _phrase(metric_id: str, row, strong: bool) -> str:
    value = row["raw_value"]
    better = f"better than {row['national_percentile']:.0f}% of valued CONUS cells"
    if metric_id == "annual_electricity_co2e":
        intensity = row.get("carbon_intensity_kg_per_mwh")
        text = f"{intensity:.0f} kg CO2e/MWh 2023 eGRID subregion average" if intensity is not None else "regional eGRID average"
        return (f"a low-carbon regional electricity grid ({text}; {better})" if strong
                else f"a carbon-intensive regional electricity grid ({text})")
    if metric_id == "local_baseline_water_stress":
        return (f"low baseline basin water stress (Aqueduct {value:.1f} of 5)" if strong
                else f"high baseline basin water stress (Aqueduct {value:.1f} of 5)")
    if metric_id == "transmission_proximity":
        return (f"a mapped EIA transmission line {value:.1f} km away (proximity only, not available capacity)" if strong
                else f"the nearest mapped transmission line {value:.0f} km away")
    if metric_id == "suitable_land_fraction":
        return (f"{100 * value:.0f}% potentially suitable land cover in the 1 km cell (NLCD proxy, not parcel availability)" if strong
                else f"only {100 * value:.0f}% potentially suitable land cover in the 1 km cell")
    return metric_id.replace("_", " ")


def _join(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def explain(factors: pd.DataFrame, *, strong_min: float, weak_max: float, design_id: str, place: str | None) -> dict:
    """Return explanation text plus the strengths/weaknesses it was built from (one candidate's factor rows)."""
    location = factors[factors.location_dependent].sort_values(["contribution", "metric_id"], ascending=[False, True])
    strengths = location[location.normalized_score >= strong_min]
    weaknesses = location[location.normalized_score <= weak_max]
    where = place or "This site"
    if len(strengths):
        sentence = f"{where} ranks highly because of {_join([_phrase(m, r, True) for m, r in zip(strengths.metric_id, strengths.to_dict('records'))])}."
    else:
        sentence = f"{where} has no location criterion at or above {strong_min:g} on the model's 0–100 scale; its rank comes from balanced moderate criteria."
    parts = [sentence]
    if len(weaknesses):
        parts.append(f"It is weaker on {_join([_phrase(m, r, False) for m, r in zip(weaknesses.metric_id, weaknesses.to_dict('records'))])}.")
    design = factors[~factors.location_dependent]
    for row in design.to_dict("records"):
        if row["metric_id"] == "annual_site_water_consumption":
            parts.append(f"Its cooling design, {design_id}, assumes {row['raw_value']:,.0f} m³ of direct site water a year. That is a design assumption, the same everywhere, not a property of this place.")
    parts.append("Fiber, climate/cooling conditions, natural hazards and energy cost are not scored by this model and still need site-level due diligence.")
    return {"explanation": " ".join(parts), "strengths": strengths.metric_id.tolist(), "weaknesses": weaknesses.metric_id.tolist(),
            "explanation_basis": f"normalized criterion ≥ {strong_min:g} is a strength, ≤ {weak_max:g} a weakness (declared presentation rule)"}
