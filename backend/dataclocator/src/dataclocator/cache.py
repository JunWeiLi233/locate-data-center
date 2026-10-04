"""Validate immutable run identity and recorded artifacts before any cache reuse."""

import hashlib
import json
from pathlib import Path
import re

from . import MODEL_VERSION
from .pipeline import write_json
from .schemas import validate_config

CORE_ARTIFACTS = {"config.json", "run_identity.json", "candidate_evidence.json", "results.json"}
MODEL_ARTIFACTS = {"samples.npz", "common_draws.npz", "annual_trajectories.csv", "candidates.csv", "report.md"}
PLOT_ARTIFACTS = {"frontiers.png", "frontiers.svg"}
INTEGRITY_FILE = "cache_integrity.json"
HASH_PATTERN = re.compile(r"[0-9a-f]{64}\Z")


class CacheIntegrityError(ValueError):
    """Reject damaged, stale or rebound caches without changing their evidence."""


def read_cache_json(path):
    """Read finite JSON once, converting missing or malformed evidence to rejection."""
    def nonfinite(value):
        """Nonfinite constants cannot describe valid frozen JSON artifacts."""
        raise ValueError("nonfinite JSON")
    try:
        value = json.loads(Path(path).read_bytes(), parse_constant=nonfinite)
        # Serialization catches overflowing exponents parsed as floating infinity.
        json.dumps(value, allow_nan=False)
        return value
    except (OSError, ValueError, TypeError, RecursionError) as exc:
        raise CacheIntegrityError(f"cache artifact unavailable or invalid: {Path(path).name}") from exc


def identity_run_id(identity):
    """Retain the existing canonical CLI/API run-ID formula without altering math."""
    try:
        digest = hashlib.sha256(json.dumps(identity, sort_keys=True, allow_nan=False).encode()).hexdigest()
    except (TypeError, ValueError) as exc:
        raise CacheIntegrityError("cache identity is invalid") from exc
    return "run_" + digest[:16]


def source_hashes(sources):
    """Require unique, explicitly pinned sources rather than a lossy dictionary."""
    try:
        hashes = {source["source_id"]: source["sha256"] for source in sources}
        if len(hashes) != len(sources) or any(not isinstance(value, str) or not HASH_PATTERN.fullmatch(value) for value in hashes.values()):
            raise ValueError("invalid source hashes")
        return hashes
    except (KeyError, TypeError, ValueError) as exc:
        raise CacheIntegrityError("cache source identity is invalid") from exc


def validate_frozen(frozen):
    """Validate the accepted snapshot identity and its source/evidence bindings."""
    try:
        identity = frozen["identity"]
        required = {"config", "input_hashes", "dataset_hashes", "model_version", "with_sensitivity", "with_convergence"}
        if set(identity) != required or identity["model_version"] != MODEL_VERSION:
            raise ValueError("stale or malformed model identity")
        if validate_config(identity["config"]) != identity["config"]:
            raise ValueError("configuration differs from current validation")
        if any(type(identity[key]) is not bool for key in ("with_sensitivity", "with_convergence")):
            raise ValueError("invalid audit settings")
        inputs = identity["input_hashes"]
        if set(inputs) != {"candidate_evidence", "grid_regions"} or any(not isinstance(value, str) or not HASH_PATTERN.fullmatch(value) for value in inputs.values()):
            raise ValueError("invalid input hashes")
        if frozen["run_id"] != identity_run_id(identity):
            raise ValueError("run ID does not match frozen identity")
        if source_hashes(frozen["manifest"]["sources"]) != identity["dataset_hashes"]:
            raise ValueError("dataset hashes do not match frozen sources")
        if not isinstance(frozen["evidence"]["candidates"], list):
            raise ValueError("candidate evidence is invalid")
        if frozen["evidence"].get("model_version") != MODEL_VERSION or frozen["evidence"].get("sources") != frozen["manifest"]["sources"] or source_hashes(frozen["evidence"].get("sources", [])) != identity["dataset_hashes"]:
            raise ValueError("candidate evidence source/model lineage is stale")
        lineage = frozen["preprocess_lineage"]
        if lineage.get("model_version") != MODEL_VERSION or lineage.get("dataset_hashes") != identity["dataset_hashes"]:
            raise ValueError("processed lineage differs from frozen identity")
        if any(lineage.get("artifact_hashes", {}).get(path) != inputs[key] for key, path in (
                ("candidate_evidence", "outputs/task2/candidates.json"), ("grid_regions", "data/processed/grid_regions.parquet"))):
            raise ValueError("processed lineage differs from frozen input hashes")
        json.dumps(frozen, allow_nan=False)
    except (KeyError, TypeError, ValueError) as exc:
        raise CacheIntegrityError("cache frozen input identity or evidence is invalid") from exc
    return identity


