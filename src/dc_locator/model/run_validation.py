"""Pure current-run validation and deterministic sensitivity recomputation.

This module validates the inputs and results supplied by the Phase 7 delivery
pipeline.  It performs no file I/O, does not reuse Phase 6 acceptance as proof
for current code, and never changes an accepted geography or model result.
"""

from __future__ import annotations

import hashlib
import json
import math
import warnings
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal, Mapping, Sequence

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator, model_validator

from dc_locator.model.cooling import CoolingDesign, PhysicalScenario
from dc_locator.model.decision import decide
from dc_locator.model.enhanced import rebind_external_scenario, validate_matched_preferences
from dc_locator.model.metrics import ScoringProfile, clean, json_text, profile_fingerprint
from dc_locator.model.physics import simulate
from dc_locator.model.scenarios import ExternalScenario
from dc_locator.model.screening import Requirement, screen
from dc_locator.model.validation.analysis import (
    PAIR_KEY,
    compare_ranked_cases,
    summarize_case,
    summarize_fixed_regions,
)
from dc_locator.schemas import FacilityConfig
from dc_locator.validation import validate_feature_provenance


HASH_PATTERN = "0123456789abcdef"
CaseCategory = Literal["weights", "pue", "wue", "load", "carbon", "land", "screening"]


def _validate_hashes(value: Mapping[str, str], label: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or not value:
        raise ValueError(f"{label} must be a nonempty path/identity to SHA256 mapping")
    result = {}
    for key, digest in value.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError(f"{label} keys must be nonempty strings")
        if not isinstance(digest, str) or len(digest) != 64 or any(ch not in HASH_PATTERN for ch in digest.lower()):
            raise ValueError(f"{label} values must be SHA256 hex digests")
        result[key] = digest.lower()
    return dict(sorted(result.items()))


class CurrentRunIdentity(BaseModel):
    """Caller-supplied fingerprints for the exact current delivery run."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    run_id: str = Field(min_length=1)
    model_revision: str = Field(min_length=1)
    model_hashes: dict[str, str]
    config_hashes: dict[str, str]
    source_hashes: dict[str, str]

    @field_validator("run_id", "model_revision")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Identity strings cannot be blank")
        return value

    @field_validator("model_hashes", "config_hashes", "source_hashes")
    @classmethod
    def hash_maps(cls, value, info):
        return _validate_hashes(value, info.field_name)


class CurrentSensitivityCase(BaseModel):
    """One explicitly requested current-run stress case."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    case_id: str = Field(min_length=1)
    category: CaseCategory
    basis: Literal["project_assumption", "user_assumption"]
    rationale: str = Field(min_length=1)
    multiplier: float | None = None
    group_weights: dict[str, float] | None = None
    mode: Literal["STRICT", "EXPLORATORY"] | None = None

    @field_validator("case_id", "rationale")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Case identity and rationale cannot be blank")
        return value

    @field_validator("multiplier", mode="before")
    @classmethod
    def finite_multiplier(cls, value):
        if value is None:
            return None
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.integer, np.floating)):
            raise ValueError("Sensitivity multiplier must be numeric and cannot be boolean")
        value = float(value)
        if not math.isfinite(value) or value <= 0:
            raise ValueError("Sensitivity multiplier must be finite and positive")
        return value

    @field_validator("group_weights", mode="before")
    @classmethod
    def finite_weights(cls, value):
        if value is None:
            return None
        if not isinstance(value, Mapping):
            raise ValueError("Weight sensitivity requires a key/value mapping")
        if not value:
            raise ValueError("Weight sensitivity requires nonempty group weights")
        result = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise ValueError("Weight keys must be nonempty strings")
            if isinstance(item, (bool, np.bool_)) or not isinstance(item, (int, float, np.integer, np.floating)):
                raise ValueError("Weights must be numeric and cannot be boolean")
            number = float(item)
            if not math.isfinite(number) or number < 0:
                raise ValueError("Weights must be finite and nonnegative")
            result[key] = number
        if sum(result.values()) <= 0:
            raise ValueError("At least one requested group weight must be positive")
        return result

    @model_validator(mode="after")
    def exact_parameters(self):
        if self.category == "weights":
            if self.group_weights is None or self.multiplier is not None or self.mode is not None:
                raise ValueError("Weight cases require only group_weights")
        elif self.category == "screening":
            if self.mode is None or self.multiplier is not None or self.group_weights is not None:
                raise ValueError("Screening cases require only mode")
        elif self.multiplier is None or self.group_weights is not None or self.mode is not None:
            raise ValueError(f"{self.category} cases require only multiplier")
        return self


