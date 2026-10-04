"""Human-readable report of one rediscovery analysis (written beside the machine-readable summary)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd


def _pct(value) -> str:
    return "—" if value is None else f"{100 * value:.1f}%"


def write_report(path: Path, summary: dict, candidates: pd.DataFrame) -> None:
    generation = summary["candidate_generation"]
    validation = summary["validation"]
    facilities = summary["facilities"]
    lines = [
        f"# Rediscovery check: {summary['analysis_name']}", "",
        f"> {summary['interpretation']}", "",
        f"> {summary['validation_framing']}", "",
        "## Question", "", summary["research_question"], "",
        "## What was compared", "",
        f"- **Model run:** `{summary['model_run']['model_run']}`, profile `{generation['profile_id']}`, scenario `{generation['scenario_id']}`. "
        f"{generation['cells_valued']:,} of {generation['cells_total']:,} national 1 km cells carry a model score "
        f"(recomposition check: max |Δ| = {generation['verification']['recomposed_score_max_abs_difference']:g}).",
        f"- **Candidates:** Top {generation['top_n_values'][-1]} by score, ties ordered by grid_id, kept at least "
        f"{generation['min_candidate_distance_km']:g} km apart ({generation['distance_method']}). {generation['cells_tied_at_max_score']:,} cells tie at the maximum score "
        f"{generation['max_score']:.3f}. Status: {generation['screening_status']}.",
        f"- **Existing facilities (revealed after generation):** {facilities['source_name']} {facilities['version']} "
        f"(doi:{facilities['doi']}, {facilities['license']}): {facilities['conus_facility_records']:,} CONUS records from "
        f"{facilities['unique_osm_ids']:,} OSM ids.",
        f"- **Blind candidate file:** `candidates_blind.parquet`, sha256 `{summary['candidates_blind_sha256']}`, hashed before the facility inventory was opened.",
        "", "## Hit rates (share of Top-N candidates within r km of an existing facility)", "",
        "| Top N | " + " | ".join(f"≤ {radius:g} km" for radius in validation["hit_radii_km"]) + " |",
        "|---|" + "---|" * len(validation["hit_radii_km"]),
    ]
    by_n: dict[int, dict] = {}
    for row in validation["hit_rates"]:
        by_n.setdefault(row["top_n"], {})[row["radius_km"]] = row["hit_rate"]
    for n, values in by_n.items():
        lines.append(f"| {n} | " + " | ".join(_pct(values.get(radius)) for radius in validation["hit_radii_km"]) + " |")
    ties = validation.get("tie_sensitivity")
    blocks = validation.get("tie_blocks", {})
    if ties:
        lines += ["", f"**Tied scores.** {blocks.get('candidates_in_top_score_block', 0)} of the candidates come from one block of "
                  f"{blocks.get('top_score_block_cells', 0):,} cells that share the maximum score. Their published order follows grid_id, "
                  f"which is deterministic but arbitrary. Repeating the selection over {ties['permutations']} random tie orders gives a mean hit rate, "
                  "with its 2.5–97.5% range:", "",
                  "| Top N | " + " | ".join(f"≤ {radius:g} km" for radius in validation["hit_radii_km"]) + " |",
                  "|---|" + "---|" * len(validation["hit_radii_km"])]
        spread: dict[int, dict] = {}
        for row in ties["hit_rates"]:
            spread.setdefault(row["top_n"], {})[row["radius_km"]] = row
        for n, values in spread.items():
            lines.append(f"| {n} | " + " | ".join(f"{_pct(values[r]['mean'])} ({_pct(values[r]['p2_5'])}–{_pct(values[r]['p97_5'])})"
                                                   for r in validation["hit_radii_km"]) + " |")
    lines += ["", "## Model versus random controls", "",
              "| Control | Top N | Radius | Model | Control mean [95% interval] | Lift | One-sided p |", "|---|---|---|---|---|---|---|"]
    for row in summary["baselines"]["comparison"]:
        lift = "—" if row["lift"] is None else f"{row['lift']:.2f}×"
        lines.append(f"| {row['control_label']} | {row['top_n']} | {row['radius_km']:g} km | {_pct(row['model_hit_rate'])} | "
                     f"{_pct(row['mean'])} [{_pct(row['p2_5'])}, {_pct(row['p97_5'])}] | {lift} | {row['p_value_one_sided']:.3f} |")
    presence = validation["presence_background"]["baseline"]
    if presence.get("auc") is not None:
        lines += ["", "## Where existing facilities sit on the model's score surface", "",
                  f"{presence['occupied_cells_valued']:,} 1 km cells that hold at least one facility have a median score percentile of "
                  f"{presence['median_score_percentile']:.1f}; presence–background AUC = {presence['auc']:.3f} (chance 0.5). "
                  f"{_pct(presence['share_in_top_quartile'])} of occupied cells fall in the model's top quartile.", ""]
        cases = {key: value for key, value in validation["presence_background"].items() if key != "baseline" and value.get("auc") is not None}
        if cases:
            lines.append("Declared weighting cases (deterministic sensitivity, not tuned to facilities): " +
                         "; ".join(f"{case} AUC {value['auc']:.3f}" for case, value in cases.items()) + ".")
    counts = validation["classification"]["counts_by_top_n"]
    lines += ["", "## Classification", "",
              f"validated: nearest facility ≤ {validation['classification']['validated_max_km']:g} km; "
              f"emerging: > {validation['classification']['emerging_min_km']:g} km; otherwise unresolved.", "",
              "| Top N | validated | unresolved | emerging |", "|---|---|---|---|"]
    for n, value in counts.items():
        lines.append(f"| {n} | {value['validated']} | {value['unresolved']} | {value['emerging']} |")
    lines += ["", "An emerging candidate deserves further engineering, economic, regulatory and site-level due diligence; "
              "it is not shown to be suitable for construction.", "", "## Top 10 candidates", "",
              "| Rank | Location | Score | Robustness | Nearest existing facility | Distance | Class |", "|---|---|---|---|---|---|---|"]
    for row in candidates.head(10).itertuples(index=False):
        robustness = "—" if pd.isna(row.robustness_score) else f"{row.robustness_score:.0f} ({row.robustness_method})"
        name = row.nearest_existing_dc_name or row.nearest_existing_dc_operator or row.nearest_existing_dc_id
        tie = f" (tied: score rank {row.score_rank_min}–{row.score_rank_max})" if row.score_rank_max > row.score_rank_min else ""
        lines.append(f"| {row.rank}{tie} | {row.place_label or f'{row.lat:.3f}, {row.lon:.3f}'} | {row.suitability_score:.2f} | {robustness} | "
                     f"{name} ({row.nearest_existing_dc_state}) | {row.distance_to_nearest_existing_dc_km:.1f} km | {row.classification} |")
    lines += ["", "## Limitations", ""] + [f"- {item}" for item in summary["limitations"] + facilities["limitations"]]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
