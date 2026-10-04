"""Generated explanations come from the candidate's own factors and never claim unscored strengths."""
import pandas as pd

from dc_rediscovery.explain import explain


def _factors(**normalized):
    raw = {"annual_electricity_co2e": 92_000.0, "local_baseline_water_stress": 0.4, "transmission_proximity": 1.5,
           "suitable_land_fraction": 0.97, "annual_site_water_consumption": 0.0}
    weights = {"annual_electricity_co2e": 0.25, "local_baseline_water_stress": 0.125, "transmission_proximity": 0.25,
               "suitable_land_fraction": 0.25, "annual_site_water_consumption": 0.125}
    rows = []
    for metric, value in normalized.items():
        rows.append({"metric_id": metric, "normalized_score": value, "contribution": weights[metric] * value, "raw_value": raw[metric],
                     "national_percentile": 97.0, "location_dependent": metric != "annual_site_water_consumption",
                     "carbon_intensity_kg_per_mwh": 110.0 if metric == "annual_electricity_co2e" else None})
    return pd.DataFrame(rows)


def test_strengths_follow_contribution_order_and_weaknesses_are_named():
    factors = _factors(annual_electricity_co2e=90.8, local_baseline_water_stress=92.0, transmission_proximity=40.0,
                       suitable_land_fraction=97.0, annual_site_water_consumption=100.0)
    result = explain(factors, strong_min=80, weak_max=50, design_id="air_dry_assumed", place="Clinton County, NY")
    assert result["strengths"] == ["suitable_land_fraction", "annual_electricity_co2e", "local_baseline_water_stress"]
    assert result["weaknesses"] == ["transmission_proximity"]
    text = result["explanation"]
    assert text.startswith("Clinton County, NY ranks highly because of 97% potentially suitable land cover")
    assert "110 kg CO2e/MWh" in text and "Aqueduct 0.4 of 5" in text
    assert "weaker on the nearest mapped transmission line 2 km away" in text
    # Design-level water is an assumption, never a strength of the place; unscored factors are named as unscored.
    assert "annual_site_water_consumption" not in result["strengths"]
    assert "design assumption" in text
    assert "not scored by this model" in text
    for claim in ("fiber connectivity is strong", "low hazard", "favorable cooling"):
        assert claim not in text.lower()


def test_no_strength_produces_a_neutral_sentence():
    factors = _factors(annual_electricity_co2e=60.0, local_baseline_water_stress=70.0, transmission_proximity=65.0,
                       suitable_land_fraction=75.0, annual_site_water_consumption=100.0)
    result = explain(factors, strong_min=80, weak_max=50, design_id="d", place=None)
    assert result["strengths"] == [] and result["weaknesses"] == []
    assert result["explanation"].startswith("This site has no location criterion at or above 80")
