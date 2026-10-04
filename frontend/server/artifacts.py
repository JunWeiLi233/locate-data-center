"""Read-only transport for the separately bound cached regional executor."""
from __future__ import annotations

import hashlib
from contextlib import contextmanager
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from .serialization import ADAPTER_VERSION, ApiError, ArtifactReader, file_digest, json_bytes, read_json, regional_catalog


FAST_VERSION = "fixed_cohort_cached_v1"
FAST_GUARDS = {"src/dc_locator/model/enhanced.py"}
FAST_REQUIRED = {"config_snapshot.json", "profile_snapshot.json", "weight_result.json", "screening_summary.json",
    "ranked_cells.parquet", "candidate_regions.parquet", "candidate_regions.geojson", "region_membership.parquet",
    "us_grid_dataset.parquet", "regional_catalog.json", "validation_report.json", "screening_checks.parquet",
    "representative_evidence.parquet", "representative_screening.parquet", "representative_geography.parquet",
    "representative_provenance.parquet"}


def is_fast_run(metadata):
    return isinstance(metadata, dict) and metadata.get("delivery_version") == FAST_VERSION


def cached_cohort_status(root, baseline):
    from dc_locator_fast import cached_cohort_status as status
    return status(root, baseline)


def fast_request_identity(root, baseline, facility):
    from dc_locator_fast import fast_request_identity as identity
    return identity(root, baseline, facility)


def run_cached_evaluation(root, baseline, facility, output):
    """Picklable child-process entry point; all mathematics remains in the executor."""
    from dc_locator_fast import evaluate_cached_regions
    return evaluate_cached_regions(root, baseline, facility, output)


def _inside(root, value):
    path = (root / value).resolve()
    if path == root or not path.is_relative_to(root):
        raise ApiError("Cached artifact path escapes its bound directory", 422, "completed_run_checksum_mismatch")
    return path


def _verify_hashes(folder, hashes, *, required=()):
    if not isinstance(hashes, dict) or not set(required).issubset(hashes):
        raise ApiError("Cached artifact checksum inventory is incomplete", 422, "completed_run_checksum_mismatch")
    for name, expected in sorted(hashes.items()):
        if not isinstance(name, str) or not isinstance(expected, str):
            raise ApiError("Invalid cached artifact checksum inventory", 422, "completed_run_checksum_mismatch")
        path = _inside(folder, name)
        if not path.is_file() or file_digest(path) != expected:
            raise ApiError("Cached artifact checksum mismatch: " + name, 422, "completed_run_checksum_mismatch")


