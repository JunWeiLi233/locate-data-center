"""County-supported comparison with operating facilities, never optimality labels.

Inputs are already acquired and administratively matched outside the model. A
county observation supports a range over intersecting cells, not a point score.
Facility capacity without a compatible IT/system boundary is not a measurement
of the illustrative facility's annual energy, water or emissions.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


KEYS = ["grid_id", "design_id", "scenario_id"]
RAW_METRICS = [
    "raw_annual_electricity_co2e", "raw_annual_site_water_consumption",
    "raw_local_baseline_water_stress", "raw_transmission_proximity",
    "raw_suitable_land_fraction",
]


def compare_county_support(reference: pd.DataFrame, grid: pd.DataFrame,
                           ranked: pd.DataFrame) -> pd.DataFrame:
    """Return one uncertain spatial comparison per reference/design/scenario.

    ``county_geoid_all`` must be an explicit list from a geographic adapter.
    An uncomputed fine-grid county is OUTSIDE_EVALUATED_DOMAIN, never a failure.
    Ranges describe whole intersecting cells, whose support can extend outside
    the county. They are not facility performance errors or classifier accuracy.
    """
    required_reference = {"facility_id", "name", "operating_status", "county_geoid"}
    required_grid = {"grid_id", "grid_definition_id", "data_mode", "county_geoid_all"}
    required_ranked = {*KEYS, "grid_definition_id", "data_mode", "rankable",
                       "eligible", "hard_fail", "critical_unknown", "conditional",
                       "mcda_score", "mcda_rank"}
    for frame, required, label in ((reference, required_reference, "Reference"),
                                   (grid, required_grid, "Grid"),
                                   (ranked, required_ranked, "Ranked")):
        if not required <= set(frame):
            raise ValueError(f"{label} lacks required comparison fields")
    if reference.facility_id.isna().any() or reference.facility_id.duplicated().any():
        raise ValueError("Reference facility identities must be non-null and unique")
    if not reference.operating_status.eq("operating").all():
        raise ValueError("Only explicitly operating reference facilities may be compared")
    if reference.empty:
        raise ValueError("No operating reference records are available")
    if grid.empty or ranked.empty or grid.grid_id.duplicated().any() or ranked.duplicated(KEYS).any():
        raise ValueError("Comparison requires nonempty, unique model inputs")
    for field in ("grid_definition_id", "data_mode"):
        values = grid[field].unique()
        if len(values) != 1 or pd.isna(values[0]) or set(ranked[field]) != set(values):
            raise ValueError(f"Comparison inputs have incompatible {field}")
    if not set(ranked.grid_id) <= set(grid.grid_id):
        raise ValueError("Ranked alternatives leave the evaluated grid")
    for flag in ("rankable", "eligible", "hard_fail", "critical_unknown", "conditional"):
        if not ranked[flag].map(lambda v: isinstance(v, (bool, np.bool_))).all():
            raise ValueError(f"{flag} must contain only explicit booleans")
    if (ranked.rankable & (~ranked.eligible | ranked.hard_fail)).any():
        raise ValueError("An ineligible or hard-failing alternative cannot be ranked")
    for column in ("mcda_score", "mcda_rank"):
        if not ranked[column].notna().equals(ranked.rankable):
            raise ValueError("Score/rank nullability must match rankable")
        if not np.isfinite(pd.to_numeric(ranked.loc[ranked.rankable, column])).all():
            raise ValueError("Ranked score/rank must be finite")
    scores = pd.to_numeric(ranked.loc[ranked.rankable, "mcda_score"])
    ranks = pd.to_numeric(ranked.loc[ranked.rankable, "mcda_rank"])
    if not scores.between(0, 100).all() or (ranks < 1).any() or (ranks % 1 != 0).any():
        raise ValueError("Invalid score/rank domain")
    if not grid.county_geoid_all.map(lambda v: isinstance(v, (list, tuple, np.ndarray))).all():
        raise ValueError("County support must be explicit geographic lists")
    support = grid[["grid_id", "county_geoid_all"]].explode("county_geoid_all").rename(
        columns={"county_geoid_all": "county_geoid"})
    support = support.dropna().drop_duplicates().sort_values(["county_geoid", "grid_id"])
    contexts = ranked[["design_id", "scenario_id"]].drop_duplicates().sort_values(
        ["design_id", "scenario_id"])
    groups = {key: value for key, value in ranked.groupby(["design_id", "scenario_id"], sort=True)}
    if any(set(case.grid_id) != set(grid.grid_id) for case in groups.values()):
        raise ValueError("Each design/scenario must retain every evaluated grid cell")
    rows = []
    for ref in reference.sort_values("facility_id").to_dict("records"):
        county = ref["county_geoid"]
        matched = pd.notna(county)
        ids = set(support.loc[support.county_geoid.eq(county), "grid_id"]) if matched else set()
        for context in contexts.to_dict("records"):
            case = groups[(context["design_id"], context["scenario_id"])]
            selected = case.loc[case.grid_id.isin(ids)]
            ranked_support = selected.loc[selected.rankable]
            row = {
                "schema_version": "1.0.0", "reference_facility_id": ref["facility_id"],
                "reference_name": ref["name"], "reference_source_url": ref.get("source_url"),
                "county_geoid": county if matched else None,
                "grid_definition_id": grid.grid_definition_id.iloc[0],
                "data_mode": grid.data_mode.iloc[0], **context,
                "spatial_support": "county_intersecting_whole_cells",
                "comparison_status": "COUNTY_SUPPORTED" if ids else "OUTSIDE_EVALUATED_DOMAIN" if matched else "UNMATCHED_COUNTY",
                "missing_reason": None if ids else "county_not_evaluated" if matched else ref.get("county_match_missing_reason") or "county_not_matched",
                "support_cells": len(ids), "evaluated_alternatives": len(selected),
                "ranked_support_cells": len(ranked_support),
                "hard_failure_cells": int(selected.hard_fail.sum()),
                "critical_unknown_cells": int(selected.critical_unknown.sum()),
                "conditional_ranked_cells": int((selected.rankable & selected.conditional).sum()),
                "facility_score": None, "facility_score_status": "unknown",
                "facility_score_missing_reason": "exact_facility_location_not_available",
                "physical_validation_status": "EXTERNALLY_UNVALIDATED",
                "physical_validation_missing_reason": "compatible_measured_facility_inputs_and_outputs_not_available",
                "support_statistics_status": "calculated" if ids else "unknown",
                "confidence": "low" if ids else "unknown",
            }
            for column in ("mcda_score", "mcda_rank", *[m for m in RAW_METRICS if m in case]):
                values = pd.to_numeric((ranked_support if column in {"mcda_score", "mcda_rank"} else selected)[column], errors="coerce")
                values = values[np.isfinite(values)]
                row[column + "_min"] = None if values.empty else float(values.min())
                row[column + "_max"] = None if values.empty else float(values.max())
                row[column + "_range_status"] = "unknown" if values.empty else "calculated"
                row[column + "_range_missing_reason"] = "no_finite_supported_model_values" if values.empty else None
            rows.append(row)
    return pd.DataFrame(rows).sort_values(["reference_facility_id", "design_id", "scenario_id"]).reset_index(drop=True)


def comparison_summary(comparison: pd.DataFrame) -> dict:
    """Count reference coverage once per facility, keeping non-label semantics."""
    facilities = comparison.drop_duplicates("reference_facility_id")
    return {
        "reference_facilities": len(facilities),
        "coverage_counts": facilities.comparison_status.value_counts().sort_index().to_dict(),
        "spatial_support": "County-intersecting whole-cell ranges; no facility is snapped to a centroid.",
        "selection_bias": "Public largest-operating tables are a capacity-selected sample, not a complete or representative inventory.",
        "accuracy": None,
        "accuracy_missing_reason": "Existing locations are not sustainability optimality labels; absence is not a negative label.",
        "externally_validated_modules": [],
        "externally_unvalidated_modules": ["facility_energy", "facility_water", "facility_carbon", "parcel_feasibility", "utility_capacity", "fiber_diversity"],
    }
