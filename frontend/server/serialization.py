"""Presentation of authoritative model artifacts, without scoring or imputation."""
from __future__ import annotations

import hashlib
import json
import math
from collections import OrderedDict
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import yaml
from shapely.geometry import mapping, shape

SCHEMA_VERSION = "1.8.0"
SCOPE = "No completed real run is loaded; analyzed coverage is unavailable."
ADAPTER_VERSION = "1.8.0"
# Operational transport allowance for completed regional payloads, not a scientific limit.
MAX_DURABLE_RESPONSE_BYTES = 64 * 1024 * 1024
GROUPS = ("energy_carbon", "water_stewardship", "grid_infrastructure", "land")
FACTOR_LABELS = {"power_carbon": "Power & Carbon", "water": "Water Availability", "land": "Land Impact",
                 "climate": "Climate Risk", "heat_reuse": "Heat Reuse Potential", "community_economic": "Community / Economic"}
EXPORTS = {"ranking": ("ranking.csv", "Authoritative alternative ranking (CSV)"),
           "regions": ("candidate_regions.geojson", "Search region geometry (GeoJSON)"),
           "report": ("recommendation_report.md", "Model recommendation report"),
           "validation": ("validation_report.json", "Current run validation evidence"),
           "sensitivity": ("sensitivity_results.parquet", "Sensitivity evidence (Parquet)"),
           "configuration": ("config_snapshot.json", "Run configuration snapshot")}
BRIEF_INPUTS = ("run_metadata.json", "ranked_cells.parquet", "site_performance.parquet", "candidate_regions.parquet",
                "us_grid_dataset.parquet", "screening_results.parquet", "feature_provenance.parquet", "profile_snapshot.json",
                "weight_result.json", "config_snapshot.json", "source_coverage.json", "validation_report.json",
                "regional_catalog.json", "lifecycle_results.parquet")


def build_submission_brief(folder: Path, scenario_id=None):
    """Load the read-only model presentation builder without adding scientific decisions."""
    from dc_locator.submission import build_submission_brief as build
    return build(folder, scenario_id=scenario_id)


def contribution_statements(representative: dict, profile: dict) -> list[str]:
    """Describe persisted score components without deriving scores or choosing a new winner."""
    recorded = parse_record(representative.get("contribution_by_metric_json"))
    statements = []
    for definition in profile.get("metrics", []):
        identifier = definition["metric_id"]
        value = recorded.get(identifier, representative.get("contribution_" + identifier))
        normalized = representative.get(identifier)
        if not isinstance(value, (float, int)) or not math.isfinite(value) or value <= 0:
            continue
        text = f"{definition.get('label') or identifier}: stored contribution {value:g} score points"
        if isinstance(normalized, (float, int)) and math.isfinite(normalized):
            text += f"; stored normalized score {normalized:g}/100"
        caveat = {"grid_infrastructure": "Transmission proximity is a proxy; utility capacity and connection remain unverified.",
                  "land": "Mapped suitable land is a proxy; contiguous parcels and zoning remain unverified.",
                  "water_stewardship": "Water estimates and basin stress do not establish committed water supply.",
                  "energy_carbon": "Historical grid emissions and assumed annual cooling do not establish future or hourly performance."}.get(definition.get("group_id"))
        statements.append(text + (". " + caveat if caveat else "."))
    return statements


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400, code: str = "invalid_request"):
        super().__init__(message)
        self.status, self.code = status, code


