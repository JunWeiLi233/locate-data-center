"""End-to-end rediscovery analysis: blind candidate generation, then post-hoc reveal of existing facilities.

Order of operations is part of the method:

1. Verify the completed model run. Score its national fine surface and select separated candidates. No
   facility data is opened.
2. Write ``candidates_blind.parquet`` and record its SHA-256 and timestamp.
3. Only then open the external facility inventory, measure distances, hit rates and recall, and run the
   random baselines.
4. Attach classification, robustness and explanations, then write every artifact with a checksum ledger.

An existing output folder with the same identity and intact outputs is reused. A different identity is
refused, so stale results are never relabelled.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from dc_locator.geography.sources.ingestion import file_digest
from dc_locator.io import write_parquet
from dc_locator.provenance import DataMode

from . import SCHEMA_VERSION, __version__
from .baselines import run_controls
from .config import RediscoveryConfig, load_config
from .explain import NOT_SCORED, USER_FACTOR_MAP, explain
from .facilities import acquire, download_record, load_inventory
from .geodesy import DISTANCE_METHOD, EARTH_RADIUS_KM, SphericalIndex
from .places import label_points, load_counties
from .robustness import build_providers, combine
from .surface import cell_centers, candidate_table, load_model_run, score_national_surface, select_candidates
from .surface_image import render
from .ties import tie_block_structure, tie_shuffled_hit_rates
from .validation import (classify, distance_check, facility_cells, facility_hubs, facility_recall, hit_rates, hub_recall,
                         nearest_facilities, presence_background)

MANIFEST = "rediscovery_manifest.json"
INTERPRETATION = ("These geographic regions deserve further investigation under the stated facility requirements, datasets, "
                  "constraints, assumptions, and decision preferences. They are NOT proven buildable parcels and NOT "
                  "America's objectively best places to build a data center.")
VALIDATION_FRAMING = ("The comparison with existing facilities provides an external sanity check on the geographic suitability "
                      "model. Existing data centers are not ground truth: they reflect historical, market, latency, tax, "
                      "regulatory and company-specific reasons the model does not capture, and the inventory is incomplete. "
                      "A candidate without nearby facilities is not shown to be suitable; a candidate near them is not shown to be correct.")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_default(value):
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    raise TypeError(f"Unserializable {type(value).__name__}")


def _clean(value):
    if isinstance(value, dict):
        return {str(key): _clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(item) for item in value]
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if isinstance(value, np.floating):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if value is pd.NA:
        return None
    return value


def write_json(path: Path, value) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(_clean(value), indent=2, sort_keys=True, allow_nan=False, default=_json_default) + "\n", encoding="utf-8")
    temporary.replace(path)


def _code_hashes() -> dict[str, str]:
    package = Path(__file__).resolve().parent
    return {path.name: file_digest(path) for path in sorted(package.glob("*.py"))}


def _environment() -> dict:
    names = ("numpy", "pandas", "geopandas", "shapely", "pyproj", "pyarrow", "pydantic", "scipy", "pyogrio")
    return {"python": platform.python_version(), "platform": platform.platform(),
            "packages": {name: importlib.metadata.version(name) for name in names}}


def _identity(config: RediscoveryConfig, config_path: Path, model_identity: dict) -> str:
    document = {"config": config.model_dump(mode="json"), "config_sha256": file_digest(config_path), "model": model_identity,
                "code": _code_hashes(), "environment": _environment(), "schema_version": SCHEMA_VERSION}
    return hashlib.sha256(json.dumps(document, sort_keys=True).encode()).hexdigest()


def _resolve_output(root: Path, output: str) -> Path:
    folder = (root / output).resolve()
    allowed = [(root / "runs").resolve(), (root / ".pytest-work").resolve()]
    if not any(folder.is_relative_to(base) and folder != base for base in allowed):
        raise ValueError("Rediscovery outputs belong in runs/<name>/ (or .pytest-work/ for tests)")
    protected = ("phase", "orchestrator_", "example")
    if folder.parent == allowed[0] and folder.name.startswith(protected):
        raise ValueError("Accepted evidence folders are never written by this analysis")
    return folder


def _verified_reuse(folder: Path, identity: str) -> dict | None:
    manifest_path = folder / MANIFEST
    if not manifest_path.is_file():
        if folder.exists() and any(folder.iterdir()):
            raise ValueError("Nonempty output folder without a rediscovery manifest; choose a new output folder")
        return None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("analysis_identity") != identity:
        raise ValueError("Output folder belongs to another rediscovery identity (code, configuration, model run or "
                         "environment changed); choose a new output folder instead of relabelling stale results")
    for name, digest in manifest.get("output_hashes", {}).items():
        if not (folder / name).is_file() or file_digest(folder / name) != digest:
            raise ValueError(f"Rediscovery output checksum mismatch: {name}")
    return manifest


def _round_rows(rows: list[dict]) -> list[dict]:
    return [{key: (round(value, 6) if isinstance(value, float) else value) for key, value in row.items()} for row in rows]


def run(config_path: str | Path, output: str, *, root: Path, acquire_facilities: bool = False, progress=print) -> dict:
    """Execute (or verify and reuse) one rediscovery analysis; returns its manifest."""
    started = time.perf_counter()
    progress = progress or (lambda message: None)
    root = root.resolve()
    config_path = Path(config_path) if Path(config_path).is_absolute() else root / config_path
    config = load_config(config_path)
    data_mode = DataMode(config.data_mode)
    folder = _resolve_output(root, output)
    generation = config.candidate_generation
    model = load_model_run(root, generation.model_run)
    if model.identity["data_mode"] != config.data_mode:
        raise ValueError("Configuration data_mode differs from the model run; real runs never mix with synthetic fixtures")
    identity = _identity(config, config_path, model.identity)
    reused = _verified_reuse(folder, identity)
    if reused is not None:
        progress(f"Verified existing rediscovery outputs in {folder}; nothing recomputed")
        return reused
    folder.mkdir(parents=True, exist_ok=True)
    timeline = {"started_at_utc": _now()}

    # ---- 1. Blind candidate generation: no facility data is opened in this block. ----
    progress(f"Scoring the national fine surface of {model.relative}")
    national = score_national_surface(model, controls=config.baselines.controls,
                                      evaluated_path=folder / "evaluated_cells.parquet" if generation.write_evaluated_cells else None,
                                      data_mode=data_mode, progress=progress)
    largest = generation.top_n_values[-1]
    positions = select_candidates(national.score, national, model.grid, largest, generation.min_candidate_distance_km)
    if len(positions) < largest:
        raise ValueError(f"Only {len(positions)} separated candidates exist; reduce top_n_values or the separation")
    candidates, factors = candidate_table(model, national, positions)
    higher, tied = tie_block_structure(national.score, positions)
    candidates["cells_with_higher_score"] = higher
    candidates["score_rank_min"] = higher + 1
    candidates["score_rank_max"] = higher + tied
    counties, county_record = load_counties(root, config.places.county_boundaries, config.places.county_boundaries_manifest)
    candidates = pd.concat([candidates, label_points(candidates, counties, config.places.nearest_county_max_km)], axis=1)
    case_positions = {case: select_candidates(scores, national, model.grid, largest, generation.min_candidate_distance_km)
                      for case, scores in national.case_scores.items()} if config.robustness.declared_weight_cases == "from_model_run" else {}
    blind = candidates.assign(analysis_name=config.analysis_name, generated_without_facility_data=True)
    write_parquet(blind, folder / "candidates_blind.parquet", schema_name="RediscoveryCandidateBlind", schema_version=SCHEMA_VERSION,
                  data_mode=data_mode, grid_definition_id=model.identity["grid_definition_id"])
    timeline["candidates_blind_written_at_utc"] = _now()
    blind_sha = file_digest(folder / "candidates_blind.parquet")
    progress(f"Blind candidates written ({len(candidates)}; sha256 {blind_sha[:12]}…) before any facility data was read")

    # ---- 2. Reveal: external facility inventory (validation only). ----
    source = config.facilities
    if acquire_facilities:
        acquire(source, root)
    record = download_record(source, root)
    facilities, inventory = load_inventory(source, root, record, config.data_mode)
    timeline["facilities_loaded_at_utc"] = _now()
    radii = config.validation.hit_radii_km
    nearest = nearest_facilities(candidates, facilities, radii)
    if (nearest.grid_id.to_numpy() != candidates.grid_id.to_numpy()).any():
        raise ValueError("Nearest-facility rows lost candidate order")
    distances = nearest.distance_to_nearest_existing_dc_km.to_numpy()
    rates = hit_rates(distances, radii, generation.top_n_values)
    recall = facility_recall(facilities, candidates, radii, generation.top_n_values)
    hubs, membership = facility_hubs(facilities, config.validation.hubs.linkage_km, config.validation.hubs.min_facilities)
    facilities = facilities.assign(hub_id=[value if isinstance(value, str) else None for value in membership])
    hub_rows, hub_detail = hub_recall(hubs, facilities, membership, candidates, radii, generation.top_n_values)
    rows, cols = facility_cells(facilities, model.grid)
    cell_positions = national.lookup(rows, cols)
    facilities = facilities.assign(model_cell_row=rows, model_cell_col=cols,
                                   model_cell_score=np.where(cell_positions >= 0, national.score[np.maximum(cell_positions, 0)], np.nan))
    presence = {"baseline": presence_background(national.score, cell_positions)}
    for case, scores in national.case_scores.items():
        presence[case] = presence_background(scores, cell_positions)
    thresholds = config.validation.classification
    tie_check = None
    if config.tie_sensitivity.permutations:
        progress(f"Repeating selection over {config.tie_sensitivity.permutations} random tie orders")
        tie_check = tie_shuffled_hit_rates(
            national.score, national, model.grid, largest, generation.min_candidate_distance_km, facilities, radii,
            generation.top_n_values, lambda d: classify(d, thresholds.validated_max_km, thresholds.emerging_min_km),
            config.tie_sensitivity.permutations, config.tie_sensitivity.seed)

    # ---- 3. Random baselines with the same separation rule. ----
    progress(f"Drawing {config.baselines.draws} random control sets per baseline")

    def coordinates(indices):
        return cell_centers(model.grid, national.row[indices], national.col[indices])

    draws, comparison = run_controls(config.baselines.controls, masks=national.control_masks, weights=national.area_km2,
                                     coordinates=coordinates, facilities=facilities, model_rates=rates,
                                     top_n_values=generation.top_n_values, radii_km=radii,
                                     min_distance_km=generation.min_candidate_distance_km, draws=config.baselines.draws,
                                     seed=config.baselines.seed, area_weighted=config.baselines.area_weighted)

    # ---- 4. Classification, robustness, weight-case retention and explanations. ----
    candidates = candidates.join(nearest.drop(columns="grid_id"))
    candidates["classification"] = classify(distances, thresholds.validated_max_km, thresholds.emerging_min_km)
    candidates["top_n_bucket"] = [next(n for n in generation.top_n_values if rank <= n) for rank in candidates["rank"]]
    retention = []
    for candidate in candidates.itertuples(index=False):
        kept = []
        for case, pos in case_positions.items():
            limit = candidate.top_n_bucket
            lat, lon = cell_centers(model.grid, national.row[pos[:limit]], national.col[pos[:limit]])
            nearest_case, _ = SphericalIndex(lat, lon).nearest([candidate.lat], [candidate.lon])
            if float(nearest_case[0]) < generation.min_candidate_distance_km:
                kept.append(case)
        retention.append(kept)
    candidates["weight_cases_retained"] = [len(kept) for kept in retention]
    candidates["weight_cases_total"] = len(case_positions)
    candidates["weight_cases_retained_ids"] = retention
    providers = build_providers(config.robustness.providers, root)
    robustness = combine(providers, candidates)
    candidates = pd.concat([candidates.reset_index(drop=True), robustness], axis=1)
    candidates["robustness_details_json"] = candidates.robustness_details.map(lambda value: None if value is None else json.dumps(_clean(value), sort_keys=True))
    candidates = candidates.drop(columns="robustness_details")
    explanations = []
    factors = factors.merge(candidates[["grid_id", "place_label"]], on="grid_id", how="left")
    for candidate in candidates.itertuples(index=False):
        own = factors[factors.grid_id.eq(candidate.grid_id)]
        explanations.append(explain(own, strong_min=config.explanation.strong_normalized_min, weak_max=config.explanation.weak_normalized_max,
                                    design_id=candidate.design_id, place=candidate.place_label))
    candidates["explanation"] = [item["explanation"] for item in explanations]
    candidates["strengths"] = [item["strengths"] for item in explanations]
    candidates["weaknesses"] = [item["weaknesses"] for item in explanations]
    candidates["data_mode"] = config.data_mode
    factors = factors.drop(columns="place_label")
    check = distance_check(candidates, candidates)
    if check > 1e-6:
        raise ValueError("Reported nearest-facility distances disagree with direct haversine recomputation")

    # ---- 5. Presentation image and artifacts. ----
    outputs = {}
    if config.surface_image.enabled:
        image, legend = render(national, model.grid, config.surface_image.width_px)
        (folder / "suitability_surface.png").write_bytes(image)
        write_json(folder / "suitability_surface.json", legend)
    grid_definition = model.identity["grid_definition_id"]
    write_parquet(candidates, folder / "candidates.parquet", schema_name="RediscoveryCandidate", schema_version=SCHEMA_VERSION,
                  data_mode=data_mode, grid_definition_id=grid_definition)
    candidates.drop(columns=["strengths", "weaknesses", "weight_cases_retained_ids"]).to_csv(folder / "candidates.csv", index=False)
    write_parquet(factors, folder / "candidate_factors.parquet", schema_name="RediscoveryCandidateFactor", schema_version=SCHEMA_VERSION,
                  data_mode=data_mode, grid_definition_id=grid_definition)
    write_parquet(facilities, folder / "existing_facilities.parquet", schema_name="RediscoveryFacility", schema_version=SCHEMA_VERSION,
                  data_mode=data_mode)
    write_parquet(hub_detail, folder / "facility_hubs.parquet", schema_name="RediscoveryHub", schema_version=SCHEMA_VERSION,
                  data_mode=data_mode)
    write_parquet(draws, folder / "baseline_draws.parquet", schema_name="RediscoveryBaselineDraw", schema_version=SCHEMA_VERSION,
                  data_mode=data_mode)
    classes = candidates.classification
    summary = {
        "schema_version": SCHEMA_VERSION, "analysis_name": config.analysis_name, "data_mode": config.data_mode,
        "interpretation": INTERPRETATION, "validation_framing": VALIDATION_FRAMING,
        "research_question": "Can infrastructure and geographic data independently rediscover existing U.S. data-center hubs, while also identifying potentially overlooked locations for future development?",
        "model_run": model.identity, "candidates_blind_sha256": blind_sha,
        "candidate_generation": {
            "source": "national_fine_surface", "cells_valued": int(np.isfinite(national.score).sum()), "cells_total": int(len(national.score)),
            "unscored_reasons": national.unscored_reasons, "verification": national.verification,
            "designs": national.designs, "design_selection": generation.design_selection,
            "ranking": "score descending; ties by grid_id (equivalently row, col for fixed-width IDs)",
            "min_candidate_distance_km": generation.min_candidate_distance_km, "distance_method": DISTANCE_METHOD,
            "earth_radius_km": EARTH_RADIUS_KM, "separation_rule": "greedy non-maximum suppression in rank order; kept candidates are pairwise at least the minimum distance apart",
            "top_n_values": generation.top_n_values, "candidates": int(len(candidates)),
            "max_score": float(np.nanmax(national.score)), "cells_tied_at_max_score": int(np.sum(national.score == np.nanmax(national.score))),
            "screening_status": "UNSCREENED national valuation; critical parcel/utility/water/fiber/hazard requirements remain unknown",
            "weights": model.weights, "profile_id": model.profile.profile_id, "scenario_id": model.identity["scenario_id"],
            "runtime_seconds": national.runtime_seconds,
        },
        "facilities": inventory,
        "validation": {
            "hit_radii_km": radii, "hit_rates": _round_rows(rates), "facility_recall": _round_rows(recall),
            "hubs": {"linkage_km": config.validation.hubs.linkage_km, "min_facilities": config.validation.hubs.min_facilities,
                     "count": int(len(hubs)), "facilities_in_hubs": int(membership.notna().sum()), "recall": _round_rows(hub_rows),
                     "declared": config.validation.hubs.declared.model_dump()},
            "presence_background": presence,
            "classification": {"validated_max_km": thresholds.validated_max_km, "emerging_min_km": thresholds.emerging_min_km,
                               "declared": thresholds.declared.model_dump(),
                               "counts_by_top_n": {str(n): {label: int((classes.iloc[:n] == label).sum()) for label in ("validated", "unresolved", "emerging")}
                                                   for n in generation.top_n_values}},
            "nearest_distance_km_quantiles_by_top_n": {str(n): {q: float(np.quantile(distances[:n], float(q))) for q in ("0.1", "0.25", "0.5", "0.75", "0.9")}
                                                       for n in generation.top_n_values},
            "distance_recomputation_max_abs_km": check,
            "tie_sensitivity": tie_check,
            "tie_blocks": {"candidates_in_top_score_block": int((candidates.score_rank_min == 1).sum()),
                           "top_score_block_cells": int(candidates.loc[candidates.score_rank_min == 1, "tied_cells_at_score"].max())
                           if (candidates.score_rank_min == 1).any() else 0,
                           "rule": "Published ranks order tied scores by grid_id (the model's convention); tie_sensitivity shows the spread over random tie orders"},
        },
        "baselines": {"draws": config.baselines.draws, "seed": config.baselines.seed, "area_weighted": config.baselines.area_weighted,
                      "controls": [control.model_dump() for control in config.baselines.controls],
                      "comparison": _round_rows(comparison),
                      "p_value": "one-sided empirical (1 + draws with hit rate >= model) / (1 + draws)"},
        "robustness": {"providers": [provider.describe() for provider in providers],
                       "candidates_with_score": int(candidates.robustness_score.notna().sum()),
                       "weight_cases": [{"case_id": case["case_id"], "group_weights": case["group_weights"], "basis": case.get("basis"),
                                         "rationale": case.get("rationale")} for case in model.weight_cases],
                       "weight_case_retention_rule": "A candidate is retained in a declared weighting case when that case's own separated Top-N (N = the candidate's Top-N bucket) has a candidate closer than the minimum separation distance."},
        "factors": {"model_criteria": [{"metric_id": metric.metric_id, "group_id": metric.group_id, "weight": model.weights[metric.metric_id],
                                        "direction": metric.direction, "reference_low": metric.reference_low, "reference_high": metric.reference_high,
                                        "unit": metric.unit, "role": metric.role, "definition": metric.definition}
                                       for metric in model.profile.metrics],
                    "user_factor_map": USER_FACTOR_MAP, "not_scored": NOT_SCORED},
        "places": county_record,
        "explanation_rule": {"strong_normalized_min": config.explanation.strong_normalized_min,
                             "weak_normalized_max": config.explanation.weak_normalized_max,
                             "declared": config.explanation.declared.model_dump()},
        "limitations": [
            "Candidates come from an UNSCREENED national 1 km valuation; parcel, utility capacity, committed water, diverse fiber, zoning and hazard clearance are not verified.",
            "The score uses regional proxies (eGRID subregion carbon, Aqueduct basin stress), so many cells tie; ties are ordered by grid_id, a deterministic but arbitrary rule.",
            "Existing-facility locations are an incomplete, crowd-sourced (OpenStreetMap-derived) reference and are not ground truth for suitability.",
            "Hit rates depend on N, the separation rule and the radii; they are agreement statistics, not accuracy.",
            "Baselines control for spatial chance but not for every confounder (population, fiber, tax incentives).",
            "Robustness from the county Monte Carlo is county-level, covers only its selected counties and uses different objectives.",
        ],
    }
    write_json(folder / "validation_summary.json", summary)
    from .report import write_report

    write_report(folder / "report.md", summary, candidates)
    for name in ("candidates_blind.parquet", "candidates.parquet", "candidates.csv", "candidate_factors.parquet", "existing_facilities.parquet",
                 "facility_hubs.parquet", "baseline_draws.parquet", "validation_summary.json", "report.md",
                 "suitability_surface.png", "suitability_surface.json", "evaluated_cells.parquet"):
        if (folder / name).is_file():
            outputs[name] = file_digest(folder / name)
    timeline["finished_at_utc"] = _now()
    manifest = {
        "schema_version": SCHEMA_VERSION, "package_version": __version__, "analysis_name": config.analysis_name,
        "analysis_identity": identity, "data_mode": config.data_mode,
        "config_path": config_path.relative_to(root).as_posix() if config_path.is_relative_to(root) else str(config_path),
        "config_sha256": file_digest(config_path), "config": config.model_dump(mode="json"),
        "model_run": model.identity, "facility_inventory": record, "county_boundaries": county_record,
        "code_sha256": _code_hashes(), "environment": _environment(), "timeline": timeline,
        "runtime_seconds": round(time.perf_counter() - started, 1),
        "leakage_controls": ["Candidate generation reads only the model run (fine surface, profile, configuration) and Census county labels.",
                             "candidates_blind.parquet was hashed before the facility inventory was opened (see timeline).",
                             "dc_locator never imports dc_rediscovery; tests/test_rediscovery_leakage.py enforces this."],
        "candidates_blind_sha256": blind_sha, "output_hashes": outputs, "interpretation": INTERPRETATION,
    }
    write_json(folder / MANIFEST, manifest)
    progress(f"Rediscovery analysis complete in {manifest['runtime_seconds']} s: {folder}")
    return manifest