def validate_result(result, frozen):
    """Require the response to identify the exact frozen model/settings/datasets."""
    identity = validate_frozen(frozen)
    expected = {"run_id": frozen["run_id"], "model_version": identity["model_version"],
                "config": identity["config"], "seed": identity["config"]["seed"],
                "input_hashes": identity["input_hashes"], "dataset_hashes": identity["dataset_hashes"]}
    if not isinstance(result, dict) or any(result.get(key) != value for key, value in expected.items()):
        raise CacheIntegrityError("cache result does not match frozen run identity")
    if result.get("sources") != frozen["manifest"]["sources"] or source_hashes(result["sources"]) != identity["dataset_hashes"]:
        raise CacheIntegrityError("cache result sources do not match frozen datasets")
    if result.get("scope") != frozen["evidence"].get("scope") or result.get("boundary_exclusions") != frozen["evidence"].get("boundaries"):
        raise CacheIntegrityError("cache result does not match frozen evidence scope")


def artifact_hash(path):
    """Stream checksums so validation does not load simulation arrays into RAM."""
    try:
        with Path(path).open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()
    except OSError as exc:
        raise CacheIntegrityError(f"cache artifact missing: {Path(path).name}") from exc


def seal_cached_run(directory, frozen, *, require_model_artifacts=True):
    """Record hashes only after all expected results and frozen evidence are written."""
    directory = Path(directory)
    validate_frozen(frozen)
    result = read_cache_json(directory / "results.json")
    validate_result(result, frozen)
    artifacts = set(CORE_ARTIFACTS)
    if require_model_artifacts:
        artifacts |= MODEL_ARTIFACTS
        if result.get("scenarios"):
            artifacts |= PLOT_ARTIFACTS
    if (directory / "input_snapshot.json").exists():
        artifacts.add("input_snapshot.json")
    # This integrity record is the final completion marker; partial runs lack it.
    record = {"schema_version": "1.0.0", "run_id": frozen["run_id"],
              "identity_sha256": hashlib.sha256(json.dumps(frozen["identity"], sort_keys=True, allow_nan=False).encode()).hexdigest(),
              "artifact_hashes": {name: artifact_hash(directory / name) for name in sorted(artifacts)}}
    write_json(directory / INTEGRITY_FILE, record)


def load_cached_run(directory, frozen=None, *, require_model_artifacts=True):
    """Verify stored identities, semantic frozen evidence and every recorded hash."""
    directory = Path(directory)
    # Polling uses accepted historical snapshots, not mutable later preprocessing.
    if frozen is None:
        frozen = read_cache_json(directory / "input_snapshot.json")
    identity = validate_frozen(frozen)
    if directory.name != frozen["run_id"]:
        raise CacheIntegrityError("cache directory does not match frozen run ID")
    if read_cache_json(directory / "run_identity.json") != identity:
        raise CacheIntegrityError("cache stored run identity differs from accepted inputs")
    if read_cache_json(directory / "config.json") != identity["config"]:
        raise CacheIntegrityError("cache stored configuration differs from accepted inputs")
    if read_cache_json(directory / "candidate_evidence.json") != frozen["evidence"]:
        raise CacheIntegrityError("cache candidate evidence differs from frozen inputs")
    if (directory / "input_snapshot.json").exists() and read_cache_json(directory / "input_snapshot.json") != frozen:
        raise CacheIntegrityError("cache stored snapshot differs from accepted inputs")
    result = read_cache_json(directory / "results.json")
    validate_result(result, frozen)
    record = read_cache_json(directory / INTEGRITY_FILE)
    expected_digest = hashlib.sha256(json.dumps(identity, sort_keys=True, allow_nan=False).encode()).hexdigest()
    if not isinstance(record, dict) or record.get("schema_version") != "1.0.0" or record.get("run_id") != frozen["run_id"] or record.get("identity_sha256") != expected_digest:
        raise CacheIntegrityError("cache integrity record identifies another run")
    hashes = record.get("artifact_hashes")
    required = set(CORE_ARTIFACTS)
    if require_model_artifacts:
        required |= MODEL_ARTIFACTS
        if result.get("scenarios"):
            required |= PLOT_ARTIFACTS
    if (directory / "input_snapshot.json").exists():
        required.add("input_snapshot.json")
    if not isinstance(hashes, dict) or not required <= set(hashes):
        raise CacheIntegrityError("cache integrity record lacks required artifacts")
    # Reject traversal and links escaping the run; hash all recorded artifacts.
    for name, expected in hashes.items():
        path = directory / name
        if Path(name).name != name or not path.resolve().is_relative_to(directory.resolve()) or not isinstance(expected, str) or not HASH_PATTERN.fullmatch(expected):
            raise CacheIntegrityError("cache artifact hash declaration is invalid")
        if artifact_hash(path) != expected:
            raise CacheIntegrityError(f"cache artifact checksum mismatch: {name}")
    return result
