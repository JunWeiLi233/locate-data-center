"""Bounded job registry and configuration adapter for the deterministic model."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import queue
import shutil
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .serialization import FINE_SELECTIONS, ApiError, ArtifactReader, EXPORTS, GROUPS, SCHEMA_VERSION, SCOPE, available_scenarios, describe_scope, clean, fine_surface_metadata, json_bytes, read_json, regional_catalog, regional_scope, snapshot_configuration
from . import socioeconomic
from .artifacts import ModelArtifactReader, cached_cohort_status, fast_request_identity, is_fast_run, run_cached_evaluation, verify_fast_artifacts

STAGES = ("ingest", "build-features", "screen", "simulate", "rank", "cluster", "validate")
COOLING = ("all", "air_dry_assumed", "cold_plate_tower_assumed")
FIELDS = {"peak_it_power_mw", "average_load_percent", "target_opening_year", "lifetime_years", "cooling", "weighting", "screening_mode", "group_weights", "ahp_matrix"}
DEFAULT_BOUNDS = {"peak_it_power_mw": {"min_exclusive": 0, "max": 1000}, "average_load_percent": {"min_exclusive": 0, "max": 100},
                  "target_opening_year": {"min": 2026, "max": 2100}, "lifetime_years": {"min": 1, "max": 100}}
REGIONAL_BASELINES = ("runs/regional_refinement_v3", "runs/regional_refinement_v4", "runs/cleanview_regional_v2", "runs/national_fine_regional_v1",
                      "runs/national_fine_region_v1", "runs/national_fine_region_v2")
REGIONAL_WRAPPERS = {"representative_parent_cells": "configs/run_regional_exploratory.yaml",
                     "national_fine_surface": "configs/run_regional_fine_surface.yaml",
                     "national_fine_region_parents": "configs/run_regional_fine_region.yaml"}


def validate_facility(body):
    if not isinstance(body, dict) or set(body) != {"facility"} or not isinstance(body["facility"], dict):
        raise ApiError("Request must contain exactly one facility object")
    facility = body["facility"]
    if set(facility) - FIELDS:
        raise ApiError("Unknown facility fields: " + ", ".join(sorted(set(facility) - FIELDS)))
    required = FIELDS - {"group_weights", "ahp_matrix"}
    if required - set(facility):
        raise ApiError("Missing facility fields: " + ", ".join(sorted(required - set(facility))))
    for name, high in (("peak_it_power_mw", 1000), ("average_load_percent", 100)):
        value = facility[name]
        if type(value) not in (float, int) or not math.isfinite(value) or not 0 < value <= high:
            raise ApiError(f"{name} must be a finite number greater than 0 and at most {high}")
    for name, low, high in (("target_opening_year", 2026, 2100), ("lifetime_years", 1, 100)):
        if type(facility[name]) is not int or not low <= facility[name] <= high:
            raise ApiError(f"{name} must be an integer from {low} to {high}")
    if facility["cooling"] not in COOLING or type(facility["cooling"]) is not str:
        raise ApiError("cooling must name an accepted design or all")
    if facility["screening_mode"] not in ("STRICT", "EXPLORATORY"):
        raise ApiError("screening_mode must be STRICT or EXPLORATORY")
    weighting = facility["weighting"]
    if weighting not in ("equal", "user", "ahp"):
        raise ApiError("weighting must be equal, user or ahp")
    weights = facility.get("group_weights")
    if weights is not None:
        if not isinstance(weights, dict) or set(weights) != set(GROUPS):
            raise ApiError("group_weights must contain all four accepted group IDs")
        if any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in weights.values()):
            raise ApiError("group_weights must be finite nonnegative numbers")
        if sum(weights.values()) <= 0 or not math.isfinite(sum(weights.values())):
            raise ApiError("group_weights require a finite positive total")
    if weighting == "user" and weights is None:
        raise ApiError("user weighting requires all four group preferences")
    matrix = facility.get("ahp_matrix")
    if weighting == "ahp":
        if not isinstance(matrix, list) or len(matrix) != len(GROUPS) or any(not isinstance(row, list) or len(row) != len(GROUPS) for row in matrix):
            raise ApiError("ahp_matrix must be a complete 4 by 4 matrix in the advertised group order")
        if any(type(v) not in (int, float) or not math.isfinite(v) or not 1 / 9 <= v <= 9 for row in matrix for v in row):
            raise ApiError("AHP judgments must be numeric, finite and between 1/9 and 9")
        # The accepted backend validates reciprocity and consistency; no frontend-derived weights.
        from dc_locator.model.ahp import evaluate_ahp
        try:
            review = evaluate_ahp(GROUPS, matrix, active_criteria_ids=GROUPS)
        except ValueError as exc:
            raise ApiError(str(exc)) from exc
        if review["status"] == "REVIEW_REQUIRED":
            raise ApiError(f"Your pairwise priorities are internally inconsistent. Review comparisons. CR={review['CR']:.6f}; accepted threshold={review['consistency_threshold']:.2f}. No automatic override is allowed.", 422, "ahp_review_required")
    elif matrix is not None:
        raise ApiError("ahp_matrix is only accepted for AHP weighting")
    result = copy.deepcopy(facility)
    result["group_weights"] = weights or dict.fromkeys(GROUPS, 0.25)
    result["ahp_matrix"] = matrix
    return result


def _atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(json_bytes(value))
    temporary.replace(path)


def _write_frozen(path: Path, content: bytes):
    """A scientific configuration identity is immutable once created."""
    if path.is_file():
        if path.read_bytes() != content:
            raise ValueError("Existing service configuration bytes differ from their immutable identity: " + str(path))
        return
    path.write_bytes(content)


def reuse_bound_geography(pipeline, candidates):
    """Reuse verified facility-independent artifacts through accepted stage binding.

    All native source checksums, working model hashes, environment, grid, geographic
    config references and future acquisition domains must match. Model stages still
    execute for the submitted facility. No scientific output or prior manifest is edited.
    """
    from dc_locator.geography.sources.ingestion import file_digest
    if pipeline.cached("build-features"):
        return True
    expected = pipeline.config.model_dump(mode="json")
    def normalize(values):
        return {str(k).replace("\\", "/"): v for k, v in values.items()}
    fields = ("data_mode", "grid_config", "grid_path", "grid_definition_id", "study_area", "source_registry", "local_sources",
              "core_source_inputs", "expanded_source_inputs", "aqueduct_source_input", "expanded_features")
    config_fields = ("grid_config", "source_registry", "local_sources", "core_source_inputs", "expanded_source_inputs", "aqueduct_source_input")
    for folder in candidates:
        meta = read_json(folder / "run_metadata.json", {})
        old = meta.get("configuration", {})
        if any(old.get(f) != expected.get(f) for f in fields):
            continue
        if any(old.get("future", {}).get(f) != expected.get("future", {}).get(f) for f in ("enabled", "pathways", "milestone_years")):
            continue
        if normalize(meta.get("actual_working_code_sha256", {})) != normalize(pipeline.model_hashes) or meta.get("environment") != pipeline.environment:
            continue
        if any(meta.get("source_checksums", {}).get(k) != v for k, v in pipeline.source_hashes.items()):
            continue
        if meta.get("configured_grid", {}).get("sha256") != file_digest(pipeline.path(expected["grid_path"])):
            continue
        if any(meta.get("config_hashes", {}).get(str(pipeline.path(expected[f]))) != pipeline.config_hashes.get(str(pipeline.path(expected[f]))) for f in config_fields if expected.get(f)):
            continue
        manifest = read_json(folder / "stage_manifests/build-features.json", {})
        hashes = manifest.get("output_hashes", {})
        required = {"us_grid_dataset.parquet", "feature_provenance.parquet", "source_coverage.json", "source_data_manifest.json"}
        if set(hashes) != required or any(not (folder / n).is_file() or file_digest(folder / n) != hashes[n] for n in required):
            continue
        pipeline.require("ingest")
        for name in sorted(required):
            shutil.copy2(folder / name, pipeline.output / name)
        pipeline.finish("build-features", sorted(required), {"cache_operation": "reuse checksum-verified facility-independent geography",
                        "reused_from_run_id": meta["run_id"], "geographic_input_identity_verified": True, **manifest.get("details", {})})
        return True
    return False


class LocatorService:
    def __init__(self, root: Path, *, start_worker=True):
        self.root = root.resolve()
        self.owned = self.root / "runs/frontend_service"
        self.registry_path = self.owned / "registry.json"
        self.lock = threading.RLock()
        self.reader_lock = threading.RLock()
        self.reader = ModelArtifactReader(self.owned / "response_cache", self.root)
        self.runs: dict[str, Path] = {}
        self.jobs: dict[str, dict] = {}
        self.queue = queue.Queue(maxsize=8)
        self.fast_queue = queue.Queue(maxsize=4)
        for relative in ("runs/example", "runs/phase7/root_v2_exploratory", "runs/national_discovery_v2", *REGIONAL_BASELINES):
            self.register_run(self.root / relative, save=False)
        # Completion discovery is limited to deliveries absent at startup. A
        # deliberately removed completed run must never become a new search.
        registered_paths = set(self.runs.values())
        self._pending_regional_baselines = {self.root / relative for relative in REGIONAL_BASELINES
                                            if self.root / relative not in registered_paths}
        durable = read_json(self.registry_path, {})
        for relative in durable.get("runs", {}).values():
            path = (self.root / relative).resolve()
            if path.is_relative_to(self.owned):
                self.register_run(path, save=False)
        national = self.root / "runs/national_discovery_v2"
        national_id = read_json(national / "run_metadata.json", {}).get("run_id")
        latest = self.latest_run_id()
        latest_meta = read_json(self.runs[latest] / "run_metadata.json", {}) if latest else {}
        latest_extent = latest_meta.get("configuration", {}).get("study_area") or latest_meta.get("scope", {}).get("scope")
        if national_id in self.runs and latest_extent not in {"conus", "regional_refinement", "cached_regional_cohort"}:
            self.register_run(national, save=False)
        regional = self._regional_baseline()
        if regional:
            latest_catalog = regional_catalog(self.runs[latest]) if latest else None
            preferred_catalog = regional_catalog(regional)
            if not is_fast_run(latest_meta) and (not latest_catalog or (preferred_catalog and preferred_catalog.get("selection") in FINE_SELECTIONS
                                       and latest_catalog.get("selection") not in FINE_SELECTIONS)):
                self.register_run(regional, save=False)
        for identifier, job in durable.get("jobs", {}).items():
            if isinstance(job, dict):
                if job.get("state") in {"QUEUED", "RUNNING"}:
                    job.update(state="ERROR", error="Server restarted during execution; submit again to resume the deterministic cached run", stage="interrupted")
                self.jobs[identifier] = job
        self._prune_jobs()
        self.worker = None
        self.fast_worker = None
        if start_worker:
            self.worker = threading.Thread(target=self._work, name="locator-model-worker", daemon=True)
            self.worker.start()
            self.fast_worker = threading.Thread(target=self._work_fast, name="locator-cached-worker", daemon=True)
            self.fast_worker.start()

    def register_run(self, folder: Path, *, save=True):
        meta = read_json(folder / "run_metadata.json", {})
        if is_fast_run(meta):
            verify_fast_artifacts(self.root, folder)
            with self.lock:
                self.runs.pop(meta["run_id"], None)
                self.runs[meta["run_id"]] = folder.resolve()
                if save:
                    self._save()
            return
        if meta.get("run_id") and meta.get("scope", {}).get("data_mode") == "real" and "validate" in meta.get("completed_current_stages", []):
            catalog = regional_catalog(folder)
            if (folder in {self.root / "runs/national_fine_regional_v1", self.root / "runs/national_fine_region_v1",
                           self.root / "runs/national_fine_region_v2"}
                    or (catalog and catalog.get("selection") in FINE_SELECTIONS)):
                if not set(STAGES).issubset(meta.get("completed_current_stages", [])) or not catalog or catalog.get("selection") not in FINE_SELECTIONS:
                    return
                fine_surface_metadata(folder, catalog)
            if catalog and catalog.get("parent_run_path"):
                parent = (self.root / catalog["parent_run_path"]).resolve()
                if parent.is_relative_to(self.root / "runs") and parent != folder.resolve():
                    self.register_run(parent, save=False)
            with self.lock:
                # A completed cache hit is the latest search even if this run ID
                # was registered before another saved run.
                self.runs.pop(meta["run_id"], None)
                self.runs[meta["run_id"]] = folder.resolve()
                if save:
                    self._save()

    def _save(self):
        with self.lock:
            self._prune_jobs()
            _atomic_json(self.registry_path, {"runs": {identifier: str(path.relative_to(self.root)) for identifier, path in self.runs.items()}, "jobs": self.jobs})

    def _prune_jobs(self):
        active = {identifier for identifier, record in self.jobs.items() if record.get("state") in {"QUEUED", "RUNNING"}}
        terminal = [identifier for identifier in self.jobs if identifier not in active][-100:]
        retained = active | set(terminal)
        self.jobs = {identifier: record for identifier, record in self.jobs.items() if identifier in retained}

    def resolve_run(self, identifier):
        with self.lock:
            folder = self.runs.get(identifier)
        if folder is None:
            raise ApiError("Unknown run ID", 404, "run_not_found")
        return folder

    def latest_run_id(self):
        with self.lock:
            return next(reversed(self.runs), None)

    def _regional_baseline(self):
        with self.lock:
            for relative in reversed(REGIONAL_BASELINES):
                folder = self.root / relative
                identifier = read_json(folder / "run_metadata.json", {}).get("run_id")
                if identifier and self.runs.get(identifier) == folder:
                    return folder
        return None

    def _regional_wrapper_path(self, folder=None):
        baseline = folder or self._regional_baseline()
        catalog = regional_catalog(baseline) if baseline else None
        selection = catalog.get("selection") if catalog else None
        selection = selection or "representative_parent_cells"
        if selection not in REGIONAL_WRAPPERS:
            raise ApiError("Unsupported regional parent selection", 422, "invalid_regional_configuration")
        return self.root / REGIONAL_WRAPPERS[selection]

    def _nationwide_region_candidate(self, folder):
        """Validate a saved regional map choice without replaying scientific work."""
        from dc_locator.geography.sources.ingestion import file_digest

        try:
            meta = read_json(folder / "run_metadata.json", {})
            scope = meta.get("scope", {})
            if (not isinstance(meta.get("run_id"), str) or not meta["run_id"]
                    or scope.get("data_mode") != "real" or scope.get("scope") != "regional_refinement"
                    or not set(STAGES).issubset(meta.get("completed_current_stages", []))):
                return None
            catalog = regional_catalog(folder)
            if (not catalog or catalog.get("selection") not in {"representative_parent_cells", "national_fine_region_parents"}
                    or catalog.get("cell_size_m") != 1000 or not 0 < catalog.get("maximum_region_extent_km", 0) <= 20):
                return None
            self.reader.require_result_artifacts(folder, folder)
            # Check bound presentation artifacts; no national surface or raw source
            # is loaded, and an old scientific revision remains a valid saved view.
            names = ("regional_catalog.json", "config_snapshot.json", "screening_summary.json", "candidate_regions.parquet",
                     "candidate_regions.geojson", "ranked_cells.parquet", "profile_snapshot.json", "weight_result.json")
            hashes = meta.get("output_hashes", {})
            if any(not hashes.get(name) or file_digest(folder / name) != hashes[name] for name in names):
                return None
            parent = (self.root / catalog.get("parent_run_path", "")).resolve()
            if not parent.is_relative_to(self.root / "runs") or parent == folder.resolve():
                return None
            parent_meta = read_json(parent / "run_metadata.json", {})
            parent_scope = parent_meta.get("scope", {})
            if (parent_scope.get("data_mode") != "real" or parent_scope.get("scope") != "conus"
                    or parent_scope.get("national_model_supported") is not True
                    or not set(STAGES).issubset(parent_meta.get("completed_current_stages", []))
                    or parent_meta.get("run_id") != catalog.get("parent_run_id")
                    or not parent_meta.get("stage_identity")
                    or parent_meta["stage_identity"] != catalog.get("parent_stage_identity")):
                return None
            return meta["run_id"]
        except (ApiError, OSError, ValueError, TypeError, AttributeError):
            return None

    def _refresh_completed_regional_baselines(self):
        """Discover an external delivery once complete, leaving known run order alone."""
        verified = {}
        with self.lock:
            for relative in REGIONAL_BASELINES:
                folder = self.root / relative
                if folder not in self._pending_regional_baselines:
                    continue
                try:
                    existing = read_json(folder / "run_metadata.json", {}).get("run_id")
                except (OSError, ValueError, AttributeError):
                    continue
                if existing in self.runs:
                    self._pending_regional_baselines.discard(folder)
                    continue
                identifier = self._nationwide_region_candidate(folder)
                verified[folder] = identifier
                if identifier and identifier not in self.runs:
                    self.register_run(folder)
                    self._pending_regional_baselines.discard(folder)
        return verified

    def nationwide_regional_run_id(self, verified=None):
        verified = verified or {}
        with self.lock:
            folders = [(self.root / relative) for relative in reversed(REGIONAL_BASELINES)]
            candidates = []
            for folder in folders:
                identifier = verified[folder] if folder in verified else self._nationwide_region_candidate(folder)
                if identifier and self.runs.get(identifier) == folder:
                    candidates.append((identifier, regional_catalog(folder)["selection"]))
            return next((identifier for identifier, selection in candidates if selection == "national_fine_region_parents"),
                        next((identifier for identifier, _ in candidates), None))

    def capabilities(self):
        verified = self._refresh_completed_regional_baselines()
        latest = self.latest_run_id()
        folder = self.resolve_run(latest) if latest else None
        national = self.root / "runs/national_discovery_v2"
        regional = self._regional_baseline()
        baseline = regional or (national if (national / "config_snapshot.json").is_file() else self.root / "runs/phase7/root_v2_exploratory")
        defaults = snapshot_configuration(baseline) if (baseline / "config_snapshot.json").is_file() else {"peak_it_power_mw": 100, "average_load_percent": 80, "target_opening_year": 2030,
                    "lifetime_years": 25, "cooling": "all", "weighting": "equal", "screening_mode": "EXPLORATORY", "group_weights": dict.fromkeys(GROUPS, 0.25), "ahp_matrix": None}
        names = {"energy_carbon": "Energy / carbon", "water_stewardship": "Water stewardship", "grid_infrastructure": "Grid infrastructure", "land": "Land"}
        layers = [
            {"id": "candidates", "label": "Candidate search regions", "available": True, "reason": None, "sublayers": []},
            {"id": "grid", "label": "Analyzed grid / screening", "available": True, "reason": None, "sublayers": [{"id": "screening", "label": "Screening status", "available": True}]},
            {"id": "power_carbon", "label": "Power & Carbon", "available": True, "reason": None, "sublayers": [{"id": "carbon_intensity", "label": "Historical carbon intensity", "available": True}]},
            {"id": "water", "label": "Water", "available": True, "reason": None, "sublayers": [{"id": "water_stress", "label": "Basin water stress", "available": True}]},
            {"id": "land", "label": "Land", "available": True, "reason": None, "sublayers": [{"id": "suitable_land", "label": "Suitable land proxy", "available": True}]},
            {"id": "climate", "label": "Climate / hazard context", "available": True, "reason": None, "sublayers": [{"id": "flood", "label": "Mapped flood overlap", "available": True}, {"id": "wildfire", "label": "WHP hazard potential", "available": True},
             {"id": "wrc", "label": "Verified wildfire resilience", "available": False, "reason": "WRC source packing/mask unresolved"},
             {"id": "hurricane", "label": "Hurricane exposure", "available": False, "reason": "No accepted hurricane metric or geometry"},
             {"id": "drought", "label": "Drought hazard", "available": False, "reason": "No accepted drought hazard metric; basin water stress is displayed separately"},
             {"id": "extreme_heat", "label": "Extreme heat hazard", "available": False, "reason": "Climate normals do not establish an extreme heat hazard model"},
             {"id": "future", "label": "Future climate hazard", "available": False, "reason": "Independent NASA context is not bound to the water pathways or facility hazard scoring"}]},
            {"id": "infrastructure", "label": "Infrastructure proxy", "available": True, "reason": None, "sublayers": [{"id": "transmission_distance", "label": "Transmission distance (unverified capacity)", "available": True}]},
            {"id": "heat_reuse", "label": "Heat Reuse", "available": False, "reason": "Accepted outputs contain no heat consumer / committed partner evidence", "sublayers": []},
            socioeconomic.capability(self.root),
        ]
        scenarios = self.reader.scenarios(folder)
        catalog = regional_catalog(folder) if folder else None
        scope = regional_scope(catalog) if catalog else describe_scope(read_json(folder / "run_metadata.json", {})) if folder else SCOPE
        cached = cached_cohort_status(self.root, self.root / "runs/cleanview_regional_v2")
        ready = cached.get("ready") is True and cached.get("available") is True
        return {"schema_version": SCHEMA_VERSION, "scope": scope, "default_configuration": defaults,
                "cooling_options": [{"id": "all", "label": "Compare both accepted design assumptions"}, {"id": "air_dry_assumed", "label": "Air / dry cooling assumption"}, {"id": "cold_plate_tower_assumed", "label": "Direct-to-chip / tower assumption"}],
                "weighting_groups": [{"id": g, "label": names[g]} for g in GROUPS], "layers": layers, "scenarios": scenarios,
                "latest_run_id": latest, "nationwide_regional_run_id": self.nationwide_regional_run_id(verified),
                "analysis_modes": [{"id": "cached_regional", "label": "Cached nationwide regional evaluation", "available": ready,
                                    "reason": None if ready else cached.get("reason") or "Static native cache is unavailable"},
                                   {"id": "full_rediscovery", "label": "Full nationwide rediscovery", "available": True, "reason": None}],
                "default_analysis_mode": "cached_regional" if ready else "full_rediscovery",
                "cached_regional_baseline_run_id": cached.get("baseline_run_id") if ready else None,
                "demo": False, "configuration_bounds": DEFAULT_BOUNDS}

    def run_result(self, identifier, scenario="current"):
        folder = self.resolve_run(identifier)
        with self.reader_lock:
            return self.reader.run(folder, scenario)

    def run_response(self, identifier, scenario="current"):
        folder = self.resolve_run(identifier)
        with self.reader_lock:
            return self.reader.run_bytes(folder, scenario)

    def layer_result(self, identifier, run_id, scenario="current", sublayer=None):
        folder = self.resolve_run(run_id)
        with self.reader_lock:
            if identifier == "community_economic":
                return socioeconomic.layer(self.root, sublayer)
            return self.reader.layer(folder, identifier, scenario, sublayer)

    def socioeconomic_result(self, run_id, boundary_year=2025, scenario="current"):
        folder = self.resolve_run(run_id)
        with self.reader_lock:
            return socioeconomic.context(self.root, folder, run_id, boundary_year, scenario=scenario)

    def export(self, identifier, export_id, scenario="current"):
        folder = self.resolve_run(identifier)
        context = self.reader.context(folder, scenario)
        if export_id not in EXPORTS:
            raise ApiError("Unknown export ID", 404, "export_not_found")
        filename = EXPORTS[export_id][0]
        target = context / filename
        if export_id in {"validation", "sensitivity", "configuration"}:
            target = folder / filename
        if export_id == "validation" and not target.is_file():
            target = folder / "model_validation_summary.json"
        if not target.is_file() or not target.resolve().is_relative_to(folder.resolve()):
            raise ApiError("This export is unavailable for the selected context", 404, "export_not_found")
        return target

    def search(self, body):
        if not isinstance(body, dict) or set(body) - {"facility", "analysis_mode"}:
            raise ApiError("Request must contain a facility object and optional analysis_mode")
        mode = body.get("analysis_mode", "full_rediscovery")
        if type(mode) is not str or mode not in {"cached_regional", "full_rediscovery"}:
            raise ApiError("analysis_mode must be cached_regional or full_rediscovery")
        facility = validate_facility({"facility": body.get("facility")})
        if mode == "cached_regional":
            return self._search_cached(facility)
        with self.lock:
            if self.queue.full():
                raise ApiError("Local model worker queue is full; try again after a job completes", 429, "queue_full")
            job_id = "job_" + uuid.uuid4().hex
            job = {"schema_version": SCHEMA_VERSION, "id": job_id, "state": "QUEUED", "stage": "queued", "run_id": None, "error": None,
                   "facility": facility, "submitted_at": datetime.now(timezone.utc).isoformat()}
            job["analysis_mode"] = "full_rediscovery"
            self.jobs[job_id] = job
            self._save()
            self.queue.put_nowait(job_id)
        return {"schema_version": SCHEMA_VERSION, "job_id": job_id}

    def _search_cached(self, facility):
        baseline = self.root / "runs/cleanview_regional_v2"
        status = cached_cohort_status(self.root, baseline)
        if status.get("ready") is not True or status.get("available") is not True:
            raise ApiError(status.get("reason") or "Static native cache is not prepared", 422, "cached_regional_unavailable")
        try:
            identity = fast_request_identity(self.root, baseline, facility)
        except (ValueError, OSError, KeyError) as exc:
            raise ApiError(str(exc), 422, "cached_regional_unavailable") from exc
        if not isinstance(identity, str) or len(identity) != 64 or any(c not in "0123456789abcdef" for c in identity):
            raise ApiError("Invalid cached request identity", 422, "cached_regional_unavailable")
        output = self.owned / "cached_regional_runs" / identity
        with self.lock:
            for identifier, record in self.jobs.items():
                if record.get("analysis_mode") != "cached_regional" or record.get("request_identity") != identity:
                    continue
                if record.get("state") in {"QUEUED", "RUNNING"}:
                    return {"schema_version": SCHEMA_VERSION, "job_id": identifier}
                if record.get("state") == "COMPLETE":
                    meta = verify_fast_artifacts(self.root, output)
                    if meta.get("run_id") != record.get("run_id") or meta.get("stage_identity") != identity:
                        raise ApiError("Cached completed job lineage mismatch", 422, "completed_run_checksum_mismatch")
                    self.register_run(output)
                    return {"schema_version": SCHEMA_VERSION, "job_id": identifier}
            if (output / "run_metadata.json").is_file():
                meta = verify_fast_artifacts(self.root, output)
                if meta.get("stage_identity") != identity:
                    raise ApiError("Cached completed folder identity mismatch", 422, "completed_run_checksum_mismatch")
                self.register_run(output)
                self.run_response(meta["run_id"])
                identifier = "job_" + uuid.uuid4().hex
                self.jobs[identifier] = {"schema_version": SCHEMA_VERSION, "id": identifier, "state": "COMPLETE", "stage": "reused verified cached evaluation",
                    "run_id": meta["run_id"], "error": None, "facility": facility, "analysis_mode": "cached_regional",
                    "request_identity": identity, "output_path": str(output), "submitted_at": datetime.now(timezone.utc).isoformat()}
                self._save()
                return {"schema_version": SCHEMA_VERSION, "job_id": identifier}
            if self.fast_queue.full():
                raise ApiError("Cached regional worker queue is full; try again after a job completes", 429, "queue_full")
            job_id = "job_" + uuid.uuid4().hex
            self.jobs[job_id] = {"schema_version": SCHEMA_VERSION, "id": job_id, "state": "QUEUED", "stage": "queued",
                "run_id": None, "error": None, "facility": facility, "analysis_mode": "cached_regional",
                "request_identity": identity, "output_path": str(output), "submitted_at": datetime.now(timezone.utc).isoformat()}
            self._save()
            self.fast_queue.put_nowait(job_id)
        return {"schema_version": SCHEMA_VERSION, "job_id": job_id}

    def job(self, identifier):
        with self.lock:
            record = self.jobs.get(identifier)
            if record is None:
                raise ApiError("Unknown job ID", 404, "job_not_found")
            return {**{k: record[k] for k in ("schema_version", "id", "state", "stage", "run_id", "error")},
                    "analysis_mode": record.get("analysis_mode", "full_rediscovery")}

    def _update(self, identifier, **values):
        with self.lock:
            self.jobs[identifier].update(values)
            self._save()

    def _write_configuration(self, facility):
        # All created scientific configuration files are scoped under the owned service directory.
        template = self.root / "configs/run_national_exploratory.yaml"
        if not template.is_file():
            raise ApiError("National search configuration is unavailable; no development-area fallback is permitted", 422, "missing_national_configuration")
        run_bytes = template.read_bytes()
        base = yaml.safe_load(run_bytes.decode("utf-8"))
        if base.get("study_area") != "conus" or base.get("data_mode") != "real":
            raise ApiError("National search configuration must use real CONUS geography", 422, "invalid_national_configuration")
        facility_bytes = (self.root / base["facility"]).read_bytes()
        cooling_bytes = (self.root / base["cooling_designs"]).read_bytes()
        adapter_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        baseline_hashes = {"run": hashlib.sha256(run_bytes).hexdigest(), "facility": hashlib.sha256(facility_bytes).hexdigest(),
                           "cooling": hashlib.sha256(cooling_bytes).hexdigest()}
        digest = hashlib.sha256(json_bytes({"facility": facility, "baseline_template_hashes": baseline_hashes, "configuration_adapter_sha256": adapter_hash})).hexdigest()[:24]
        folder = self.owned / "configurations" / digest
        if not folder.exists() and len(list((self.owned / "configurations").glob("*"))) >= 64:
            raise ApiError("Local service configuration budget (64) reached; preserve or archive old service runs before adding configurations", 429, "configuration_budget")
        folder.mkdir(parents=True, exist_ok=True)
        facility_doc = yaml.safe_load(facility_bytes.decode("utf-8"))
        entry = facility_doc["facilities"][0]
        entry.update(facility_id="frontend_" + digest, peak_it_power_mw=facility["peak_it_power_mw"],
                     average_it_load_factor=facility["average_load_percent"] / 100, target_opening_year=facility["target_opening_year"],
                     operating_lifetime_years=facility["lifetime_years"], screening_mode=facility["screening_mode"],
                     cooling_design_id=None, cooling_designs=list(COOLING[1:]) if facility["cooling"] == "all" else [facility["cooling"]],
                     basis="project_assumption", rationale="User-supplied frontend facility requirements. Remaining project assumptions: 8760 hours per nonleap modeled year and 0.40468564224 km2 (100 acres) planning land area; see docs/research/phase3/screening_threshold_basis.md section 7. Land is not surveyed contiguous/buildable acreage.")
        designs_doc = yaml.safe_load(cooling_bytes.decode("utf-8"))
        if facility["cooling"] != "all":
            designs_doc["cooling_designs"] = [d for d in designs_doc["cooling_designs"] if d["design_id"] == facility["cooling"]]
        base.update(run_name="frontend_" + digest, facility=str((folder / "facility.yaml").relative_to(self.root)),
                    cooling_designs=str((folder / "cooling_designs.yaml").relative_to(self.root)), screening_mode=facility["screening_mode"],
                    weighting_method=facility["weighting"], user_group_weights=facility["group_weights"] if facility["weighting"] == "user" else None, ahp_input=None)
        if facility["weighting"] == "ahp":
            _write_frozen(folder / "ahp.json", json_bytes({"criteria_ids": list(GROUPS), "matrix": facility["ahp_matrix"]}))
            base["ahp_input"] = str((folder / "ahp.json").relative_to(self.root))
        policy = base.get("future", {}).get("annual_extension")
        if isinstance(policy, dict) and policy.get("enabled"):
            policy["rationale"] = f"User-declared constant historical-static opening-year physical scenario repeated for exactly {facility['lifetime_years']} years from {facility['target_opening_year']}. No future-grid forecast, Aqueduct interpolation or geographic cooling performance is asserted."
        for filename, document in (("facility.yaml", facility_doc), ("cooling_designs.yaml", designs_doc), ("run.yaml", base)):
            target = folder / filename
            serialized = yaml.safe_dump(document, allow_unicode=True, sort_keys=False).encode("utf-8")
            # Stable frozen bytes allow accepted Pipeline identities and completed stages to be reused.
            _write_frozen(target, serialized)
        return folder / "run.yaml"

    def _write_regional_configuration(self, parent: Path) -> Path:
        template = self._regional_wrapper_path()
        if not template.is_file():
            raise ApiError("Regional refinement configuration is unavailable", 422, "missing_regional_configuration")
        wrapper = yaml.safe_load(template.read_text(encoding="utf-8"))
        delivery = {"representative_parent_cells": "phase9_regional_v1", "national_fine_surface": "phase11_national_fine_surface_v1",
                    "national_fine_region_parents": "phase11_national_fine_surface_v1"}
        if (wrapper.get("schema_version") != "3.0.0" or wrapper.get("delivery_version") != delivery.get(wrapper.get("selection"))
                or REGIONAL_WRAPPERS.get(wrapper.get("selection")) != template.relative_to(self.root).as_posix()):
            raise ApiError("Invalid regional refinement configuration", 422, "invalid_regional_configuration")
        wrapper["parent_config"] = parent.relative_to(self.root).as_posix()
        content = yaml.safe_dump(wrapper, allow_unicode=True, sort_keys=False).encode("utf-8")
        target = parent.parent / ("regional_" + hashlib.sha256(content).hexdigest()[:24] + ".yaml")
        _write_frozen(target, content)
        return target

    def _work(self):
        while True:
            identifier = self.queue.get()
            try:
                self._execute_job(identifier)
            except Exception as exc:
                self._update(identifier, state="ERROR", error=f"{type(exc).__name__}: {exc}")
            finally:
                self.queue.task_done()

    def _work_fast(self):
        while True:
            identifier = self.fast_queue.get()
            try:
                self._execute_fast_job(identifier)
            except Exception as exc:
                self._update(identifier, state="ERROR", error=f"{type(exc).__name__}: {exc}")
            finally:
                self.fast_queue.task_done()

    def _invoke_fast_runner(self, facility, output):
        # Isolate the model heap from any concurrently running full rediscovery.
        from concurrent.futures import ProcessPoolExecutor
        from multiprocessing import get_context
        with ProcessPoolExecutor(max_workers=1, mp_context=get_context("spawn")) as executor:
            return executor.submit(run_cached_evaluation, self.root, self.root / "runs/cleanview_regional_v2", facility, output).result()

    def _execute_fast_job(self, identifier):
        started = time.perf_counter()
        self._update(identifier, state="RUNNING", stage="evaluate cached cohort")
        record = self.jobs[identifier]
        output = self.owned / "cached_regional_runs" / record["request_identity"]
        if record.get("output_path") != str(output):
            raise ApiError("Cached job output binding mismatch", 422, "completed_run_checksum_mismatch")
        if (output / "run_metadata.json").is_file():
            meta = verify_fast_artifacts(self.root, output)
        else:
            self._invoke_fast_runner(record["facility"], output)
            meta = verify_fast_artifacts(self.root, output)
        if meta.get("stage_identity") != record["request_identity"]:
            raise ApiError("Cached evaluation identity mismatch", 422, "completed_run_checksum_mismatch")
        evaluated = time.perf_counter()
        self.register_run(output)
        self._update(identifier, stage="materialize response", evaluation_seconds=evaluated - started)
        self.run_response(meta["run_id"])
        finished = time.perf_counter()
        self._update(identifier, state="COMPLETE", stage="complete", run_id=meta["run_id"], error=None,
                     response_materialization_seconds=finished - evaluated, total_execution_seconds=finished - started)

    def _completed_default_run(self, facility):
        """Verify the completed default without creating another scientific identity.

        This deliberately reuses only the registered default baseline. Every native
        input and output is content-hashed on each check; no stat-based shortcut is
        used. Stale inputs retain the normal new-run path, while damaged completed
        evidence fails explicitly instead of being silently rebound or overwritten.
        """
        folder = self._regional_baseline()
        if folder is None:
            return None, "completed default baseline unavailable"
        meta = read_json(folder / "run_metadata.json", {})
        with self.lock:
            registered = self.runs.get(meta.get("run_id")) == folder
        if not registered or not set(STAGES).issubset(meta.get("completed_current_stages", [])):
            return None, "completed default baseline unavailable"
        if meta.get("scope", {}).get("data_mode") != "real" or meta.get("scope", {}).get("scope") != "regional_refinement":
            return None, "completed default scope differs"
        if snapshot_configuration(folder) != facility:
            return None, "completed default facility or preferences differ"

        from dc_locator.geography.sources.ingestion import file_digest
        from dc_locator.pipeline import digest_json, environment_identity
        from dc_locator.regional import RegionalConfig
        from dc_locator.run_config import load_delivery_config, load_source_document

        def native_path(value):
            path = (self.root / value).resolve()
            if not path.is_relative_to(self.root):
                raise ApiError("Completed baseline references a path outside the project", 422, "completed_run_checksum_mismatch")
            return path

        models = meta.get("actual_working_code_sha256", {})
        current_models = {str(p.relative_to(self.root)) for p in (self.root / "src/dc_locator").rglob("*.py")}
        current_models |= {"requirements.lock.txt", "pyproject.toml"}
        if set(models) != current_models:
            return None, "completed default model file set differs"
        for name, sha in sorted(models.items()):
            path = native_path(name)
            if not path.is_file() or file_digest(path) != sha:
                return None, "completed default model content differs: " + name
        environment = environment_identity()
        if meta.get("environment") != environment:
            return None, "completed default environment differs"
        configs = meta.get("config_hashes", {})
        for name, sha in sorted(configs.items()):
            path = native_path(name)
            if not path.is_file() or file_digest(path) != sha:
                return None, "completed default configuration content differs: " + name

        wrapper_path = self._regional_wrapper_path(folder)
        if str(wrapper_path) not in configs:
            return None, "completed default configuration identity differs: missing regional wrapper"
        wrapper = RegionalConfig.model_validate(yaml.safe_load(wrapper_path.read_text(encoding="utf-8")))
        parent_path = native_path(wrapper.parent_config)
        parent_config = load_delivery_config(parent_path)
        configuration = parent_config.model_dump(mode="json")
        references = {parent_path, native_path(parent_config.grid_path), native_path(parent_config.grid_config),
                      native_path(parent_config.source_registry), native_path(parent_config.local_sources)}
        for field in ("core_source_inputs", "expanded_source_inputs", "aqueduct_source_input", "fixture_geography", "fixture_provenance",
                      "facility", "cooling_designs", "physical_scenarios", "constraints", "scoring_profile", "ahp_input"):
            value = getattr(parent_config, field)
            if value:
                references.add(native_path(value))
        if parent_config.future["enabled"]:
            references.update(native_path(parent_config.future[k]) for k in ("profile_declaration", "lifecycle"))
            references.update(native_path(parent_config.future["profiles_directory"]) / f"{way}_{year}.yaml"
                              for way in parent_config.future["pathways"] for year in parent_config.future["milestone_years"])
        policy_paths = {wrapper_path, native_path(wrapper.grid_config), native_path(wrapper.scoring_profile)}
        if set(configs) != {str(p) for p in references | policy_paths}:
            return None, "completed default configuration file set differs"
        parent_hashes = {str(p): configs[str(p)] for p in sorted(references)}

        records = load_source_document(native_path(parent_config.local_sources), self.root).get("files", [])
        sources = meta.get("source_checksums", {})
        if not records or set(sources) != {str(native_path(record["path"])) for record in records}:
            return None, "completed default source file set differs"
        for record in records:
            path = native_path(record["path"])
            if not path.exists():
                return None, "completed default source content differs: missing " + str(path)
            size = sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) if path.is_dir() else path.stat().st_size
            if size != record["bytes"] or file_digest(path) != record["sha256"] or sources[str(path)] != record["sha256"]:
                return None, "completed default source content differs: " + str(path)

        parent_identity = digest_json({"delivery_version": parent_config.delivery_version, "config": configuration,
                                      "config_hashes": parent_hashes, "model_hashes": models, "source_hashes": sources,
                                      "grid_sha256": configs[str(native_path(parent_config.grid_path))], "environment": environment})
        binding = read_json(folder / "regional_binding.json", {})
        if (binding.get("config") != wrapper.model_dump(mode="json") or binding.get("parent_identity") != parent_identity
                or binding.get("wrapper_sha256") != configs[str(wrapper_path)]
                or binding.get("grid_config_sha256") != configs[str(native_path(wrapper.grid_config))]
                or binding.get("profile_sha256") != configs[str(native_path(wrapper.scoring_profile))]
                or digest_json(binding) != meta.get("stage_identity")
                or meta.get("run_id") != "regional_refinement__" + digest_json(binding)[:16]):
            raise ApiError("Completed baseline scientific binding mismatch", 422, "completed_run_checksum_mismatch")

        hashes = meta.get("output_hashes", {})
        # Match the native regional inventory exclusions; added/unlisted evidence
        # cannot remove a checksum obligation from the completion metadata.
        inventory = {p.relative_to(folder).as_posix() for p in folder.rglob("*")
                     if p.is_file() and p.name not in {"run_metadata.json", "checkpoint.json"}}
        required = {"regional_binding.json", "regional_catalog.json", "config_snapshot.json", "profile_snapshot.json",
                    "ranked_cells.parquet", "candidate_regions.parquet", "region_membership.parquet"}
        if set(hashes) != inventory or not required.issubset(hashes):
            raise ApiError("Completed baseline output checksum inventory mismatch", 422, "completed_run_checksum_mismatch")
        for name, sha in sorted(hashes.items()):
            path = (folder / name).resolve()
            if not path.is_relative_to(folder) or not path.is_file() or file_digest(path) != sha:
                raise ApiError("Completed baseline output checksum mismatch: " + name, 422, "completed_run_checksum_mismatch")
        catalog = regional_catalog(folder)
        if catalog.get("selection") in FINE_SELECTIONS:
            from dc_locator.fine_surface import stage_identity
            surface = fine_surface_metadata(folder, catalog)
            if surface["stage_identity"] != digest_json(stage_identity(meta["stage_identity"])):
                raise ApiError("Completed baseline national fine stage identity mismatch", 422, "completed_run_checksum_mismatch")
        parent = native_path(catalog.get("parent_run_path", ""))
        parent_meta = read_json(parent / "run_metadata.json", {})
        if (not parent.is_relative_to(folder) or parent_meta.get("stage_identity") != parent_identity
                or catalog.get("parent_stage_identity") != parent_identity or catalog.get("parent_run_id") != parent_meta.get("run_id")
                or parent_meta.get("configuration") != configuration or parent_meta.get("config_hashes") != parent_hashes
                or parent_meta.get("actual_working_code_sha256") != models or parent_meta.get("source_checksums") != sources
                or parent_meta.get("environment") != environment or not set(STAGES).issubset(parent_meta.get("completed_current_stages", []))
                or read_json(folder / "config_snapshot.json", {}).get("run") != meta.get("configuration")):
            raise ApiError("Completed baseline parent lineage mismatch", 422, "completed_run_checksum_mismatch")
        return folder, "reused verified completed run"

    def _execute_job(self, identifier):
        from dc_locator.pipeline import Pipeline
        from dc_locator.regional import run_regional
        self._update(identifier, state="RUNNING", stage="verify inputs")
        facility = self.jobs[identifier]["facility"]
        completed, reuse_reason = self._completed_default_run(facility)
        self._update(identifier, baseline_reuse_reason=reuse_reason)
        if completed is not None:
            run_id = read_json(completed / "run_metadata.json")["run_id"]
            self.register_run(completed)
            self.run_response(run_id)
            self._update(identifier, state="COMPLETE", stage=reuse_reason, run_id=run_id, error=None)
            return
        configuration = self._write_configuration(facility)
        wrapper = self._write_regional_configuration(configuration)
        # Pipeline computes and verifies complete source/config/model/environment identity.
        # A fresh owned probe is removed only when empty; completed runs are never overwritten.
        probe = self.owned / "jobs" / identifier / "output"
        pipeline = Pipeline(configuration, probe, root=self.root)
        wrapper_doc = yaml.safe_load(wrapper.read_text(encoding="utf-8"))
        regional_inputs = {name: hashlib.sha256((self.root / wrapper_doc[name]).read_bytes()).hexdigest()
                           for name in ("grid_config", "scoring_profile")}
        identity = hashlib.sha256(json_bytes({"parent_identity": pipeline.identity,
                        "regional_wrapper_sha256": hashlib.sha256(wrapper.read_bytes()).hexdigest(),
                        "regional_input_hashes": regional_inputs})).hexdigest()
        output = self.owned / "regional_runs" / identity
        if probe.is_dir() and not any(probe.iterdir()):
            probe.rmdir()
        # The orchestrator verifies parent and batch identities and all reused output hashes.
        output = run_regional(wrapper, output, root=self.root, progress=lambda stage: self._update(identifier, stage=stage))
        run_id = read_json(output / "run_metadata.json", {}).get("run_id")
        if not run_id:
            raise ValueError("Regional workflow did not produce a completed run identity")
        with self.lock:
            self.register_run(output)
        # Verify/materialize canonical adapter bytes before declaring completion.
        self.run_response(run_id)
        self._update(identifier, state="COMPLETE", stage="complete", run_id=run_id, error=None)
