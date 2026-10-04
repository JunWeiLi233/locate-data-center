"""Read-only external reference comparison of checksum-bound saved model runs."""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from dc_locator.geography.boundary import load_conus_boundary
from dc_locator.geography.sources.ingestion import file_digest
from dc_locator.io import read_parquet_metadata, write_parquet
from dc_locator.model.metrics import json_text
from dc_locator.model.validation.existing_sites import (
    KEYS, RAW_METRICS, compare_county_support, comparison_summary,
)
from dc_locator.paths import project_root
from dc_locator.provenance import DataMode
from dc_locator.regional import owned_output


def _verify_reference_lineage(document, downloads, root):
    """Reconstruct only public listing rows from the verified acquired bytes."""
    from dc_locator.reference_data import NATIONAL_URL, deduplicate_reference_rows, parse_reference_html
    root = Path(root).resolve()
    rows, hashes, summary = [], {}, None
    for entry in sorted(downloads, key=lambda item: item["url"]):
        path = Path(entry["path"])
        path = (root / path).resolve() if not path.is_absolute() else path.resolve()
        if not path.is_relative_to(root):
            raise ValueError("Cleanview cache path escapes project")
        if path.stat().st_size != entry["bytes"] or file_digest(path) != entry["sha256"]:
            raise ValueError("Cleanview public listing cache checksum mismatch")
        parsed = parse_reference_html(path.read_text(encoding="utf-8"), page_url=entry["url"],
                                      retrieved_at=entry["retrieved_at_utc"])
        rows.extend(parsed["rows"])
        if entry["url"] == NATIONAL_URL:
            summary = parsed["summary"]
        hashes[str(path)] = entry["sha256"]
    if summary is None or summary != document.get("summary") or deduplicate_reference_rows(rows) != document.get("rows"):
        raise ValueError("Reference rows/summary do not match acquired public listing bytes")
    return hashes


def _saved_inputs(folder: Path):
    metadata_path = folder / "run_metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    names = ["us_grid_dataset.parquet", "ranked_cells.parquet"]
    hashes = {str(metadata_path): file_digest(metadata_path)}
    frames = []
    for name in names:
        path = folder / name
        sha = metadata.get("output_hashes", {}).get(name)
        if sha is None or file_digest(path) != sha:
            raise ValueError("Saved comparison input is missing or changed: " + str(path))
        table_metadata = read_parquet_metadata(path)
        if table_metadata.get("data_mode") != "real":
            raise ValueError("External real-reference comparison requires a real model run")
        columns = (["grid_id", "grid_definition_id", "data_mode", "county_geoid_all"] if name.startswith("us_grid") else
                   [*KEYS, "grid_definition_id", "data_mode", "rankable", "eligible", "hard_fail",
                    "critical_unknown", "conditional", "mcda_score", "mcda_rank", *RAW_METRICS])
        available = pq.read_schema(path).names
        frame = pd.read_parquet(path, columns=[c for c in columns if c in available])
        if frame.empty:
            raise ValueError("Saved comparison run has no evaluated alternatives or grid cells")
        if name.startswith("us_grid"):
            missing = {"data_mode", "county_geoid_all"} - set(frame)
            if missing:
                catalog_path = folder / "regional_catalog.json"
                catalog_sha = metadata.get("output_hashes", {}).get(catalog_path.name)
                if not catalog_sha or file_digest(catalog_path) != catalog_sha:
                    raise ValueError("Sparse regional grid needs a verified native-part catalog")
                catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
                native = []
                for part in catalog.get("parts", []):
                    part_path = (folder / part["path"] / "us_grid_dataset.parquet").resolve()
                    if not part_path.is_relative_to(folder.resolve()):
                        raise ValueError("Native comparison part escapes saved run")
                    part_sha = part.get("output_hashes", {}).get("us_grid_dataset.parquet")
                    if not part_sha or file_digest(part_path) != part_sha:
                        raise ValueError("Native county-support checksum mismatch")
                    native_metadata = read_parquet_metadata(part_path)
                    if native_metadata.get("data_mode") != "real" or native_metadata.get("grid_definition_id") != table_metadata.get("grid_definition_id"):
                        raise ValueError("Native county-support identity mismatch")
                    native.append(pd.read_parquet(part_path, columns=["grid_id", *sorted(missing)]))
                    hashes[str(part_path)] = part_sha
                if not native:
                    raise ValueError("No native county support in sparse regional run")
                support = pd.concat(native, ignore_index=True)
                if support.grid_id.duplicated().any() or set(support.grid_id) != set(frame.grid_id):
                    raise ValueError("Native county support must match exact evaluated grid")
                frame = frame.merge(support, on="grid_id", validate="one_to_one", sort=False)
                hashes[str(catalog_path)] = catalog_sha
            def county_list(value):
                if not isinstance(value, str) or not re.fullmatch(r"[0-9]{5}(;[0-9]{5})*", value):
                    raise ValueError("Saved grid county support is malformed")
                return value.split(";")
            frame["county_geoid_all"] = frame.county_geoid_all.map(county_list)
        if table_metadata.get("grid_definition_id") != str(frame.grid_definition_id.iloc[0]):
            raise ValueError("Saved table metadata disagrees with geographic identity")
        if set(frame.data_mode) != {"real"}:
            raise ValueError("Saved comparison rows disagree with real table metadata")
        frames.append(frame)
        hashes[str(path)] = sha
    return *frames, metadata, hashes


