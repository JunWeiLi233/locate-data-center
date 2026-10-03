"""Frozen Phase 6 verification, sensitivity, and prospective-holdout runner.

The runner recomputes screening, physical performance, and decisions for every
case.  It never edits an accepted geography, provenance, or Phase 5 result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import shapely

from dc_locator.config import load_facility_config
from dc_locator.geography.sources.aqueduct_future import future_period
from dc_locator.io import read_geoparquet, read_parquet, read_parquet_metadata, write_parquet
from dc_locator.model.cooling import CoolingDesign, load_cooling_designs, load_physical_scenarios
from dc_locator.model.decision import decide, sha256
from dc_locator.model.enhanced import _read_baseline, rebind_external_scenario, validate_matched_preferences
from dc_locator.model.metrics import ScoringProfile, clean, json_text, load_profile, profile_fingerprint
from dc_locator.model.physics import simulate
from dc_locator.model.scenarios import ExternalScenario, make_external_scenarios
from dc_locator.model.screening import Requirement, load_requirements, screen
from dc_locator.model.validation.analysis import (
    METRIC_IDS,
    compare_ranked_cases,
    summarize_case,
    summarize_fixed_regions,
)
from dc_locator.model.validation.config import Phase6Config, load_phase6_config
from dc_locator.model.validation.freeze import verify_freeze
from dc_locator.model.validation.schemas import AlternativeRankRangeRow
from dc_locator.provenance import DataMode
from dc_locator.schemas import FacilityConfig


@dataclass(frozen=True)
class CaseRun:
    case_id: str
    category: str
    result: dict
    screening_summary: dict
    assumptions: dict
    profile: ScoringProfile
    external_scenario: ExternalScenario


def _root() -> Path:
    return Path(__file__).resolve().parents[4]


def _path(root: Path, value: str | Path) -> Path:
    target = Path(value)
    return target if target.is_absolute() else root / target


def _scenario(physical_id: str, pathway: str, year: int) -> ExternalScenario:
    return make_external_scenarios(physical_id, [future_period(pathway, year)])[0]


def _case_scenario(base: ExternalScenario, case_id: str) -> ExternalScenario:
    document = base.model_dump(mode="json")
    document["scenario_id"] = f"{base.scenario_id}__phase6_{case_id}"
    return ExternalScenario.model_validate(document)


def _custom_profile(base: ScoringProfile, case_id: str, *, group_weights=None, removed_group=None) -> ScoringProfile:
    document = base.model_dump(mode="json")
    document["profile_id"] = f"{base.profile_id}__phase6_{case_id}"
    document["profile_version"] = "phase6_v1"
    document["description"] = f"{base.description} Phase 6 preregistered case {case_id}."
    if group_weights is not None:
        document["weighting_method"] = "user"
        document["user_weights"] = dict(group_weights)
        document["ahp_judgments"] = None
    if removed_group is not None:
        removed = [m for m in document["metrics"] if m["group_id"] == removed_group]
        retained = [m for m in document["metrics"] if m["group_id"] != removed_group]
        groups = [g for g in document["groups"] if g["group_id"] != removed_group]
        for group in groups:
            group["equal_parent_weight"] = 1 / len(groups)
        document["metrics"] = retained
        document["groups"] = groups
        document["weighting_method"] = "equal"
        document["user_weights"] = None
        document["ahp_judgments"] = None
        document["pareto"]["absolute_tolerances"] = {
            key: value for key, value in document["pareto"]["absolute_tolerances"].items()
            if key in {m["metric_id"] for m in retained}
        }
        document["excluded_criteria"] = list(document["excluded_criteria"]) + [
            {
                "criterion": m["metric_id"],
                "reason": f"Phase 6 diagnostic ablation removed parent group {removed_group}; this is not evidence that the criterion is unimportant.",
            }
            for m in removed
        ]
    return ScoringProfile.model_validate(document)


def _adjust_designs(designs: list[CoolingDesign], field: str, multiplier: float) -> list[CoolingDesign]:
    adjusted = []
    for design in designs:
        document = design.model_dump(mode="json")
        value = document[field]
        document[field] = None if value is None else value * multiplier
        document["rationale"] = (
            f"{document['rationale']} Phase 6 preregistered multiplier {multiplier:g} applied to {field}; "
            "this is a project-assumption stress case, not an empirical uncertainty interval."
        )
        adjusted.append(CoolingDesign.model_validate(document))
    return adjusted


def _adjust_facility(facility: FacilityConfig, field: str, multiplier: float) -> FacilityConfig:
    document = facility.model_dump(mode="json")
    value = document[field]
    document[field] = None if value is None else value * multiplier
    document["rationale"] = (
        f"{document['rationale']} Phase 6 preregistered multiplier {multiplier:g} applied to {field}; "
        "this is a project-assumption stress case."
    )
    return FacilityConfig.model_validate(document)


def _carbon_scenario_view(geography, provenance, multiplier: float, case_id: str):
    """Return an ephemeral scenario view while retaining the EPA source trail."""
    metric = "grid_carbon_intensity_kg_per_mwh"
    geo = geography.copy()
    prov = provenance.copy()
    geo.attrs.update(geography.attrs)
    prov.attrs.update(provenance.attrs)
    selected = prov.metric.eq(metric)
    if not selected.any() or selected.sum() != len(geo):
        raise ValueError("Every cell needs one carbon provenance row before scenario scaling")
    originals = pd.to_numeric(prov.loc[selected, "value"], errors="raise")
    if originals.isna().any() or not np.isfinite(originals).all():
        raise ValueError("Carbon sensitivity cannot scale missing or nonfinite factors")
    wide = pd.to_numeric(geo[metric], errors="raise")
    if wide.isna().any() or not np.isfinite(wide).all():
        raise ValueError("Carbon sensitivity cannot scale missing or nonfinite wide values")
    geo[metric] = wide * multiplier
    geo[metric + "_status"] = "scenario"
    prov.loc[selected, "value"] = originals * multiplier
    prov.loc[selected, "status"] = "scenario"
    methods = []
    for original, prior in zip(originals, prov.loc[selected, "aggregation_method"]):
        methods.append(
            f"{prior}; Phase6 {case_id} project-assumption multiplier={multiplier:g} applied to "
            f"original EPA eGRID2023 SRC2ERTA-derived value={float(original):.12g}; scaled value is not publisher-observed SRC2ERTA"
        )
    prov.loc[selected, "aggregation_method"] = methods
    metadata = {
        "basis": "project_assumption",
        "case_id": case_id,
        "factor": multiplier,
        "input_source_id": "epa_egrid",
        "input_source_field": "SRC2ERTA",
        "input_source_year": "2023",
        "input_value_min": float(originals.min()),
        "input_value_max": float(originals.max()),
        "transformed_status": "scenario",
        "interpretation": "Counterfactual scaling of historical eGRID2023 evidence; not an EPA value or future-grid forecast.",
    }
    return geo, prov, metadata


def _annotate_performance(performance: pd.DataFrame, assumptions: dict) -> pd.DataFrame:
    result = performance.copy()
    encoded, warnings = [], []
    warning = assumptions.get("warning")
    for assumption_text, warning_text in zip(result.assumptions_json, result.warnings_json):
        document = json.loads(assumption_text)
        document["phase6_validation_case"] = assumptions
        encoded.append(json_text(document))
        items = json.loads(warning_text)
        if warning and warning not in items:
            items.append(warning)
        warnings.append(json_text(items))
    result["assumptions_json"] = encoded
    result["warnings_json"] = warnings
    return result


def _run_case(
    geography,
    provenance,
    facility,
    designs,
    physical,
    requirements,
    profile,
    external,
    *,
    mode,
    case_id,
    category,
    assumptions,
    annotate_performance=True,
    profile_hash=None,
) -> CaseRun:
    screening, eligibility, summary = screen(
        geography, provenance, facility, designs, [physical], requirements, mode=mode
    )
    performance = simulate(geography, provenance, facility, designs, [physical])
    performance = rebind_external_scenario(performance, external, physical_metadata=True)
    eligibility = rebind_external_scenario(eligibility, external)
    if annotate_performance:
        performance = _annotate_performance(performance, assumptions)
    result = decide(
        geography,
        provenance,
        performance,
        eligibility,
        profile,
        profile_hash=profile_hash or profile_fingerprint(profile),
        provenance_grid_definition_id=provenance.attrs.get("grid_definition_id"),
    )
    if len(result["ranked_cells"]) != len(geography) * len(designs):
        raise ValueError("A validation case did not retain every grid/design alternative")
    if result["ranked_cells"].hard_fail.any() and result["ranked_cells"].loc[result["ranked_cells"].hard_fail, "rankable"].any():
        raise ValueError("Hard failures entered ranking")
    return CaseRun(case_id, category, result, summary, assumptions, profile, external)


def _load_profile_declaration(root: Path, config: Phase6Config, baseline: ScoringProfile):
    declaration_path = _path(root, config.inputs["phase5_profile_declaration"])
    declaration = json.loads(declaration_path.read_text(encoding="utf-8"))
    accepted_original = root / "configs" / "scoring_profile.yaml"
    if declaration.get("status") != "PREDECLARED_BEFORE_FIRST_RANKING" or declaration.get("baseline_profile_sha256") != sha256(accepted_original):
        raise ValueError("Phase 5 profile declaration no longer binds the accepted original profile")
    entries = {Path(item["path"]).stem: item for item in declaration.get("profiles", [])}
    profile_paths = [_path(root, config.inputs["baseline_profile"])] + [_path(root, case.profile) for case in config.water_cases]
    for path in profile_paths:
        entry = entries.get(path.stem)
        profile = load_profile(path)
        if not entry or entry.get("status") != "PREDECLARED_BEFORE_FIRST_RANKING" or sha256(path) != entry.get("sha256"):
            raise ValueError("Future-water profile is missing or changed after Phase 5 predeclaration")
        if profile.model_dump(mode="json") != ScoringProfile.model_validate(entry.get("profile")).model_dump(mode="json"):
            raise ValueError("Future-water profile content differs from its declaration")
        validate_matched_preferences(baseline, profile)
    return declaration


def _assert_accepted_baseline(fresh: pd.DataFrame, accepted: pd.DataFrame):
    if set(fresh.columns) != set(accepted.columns):
        raise ValueError("Fresh Phase 6 baseline columns differ from the accepted Phase 5 baseline")
    order = ["grid_id", "design_id", "scenario_id"]
    left = fresh.sort_values(order).reset_index(drop=True)[accepted.columns]
    right = accepted.sort_values(order).reset_index(drop=True)
    try:
        pd.testing.assert_frame_equal(left, right, check_dtype=False, check_exact=True)
    except AssertionError as exc:
        raise ValueError("Fresh Phase 6 baseline does not reproduce accepted Phase 5 decision rows") from exc


def _input_hashes(
    root: Path, config: Phase6Config, config_path: Path, freeze_manifest: Path | None,
    *, include_holdout: bool = False,
):
    paths = [config_path, _path(root, config.accepted_phase5_record), _path(root, config.preselection_manifest)]
    paths += [_path(root, value) for value in config.inputs.values()]
    paths += [_path(root, case.profile) for case in config.water_cases]
    software_evidence = _path(root, config.software_evidence)
    if software_evidence.is_file():
        paths.append(software_evidence)
    elif freeze_manifest is not None:
        raise FileNotFoundError("Frozen/final Phase 6 run requires software verification evidence")
    if freeze_manifest is not None:
        paths.append(freeze_manifest)
    if include_holdout:
        for geography_field, provenance_field in (
            ("holdout_geography", "holdout_provenance"),
            ("fine_geography", "fine_provenance"),
            ("coarse_geography", "coarse_provenance"),
        ):
            geography_path = _path(root, getattr(config.holdout, geography_field))
            paths.extend([geography_path, _path(root, getattr(config.holdout, provenance_field))])
            paths.append(geography_path.parents[1] / "evaluation_manifest.json")
    unique = sorted(set(path.resolve() for path in paths))
    missing = [str(path) for path in unique if not path.is_file()]
    if missing:
        raise FileNotFoundError("Required Phase 6 inputs are missing: " + ", ".join(missing))
    return {str(path.relative_to(root)): sha256(path) for path in unique}


def _load_freeze(path: Path | None, config: Phase6Config, *, required: bool):
    if path is None:
        if required:
            raise ValueError("Prospective holdout evaluation requires the preserved pre-holdout freeze manifest")
        return {"freeze_id": "PREHOLDOUT_DRY_RUN", "status": "PREFLIGHT_ONLY"}
    document = verify_freeze(path)
    if document.get("status") != "FROZEN_BEFORE_HOLDOUT" or not document.get("freeze_id"):
        raise ValueError("Invalid Phase 6 freeze manifest")
    if document.get("evaluation_version") != config.evaluation_version:
        raise ValueError("Freeze evaluation version differs from Phase 6 configuration")
    return document


def _case_runs(config, geography, provenance, facility, designs, physical, requirements, baseline_profile, baseline_external, baseline_profile_hash):
    base_assumptions = {
        "basis": config.baseline.basis,
        "rationale": config.baseline.rationale,
        "case_id": config.baseline.case_id,
        "external_context": baseline_external.model_dump(mode="json"),
    }
    baseline = _run_case(
        geography, provenance, facility, designs, physical, requirements, baseline_profile, baseline_external,
        mode=config.baseline.screening_mode, case_id=config.baseline.case_id, category="baseline", assumptions=base_assumptions,
        annotate_performance=False, profile_hash=baseline_profile_hash,
    )
    cases = [baseline]
    for spec in config.weight_cases:
        profile = _custom_profile(baseline_profile, spec.case_id, group_weights=spec.group_weights)
        external = _case_scenario(baseline_external, spec.case_id)
        metadata = {**spec.model_dump(mode="json"), "external_context": external.model_dump(mode="json")}
        cases.append(_run_case(geography, provenance, facility, designs, physical, requirements, profile, external,
            mode=config.baseline.screening_mode, case_id=spec.case_id, category="weights", assumptions=metadata))
    for spec in config.scalar_cases:
        geo, prov, adjusted_facility, adjusted_designs = geography, provenance, facility, designs
        metadata = spec.model_dump(mode="json")
        if spec.category == "pue":
            adjusted_designs = _adjust_designs(designs, "annual_pue", spec.multiplier)
        elif spec.category == "wue":
            adjusted_designs = _adjust_designs(designs, "wue_l_per_it_kwh", spec.multiplier)
        elif spec.category == "load":
            adjusted_facility = _adjust_facility(facility, "average_it_load_factor", spec.multiplier)
        elif spec.category == "land":
            adjusted_facility = _adjust_facility(facility, "minimum_land_area_km2", spec.multiplier)
        elif spec.category == "carbon":
            geo, prov, carbon_metadata = _carbon_scenario_view(geography, provenance, spec.multiplier, spec.case_id)
            metadata["carbon_source_transform"] = carbon_metadata
            metadata["warning"] = carbon_metadata["interpretation"]
        external = _case_scenario(baseline_external, spec.case_id)
        metadata["external_context"] = external.model_dump(mode="json")
        cases.append(_run_case(geo, prov, adjusted_facility, adjusted_designs, physical, requirements,
            baseline_profile, external, mode=config.baseline.screening_mode, case_id=spec.case_id,
            category=spec.category, assumptions=metadata, profile_hash=baseline_profile_hash))
    for spec in config.water_cases:
        profile = load_profile(_path(_root(), spec.profile))
        external = _scenario(physical.scenario_id, spec.pathway, spec.milestone_year)
        metadata = {
            **spec.model_dump(mode="json"),
            "basis": "native_aqueduct_scenario",
            "rationale": "Separate native Aqueduct pathway/milestone/window context; no interpolation or weather optimization.",
            "external_context": external.model_dump(mode="json"),
        }
        cases.append(_run_case(geography, provenance, facility, designs, physical, requirements, profile, external,
            mode=config.baseline.screening_mode, case_id=spec.case_id, category="water", assumptions=metadata,
            profile_hash=sha256(_path(_root(), spec.profile))))
    for spec in config.screening_cases:
        external = _case_scenario(baseline_external, spec.case_id)
        metadata = {**spec.model_dump(mode="json"), "external_context": external.model_dump(mode="json")}
        cases.append(_run_case(geography, provenance, facility, designs, physical, requirements,
            baseline_profile, external, mode=spec.mode, case_id=spec.case_id, category="screening", assumptions=metadata,
            profile_hash=baseline_profile_hash))
    for spec in config.ablation_cases:
        profile = _custom_profile(baseline_profile, spec.case_id, removed_group=spec.removed_group)
        external = _case_scenario(baseline_external, spec.case_id)
        metadata = {
            **spec.model_dump(mode="json"),
            "basis": "diagnostic_ablation",
            "renormalization": config.ablation_policy.model_dump(mode="json"),
            "external_context": external.model_dump(mode="json"),
            "driver_scope": "Known retained-metric contribution changes only; omitted contribution is declared zero by policy, not missing evidence.",
        }
        cases.append(_run_case(geography, provenance, facility, designs, physical, requirements, profile, external,
            mode=config.baseline.screening_mode, case_id=spec.case_id, category="ablation", assumptions=metadata))
    return cases


def _data_quality(provenance: pd.DataFrame, dataset: str) -> pd.DataFrame:
    rows = []
    for metric, group in provenance.groupby("metric", sort=True):
        coverage = pd.to_numeric(group.coverage_frac, errors="coerce")
        known = (group.value.notna() | group.value_text.notna()) & ~group.status.eq("unknown")
        unknown = group.status.eq("unknown")
        partial_coverage = coverage.notna() & coverage.lt(1 - 1e-6) & ~unknown
        rows.append({
            "dataset": dataset,
            "metric": metric,
            "rows": len(group),
            "known_rows": int(known.sum()),
            "unknown_rows": int(unknown.sum()),
            "partial_coverage_rows": int(partial_coverage.sum()),
            "minimum_coverage_frac": None if coverage.notna().sum() == 0 else float(coverage.min()),
            "mean_coverage_frac": None if coverage.notna().sum() == 0 else float(coverage.mean()),
            "source_ids_json": json_text(sorted(set(group.source_id.dropna().astype(str)))),
        })
    return pd.DataFrame(rows)


def _manifest_hash(binding_root: Path, mapping: dict, required_path: Path):
    matches = []
    for key, expected in mapping.items():
        candidate = Path(key)
        candidate = candidate if candidate.is_absolute() else binding_root / candidate
        if candidate.resolve() == required_path.resolve():
            matches.append(expected)
    if len(matches) != 1 or matches[0] != sha256(required_path):
        raise ValueError(f"Evaluation manifest hash is missing or wrong for {required_path}")


def _resolve_manifest_path(base: Path, value: str) -> Path:
    candidate = Path(value)
    return candidate if candidate.is_absolute() else (base / candidate).resolve()


def _frozen_records_by_path(root: Path, freeze: dict) -> dict[Path, tuple[str, bool]]:
    records = {}
    for section in ("software_files", "input_files"):
        for record in freeze.get(section, {}).values():
            target = _path(root, record["path"]).resolve()
            records[target] = (record["sha256"], record.get("directory_member_count") is not None)
    return records


def _protected_by_freeze(candidate: Path, expected: str, frozen_records: dict[Path, tuple[str, bool]]) -> bool:
    exact = frozen_records.get(candidate)
    if exact is not None:
        return exact[0] == expected
    return any(is_directory and candidate.is_relative_to(path) for path, (_, is_directory) in frozen_records.items())


def _verify_build_manifest(
    root: Path, binding: Path, dataset_id: str, freeze_id: str, geo_path: Path, prov_path: Path,
    freeze_path: Path, freeze: dict,
):
    document = json.loads(binding.read_text(encoding="utf-8"))
    required = {
        "schema_version", "phase6_freeze_id", "dataset_id", "grid_definition_id", "grid_ids",
        "output_hashes", "repeat_output_hashes", "repeat_identical", "build_evidence",
    }
    if set(document) != required or document["schema_version"] != "1.0.0":
        raise ValueError("Holdout evaluation manifest has an incompatible contract")
    if document["phase6_freeze_id"] != freeze_id or document["dataset_id"] != dataset_id:
        raise ValueError("Holdout feature build is not bound to this freeze/dataset")
    if document["repeat_identical"] is not True:
        raise ValueError("Holdout native build repeat was not byte-identical")
    evidence = document["build_evidence"]
    if not isinstance(evidence, dict) or set(evidence) != {"build_script", "freeze_manifest_sha256", "protected_input_hashes"}:
        raise ValueError("Holdout build evidence has an incompatible contract")
    if evidence["freeze_manifest_sha256"] != sha256(freeze_path):
        raise ValueError("Holdout build evidence refers to a different freeze manifest")
    script = evidence["build_script"]
    if not isinstance(script, dict) or set(script) != {"path", "sha256"}:
        raise ValueError("Holdout build-script evidence has an incompatible contract")
    script_path = _resolve_manifest_path(binding.parent, script["path"])
    expected_script = (root / "runs" / "phase6" / "inputs" / "preselection" / "build_inputs.py").resolve()
    if script_path != expected_script or not script_path.is_file() or sha256(script_path) != script["sha256"]:
        raise ValueError("Holdout build script is missing, changed, or not the preregistered script")
    protected = evidence["protected_input_hashes"]
    if not isinstance(protected, dict) or not protected:
        raise ValueError("Holdout build evidence lacks protected input hashes")
    frozen_records = _frozen_records_by_path(root, freeze)
    if not _protected_by_freeze(script_path, script["sha256"], frozen_records):
        raise ValueError("Holdout build script was not captured by the pre-evaluation freeze")
    for relative, expected in protected.items():
        candidate = _resolve_manifest_path(binding.parent, relative)
        if not candidate.is_file() or sha256(candidate) != expected:
            raise ValueError("Holdout protected build input is missing or changed")
        if not _protected_by_freeze(candidate, expected, frozen_records):
            raise ValueError("Holdout build input was not protected by the pre-evaluation freeze")
    _manifest_hash(binding.parent, document["output_hashes"], geo_path)
    _manifest_hash(binding.parent, document["output_hashes"], prov_path)
    primary_hashes = []
    primary_paths = set()
    if not isinstance(document["output_hashes"], dict) or not document["output_hashes"]:
        raise ValueError("Holdout primary output hashes are missing")
    for key, expected in document["output_hashes"].items():
        candidate = _resolve_manifest_path(binding.parent, key)
        if not candidate.is_relative_to(binding.parent.resolve()) or candidate in primary_paths:
            raise ValueError("Holdout primary output path is duplicated or outside its immutable dataset directory")
        if not candidate.is_file() or sha256(candidate) != expected:
            raise ValueError("Holdout primary artifact is missing or changed")
        primary_paths.add(candidate)
        primary_hashes.append(expected)
    repeat_hashes = document["repeat_output_hashes"]
    if not isinstance(repeat_hashes, dict) or not repeat_hashes:
        raise ValueError("Holdout repeat output hashes are missing")
    actual_repeat = []
    for key, expected in repeat_hashes.items():
        candidate = Path(key)
        candidate = candidate if candidate.is_absolute() else binding.parent / candidate
        candidate = candidate.resolve()
        if not candidate.is_relative_to(binding.parent.resolve()) or not candidate.is_file() or sha256(candidate) != expected:
            raise ValueError("Holdout repeated artifact is missing or changed")
        actual_repeat.append(expected)
    if sorted(actual_repeat) != sorted(primary_hashes):
        raise ValueError("Holdout primary/repeat substantive hashes differ")
    return document


def _geometry_sha(geometry):
    return hashlib.sha256(geometry.wkb).hexdigest()


def _load_holdout_pair(
    root: Path, geography_path: str, provenance_path: str, expected: int, freeze_id: str,
    dataset_id: str, selection: dict, freeze_path: Path, freeze: dict,
):
    geo_path, prov_path = _path(root, geography_path), _path(root, provenance_path)
    binding = geo_path.parents[1] / "evaluation_manifest.json"
    if not binding.is_file():
        raise FileNotFoundError(f"Holdout feature build lacks freeze-binding manifest: {binding}")
    document = _verify_build_manifest(root, binding, dataset_id, freeze_id, geo_path, prov_path, freeze_path, freeze)
    geography, provenance, metadata = _read_baseline(geo_path, prov_path)
    if len(geography) != expected:
        raise ValueError(f"Holdout feature cell count {len(geography)} differs from preregistered {expected}")
    if document["grid_definition_id"] != metadata["grid_definition_id"] or document["grid_ids"] != geography.grid_id.tolist():
        raise ValueError("Holdout evaluation manifest identity differs from output rows")
    prereg = selection["holdout"]
    resolution = selection["resolution_comparison"]
    if dataset_id == "holdout25":
        expected_definition, expected_ids = prereg["grid_definition_id"], prereg["grid_ids"]
        expected_cells = {item["grid_id"]: item for item in prereg["cells"]}
    elif dataset_id == "common_fine16":
        expected_definition, expected_ids = resolution["fine_grid_definition_id"], resolution["fine_grid_ids"]
        all_cells = {item["grid_id"]: item for item in prereg["cells"]}
        expected_cells = {grid_id: all_cells[grid_id] for grid_id in expected_ids}
    elif dataset_id == "common_coarse20km4":
        expected_definition = resolution["coarse_grid_definition_id"]
        expected_cells = {item["grid_id"]: item for item in resolution["coarse_cells_planned"]}
        expected_ids = list(expected_cells)
    else:
        raise ValueError("Unknown holdout dataset identity")
    if metadata["grid_definition_id"] != expected_definition or geography.grid_id.tolist() != expected_ids:
        raise ValueError("Holdout grid definition/IDs differ from geometry preregistration")
    indexed = geography.set_index("grid_id")
    for grid_id, expected_cell in expected_cells.items():
        row = indexed.loc[grid_id]
        if int(row["row"]) != expected_cell["row"] or int(row["col"]) != expected_cell["col"]:
            raise ValueError("Holdout row/column differs from preregistration")
        if list(row.geometry.bounds) != expected_cell["bounds_5070"]:
            raise ValueError("Holdout cell bounds differ from preregistration")
        if "geometry_sha256" in expected_cell and _geometry_sha(row.geometry) != expected_cell["geometry_sha256"]:
            raise ValueError("Holdout cell geometry differs from preregistration")
        if "geometry_sha256" not in expected_cell and not row.geometry.equals(shapely.box(*expected_cell["bounds_5070"])):
            raise ValueError("Coarse holdout geometry is not the preregistered full square")
    return geography, provenance, metadata


def _geometry_union(geography):
    if geography.crs is None or geography.crs.to_epsg() != 5070:
        raise ValueError("Resolution comparison requires EPSG:5070")
    union = shapely.union_all(geography.geometry.values)
    if union.is_empty or not union.is_valid:
        raise ValueError("Resolution comparison has invalid union geometry")
    return union


def _resolution_summary(fine_geo, coarse_geo, fine_run, coarse_run, config):
    bounds = config.holdout.common_footprint_epsg5070
    target = shapely.box(*bounds)
    expected_m2 = config.holdout.expected_common_square_union_km2 * 1_000_000
    fine_union, coarse_union = _geometry_union(fine_geo), _geometry_union(coarse_geo)
    for label, union in (("fine", fine_union), ("coarse", coarse_union)):
        if not math.isclose(union.area, expected_m2, rel_tol=0, abs_tol=1e-5) or not union.equals(target):
            raise ValueError(f"{label} resolution cells do not cover the preregistered common footprint")
    if not fine_union.equals(coarse_union):
        raise ValueError("Fine and coarse full-square unions differ")
    fine_study = float(fine_geo.study_area_intersection_km2.sum())
    coarse_study = float(coarse_geo.study_area_intersection_km2.sum())
    if not math.isclose(fine_study, coarse_study, rel_tol=0, abs_tol=1e-6):
        raise ValueError("Fine/coarse Census study-intersection areas differ")
    selected_geometries = {}
    for label, geo, case in (("fine_10km", fine_geo, fine_run), ("coarse_20km", coarse_geo, coarse_run)):
        by_id = geo.set_index("grid_id")
        for design_id in sorted(case.result["ranked_cells"].design_id.unique()):
            selected = case.result["region_membership"].loc[
                case.result["region_membership"].design_id.eq(design_id), "grid_id"
            ]
            selected_geometries[(label, design_id)] = (
                shapely.GeometryCollection()
                if selected.empty
                else shapely.union_all(by_id.loc[selected, "geometry"].values)
            )
    selection_comparison = {}
    designs = sorted(set(fine_run.result["ranked_cells"].design_id) | set(coarse_run.result["ranked_cells"].design_id))
    for design_id in designs:
        fine_selected = selected_geometries.get(("fine_10km", design_id), shapely.GeometryCollection())
        coarse_selected = selected_geometries.get(("coarse_20km", design_id), shapely.GeometryCollection())
        selected_union = fine_selected.union(coarse_selected)
        selected_intersection = fine_selected.intersection(coarse_selected)
        union_area = selected_union.area / 1_000_000
        intersection_area = selected_intersection.area / 1_000_000
        selection_comparison[design_id] = {
            "fine_coarse_selected_intersection_km2": float(intersection_area),
            "fine_coarse_selected_union_km2": float(union_area),
            "fine_coarse_selected_jaccard": None if union_area == 0 else float(intersection_area / union_area),
        }
    rows = []
    for label, geo, case in (("fine_10km", fine_geo, fine_run), ("coarse_20km", coarse_geo, coarse_run)):
        ranked, members, regions = case.result["ranked_cells"], case.result["region_membership"], case.result["candidate_regions"]
        by_id = geo.set_index("grid_id")
        for design_id, group in ranked.groupby("design_id", sort=True):
            selected = members.loc[members.design_id.eq(design_id), "grid_id"]
            selected_area = float(selected_geometries[(label, design_id)].area / 1_000_000)
            rows.append({
                "resolution": label,
                "grid_definition_id": str(geo.grid_definition_id.iloc[0]),
                "design_id": design_id,
                "cells": len(group),
                "rankable_cells": int(group.rankable.sum()),
                "study_area_intersection_km2": float(geo.study_area_intersection_km2.sum()),
                "selected_members": len(selected),
                "selected_union_km2": selected_area,
                **selection_comparison[design_id],
                "connected_regions": int(regions.design_id.eq(design_id).sum()) if len(regions) else 0,
                "rankable_score_mean": None if not group.rankable.any() else float(group.loc[group.rankable, "mcda_score"].mean()),
                "comparison_basis": "Equal projected footprint; native features and all model stages recomputed independently; cell IDs are not matched across resolutions.",
            })
    return pd.DataFrame(rows)


def _evaluate_holdout(root, config, freeze_id, freeze_path, freeze, facility, designs, physical, requirements, baseline_profile, baseline_profile_hash):
    selection = json.loads(_path(root, config.preselection_manifest).read_text(encoding="utf-8"))
    hold_geo, hold_prov, hold_meta = _load_holdout_pair(root, config.holdout.holdout_geography, config.holdout.holdout_provenance, config.holdout.expected_holdout_cells, freeze_id, "holdout25", selection, freeze_path, freeze)
    fine_geo, fine_prov, _ = _load_holdout_pair(root, config.holdout.fine_geography, config.holdout.fine_provenance, config.holdout.expected_fine_cells, freeze_id, "common_fine16", selection, freeze_path, freeze)
    coarse_geo, coarse_prov, _ = _load_holdout_pair(root, config.holdout.coarse_geography, config.holdout.coarse_provenance, config.holdout.expected_coarse_cells, freeze_id, "common_coarse20km4", selection, freeze_path, freeze)
    baseline_geo, _, _ = _read_baseline(_path(root, config.inputs["geography"]), _path(root, config.inputs["provenance"]))
    hold_union, baseline_union = _geometry_union(hold_geo), _geometry_union(baseline_geo)
    if hold_union.intersects(baseline_union) or set(hold_geo.grid_id) & set(baseline_geo.grid_id):
        raise ValueError("Prospective holdout overlaps the inspected baseline")
    separation = hold_union.distance(baseline_union) / 1000
    if separation + 1e-9 < config.holdout.minimum_baseline_separation_km or not math.isclose(separation, selection["actual_separation_km"], rel_tol=0, abs_tol=1e-9):
        raise ValueError("Prospective holdout separation differs from preregistration")
    external = _scenario(physical.scenario_id, config.baseline.pathway, config.baseline.milestone_year)
    assumptions = {
        "basis": "prospective_geographic_holdout",
        "selection_policy": "Geometry and cached-source coverage only; selected and frozen before feature/ranking inspection.",
        "external_context": external.model_dump(mode="json"),
        "external_validation": "UNAVAILABLE",
    }
    hold = _run_case(hold_geo, hold_prov, facility, designs, physical, requirements, baseline_profile, external,
        mode=config.baseline.screening_mode, case_id="prospective_holdout25", category="baseline", assumptions=assumptions,
        profile_hash=baseline_profile_hash)
    fine = _run_case(fine_geo, fine_prov, facility, designs, physical, requirements, baseline_profile, external,
        mode=config.baseline.screening_mode, case_id="resolution_fine10km", category="baseline", assumptions=assumptions,
        profile_hash=baseline_profile_hash)
    coarse = _run_case(coarse_geo, coarse_prov, facility, designs, physical, requirements, baseline_profile, external,
        mode=config.baseline.screening_mode, case_id="resolution_coarse20km", category="baseline", assumptions=assumptions,
        profile_hash=baseline_profile_hash)
    resolution = _resolution_summary(fine_geo, coarse_geo, fine, coarse, config)
    quality = pd.concat([_data_quality(hold_prov, "prospective_holdout25"), _data_quality(fine_prov, "common_fine10km16"), _data_quality(coarse_prov, "common_coarse20km4")], ignore_index=True)
    return hold, resolution, quality, hold_meta


def run_phase6(config_path="configs/phase6.yaml", output_dir="runs/phase6/final", *, freeze_manifest=None, include_holdout=True):
    """Run the callable Phase 6 pipeline; use include_holdout=False before freeze."""
    if type(include_holdout) is not bool:
        raise ValueError("include_holdout must be an explicit boolean")
    root = _root()
    config_path = _path(root, config_path).resolve()
    config = load_phase6_config(config_path)
    output = _path(root, output_dir).resolve()
    protected = [
        root / "src", root / "configs", root / "data" / "processed",
        root / "runs" / "phase6" / "inputs", root / "runs" / "phase6" / "freeze",
    ] + [root / "runs" / f"phase{i}" for i in range(1, 6)]
    if output == root or any(output.is_relative_to(path) for path in protected):
        raise ValueError("Phase 6 output cannot overwrite source, configuration, processed data, or accepted Phase 1-5 runs")
    freeze_path = None if freeze_manifest is None else _path(root, freeze_manifest).resolve()
    freeze = _load_freeze(freeze_path, config, required=include_holdout)
    freeze_id = freeze["freeze_id"]
    before = _input_hashes(root, config, config_path, freeze_path, include_holdout=include_holdout)
    geography, provenance, metadata = _read_baseline(_path(root, config.inputs["geography"]), _path(root, config.inputs["provenance"]))
    facilities = load_facility_config(_path(root, config.inputs["facility"])).facilities
    if len(facilities) != 1:
        raise ValueError("Phase 6 requires exactly one configured facility")
    facility = FacilityConfig.model_validate(facilities[0].model_dump(mode="json"))
    designs = load_cooling_designs(_path(root, config.inputs["cooling_designs"]))
    physical = load_physical_scenarios(_path(root, config.inputs["physical_scenarios"]))
    if len(physical) != 1:
        raise ValueError("Phase 6 requires exactly one physical scenario")
    physical = physical[0]
    requirements, _ = load_requirements(_path(root, config.inputs["constraints"]))
    baseline_profile = load_profile(_path(root, config.inputs["baseline_profile"]))
    _load_profile_declaration(root, config, baseline_profile)
    baseline_external = _scenario(physical.scenario_id, config.baseline.pathway, config.baseline.milestone_year)
    baseline_profile_hash = sha256(_path(root, config.inputs["baseline_profile"]))
    cases = _case_runs(config, geography, provenance, facility, designs, physical, requirements, baseline_profile, baseline_external, baseline_profile_hash)
    baseline = cases[0]
    accepted = read_parquet(_path(root, config.inputs["baseline_ranked_cells"]))
    _assert_accepted_baseline(baseline.result["ranked_cells"], accepted)
    membership = read_parquet(_path(root, config.inputs["baseline_region_membership"]))
    comparisons, summaries, regions = [], [], []
    for case in cases:
        comparison = compare_ranked_cases(
            baseline.result["ranked_cells"], case.result["ranked_cells"],
            evaluation_version=config.evaluation_version, freeze_id=freeze_id, case_id=case.case_id,
            case_category=case.category, k=config.top_k.k, case_metadata=case.assumptions,
        )
        comparisons.append(comparison)
        summaries.append(summarize_case(
            comparison, case.result["ranked_cells"], evaluation_version=config.evaluation_version,
            freeze_id=freeze_id, case_id=case.case_id, case_category=case.category,
            k=config.top_k.k, weighting_method=case.result["weighting_method"],
        ))
        regions.append(summarize_fixed_regions(
            membership, case.result["ranked_cells"], evaluation_version=config.evaluation_version,
            freeze_id=freeze_id, case_id=case.case_id, baseline_scenario_id=baseline_external.scenario_id,
        ))
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="The behavior of DataFrame concatenation with empty or all-NA entries is deprecated", category=FutureWarning)
        sensitivity = pd.concat(comparisons, ignore_index=True).sort_values(["case_id", "grid_id", "design_id"]).reset_index(drop=True)
        fixed_regions = pd.concat(regions, ignore_index=True).sort_values(["case_id", "region_id", "design_id"]).reset_index(drop=True)
    robustness = pd.DataFrame(summaries).sort_values("case_id").reset_index(drop=True)
    rank_ranges = []
    for (grid_id, design_id), group in sensitivity.groupby(["grid_id", "design_id"], sort=True):
        base = group.loc[group.case_category.eq("baseline")]
        if len(base) != 1:
            raise ValueError("Each alternative requires one baseline rank row")
        ranks = pd.to_numeric(group.case_rank, errors="coerce")
        ranked = ranks.dropna().astype(int)
        base_rank = clean(base.base_rank.iloc[0])
        rank_ranges.append(AlternativeRankRangeRow(
            evaluation_version=config.evaluation_version,
            freeze_id=freeze_id,
            grid_id=grid_id,
            design_id=design_id,
            baseline_scenario_id=str(base.baseline_scenario_id.iloc[0]),
            base_rank=base_rank,
            evaluated_cases=len(group),
            ranked_cases=len(ranked),
            unranked_cases=int(ranks.isna().sum()),
            minimum_rank=None if ranked.empty else int(ranked.min()),
            maximum_rank=None if ranked.empty else int(ranked.max()),
            rank_range=None if ranked.empty else int(ranked.max() - ranked.min()),
            scope="Ranks summarized across separately evaluated preregistered cases by grid/design correspondence; external scenarios were never pooled.",
        ).model_dump(mode="json"))
    rank_ranges = pd.DataFrame(rank_ranges)
    ablation_rows = []
    baseline_weights = baseline.result["weights"]
    by_id = {case.case_id: case for case in cases}
    for spec in config.ablation_cases:
        case = by_id[spec.case_id]
        summary = robustness.loc[robustness.case_id.eq(spec.case_id)].iloc[0]
        ablation_rows.append({
            "case_id": spec.case_id,
            "removed_group": spec.removed_group,
            "renormalization_policy": config.ablation_policy.method,
            "original_global_weights_json": json_text(baseline_weights),
            "retained_global_weights_json": json_text(case.result["weights"]),
            "removed_metric_ids_json": json_text([m.metric_id for m in baseline_profile.metrics if m.group_id == spec.removed_group]),
            "rankable": int(summary.rankable),
            "eligibility_changes": int(summary.eligibility_changes),
            "top_k_overlap_count": int(summary.top_k_overlap_count),
            "top_k_jaccard": clean(summary.top_k_jaccard),
            "interpretation": "Diagnostic removal with global parent-weight renormalization; not evidence that the omitted group is unimportant.",
        })
    ablations = pd.DataFrame(ablation_rows).sort_values("case_id").reset_index(drop=True)
    holdout = resolution = quality = holdout_metadata = None
    if include_holdout:
        holdout, resolution, quality, holdout_metadata = _evaluate_holdout(
            root, config, freeze_id, freeze_path, freeze, facility, designs, physical, requirements, baseline_profile, baseline_profile_hash
        )
    output.mkdir(parents=True, exist_ok=True)
    mode = DataMode(metadata["data_mode"])
    write_parquet(sensitivity, output / "sensitivity_results.parquet", schema_name="SensitivityResult", schema_version="1.0.0", data_mode=mode, grid_definition_id=metadata["grid_definition_id"])
    robustness.to_csv(output / "robustness_summary.csv", index=False, lineterminator="\n")
    ablations.to_csv(output / "ablation_results.csv", index=False, lineterminator="\n")
    fixed_regions.to_csv(output / "fixed_region_summary.csv", index=False, lineterminator="\n")
    rank_ranges.to_csv(output / "alternative_rank_ranges.csv", index=False, lineterminator="\n")
    if holdout is not None:
        hmode = DataMode(holdout_metadata["data_mode"])
        write_parquet(holdout.result["ranked_cells"], output / "holdout_ranked_cells.parquet", schema_name="DecisionResult", schema_version="1.1.0", data_mode=hmode, grid_definition_id=holdout_metadata["grid_definition_id"])
        resolution.to_csv(output / "resolution_results.csv", index=False, lineterminator="\n")
        quality.to_csv(output / "holdout_data_quality.csv", index=False, lineterminator="\n")
    after = _input_hashes(root, config, config_path, freeze_path, include_holdout=include_holdout)
    if before != after:
        raise ValueError("A Phase 6 accepted input changed during validation")
    if freeze_path is not None:
        verify_freeze(freeze_path)
    software = None
    software_path = _path(root, config.software_evidence)
    if software_path.is_file():
        software = json.loads(software_path.read_text(encoding="utf-8"))
        if software.get("status") != "PASSED" or software.get("failed") != 0 or not isinstance(software.get("passed"), int) or software["passed"] < 1:
            raise ValueError("Software verification evidence does not record a passing test run")
        tested = software.get("tested_files")
        if not isinstance(tested, dict) or not tested:
            raise ValueError("Software verification evidence lacks tested source/config fingerprints")
        for relative, expected in tested.items():
            target = _path(root, relative)
            if not target.is_file() or sha256(target) != expected:
                raise ValueError("Software verification evidence belongs to a different source/config version")
    report = {
        "schema_version": "1.0.0",
        "phase": 6,
        "evaluation_version": config.evaluation_version,
        "freeze_id": freeze_id,
        "prospective_holdout_evaluated": include_holdout,
        "software_verification": software or {"status": "PENDING", "reason": "No frozen full-suite evidence file was supplied for this preflight run."},
        "data_quality": {
            "baseline_cells": len(geography),
            "baseline_provenance_rows": len(provenance),
            "holdout_cells": None if holdout is None else len(holdout.result["ranked_cells"]) // len(designs),
            "holdout_quality_rows": 0 if quality is None else len(quality),
            "interpretation": "Source lookup, schema, identity, coverage and join checks are data-quality verification, not independent physical validation.",
        },
        "external_validation": {
            "status": config.external_validation.status,
            "rationale": config.external_validation.rationale,
            "externally_validated_modules": [],
            "externally_unvalidated_modules": [
                "annual electricity and operational carbon", "on-site operational water",
                "parcel/power/water/fiber feasibility", "future water-stress scenario binding",
                "MCDA ranking and search-region recommendations",
            ],
            "overall_accuracy": None,
        },
        "sensitivity": {
            "cases": len(cases),
            "alternatives_per_case": len(baseline.result["ranked_cells"]),
            "all_alternatives_recomputed": True,
            "case_categories": robustness.groupby("case_category").size().sort_index().to_dict(),
            "eligibility_changes_total": int(robustness.eligibility_changes.sum()),
            "top_k_overlap_range": [int(robustness.top_k_overlap_count.min()), int(robustness.top_k_overlap_count.max())],
            "rank_correlation_range": [clean(robustness.rank_correlation.min()), clean(robustness.rank_correlation.max())],
            "fixed_region_policy": config.fixed_region_policy.model_dump(mode="json"),
            "top_k_policy": config.top_k.model_dump(mode="json"),
            "driver_scope": "Known retained-metric contribution changes only. Ablated metrics are declared omitted, not treated as missing evidence.",
            "alternative_rank_range_rows": len(rank_ranges),
        },
        "weighting_method_agreement": {
            "baseline_method": baseline.result["weighting_method"],
            "user_weight_cases": len(config.weight_cases),
            "ahp_evidence": "Software-only consistent ratio-matrix fixtures verify right-eigenvector equivalence. No expert or stakeholder judgments were supplied.",
        },
        "inactive_analyses": [item.model_dump(mode="json") for item in config.inactive_analyses],
        "holdout": None if holdout is None else {
            "selection": "25 cells selected by geometry/cached-source coverage before feature or ranking inspection",
            "externally_validated": False,
            "alternatives": len(holdout.result["ranked_cells"]),
            "rankable": int(holdout.result["ranked_cells"].rankable.sum()),
            "conditional_ranked": int((holdout.result["ranked_cells"].rankable & holdout.result["ranked_cells"].conditional).sum()),
            "hard_failures": int(holdout.result["ranked_cells"].hard_fail.sum()),
        },
        "resolution": None if resolution is None else {
            "equal_projected_footprint_verified": True,
            "expected_union_km2": config.holdout.expected_common_square_union_km2,
            "comparison_rows": len(resolution),
            "interpretation": "Native source aggregation and all model stages rerun at each resolution; different cell IDs are not paired.",
        },
        "remaining_blockers": [
            "No independent system-boundary-compatible facility observations or engineering benchmarks are available.",
            "Critical parcel, contiguous land, utility capacity, water-supply and fiber evidence remain unresolved where marked UNKNOWN.",
            "Climate-to-cooling and construction-lifecycle sensitivities are inactive because required response functions/inventories/factors are unavailable.",
            "National-scale runtime and memory remain unvalidated.",
        ],
        "input_hashes": before,
    }
    (output / "validation_report.json").write_text(json_text(report) + "\n", encoding="utf-8")
    from dc_locator.model.validation.reporting import report_markdown
    (output / "validation_report.md").write_text(report_markdown(report, robustness, fixed_regions), encoding="utf-8")
    substantive = [path for path in sorted(output.iterdir()) if path.is_file() and path.name != "run_metadata.json"]
    manifest = {
        "schema_version": "1.0.0",
        "phase": 6,
        "status": "awaiting_orchestrator_acceptance",
        "evaluation_version": config.evaluation_version,
        "freeze_id": freeze_id,
        "input_hashes": before,
        "output_hashes": {path.name: sha256(path) for path in substantive},
        "cases": len(cases),
        "sensitivity_rows": len(sensitivity),
        "robustness_rows": len(robustness),
        "fixed_region_rows": len(fixed_regions),
        "holdout_evaluated": include_holdout,
    }
    (output / "run_metadata.json").write_text(json_text(manifest) + "\n", encoding="utf-8")
    return {"report": report, "manifest": manifest, "cases": cases, "holdout": holdout}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/phase6.yaml")
    parser.add_argument("--output-dir", default="runs/phase6/final")
    parser.add_argument("--freeze-manifest")
    parser.add_argument("--preflight", action="store_true", help="Run accepted42 sensitivity only; do not read prospective holdout features.")
    args = parser.parse_args(argv)
    result = run_phase6(args.config, args.output_dir, freeze_manifest=args.freeze_manifest, include_holdout=not args.preflight)
    print(json_text({key: result["manifest"][key] for key in ("evaluation_version", "freeze_id", "cases", "sensitivity_rows", "holdout_evaluated")}))


if __name__ == "__main__":
    main()