def clean(value: Any) -> Any:
    """Convert numeric missing/nonfinite values to strict JSON null, recursively."""
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [clean(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    return value


def json_bytes(value: Any) -> bytes:
    return json.dumps(clean(value), ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")


def grouped_records(frame: pd.DataFrame, columns: tuple[str, ...]) -> dict[tuple, list[dict]]:
    """Index stored evidence once while preserving its original row order."""
    groups = {}
    for record in clean(frame.to_dict("records")):
        key = tuple(record[column] for column in columns)
        # A missing comparison key never matched the previous dataframe filters.
        if any(value is None for value in key):
            continue
        groups.setdefault(key, []).append(record)
    return groups


def read_json(path: Path, fallback=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else fallback


def describe_scope(metadata: dict, cells=None) -> str:
    """Describe archived geographic extent without inferring nationwide source coverage."""
    scope = metadata.get("scope", {})
    scope = scope if isinstance(scope, dict) else {}
    cells = cells if cells is not None else scope.get("geographic_cells")
    extent = scope.get("scope") or metadata.get("configuration", {}).get("study_area")
    if cells is None:
        return "Analyzed geographic coverage is not specified in this run."
    label = "CONUS" if extent == "conus" else extent or "extent not recorded"
    return f"{cells} analyzed cells ({label}); inspect per-metric coverage and unresolved requirements."


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def regional_catalog(folder: Path) -> dict | None:
    catalog = read_json(folder / "regional_catalog.json")
    if catalog is not None and (not isinstance(catalog, dict) or catalog.get("analysis_level") != "regional"):
        raise ApiError("Invalid regional catalog", 422, "invalid_regional_catalog")
    return catalog


def regional_part(folder: Path, relative: str) -> Path:
    target = (folder / relative).resolve()
    if not target.is_relative_to(folder.resolve()) or target == folder.resolve():
        raise ApiError("Regional batch path escapes the run output", 422, "invalid_regional_catalog")
    return target


FINE_SELECTIONS = ("national_fine_surface", "national_fine_region_parents")
FINE_SURFACE_OUTPUTS = {"fine_surface_cells.parquet", "fine_surface_parents.parquet", "feature_provenance.parquet"}


def fine_surface_metadata(folder: Path, catalog: dict) -> dict | None:
    """Read checksum-bound valuation metadata without loading or scoring the surface."""
    if catalog.get("selection") not in FINE_SELECTIONS:
        return None
    record = catalog.get("national_fine_surface")
    if not isinstance(record, dict) or not isinstance(record.get("manifest"), str):
        raise ApiError("National fine surface metadata is missing", 422, "invalid_fine_surface")
    path = regional_part(folder, record["manifest"])
    if not path.is_file():
        raise ApiError("Completed run is missing required result artifacts: " + record["manifest"], 422, "missing_artifact")
    meta = read_json(folder / "run_metadata.json", {})
    expected = meta.get("output_hashes", {}).get(record["manifest"])
    if not expected or file_digest(path) != record.get("manifest_sha256") or expected != record.get("manifest_sha256"):
        raise ApiError("National fine surface manifest checksum mismatch", 422, "completed_run_checksum_mismatch")
    manifest = read_json(path, {})
    if (not manifest.get("stage_identity") or manifest.get("stage_identity") != record.get("stage_identity")
            or manifest.get("method_versions") != record.get("method_versions")
            or manifest.get("cells") != record.get("valued_cells")
            or manifest.get("scored_alternatives") != record.get("scored_alternatives")
            or manifest.get("data_mode") != "real" or manifest.get("cell_size_m") != catalog.get("cell_size_m")
            or manifest.get("grid_definition_id") != catalog.get("grid_definition_id")
            or manifest.get("source_checksums") != meta.get("source_checksums", {})
            or set(manifest.get("output_hashes", {})) != FINE_SURFACE_OUTPUTS):
        raise ApiError("National fine surface lineage mismatch", 422, "invalid_fine_surface")
    missing = [str((path.parent / name).relative_to(folder)) for name in sorted(FINE_SURFACE_OUTPUTS) if not (path.parent / name).is_file()]
    if missing:
        raise ApiError("Completed run is missing required result artifacts: " + ", ".join(missing), 422, "missing_artifact")
    keys = ("manifest", "manifest_sha256", "stage_identity", "method_versions", "valued_cells", "scored_alternatives",
            "ranked_parent_windows", "selection_limit")
    return {**{key: record.get(key) for key in keys}, "screening_status": "UNSCREENED",
            "alternatives": manifest.get("alternatives"), "unscored_alternatives": manifest.get("unscored_alternatives")}


def regional_analysis(catalog: dict, folder: Path | None = None) -> dict:
    keys = ("analysis_level", "parent_run_path", "parent_run_id", "grid_definition_id", "cell_size_m",
            "maximum_region_extent_km", "refined_cells", "national_cells", "shortlisted_parent_cells",
            "refined_parent_cells", "refined_area_km2", "shortlisted_parent_area_km2", "ranking_universe",
            "selection", "coverage_warning", "land_search_scope")
    return {**{key: catalog.get(key) for key in keys},
            "national_fine_surface": fine_surface_metadata(folder, catalog) if folder else None}


def regional_scope(catalog: dict) -> str:
    if catalog.get("selection") == "fixed_cached_cohort":
        return (f"{catalog.get('refined_cells')} evaluated 1 km cells in {catalog.get('refined_parent_cells')} fixed cached nationwide regional windows; "
                "remaining national 1 km cells are unassessed; parent selection was not refreshed.")
    if catalog.get("selection") in FINE_SELECTIONS:
        surface = catalog.get("national_fine_surface", {})
        refined = (f"{catalog.get('refined_parent_cells')} parent windows refined, the best fine-surface parent of each national region. "
                   if catalog.get("selection") == "national_fine_region_parents" else
                   f"{catalog.get('refined_parent_cells')} of {surface.get('ranked_parent_windows')} ranked parent windows refined. ")
        return (f"{surface.get('valued_cells')} national fine cells valued (UNSCREENED); "
                f"{catalog.get('refined_cells')} cells screened and evaluated (partial regional refinement); "
                + refined + (catalog.get("coverage_warning") or "Unselected parent windows remain unrefined."))
    return (f"{catalog.get('refined_cells')} analyzed 1 km cells (partial regional refinement); "
            f"{catalog.get('refined_parent_cells')} of {catalog.get('shortlisted_parent_cells')} shortlisted national parent cells refined. "
            "Inspect refinement area, lineage and per-metric coverage; no national 1 km optimum claimed.")


def available_scenarios(folder: Path | None) -> list[dict]:
    """Advertise contexts only when supported and their required artifacts are present."""
    def complete(context):
        if folder is None:
            return False
        try:
            ArtifactReader.require_result_artifacts(folder, context)
            return True
        except ApiError:
            return False
    current_available = complete(folder)
    result = [{"id": "current", "label": "Current historical-static context", "year": None, "pathway": None,
               "available": current_available, "reason": None if current_available else "No complete output for this run"}]
    for pathway in ("bau", "opt", "pes"):
        for year in (2030, 2040, 2050, 2080):
            identifier = f"{pathway}_{year}"
            context = folder / "future_contexts" / identifier if folder else None
            external = read_json(context / "external_scenario.json", {}) if context else {}
            supported = year != 2040 and external.get("supported") is True and complete(context)
            result.append({"id": identifier, "label": f"{year} · {pathway.upper()} water context", "year": year, "pathway": pathway,
                           "available": supported, "reason": None if supported else "No native 2040 window; no interpolation" if year == 2040 else "No complete supported output for this run"})
    return result


def parse_record(value, fallback=None):
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            pass
    return {} if fallback is None else fallback


def source(record: dict, *, scenario=None, calculation_method=None) -> dict:
    methods = []
    if calculation_method:
        methods.append("Calculation: " + str(calculation_method))
    if record.get("aggregation_method"):
        methods.append("Source spatial aggregation: " + str(record["aggregation_method"]))
    if record.get("method") and record["method"] != calculation_method:
        methods.append("Source method: " + str(record["method"]))
    return clean({"name": record.get("source_name") or record.get("source_id") or "Declared model assumptions",
                  "url": record.get("source_url") or record.get("reference"),
                  "dataset_year": record.get("data_year"), "geography": record.get("geography") or record.get("grid_id"),
                  "resolution": record.get("spatial_resolution"),
                  "method": "; ".join(methods) or None, "scenario": scenario})


def metric(identifier, label, value, group, evidence=None, *, unit=None, scenario=None) -> dict:
    evidence = evidence or {}
    value = clean(value)
    status = evidence.get("status", "unknown")
    if status not in {"observed", "calculated", "scenario", "proxy", "unknown"}:
        status = "unknown"
    if value is None or status == "unknown":
        value, status = None, "unknown"
    native = evidence.get("source_evidence") or evidence
    return {"id": identifier, "label": label, "value": value,
            "unit": unit or evidence.get("unit") or "unknown", "group": group, "status": status,
            "confidence": evidence.get("confidence") or "unknown",
            "missing_reason": (evidence.get("missing_reason") or "Not available in the accepted model outputs") if value is None else None,
            "sources": [source(native, scenario=scenario, calculation_method=evidence.get("method") if evidence.get("source_evidence") else None)]}


def valid_geometry(geometry):
    try:
        geom = shape(geometry)
        if geom.is_empty or not geom.is_valid or geom.geom_type not in {"Polygon", "MultiPolygon"}:
            raise ValueError("empty or invalid polygon")
        west, south, east, north = geom.bounds
        if not all(math.isfinite(v) for v in geom.bounds) or west < -180 or east > 180 or south < -90 or north > 90:
            raise ValueError("coordinates outside EPSG:4326 bounds")
        return clean(mapping(geom)), None
    except Exception as exc:
        return None, f"Region geometry unavailable: {exc}"


def screening_status(row: dict) -> str:
    if row.get("hard_fail") is True:
        return "FAIL"
    if row.get("conditional") is True:
        return "CONDITIONAL"
    if row.get("critical_unknown") is True or row.get("eligible") is not True:
        return "UNKNOWN"
    return "PASS"


def member_grid_ids(value: Any) -> list[str]:
    """Normalize a candidate_regions member_grid_ids cell (JSON string, list or numpy array) to a list of ids."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            return []
    if isinstance(value, (list, tuple, np.ndarray)):
        return [str(v) for v in value]
    return []


def place_label(geo_row: dict | None) -> str | None:
    """Presentation '{county}, {state}' label for a geography row; null if either part is missing or blank.

    Mirrors the geographic_label convention in dc_locator.submission, but never falls back to a
    partial label: both county and state must be present and non-blank.
    """
    county = (geo_row or {}).get("county_name_primary")
    state = (geo_row or {}).get("state_abbr_primary")
    if not isinstance(county, str) or not county.strip() or not isinstance(state, str) or not state.strip():
        return None
    return f"{county}, {state}"


def region_states(ids: list[str], geo_rows: dict) -> list[str] | None:
    """Distinct member-cell state_abbr_primary values, ordered by descending cell count then alphabetically.

    Null (never a partial list) unless every member grid id resolves to a non-blank state in geo_rows.
    """
    if not ids:
        return None
    counts: dict[str, int] = {}
    for grid_id in ids:
        row = geo_rows.get(grid_id)
        state = row.get("state_abbr_primary") if row else None
        if not isinstance(state, str) or not state.strip():
            return None
        counts[state] = counts.get(state, 0) + 1
    return sorted(counts, key=lambda state: (-counts[state], state))


def snapshot_configuration(folder: Path) -> dict:
    """Read the actual archived inputs, including inputs of old accepted runs."""
    snapshot = read_json(folder / "config_snapshot.json", {})
    if read_json(folder / "run_metadata.json", {}).get("delivery_version") == "fixed_cohort_cached_v1":
        # Baseline files record immutable assumption lineage. Submitted and
        # resolved native inputs record this evaluation's actual facility.
        from .service import validate_facility
        try:
            submitted = validate_facility({"facility": snapshot.get("submitted_facility")})
            native = snapshot["facility"]
            run = snapshot["run"]
            expected_designs = ["air_dry_assumed", "cold_plate_tower_assumed"] if submitted["cooling"] == "all" else [submitted["cooling"]]
            if (native.get("peak_it_power_mw") != submitted["peak_it_power_mw"]
                    or not math.isclose(native.get("average_it_load_factor", math.nan) * 100, submitted["average_load_percent"], rel_tol=0, abs_tol=1e-10)
                    or native.get("target_opening_year") != submitted["target_opening_year"]
                    or native.get("operating_lifetime_years") != submitted["lifetime_years"]
                    or native.get("screening_mode") != submitted["screening_mode"]
                    or native.get("cooling_designs") != expected_designs
                    or run.get("screening_mode") != submitted["screening_mode"]
                    or run.get("weighting_method") != submitted["weighting"]):
                raise ApiError("Cached facility configuration differs from the resolved native inputs", 422, "missing_configuration")
            return clean(submitted)
        except (KeyError, TypeError, ValueError) as exc:
            raise ApiError("Invalid cached facility configuration: " + str(exc), 422, "missing_configuration") from exc
    run = snapshot.get("run", {})
    files = snapshot.get("files", {})
    facility_path = run.get("facility", "")
    facility_text = next((v for k, v in files.items() if Path(k).as_posix().endswith(Path(facility_path).as_posix())), None)
    if facility_text is None:
        raise ApiError("The run has no archived facility configuration", 422, "missing_configuration")
    facility = yaml.safe_load(facility_text)["facilities"][0]
    designs = facility.get("cooling_designs") or ([facility["cooling_design_id"]] if facility.get("cooling_design_id") else [])
    profile_record = read_json(folder / "profile_snapshot.json", {})
    profile = profile_record.get("profile", profile_record)
    weights = run.get("user_group_weights") or {g["group_id"]: g.get("equal_parent_weight") for g in profile.get("groups", [])}
    matrix = None
    if run.get("ahp_input"):
        path = Path(run["ahp_input"]).as_posix()
        text = next((v for k, v in files.items() if Path(k).as_posix().endswith(path)), None)
        matrix = json.loads(text)["matrix"] if text else None
    return clean({"peak_it_power_mw": facility["peak_it_power_mw"],
                  "average_load_percent": facility["average_it_load_factor"] * 100,
                  "target_opening_year": facility["target_opening_year"], "lifetime_years": facility["operating_lifetime_years"],
                  "cooling": designs[0] if len(designs) == 1 else "all", "weighting": run.get("weighting_method", "equal"),
                  "screening_mode": run.get("screening_mode", facility["screening_mode"]),
                  "group_weights": weights, "ahp_matrix": matrix})


def snapshot_grid_resolution(folder: Path):
    snapshot = read_json(folder / "config_snapshot.json", {})
    relative = Path(snapshot.get("run", {}).get("grid_config", "")).as_posix()
    text = next((value for key, value in snapshot.get("files", {}).items() if relative and Path(key).as_posix().endswith(relative)), None)
    document = yaml.safe_load(text) if text else {}
    return clean(document.get("cell_size_m")) if isinstance(document, dict) else None


class ArtifactReader:
    """Bounded memory and durable response caches, bound to actual output identity."""
    def __init__(self, cache_root: Path):
        self.cache_root = cache_root
        self._tables: OrderedDict = OrderedDict()
        self._responses: OrderedDict = OrderedDict()

    def table(self, folder: Path, name: str, *, geo=False, grid_ids=None, metric_ids=None, columns=None):
        path = folder / (name + ".parquet")
        if not path.is_file():
            return gpd.GeoDataFrame() if geo else pd.DataFrame()
        stat = path.stat()
        ids = tuple(sorted(set(grid_ids))) if grid_ids is not None else None
        metrics = tuple(sorted(set(metric_ids))) if metric_ids is not None else None
        key = (str(path), stat.st_size, file_digest(path), geo, ids, metrics, tuple(columns) if columns is not None else None)
        if key not in self._tables:
            if ids == ():
                # Arrow cannot compare some typed grid IDs to an empty/null set.
                # The requested domain is empty, so retain the file schema and
                # return zero rows without scanning its potentially large table.
                schema = pq.read_schema(path)
                if columns is not None:
                    schema = pa.schema([schema.field(name) for name in columns], metadata=schema.metadata)
                frame = pa.Table.from_batches([], schema=schema).to_pandas()
                if geo:
                    geometry = gpd.GeoSeries.from_wkb(frame.pop("geometry"), crs=4326)
                    frame = gpd.GeoDataFrame(frame, geometry=geometry, crs=4326)
                return frame
            options = {"filters": [("grid_id", "in", list(ids))]} if ids is not None else {}
            if metrics:
                schema = pq.read_schema(path)
                if "metric" in schema.names and not pa.types.is_null(schema.field("metric").type):
                    options.setdefault("filters", []).append(("metric", "in", list(metrics)))
            if columns is not None:
                options["columns"] = columns
            frame = gpd.read_parquet(path, **options) if geo else pd.read_parquet(path, **options)
            if metrics == ():
                frame = frame.iloc[:0]
            if geo and len(frame):
                frame = frame.to_crs(4326)
            self._tables[key] = frame
            while len(self._tables) > 24:
                self._tables.popitem(last=False)
        self._tables.move_to_end(key)
        return self._tables[key]

    def context(self, folder: Path, scenario: str) -> Path:
        if scenario == "current":
            return folder
        if scenario not in {f"{p}_{y}" for p in ("bau", "opt", "pes") for y in (2030, 2050, 2080)}:
            raise ApiError("Unsupported scenario; 2040 has no native window and is not interpolated", 422, "unsupported_scenario")
        target = folder / "future_contexts" / scenario
        external = read_json(target / "external_scenario.json", {})
        if external.get("supported") is not True:
            raise ApiError("This run has no supported output for the requested external context", 422, "unsupported_scenario")
        return target

    def scenarios(self, folder):
        return available_scenarios(folder)

    def identity(self, folder: Path, context: Path):
        meta = read_json(folder / "run_metadata.json", {})
        files = [folder / "run_metadata.json", folder / "config_snapshot.json", folder / "feature_provenance.parquet", folder / "us_grid_dataset.parquet",
                 folder / "screening_results.parquet", folder / "screening_summary.json", folder / "alternative_rank_ranges.parquet", folder / "sensitivity_results.parquet"]
        files += [context / n for n in ("candidate_regions.geojson", "candidate_regions.parquet", "ranked_cells.parquet", "profile_snapshot.json", "weight_result.json", "ahp_result.json", "external_scenario.json")]
        files += [context / name for name in BRIEF_INPUTS]
        files += [Path(__file__).resolve().parents[2] / "src" / "dc_locator" / name for name in ("submission.py", "submission_rendering.py")]
        catalog = regional_catalog(folder)
        if catalog:
            files.append(folder / "regional_catalog.json")
            if catalog.get("selection") in FINE_SELECTIONS:
                record = fine_surface_metadata(folder, catalog)
                files.append(regional_part(folder, record["manifest"]))
            for part in catalog.get("parts", []):
                batch = regional_part(folder, part["path"])
                files += [batch / name for name in ("us_grid_dataset.parquet", "feature_provenance.parquet", "site_performance.parquet", "screening_results.parquet", "ranked_cells.parquet")]
        signatures = [(str(p), p.stat().st_size, file_digest(p)) for p in sorted(set(files)) if p.is_file()]
        key = (ADAPTER_VERSION, meta.get("stage_identity"), tuple(signatures))
        return key, hashlib.sha256(json_bytes(key)).hexdigest()

    @staticmethod
    def require_result_artifacts(folder: Path, context: Path):
        """A completed result needs present artifacts even when its tables are empty."""
        required = [folder / name for name in ("run_metadata.json", "config_snapshot.json", "screening_summary.json")]
        catalog = regional_catalog(folder)
        if catalog:
            fine_surface_metadata(folder, catalog)
            for part in catalog.get("parts", []):
                batch = regional_part(folder, part["path"])
                required += [batch / name for name in ("us_grid_dataset.parquet", "feature_provenance.parquet", "site_performance.parquet", "screening_results.parquet")]
        else:
            required += [folder / name for name in ("us_grid_dataset.parquet", "feature_provenance.parquet", "screening_results.parquet")]
        required += [context / name for name in ("candidate_regions.parquet", "candidate_regions.geojson", "ranked_cells.parquet",
                                                "profile_snapshot.json", "weight_result.json")]
        missing = [str(path.relative_to(folder)).replace("\\", "/") for path in required if not path.is_file()]
        if missing:
            raise ApiError("Completed run is missing required result artifacts: " + ", ".join(missing), 422, "missing_artifact")

    def run(self, folder: Path, scenario="current") -> dict:
        context = self.context(folder, scenario)
        self.require_result_artifacts(folder, context)
        identity, digest = self.identity(folder, context)
        key = (identity, scenario)
        if key in self._responses:
            self._responses.move_to_end(key)
            return self._responses[key]
        cached = self.cache_root / f"{digest}.json"
        if cached.is_file():
            result = read_json(cached)
        else:
            result = self._serialize_run(folder, context, scenario)
            self.cache_root.mkdir(parents=True, exist_ok=True)
            body = json_bytes(result)
            if len(body) <= MAX_DURABLE_RESPONSE_BYTES:
                cached.write_bytes(body)
            old = sorted(self.cache_root.glob("*.json"), key=lambda p: p.stat().st_mtime_ns, reverse=True)
            for path in old[24:]:
                path.unlink()
        self._responses[key] = result
        while len(self._responses) > 8:
            self._responses.popitem(last=False)
        return result

    def run_bytes(self, folder: Path, scenario="current") -> bytes:
        """Return canonical cached JSON without rebuilding its object tree.

        Required artifacts and their content identity are checked on every read,
        exactly as for ``run``. Response size and retention bounds are unchanged.
        """
        context = self.context(folder, scenario)
        self.require_result_artifacts(folder, context)
        _, digest = self.identity(folder, context)
        cached = self.cache_root / f"{digest}.json"
        if cached.is_file():
            return cached.read_bytes()
        result = self.run(folder, scenario)
        return cached.read_bytes() if cached.is_file() else json_bytes(result)

    def _serialize_run(self, folder, context, scenario):
        self.require_result_artifacts(folder, context)
        meta = read_json(folder / "run_metadata.json", {})
        regions = self.table(context, "candidate_regions")
        catalog = regional_catalog(folder)
        representatives = regions.representative_grid_id.unique().tolist() if len(regions) else []
        ranked = self.table(context, "ranked_cells", grid_ids=representatives) if catalog else self.table(context, "ranked_cells")
        performance = pd.DataFrame()
        if catalog:
            geography, provenance, screening, performance = self._regional_representatives(folder, catalog, representatives)
            counts = self.table(context, "ranked_cells", columns=["eligible", "rankable"])
        else:
            provenance = self.table(folder, "feature_provenance")
            screening = self.table(folder, "screening_results")
            geography = self.table(folder, "us_grid_dataset")
            counts = ranked
        ranges = self.table(folder, "alternative_rank_ranges", grid_ids=representatives if catalog else None)
        sensitivity = self.table(folder, "sensitivity_results", grid_ids=representatives if catalog else None)
        profile_record = read_json(context / "profile_snapshot.json", {})
        profile = profile_record.get("profile", profile_record)
        geo_rows = {r["grid_id"]: r for r in clean(geography.drop(columns=["geometry"], errors="ignore").to_dict("records"))}
        prov = {(r["grid_id"], r["metric"]): r for r in clean(provenance.to_dict("records"))}
        alternatives = {(r["grid_id"], r["design_id"], r["scenario_id"]): r for r in clean(ranked.to_dict("records"))}
        physical_rows = {(r["grid_id"], r["design_id"], r["scenario_id"]): r for r in clean(performance.to_dict("records"))}
        geometry = {f["properties"]["region_id"]: f.get("geometry") for f in read_json(context / "candidate_regions.geojson", {"features": []})["features"]}
        checks_by_alternative = grouped_records(screening, ("grid_id", "design_id"))
        ranges_by_alternative = grouped_records(ranges, ("grid_id", "design_id", "baseline_scenario_id"))
        sensitivity_by_alternative = grouped_records(sensitivity, ("grid_id", "design_id", "baseline_scenario_id"))
        result_regions, warnings = [], list(meta.get("warnings", []))
        for row in clean(regions.drop(columns=["geometry"], errors="ignore").to_dict("records")):
            key = (row["representative_grid_id"], row["design_id"], row["scenario_id"])
            representative = alternatives.get(key)
            if representative is not None and catalog:
                representative = {**physical_rows.get(key, {}), **parse_record(row.get("representative_json")), **representative}
            if representative is None:
                warnings.append(f"{row['region_id']}: representative alternative is missing; scores withheld")
                representative = {}
            # A failed alternative is never promoted by a stored geographic region.
            status = screening_status(representative)
            if status == "FAIL":
                warnings.append(f"{row['region_id']}: excluded because representative has a hard failure")
                continue
            grid = row["representative_grid_id"]
            evidence = parse_record(representative.get("metric_metadata_json"))
            factors = self._factors(representative, profile, prov, grid)
            measures = []
            physical = [("e_it_mwh", "Annual IT electricity", "power_carbon"), ("e_facility_mwh", "Annual facility electricity", "power_carbon"),
                        ("grid_carbon_intensity_kg_per_mwh", "Historical grid carbon intensity", "power_carbon"),
                        ("c_electricity_tonnes", "Annual operational electricity emissions", "power_carbon"),
                        ("pue", "Assumed annual PUE", "power_carbon"), ("peak_facility_demand_mw", "Verified peak facility demand", "power_carbon"),
                        ("w_site_m3", "Annual site water consumption", "water"), ("w_electricity_m3", "Annual generation water consumption", "water"),
                        ("w_site_withdrawal_m3", "Annual site water withdrawal", "water"), ("wue_l_per_kwh", "Assumed WUE", "water")]
            for name, label, group in physical:
                measures.append(metric(name, label, representative.get(name), group, evidence.get(name), scenario=row["scenario_id"]))
            geo = geo_rows.get(grid, {})
            columns = [("baseline_water_stress_score", "Baseline basin water stress", "water"),
                       ("transmission_distance_km", "Mapped transmission distance (capacity unverified)", "power_carbon"),
                       ("potentially_suitable_land_frac", "Mapped potentially suitable land fraction", "land"),
                       ("suitable_land_area_km2", "Mapped potentially suitable land area", "land"),
                       ("flood_overlap_frac", "Mapped flood overlap fraction", "climate"),
                       ("wildfire_hazard_potential_whp2023", "Wildfire hazard potential (WHP, not WRC)", "climate"),
                       ("wildfire_burn_probability", "Wildfire burn probability", "climate"),
                       ("temperature_mean_c", "Observed mean annual temperature", "climate")]
            if scenario != "current":
                columns.append((f"aqueduct_{scenario}_water_stress_score", "External context basin water stress", "water"))
            for name, label, group in columns:
                native = prov.get((grid, name), {})
                measures.append(metric(name, label, geo.get(name), group, native, scenario=scenario))
            checks = checks_by_alternative.get((grid, row["design_id"]), [])
            unknowns, verification = [], []
            for check in checks:
                if check["outcome"] == "UNKNOWN":
                    text = f"{check['requirement']}: {check.get('reason') or check.get('missing_reason') or 'Unknown'}"
                    unknowns.append(text)
                    if check.get("is_critical"):
                        verification.append(text)
                    measures.append(metric(check["metric"], check["requirement"].replace("_", " "), None, "verification",
                                           {"status": "unknown", "confidence": check.get("confidence"), "unit": check.get("unit"), "missing_reason": check.get("missing_reason")}))
            geom, geom_warning = valid_geometry(geometry.get(row["region_id"]))
            if geom_warning:
                warnings.append(f"{row['region_id']}: {geom_warning}")
            current_range = ranges_by_alternative.get(key, [])
            drivers = sorted({item["main_driver"] for item in sensitivity_by_alternative.get(key, [])
                              if item.get("main_driver") is not None})
            sense = None
            if current_range:
                rr = current_range[0]
                sense = {"base_rank": rr["base_rank"], "min_rank": rr["minimum_rank"], "max_rank": rr["maximum_rank"], "drivers": drivers}
            lat, lon = row.get("centroid_lat"), row.get("centroid_lon")
            centroid = {"lat": lat, "lon": lon} if lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180 else None
            result_regions.append({"region_id": row["region_id"], "label": f"Search region {row['region_id'].removeprefix('region_')[:8]}",
                                   "rank": representative.get("mcda_rank"),
                                   "rank_basis": ("Rank of this region's representative cell/cooling alternative among all evaluated refined alternatives; no national 1 km optimum claimed." if catalog else
                                                  "Rank of this region's representative cell/cooling alternative within this external scenario; no independent region ranking exists."),
                                   "overall_score": representative.get("mcda_score"), "region_mean_score": row.get("mean_mcda_score"),
                                   "pareto_optimal": representative.get("is_pareto_optimal"), "centroid": centroid, "geometry": geom,
                                   "geometry_warning": geom_warning, "screening_status": status, "design_id": row["design_id"], "scenario_id": row["scenario_id"],
                                   "representative_grid_id": grid,
                                   "parent_grid_id": self._parent_grid_id(catalog, grid) if catalog else None,
                                   "factors": factors, "raw_metrics": measures, "verification_required": sorted(set(verification)),
                                   "uncertainties": sorted(set(unknowns)), "strengths": contribution_statements(representative, profile) if status != "FAIL" else [],
                                   "limitations": parse_record(representative.get("warnings_json"), []) + [row.get("interpretation", "Search area; no approved parcel")],
                                   "data_quality": "Unknown; the model has no overall data-quality tier. Critical parcel, power, water and fiber evidence remain unverified; inspect per-metric confidence and provenance.",
                                   "sensitivity": sense,
                                   "place_label": place_label(geo),
                                   "region_states": region_states(member_grid_ids(row.get("member_grid_ids")), geo_rows),
                                   "cell_count": row.get("n_cells"), "area_km2": row.get("total_area_km2")})
        result_regions.sort(key=lambda r: (r["rank"] is None, r["rank"] or 0, r["region_id"]))
        weights = read_json(context / "weight_result.json", {})
        ahp = read_json(context / "ahp_result.json", {})
        parent_weights = {g: sum(float(weights.get("weights", {}).get(m["metric_id"], 0)) for m in profile.get("metrics", []) if m["group_id"] == g) for g in GROUPS}
        summary = read_json(folder / "screening_summary.json", {})
        state = "EMPTY" if not result_regions else "PARTIAL" if any(r["screening_status"] != "PASS" for r in result_regions) else "SUCCESS"
        cells = catalog["refined_cells"] if catalog else len(geography)
        stages = [{"label": "Analyzed geographic cells", "count": cells}, {"label": "Screened cooling alternatives", "count": summary.get("n_alternatives")},
                  {"label": "Eligible alternatives", "count": int(counts.eligible.sum()) if "eligible" in counts else None},
                  {"label": "Rankable alternatives", "count": int(counts.rankable.sum()) if "rankable" in counts else None},
                  {"label": "Conditional search regions", "count": len(result_regions)}]
        exports = [{"label": label, "url": f"/api/exports/{meta['run_id']}/{identifier}?scenario={scenario}"} for identifier, (filename, label) in EXPORTS.items()
                   if (context / filename).is_file() or ((folder / filename).is_file() and identifier in {"validation", "sensitivity", "configuration"}) or
                      (identifier == "validation" and (folder / "model_validation_summary.json").is_file())]
        brief, brief_reason = None, None
        if catalog and cells == 0 and not result_regions:
            validation = read_json(folder / "validation_report.json", {})
            recorded_reason = validation.get("reason")
            brief_reason = recorded_reason if isinstance(recorded_reason, str) and recorded_reason else "No fine cells were evaluated; inspect the national discovery lineage."
            if brief_reason not in warnings:
                warnings.append(brief_reason)
        else:
            try:
                brief = build_submission_brief(context)
            except (ValueError, FileNotFoundError) as exc:
                brief_reason = str(exc)
            except ModuleNotFoundError as exc:
                if exc.name != "dc_locator.submission":
                    raise
                brief_reason = "The verified saved-run decision brief builder is unavailable."
        return clean({"schema_version": SCHEMA_VERSION, "run_id": meta["run_id"], "timestamp": meta.get("created_at_utc"),
                      "model_version": meta.get("delivery_version", "unknown"), "demo": False, "state": state,
                      "scope": regional_scope(catalog) if catalog else describe_scope(meta, cells),
                      "analysis": regional_analysis(catalog, folder) if catalog else None,
                      "analysis_resolution_m": catalog.get("cell_size_m") if catalog else snapshot_grid_resolution(folder),
                      "analyzed_cell_count": cells, "scenarios": self.scenarios(folder),
                      "configuration": snapshot_configuration(folder), "scenario_id": scenario, "regions": result_regions,
                      "warnings": warnings, "search_stages": stages,
                      "weighting": {"status": ahp.get("status", "NOT_APPLICABLE"), "weights": parent_weights, "consistency_ratio": ahp.get("CR")}, "exports": exports,
                      "decision_brief": brief, "decision_brief_context_id": scenario, "decision_brief_unavailable_reason": brief_reason})

    @staticmethod
    def _parent_grid_id(catalog, grid):
        relative = catalog.get("representative_parts", {}).get(grid)
        return next((part.get("parent_grid_id") for part in catalog.get("parts", []) if part["path"] == relative), None)

    def _regional_representatives(self, folder, catalog, grids):
        grouped = {}
        allowed = {part["path"] for part in catalog.get("parts", [])}
        for grid in grids:
            relative = catalog.get("representative_parts", {}).get(grid)
            if relative not in allowed:
                raise ApiError("Regional representative has no recorded batch", 422, "invalid_regional_catalog")
            grouped.setdefault(relative, []).append(grid)
        tables = []
        for name in ("us_grid_dataset", "feature_provenance", "screening_results", "site_performance"):
            frames = [self.table(regional_part(folder, relative), name, grid_ids=ids) for relative, ids in sorted(grouped.items())]
            tables.append(pd.concat(frames, ignore_index=True) if frames else pd.DataFrame())
        return tables

    @staticmethod
    def _factors(representative, profile, provenance, grid):
        members = {m["metric_id"]: m for m in profile.get("metrics", [])}
        definitions = {"power_carbon": ["annual_electricity_co2e"], "water": ["annual_site_water_consumption", "local_baseline_water_stress"], "land": ["suitable_land_fraction"]}
        factors = []
        for identifier, label in FACTOR_LABELS.items():
            leaves = definitions.get(identifier, [])
            values = [representative.get(m) for m in leaves]
            score = None
            if leaves and all(v is not None for v in values) and all(m in members for m in leaves):
                # Display accepted parent-group leaves using archived local weights, not a new model rank.
                score = sum(float(v) * float(members[m]["local_weight"]) for m, v in zip(leaves, values))
            native_sources = []
            for m in leaves:
                column = members.get(m, {}).get("column")
                evidence = provenance.get((grid, column)) or parse_record(representative.get("metric_metadata_json")).get(column)
                if evidence:
                    native_sources.append(source(evidence.get("source_evidence") or evidence, scenario=representative.get("scenario_id"),
                                                 calculation_method=evidence.get("method") if evidence.get("source_evidence") else None))
            basis = "Unavailable in accepted scoring profile; no score is inferred" if not leaves else "Stored accepted normalized metric (0–100)"
            if identifier == "water":
                basis = "Presentation aggregation of stored normalized site consumption and basin stress using archived parent-group local weights; no new ranking"
            factors.append({"id": identifier, "label": label, "score": score, "direction": "higher_is_better", "basis": basis, "sources": native_sources})
        return factors

    def layer(self, folder: Path, identifier: str, scenario="current", sublayer=None):
        context = self.context(folder, scenario)
        self.require_result_artifacts(folder, context)
        if identifier == "candidates":
            run = self.run(folder, scenario)
            features = [{"type": "Feature", "id": r["region_id"], "geometry": r["geometry"], "properties": {"region_id": r["region_id"], "label": r["label"], "value": r["overall_score"], "status": r["screening_status"], "rank": r["rank"], "design_id": r["design_id"], "explanations": r["verification_required"]}} for r in run["regions"] if r["geometry"]]
            return self._layer_payload(identifier, features, "Conditional search regions", "score_0_to_100", "higher_is_better", "Accepted representative alternative MCDA score", "Search areas are not approved parcels")
        definitions = {
            "power_carbon": {"carbon_intensity": ("grid_carbon_intensity_kg_per_mwh", "Historical grid carbon intensity", "kg_CO2e_per_mwh", "higher_is_worse")},
            "water": {"water_stress": ("baseline_water_stress_score" if scenario == "current" else f"aqueduct_{scenario}_water_stress_score", "Basin water stress", "score_0_to_5", "higher_is_worse")},
            "land": {"suitable_land": ("potentially_suitable_land_frac", "Potentially suitable land proxy", "frac", "higher_is_better")},
            "climate": {"flood": ("flood_overlap_frac", "Mapped flood overlap", "frac", "higher_is_worse"), "wildfire": ("wildfire_hazard_potential_whp2023", "Wildfire hazard potential (WHP, not WRC)", "WHP_index", "higher_is_worse")},
            "infrastructure": {"transmission_distance": ("transmission_distance_km", "Mapped transmission distance", "km", "neutral")},
            "grid": {"screening": (None, "Analyzed grid screening status", "categorical", "categorical")},
        }
        if identifier not in definitions:
            raise ApiError("Layer is unavailable: no accepted heat reuse or community evidence", 422, "unavailable_layer")
        choices = definitions[identifier]
        catalog = regional_catalog(folder)
        layer_folder = folder
        if catalog:
            indicator, separator, window = (sublayer or "").partition("@")
            if not separator:
                window, indicator = indicator, next(iter(choices))
            if not window:
                raise ApiError("Select a regional search area to inspect its active refinement window", 422, "regional_window_required")
            part = next((p for p in catalog.get("parts", []) if p.get("parent_grid_id") == window), None)
            if part is None:
                regions = self.table(context, "candidate_regions")
                selected = regions[regions.region_id == window] if len(regions) else regions
                if len(selected):
                    relative = catalog.get("representative_parts", {}).get(selected.iloc[0].representative_grid_id)
                    part = next((p for p in catalog.get("parts", []) if p["path"] == relative), None)
            if part is None:
                raise ApiError("Unknown regional refinement window", 422, "unavailable_window")
            if part.get("cell_count", 10001) > 10000:
                raise ApiError("Refinement window exceeds browser layer limit", 422, "layer_budget")
            layer_folder = self._layer_part(folder, part)
            sublayer = indicator
        sublayer = sublayer or next(iter(choices))
        if sublayer not in choices:
            raise ApiError("Unknown sublayer", 422, "unavailable_layer")
        column, label, unit, direction = choices[sublayer]
        geography = self.table(layer_folder, "us_grid_dataset", geo=True)
        if len(geography) > 10000:
            raise ApiError("Analyzed layer exceeds browser feature limit", 422, "layer_budget")
        provenance = self.table(layer_folder, "feature_provenance", metric_ids=[column]) if column else pd.DataFrame()
        prov = {(r["grid_id"], r["metric"]): r for r in clean(provenance.to_dict("records"))}
        ranked = self.table(context, "ranked_cells", grid_ids=geography.grid_id.tolist()) if catalog else self.table(context, "ranked_cells")
        checks = self._layer_checks(folder, layer_folder, geography.grid_id.tolist())
        alternatives_by_cell = grouped_records(ranked, ("grid_id",))
        checks_by_cell = grouped_records(checks, ("grid_id",))
        features, source_names = [], set()
        for row in geography.to_dict("records"):
            geometry, warning = valid_geometry(mapping(row["geometry"]))
            if geometry is None:
                continue
            grid_id = row["grid_id"]
            alternatives = alternatives_by_cell.get((grid_id,), [])
            statuses = [screening_status(r) for r in alternatives]
            grid_status = next((s for s in ("FAIL", "UNKNOWN", "CONDITIONAL", "PASS") if s in statuses), "UNKNOWN")
            native = prov.get((grid_id, column), {}) if column else {}
            value = clean(row.get(column)) if column else grid_status
            status = native.get("status", "unknown") if column else grid_status
            if column and (status == "unknown" or value is None):
                value, status = None, "unknown"
            if native.get("source_name"):
                source_names.add(native["source_name"])
            cell_checks = checks_by_cell.get((grid_id,), [])
            reasons = sorted(set(f"{r['requirement']}: {r.get('reason') or r.get('missing_reason') or r['outcome']}" for r in cell_checks if r["outcome"] == "FAIL"))
            unknowns = sorted(set(f"{r['requirement']}: {r.get('missing_reason') or 'Unknown'}" for r in cell_checks if r["outcome"] == "UNKNOWN"))
            properties = {"grid_id": grid_id, "value": value, "status": status, "unit": native.get("unit") or unit,
                          "confidence": native.get("confidence", "unknown"), "missing_reason": native.get("missing_reason") if column else None,
                          "source": source(native, scenario=scenario) if column else None,
                          "screening_status": grid_status, "reasons": reasons, "unknowns": unknowns,
                          "explanations": reasons + unknowns if column is None else [native.get("method") or "See source provenance"],
                          "alternatives": [{"design_id": r["design_id"], "scenario_id": r["scenario_id"], "screening_status": screening_status(r)} for r in alternatives]}
            features.append({"type": "Feature", "id": grid_id, "geometry": geometry, "properties": properties})
        if column and not any(f["properties"]["value"] is not None for f in features):
            raise ApiError("This indicator has no accepted values in this run/context", 422, "unavailable_layer")
        warning = "Mapped distance is a proxy; this layer contains analyzed cell polygons, not transmission lines or verified capacity" if identifier == "infrastructure" else "Analyzed cells only; metric coverage varies. Read each cell's status, confidence and provenance"
        if catalog:
            warning += "; active refinement window only. Map zoom changes presentation, not the evaluated grid or region extent cap."
        return self._layer_payload(identifier, features, label, unit, direction, ", ".join(sorted(source_names)) or "Accepted model screening", warning)

    def _layer_part(self, folder, part):
        return regional_part(folder, part["path"])

    def _layer_checks(self, folder, layer_folder, grid_ids):
        return self.table(layer_folder, "screening_results")

    @staticmethod
    def _layer_payload(identifier, features, label, unit, direction, source_label, warning):
        numeric = [f["properties"]["value"] for f in features if type(f["properties"]["value"]) in (int, float)]
        return clean({"schema_version": SCHEMA_VERSION, "id": identifier, "data": {"type": "FeatureCollection", "features": features},
                      "label": label, "unit": unit, "direction": direction, "min": min(numeric) if numeric else None,
                      "max": max(numeric) if numeric else None, "source": source_label, "warning": warning,
                      "value_property": "value", "status_property": "status"})
