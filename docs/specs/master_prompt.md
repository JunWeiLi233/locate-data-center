# Master orchestration requirements (from the user, 2026-10-02)

This file preserves the user's master requirements so every phase agent can read them.
The per-phase detailed specifications are in `docs/specs/phase1.md.txt` … `phase7.md.txt`.
Where the two overlap, apply BOTH (the stricter requirement wins).

## Project objective

Build a deterministic geospatial decision-support system that searches across the United States and
identifies promising geographic regions for sustainable AI data-center construction.
The system must NOT start from a manually selected list of cities.

Core pipeline:

U.S. geography → geographic grid → environmental/infrastructure features → feasibility screening →
physical data-center calculations → Pareto analysis → AHP/MCDA → spatial clustering → candidate regions →
sensitivity/validation

Question answered: given a data-center specification, which geographic regions in the United States deserve
further investigation for sustainable data-center development, and why? It must NOT claim that national-scale
data proves an exact parcel is buildable.

## Core architecture (two parts)

PART 1 — GEOGRAPHIC DATA: what does each part of the United States look like?
GridID → [energy, water, climate, hazards, land, ecology, infrastructure, construction/logistics]

PART 2 — LOCATION MODEL: given a data-center specification, which geographic areas are promising?
USGridDataset + DataCenterRequirements + DecisionConfiguration → PotentialDataCenterRegions

## Non-negotiable model principles

- The core model must be deterministic under fixed inputs.
- Do NOT use an LLM to decide scores or winners.
- Do NOT train a black-box ML predictor without a legitimate labeled target.
- AI/subagents may help write code, investigate documentation, build data adapters, test, review, and explain
  structured outputs. They must NOT invent geographic values, engineering coefficients, expert judgments, or
  missing evidence.
- Always distinguish OBSERVED DATA, CALCULATED VALUE, SCENARIO, PROXY, UNKNOWN.
- UNKNOWN must never silently become zero or PASS.

## Maintained artifacts

AGENTS.md, docs/methodology.md, docs/data_contracts.md, docs/data_dictionary.md, docs/sources.md,
docs/limitations.md, docs/phase_handoff.md; configuration under configs/; tests under tests/; production code
under src/. Important production logic must not remain only in notebooks.

## Phase gate rule

DELEGATE → IMPLEMENT → REVIEW → TEST → FIX → ACCEPT → HANDOFF → NEXT PHASE.
Never advance solely because an agent says "Done". Inspect code and outputs, run tests, compare against
acceptance criteria. If tests disagree with assumptions: investigate before changing the test. Never change
expected results merely to make tests green.

## Source policy

Prefer the authoritative sources specified by this project:

- ENERGY: NREL NSRDB; NREL wind-resource datasets / WIND Toolkit / specified WRDB; EPA eGRID;
  Berkeley Lab Queued Up; EIA Form EIA-861; EIA / U.S. Energy Atlas.
- WATER: WRI Aqueduct 4.0; NOAA/NCEI climate information; EPA Clean Watersheds Needs Survey.
- CONSTRUCTION: Global Iron and Steel Tracker; Global Cement and Concrete Tracker; Freight Analysis Framework;
  Building Transparency / EC3.
- LAND / INFRASTRUCTURE: USGS Annual NLCD; EIA / U.S. Energy Atlas; FCC broadband data; National
  Transportation Atlas Database.
- CLIMATE: FEMA flood data; Wildfire Risk to Communities; NOAA IBTrACS; U.S. Drought Monitor;
  NASA NEX-GDDP-CMIP6; FEMA RAPT where useful.

Use additional authoritative sources only when necessary and document why. Do not silently replace a requested
source with a weaker proxy.

## Data provenance contract

Every important metric preserves metadata similar to:

```json
{"metric": "", "value": null, "unit": "", "source": "", "source_url": "", "data_year": "",
 "retrieved_at": "", "spatial_resolution": "", "method": "",
 "status": "observed | calculated | scenario | proxy | unknown",
 "confidence": "high | medium | low | unknown"}
```

## Phase summaries from the master prompt (detailed specs in docs/specs/phaseN.md.txt)

PHASE 1 — Foundation + U.S. grid: inspect repo; package structure; AGENTS.md; shared schemas; authoritative
CONUS boundary; configurable regular grid (~10 km × 10 km); appropriate CRS; stable GridIDs; cell and
land-intersection area; state/county metadata where practical; development-area and national modes; tests.
Output data/processed/us_grid.parquet. Acceptance: deterministic grid IDs, valid geometries, explicit units,
configurable resolution, repeatable generation, national grid independent of manually selected cities.

PHASE 2 — Core geographic dataset: source adapters, caching, resumable processing, spatial joins/zonal
statistics, explicit missing-data handling, coverage tracking, source metadata, unit conversions, tests. Do NOT
rank sites. Outputs data/processed/us_grid_dataset.parquet, feature_provenance.parquet, coverage_report.json,
data_manifest.json. Reject work that uses synthetic data as real data; treats missing flood data as zero risk;
treats transmission proximity as power availability; treats Aqueduct as confirmed water supply; hides source
resolution.

PHASE 3 — Screening + physical model: configurable peak_it_power_mw, average_it_load_factor,
target_opening_year, operating_lifetime_years, cooling design, screening mode. PASS/FAIL/UNKNOWN for critical
constraints; STRICT and EXPLORATORY modes. E_IT = P_peak × load_factor × hours; E_facility = E_IT × PUE;
C_electricity = E_facility × grid_carbon_intensity; W_site = E_IT × WUE, with correct unit conversions. Keep
site water and electricity-related water separate. Do not invent PUE/WUE relationships: documented engineering
functions or explicit scenario assumptions. One performance record per grid × cooling design × scenario.
Outputs screening_results.parquet, site_performance.parquet, screening_summary.json. Hand-calculated
numerical tests required.

