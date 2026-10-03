"""Deterministic human-readable Phase 6 report rendering."""

from __future__ import annotations


def report_markdown(report, robustness, fixed_regions):
    software = report["software_verification"]
    holdout = report["holdout"]
    lines = [
        "# Phase 6 validation report",
        "",
        f"Evaluation `{report['evaluation_version']}` is bound to freeze `{report['freeze_id']}`.",
        "",
        "## Software verification",
        "",
        f"Status: **{software.get('status', 'UNKNOWN')}**. Tests passed: {software.get('passed', 'not recorded')}; failed: {software.get('failed', 'not recorded')}.",
        "",
        "Software fixtures cover formulas, units, screening, normalization, AHP, Pareto, clustering, scenario indexing, schemas, missing data, ties, invalid geometry, empty results, and unavailable sources. The AHP ratio fixture is a software check; it is not expert preference evidence.",
        "",
        "## Data quality",
        "",
        report["data_quality"]["interpretation"],
        "",
        "## External validation",
        "",
        f"Status: **{report['external_validation']['status']}**. {report['external_validation']['rationale']}",
        "",
        "No overall accuracy is reported. The physical, feasibility, future-water, ranking, and region modules remain externally unvalidated because no independent observations with compatible boundaries were available.",
        "",
        "## Sensitivity and ranking stability",
        "",
        f"The runner recomputed screening, simulation, and decision outputs for {report['sensitivity']['cases']} preregistered cases and retained every alternative, including baseline-dominated alternatives.",
        "",
        f"Top-k overlap ranged from {report['sensitivity']['top_k_overlap_range'][0]} to {report['sensitivity']['top_k_overlap_range'][1]} under the declared exact-k tie policy. Eligibility changed {report['sensitivity']['eligibility_changes_total']} times across case/alternative comparisons.",
        "",
        "Fixed-region summaries retain every accepted baseline member. Min/max use ranked members; the mean is null whenever any member is unranked.",
        "",
        "Ablations remove one complete parent group and assign equal parent weight to each retained group. They do not establish that an omitted criterion is unimportant. Driver attribution covers known retained contributions only.",
        "",
        "## Prospective geographic holdout",
        "",
    ]
    if holdout is None:
        lines.append("Not evaluated in this prefreeze dry run.")
    else:
        lines.extend([
            "The 25-cell block was selected by geometry and cached-source coverage before features or rankings were inspected.",
            "",
            f"It produced {holdout['alternatives']} alternatives, {holdout['rankable']} rankable and {holdout['hard_failures']} hard failures. These are software/data-quality observations, not an accuracy estimate.",
            "",
            "The 10 km versus 20 km comparison uses the same projected footprint, recomputes native aggregations at each resolution, and does not match unlike cell IDs.",
        ])
    lines.extend([
        "",
        "## Inapplicable analyses",
        "",
    ])
    for item in report["inactive_analyses"]:
        lines.append(f"- `{item['module_id']}`: **{item['status']}** — {item['reason']}")
    lines.extend(["", "## Remaining blockers", ""])
    for item in report["remaining_blockers"]:
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


__all__ = ["report_markdown"]

