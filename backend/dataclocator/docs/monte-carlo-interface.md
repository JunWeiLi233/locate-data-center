# Monte Carlo configuration and JSON interface

The Python/CLI interface works offline. HTTP endpoints and a frontend have not been implemented in this task.

```sh
export PYTHONPATH=src
.venv/bin/python -m dataclocator.cli simulate --config configs/monte-carlo-demo.json
```

Use `--skip-convergence` or `--skip-sensitivity` only for a quick debugging run; the normal handoff includes both. `--no-cache` recomputes an identical run. Complete artifacts live under a run ID derived from configuration, source/processed hashes, audit flags and model version. Completion requires a valid `cache_integrity.json` binding the result, frozen evidence, identity, configuration and simulation artifacts; `results.json` alone is not sufficient. Derived inputs require the committed `outputs/task2/preprocess_manifest.json` to match the current source/model/selection identity and artifact checksums. Legacy, stale or damaged caches fail explicitly rather than being rebound.

## Configuration

Every setting is explicit, with no default PUE/WUE or future rate. Copy the demo config and replace source labels with engineering evidence or confirmed assumptions. Demo workload, 2027 opening, 25-year horizon, 5% real discount rate and triangular priors are proposed demonstration choices, not measured site performance.

| Field | Required interpretation |
|---|---|
| it_nameplate_mw / utilization / annual_hours | Equal workload across every county; finite validated values |
| opening_year / analysis_horizon_years | Opening 2025–2050; 1–40 consecutive operating years |
| base_currency / base_year | Current anchor supports USD, 2025 only |
| currency_convention / discount_rate | Real or nominal prices and matching rate; end-year monetary discounting; no physical discounting |
| cooling.pue | Fixed or triangular prior, bounds/mode, dimensionless units and source; PUE ≥ 1 |
| cooling.wue | Fixed or triangular prior, bounds/mode, L/kWh units and source |
| cooling.wue_basis / water_definition | IT or facility energy denominator; consumption only |
| dependence | `shared_independent_engineering` explicitly simplifies dependence; `shared_comonotonic_engineering` couples engineering quantiles as a sensitivity |
| scenario_set | 1–12 separate structural scenarios, no mixture weights; each has id, description, price_growth, carbon_decline, regional_overrides |
| price_growth / carbon_decline | Priors with fraction/year units; rates are assumed, anchored to 2025 price / 2023 carbon respectively |
| regional_overrides | Grid-region keys, then county-FIPS keys; county takes precedence; unknown keys rejected |
| seed / simulation_count | Stored seed; 1–10,000 draws; current engine supports at most 50 counties |
| feasibility_mode | Exploratory retains unknowns; verified requires evidence for power, water allocation, parcel/zoning and fiber redundancy |
| hard_constraints | Explicit maximum thresholds for regional price, carbon rate or water stress; missing values excluded; these are screening filters, not capacity certificates or chance constraints |
| numerical_tolerances | Physical objective absolute tolerances [USD, tonnes CO2e, m³] plus relative allowance |
| cvar_alpha | Upper-tail CVaR alpha; demo 0.95 |
| bootstrap_resamples | 20–200 common-index bootstrap resamples for Monte Carlo mean-estimator error |
| convergence_tolerances | Predeclared relative objective-mean and absolute Pareto-frequency thresholds |

A prior always contains exactly `kind`, `lower`, `mode`, `upper`, `units` and `source`. Fixed priors have identical lower/mode/upper values. Triangular priors require ordered, nondegenerate bounds. Invalid ranges, booleans masquerading as numbers, nonfinite values, duplicate scenarios, unknown settings and oversized computations are rejected. Correlation matrices and hazard-derived chance constraints are unsupported and not silently accepted.

## Randomness, dependencies and trajectories

Seed-stable named random streams generate shared engineering and rate quantiles once, before any county evaluation. Candidate FIPS ordering and scenario ordering do not affect draws; smaller runs are prefixes of larger runs. Regional priors transform the same global rate quantile, preserving common drivers while allowing different regional responses.

PUE/WUE uncertainty describes an unknown lifetime design parameter, held constant within a draw. Rates describe assumed lifetime trajectory parameters. Fixed structural rates intentionally have no stochastic future variability. The demo has no sampled measurement error, annual weather, outage or calibrated grid/price process. Historical observations and climate normals are not converted into fabricated uncertainty distributions.