PHASE 4 — AHP + Pareto + ranking + clustering: metric registry first (units, direction, normalization,
thresholds, role, source requirements); prevent double counting. Pareto: nondominated alternatives; do not
permanently delete dominated alternatives. Weighting: equal, user, AHP. AHP: pairwise matrix A with A_ii = 1,
A_ji = 1/A_ij, A_ij > 0; principal right eigenvector normalized to sum 1; CI = (λmax − n)/(n − 1);
CR = CI/RI with a documented RI table; CR ≤ 0.10 is a configurable conventional review threshold, not proof;
if inconsistent → REVIEW_REQUIRED; do not silently modify judgments; do not fabricate expert comparisons; no
judgments → equal-weight baseline. MCDA: Score(s) = Σ_j w_j N_j(s), export every contribution; a hard FAIL
cannot be compensated. Clustering: adjacent high-performing cells into candidate regions; preserve member
GridIDs; do not merge distant cells; no fictional "super-site". Outputs normalized_metrics.parquet,
ahp_result.json (when applicable), pareto_results.parquet, ranked_cells.parquet, candidate_regions.geojson,
region_membership.parquet, ranking.csv. At the end of Phase 4 the full first version must run:
U.S. grid → geographic data → screening → physical model → decision model → candidate regions.

PHASE 5 — Expanded data + future scenarios: NSRDB, wind-resource data, EIA-861, Queued Up, Aqueduct future
scenarios, EPA CWNS, Drought Monitor, IBTrACS, NEX-GDDP-CMIP6, FCC, NTAD, Global Iron & Steel Tracker,
Global Cement & Concrete Tracker, FAF, EC3 where feasible. Preserve current/2030/2040/2050 distinctions where
supported; do not fabricate intermediate years; do not infer future grid carbon from queue MW. Separate
decision alternatives (cooling design) from external scenarios (climate pathway). Lifecycle components where
defensible (construction, equipment, operations, replacement, end-of-life); UNKNOWN components remain UNKNOWN.
Outputs: enhanced geographic dataset, future_scenarios.parquet, lifecycle_results.parquet, updated rankings,
baseline-vs-enhanced comparison. Phase 4 baseline must remain runnable.

PHASE 6 — Validation + sensitivity (independent agent): unit verification (grid, CRS, joins, energy/water/
carbon formulas, normalization, AHP, Pareto, clustering, scenario indexing); directional tests (higher PUE
cannot reduce facility electricity; higher WUE cannot reduce site water; higher carbon intensity cannot reduce
emissions; higher risk cannot improve a cost-type normalized metric; missing data cannot improve a candidate via
silent weight redistribution); external validation with independent evidence (re-reading the same source is not
independent validation; existing data-center locations are NOT ground-truth labels); holdout testing with a
frozen model/config version; sensitivity (weights, PUE, WUE, load factor, future grid carbon, future water,
future climate, construction assumptions, screening thresholds, grid resolution in selected test areas) by
re-running affected calculations; ablation (minus water/carbon/climate/infrastructure/construction); optional
Monte Carlo separate from the deterministic core with explicit distributions and fixed seed, reporting
selection frequencies. Outputs validation_report.json, validation_report.md, sensitivity_results.parquet,
robustness_summary.csv, ablation_results.csv. Do not hide failed tests.

PHASE 7 — Integration + final delivery: CLI commands build-grid, ingest, build-features, screen, simulate,
rank, cluster, validate, run; top-level command like
`python -m dc_locator run --config configs/run.yaml --output runs/example` that actually works. Run metadata:
run ID, timestamp, code revision, environment, dataset versions, configuration, grid resolution, source
coverage, random seed where applicable, warnings, blockers. Output package (as applicable):
us_grid_dataset.parquet, screening_results.parquet, site_performance.parquet, normalized_metrics.parquet,
pareto_results.parquet, ranked_cells.parquet, candidate_regions.geojson, region_membership.parquet,
ranking.csv, feature_provenance.parquet, run_metadata.json, validation_report.json, sensitivity_results.parquet,
recommendation_report.md. Required runs: synthetic test run; real-data development-area run; national run ONLY
if acquired data coverage and compute resources support it. Do not claim national completion if only a subset
was processed.

## Failure handling

If a dataset cannot be accessed: do not fabricate it; do not block the whole project unnecessarily; implement
the adapter/interface where possible; document required access; mark the source BLOCKED or PARTIAL; preserve
UNKNOWN values; continue with an explicitly reduced-data model if valid; clearly label resulting limitations.

## Performance

Vectorized operations, spatial indexing, chunking, Parquet/GeoParquet, caching, resumable processing, no
repeated downloads, no per-cell HTTP requests. No premature distributed infrastructure. Establish correctness on
a development area first, then scale.

## Versioning rule

After every accepted phase create/update a phase completion record (phase, code revision, schema version, data
versions, tests, known limitations). Never allow a later phase to silently change an earlier phase's meaning.
If a schema must change, document the migration.

## Final model interpretation

The output means: "These geographic regions deserve further investigation under the stated facility
requirements, datasets, constraints, assumptions, and decision preferences." It does NOT mean: "We have proven
this exact parcel is America's objectively best place to build a data center." This distinction must appear in
documentation and final reports.
