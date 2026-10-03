"""Deterministic, scenario-separated rank and fixed-region comparisons."""

from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd

from dc_locator.model.metrics import clean, json_text
from dc_locator.model.validation.schemas import FixedRegionSummaryRow, RobustnessSummaryRow, SensitivityResultRow


METRIC_IDS = [
    "annual_electricity_co2e", "annual_site_water_consumption",
    "local_baseline_water_stress", "transmission_proximity", "suitable_land_fraction",
]
PAIR_KEY = ["grid_id", "design_id"]


def _strict_bool_series(series, label):
    if not series.map(lambda value: isinstance(value, (bool, np.bool_))).all():
        raise ValueError(f"{label} must contain only boolean values")
    return series.astype(bool)


def _validate_ranked_frame(frame, label):
    required = {
        "grid_id", "grid_definition_id", "facility_id", "design_id", "scenario_id", "data_mode",
        "eligible", "rankable", "hard_fail", "critical_unknown", "conditional", "mcda_rank", "mcda_score",
        "profile_id", "is_pareto_optimal", "mode",
    }
    if frame.empty or not required <= set(frame):
        raise ValueError(f"{label} is empty or lacks required ranked-result fields")
    if frame.duplicated(PAIR_KEY).any():
        raise ValueError(f"{label} has duplicate grid/design alternatives")
    for field in ("grid_definition_id", "facility_id", "data_mode", "scenario_id", "mode"):
        values = frame[field].dropna().unique()
        if len(values) != 1 or len(values) != frame[field].nunique(dropna=False):
            raise ValueError(f"{label} must have one non-null {field}")
    if str(frame.data_mode.iloc[0]) not in {"real", "synthetic"}:
        raise ValueError(f"{label} has invalid data_mode")
    mode = str(frame["mode"].iloc[0])
    if mode not in {"STRICT", "EXPLORATORY"}:
        raise ValueError(f"{label} has invalid screening mode")
    if not frame.grid_id.map(lambda value: isinstance(value, str) and bool(value)).all() or not frame.design_id.map(lambda value: isinstance(value, str) and bool(value)).all():
        raise ValueError(f"{label} grid/design identities must be nonempty strings")
    flags = {field: _strict_bool_series(frame[field], f"{label}.{field}") for field in ("eligible", "rankable", "hard_fail", "critical_unknown", "conditional")}
    ranks = pd.to_numeric(frame.mcda_rank, errors="coerce")
    scores = pd.to_numeric(frame.mcda_score, errors="coerce")
    has_rank, has_score = ranks.notna(), scores.notna()
    if not has_rank.equals(flags["rankable"]) or not has_score.equals(flags["rankable"]):
        raise ValueError(f"{label} rank/score nullability contradicts rankable")
    if has_rank.any() and (not np.isfinite(ranks[has_rank]).all() or (ranks[has_rank] < 1).any() or not (ranks[has_rank] % 1 == 0).all()):
        raise ValueError(f"{label} contains invalid ranks")
    if has_score.any() and (not np.isfinite(scores[has_score]).all() or not scores[has_score].between(0, 100).all()):
        raise ValueError(f"{label} contains invalid scores")
    if (flags["rankable"] & (~flags["eligible"] | flags["hard_fail"])).any():
        raise ValueError(f"{label} ranks an ineligible or hard-failing alternative")
    if (flags["hard_fail"] & flags["eligible"]).any():
        raise ValueError(f"{label} marks a hard failure eligible")
    if (flags["conditional"] & (~flags["eligible"] | flags["hard_fail"] | ~flags["critical_unknown"])).any():
        raise ValueError(f"{label} has inconsistent conditional flags")
    if mode == "STRICT" and (flags["conditional"].any() or (flags["critical_unknown"] & (flags["eligible"] | flags["rankable"])).any()):
        raise ValueError(f"{label} violates strict UNKNOWN exclusion")
    if mode == "EXPLORATORY" and not flags["conditional"].equals(flags["eligible"] & flags["critical_unknown"]):
        raise ValueError(f"{label} exploratory conditional flags are inconsistent")
    return {
        "grid_definition_id": str(frame.grid_definition_id.iloc[0]),
        "facility_id": str(frame.facility_id.iloc[0]),
        "data_mode": str(frame.data_mode.iloc[0]),
        "scenario_id": str(frame.scenario_id.iloc[0]),
    }


def _one_scenario(frame, label):
    values = sorted(set(frame.scenario_id))
    if len(values) != 1:
        raise ValueError(f"{label} must contain exactly one separated external scenario")
    return values[0]


def stable_top_k(frame, k):
    if type(k) is not int or k < 1:
        raise ValueError("Top-k requires a positive explicit integer")
    _validate_ranked_frame(frame, "Top-k table")
    ranked = frame.loc[frame.rankable].sort_values(
        ["mcda_score", "grid_id", "design_id", "scenario_id"],
        ascending=[False, True, True, True], kind="stable",
    )
    return set(map(tuple, ranked.head(k)[PAIR_KEY].to_numpy()))


