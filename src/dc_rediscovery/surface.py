"""Blind candidate generation from a completed run's national 1 km fine surface.

This module receives no facility input. It uses the model's own decision value
(``dc_locator.model.fine_selection.score_window``) with the run's archived profile, weights and design
constants. The fine surface is the model's evaluation of every CONUS 1 km cell. It is UNSCREENED: parcel,
utility, water, fiber and hazard clearance stay critical unknowns, as they are in EXPLORATORY regional
screening.

Each row group is scored once with ``score_window``. Per-criterion normalized values come from the model's
``normalize_values`` on the same raw quantities. They are accepted only if their weighted sum reproduces
the direct score in every row group, so a candidate's factor breakdown always adds up to the model's own
score.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import yaml
from pyproj import Transformer

from dc_locator.config import GridConfig
from dc_locator.geography.grid import make_grid_id
from dc_locator.geography.sources.ingestion import file_digest
from dc_locator.io import _build_metadata, read_parquet_metadata
from dc_locator.model.fine_selection import COVERAGE, profile_weights, score_window
from dc_locator.model.mcda import hierarchical_weights
from dc_locator.model.metrics import ScoringProfile
from dc_locator.model.normalization import normalize_values
from dc_locator.provenance import DataMode

from .geodesy import greedy_separated_lazy

CELLS = "fine_surface_cells.parquet"
SURFACE_DIR = "national_fine_surface"
SURFACE_MANIFEST = "fine_surface_manifest.json"
SCORE_TOLERANCE = 1e-9
EVALUATED_SCHEMA_VERSION = "1.0.0"


@dataclass
class ModelRun:
    """A completed model run whose archived national fine surface and decision policy are verified."""
    folder: Path
    relative: str
    manifest: dict
    profile: ScoringProfile
    weights: dict[str, float]
    constants: pd.DataFrame
    grid: GridConfig
    weight_cases: list[dict]
    identity: dict


@dataclass
class NationalScores:
    """Compact per-cell arrays in fine-surface order (row-major grid order)."""
    designs: list[str]
    metric_ids: list[str]
    row: np.ndarray
    col: np.ndarray
    area_km2: np.ndarray
    score: np.ndarray
    design: np.ndarray
    normalized: np.ndarray
    case_scores: dict[str, np.ndarray]
    control_masks: dict[str, np.ndarray]
    unscored_reasons: dict[str, int]
    verification: dict
    runtime_seconds: float
    evaluated_cells_path: Path | None = None
    _order: np.ndarray | None = field(default=None, repr=False)

    @property
    def valued(self) -> np.ndarray:
        return np.isfinite(self.score)

    def lookup(self, rows: np.ndarray, cols: np.ndarray) -> np.ndarray:
        """Position of each (row, col) in these arrays, or -1 when the cell is not on the surface."""
        if self._order is None:
            self._order = np.argsort(self._key(self.row, self.col), kind="stable")
        keys = self._key(self.row, self.col)[self._order]
        query = self._key(np.asarray(rows), np.asarray(cols))
        found = np.searchsorted(keys, query)
        found = np.clip(found, 0, len(keys) - 1)
        hit = keys[found] == query
        return np.where(hit, self._order[found], -1)

    @staticmethod
    def _key(row, col):
        return np.asarray(row, dtype=np.int64) * 1_000_000 + np.asarray(col, dtype=np.int64)


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_model_run(root: Path, relative: str) -> ModelRun:
    """Verify and load the archived decision policy and national fine surface of a completed run."""
    folder = (root / relative).resolve()
    if not folder.is_relative_to(root.resolve()):
        raise ValueError("The model run must live inside the project")
    surface = folder / SURFACE_DIR
    manifest = _json(surface / SURFACE_MANIFEST)
    cells = surface / CELLS
    expected = manifest.get("output_hashes", {}).get(CELLS)
    if not expected or not cells.is_file() or file_digest(cells) != expected:
        raise ValueError("National fine surface cells are missing or do not match their manifest checksum")
    metadata = read_parquet_metadata(cells)
    if (metadata.get("schema"), metadata.get("schema_version")) != ("NationalFineSurfaceCell", "1.1.0"):
        raise ValueError("Unsupported national fine surface schema")
    if metadata.get("grid_definition_id") != manifest["grid_definition_id"] or metadata.get("data_mode") != manifest["data_mode"]:
        raise ValueError("National fine surface metadata disagrees with its manifest")
    snapshot_path = folder / "profile_snapshot.json"
    profile = ScoringProfile.model_validate(_json(snapshot_path)["profile"])
    if profile.profile_id != manifest["profile_id"]:
        raise ValueError("The archived profile is not the profile that valued the fine surface")
    weights = profile_weights(profile)
    if set(weights) != set(manifest["weights"]) or any(abs(weights[k] - manifest["weights"][k]) > 1e-12 for k in weights):
        raise ValueError("Resolved profile weights differ from the fine surface manifest")
    config_path = folder / "config_snapshot.json"
    config = _json(config_path)
    grid_path = (root / config["regional"]["grid_config"]).resolve()
    grid = GridConfig.model_validate(yaml.safe_load(grid_path.read_text(encoding="utf-8")))
    if grid.grid_definition_id() != manifest["grid_definition_id"]:
        raise ValueError("The current grid configuration no longer defines the archived fine-surface grid")
    cases = [case for case in config["run"].get("validation", {}).get("cases", []) if case.get("category") == "weights"]
    constants = pd.DataFrame(manifest["design_constants"]).sort_values(["design_id", "scenario_id"]).reset_index(drop=True)
    if constants.scenario_id.nunique() != 1:
        raise ValueError("Exactly one external scenario is required; optimizers never choose a scenario")
    identity = {
        "model_run": relative, "fine_surface_manifest_sha256": file_digest(surface / SURFACE_MANIFEST),
        "fine_surface_cells_sha256": expected, "profile_snapshot_sha256": file_digest(snapshot_path),
        "config_snapshot_sha256": file_digest(config_path), "grid_config": config["regional"]["grid_config"],
        "grid_config_sha256": file_digest(grid_path), "grid_definition_id": manifest["grid_definition_id"],
        "profile_id": profile.profile_id, "stage_identity": manifest.get("stage_identity"),
        "scenario_id": str(constants.scenario_id.iloc[0]), "data_mode": manifest["data_mode"],
    }
    return ModelRun(folder, relative, manifest, profile, weights, constants, grid, cases, identity)


def _raw_metric(features: pd.DataFrame, metric, constant) -> np.ndarray:
    """The same raw quantities ``score_window`` normalizes (performance metrics from design constants)."""
    if metric.column == "c_electricity_tonnes":
        return constant.e_facility_mwh * features.grid_carbon_intensity_kg_per_mwh.to_numpy(dtype=float) / 1000.0
    if metric.column == "w_site_m3":
        return np.full(len(features), float(constant.w_site_m3))
    return features[metric.column].to_numpy(dtype=float)


def cell_centers(grid: GridConfig, row: np.ndarray, col: np.ndarray, transformer: Transformer | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Latitude/longitude of 1 km cell square centres (GRID CONTRACT, EPSG:5070 -> EPSG:4326)."""
    transformer = transformer or Transformer.from_crs("EPSG:5070", "EPSG:4326", always_xy=True)
    x = grid.origin_x_m + (np.asarray(col, dtype=float) + 0.5) * grid.cell_size_m
    y = grid.origin_y_m - (np.asarray(row, dtype=float) + 0.5) * grid.cell_size_m
    lon, lat = transformer.transform(x, y)
    return np.asarray(lat), np.asarray(lon)


