"""Read-only transport for completed rediscovery analyses (``runs/<name>/rediscovery_manifest.json``).

The bridge never runs the analysis and never computes scores, distances or hit rates. It verifies each
artifact against the analysis manifest's SHA-256 ledger before it serializes anything. A damaged or
incomplete analysis therefore returns an explicit error, not a partial view. Analysis IDs are folder names
under ``runs/`` that match a strict pattern, never arbitrary paths. Responses are cached by manifest
content, so any rerun or edit invalidates them.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
from pathlib import Path

import pandas as pd

from frontend.server.serialization import ApiError, clean, json_bytes

API_SCHEMA_VERSION = "1.0.0"
MANIFEST = "rediscovery_manifest.json"
ANALYSIS_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")
REQUIRED = ("candidates.parquet", "candidate_factors.parquet", "existing_facilities.parquet", "facility_hubs.parquet",
            "validation_summary.json")
FACTOR_FIELDS = ("metric_id", "label", "group_id", "group_label", "weight", "normalized_score", "contribution", "national_percentile",
                 "direction", "reference_low", "reference_high", "raw_value", "raw_unit", "value_status", "confidence", "source_id",
                 "data_year", "role", "location_dependent", "coverage_frac")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class RediscoveryReader:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.runs = self.root / "runs"
        self.lock = threading.RLock()
        self.cache: dict[str, tuple[str, bytes]] = {}

    def _folder(self, analysis_id: str) -> Path:
        if not ANALYSIS_ID.fullmatch(analysis_id or ""):
            raise ApiError("Unknown rediscovery analysis", 404, "rediscovery_not_found")
        folder = (self.runs / analysis_id).resolve()
        if folder.parent != self.runs.resolve() or not (folder / MANIFEST).is_file():
            raise ApiError("Unknown rediscovery analysis", 404, "rediscovery_not_found")
        return folder

    def _manifest(self, folder: Path) -> dict:
        try:
            manifest = json.loads((folder / MANIFEST).read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise ApiError("Rediscovery manifest is unreadable", 422, "rediscovery_invalid") from error
        if manifest.get("schema_version") != "1.0.0" or not isinstance(manifest.get("output_hashes"), dict):
            raise ApiError("Unsupported rediscovery manifest", 422, "rediscovery_invalid")
        return manifest

    def _verify(self, folder: Path, manifest: dict, names) -> None:
        ledger = manifest["output_hashes"]
        for name in names:
            path = folder / name
            if name not in ledger or not path.is_file():
                raise ApiError(f"Rediscovery analysis lacks a required artifact: {name}", 422, "rediscovery_incomplete")
            if _sha256(path) != ledger[name]:
                raise ApiError(f"Rediscovery artifact checksum mismatch: {name}", 422, "rediscovery_checksum_mismatch")

    def index(self) -> dict:
        analyses = []
        if self.runs.is_dir():
            for folder in sorted(path for path in self.runs.iterdir() if path.is_dir() and (path / MANIFEST).is_file()):
                if not ANALYSIS_ID.fullmatch(folder.name):
                    continue
                try:
                    manifest = self._manifest(folder)
                    summary = json.loads((folder / "validation_summary.json").read_text(encoding="utf-8"))
                    analyses.append({"analysis_id": folder.name, "analysis_name": manifest.get("analysis_name"),
                                     "data_mode": manifest.get("data_mode"), "finished_at_utc": manifest.get("timeline", {}).get("finished_at_utc"),
                                     "model_run": manifest.get("model_run", {}).get("model_run"),
                                     "candidates": summary.get("candidate_generation", {}).get("candidates"),
                                     "facility_source": summary.get("facilities", {}).get("source_name"), "available": True, "reason": None})
                except (ApiError, OSError, ValueError) as error:
                    analyses.append({"analysis_id": folder.name, "available": False, "reason": str(error)})
        real = [item for item in analyses if item["available"] and item.get("data_mode") == "real"]
        default = max(real, key=lambda item: item.get("finished_at_utc") or "")["analysis_id"] if real else None
        return {"schema_version": API_SCHEMA_VERSION, "analyses": analyses, "default_analysis_id": default}

    def payload_bytes(self, analysis_id: str) -> bytes:
        folder = self._folder(analysis_id)
        identity = _sha256(folder / MANIFEST)
        with self.lock:
            cached = self.cache.get(analysis_id)
            if cached and cached[0] == identity:
                # Artifacts can change under an unchanged manifest; the ledger is rechecked on every read.
                self._verify(folder, self._manifest(folder), REQUIRED)
                return cached[1]
        body = json_bytes(self._payload(folder, analysis_id))
        with self.lock:
            self.cache[analysis_id] = (identity, body)
            if len(self.cache) > 8:
                self.cache.pop(next(iter(self.cache)))
        return body

    def surface(self, analysis_id: str) -> bytes:
        folder = self._folder(analysis_id)
        manifest = self._manifest(folder)
        self._verify(folder, manifest, ("suitability_surface.png",))
        return (folder / "suitability_surface.png").read_bytes()

    def _payload(self, folder: Path, analysis_id: str) -> dict:
        manifest = self._manifest(folder)
        self._verify(folder, manifest, REQUIRED)
        summary = json.loads((folder / "validation_summary.json").read_text(encoding="utf-8"))
        candidates = pd.read_parquet(folder / "candidates.parquet")
        factors = pd.read_parquet(folder / "candidate_factors.parquet")
        facilities = pd.read_parquet(folder / "existing_facilities.parquet")
        hubs = pd.read_parquet(folder / "facility_hubs.parquet")
        if candidates.empty or candidates["rank"].duplicated().any() or not candidates["rank"].is_monotonic_increasing:
            raise ApiError("Rediscovery candidates are empty or not in rank order", 422, "rediscovery_invalid")
        by_rank = {rank: group for rank, group in factors.groupby("rank", sort=True)}
        radii = summary["validation"]["hit_radii_km"]
        rows = []
        for record in clean(candidates.to_dict("records")):
            details = json.loads(record["robustness_details_json"]) if record.get("robustness_details_json") else None
            factor_rows = by_rank.get(record["rank"])
            rows.append({
                "rank": record["rank"], "candidate_id": record["candidate_id"], "grid_id": record["grid_id"],
                "lat": record["lat"], "lon": record["lon"], "coordinate_basis": record["coordinate_basis"],
                "place_label": record.get("place_label"), "county_name": record.get("county_name"), "state_abbr": record.get("state_abbr"),
                "county_geoid": record.get("county_geoid"), "place_label_basis": record.get("place_label_basis"),
                "design_id": record["design_id"], "scenario_id": record["scenario_id"],
                "suitability_score": record["suitability_score"], "score_percentile": record["score_percentile"],
                "tied_cells_at_score": record["tied_cells_at_score"], "score_rank_min": record["score_rank_min"],
                "score_rank_max": record["score_rank_max"], "top_n_bucket": record["top_n_bucket"],
                "screening_status": record["screening_status"], "screening_note": record["screening_note"],
                "classification": record["classification"], "distance_to_nearest_existing_dc_km": record["distance_to_nearest_existing_dc_km"],
                "nearest_existing_dc": {"facility_id": record["nearest_existing_dc_id"], "name": record["nearest_existing_dc_name"],
                                        "operator": record["nearest_existing_dc_operator"], "county": record["nearest_existing_dc_county"],
                                        "state_abbr": record["nearest_existing_dc_state"], "footprint_type": record["nearest_existing_dc_type"],
                                        "lat": record["nearest_existing_dc_lat"], "lon": record["nearest_existing_dc_lon"]},
                "existing_dc_within_km": {f"{radius:g}": record.get(f"existing_dc_within_{f'{radius:g}'.replace('.', 'p')}km") for radius in radii},
                "robustness": {"score": record["robustness_score"], "status": record["robustness_status"], "provider": record["robustness_provider"],
                               "method": record["robustness_method"], "source": record["robustness_source"],
                               "spatial_support": record["robustness_spatial_support"], "missing_reason": record["robustness_missing_reason"],
                               "details": details},
                "weight_cases": {"retained": record["weight_cases_retained"], "total": record["weight_cases_total"],
                                 "retained_ids": record["weight_cases_retained_ids"]},
                "explanation": record["explanation"], "strengths": record["strengths"], "weaknesses": record["weaknesses"],
                "factors": [] if factor_rows is None else clean(factor_rows[list(FACTOR_FIELDS)].to_dict("records")),
            })
        facility_rows = clean(facilities[["facility_id", "name", "operator", "county", "state_abbr", "lat", "lon", "footprint_type",
                                          "footprint_sqft", "hub_id"]].to_dict("records"))
        hub_rows = clean(hubs.to_dict("records"))
        surface = None
        if "suitability_surface.png" in manifest["output_hashes"] and (folder / "suitability_surface.json").is_file():
            legend = json.loads((folder / "suitability_surface.json").read_text(encoding="utf-8"))
            surface = {"url": f"/api/rediscovery/{analysis_id}/surface.png", **legend}
        generation = summary["candidate_generation"]
        validation = summary["validation"]
        return {
            "schema_version": API_SCHEMA_VERSION, "analysis_id": analysis_id, "analysis_name": summary["analysis_name"],
            "analysis_identity": manifest["analysis_identity"], "data_mode": summary["data_mode"],
            "finished_at_utc": manifest.get("timeline", {}).get("finished_at_utc"), "timeline": manifest.get("timeline"),
            "interpretation": summary["interpretation"], "validation_framing": summary["validation_framing"],
            "research_question": summary["research_question"],
            "model": {**summary["model_run"], **{key: generation[key] for key in (
                "cells_valued", "cells_total", "max_score", "cells_tied_at_max_score", "screening_status", "weights", "profile_id",
                "scenario_id", "designs", "verification", "unscored_reasons")}},
            "parameters": {"top_n_values": generation["top_n_values"], "min_candidate_distance_km": generation["min_candidate_distance_km"],
                           "distance_method": generation["distance_method"], "separation_rule": generation["separation_rule"],
                           "ranking": generation["ranking"], "hit_radii_km": radii,
                           "classification": validation["classification"], "hubs": {key: validation["hubs"][key] for key in ("linkage_km", "min_facilities", "declared")},
                           "baselines": {key: summary["baselines"][key] for key in ("draws", "seed", "area_weighted", "controls", "p_value")}},
            "facility_source": summary["facilities"],
            "results": {"hit_rates": validation["hit_rates"], "tie_sensitivity": validation.get("tie_sensitivity"),
                        "tie_blocks": validation.get("tie_blocks"), "baseline_comparison": summary["baselines"]["comparison"],
                        "presence_background": validation["presence_background"], "facility_recall": validation["facility_recall"],
                        "hub_recall": validation["hubs"]["recall"], "hub_count": validation["hubs"]["count"],
                        "classification_counts": validation["classification"]["counts_by_top_n"],
                        "nearest_distance_quantiles": validation["nearest_distance_km_quantiles_by_top_n"]},
            "robustness": summary["robustness"], "factors": summary["factors"], "explanation_rule": summary["explanation_rule"],
            "places": summary["places"], "candidates": rows, "facilities": facility_rows, "hubs": hub_rows, "surface": surface,
            "limitations": summary["limitations"] + summary["facilities"].get("limitations", []),
            "files": manifest["output_hashes"],
        }