def _finite_or_none(value):
    value = clean(value)
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def compare_ranked_cases(base, case, *, evaluation_version, freeze_id, case_id, case_category, k, case_metadata):
    """Match grid/design across two separately evaluated external contexts."""
    base_identity = _validate_ranked_frame(base, "Baseline")
    case_identity = _validate_ranked_frame(case, "Case")
    for field in ("grid_definition_id", "facility_id", "data_mode"):
        if base_identity[field] != case_identity[field]:
            raise ValueError(f"Sensitivity case has incompatible {field}")
    base_scenario, case_scenario = _one_scenario(base, "Baseline"), _one_scenario(case, "Case")
    base_keys, case_keys = set(map(tuple, base[PAIR_KEY].to_numpy())), set(map(tuple, case[PAIR_KEY].to_numpy()))
    if base_keys != case_keys:
        raise ValueError("Sensitivity cases must align the exact grid/design alternative domain")
    base_top, case_top = stable_top_k(base, k), stable_top_k(case, k)
    b = base.set_index(PAIR_KEY, drop=False)
    c = case.set_index(PAIR_KEY, drop=False)
    rows = []
    for key in sorted(base_keys):
        left, right = b.loc[key], c.loc[key]
        raw_base = {m: _finite_or_none(left.get("raw_" + m)) for m in METRIC_IDS}
        raw_case = {m: _finite_or_none(right.get("raw_" + m)) for m in METRIC_IDS}
        raw_delta = {m: None if raw_base[m] is None or raw_case[m] is None else raw_case[m] - raw_base[m] for m in METRIC_IDS}
        contribution_base = {m: _finite_or_none(left.get("contribution_" + m)) for m in METRIC_IDS}
        contribution_case = {m: _finite_or_none(right.get("contribution_" + m)) for m in METRIC_IDS}
        contribution_delta = {m: None if contribution_base[m] is None or contribution_case[m] is None else contribution_case[m] - contribution_base[m] for m in METRIC_IDS}
        known = {m: abs(v) for m, v in contribution_delta.items() if v is not None and abs(v) > 1e-15}
        driver = min((m for m, v in known.items() if v == max(known.values())), default=None)
        base_rankable, case_rankable = bool(left.rankable), bool(right.rankable)
        base_rank = int(left.mcda_rank) if base_rankable else None
        case_rank = int(right.mcda_rank) if case_rankable else None
        base_score = float(left.mcda_score) if base_rankable else None
        case_score = float(right.mcda_score) if case_rankable else None
        row = SensitivityResultRow(
            evaluation_version=evaluation_version, freeze_id=freeze_id, case_id=case_id,
            case_category=case_category, grid_definition_id=str(left.grid_definition_id),
            data_mode=str(left.data_mode), grid_id=key[0], design_id=key[1],
            baseline_scenario_id=base_scenario, case_scenario_id=case_scenario,
            baseline_profile_id=str(left.profile_id), case_profile_id=str(right.profile_id),
            base_eligible=bool(left.eligible), case_eligible=bool(right.eligible),
            eligibility_changed=bool(left.eligible) != bool(right.eligible),
            base_rankable=base_rankable, case_rankable=case_rankable,
            base_hard_fail=bool(left.hard_fail), case_hard_fail=bool(right.hard_fail),
            base_critical_unknown=bool(left.critical_unknown), case_critical_unknown=bool(right.critical_unknown),
            base_conditional=bool(left.conditional), case_conditional=bool(right.conditional),
            base_rank=base_rank, case_rank=case_rank,
            rank_change=None if base_rank is None or case_rank is None else case_rank - base_rank,
            base_score=base_score, case_score=case_score,
            score_change=None if base_score is None or case_score is None else case_score - base_score,
            base_pareto=clean(left.get("is_pareto_optimal")), case_pareto=clean(right.get("is_pareto_optimal")),
            base_top_k=key in base_top, case_top_k=key in case_top,
            main_driver=driver, driver_abs_contribution_change=None if driver is None else known[driver],
            base_raw_metrics_json=json_text(raw_base), case_raw_metrics_json=json_text(raw_case),
            raw_metric_delta_json=json_text(raw_delta), base_contributions_json=json_text(contribution_base),
            case_contributions_json=json_text(contribution_case), contribution_delta_json=json_text(contribution_delta),
            case_assumptions_json=json_text(case_metadata),
            status="MATCHED_RANKED" if case_rankable else "MATCHED_INELIGIBLE" if not bool(right.eligible) else "MATCHED_UNRANKED",
        ).model_dump(mode="json")
        rows.append(row)
    return pd.DataFrame(rows).sort_values(PAIR_KEY).reset_index(drop=True)