def _evaluated_schema(metric_ids: list[str]) -> pa.Schema:
    return pa.schema([pa.field("grid_id", pa.string()), pa.field("row", pa.int32()), pa.field("col", pa.int32()),
                      pa.field("lat", pa.float64()), pa.field("lon", pa.float64()),
                      pa.field("is_boundary_cell", pa.bool_()), pa.field("study_area_intersection_km2", pa.float32()),
                      pa.field("design_id", pa.string()), pa.field("suitability_score", pa.float64()),
                      *[pa.field("factor_" + metric, pa.float32()) for metric in metric_ids],
                      pa.field("grid_carbon_intensity_kg_per_mwh", pa.float32()), pa.field("baseline_water_stress_score", pa.float32()),
                      pa.field("transmission_distance_km", pa.float32()), pa.field("potentially_suitable_land_frac", pa.float32()),
                      pa.field("unscored_reason", pa.string())])


def score_national_surface(run: ModelRun, *, controls: list, evaluated_path: Path | None = None,
                           data_mode: DataMode = DataMode.REAL, progress=print) -> NationalScores:
    """Score every fine-surface cell for the baseline and every declared weight case, streaming row groups."""
    started = time.perf_counter()
    profile = run.profile
    metrics = list(profile.metrics)
    metric_ids = [metric.metric_id for metric in metrics]
    designs = list(run.constants.design_id)
    constants = {row.design_id: row for row in run.constants.itertuples(index=False)}
    case_weights = {case["case_id"]: hierarchical_weights(profile, case["group_weights"]) for case in run.weight_cases}
    reader = pq.ParquetFile(run.folder / SURFACE_DIR / CELLS)
    transformer = Transformer.from_crs("EPSG:5070", "EPSG:4326", always_xy=True)
    writer = None
    if evaluated_path is not None:
        schema = _evaluated_schema(metric_ids).with_metadata(_build_metadata(
            "RediscoveryEvaluatedCell", EVALUATED_SCHEMA_VERSION, data_mode, run.manifest["grid_definition_id"]))
        evaluated_path.parent.mkdir(parents=True, exist_ok=True)
        writer = pq.ParquetWriter(evaluated_path.with_suffix(".parquet.part"), schema, compression="zstd")
    parts: dict[str, list] = {key: [] for key in ("row", "col", "area", "score", "design", "normalized", "parent")}
    case_parts = {case: [] for case in case_weights}
    mask_parts = {control.control_id: [] for control in controls}
    reasons: dict[str, int] = {}
    parents: dict[str, int] = {}
    max_difference, mask_mismatches = 0.0, 0
    try:
        for index in range(reader.num_row_groups):
            features = reader.read_row_group(index).to_pandas()
            count = len(features)
            direct = score_window(features, profile, run.weights, pd.DataFrame(run.constants))
            design_scores, design_normalized = [], []
            for design in designs:
                chosen = direct.loc[direct.design_id.eq(design)]
                if not chosen.index.equals(features.index):
                    raise ValueError("score_window output is not aligned with its input rows")
                reference = chosen.fine_score.to_numpy(dtype=float)
                known = np.isfinite(reference)
                normalized = np.full((count, len(metrics)), np.nan)
                total = np.zeros(count)
                for position, metric in enumerate(metrics):
                    values, _ = normalize_values(_raw_metric(features, metric, constants[design]), metric.reference_low,
                                                 metric.reference_high, metric.direction)
                    values = np.where(known, values, np.nan)
                    normalized[:, position] = values
                    total += run.weights[metric.metric_id] * np.where(known, values, 0.0)
                recomposed = np.where(known, total, np.nan)
                if not np.array_equal(np.isnan(recomposed), ~known) or np.isnan(normalized[known]).any():
                    mask_mismatches += 1
                    raise ValueError("Normalized criteria are unknown where the model scored a cell")
                if known.any():
                    max_difference = max(max_difference, float(np.max(np.abs(recomposed[known] - reference[known]))))
                if max_difference > SCORE_TOLERANCE:
                    raise ValueError(f"Recomposed criteria differ from the model score by {max_difference:g}")
                design_scores.append(reference)
                design_normalized.append(normalized)
                if design == designs[0]:
                    for reason, size in chosen.unscored_reason.dropna().value_counts().items():
                        reasons[reason] = reasons.get(reason, 0) + int(size)
            stacked = np.vstack(design_scores)
            filled = np.where(np.isnan(stacked), -np.inf, stacked)
            best = np.argmax(filled, axis=0)  # first maximum: ties keep the lexically first design
            best_score = filled[best, np.arange(count)]
            valued = np.isfinite(best_score)
            best_score = np.where(valued, best_score, np.nan)
            best_design = np.where(valued, best, -1).astype(np.int8)
            chosen_normalized = np.stack(design_normalized)[best, np.arange(count), :]
            chosen_normalized[~valued] = np.nan
            for case, leaf in case_weights.items():
                case_totals = []
                for normalized in design_normalized:
                    total = np.zeros(count)
                    for position, metric in enumerate(metrics):
                        total += leaf[metric.metric_id] * np.nan_to_num(normalized[:, position], nan=0.0)
                    case_totals.append(np.where(np.isfinite(normalized).all(axis=1), total, -np.inf))
                case_best = np.max(np.vstack(case_totals), axis=0)
                case_parts[case].append(np.where(np.isfinite(case_best), case_best, np.nan))
            for control in controls:
                mask = valued.copy()
                if control.max_transmission_distance_km is not None:
                    mask &= features.transmission_distance_km.to_numpy(dtype=float) <= control.max_transmission_distance_km
                if control.min_suitable_land_frac is not None:
                    mask &= features.potentially_suitable_land_frac.to_numpy(dtype=float) >= control.min_suitable_land_frac
                mask_parts[control.control_id].append(mask)
            rows = features.row.to_numpy(dtype=np.int32)
            cols = features.col.to_numpy(dtype=np.int32)
            parts["row"].append(rows)
            parts["col"].append(cols)
            parts["area"].append(features.study_area_intersection_km2.to_numpy(dtype=np.float32))
            parts["score"].append(best_score)
            parts["design"].append(best_design)
            parts["normalized"].append(chosen_normalized.astype(np.float32))
            parts["parent"].append(np.array([parents.setdefault(parent, len(parents)) for parent in features.parent_grid_id], dtype=np.int32))
            if writer is not None:
                lat, lon = cell_centers(run.grid, rows, cols, transformer)
                design_names = np.array(designs + [None], dtype=object)[np.where(best_design >= 0, best_design, len(designs))]
                reason = direct.loc[direct.design_id.eq(designs[0]), "unscored_reason"].to_numpy(dtype=object)
                table = {"grid_id": features.grid_id.to_numpy(dtype=object), "row": rows, "col": cols, "lat": lat, "lon": lon,
                         "is_boundary_cell": features.is_boundary_cell.to_numpy(dtype=bool),
                         "study_area_intersection_km2": features.study_area_intersection_km2.to_numpy(dtype=np.float32),
                         "design_id": design_names, "suitability_score": best_score,
                         **{"factor_" + metric: chosen_normalized[:, position].astype(np.float32) for position, metric in enumerate(metric_ids)},
                         **{column: features[column].to_numpy(dtype=np.float32) for column in (
                             "grid_carbon_intensity_kg_per_mwh", "baseline_water_stress_score", "transmission_distance_km",
                             "potentially_suitable_land_frac")},
                         "unscored_reason": np.where(valued, None, reason)}
                writer.write_table(pa.Table.from_pydict(table, schema=writer.schema))
            if progress and (index % 10 == 0 or index == reader.num_row_groups - 1):
                progress(f"Scored row group {index + 1}/{reader.num_row_groups} ({time.perf_counter() - started:.0f} s)")
            del features, direct
    finally:
        if writer is not None:
            writer.close()
    if evaluated_path is not None:
        evaluated_path.with_suffix(".parquet.part").replace(evaluated_path)
    reproduction = _parent_reproduction(run, np.concatenate(parts["parent"]), np.concatenate(parts["score"]), parents)
    result = NationalScores(
        designs=designs, metric_ids=metric_ids, row=np.concatenate(parts["row"]), col=np.concatenate(parts["col"]),
        area_km2=np.concatenate(parts["area"]), score=np.concatenate(parts["score"]), design=np.concatenate(parts["design"]),
        normalized=np.concatenate(parts["normalized"]),
        case_scores={case: np.concatenate(values) for case, values in case_parts.items()},
        control_masks={control: np.concatenate(values) for control, values in mask_parts.items()},
        unscored_reasons=dict(sorted(reasons.items())),
        verification={"recomposed_score_max_abs_difference": max_difference, "tolerance": SCORE_TOLERANCE,
                      "unknown_mask_mismatches": mask_mismatches, "row_groups": reader.num_row_groups,
                      "method": "Per-criterion normalize_values on score_window's raw quantities; weighted sum equals score_window's fine_score",
                      "persisted_parent_best_reproduction": reproduction},
        runtime_seconds=round(time.perf_counter() - started, 1), evaluated_cells_path=evaluated_path)
    if result.row.size and (result.row.max() >= 10 ** run.grid.id_row_col_digits or result.col.max() >= 10 ** run.grid.id_row_col_digits):
        raise ValueError("Grid rows/columns exceed the fixed ID width; grid_id order would differ from (row, col) order")
    return result


