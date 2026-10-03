"""Bounded job registry and configuration adapter for the deterministic model."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import queue
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .serialization import ApiError, ArtifactReader, EXPORTS, GROUPS, SCHEMA_VERSION, SCOPE, clean, json_bytes, read_json, snapshot_configuration

STAGES = ("ingest", "build-features", "screen", "simulate", "rank", "cluster", "validate")
COOLING = ("all", "air_dry_assumed", "cold_plate_tower_assumed")
FIELDS = {"peak_it_power_mw", "average_load_percent", "target_opening_year", "lifetime_years", "cooling", "weighting", "screening_mode", "group_weights", "ahp_matrix"}
DEFAULT_BOUNDS = {"peak_it_power_mw": {"min_exclusive": 0, "max": 1000}, "average_load_percent": {"min_exclusive": 0, "max": 100},
                  "target_opening_year": {"min": 2026, "max": 2100}, "lifetime_years": {"min": 1, "max": 100}}


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
        self.reader = ArtifactReader(self.owned / "response_cache")
        self.runs: dict[str, Path] = {}
        self.jobs: dict[str, dict] = {}
        self.queue = queue.Queue(maxsize=8)
        for relative in ("runs/example", "runs/phase7/root_v2_exploratory"):
            self.register_run(self.root / relative, save=False)
        durable = read_json(self.registry_path, {})
        for relative in durable.get("runs", {}).values():
            path = (self.root / relative).resolve()
            if path.is_relative_to(self.owned):
                self.register_run(path, save=False)
        for identifier, job in durable.get("jobs", {}).items():
            if isinstance(job, dict):
                if job.get("state") in {"QUEUED", "RUNNING"}:
                    job.update(state="ERROR", error="Server restarted during execution; submit again to resume the deterministic cached run", stage="interrupted")
                self.jobs[identifier] = job
        self._prune_jobs()
        self.worker = None
        if start_worker:
            self.worker = threading.Thread(target=self._work, name="locator-model-worker", daemon=True)
            self.worker.start()

    def register_run(self, folder: Path, *, save=True):
        meta = read_json(folder / "run_metadata.json", {})
        if meta.get("run_id") and meta.get("scope", {}).get("data_mode") == "real" and "validate" in meta.get("completed_current_stages", []):
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

    def capabilities(self):
        latest = self.latest_run_id()
        folder = self.resolve_run(latest) if latest else None
        baseline = self.root / "runs/phase7/root_v2_exploratory"
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
            {"id": "community_economic", "label": "Community / Economic", "available": False, "reason": "Accepted outputs contain no compatible community / economic score", "sublayers": []},
        ]
        scenarios = [{"id": "current", "label": "Current historical-static context", "year": None, "pathway": None, "available": bool(folder), "reason": None}]
        for pathway in ("bau", "opt", "pes"):
            for year in (2030, 2040, 2050, 2080):
                identifier = f"{pathway}_{year}"
                external = read_json(folder / "future_contexts" / identifier / "external_scenario.json", {}) if folder else {}
                available = external.get("supported") is True and year != 2040
                scenarios.append({"id": identifier, "label": f"{year} · {pathway.upper()} water context", "year": year, "pathway": pathway,
                                  "available": available, "reason": None if available else "No native 2040 window; no interpolation" if year == 2040 else "No supported output for this run"})
        return {"schema_version": SCHEMA_VERSION, "scope": SCOPE, "default_configuration": defaults,
                "cooling_options": [{"id": "all", "label": "Compare both accepted design assumptions"}, {"id": "air_dry_assumed", "label": "Air / dry cooling assumption"}, {"id": "cold_plate_tower_assumed", "label": "Direct-to-chip / tower assumption"}],
                "weighting_groups": [{"id": g, "label": names[g]} for g in GROUPS], "layers": layers, "scenarios": scenarios,
                "latest_run_id": latest, "demo": False, "configuration_bounds": DEFAULT_BOUNDS}

    def run_result(self, identifier, scenario="current"):
        folder = self.resolve_run(identifier)
        with self.reader_lock:
            return self.reader.run(folder, scenario)

    def layer_result(self, identifier, run_id, scenario="current", sublayer=None):
        folder = self.resolve_run(run_id)
        with self.reader_lock:
            return self.reader.layer(folder, identifier, scenario, sublayer)

    def export(self, identifier, export_id, scenario="current"):
        folder = self.resolve_run(identifier)
        context = self.reader.context(folder, scenario)
        if export_id not in EXPORTS:
            raise ApiError("Unknown export ID", 404, "export_not_found")
        filename = EXPORTS[export_id][0]
        target = context / filename
        if export_id in {"validation", "sensitivity", "configuration"}:
            target = folder / filename
        if not target.is_file() or not target.resolve().is_relative_to(folder.resolve()):
            raise ApiError("This export is unavailable for the selected context", 404, "export_not_found")
        return target

    def search(self, body):
        facility = validate_facility(body)
        with self.lock:
            if self.queue.full():
                raise ApiError("Local model worker queue is full; try again after a job completes", 429, "queue_full")
            job_id = "job_" + uuid.uuid4().hex
            job = {"schema_version": SCHEMA_VERSION, "id": job_id, "state": "QUEUED", "stage": "queued", "run_id": None, "error": None,
                   "facility": facility, "submitted_at": datetime.now(timezone.utc).isoformat()}
            self.jobs[job_id] = job
            self._save()
            self.queue.put_nowait(job_id)
        return {"schema_version": SCHEMA_VERSION, "job_id": job_id}

    def job(self, identifier):
        with self.lock:
            record = self.jobs.get(identifier)
            if record is None:
                raise ApiError("Unknown job ID", 404, "job_not_found")
            return {k: record[k] for k in ("schema_version", "id", "state", "stage", "run_id", "error")}

    def _update(self, identifier, **values):
        with self.lock:
            self.jobs[identifier].update(values)
            self._save()

    def _write_configuration(self, facility):
        # All created scientific configuration files are scoped under the owned service directory.
        run_bytes = (self.root / "configs/run_exploratory.yaml").read_bytes()
        base = yaml.safe_load(run_bytes.decode("utf-8"))
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
        policy = base["future"]["annual_extension"]
        policy["rationale"] = f"User-declared constant historical-static opening-year physical scenario repeated for exactly {facility['lifetime_years']} years from {facility['target_opening_year']}. No future-grid forecast, Aqueduct interpolation or geographic cooling performance is asserted."
        for filename, document in (("facility.yaml", facility_doc), ("cooling_designs.yaml", designs_doc), ("run.yaml", base)):
            target = folder / filename
            serialized = yaml.safe_dump(document, allow_unicode=True, sort_keys=False).encode("utf-8")
            # Stable frozen bytes allow accepted Pipeline identities and completed stages to be reused.
            _write_frozen(target, serialized)
        return folder / "run.yaml"

    def _work(self):
        while True:
            identifier = self.queue.get()
            try:
                self._execute_job(identifier)
            except Exception as exc:
                self._update(identifier, state="ERROR", error=f"{type(exc).__name__}: {exc}")
            finally:
                self.queue.task_done()

    def _execute_job(self, identifier):
        from dc_locator.pipeline import Pipeline
        self._update(identifier, state="RUNNING", stage="verify inputs")
        facility = self.jobs[identifier]["facility"]
        configuration = self._write_configuration(facility)
        # Pipeline computes and verifies complete source/config/model/environment identity.
        # A fresh owned probe is removed only when empty; completed runs are never overwritten.
        probe = self.owned / "jobs" / identifier / "output"
        pipeline = Pipeline(configuration, probe, root=self.root)
        output = self.owned / "model_runs" / pipeline.identity
        if probe.is_dir() and not any(probe.iterdir()):
            probe.rmdir()
        output.mkdir(parents=True, exist_ok=True)
        for manifest in (output / "stage_manifests").glob("*.json"):
            if read_json(manifest, {}).get("stage_identity") != pipeline.identity:
                raise ValueError("Owned output directory has a mismatched scientific identity")
        if any(output.iterdir()) and not list((output / "stage_manifests").glob("*.json")):
            raise ValueError("Owned output directory has no accepted stage manifests")
        pipeline.output = output
        for stage in STAGES:
            self._update(identifier, stage=stage)
            if stage == "build-features":
                reuse_bound_geography(pipeline, list(self.runs.values()))
            pipeline.execute(stage)
        with self.lock:
            self.register_run(output)
        # Serialize now so COMPLETE cannot conceal an incompatible frontend response.
        self.run_result(pipeline.run_id)
        self._update(identifier, state="COMPLETE", stage="complete", run_id=pipeline.run_id, error=None)
