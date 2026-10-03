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
import yaml
from shapely.geometry import mapping, shape

SCHEMA_VERSION = "1.0.0"
SCOPE = "42 analyzed development cells (dev_tiny); national map context is not analyzed coverage."
ADAPTER_VERSION = "1.0.4"
GROUPS = ("energy_carbon", "water_stewardship", "grid_infrastructure", "land")
FACTOR_LABELS = {"power_carbon": "Power & Carbon", "water": "Water Availability", "land": "Land Impact",
                 "climate": "Climate Risk", "heat_reuse": "Heat Reuse Potential", "community_economic": "Community / Economic"}
EXPORTS = {"ranking": ("ranking.csv", "Authoritative alternative ranking (CSV)"),
           "regions": ("candidate_regions.geojson", "Search region geometry (GeoJSON)"),
           "report": ("recommendation_report.md", "Model recommendation report"),
           "validation": ("validation_report.json", "Current run validation evidence"),
           "sensitivity": ("sensitivity_results.parquet", "Sensitivity evidence (Parquet)"),
           "configuration": ("config_snapshot.json", "Run configuration snapshot")}


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


def read_json(path: Path, fallback=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else fallback


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


def snapshot_configuration(folder: Path) -> dict:
    """Read the actual archived inputs, including inputs of old accepted runs."""
    snapshot = read_json(folder / "config_snapshot.json", {})
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


class ArtifactReader:
    """Bounded memory and durable response caches, bound to actual output identity."""
    def __init__(self, cache_root: Path):
        self.cache_root = cache_root
        self._tables: OrderedDict = OrderedDict()
        self._responses: OrderedDict = OrderedDict()

    def table(self, folder: Path, name: str, *, geo=False):
        path = folder / (name + ".parquet")
        if not path.is_file():
            return gpd.GeoDataFrame() if geo else pd.DataFrame()
        stat = path.stat()
        key = (str(path), stat.st_size, hashlib.sha256(path.read_bytes()).hexdigest(), geo)
        if key not in self._tables:
            frame = gpd.read_parquet(path) if geo else pd.read_parquet(path)
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

    def identity(self, folder: Path, context: Path):
        meta = read_json(folder / "run_metadata.json", {})
        files = [folder / "run_metadata.json", folder / "config_snapshot.json", folder / "feature_provenance.parquet", folder / "us_grid_dataset.parquet",
                 folder / "screening_results.parquet", folder / "screening_summary.json", folder / "alternative_rank_ranges.parquet", folder / "sensitivity_results.parquet"]
        files += [context / n for n in ("candidate_regions.geojson", "candidate_regions.parquet", "ranked_cells.parquet", "profile_snapshot.json", "weight_result.json", "ahp_result.json", "external_scenario.json")]
        signatures = [(str(p), p.stat().st_size, hashlib.sha256(p.read_bytes()).hexdigest()) for p in files if p.is_file()]
        key = (ADAPTER_VERSION, meta.get("stage_identity"), tuple(signatures))
        return key, hashlib.sha256(json_bytes(key)).hexdigest()

    @staticmethod
    def require_result_artifacts(folder: Path, context: Path):
        """A completed result needs present artifacts even when its tables are empty."""
        required = [folder / name for name in ("run_metadata.json", "config_snapshot.json", "us_grid_dataset.parquet",
                    "feature_provenance.parquet", "screening_results.parquet", "screening_summary.json")]
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
            if len(body) < 16 * 1024 * 1024:
                cached.write_bytes(body)
            old = sorted(self.cache_root.glob("*.json"), key=lambda p: p.stat().st_mtime_ns, reverse=True)
            for path in old[24:]:
                path.unlink()
        self._responses[key] = result
        while len(self._responses) > 8:
            self._responses.popitem(last=False)
        return result

    def _serialize_run(self, folder, context, scenario):
        self.require_result_artifacts(folder, context)
        meta = read_json(folder / "run_metadata.json", {})
        regions = self.table(context, "candidate_regions")
        ranked = self.table(context, "ranked_cells")
        provenance = self.table(folder, "feature_provenance")
        screening = self.table(folder, "screening_results")
        ranges = self.table(folder, "alternative_rank_ranges")
        sensitivity = self.table(folder, "sensitivity_results")
        profile_record = read_json(context / "profile_snapshot.json", {})
        profile = profile_record.get("profile", profile_record)
        geography = self.table(folder, "us_grid_dataset")
        geo_rows = {r["grid_id"]: r for r in clean(geography.drop(columns=["geometry"], errors="ignore").to_dict("records"))}
        prov = {(r["grid_id"], r["metric"]): r for r in clean(provenance.to_dict("records"))}
        alternatives = {(r["grid_id"], r["design_id"], r["scenario_id"]): r for r in clean(ranked.to_dict("records"))}
        geometry = {f["properties"]["region_id"]: f.get("geometry") for f in read_json(context / "candidate_regions.geojson", {"features": []})["features"]}
        result_regions, warnings = [], list(meta.get("warnings", []))
        for row in clean(regions.drop(columns=["geometry"], errors="ignore").to_dict("records")):
            key = (row["representative_grid_id"], row["design_id"], row["scenario_id"])
            representative = alternatives.get(key)
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
                       ("potentially_suitable_land_area_km2", "Mapped potentially suitable land area", "land"),
                       ("flood_overlap_frac", "Mapped flood overlap fraction", "climate"),
                       ("wildfire_hazard_potential_whp2023", "Wildfire hazard potential (WHP, not WRC)", "climate"),
                       ("wildfire_burn_probability", "Wildfire burn probability", "climate"),
                       ("temperature_mean_c", "Observed mean annual temperature", "climate")]
            if scenario != "current":
                columns.append((f"aqueduct_{scenario}_water_stress_score", "External context basin water stress", "water"))
            for name, label, group in columns:
                native = prov.get((grid, name), {})
                measures.append(metric(name, label, geo.get(name), group, native, scenario=scenario))
            checks = screening[(screening.grid_id == grid) & (screening.design_id == row["design_id"])] if len(screening) else screening
            unknowns, verification = [], []
            for check in clean(checks.to_dict("records")):
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
            current_range = ranges[(ranges.grid_id == grid) & (ranges.design_id == row["design_id"]) & (ranges.baseline_scenario_id == row["scenario_id"])] if len(ranges) else ranges
            drivers = []
            if len(sensitivity):
                selected = sensitivity[(sensitivity.grid_id == grid) & (sensitivity.design_id == row["design_id"]) & (sensitivity.baseline_scenario_id == row["scenario_id"])]
                drivers = sorted(set(selected.main_driver.dropna().tolist()))
            sense = None
            if len(current_range):
                rr = clean(current_range.iloc[0].to_dict())
                sense = {"base_rank": rr["base_rank"], "min_rank": rr["minimum_rank"], "max_rank": rr["maximum_rank"], "drivers": drivers}
            lat, lon = row.get("centroid_lat"), row.get("centroid_lon")
            centroid = {"lat": lat, "lon": lon} if lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180 else None
            result_regions.append({"region_id": row["region_id"], "label": f"Search region {row['region_id'].removeprefix('region_')[:8]}",
                                   "rank": representative.get("mcda_rank"),
                                   "rank_basis": "Rank of this region's representative cell/cooling alternative within this external scenario; no independent region ranking exists.",
                                   "overall_score": representative.get("mcda_score"), "region_mean_score": row.get("mean_mcda_score"),
                                   "pareto_optimal": representative.get("is_pareto_optimal"), "centroid": centroid, "geometry": geom,
                                   "geometry_warning": geom_warning, "screening_status": status, "design_id": row["design_id"], "scenario_id": row["scenario_id"],
                                   "factors": factors, "raw_metrics": measures, "verification_required": sorted(set(verification)),
                                   "uncertainties": sorted(set(unknowns)), "strengths": [],
                                   "limitations": parse_record(representative.get("warnings_json"), []) + [row.get("interpretation", "Search area; no approved parcel")],
                                   "data_quality": "Unknown; the model has no overall data-quality tier. Critical parcel, power, water and fiber evidence remain unverified; inspect per-metric confidence and provenance.",
                                   "sensitivity": sense})
        result_regions.sort(key=lambda r: (r["rank"] is None, r["rank"] or 0, r["region_id"]))
        weights = read_json(context / "weight_result.json", {})
        ahp = read_json(context / "ahp_result.json", {})
        parent_weights = {g: sum(float(weights.get("weights", {}).get(m["metric_id"], 0)) for m in profile.get("metrics", []) if m["group_id"] == g) for g in GROUPS}
        summary = read_json(folder / "screening_summary.json", {})
        state = "EMPTY" if not result_regions else "PARTIAL" if any(r["screening_status"] != "PASS" for r in result_regions) else "SUCCESS"
        scope = meta.get("scope", {})
        cells = scope.get("geographic_cells", len(geography)) if isinstance(scope, dict) else len(geography)
        stages = [{"label": "Analyzed development cells", "count": cells}, {"label": "Screened cooling alternatives", "count": summary.get("n_alternatives")},
                  {"label": "Eligible alternatives", "count": int(ranked.eligible.sum()) if "eligible" in ranked else None},
                  {"label": "Rankable alternatives", "count": int(ranked.rankable.sum()) if "rankable" in ranked else None},
                  {"label": "Conditional search regions", "count": len(result_regions)}]
        exports = [{"label": label, "url": f"/api/exports/{meta['run_id']}/{identifier}?scenario={scenario}"} for identifier, (filename, label) in EXPORTS.items()
                   if (context / filename).is_file() or ((folder / filename).is_file() and identifier in {"validation", "sensitivity", "configuration"})]
        return clean({"schema_version": SCHEMA_VERSION, "run_id": meta["run_id"], "timestamp": meta.get("created_at_utc"),
                      "model_version": meta.get("delivery_version", "unknown"), "demo": False, "state": state,
                      "scope": f"{cells} analyzed development cells (dev_tiny); national model coverage is unsupported.", "analyzed_cell_count": cells,
                      "configuration": snapshot_configuration(folder), "scenario_id": scenario, "regions": result_regions,
                      "warnings": warnings, "search_stages": stages,
                      "weighting": {"status": ahp.get("status", "NOT_APPLICABLE"), "weights": parent_weights, "consistency_ratio": ahp.get("CR")}, "exports": exports})

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
        sublayer = sublayer or next(iter(choices))
        if sublayer not in choices:
            raise ApiError("Unknown sublayer", 422, "unavailable_layer")
        column, label, unit, direction = choices[sublayer]
        geography = self.table(folder, "us_grid_dataset", geo=True)
        provenance = self.table(folder, "feature_provenance")
        prov = {(r["grid_id"], r["metric"]): r for r in clean(provenance.to_dict("records"))}
        ranked = self.table(context, "ranked_cells")
        checks = self.table(folder, "screening_results")
        features, source_names = [], set()
        for row in geography.to_dict("records"):
            geometry, warning = valid_geometry(mapping(row["geometry"]))
            if geometry is None:
                continue
            grid_id = row["grid_id"]
            alternatives = clean(ranked[ranked.grid_id == grid_id].to_dict("records")) if len(ranked) else []
            statuses = [screening_status(r) for r in alternatives]
            grid_status = next((s for s in ("FAIL", "UNKNOWN", "CONDITIONAL", "PASS") if s in statuses), "UNKNOWN")
            native = prov.get((grid_id, column), {}) if column else {}
            value = clean(row.get(column)) if column else grid_status
            status = native.get("status", "unknown") if column else grid_status
            if column and (status == "unknown" or value is None):
                value, status = None, "unknown"
            if native.get("source_name"):
                source_names.add(native["source_name"])
            cell_checks = clean(checks[checks.grid_id == grid_id].to_dict("records")) if len(checks) else []
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
        warning = "Mapped distance is a proxy; this layer contains analyzed cell polygons, not transmission lines or verified capacity" if identifier == "infrastructure" else "Development subset only; read each cell's status, confidence and provenance"
        return self._layer_payload(identifier, features, label, unit, direction, ", ".join(sorted(source_names)) or "Accepted model screening", warning)

    @staticmethod
    def _layer_payload(identifier, features, label, unit, direction, source_label, warning):
        numeric = [f["properties"]["value"] for f in features if type(f["properties"]["value"]) in (int, float)]
        return clean({"schema_version": SCHEMA_VERSION, "id": identifier, "data": {"type": "FeatureCollection", "features": features},
                      "label": label, "unit": unit, "direction": direction, "min": min(numeric) if numeric else None,
                      "max": max(numeric) if numeric else None, "source": source_label, "warning": warning,
                      "value_property": "value", "status_property": "status"})
