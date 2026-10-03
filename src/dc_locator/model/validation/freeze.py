"""Create and verify a restorable Phase 6 pre-holdout evaluation freeze."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from dc_locator.model.decision import sha256
from dc_locator.model.metrics import json_text
from dc_locator.model.validation.config import load_phase6_config


def _root() -> Path:
    return Path(__file__).resolve().parents[4]


def _path(root, value):
    target = Path(value)
    return target if target.is_absolute() else root / target


def _software_files(root: Path):
    files = []
    files += [p for p in (root / "src" / "dc_locator").rglob("*.py") if p.is_file()]
    files += [p for p in (root / "configs").rglob("*") if p.is_file() and p.suffix.lower() in {".yaml", ".json"}]
    files += [p for p in (root / "tests").rglob("*.py") if p.is_file()]
    preselection = root / "runs" / "phase6" / "inputs" / "preselection"
    if preselection.is_dir():
        files += [p for p in preselection.glob("*.py") if p.is_file()]
    for path in (
        root / "docs" / "specs" / "phase6.md.txt",
        root / "docs" / "methodology.md",
        root / "docs" / "data_dictionary.md",
        root / "docs" / "data_contracts.md",
        root / "docs" / "limitations.md",
        root / "docs" / "environment.md",
        root / "docs" / "sources.md",
        root / "pyproject.toml",
        root / "requirements.lock.txt",
    ):
        if path.is_file():
            files.append(path)
    return sorted(set(p.resolve() for p in files))


def _input_files(root, config, config_path):
    files = [config_path, _path(root, config.accepted_phase5_record), _path(root, config.preselection_manifest)]
    files += [_path(root, value) for value in config.inputs.values()]
    files += [_path(root, case.profile) for case in config.water_cases]
    files.append(_path(root, config.software_evidence))
    preselection = _path(root, config.preselection_manifest).parent
    files += [p for p in preselection.iterdir() if p.is_file()]
    selection = json.loads(_path(root, config.preselection_manifest).read_text(encoding="utf-8"))
    for section in ("source_files", "source_manifest_files"):
        for record in selection.get(section, {}).values():
            files.append(Path(record["path"]))
    for key in ("baseline_grid_file", "development_grid_file"):
        files.append(Path(selection[key]["path"]))
    files += [root / path for path in selection.get("preserved_master_files", {})]
    unique = sorted(set(path.resolve() for path in files))
    missing = [str(path) for path in unique if not path.is_file() and not path.is_dir()]
    if missing:
        raise FileNotFoundError("Freeze input is missing: " + ", ".join(missing))
    return unique


def _record(root: Path, path: Path):
    if path.is_dir():
        members = sorted(item for item in path.rglob("*") if item.is_file())
        digest = hashlib.sha256()
        total = 0
        for member in members:
            relative = member.relative_to(path).as_posix().encode()
            item_hash = sha256(member).encode()
            digest.update(relative + b"\0" + item_hash + b"\n")
            total += member.stat().st_size
        fingerprint = digest.hexdigest()
        count = len(members)
    else:
        fingerprint = sha256(path)
        total = path.stat().st_size
        count = None
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError:
        relative = str(path)
    return {"path": relative, "sha256": fingerprint, "bytes": total, "directory_member_count": count}


def _copy_snapshot(root: Path, files, snapshot: Path):
    if snapshot.exists():
        raise FileExistsError(f"Freeze snapshot already exists: {snapshot}")
    copied = {}
    for source in files:
        relative = source.relative_to(root)
        target = snapshot / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied[relative.as_posix()] = sha256(target)
    return copied


def _zip_snapshot(snapshot: Path, archive: Path):
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as stream:
        for path in sorted(p for p in snapshot.rglob("*") if p.is_file()):
            info = zipfile.ZipInfo(path.relative_to(snapshot).as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            stream.writestr(info, path.read_bytes())


def create_freeze(config_path="configs/phase6.yaml", output_dir="runs/phase6/freeze/v1"):
    root = _root()
    config_path = _path(root, config_path).resolve()
    config = load_phase6_config(config_path)
    output = _path(root, output_dir).resolve()
    if not output.is_relative_to(root / "runs" / "phase6" / "freeze"):
        raise ValueError("Freeze output must remain under runs/phase6/freeze")
    if output.exists():
        raise FileExistsError("A freeze is immutable; choose a new versioned directory")
    software = _software_files(root)
    inputs = _input_files(root, config, config_path)
    software_records = {path.relative_to(root).as_posix(): _record(root, path) for path in software}
    input_records = {}
    for path in inputs:
        record = _record(root, path)
        input_records[record["path"]] = record
    fingerprint_payload = {
        "evaluation_version": config.evaluation_version,
        "software": {key: item["sha256"] for key, item in software_records.items()},
        "inputs": {key: item["sha256"] for key, item in input_records.items()},
    }
    fingerprint = hashlib.sha256(json_text(fingerprint_payload).encode("utf-8")).hexdigest()
    version_prefix = config.evaluation_version.replace("_", "-")
    freeze_id = f"{version_prefix}-{fingerprint[:16]}"
    output.mkdir(parents=True)
    snapshot = output / "snapshot"
    copied = _copy_snapshot(root, software, snapshot)
    archive = output / "source_config_snapshot.zip"
    _zip_snapshot(snapshot, archive)
    manifest = {
        "schema_version": "1.0.0",
        "status": "FROZEN_BEFORE_HOLDOUT",
        "freeze_id": freeze_id,
        "evaluation_version": config.evaluation_version,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "holdout_feature_evaluation_started": False,
        "fingerprint_sha256": fingerprint,
        "software_files": software_records,
        "input_files": input_records,
        "snapshot_files": copied,
        "snapshot_archive": {"path": archive.relative_to(root).as_posix(), "sha256": sha256(archive), "bytes": archive.stat().st_size},
        "change_policy": "Any model/config/test change after holdout inspection requires a new freeze ID, preserved snapshot, and new result directory.",
    }
    manifest_path = output / "freeze_manifest.json"
    manifest_path.write_text(json_text(manifest) + "\n", encoding="utf-8")
    verify_freeze(manifest_path)
    return manifest


def verify_freeze(manifest_path):
    root = _root()
    path = _path(root, manifest_path).resolve()
    manifest = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "schema_version", "status", "freeze_id", "evaluation_version", "created_at_utc",
        "holdout_feature_evaluation_started", "fingerprint_sha256", "software_files", "input_files",
        "snapshot_files", "snapshot_archive", "change_policy",
    }
    if set(manifest) != required or manifest.get("schema_version") != "1.0.0":
        raise ValueError("Invalid Phase 6 freeze manifest contract")
    if manifest.get("status") != "FROZEN_BEFORE_HOLDOUT" or not manifest.get("freeze_id") or manifest.get("holdout_feature_evaluation_started") is not False:
        raise ValueError("Invalid Phase 6 freeze status/identity")
    if not all(isinstance(manifest.get(section), dict) and manifest[section] for section in ("software_files", "input_files", "snapshot_files")):
        raise ValueError("Freeze requires nonempty software, input, and restorable snapshot records")
    if set(manifest["snapshot_files"]) != set(manifest["software_files"]):
        raise ValueError("Restorable snapshot must contain every frozen software/config/test/document file")
    if any(manifest["snapshot_files"][key] != record["sha256"] for key, record in manifest["software_files"].items()):
        raise ValueError("Snapshot fingerprints differ from frozen software")
    current_inventory = {path.relative_to(root).as_posix() for path in _software_files(root)}
    if current_inventory != set(manifest["software_files"]):
        raise ValueError("Frozen software/config/test/document inventory changed; a new evaluation version is required")
    for section in ("software_files", "input_files"):
        for relative, record in manifest.get(section, {}).items():
            target = Path(record["path"])
            target = target if target.is_absolute() else root / target
            actual = _record(root, target)
            if actual["sha256"] != record["sha256"] or actual["bytes"] != record["bytes"] or actual["directory_member_count"] != record.get("directory_member_count"):
                raise ValueError(f"Frozen {section} mismatch requires a new evaluation version: {relative}")
    snapshot_root = path.parent / "snapshot"
    for relative, fingerprint in manifest.get("snapshot_files", {}).items():
        target = snapshot_root / relative
        if not target.is_file() or sha256(target) != fingerprint:
            raise ValueError(f"Restorable freeze snapshot mismatch: {relative}")
    archive_record = manifest.get("snapshot_archive", {})
    archive = _path(root, archive_record.get("path", ""))
    if not archive.is_file() or sha256(archive) != archive_record.get("sha256") or archive.stat().st_size != archive_record.get("bytes"):
        raise ValueError("Freeze source/config archive is missing or changed")
    fingerprint_payload = {
        "evaluation_version": manifest["evaluation_version"],
        "software": {key: item["sha256"] for key, item in manifest["software_files"].items()},
        "inputs": {key: item["sha256"] for key, item in manifest["input_files"].items()},
    }
    fingerprint = hashlib.sha256(json_text(fingerprint_payload).encode("utf-8")).hexdigest()
    version_prefix = manifest["evaluation_version"].replace("_", "-")
    if fingerprint != manifest.get("fingerprint_sha256") or manifest["freeze_id"] != f"{version_prefix}-{fingerprint[:16]}":
        raise ValueError("Freeze fingerprint/ID is inconsistent")
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/phase6.yaml")
    parser.add_argument("--output-dir", default="runs/phase6/freeze/v1")
    parser.add_argument("--verify")
    args = parser.parse_args(argv)
    result = verify_freeze(args.verify) if args.verify else create_freeze(args.config, args.output_dir)
    print(json_text({"freeze_id": result["freeze_id"], "status": result["status"], "evaluation_version": result["evaluation_version"]}))


if __name__ == "__main__":
    main()


__all__ = ["create_freeze", "verify_freeze"]