Annual prices = 2025 retail anchor × (1 + assumed growth)^(year − 2025).
Annual carbon = 2023 eGRID anchor × (1 − assumed decline)^(year − 2023).

The 2023-to-opening extrapolation is an explicit bridge assumption. Real price scenarios are anchored to observed 2025 USD; no nominal historical growth is incorrectly labeled an empirical real-growth process. Rates of zero are explicit no-change controls. The demo uses the full 3×3 grid of price growth 0/1/2% and carbon decline 0/2/5%, with no scenario probabilities.

## Results contract

`results.json` contains:

- `schema_version`, `model_version`, `run_id`, `status`, `seed`, and the full validated `config`.
- `dataset_hashes`, `input_hashes`, official `sources` and URLs, `scope`, `boundary_exclusions` and completeness/assumption `warnings`.
- `objective_units`, discount convention/timing, and `scenario_mixture: null`.
- `excluded_candidates` with IDs and reasons; `no_eligible_candidates` is valid in verified mode.
- A separate `scenarios` entry for each structural path, with its assumptions and `scenario_weight: null`.
- Per scenario, `expected_frontier_ids`, `robust_frontier_ids`, and candidate summaries.
- Per candidate/objective, `mean`, `median`, `p05`, `p95`, `cvar`; conditional `pareto_frequency`; feasibility/evidence, coverage, provenance, grid ambiguity and water-stress context.
- `monte_carlo_error` with bootstrap SE/p025/p975 for means and Wilson 95% frequency-estimator bounds. These quantify estimator error, not input uncertainty or calibrated future probabilities.
- `sensitivity_results` with exact alternative configurations, grids/sector anchors, exclusions and summaries; `convergence` checks/exception lists and `near_frontier_ties`.

Objective order is lifetime operational electricity cost, operational CO2e, direct cooling consumption. Cost is discounted 2025-base USD; carbon is tonnes CO2e; water is m³ consumption. Missing feasibility remains unknown. All JSON numbers are finite or null and FIPS are strings.

## Frontier semantics

Exact pairwise enumeration minimizes every objective. A dominates B if it is no worse within the symmetric pair tolerance on all objectives and better beyond that tolerance on at least one. The demo absolute tolerances are $1, 0.001 tonnes and 0.001 m³; relative tolerance is 1e−10. No min–max scaling, utility weighting or invented regret is used.

Expected frontiers use objective means. Robust frontiers independently use upper-tail CVaR: the exact worst 5% mass, including fractional boundary observations. Per-draw frontiers are calculated in bounded batches; `pareto_frequency` counts membership, can sum above one, and is not probability of being best.

At common WUE, direct water is equal across counties. Basin stress is separate context; it is not a volume or probability. In the uniform-rate demo, common engineering draws scale each county equally, so frequencies 0/1 and identical expected/robust frontiers are structural model properties. A separate test demonstrates differing expected/robust frontiers under explicit regional rate uncertainty.

## Reproduction artifacts and limits

`samples.npz` maps `scenario_0`, `scenario_1`, etc. to draw × sorted-candidate × objective arrays in config scenario order. `common_draws.npz` records shared PUE/WUE and latent rate quantiles. `annual_trajectories.csv` freezes conditional annual mean prices/carbon; exact draw paths can be reconstructed from config and latent draws. `candidates.csv`, `report.md`, `frontiers.png` and `frontiers.svg` support review/export.

The normal run compares paired 1,000/5,000/10,000 draws, checking every candidate/objective against 10,000 as a numerical reference. Tolerances are <2% mean change and <0.03 frequency change in the demo. Source/engineering validity is not established by convergence. Tests include independent hand calculations, distribution tail handling, deterministic collapse, reproducibility, ordering/prefix behavior, dependencies, invalid config/coverage, differing risk frontiers, offline artifact generation and cache reuse.

Optional site-level capacity/chance constraints, a trained ML model, construction, heat reuse, indirect generation water, backup-fuel emissions, full TCO and HTTP jobs are outside this task's implemented model. All locally unverified candidates remain exploratory.