def _parent_reproduction(run: ModelRun, parent_codes: np.ndarray, scores: np.ndarray, parents: dict[str, int]) -> dict:
    """Compare each 50 km parent's best recomputed score with the run's persisted fine-surface parent summary."""
    path = run.folder / SURFACE_DIR / "fine_surface_parents.parquet"
    expected = run.manifest.get("output_hashes", {}).get(path.name)
    if not expected or not path.is_file() or file_digest(path) != expected:
        return {"status": "not_available", "reason": "No checksum-bound persisted parent summary"}
    persisted = pd.read_parquet(path, columns=["parent_grid_id", "best_fine_score"])
    persisted = persisted.groupby("parent_grid_id").best_fine_score.max()
    frame = pd.DataFrame({"parent": parent_codes, "score": scores})
    mine = frame.groupby("parent").score.max()
    names = {code: name for name, code in parents.items()}
    mine.index = [names[code] for code in mine.index]
    joined = pd.concat([persisted.rename("persisted"), mine.rename("recomputed")], axis=1)
    both = joined.dropna()
    one_sided = int(joined.persisted.isna().ne(joined.recomputed.isna()).sum())
    difference = float((both.persisted - both.recomputed).abs().max()) if len(both) else 0.0
    if one_sided or difference > SCORE_TOLERANCE:
        raise ValueError(f"Recomputed parent best scores differ from the persisted summary (max {difference:g}, {one_sided} one-sided)")
    return {"status": "verified", "parents_compared": int(len(both)), "max_abs_difference": difference,
            "rule": "max over designs of persisted best_fine_score per 50 km parent equals the recomputed parent maximum"}


