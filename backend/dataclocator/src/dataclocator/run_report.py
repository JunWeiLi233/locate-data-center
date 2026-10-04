"""Standalone technical reports and exportable plots of conditional tradeoffs."""

from pathlib import Path

import numpy as np

from .simulation import OBJECTIVES


def write_run_report(directory: Path, result: dict):
    """Explain all surviving frontier counties and which assumptions can change them."""
    cfg = result["config"]
    scenarios = result["scenarios"]
    baseline = next((s for s in scenarios if s["scenario_id"] == "price01_carbon02"), scenarios[0] if scenarios else None)
    lines = ["# Monte Carlo location tradeoffs", "", f"Run `{result['run_id']}` · model {result['model_version']} · seed {result['seed']}", "",
             "This is an exploratory regional comparison using frozen official data and explicit bounded assumptions. It does not certify a parcel or identify a globally optimal site. No pathway probabilities or preference weights are assigned.", "",
             "## Configuration and uncertainty", "",
             f"Equal workload: {cfg['it_nameplate_mw']:g} MW IT, utilization {cfg['utilization']:g}, {cfg['annual_hours']:g} hours/year. Opening {cfg['opening_year']}, horizon {cfg['analysis_horizon_years']} years. {cfg['simulation_count']:,} draws per separate scenario; {cfg['discount_rate']:.1%} {cfg['currency_convention']} discount rate; 2025 USD base year; end-of-operating-year payments. Physical totals are not discounted.", "",
             f"PUE prior: {cfg['cooling']['pue']}. WUE prior: {cfg['cooling']['wue']}; denominator {cfg['cooling']['wue_basis']} energy; consumption only. The source label records whether assumptions are proposed/unconfirmed. Design parameters are sampled once per future and shared across all counties; they remain constant over operating years within that future.", "",
             f"Dependence model: `{cfg['dependence']}`. Independence is an explicit simplification, with a comonotonic engineering sensitivity supplied separately. No temperature-to-cooling response curve is available, so normals do not create annual variability or county-specific PUE/WUE. Historical price/grid observations are held fixed; their measurement errors are not estimated.", "",
             "Annual price and carbon rates are supplied as separate structural scenarios. Prices start from preliminary 2025 state retail observations, interpreted at a 2025 real-dollar anchor for real scenarios; grid carbon starts at 2023 eGRID average rates. Grid decline is extrapolated across the historical-to-opening gap. Rates are assumptions, not sourced decarbonization forecasts. Explicit zero-rate cases are no-change sensitivity controls.", "",
             "## Promising tradeoffs", ""]
    if baseline is not None:
        rows = sorted([r for r in baseline["candidates"] if r["expected_frontier"]], key=lambda r: r["objectives"][OBJECTIVES[0]]["mean"])
        lines += [f"Under `{baseline['scenario_id']}`, the complete expected frontier contains {len(rows)} counties. Expected and robust frontiers are computed independently; robust objectives use upper-tail CVaR at alpha {cfg['cvar_alpha']:g} with fractional empirical tail mass.", "",
                  "| County | FIPS | Mean electricity NPV, $M | Mean operational carbon, Mt CO2e | Mean direct water, million m³ | Cost CVaR, $M | Carbon CVaR, Mt | Water stress 0–5 | Grid ambiguous | Feasibility |",
                  "|---|---|---:|---:|---:|---:|---:|---:|---|---|"]
        for row in rows:
            cost, carbon, water = [row["objectives"][name] for name in OBJECTIVES]
            stress = row["water_stress_score"]
            stress_text = "unknown" if stress is None else f"{stress:.2f}"
            lines.append(f"| {row['name']}, {row['state_abbr']} | {row['candidate_id']} | {cost['mean']/1e6:.2f} | {carbon['mean']/1e6:.2f} | {water['mean']/1e6:.2f} | {cost['cvar']/1e6:.2f} | {carbon['cvar']/1e6:.2f} | {stress_text} | {'yes' if row['grid_border_or_multiple_subregions'] else 'no'} | {row['feasibility_status']} |")
        lines += ["", "Each frontier county survives because none of the alternatives is no worse in all three modeled objectives. Reading from lower cost to lower carbon:", ""]
        for index, row in enumerate(rows):
            cost, carbon = [row["objectives"][name]["mean"] for name in OBJECTIVES[:2]]
            if index == 0:
                rationale = "It offers the lowest expected electricity cost on this frontier, accepting more operational carbon than the cleaner frontier alternatives."
            else:
                previous = rows[index - 1]
                extra = cost - previous["objectives"][OBJECTIVES[0]]["mean"]
                saved = previous["objectives"][OBJECTIVES[1]]["mean"] - carbon
                rationale = f"Compared with {previous['name']}, it trades approximately ${extra/1e6:.2f}M extra electricity NPV for {saved/1e6:.3f} million fewer modeled tonnes CO2e over the horizon. This is an electricity-only tradeoff, not a project abatement-cost estimate."
            lines.append(f"- **{row['name']}, {row['state_abbr']} ({row['candidate_id']}):** {rationale} Water context: {row['water_stress_label'] or 'unknown'}. Utility rates, actual supplier/grid assignment, region-specific decarbonization and parcel water feasibility could change competitiveness; all local feasibility remains unverified.")
        lines += ["", "![Expected and robust electricity/carbon tradeoffs](frontiers.png)", "",
                  "Direct water is the same across counties under the shared WUE model. Basin stress is retained as context, not multiplied into cubic meters or added as an invented objective. Water allocation and engineering evidence could later change the feasible set or water objective.", "",
                  "In the proposed uniform-rate demo, shared engineering uncertainty multiplies counties in the same way, so Pareto membership can remain identical in every draw. A frontier frequency of 1 means membership in this conditional model; it is not certainty that the county is best or buildable. Frequencies need not sum to one.", ""]
    else:
        lines += ["No candidates satisfy the configured feasibility/coverage requirements. This is a valid output; unknown feasibility is not promoted to approval.", ""]
    lines += ["## Separate structural scenarios", "",
              "| Scenario | Expected frontier FIPS | Robust frontier FIPS |", "|---|---|---|"]
    for scenario in scenarios:
        lines.append(f"| {scenario['scenario_id']} | {', '.join(scenario['expected_frontier_ids'])} | {', '.join(scenario['robust_frontier_ids'])} |")
    lines += ["", "Scenarios are a factorial sensitivity grid, not a probability mixture. Uniform rate changes can shift totals while leaving relative county tradeoffs unchanged. Regional overrides are supported and must carry bounds, units and source labels; none is inferred from the available data.", "",
              "## Sensitivity evidence", "",
              "| Case | Expected frontier FIPS | Robust frontier FIPS |", "|---|---|---|"]
    for case in result["sensitivity_results"]:
        scenario = case["scenarios"][0] if case["scenarios"] else None
        expected = ', '.join(scenario["expected_frontier_ids"]) if scenario else "none"
        robust = ', '.join(scenario["robust_frontier_ids"]) if scenario else "none"
        lines.append(f"| {case['case']} | {expected} | {robust} |")
    # Name alternative frontier counties introduced by tariff or grid sensitivities.
    lines += ["", "Additional competitive counties in sensitivity cases:", ""]
    for case in result["sensitivity_results"]:
        if not case["scenarios"]:
            continue
        case_scenario = case["scenarios"][0]
        frontier = sorted([row for row in case_scenario["candidates"] if row["expected_frontier"]],
                          key=lambda row: row["objectives"][OBJECTIVES[0]]["mean"])
        if baseline is not None and case_scenario["expected_frontier_ids"] == baseline["expected_frontier_ids"]:
            continue
        names = "; ".join(f"{row['name']}, {row['state_abbr']} ({row['candidate_id']})" for row in frontier)
        lines.append(f"- **{case['case']}:** {names}. Ordered by electricity cost; higher-cost members remain competitive by offering lower carbon. This case changes the tariff or mapped carbon anchor, not local feasibility. Stress context: " + "; ".join(f"{row['name']}: {row['water_stress_label'] or 'unknown'}" for row in frontier) + ".")
    lines += ["", "Horizon cases use 20/30 years, compared with the configured main horizon. Commercial retail prices test sector dependence. Grid lower/upper envelopes use minimum/maximum known primary map rates intersecting each county, with no supplier probabilities or area-weighted power mix; EPA's multiple-service overlay may not identify every alternative supplier. Verified-feasibility mode may exclude every candidate until local evidence is supplied. A county with high/arid water stress can be cost/carbon competitive while needing further water due diligence. Connecting plot lines guide the eye; counties remain discrete choices.", "",
              "## Tests and numerical convergence", ""]
    convergence = result["convergence"]
    if convergence:
        max_mean = max((c["max_relative_mean_change"] for c in convergence["checks"]), default=0)
        max_frequency = max((c["max_absolute_frequency_change"] for c in convergence["checks"]), default=0)
        lines += [f"Runs of 1,000, 5,000 and 10,000 draws share seed-stable prefix draws. Predeclared tolerances are less than {cfg['convergence_tolerances']['relative_objective_mean']:.1%} relative change in each objective mean and less than {cfg['convergence_tolerances']['absolute_pareto_frequency']:g} absolute change in frontier frequency, using 10,000 as the numerical reference. Across checks: max mean change {max_mean:.4%}; max frequency change {max_frequency:.4f}; all passed: {convergence['all_passed']}.", "",
                  "Convergence exceptions and near-frontier objective ties remain in the JSON. This establishes numerical stability for the assumed model, not calibration of engineering priors, climate pathways or data-center suitability.", ""]
    lines += [f"Mean-estimator Monte Carlo error uses {cfg['bootstrap_resamples']} bootstrap resamples of shared draw indices. Conditional input uncertainty is shown separately as p05/p95 and CVaR. Frontier-frequency estimator intervals use Wilson 95% bounds, preserving finite uncertainty at observed frequencies zero/one. Structural scenario uncertainty has no probability estimate.", "",
              "Unit/acceptance tests cover dominance, ties, tolerances, fractional CVaR, deterministic collapse, same-seed reproducibility, candidate ordering, draw prefixes, shared draws, dependence behavior, regional overrides, trajectory growth/decline, feasibility exclusion, invalid/missing inputs, physical accounting and frozen offline runs. Executed results are recorded separately in `outputs/task3-tests.xml`.", "",
              "## Reproduction and artifacts", "",
              "```sh", ".venv/bin/python -m dataclocator.cli simulate --config configs/monte-carlo-demo.json",
              ".venv/bin/python -m pytest -q --junitxml=outputs/task3-tests.xml", "```", "",
              "The configuration, model version, raw and processed hashes determine the run ID. `results.json` is written only after artifacts complete. `samples.npz` records draw/candidate/objective arrays in scenario-config order, with candidates sorted by FIPS. `common_draws.npz` freezes shared factors. `annual_trajectories.csv` records conditional annual mean price/carbon paths. Candidate summaries, frontiers, source URLs and every sensitivity config are included in JSON and candidate CSV; plots are standalone PNG and SVG.", "",
              "## Coverage and boundaries", ""]
    lines += [f"- {warning}" for warning in result["warnings"]]
    lines += [f"- {boundary}" for boundary in result["boundary_exclusions"]]
    # Scientific units and county names require stable Unicode output on Windows.
    (directory / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if baseline is not None:
        plot_frontiers(directory, baseline, cfg)


def plot_frontiers(directory: Path, baseline: dict, config: dict):
    """Export scientific plots showing all counties, both frontiers and water ties."""
    # A local noninteractive backend keeps rendering offline and avoids GUI state.
    import os
    os.environ.setdefault("MPLCONFIGDIR", str(directory / "matplotlib-cache"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    rows = baseline["candidates"]
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.8), constrained_layout=True)
    for axis, statistic, flag, title in zip(axes, ["mean", "cvar"], ["expected_frontier", "robust_frontier"], ["Expected outcomes", f"Upper-tail CVaR ({config['cvar_alpha']:.0%})"]):
        cost = np.array([row["objectives"][OBJECTIVES[0]][statistic] / 1e6 for row in rows])
        carbon = np.array([row["objectives"][OBJECTIVES[1]][statistic] / 1e6 for row in rows])
        front = np.array([row[flag] for row in rows], dtype=bool)
        axis.scatter(cost[~front], carbon[~front], s=32, color="#8795a2", alpha=.65, label="Other screened counties")
        axis.scatter(cost[front], carbon[front], s=80, color="#087f8c", label="Pareto frontier", zorder=3)
        order = np.argsort(cost[front])
        axis.plot(cost[front][order], carbon[front][order], color="#087f8c", linewidth=1.2, alpha=.7)
        for index, row in enumerate(rows):
            if front[index]:
                axis.annotate(f"{row['name']} ({row['state_abbr']})", (cost[index], carbon[index]),
                              xytext=(7, 6 + 12 * (index % 2)), textcoords="offset points", fontsize=8)
        axis.set(xlabel="Lifetime electricity NPV (million 2025 USD)", ylabel="Lifetime operational carbon (million tonnes CO2e)", title=title)
        axis.grid(alpha=.16)
        axis.legend(fontsize=8, loc="upper right")
    fig.suptitle(f"{baseline['scenario_id']} · {config['analysis_horizon_years']}-year conditional comparison\nShared WUE gives equal direct water use; all local feasibility remains unverified", fontsize=12)
    fig.savefig(directory / "frontiers.png", dpi=180)
    fig.savefig(directory / "frontiers.svg")
    plt.close(fig)