def verify_fast_artifacts(root: Path, folder: Path):
    """Bind fresh outputs and the compact input cache, without loading old physics."""
    root, folder = Path(root).resolve(), Path(folder).resolve()
    _inside(root / "runs", folder)
    try:
        meta = read_json(folder / "run_metadata.json", {})
        if (not is_fast_run(meta) or meta.get("data_mode") != "real" or not meta.get("stage_identity")
                or meta.get("run_id") != "cached_regional__" + meta["stage_identity"][:16]):
            raise ApiError("Invalid cached regional completion metadata", 422, "completed_run_checksum_mismatch")
        hashes = meta.get("output_hashes", {})
        _verify_hashes(folder, hashes, required=FAST_REQUIRED)
        inventory = {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file() and p.name != "run_metadata.json"}
        if set(hashes) != inventory:
            raise ApiError("Cached output inventory differs from completion metadata", 422, "completed_run_checksum_mismatch")
        inputs = meta.get("input_cache", {})
        manifest_path = _inside(root / "data/interim/fast_cached_regions", inputs.get("manifest_path", ""))
        if manifest_path.name != "manifest.json" or not manifest_path.is_file() or file_digest(manifest_path) != inputs.get("manifest_sha256"):
            raise ApiError("Cached input manifest checksum mismatch", 422, "completed_run_checksum_mismatch")
        manifest = read_json(manifest_path, {})
        if (manifest.get("data_mode") != "real" or manifest.get("cache_identity") != inputs.get("cache_identity")
                or manifest.get("output_hashes") != inputs.get("output_hashes")
                or manifest.get("baseline_run_id") != inputs.get("baseline_run_id")
                or manifest.get("source_checksums") != meta.get("source_checksums")
                or manifest.get("method_hashes") != meta.get("actual_working_code_sha256")
                or manifest.get("external_runner_sha256") != meta.get("external_runner_sha256")):
            raise ApiError("Cached input lineage mismatch", 422, "completed_run_checksum_mismatch")
        if "guard_hashes" in manifest or "guard_hashes" in meta:
            guards = meta.get("guard_hashes")
            if not isinstance(guards, dict) or guards != manifest.get("guard_hashes") or set(guards) != FAST_GUARDS:
                raise ApiError("Cached runtime guard binding mismatch", 422, "completed_run_checksum_mismatch")
            try:
                _verify_hashes(root, guards, required=FAST_GUARDS)
            except ApiError as exc:
                raise ApiError("Cached runtime guard content mismatch: " + str(exc), 422, "completed_run_checksum_mismatch") from exc
        _verify_hashes(manifest_path.parent, manifest.get("output_hashes", {}),
                       required={"compact.parquet", "strict_compact.parquet", "carbon.parquet", "geometry.parquet", "screening_checks.parquet"})
        lineage = meta.get("baseline_lineage", {})
        baseline = (root / "runs/cleanview_regional_v2").resolve()
        if Path(lineage.get("path", "")).resolve() != baseline or Path(manifest.get("baseline_path", "")).resolve() != baseline:
            raise ApiError("Cached native baseline path mismatch", 422, "completed_run_checksum_mismatch")
        baseline_meta = read_json(baseline / "run_metadata.json", {})
        sha = file_digest(baseline / "run_metadata.json")
        if (sha != lineage.get("run_metadata_sha256") or sha != manifest.get("baseline_run_metadata_sha256")
                or lineage.get("run_id") != baseline_meta.get("run_id")
                or lineage.get("run_id") != inputs.get("baseline_run_id")):
            raise ApiError("Cached native baseline identity mismatch", 422, "completed_run_checksum_mismatch")
        catalog = regional_catalog(folder)
        scope = meta.get("scope", {})
        if (not catalog or catalog.get("selection") != "fixed_cached_cohort" or catalog.get("cell_size_m") != 1000
                or catalog.get("maximum_region_extent_km") != 20 or catalog.get("refined_cells") != manifest.get("cohort_cells")
                or catalog.get("refined_parent_cells") != manifest.get("parent_windows")
                or meta.get("grid_definition_id") != manifest.get("grid_definition_id")
                or scope.get("kind") != "fixed_cached_national_regional_cohort" or scope.get("data_mode") != "real"
                or scope.get("evaluated_cells") != manifest.get("cohort_cells")):
            raise ApiError("Cached cohort geographic scope mismatch", 422, "completed_run_checksum_mismatch")
        return meta
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise ApiError("Invalid cached regional artifacts: " + str(exc), 422, "completed_run_checksum_mismatch") from exc