def write_reference_comparison(reference_path, national_run, output, *, regional_run=None,
                               root=None):
    """Compare public operating samples without changing a saved scientific run."""
    from dc_locator.reference_data import match_counties

    root = Path(root or project_root()).resolve()
    def resolve(path):
        value = Path(path)
        result = (root / value).resolve() if not value.is_absolute() else value.resolve()
        if not result.is_relative_to(root):
            raise ValueError("Comparison inputs must remain in the project")
        return result
    reference_path = resolve(reference_path)
    destination = owned_output(root, output)
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("Comparison output must be a new empty owned folder")
    document = json.loads(reference_path.read_text(encoding="utf-8"))
    if document.get("data_mode") != "real" or not isinstance(document.get("rows"), list):
        raise ValueError("Reference needs explicit real data mode and rows")
    if any(row.get("data_mode") != "real" or row.get("source_id") != "cleanview_reference"
           for row in document["rows"]):
        raise ValueError("Reference rows must retain real Cleanview source identity")
    boundary = load_conus_boundary()
    rows = match_counties(document["rows"], boundary.counties, boundary.states)
    reference = pd.DataFrame(rows)
    if reference.empty:
        raise ValueError("No public operating reference records were acquired")
    hashes = {str(reference_path): file_digest(reference_path)}
    download_log = reference_path.parent / "download_log.json"
    if not download_log.is_file():
        raise ValueError("Acquired Cleanview reference requires its download manifest")
    downloads = json.loads(download_log.read_text(encoding="utf-8"))
    hashes.update(_verify_reference_lineage(document, downloads, root))
    hashes[str(download_log)] = file_digest(download_log)
    comparisons, summaries, identities = {}, {}, {}
    for label, run in [("national", national_run), ("regional", regional_run)]:
        if run is None:
            continue
        folder = resolve(run)
        grid, ranked, metadata, inputs = _saved_inputs(folder)
        comparisons[label] = compare_county_support(reference, grid, ranked)
        summaries[label] = comparison_summary(comparisons[label])
        identities[label] = {"run_id": metadata.get("run_id"), "path": str(folder),
                             "grid_definition_id": str(grid.grid_definition_id.iloc[0])}
        hashes.update(inputs)
    report = {
        "schema_version": "1.0.0", "data_mode": "real",
        "reference_summary": document.get("summary"),
        "reference_selection": "Public largest-operating cards from the national and linked CONUS state pages; planned cards excluded.",
        "comparisons": summaries, "model_runs": identities,
        "administrative_boundary": {"source_id": boundary.source_id, "version": boundary.vintage,
                                    "state_sha256": boundary.state_zip_sha256, "county_sha256": boundary.county_zip_sha256},
        "input_hashes": hashes,
        "interpretation": "These geographic regions deserve further investigation under the stated facility requirements, datasets, constraints, assumptions, and decision preferences.",
        "limitations": [
            "Public card samples do not contain all operating facilities and favor large reported-capacity projects.",
            "Reported capacity is not established as peak IT power, average demand or annual energy; it is not compared as if those boundaries agreed.",
            "County support spans whole intersecting cells; a facility location or point score cannot be inferred.",
            "Existing sites reflect commercial and historical choices; no weights, coefficients or thresholds are calibrated to copy their locations.",
            "Fine-grid absence means uncomputed coverage, never model failure or unsuitable land.",
            "The comparison is post-inspection diagnosis, not an untouched prospective holdout.",
        ],
    }
    destination.mkdir(parents=True)
    for label, frame in comparisons.items():
        write_parquet(frame, destination / (label + "_existing_site_comparison.parquet"),
                      schema_name="ExistingSiteCountyComparison", schema_version="1.0.0",
                      data_mode=DataMode.REAL, grid_definition_id=identities[label]["grid_definition_id"])
        frame.to_csv(destination / (label + "_existing_site_comparison.csv"), index=False)
    (destination / "reference_matched.json").write_text(json_text({"data_mode": "real", "rows": rows}) + "\n", encoding="utf-8")
    (destination / "comparison_report.json").write_text(json_text(report) + "\n", encoding="utf-8")
    lines = ["# Existing data-center comparison", "", report["interpretation"], "",
             "These are investigation areas, not proven buildable parcels.", "",
             "| Evaluated domain | Public reference samples | County-supported | Outside evaluated domain | Unmatched county |",
             "|---|---:|---:|---:|---:|"]
    for label, summary in summaries.items():
        counts = summary["coverage_counts"]
        lines.append(f"| {label} | {summary['reference_facilities']} | {counts.get('COUNTY_SUPPORTED', 0)} | {counts.get('OUTSIDE_EVALUATED_DOMAIN', 0)} | {counts.get('UNMATCHED_COUNTY', 0)} |")
    lines.extend(["", "".join(["- " + item + "\n" for item in report["limitations"]]),
                  "Physical energy, water, carbon, parcel, power-capacity and fiber modules remain externally unvalidated by this source. No classifier accuracy is calculated.", ""])
    (destination / "comparison_report.md").write_text("\n".join(lines), encoding="utf-8")
    modules = ["reference_comparison.py", "reference_data.py", "model/validation/existing_sites.py"]
    code_hashes = {name: file_digest(root / "src/dc_locator" / name) for name in modules}
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True,
                              capture_output=True, text=True).stdout.strip()
    metadata = dict(schema_version="1.0.0", artifact="external_reference_comparison", data_mode="real",
        created_at_utc=datetime.now(timezone.utc).isoformat(), code_revision=revision,
        actual_working_code_sha256=code_hashes, reference_version=document.get("summary", {}).get("version"),
        source_download_manifest=str(download_log), model_runs=identities, input_hashes=hashes,
        output_hashes={path.name: file_digest(path) for path in sorted(destination.iterdir()) if path.is_file()})
    (destination / "run_metadata.json").write_text(json_text(metadata) + "\n", encoding="utf-8")
    return destination