def ranking_order(scores: np.ndarray, row: np.ndarray, col: np.ndarray) -> np.ndarray:
    """Valued positions by score descending, ties by grid_id. Fixed-width zero-padded IDs sort as (row, col)."""
    valued = np.flatnonzero(np.isfinite(scores))
    return valued[np.lexsort((col[valued], row[valued], -scores[valued]))]


def select_candidates(scores: np.ndarray, national: NationalScores, grid: GridConfig, limit: int,
                      min_distance_km: float) -> np.ndarray:
    """Positions of the separated Top-``limit`` cells (strongest representative of each neighbourhood)."""
    order = ranking_order(scores, national.row, national.col)
    transformer = Transformer.from_crs("EPSG:5070", "EPSG:4326", always_xy=True)

    def coordinates(start, stop):
        positions = order[start:stop]
        return cell_centers(grid, national.row[positions], national.col[positions], transformer)

    kept = greedy_separated_lazy(len(order), coordinates, limit, min_distance_km)
    return order[kept]


def candidate_table(run: ModelRun, national: NationalScores, positions: np.ndarray) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Candidate rows plus long-form factor rows, with raw evidence re-read from the archived surface."""
    grid = run.grid
    digits = grid.id_row_col_digits
    rows, cols = national.row[positions], national.col[positions]
    grid_ids = [make_grid_id(grid.cell_size_m, int(r), int(c), digits) for r, c in zip(rows, cols)]
    evidence = pq.read_table(run.folder / SURFACE_DIR / CELLS, filters=[("grid_id", "in", grid_ids)]).to_pandas()
    evidence = evidence.set_index("grid_id")
    if set(evidence.index) != set(grid_ids):
        raise ValueError("Candidate grid IDs could not be re-read from the archived fine surface")
    lat, lon = cell_centers(grid, rows, cols)
    valued = national.valued
    sorted_scores = np.sort(national.score[valued])
    sorted_normalized = [np.sort(national.normalized[valued, j]) for j in range(len(national.metric_ids))]
    metrics = list(run.profile.metrics)
    metric_by_id = {metric.metric_id: metric for metric in metrics}
    groups = {group["group_id"]: group["label"] for group in run.profile.groups}
    # Exact float64 criteria for the candidates, recomputed from archived raw evidence with the model's
    # normalization (the national arrays are float32 and serve percentiles only).
    ordered = evidence.reindex(grid_ids)
    chosen_designs = [national.designs[int(national.design[position])] for position in positions]
    exact = np.full((len(grid_ids), len(metrics)), np.nan)
    for design in sorted(set(chosen_designs)):
        members = np.flatnonzero(np.asarray(chosen_designs, dtype=object) == design)
        constant = run.constants.loc[run.constants.design_id.eq(design)].iloc[0]
        for j, metric in enumerate(metrics):
            values, _ = normalize_values(_raw_metric(ordered.iloc[members], metric, constant), metric.reference_low,
                                         metric.reference_high, metric.direction)
            exact[members, j] = values
    candidates, factors = [], []
    for rank, (position, grid_id) in enumerate(zip(positions, grid_ids), start=1):
        source = evidence.loc[grid_id]
        if int(source.row) != int(national.row[position]) or int(source.col) != int(national.col[position]):
            raise ValueError("Archived fine-surface evidence does not match the scored cell")
        score = float(national.score[position])
        design = chosen_designs[rank - 1]
        constant = run.constants.loc[run.constants.design_id.eq(design)].iloc[0]
        below = np.searchsorted(sorted_scores, score, side="left")
        ties = np.searchsorted(sorted_scores, score, side="right") - below
        candidates.append({
            "candidate_id": f"{run.relative.rstrip('/').split('/')[-1]}:{grid_id}", "rank": rank, "grid_id": grid_id,
            "row": int(national.row[position]), "col": int(national.col[position]),
            "lat": float(lat[rank - 1]), "lon": float(lon[rank - 1]),
            "coordinate_basis": "1 km cell square centre (EPSG:5070 grid contract) in EPSG:4326",
            "is_boundary_cell": bool(source.is_boundary_cell),
            "study_area_intersection_km2": float(source.study_area_intersection_km2),
            "design_id": design, "scenario_id": str(constant.scenario_id),
            "suitability_score": score, "score_scale": "model decision value 0-100 (fixed-reference normalization, declared weights)",
            "score_percentile": float(100.0 * (below + 0.5 * ties) / len(sorted_scores)),
            "tied_cells_at_score": int(ties),
            "screening_status": "UNSCREENED", "screening_note": "National fine-surface valuation; parcel, utility, water, fiber and hazard clearance remain critical unknowns",
            "profile_id": run.profile.profile_id,
        })
        for j, metric_id in enumerate(national.metric_ids):
            metric = metric_by_id[metric_id]
            normalized = float(exact[rank - 1, j])
            if not np.isfinite(normalized):
                raise ValueError("A ranked candidate has an unknown criterion; ranked cells must be fully known")
            sorted_values = sorted_normalized[j]
            lower = np.searchsorted(sorted_values, np.float32(normalized), side="left")
            equal = np.searchsorted(sorted_values, np.float32(normalized), side="right") - lower
            raw_value, raw_unit, status, source_id, data_year, confidence = _raw_evidence(metric, source, constant)
            factors.append({
                "grid_id": grid_id, "rank": rank, "metric_id": metric_id, "label": metric.definition,
                "group_id": metric.group_id, "group_label": groups.get(metric.group_id),
                "weight": float(run.weights[metric_id]), "normalized_score": normalized,
                "contribution": float(run.weights[metric_id] * normalized),
                "national_percentile": float(100.0 * (lower + 0.5 * equal) / len(sorted_values)),
                "direction": metric.direction, "reference_low": float(metric.reference_low), "reference_high": float(metric.reference_high),
                "raw_value": raw_value, "raw_unit": raw_unit, "value_status": status, "confidence": confidence,
                "source_id": source_id, "data_year": data_year, "role": metric.role,
                "location_dependent": metric.column != "w_site_m3",
                "coverage_frac": _coverage(metric, source),
                "carbon_intensity_kg_per_mwh": float(source.grid_carbon_intensity_kg_per_mwh)
                if metric.column == "c_electricity_tonnes" and pd.notna(source.grid_carbon_intensity_kg_per_mwh) else None,
            })
    candidates = pd.DataFrame(candidates)
    factors = pd.DataFrame(factors)
    totals = factors.groupby("rank").contribution.sum()
    difference = np.abs(totals.to_numpy() - candidates.set_index("rank").suitability_score.reindex(totals.index).to_numpy())
    if (difference > SCORE_TOLERANCE * 1000).any():
        raise ValueError("Candidate factor contributions do not add up to the model score")
    return candidates, factors


def _coverage(metric, source) -> float | None:
    column = COVERAGE.get(metric.column)
    if column is None or column not in source:
        return None
    value = source[column]
    return float(value) if pd.notna(value) else None


def _raw_evidence(metric, source, constant):
    """Raw value, unit, value status, source id, data year and confidence for one factor of one candidate."""
    if metric.column == "c_electricity_tonnes":
        intensity = float(source.grid_carbon_intensity_kg_per_mwh)
        return (float(constant.e_facility_mwh) * intensity / 1000.0, "tonnes_CO2e_per_year", "calculated",
                source.get("grid_carbon_intensity_kg_per_mwh_source_id"), source.get("grid_carbon_intensity_kg_per_mwh_data_year"),
                constant.get("e_facility_mwh_confidence"))
    if metric.column == "w_site_m3":
        return (float(constant.w_site_m3), "m3_consumed_per_year", constant.get("w_site_m3_status") or "calculated",
                None, None, constant.get("w_site_m3_confidence"))
    prefix = metric.column + "_"
    return (float(source[metric.column]) if pd.notna(source[metric.column]) else None, source.get(prefix + "unit"),
            source.get(prefix + "status"), source.get(prefix + "source_id"), source.get(prefix + "data_year"),
            source.get(prefix + "confidence"))