class CurrentValidationSettings(BaseModel):
    """Bounded, deterministic validation policy supplied by the current run."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    validation_revision: str = Field(min_length=1)
    baseline_mode: Literal["STRICT", "EXPLORATORY"]
    top_k: StrictInt = Field(default=10, gt=0, le=1000)
    cases: tuple[CurrentSensitivityCase, ...] = ()
    allow_synthetic: StrictBool = False
    max_cases: StrictInt = Field(default=64, gt=0, le=256)

    @field_validator("validation_revision")
    @classmethod
    def revision_nonblank(cls, value):
        if not value.strip():
            raise ValueError("Validation revision cannot be blank")
        return value

    @model_validator(mode="after")
    def unique_bounded_cases(self):
        identifiers = [case.case_id for case in self.cases]
        if len(identifiers) != len(set(identifiers)) or "baseline" in identifiers:
            raise ValueError("Sensitivity case IDs must be unique and cannot use reserved ID baseline")
        if len(self.cases) > self.max_cases:
            raise ValueError("Requested sensitivity cases exceed max_cases")
        return self


@dataclass(frozen=True)
class FutureValidationContext:
    """One caller-supplied, separately evaluated future-water context."""

    case_id: str
    geography: pd.DataFrame
    provenance: pd.DataFrame
    profile: ScoringProfile
    external_scenario: ExternalScenario
    identity: Mapping[str, str]
    rationale: str

    def __post_init__(self):
        if not isinstance(self.case_id, str) or not self.case_id.strip() or not isinstance(self.rationale, str) or not self.rationale.strip():
            raise ValueError("Future context requires nonblank case ID and rationale")
        if not isinstance(self.geography, pd.DataFrame) or not isinstance(self.provenance, pd.DataFrame):
            raise ValueError("Future context requires in-memory geography and provenance tables")
        if not isinstance(self.profile, ScoringProfile) or not isinstance(self.external_scenario, ExternalScenario):
            raise ValueError("Future context requires validated profile and external scenario objects")
        object.__setattr__(self, "identity", _validate_hashes(self.identity, "future_context.identity"))


@dataclass(frozen=True)
class CurrentRunValidationResult:
    sensitivity_results: pd.DataFrame
    robustness_summary: pd.DataFrame
    alternative_rank_ranges: pd.DataFrame
    fixed_region_summary: pd.DataFrame
    validation_report: dict[str, Any]
    validation_markdown: str


@dataclass(frozen=True)
class _CaseRun:
    case_id: str
    category: str
    result: dict[str, Any]
    assumptions: dict[str, Any]
    screening_summary: dict[str, Any]
    scenario_pairs: dict[str, str]


def _sha_json(value: Any) -> str:
    return hashlib.sha256(json_text(value).encode("utf-8")).hexdigest()


def _canonical_cell(value):
    if value is None or (pd.api.types.is_scalar(value) and pd.isna(value)):
        return "<NULL>"
    # Pandas intentionally considers True equal to numeric 1 in some
    # dtype-relaxed comparisons.  Persisted-table validation must retain the
    # semantic type boundary while still accepting lossless int/float dtype
    # changes introduced by Parquet round trips.
    if isinstance(value, (bool, np.bool_)):
        return ("__dc_locator_bool__", bool(value))
    if hasattr(value, "wkb_hex"):
        return value.wkb_hex
    if isinstance(value, np.ndarray):
        value = value.tolist()
    if isinstance(value, (dict, list, tuple, set)):
        if isinstance(value, set):
            value = sorted(value)
        return json_text(value)
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    return value


def _frame_fingerprint(frame: pd.DataFrame, sort_keys: Sequence[str]) -> str:
    if not isinstance(frame, pd.DataFrame):
        raise ValueError("Validation inputs must be pandas tables")
    keys = [key for key in sort_keys if key in frame]
    ordered = frame.sort_values(keys, kind="stable").reset_index(drop=True) if keys else frame.reset_index(drop=True)
    digest = hashlib.sha256()
    for column in sorted(ordered.columns):
        series = ordered[column].map(_canonical_cell)
        digest.update(column.encode("utf-8") + b"\0" + str(ordered[column].dtype).encode("utf-8") + b"\0")
        digest.update(pd.util.hash_pandas_object(series, index=False, categorize=False).to_numpy().tobytes())
    return digest.hexdigest()


def _semantic_frame(frame: pd.DataFrame, sort_keys: Sequence[str]) -> pd.DataFrame:
    """Normalize exact values without treating Parquet dtype choices as changes."""
    keys = [key for key in sort_keys if key in frame]
    ordered = frame.sort_values(keys, kind="stable").reset_index(drop=True) if keys else frame.reset_index(drop=True)
    return pd.DataFrame(
        {
            column: [_canonical_cell(value) for value in ordered[column].tolist()]
            for column in sorted(ordered.columns)
        }
    )


def _assert_semantic_frame_equal(left, right, keys, label):
    if not isinstance(left, pd.DataFrame) or not isinstance(right, pd.DataFrame):
        raise ValueError(f"Supplied baseline {label} is not a table")
    if set(left.columns) != set(right.columns):
        raise ValueError(f"Supplied baseline {label} columns are stale or incompatible")
    try:
        pd.testing.assert_frame_equal(
            _semantic_frame(left, keys),
            _semantic_frame(right, keys),
            check_dtype=False,
            check_exact=True,
        )
    except AssertionError as exc:
        raise ValueError(
            f"Supplied baseline {label} is stale or incompatible with current inputs"
        ) from exc


def _validate_input_tables(geography, provenance, provenance_grid_definition_id, settings):
    required = {"grid_id", "grid_definition_id", "data_mode"}
    if not isinstance(geography, pd.DataFrame) or geography.empty or not required <= set(geography):
        raise ValueError("Current validation requires a nonempty geographic feature table")
    if geography.grid_id.duplicated().any() or not geography.grid_id.map(lambda value: isinstance(value, str) and bool(value)).all():
        raise ValueError("Geography requires unique nonempty grid IDs")
    definitions, modes = geography.grid_definition_id.unique(), geography.data_mode.unique()
    if len(definitions) != 1 or len(modes) != 1 or modes[0] not in {"real", "synthetic"}:
        raise ValueError("Geography requires one valid grid definition and data mode")
    if modes[0] == "synthetic" and not settings.allow_synthetic:
        raise ValueError("Synthetic validation is quarantined and requires allow_synthetic=true")
    validate_feature_provenance(
        provenance, grid_ids=geography.grid_id, data_mode=str(modes[0]),
        grid_definition_id=str(definitions[0]), provenance_grid_definition_id=provenance_grid_definition_id,
    )
    return str(definitions[0]), str(modes[0])


def _annotate_performance(performance: pd.DataFrame, assumptions: Mapping[str, Any]) -> pd.DataFrame:
    result = performance.copy()
    encoded = []
    for value in result.assumptions_json:
        document = json.loads(value)
        document["current_run_validation_case"] = assumptions
        encoded.append(json_text(document))
    result["assumptions_json"] = encoded
    return result


def _adjust_designs(designs: Sequence[CoolingDesign], field: str, multiplier: float, case: CurrentSensitivityCase):
    adjusted = []
    for design in designs:
        document = design.model_dump(mode="json")
        value = document[field]
        document[field] = None if value is None else value * multiplier
        document["rationale"] = f"{document['rationale']} Current-run {case.basis} case {case.case_id}: {field} multiplier {multiplier:g}. {case.rationale}"
        adjusted.append(CoolingDesign.model_validate(document))
    return adjusted


def _adjust_facility(facility: FacilityConfig, field: str, multiplier: float, case: CurrentSensitivityCase):
    document = facility.model_dump(mode="json")
    value = document[field]
    document[field] = None if value is None else value * multiplier
    document["rationale"] = f"{document['rationale']} Current-run {case.basis} case {case.case_id}: {field} multiplier {multiplier:g}. {case.rationale}"
    return FacilityConfig.model_validate(document)


def _weighted_profile(profile: ScoringProfile, case: CurrentSensitivityCase) -> tuple[ScoringProfile, dict[str, float]]:
    requested = dict(case.group_weights or {})
    expected = set(profile.weight_criterion_ids)
    if set(requested) != expected:
        raise ValueError(f"Weight case {case.case_id} must specify exactly {sorted(expected)}")
    total = sum(requested.values())
    normalized = {key: requested[key] / total for key in sorted(requested)}
    document = profile.model_dump(mode="json")
    document["profile_id"] = f"{profile.profile_id}__current_{case.case_id}"
    document["description"] = f"{profile.description} Current-run weight stress {case.case_id}: {case.rationale}"
    document["weighting_method"] = "user"
    document["user_weights"] = normalized
    document["ahp_judgments"] = None
    return ScoringProfile.model_validate(document), normalized


def _carbon_view(geography, provenance, multiplier: float, case: CurrentSensitivityCase):
    metric = "grid_carbon_intensity_kg_per_mwh"
    if metric not in geography or not {"metric", "value", "status"} <= set(provenance):
        raise ValueError("Carbon sensitivity requires current grid-carbon geography and provenance")
    geo, prov = geography.copy(), provenance.copy()
    geo.attrs.update(getattr(geography, "attrs", {}))
    prov.attrs.update(getattr(provenance, "attrs", {}))
    selected = prov.metric.eq(metric)
    if selected.sum() != len(geo) or set(prov.loc[selected, "grid_id"]) != set(geo.grid_id):
        raise ValueError("Carbon sensitivity requires exactly one provenance row per grid cell")
    wide = pd.to_numeric(geo[metric], errors="coerce")
    long = pd.to_numeric(prov.loc[selected, "value"], errors="coerce")
    if np.isinf(wide.dropna()).any() or np.isinf(long.dropna()).any():
        raise ValueError("Carbon sensitivity cannot scale nonfinite evidence")
    geo.loc[wide.notna(), metric] = wide[wide.notna()] * multiplier
    status_column = metric + "_status"
    if status_column in geo:
        geo.loc[wide.notna(), status_column] = "scenario"
    known_index = prov.loc[selected].index[long.notna()]
    prov.loc[known_index, "value"] = long[long.notna()] * multiplier
    prov.loc[known_index, "status"] = "scenario"
    methods = []
    for index in known_index:
        prior = clean(prov.at[index, "aggregation_method"]) if "aggregation_method" in prov else None
        methods.append(f"{prior or 'current source evidence'}; {case.basis} carbon multiplier={multiplier:g}; transformed value is not publisher-observed")
    if "aggregation_method" in prov:
        prov.loc[known_index, "aggregation_method"] = methods
    source_rows = prov.loc[selected]
    metadata = {
        "basis": case.basis,
        "rationale": case.rationale,
        "multiplier": multiplier,
        "known_values_scaled": int(long.notna().sum()),
        "unknown_values_preserved": int(long.isna().sum()),
        "source_ids": sorted(set(source_rows.source_id.dropna().astype(str))) if "source_id" in source_rows else [],
        "source_fields": sorted(set(source_rows.source_field.dropna().astype(str))) if "source_field" in source_rows else [],
        "source_years": sorted(set(source_rows.data_year.dropna().astype(str))) if "data_year" in source_rows else [],
        "interpretation": "Counterfactual scaling of current source evidence; not a publisher observation or future-grid forecast.",
    }
    return geo, prov, metadata


def _validate_future_water_binding(context: FutureValidationContext) -> None:
    """Bind a supplied water profile and evidence to its external scenario."""
    scenario = context.external_scenario
    expected_column = (
        f"aqueduct_{scenario.pathway}_{scenario.milestone_year}_water_stress_score"
    )
    expected_field = (
        f"{scenario.pathway}{scenario.milestone_year % 100:02d}_ws_x_s"
        if scenario.supported
        else None
    )
    definitions = [
        metric
        for metric in context.profile.metrics
        if metric.metric_id == "local_baseline_water_stress"
    ]
    if len(definitions) != 1:
        raise ValueError("Future-water profile needs exactly one local water-stress metric")
    definition = definitions[0]
    if (
        definition.column != expected_column
        or definition.source_id != "wri_aqueduct40_future"
        or definition.source_field != expected_field
        or definition.allowed_statuses != ["scenario"]
    ):
        raise ValueError("Future-water profile source binding disagrees with the external scenario")
    rows = context.provenance.loc[context.provenance.metric.eq(expected_column)].copy()
    if len(rows) != len(context.geography) or set(rows.grid_id) != set(context.geography.grid_id):
        raise ValueError("Future-water source binding needs exactly one evidence row per grid cell")
    if set(rows.source_id) != {"wri_aqueduct40_future"}:
        raise ValueError("Future-water provenance source identity disagrees with the external scenario")
    fields = {clean(value) for value in rows.source_field}
    if fields != {expected_field}:
        raise ValueError("Future-water provenance source field disagrees with the external scenario")
    periods = [str(value) for value in rows.data_year]
    scenario_tokens = [str(scenario.milestone_year), scenario.ssp_rcp]
    if scenario.supported:
        scenario_tokens.append(f"{scenario.window_start_year}-{scenario.window_end_year}")
        known = rows.status.astype(str).eq("scenario") & rows.value.notna() & rows.missing_reason.isna()
        unknown = rows.status.astype(str).eq("unknown") & rows.value.isna() & rows.missing_reason.notna()
        if not (known | unknown).all():
            raise ValueError("Supported future-water rows must be scenario values or explicit UNKNOWN evidence")
    else:
        if set(rows.status.astype(str)) != {"unknown"} or rows.value.notna().any():
            raise ValueError("Unsupported future-water context must remain UNKNOWN")
        if set(rows.missing_reason.astype(str)) != {"unsupported_source_period"}:
            raise ValueError("Unsupported future-water context needs the unsupported-period reason")
        scenario_tokens.append("unsupported")
    if any(any(token not in period for token in scenario_tokens) for period in periods):
        raise ValueError("Future-water provenance period/window/SSP disagrees with the external scenario")


def _execute_case(
    geography, provenance, facility, designs, scenarios, requirements, profile, *, mode, case_id,
    category, assumptions, provenance_grid_definition_id, external_scenario=None,
):
    _, eligibility, summary = screen(geography, provenance, facility, list(designs), list(scenarios), list(requirements), mode=mode)
    performance = simulate(geography, provenance, facility, list(designs), list(scenarios))
    if external_scenario is not None:
        if len(scenarios) != 1 or external_scenario.physical_scenario_id != scenarios[0].scenario_id:
            raise ValueError("A future context must bind exactly one matching physical scenario")
        performance = rebind_external_scenario(performance, external_scenario, physical_metadata=True)
        eligibility = rebind_external_scenario(eligibility, external_scenario)
        scenario_pairs = {scenarios[0].scenario_id: external_scenario.scenario_id}
    else:
        scenario_pairs = {scenario.scenario_id: scenario.scenario_id for scenario in scenarios}
    if case_id != "baseline":
        performance = _annotate_performance(performance, assumptions)
    result = decide(
        geography, provenance, performance, eligibility, profile,
        profile_hash=profile_fingerprint(profile), provenance_grid_definition_id=provenance_grid_definition_id,
    )
    expected = len(geography) * len(designs) * len(scenarios)
    ranked = result["ranked_cells"]
    if len(ranked) != expected:
        raise ValueError("Current validation case dropped alternatives")
    if ranked.loc[ranked.hard_fail, "rankable"].any():
        raise ValueError("A hard failure entered current ranking")
    return _CaseRun(case_id, category, result, assumptions, summary, scenario_pairs)


def _assert_baseline_matches(fresh: dict, supplied: dict):
    required = {"normalized_metrics", "ranked_cells", "pareto_results", "candidate_regions", "region_membership", "weights"}
    if not isinstance(supplied, dict) or not required <= set(supplied):
        raise ValueError("baseline_result is not a complete current decide() result")
    left, right = fresh["ranked_cells"], supplied["ranked_cells"]
    if set(left.columns) != set(right.columns):
        raise ValueError("Supplied baseline ranked columns differ from fresh current recomputation")
    order = ["grid_id", "design_id", "scenario_id"]
    try:
        pd.testing.assert_frame_equal(
            left.sort_values(order).reset_index(drop=True)[right.columns],
            right.sort_values(order).reset_index(drop=True),
            check_dtype=False, check_exact=True,
        )
    except AssertionError as exc:
        raise ValueError("Supplied baseline result is stale or incompatible with current inputs") from exc
    if json_text(fresh["weights"]) != json_text(supplied["weights"]):
        raise ValueError("Supplied baseline weights differ from current profile recomputation")
    table_keys = {
        "normalized_metrics": ["grid_id", "design_id", "scenario_id", "metric_id"],
        "pareto_results": ["grid_id", "design_id", "scenario_id"],
        "candidate_regions": ["region_id", "design_id", "scenario_id"],
        "region_membership": ["region_id", "grid_id", "design_id", "scenario_id"],
    }
    for name, keys in table_keys.items():
        _assert_semantic_frame_equal(fresh[name], supplied[name], keys, name)


def _scenario_frames(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {str(key): group.copy().reset_index(drop=True) for key, group in frame.groupby("scenario_id", sort=True)}


def _markdown(report: Mapping[str, Any]) -> str:
    robustness = report["ranking_stability"]
    comparison_note = (
        "No ranked top-k comparison was available; zero overlap counts are diagnostics with no "
        "ranked denominator, so no stability percentage or correlation is claimed."
        if robustness["ranked_top_k_comparisons"] == 0
        else f"{robustness['ranked_top_k_comparisons']} case/scenario summaries had ranked top-k denominators."
    )
    lines = [
        "# Current-run validation report", "",
        f"Run `{report['run_id']}` was evaluated as `{report['validation_id']}` against the supplied current inputs.", "",
        "## Runtime contracts", "",
        "The helper freshly recomputed screening, physical performance and decisions. The supplied baseline matched that recomputation exactly. Hard failures and strict critical UNKNOWN alternatives did not rank, and missing metrics did not trigger candidate-specific weight redistribution.", "",
        "This runtime result is separate from a test-suite result. Historical Phase 6 evidence, when supplied, is reference-only and is not proof for the current code or configuration.", "",
        "## Sensitivity", "",
        f"{robustness['cases']} cases produced {robustness['rows']} case/scenario summaries. Rank correlation range: {robustness['rank_correlation_range']}; top-k overlap range: {robustness['top_k_overlap_range']}.", "",
        comparison_note, "",
        "## External validation", "",
        "Status: **UNAVAILABLE**. No overall accuracy is reported and no current module is described as independently validated.", "",
        "## Scope and limitations", "",
        f"Data mode: **{report['data_mode']}**. A new prospective holdout was not performed for this delivery run.", "",
    ]
    for item in report["remaining_blockers"]:
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def validate_current_run(
    *,
    geography: pd.DataFrame,
    provenance: pd.DataFrame,
    facility: FacilityConfig,
    designs: Sequence[CoolingDesign],
    physical_scenarios: Sequence[PhysicalScenario],
    requirements: Sequence[Requirement],
    active_profile: ScoringProfile,
    baseline_result: dict[str, Any],
    provenance_grid_definition_id: str,
    identity: CurrentRunIdentity,
    settings: CurrentValidationSettings,
    future_contexts: Sequence[FutureValidationContext] = (),
    baseline_regions: pd.DataFrame | None = None,
    reference_evidence: Mapping[str, Any] | None = None,
) -> CurrentRunValidationResult:
    """Recompute current cases and return in-memory validation artifacts.

    The caller owns persistence and must label any synthetic run explicitly.
    Phase 6 reference evidence is accepted only as historical context.
    """
    identity = CurrentRunIdentity.model_validate(identity)
    settings = CurrentValidationSettings.model_validate(settings)
    facility = FacilityConfig.model_validate(facility.model_dump(mode="json"))
    designs = tuple(CoolingDesign.model_validate(item.model_dump(mode="json")) for item in designs)
    physical_scenarios = tuple(PhysicalScenario.model_validate(item.model_dump(mode="json")) for item in physical_scenarios)
    requirements = tuple(Requirement.model_validate(item.model_dump(mode="json")) for item in requirements)
    active_profile = ScoringProfile.model_validate(active_profile.model_dump(mode="json"))
    if not designs or not physical_scenarios or not requirements:
        raise ValueError("Current validation needs nonempty designs, physical scenarios, and requirements")
    grid_definition_id, data_mode = _validate_input_tables(
        geography, provenance, provenance_grid_definition_id, settings
    )
    contexts = tuple(future_contexts)
    case_ids = [case.case_id for case in settings.cases] + [context.case_id for context in contexts]
    if len(case_ids) != len(set(case_ids)) or "baseline" in case_ids:
        raise ValueError("All current and future sensitivity case IDs must be unique")
    if len(case_ids) > settings.max_cases:
        raise ValueError("Current plus future cases exceed max_cases")
    if reference_evidence is not None:
        json_text(reference_evidence)

    object_binding = {
        "geography_table_sha256": _frame_fingerprint(geography, ["grid_id"]),
        "provenance_table_sha256": _frame_fingerprint(provenance, ["grid_id", "metric"]),
        "facility_object_sha256": _sha_json(facility.model_dump(mode="json")),
        "designs_object_sha256": _sha_json([item.model_dump(mode="json") for item in designs]),
        "physical_scenarios_object_sha256": _sha_json([item.model_dump(mode="json") for item in physical_scenarios]),
        "requirements_object_sha256": _sha_json([item.model_dump(mode="json") for item in requirements]),
        "profile_object_sha256": profile_fingerprint(active_profile),
        "baseline_ranked_table_sha256": _frame_fingerprint(baseline_result.get("ranked_cells", pd.DataFrame()), ["grid_id", "design_id", "scenario_id"]),
    }
    binding = {
        "caller_identity": identity.model_dump(mode="json"),
        "actual_objects": object_binding,
        "grid_definition_id": grid_definition_id,
        "data_mode": data_mode,
        "settings": settings.model_dump(mode="json"),
        "future_contexts": [
            {
                "case_id": context.case_id,
                "identity": dict(context.identity),
                "actual_geography_table_sha256": _frame_fingerprint(context.geography, ["grid_id"]),
                "actual_provenance_table_sha256": _frame_fingerprint(
                    context.provenance, ["grid_id", "metric"]
                ),
                "profile_sha256": profile_fingerprint(context.profile),
                "scenario": context.external_scenario.model_dump(mode="json"),
            }
            for context in contexts
        ],
        "historical_reference_sha256": None if reference_evidence is None else _sha_json(reference_evidence),
    }
    validation_id = "current-" + _sha_json(binding)[:16]
    baseline_assumptions = {
        "basis": "current_configured_run",
        "rationale": "Fresh current-input baseline recomputation; not inherited Phase 6 proof.",
        "input_binding_sha256": _sha_json(binding),
    }
    baseline = _execute_case(
        geography, provenance, facility, designs, physical_scenarios, requirements, active_profile,
        mode=settings.baseline_mode, case_id="baseline", category="baseline", assumptions=baseline_assumptions,
        provenance_grid_definition_id=provenance_grid_definition_id,
    )
    _assert_baseline_matches(baseline.result, baseline_result)
    cases = [baseline]
    for case in settings.cases:
        case_geography, case_provenance = geography, provenance
        case_facility, case_designs, case_profile = facility, designs, active_profile
        mode = settings.baseline_mode
        assumptions = case.model_dump(mode="json")
        if case.category == "weights":
            case_profile, normalized = _weighted_profile(active_profile, case)
            assumptions["normalized_group_weights"] = normalized
            assumptions["interpretation"] = "Explicit preference stress; not elicited expert judgment."
        elif case.category == "pue":
            case_designs = _adjust_designs(designs, "annual_pue", case.multiplier, case)
        elif case.category == "wue":
            case_designs = _adjust_designs(designs, "wue_l_per_it_kwh", case.multiplier, case)
        elif case.category == "load":
            case_facility = _adjust_facility(facility, "average_it_load_factor", case.multiplier, case)
        elif case.category == "land":
            case_facility = _adjust_facility(facility, "minimum_land_area_km2", case.multiplier, case)
        elif case.category == "carbon":
            case_geography, case_provenance, carbon = _carbon_view(geography, provenance, case.multiplier, case)
            assumptions["carbon_transform"] = carbon
        elif case.category == "screening":
            mode = case.mode
        cases.append(_execute_case(
            case_geography, case_provenance, case_facility, case_designs, physical_scenarios,
            requirements, case_profile, mode=mode, case_id=case.case_id, category=case.category,
            assumptions=assumptions, provenance_grid_definition_id=provenance_grid_definition_id,
        ))
    for context in contexts:
        if len(physical_scenarios) != 1:
            raise ValueError("Future validation contexts currently require exactly one physical scenario")
        context_grid, context_mode = _validate_input_tables(
            context.geography, context.provenance, provenance_grid_definition_id, settings
        )
        if context_grid != grid_definition_id or context_mode != data_mode or set(context.geography.grid_id) != set(geography.grid_id):
            raise ValueError("Future context must preserve the current grid definition, data mode, and grid domain")
        validate_matched_preferences(active_profile, context.profile)
        _validate_future_water_binding(context)
        assumptions = {
            "basis": "configured_future_water_context",
            "rationale": context.rationale,
            "identity": dict(context.identity),
            "external_scenario": context.external_scenario.model_dump(mode="json"),
            "interpretation": "Separately ranked supplied context; no interpolation, favorable-scenario pooling, or climate-to-cooling response.",
        }
        cases.append(_execute_case(
            context.geography, context.provenance, facility, designs, physical_scenarios,
            requirements, context.profile, mode=settings.baseline_mode, case_id=context.case_id,
            category="water", assumptions=assumptions,
            provenance_grid_definition_id=provenance_grid_definition_id,
            external_scenario=context.external_scenario,
        ))

    base_frames = _scenario_frames(baseline.result["ranked_cells"])
    comparisons, robustness_rows, fixed_rows = [], [], []
    membership = baseline.result["region_membership"].copy()
    if baseline_regions is not None:
        if not isinstance(baseline_regions, pd.DataFrame) or _frame_fingerprint(
            baseline_regions, ["region_id", "grid_id", "design_id", "scenario_id"]
        ) != _frame_fingerprint(membership, ["region_id", "grid_id", "design_id", "scenario_id"]):
            raise ValueError("Optional baseline region membership is stale or incompatible with current recomputation")
    if not isinstance(membership, pd.DataFrame):
        raise ValueError("Baseline region membership must be a table")
    for case in cases:
        case_frames = _scenario_frames(case.result["ranked_cells"])
        for baseline_scenario, case_scenario in case.scenario_pairs.items():
            if baseline_scenario not in base_frames or case_scenario not in case_frames:
                raise ValueError("Sensitivity scenario correspondence is incomplete")
            comparison = compare_ranked_cases(
                base_frames[baseline_scenario], case_frames[case_scenario],
                evaluation_version=settings.validation_revision, freeze_id=validation_id,
                case_id=case.case_id, case_category=case.category, k=settings.top_k,
                case_metadata=case.assumptions,
            )
            comparison["current_run_id"] = identity.run_id
            comparisons.append(comparison)
            summary = summarize_case(
                comparison, case_frames[case_scenario], evaluation_version=settings.validation_revision,
                freeze_id=validation_id, case_id=case.case_id, case_category=case.category,
                k=settings.top_k, weighting_method=case.result["weighting_method"],
            )
            summary["current_run_id"] = identity.run_id
            summary["ahp_status"] = (
                case.result["ahp_result"]["status"] if case.result["ahp_result"] else "NOT_APPLICABLE"
            )
            robustness_rows.append(summary)
            if not membership.empty:
                selected_membership = membership.loc[membership.scenario_id.eq(baseline_scenario)].copy()
                if not selected_membership.empty:
                    fixed = summarize_fixed_regions(
                        selected_membership, case_frames[case_scenario],
                        evaluation_version=settings.validation_revision, freeze_id=validation_id,
                        case_id=case.case_id, baseline_scenario_id=baseline_scenario,
                    )
                    fixed["current_run_id"] = identity.run_id
                    fixed_rows.append(fixed)
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="The behavior of DataFrame concatenation with empty or all-NA entries is deprecated",
            category=FutureWarning,
        )
        sensitivity = pd.concat(comparisons, ignore_index=True) if comparisons else pd.DataFrame()
    robustness = pd.DataFrame(robustness_rows)
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="The behavior of DataFrame concatenation with empty or all-NA entries is deprecated",
            category=FutureWarning,
        )
        fixed_regions = pd.concat(fixed_rows, ignore_index=True) if fixed_rows else pd.DataFrame(columns=[
            "schema_version", "evaluation_version", "freeze_id", "case_id", "region_id", "design_id",
            "baseline_scenario_id", "case_scenario_id", "total_baseline_members", "matched_members",
            "eligible_members", "rankable_members", "unranked_members", "case_rank_min", "case_rank_max",
            "case_rank_mean", "case_rank_range_basis", "case_rank_mean_basis", "current_run_id",
        ])
    for table in (sensitivity, robustness, fixed_regions):
        table.rename(columns={"evaluation_version": "validation_revision", "freeze_id": "validation_id"}, inplace=True)
    rank_rows = []
    for (grid_id, design_id, scenario_id), group in sensitivity.groupby(
        ["grid_id", "design_id", "baseline_scenario_id"], sort=True
    ):
        baseline_group = group.loc[group.case_id.eq("baseline")]
        if len(baseline_group) != 1:
            raise ValueError("Each current alternative/scenario needs exactly one baseline comparison row")
        ranks = pd.to_numeric(group.case_rank, errors="coerce")
        known = ranks.dropna().astype(int)
        base_rank = clean(baseline_group.base_rank.iloc[0])
        rank_rows.append({
            "validation_revision": settings.validation_revision,
            "validation_id": validation_id,
            "current_run_id": identity.run_id,
            "grid_id": grid_id,
            "design_id": design_id,
            "baseline_scenario_id": scenario_id,
            "base_rank": base_rank,
            "evaluated_cases": len(group),
            "ranked_cases": len(known),
            "unranked_cases": int(ranks.isna().sum()),
            "minimum_rank": None if known.empty else int(known.min()),
            "maximum_rank": None if known.empty else int(known.max()),
            "rank_range": None if known.empty else int(known.max() - known.min()),
            "scope": "Current grid/design correspondence; every external scenario was evaluated separately.",
        })
    rank_ranges = pd.DataFrame(rank_rows)
    correlations = pd.to_numeric(robustness.get("rank_correlation", pd.Series(dtype=float)), errors="coerce").dropna()
    comparable_top_k = robustness.loc[
        robustness.get("top_k_jaccard", pd.Series(index=robustness.index, dtype=float)).notna()
    ]
    overlaps = pd.to_numeric(
        comparable_top_k.get("top_k_overlap_count", pd.Series(dtype=float)), errors="coerce"
    ).dropna()
    report = {
        "schema_version": "1.0.0",
        "validation_revision": settings.validation_revision,
        "validation_id": validation_id,
        "run_id": identity.run_id,
        "validation_scope": "current_configured_run",
        "data_mode": data_mode,
        "grid_definition_id": grid_definition_id,
        "input_binding": binding,
        "runtime_contracts": {
            "status": "PASSED",
            "baseline_fresh_recomputation_exact": True,
            "all_alternatives_retained": True,
            "hard_fail_never_ranked": True,
            "strict_critical_unknown_never_ranked": True,
            "candidate_specific_missing_weight_redistribution": False,
            "test_suite_status": "NOT_EMBEDDED_IN_RUNTIME_HELPER",
            "test_suite_interpretation": "Delivery metadata must record current test evidence separately; historical Phase 6 test counts are not current proof.",
        },
        "ranking_stability": {
            "cases": len(cases),
            "case_scenario_summaries": len(robustness),
            "rows": len(robustness),
            "sensitivity_rows": len(sensitivity),
            "rank_correlation_range": None if correlations.empty else [float(correlations.min()), float(correlations.max())],
            "top_k_overlap_range": None if overlaps.empty else [int(overlaps.min()), int(overlaps.max())],
            "ranked_top_k_comparisons": len(comparable_top_k),
            "empty_ranked_comparisons": int(len(robustness) - len(comparable_top_k)),
            "eligibility_changes": int(robustness.eligibility_changes.sum()) if len(robustness) else 0,
            "fixed_region_rows": len(fixed_regions),
            "rank_range_rows": len(rank_ranges),
            "scenario_policy": "separate",
        },
        "preference_evidence": {
            "active_weighting_method": active_profile.weighting_method,
            "active_ahp_status": baseline.result["ahp_result"]["status"] if baseline.result["ahp_result"] else "NOT_APPLICABLE",
            "stress_weight_cases_are_expert_judgments": False,
        },
        "external_validation": {
            "status": "UNAVAILABLE",
            "externally_validated_modules": [],
            "externally_unvalidated_modules": [
                "physical energy/carbon/water estimates", "parcel and utility feasibility",
                "future-water binding", "preference ranking", "candidate-region clustering",
            ],
            "overall_accuracy": None,
            "reason": "No independent observations with compatible facility/system boundaries were supplied to this helper.",
        },
        "historical_reference": None if reference_evidence is None else {
            "status": "HISTORICAL_REFERENCE_ONLY",
            "evidence": dict(reference_evidence),
            "interpretation": "Prior validation is context only and does not validate current code, configuration, sources, facility, or preferences.",
        },
        "prospective_holdout": {
            "status": "NOT_PERFORMED_FOR_CURRENT_RUN",
            "interpretation": "The accepted Phase 6 holdout belongs to its frozen historical model version.",
        },
        "inactive_analyses": [
            {"module_id": "climate_to_cooling_response", "status": "INAPPLICABLE", "reason": "No configured defensible response function was supplied."},
            {"module_id": "construction_lifecycle_sensitivity", "status": "INAPPLICABLE", "reason": "No configured real inventory and compatible factor set was supplied."},
        ],
        "remaining_blockers": [
            "Independent facility observations and engineering benchmarks remain unavailable.",
            "Regional evidence does not verify parcel buildability, utility capacity, water supply, fiber, or approvals.",
            "A current prospective geographic holdout was not performed.",
        ],
        "overall_accuracy": None,
    }
    return CurrentRunValidationResult(
        sensitivity_results=sensitivity.sort_values(["case_id", "baseline_scenario_id", "grid_id", "design_id"]).reset_index(drop=True),
        robustness_summary=robustness.sort_values(["case_id", "baseline_scenario_id"]).reset_index(drop=True),
        alternative_rank_ranges=rank_ranges.sort_values(["baseline_scenario_id", "grid_id", "design_id"]).reset_index(drop=True),
        fixed_region_summary=fixed_regions.sort_values(["case_id", "baseline_scenario_id", "region_id", "design_id"]).reset_index(drop=True) if len(fixed_regions) else fixed_regions,
        validation_report=report,
        validation_markdown=_markdown(report),
    )


__all__ = [
    "CurrentRunIdentity", "CurrentSensitivityCase", "CurrentValidationSettings",
    "FutureValidationContext", "CurrentRunValidationResult", "validate_current_run",
]