class ModelArtifactReader(ArtifactReader):
    """Legacy saved results plus newly evaluated, fixed-cohort cached results."""
    def __init__(self, cache_root, root):
        super().__init__(cache_root)
        self.root = Path(root).resolve()
        self._active_verification = None

    def _fast(self, folder):
        return is_fast_run(read_json(folder / "run_metadata.json", {}))

    @contextmanager
    def _operation(self, folder):
        """Verify each public read once; nested hydration shares only that check."""
        if not self._fast(folder) or (self._active_verification and self._active_verification[0] == folder):
            yield
            return
        previous = self._active_verification
        self._active_verification = (folder, verify_fast_artifacts(self.root, folder))
        try:
            yield
        finally:
            self._active_verification = previous

    def _verified_meta(self, folder):
        if self._active_verification and self._active_verification[0] == folder:
            return self._active_verification[1]
        return verify_fast_artifacts(self.root, folder)

    def run(self, folder, scenario="current"):
        with self._operation(folder):
            return super().run(folder, scenario)

    def run_bytes(self, folder, scenario="current"):
        with self._operation(folder):
            return super().run_bytes(folder, scenario)

    def layer(self, folder, identifier, scenario="current", sublayer=None):
        with self._operation(folder):
            return super().layer(folder, identifier, scenario, sublayer)

    def context(self, folder, scenario):
        if self._fast(folder) and scenario != "current":
            raise ApiError("Cached regional evaluation has no assessed future context", 422, "unsupported_scenario")
        return super().context(folder, scenario)

    def scenarios(self, folder):
        if folder is None or not self._fast(folder):
            return super().scenarios(folder)
        self._verified_meta(folder)
        from .serialization import available_scenarios
        contexts = available_scenarios(None)
        for context in contexts:
            context["available"] = context["id"] == "current"
            context["reason"] = None if context["available"] else "Future contexts were not assessed in this fixed cached cohort evaluation"
        return contexts

    def require_result_artifacts(self, folder, context):
        if self._fast(folder):
            self._verified_meta(folder)
        else:
            super().require_result_artifacts(folder, context)

    def identity(self, folder, context):
        if not self._fast(folder):
            return super().identity(folder, context)
        meta = self._verified_meta(folder)
        signatures = {"run_metadata.json": file_digest(folder / "run_metadata.json"), **meta["output_hashes"]}
        key = (ADAPTER_VERSION, meta["stage_identity"], meta["input_cache"]["manifest_sha256"], tuple(sorted(signatures.items())))
        return key, hashlib.sha256(json_bytes(key)).hexdigest()

    def _regional_representatives(self, folder, catalog, grids):
        if not self._fast(folder):
            return super()._regional_representatives(folder, catalog, grids)
        return [self.table(folder, name, grid_ids=grids) for name in
                ("representative_geography", "representative_provenance", "representative_screening", "representative_evidence")]

    def _serialize_run(self, folder, context, scenario):
        result = super()._serialize_run(folder, context, scenario)
        if not self._fast(folder):
            return result
        catalog = regional_catalog(folder)
        result["analysis_mode"] = "cached_regional"
        result["scope"] = (f"{catalog['refined_cells']} evaluated 1 km cells in {catalog['refined_parent_cells']} fixed cached nationwide regional windows; "
                           "remaining national 1 km cells are unassessed; parent selection was not refreshed.")
        result["analysis"]["diagnostics_status"] = "NOT_ASSESSED"
        result["analysis"].pop("national_fine_surface", None)
        result["decision_brief"] = None
        result["decision_brief_unavailable_reason"] = "Optional sensitivity, rank stability and submission diagnostics were not assessed in this cached evaluation."
        columns = pq.read_schema(folder / "us_grid_dataset.parquet").names
        states = self.table(folder, "us_grid_dataset", columns=["grid_id", "state_abbr_primary"]) if "state_abbr_primary" in columns else pd.DataFrame(columns=["grid_id", "state_abbr_primary"])
        state_by_grid = {str(row.grid_id): {"state_abbr_primary": row.state_abbr_primary}
                         for row in states.itertuples(index=False)}
        regions = self.table(folder, "candidate_regions")
        from .serialization import member_grid_ids, region_states
        states_by_region = {row["region_id"]: region_states(member_grid_ids(row.get("member_grid_ids")), state_by_grid)
                            for row in regions.to_dict("records")}
        for region in result["regions"]:
            region["region_states"] = states_by_region.get(region["region_id"])
            region["sensitivity"] = None
            region["rank_basis"] = "Rank of this representative cell/cooling alternative among all evaluated fixed cached cohort alternatives; no national 1 km optimum claimed."
        return result

    def _layer_part(self, folder, part):
        if not self._fast(folder):
            return super()._layer_part(folder, part)
        meta = self._verified_meta(folder)
        manifest = read_json(Path(meta["input_cache"]["manifest_path"]))
        baseline = self.root / "runs/cleanview_regional_v2"
        batch = _inside(baseline / "parts", baseline / part["path"])
        for name in ("us_grid_dataset.parquet", "feature_provenance.parquet"):
            relative = (batch / name).relative_to(baseline).as_posix()
            expected = manifest.get("baseline_input_hashes", {}).get(relative)
            if not expected or file_digest(batch / name) != expected:
                raise ApiError("Cached native layer checksum mismatch: " + relative, 422, "completed_run_checksum_mismatch")
        return batch

    def _layer_checks(self, folder, layer_folder, grid_ids):
        if not self._fast(folder):
            return super()._layer_checks(folder, layer_folder, grid_ids)
        return self.table(folder, "screening_checks", grid_ids=grid_ids)