def summarize_case(comparison, case_ranked, *, evaluation_version, freeze_id, case_id, case_category, k, weighting_method):
    _validate_ranked_frame(case_ranked, "Robustness case")
    base_top = set(map(tuple, comparison.loc[comparison.base_top_k, PAIR_KEY].to_numpy()))
    case_top = set(map(tuple, comparison.loc[comparison.case_top_k, PAIR_KEY].to_numpy()))
    union = base_top | case_top
    both = comparison.loc[comparison.base_rankable & comparison.case_rankable]
    correlation = None if len(both) < 2 else float(np.corrcoef(both.base_rank.astype(float), both.case_rank.astype(float))[0, 1])
    if correlation is not None and not math.isfinite(correlation):
        correlation = None
    changes = both.rank_change.abs()
    driver_values = {m: [] for m in METRIC_IDS}
    for encoded in comparison.contribution_delta_json:
        for metric, value in json.loads(encoded).items():
            if value is not None:
                driver_values[metric].append(abs(float(value)))
    means = {m: float(np.mean(v)) for m, v in driver_values.items() if v}
    positive = {m: v for m, v in means.items() if v > 1e-15}
    driver = min((m for m, v in positive.items() if v == max(positive.values())), default=None)
    row = RobustnessSummaryRow(
        evaluation_version=evaluation_version, freeze_id=freeze_id, case_id=case_id,
        case_category=case_category, alternatives=len(case_ranked), eligible=int(case_ranked.eligible.sum()),
        rankable=int(case_ranked.rankable.sum()),
        conditional_ranked=int((case_ranked.rankable & case_ranked.conditional).sum()),
        hard_failures=int(case_ranked.hard_fail.sum()), eligibility_changes=int(comparison.eligibility_changed.sum()),
        top_k_requested=k, baseline_top_k_count=len(base_top), case_top_k_count=len(case_top),
        top_k_overlap_count=len(base_top & case_top), top_k_jaccard=None if not union else len(base_top & case_top) / len(union),
        rank_correlation=correlation, mean_absolute_rank_change=None if changes.empty else float(changes.mean()),
        maximum_absolute_rank_change=None if changes.empty else int(changes.max()),
        main_driver=driver, main_driver_mean_abs_contribution_change=None if driver is None else means[driver],
        weighting_method=weighting_method,
        baseline_scenario_id=str(comparison.baseline_scenario_id.iloc[0]),
        case_scenario_id=str(comparison.case_scenario_id.iloc[0]),
        comparison_key_json=json_text(PAIR_KEY),
    )
    return row.model_dump(mode="json")


def summarize_fixed_regions(membership, case_ranked, *, evaluation_version, freeze_id, case_id, baseline_scenario_id):
    required = {"region_id", "grid_id", "design_id", "scenario_id"}
    if not required <= set(membership) or membership.empty or membership.duplicated(["region_id", "grid_id", "design_id"]).any():
        raise ValueError("Accepted baseline region membership is malformed")
    _validate_ranked_frame(case_ranked, "Fixed-region case")
    case_scenario = _one_scenario(case_ranked, "Fixed-region case")
    case = case_ranked.set_index(PAIR_KEY, drop=False)
    rows = []
    for (region_id, design_id), group in membership.groupby(["region_id", "design_id"], sort=True):
        if set(group.scenario_id) != {baseline_scenario_id}:
            raise ValueError("Fixed membership is not the declared baseline scenario")
        members = []
        for grid_id in sorted(group.grid_id):
            key = (grid_id, design_id)
            if key not in case.index:
                raise ValueError("Sensitivity case dropped a fixed baseline member")
            members.append(case.loc[key])
        ranks = [int(r.mcda_rank) for r in members if bool(r.rankable)]
        row = FixedRegionSummaryRow(
            evaluation_version=evaluation_version, freeze_id=freeze_id, case_id=case_id,
            region_id=str(region_id), design_id=str(design_id), baseline_scenario_id=baseline_scenario_id,
            case_scenario_id=case_scenario, total_baseline_members=len(group), matched_members=len(members),
            eligible_members=sum(bool(r.eligible) for r in members), rankable_members=len(ranks),
            unranked_members=len(members)-len(ranks), case_rank_min=min(ranks) if ranks else None,
            case_rank_max=max(ranks) if ranks else None,
            case_rank_mean=float(np.mean(ranks)) if len(ranks) == len(members) else None,
        )
        rows.append(row.model_dump(mode="json"))
    return pd.DataFrame(rows).sort_values(["region_id", "design_id"]).reset_index(drop=True)


__all__ = ["METRIC_IDS", "PAIR_KEY", "compare_ranked_cases", "stable_top_k", "summarize_case", "summarize_fixed_regions"]
