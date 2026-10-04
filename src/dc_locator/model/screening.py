"""Evidence-based regional screening; UNKNOWN is never accepted by STRICT.

This module consumes geographic tables only. It does not download or rank.
"""

import json
import math
from pathlib import Path
from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator
import yaml

from dc_locator.model.cooling import CoolingDesign, PhysicalScenario, validate_alternative_ids
from dc_locator.provenance import ScreeningMode
from dc_locator.schemas import FacilityConfig, ScreeningResult, ScreeningEligibility


def clean_json(value):
    """Produce portable JSON with explicit nulls, never non-standard NaN."""
    if isinstance(value, dict):
        return {str(k): clean_json(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [clean_json(v) for v in value]
    if value is None or value is pd.NA:
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if hasattr(value, "item"):
        return clean_json(value.item())
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def json_text(value) -> str:
    return json.dumps(clean_json(value), sort_keys=True, allow_nan=False, default=str)


def prepare_inputs(geography: pd.DataFrame, provenance: pd.DataFrame):
    for column in ("grid_id", "grid_definition_id", "data_mode"):
        if column not in geography:
            raise ValueError(f"Missing geographic identity column {column}")
    if geography.grid_id.duplicated().any() or geography.grid_definition_id.nunique() != 1:
        raise ValueError("One grid definition and unique grid IDs are required")
    if geography.data_mode.nunique() != 1 or not set(geography.data_mode).issubset({"real", "synthetic"}):
        raise ValueError("One explicit real/synthetic data_mode is required")
    if provenance.duplicated(["grid_id", "metric"]).any():
        raise ValueError("Duplicate grid_id/metric provenance")
    if "data_mode" not in provenance or not set(provenance.data_mode).issubset(set(geography.data_mode)):
        raise ValueError("Provenance data_mode disagrees with geographic inputs")
    evidence = {(r["grid_id"], r["metric"]): r for r in provenance.to_dict("records")}
    return geography.sort_values("grid_id").to_dict("records"), evidence


def feature_evidence(row: dict, provenance: dict, metric: str) -> dict:
    found = provenance.get((row["grid_id"], metric))
    if found is None:
        return {"value": None, "status": "unknown", "confidence": "unknown", "coverage_frac": None, "missing_reason": "source_not_available", "metric": metric}
    found = clean_json(found)
    status = found.get("status", "unknown")
    value = found.get("value")
    if status not in {"observed", "calculated", "scenario", "proxy", "unknown"}:
        raise ValueError(f"Invalid value status for {metric}")
    if row.get(metric + "_status") != status:
        raise ValueError(f"Wide/long status mismatch for {metric}")
    wide = clean_json(row.get(metric))
    if value is not None and (wide is None or not math.isclose(float(value), float(wide), rel_tol=1e-10, abs_tol=1e-12)):
        raise ValueError(f"Wide/long value mismatch for {metric}")
    if status == "unknown" and (value is not None or wide is not None):
        raise ValueError(f"UNKNOWN carries a value for {metric}")
    if value is not None and not math.isfinite(float(value)):
        raise ValueError(f"Nonfinite feature {metric}")
    coverage_key = metric + "_coverage_frac"
    if coverage_key in row:
        wide_coverage, long_coverage = clean_json(row[coverage_key]), found.get("coverage_frac")
        if (wide_coverage is None) != (long_coverage is None) or (wide_coverage is not None and not math.isclose(wide_coverage, long_coverage, rel_tol=0, abs_tol=1e-10)):
            raise ValueError(f"Wide/long coverage mismatch for {metric}")
    return found


class Requirement(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    requirement_id: str = Field(min_length=1)
    metric: str = Field(min_length=1)
    operator: Literal["ge", "le", "informational"]
    threshold: float | None = None
    threshold_from: Literal["minimum_land_area_km2", "peak_facility_demand_mw"] | None = None
    unit: str
    is_critical: bool = True
    coverage_policy: Literal["full", "not_applicable"] = "full"
    min_coverage_frac: float = Field(default=1, ge=0, le=1)
    basis: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    reference: str | None = None
    accepted_statuses: list[Literal["observed", "calculated", "scenario", "proxy"]] = Field(default_factory=lambda: ["observed", "calculated"], min_length=1)
    accepted_source_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_threshold(self):
        if self.operator != "informational" and (self.threshold is None) == (self.threshold_from is None):
            raise ValueError("Exactly one numeric or facility-derived threshold is required")
        if self.operator == "informational" and self.is_critical:
            raise ValueError("Informational regional indicators cannot be critical feasibility constraints")
        if self.operator == "informational" and (self.threshold is not None or self.threshold_from is not None):
            raise ValueError("Informational indicators cannot silently ignore a threshold")
        return self


def load_requirements(path: str | Path):
    values = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    requirements = [Requirement.model_validate(r) for r in values["requirements"]]
    if not requirements or len({r.requirement_id for r in requirements}) != len(requirements):
        raise ValueError("A nonempty set of uniquely named requirements is required")
    return requirements, ScreeningMode(values["screening_mode"])


def screen(geography, provenance, facility: FacilityConfig, designs: list[CoolingDesign], scenarios: list[PhysicalScenario], requirements: list[Requirement], *, mode=None, land_search_scope: Literal["single_cell", "multi_cell_region"] = "single_cell"):
    """Return (requirement results, eligibility table, summary).

    Informational records preserve observed regional evidence in evidence_json,
    while their UNKNOWN outcome explicitly makes no parcel-clearance decision.
    In a multi-cell search, positive but insufficient classified area in one
    cell cannot disprove a parcel that crosses its boundary. Such total-area
    support remains UNKNOWN; no contiguous or obtainable parcel is inferred.
    """
    if not isinstance(land_search_scope, str) or land_search_scope not in {"single_cell", "multi_cell_region"}:
        raise ValueError("land_search_scope must be single_cell or multi_cell_region")
    mode_override = mode is not None
    mode = ScreeningMode(facility.screening_mode if mode is None else mode)
    validate_alternative_ids(designs, scenarios)
    rows, evidence = prepare_inputs(geography, provenance)
    if not requirements:
        raise ValueError("Empty screening rules cannot establish acceptance")
    if len({r.requirement_id for r in requirements}) != len(requirements):
        raise ValueError("Duplicate requirement IDs")
    results, alternatives = [], []
    for row in rows:
        for design in sorted(designs, key=lambda d: d.design_id):
            for scenario in sorted(scenarios, key=lambda s: s.scenario_id):
                outcomes = []
                for req in requirements:
                    item = feature_evidence(row, evidence, req.metric)
                    threshold = req.threshold
                    if req.threshold_from == "minimum_land_area_km2":
                        threshold = facility.minimum_land_area_km2
                    if req.threshold_from == "peak_facility_demand_mw":
                        threshold = facility.peak_it_power_mw * design.peak_pue if design.peak_pue_verified else None
                    value = item.get("value")
                    coverage = item.get("coverage_frac")
                    missing = None
                    if req.operator == "informational":
                        missing, reason = "no_feasibility_threshold", "Informational regional indicator; no parcel feasibility or clearance is inferred"
                    elif threshold is None:
                        missing, reason = "unverified_requirement", "Required peak facility demand or facility land requirement is unverified; annual PUE is not verified peak PUE"
                    elif value is None or item.get("status") == "unknown":
                        missing, reason = item.get("missing_reason") or "source_not_available", "Required evidence is unavailable; geographic proxies cannot verify this requirement"
                    elif item.get("status") not in req.accepted_statuses:
                        missing, reason = "unsupported_evidence_status", "Evidence status is not accepted for this requirement; a proxy/scenario cannot verify confirmed capacity, land or clearance"
                    elif req.accepted_source_ids and item.get("source_id") not in req.accepted_source_ids:
                        missing, reason = "unsupported_evidence_source", "Evidence source is not accepted by this configured requirement"
                    elif req.metric.startswith("confirmed_") and item.get("status") == "calculated" and not item.get("method"):
                        missing, reason = "undocumented_calculation", "Confirmed calculated evidence needs a documented method and verification boundary"
                    elif req.coverage_policy == "full" and (coverage is None or coverage + 1e-6 < req.min_coverage_frac):
                        missing, reason = "partial_coverage", "Source coverage is insufficient for this configured constraint; no extrapolation"
                    elif item.get("unit") != req.unit:
                        raise ValueError(f"Unit mismatch for {req.metric}: {item.get('unit')} != {req.unit}")
                    elif (land_search_scope == "multi_cell_region"
                          and req.requirement_id == "total_suitable_area_plausibility"
                          and req.metric == "suitable_land_area_km2"
                          and req.operator == "ge" and req.is_critical
                          and req.threshold_from == "minimum_land_area_km2"
                          and req.unit == "km2" and 0 < value < threshold):
                        missing, reason = "cross_cell_land_support_unverified", "Positive classified land in this cell is below the facility requirement; land spanning adjacent cells is unverified, not disproven. Contiguity and parcel availability remain separate requirements"
                    else:
                        reason = "Evidence compared with disclosed project requirement; this is regional screening, not parcel approval"
                    outcome = "UNKNOWN" if missing else ("PASS" if (value >= threshold if req.operator == "ge" else value <= threshold) else "FAIL")
                    outcomes.append((outcome, req.is_critical))
                    record = ScreeningResult(
                        schema_version="1.2.0" if land_search_scope == "multi_cell_region" else "1.1.0",
                        grid_id=row["grid_id"], design_id=design.design_id, scenario_id=scenario.scenario_id,
                        requirement=req.requirement_id, outcome=outcome, mode=mode,
                        value=None if missing else value, unit=req.unit, threshold=threshold,
                        is_critical=req.is_critical, missing_reason=missing,
                        grid_definition_id=row["grid_definition_id"], facility_id=facility.facility_id,
                        metric=req.metric, reason=reason, evidence_json=json_text(item),
                        source_status=item.get("status", "unknown"), confidence=item.get("confidence", "unknown"),
                        coverage_frac=coverage, basis=req.basis, rationale=req.rationale,
                        data_mode=row["data_mode"],
                    ).model_dump(mode="json")
                    results.append(record)
                hard_fail = any(outcome == "FAIL" and critical for outcome, critical in outcomes)
                unknown = any(outcome == "UNKNOWN" and critical for outcome, critical in outcomes)
                alternatives.append(ScreeningEligibility(schema_version="1.1.0" if land_search_scope == "multi_cell_region" else "1.0.0", grid_id=row["grid_id"], grid_definition_id=row["grid_definition_id"], facility_id=facility.facility_id, design_id=design.design_id, scenario_id=scenario.scenario_id, mode=mode.value, hard_fail=hard_fail, critical_unknown=unknown, eligible=not hard_fail and (mode == ScreeningMode.EXPLORATORY or not unknown), conditional=not hard_fail and unknown and mode == ScreeningMode.EXPLORATORY, data_mode=row["data_mode"]).model_dump(mode="json"))
    result = pd.DataFrame(results).sort_values(["grid_id", "design_id", "scenario_id", "requirement"]).reset_index(drop=True)
    eligible = pd.DataFrame(alternatives).sort_values(["grid_id", "design_id", "scenario_id"]).reset_index(drop=True)
    summary = dict(mode=mode.value, n_alternatives=len(eligible), n_eligible=int(eligible.eligible.sum()), n_conditional=int(eligible.conditional.sum()), n_hard_fail=int(eligible.hard_fail.sum()), n_critical_unknown=int(eligible.critical_unknown.sum()), outcomes=result.outcome.value_counts().sort_index().to_dict(), coverage_policy="Full constraint coverage within 1e-6 numerical tolerance; geographic proximity can be explicitly not_applicable", interpretation="These geographic regions deserve further investigation under the stated facility requirements, datasets, constraints, assumptions, and decision preferences. They are not proven buildable parcels.")
    summary["critical_outcomes"] = result.loc[result.is_critical, "outcome"].value_counts().sort_index().to_dict()
    summary["informational_outcomes"] = result.loc[~result.is_critical, "outcome"].value_counts().sort_index().to_dict()
    summary["mode_override_requested"] = mode_override
    if land_search_scope != "single_cell":
        summary["land_search_scope"] = land_search_scope
    return result, eligible, summary
