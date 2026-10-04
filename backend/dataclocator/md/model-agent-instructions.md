# Backend agent instructions: sustainable data center location model

## Mission and scope

Implement a Python backend that compares candidate U.S. regions for a sustainable AI data center using Monte Carlo simulation and multi-objective optimization. The user owns the frontend; provide a documented JSON interface and exported results, not a UI. Read `md/hackatonDetails.md` first. Comment every function and logical code section, explaining purpose and non-obvious behavior.

Start with the contiguous United States at county resolution, using Census FIPS as string identifiers. This is an explicit scope assumption based on the challenge title and U.S. datasets; it is not a claim to identify the world's best location. Counties are screening regions, not approved construction sites. Initially compare 20–50 geographically diverse counties selected before inspecting outcomes; expand to national coverage when joins and data completeness are validated. Do not choose only known data center markets.

Deliver a set of defensible tradeoffs rather than inventing a universally optimal location. No trained machine learning model is necessary. Randomness belongs in uncertain inputs; a stored random seed must reproduce a run.

## Required decisions and inputs

Decision variable: candidate county. Extension: county × cooling design (dry, hybrid, evaporative) only after defensible energy/water performance curves are available. Keep workload and service requirements equal across alternatives.

User configuration must specify IT nameplate MW, utilization, operating hours, analysis horizon, base currency/year, discount rate, cooling assumptions, scenario set, seed, simulation count, and any hard constraints. Suggested demonstration settings: 100 MW IT, 0.85 average utilization, 8,760 hours/year, 25 years, 5,000 simulations, seed 42. These are illustrative assumptions, not measured data. Use a configurable opening year. Run 20- and 30-year sensitivity cases. Do not silently choose numerical PUE, WUE, construction cost, or electricity escalation priors; record sourced values or clearly labeled user assumptions with bounds and units.

## Dataset acquisition plan

Sources reviewed October 3, 2026. URLs below are official discovery pages, not verified successful bulk downloads. At implementation time resolve the actual download URL, inspect the dictionary, pin the release, record access restrictions and licensing, and test extraction on a small sample before downloading large files. Do not fabricate column names or endpoints. Never silently substitute synthetic data for unavailable real data.

| Priority | Dataset and official entry point | Needed variables | Acquisition and geographic join | Limitations / fallback |
|---|---|---|---|---|
| Required | [Census Gazetteer](https://www.census.gov/geographies/reference-files/time-series/geo/gazetteer-files.html) | County/state FIPS, name, representative latitude/longitude, land area | Download county ZIP/tabular file; retain leading zeros. Obtain compatible Census county polygons when doing overlays. | Pin geography vintage; crosswalk changed county equivalents. Representative point is not a proposed parcel. |
| Required | [EPA eGRID detailed data](https://www.epa.gov/egrid/detailed-data), [technical resources](https://www.epa.gov/egrid/technical-resources) | Annual total-output CO2e rate, generation/resource mix, subregion identifiers | Download XLSX and dictionary. Prefer spatial eGRID subregion assignment using an official boundary layer when available; mark border counties. State averages are a flagged fallback. | Latest release found was eGRID2023 revised June 2025. Historical average emissions are not marginal emissions or proof of hourly clean supply. Plant locations do not define the grid supplying a county. |
| Required | [EIA electricity data](https://www.eia.gov/electricity/data.php), [API documentation](https://www.eia.gov/opendata/documentation.php) | Monthly state industrial electricity prices and dates; commercial price sensitivity | Download published XLS files without a key, or use API v2 with `EIA_API_KEY`; discover current routes/facets, paginate and check totals. Acquire at least five years when available; state-FIPS join. | Retail averages are proxies, not negotiated data center tariffs. Convert cents/kWh to USD/MWh by multiplying by 10. Include sensitivity to sector choice and demand charges excluded. |
| Required | [WRI Aqueduct 4.0 maps](https://www.wri.org/data/aqueduct-global-maps-40-data), [dictionary/FAQ](https://github.com/wri/Aqueduct40/blob/master/data_FAQ.md) | Baseline water stress/depletion; future water stress for 2030/2050 and relevant scenarios | Download spatial/tabular basin data, follow registration/attribution terms. Join county polygons to basins; retain basin overlap distribution. For initial representative-point join label spatial approximation. | Scores are screening indicators, not available withdrawal volumes or probabilities. Missing/no-data codes must not become zero risk. Future pathways have no objective probability unless explicitly assigned. |
| Required | [NOAA climate normals](https://www.ncei.noaa.gov/products/land-based-station/us-climate-normals) | Monthly temperature normals, cooling-degree measures, station coordinates; humidity/wet-bulb if separately sourced | Download monthly 1991–2020 normals and station metadata. Use nearest suitable stations with distance/elevation checks; document station assignment. | Normals cannot estimate interannual variance. Temperature alone cannot determine engineering PUE/WUE. If no validated response curve exists, keep cooling assumptions equal across counties and show climate separately. |
| Required | [FEMA NRI documentation](https://www.fema.gov/sites/default/files/documents/fema_national-risk-index_technical-documentation.pdf), [NRI entry point](https://www.fema.gov/nri) | County identifiers; hazard-specific flood, wildfire, heat, hurricane indicators; annual frequencies where documented | Resolve current official county CSV/geodatabase via NRI/RAPT; inspect current version dictionary; join FIPS. Keep frequency, exposure, expected loss and composite risk distinct. | County loss estimates refer to existing exposed assets, not this proposed facility. Do not turn scores into incident probabilities or data center downtime. If download is blocked, record blocker and accept a user-supplied official file. |
| Recommended | [EIA-861 detailed files](https://www.eia.gov/electricity/data/eia861/) | Utility SAIDI/SAIFI, reporting method, inclusion/exclusion of major events, service territory | Download annual ZIP/XLS files; combine reliability and utility service-territory records. Map utilities serving counties, retain multiple utilities and reporting differences. | Distribution-level historical metrics are not hyperscale uptime, redundant-feed capacity, or available interconnection MW. State aggregation requires justified weighting, otherwise report range. |
| Recommended | [Cambium](https://www.nrel.gov/analysis/cambium.html) | Future annual/hourly grid emissions and scenario/region/year identifiers | Follow current official download links (including redirects), select limited regional/scenario files and join documented region mapping. | Modeled futures are scenarios, not forecasts. Do not combine average and marginal emissions indiscriminately; wholesale/model costs are not retail tariffs. If unavailable use explicit decarbonization sensitivity assumptions, not claimed predictions. |
| Optional | [LBNL interconnection queues](https://emp.lbl.gov/queues) | Project fuel, status, MW, location, queue dates, completion history | Download current project workbook/codebook; aggregate where geography is valid. | Generator queue MW is not available load-serving capacity; projects can withdraw. Keep as supporting context, not a hard feasibility certificate. |
| Optional | [USGS Annual NLCD](https://www.usgs.gov/centers/eros/science/annual-nlcd-data-access) | Developed/undeveloped land classes, wetlands and land-cover constraints | Fetch only candidate-region raster windows/tiles; overlay county polygons. | Land cover is not zoning, ownership, parcel availability or protected status. Protected areas and parcel due diligence need separate official layers. |
| Optional | [NASA NEX-GDDP-CMIP6](https://www.nccs.nasa.gov/data-collections/nex-gddp-cmip6/) | Future daily temperature and precipitation for several models/pathways | Subset candidate coordinates/windows with THREDDS or public S3; avoid downloading the global archive. | Climate-model ensemble frequency is not an objective probability. Preserve pathway/model labels and avoid extrapolating unsupported weather-to-outage relationships. |

Do not block the first backend on optional global climate rasters, solar/wind resource archives or commercial fiber maps. Renewable resource quality alone does not establish firm 24/7 power. A broadband availability map does not establish redundant long-haul fiber or latency.

## Information requiring local inputs

Public regional datasets do not establish utility commitment, deliverable MW, upgrade cost or energization date. Store power capacity, water allocation, zoning/parcel status and fiber redundancy as `verified`, `unverified`, or `failed`, with evidence. Unknown feasibility must remain unknown. Offer exploratory screening and verified-feasibility modes; the latter may legitimately return no candidates.

Heat reuse requires recipient location, coincident heat demand, useful temperature, recovered heat fraction, delivery distance and cost. Default to no claimed benefit without this evidence. Embodied carbon requires material quantities and credible product emission factors; land/capex requires estimates or quotes. Indirect power-generation water requires a compatible regional consumptive-water factor with boundaries and units. Community impact needs distinct workforce/community inputs and must not be inferred from cheap land. Log these as coverage gaps rather than inventing county values. In MVP, report electricity cost rather than full total cost when capex/water tariffs are missing.

## Data contract and provenance

Store immutable `data/raw/<source>/<release>/`, normalized Parquet under `data/processed/`, configuration under `configs/`, and run artifacts under `outputs/<run_id>/`. Keep large downloaded files out of Git. Each source manifest includes source page, resolved file URL, publisher, release/data years, retrieval UTC, SHA-256, license/attribution, dictionary URL, geographic scale, transformation version and coverage notes.

Candidate fields: `candidate_id`, `county_fips`, `state_fips`, `name`, `lat`, `lon`, `grid_region`, `electricity_price_usd_per_mwh`, `grid_co2e_kg_per_mwh`, `water_stress_raw`, `water_stress_scale`, `climate_station_id`, `hazard_indicators`, `reliability_indicators`, `feasibility`, `coverage`, and per-feature provenance references. Time series/scenario tables retain year/month, units, scenario, region, status and uncertainty source. Separate measured, modeled, assumed and missing fields. Never use null as zero. Geographic identifiers must be strings; numeric outputs must be finite or null, never JSON NaN.

## Physical accounting

For each simulated year and candidate:

- IT energy MWh = IT MW × utilization × annual hours.
- Facility energy MWh = IT energy × PUE; enforce PUE ≥ 1.
- Operational grid carbon tonnes CO2e = facility MWh × grid kg CO2e/MWh ÷ 1,000. Convert eGRID lb/MWh to kg/MWh using 0.45359237.
- Electricity cost USD = facility MWh × retail USD/MWh.
- Direct cooling consumption m³ = IT MWh × WUE L/kWh when WUE is explicitly defined per IT energy: the MWh→kWh and L→m³ factors cancel. If a source uses facility energy, convert and document the definition.
- Optional indirect water m³ = facility MWh × sourced m³/MWh factor. Keep withdrawals and consumption separate; avoid double counting.
- Optional stress-weighted consumption = basin consumption × documented dimensionless stress factor. Report physical m³ alongside this index; a 0–5 risk score is not itself a water volume.
- Discount monetary costs to the base year using an explicit real/nominal convention. Do not discount physical carbon or water totals by default.

Annual price and carbon trajectories must vary over the horizon, not repeat an arbitrary present-year sample 25 times. Keep scenario-model assumptions and uncertainty bounds visible. Report full boundaries: backup fuel, construction, IT manufacturing and heat displacement are excluded until explicitly modeled. No carbon credit for heat reuse or clean-energy contracts without supported accounting.

## Monte Carlo design

1. Generate scenario trajectories once, then evaluate all candidates against the same draws (common random numbers). Preserve regional responses while sharing global drivers. Store seed and scenario identifiers; stable candidate ordering must not change results.
2. Separate uncertainty in measured inputs/engineering assumptions from future variability and structural scenario choices. Use empirical year-block bootstrap only where suitable history exists; otherwise use bounded, documented priors. Do not infer uncertainty from normals or convert risk scores into distributions.
3. Maintain dependencies: workload is shared; climate affects energy and water through sourced cooling curves; a drought/heat trajectory affects relevant inputs jointly. Use block sampling or a documented latent-factor model; validate any supplied correlation matrix. Keep factors independent only when explicitly justified or marked as a simplification.
4. SSP/grid pathways should first be compared separately. A pooled mixture needs disclosed subjective weights and a sensitivity sweep; never label scenario frequency as a calibrated future probability.
5. Begin with 500 draws while debugging, then 5,000. Compare 1,000/5,000/10,000 only for convergence validation; predeclare tolerance (for example <2% change in objective means and <0.03 absolute change in frontier frequencies), and record exceptions for near ties. Bootstrap Monte Carlo error separately from input uncertainty. Set compute limits.

## Multi-objective optimization

For a finite list of counties, enumerate candidates and calculate the Pareto frontier exactly. An evolutionary optimizer is unnecessary for MVP. Add NSGA-II only if continuous design variables later make enumeration impractical, and validate it against enumerable cases.

Primary minimization objectives: expected lifetime operational electricity cost, expected lifetime operational CO2e, and expected lifetime direct cooling-water consumption. Add stress-weighted water only when its transformation is defensible. If equal WUE makes direct water identical across counties, disclose this and use separate basin stress constraints/context; do not fabricate a differentiated water objective.

Candidate A dominates B if A is no worse on every objective and strictly better on at least one, with documented numerical tolerances. Return the whole frontier. No min-max scaling or preferences are needed to establish dominance. Reliability and hazard indicators are initially constraints/context, not fabricated monetary losses.

Offer a robust view using upper-tail CVaR at alpha 0.95 for costs, carbon and water: average the worst 5% of outcomes. Implement empirical tail handling including fractional boundary mass and test small samples. Compute robust frontiers independently from expected-value frontiers. Report median, mean, p05/p95 and CVaR per objective; these are conditional on the assumed model.

For each simulated future, optionally compute a Pareto frontier and count each candidate's frontier frequency. Name it `pareto_frequency`, not probability of being the best; multiple candidates can belong simultaneously and frequencies need not sum to one. If users require one recommendation, accept explicit preference weights/reference targets, normalize using fixed documented anchors, and show sensitivity. Never mix one arbitrary score into the main Pareto calculation. Regret requires a defined utility; do not compute an undefined multi-objective regret.

Apply verified hard constraints before optimization. Configurable chance constraints require actual sampled quantities, such as sourced power capacity: estimate violation frequency and Monte Carlo error; do not use hazard scores as violation probabilities. In exploratory mode expose unverified feasibility prominently on every candidate and recommendation.

## Backend architecture and frontend handoff

Use a supported Python version and pinned dependencies. Suggested modules: `ingest/`, `geography.py`, `schemas.py`, `accounting.py`, `scenarios.py`, `simulation.py`, `pareto.py`, `reporting.py`, `api.py`. NumPy/pandas/Parquet handle calculations; use GeoPandas only for required joins. FastAPI/Pydantic are a suggested HTTP layer; verify current official documentation when implementing. Prefer local files to a database for MVP.

Provide CLI acquisition, preprocessing and simulation commands. Simulation must work from frozen local inputs without live network access. Keep pure model functions independent from HTTP. Cache by configuration + dataset hashes + model version. Use bounded asynchronous jobs for larger runs instead of holding an HTTP request open indefinitely.

Document endpoints: `GET /health`, `GET /datasets` (versions/coverage), `GET /candidates`, `POST /runs` (validated config, returns run ID), `GET /runs/{id}` (status/results/error), and `GET /runs/{id}/candidates/{candidate_id}` (evidence/objective details). Configurable explicit CORS origins; secrets only in environment variables. Reject invalid ranges and oversized runs. No frontend implementation.

Run response contract: schema/model version, run ID, seed, scenario assumptions/weights, config, dataset hashes, completeness warnings, excluded candidates with reasons, candidate feasibility status, objective units and summaries, expected/robust frontier IDs, conditional Pareto frequencies and sensitivity results. Include provenance URLs and boundary exclusions. Export the same information to JSON plus candidate CSV. Optionally provide a standalone technical report with frontier plots; this is a backend artifact, not a frontend.

## Implementation order

1. Inspect repository and instructions. Create dependency/config scaffolding, source manifest format and acquisition report. Implement Census/EIA/eGRID ingestion first; verify actual columns/units with dictionaries.
2. Add water/climate/hazard ingestion and joins. Produce coverage report before modeling; identify failed sources, scale mismatches, border ambiguities and local feasibility gaps.
3. Implement deterministic physical accounting with explicit assumptions. Validate on hand-calculated examples and compare candidates at identical workload.
4. Add shared Monte Carlo trajectories with documented uncertainty/correlation assumptions. Freeze inputs and export scenario metadata.
5. Implement exact expected and robust frontiers, distribution summaries and Pareto frequency; add preference sensitivity only as an optional layer.
6. Expose CLI/JSON and HTTP contract, document frontend integration. Run real-data regional screening and produce a reproducible report. Synthetic fixtures may test the engine but cannot substantiate an actual location recommendation.
7. Add optional Cambium/reliability/local evidence and construction/heat/indirect-water accounting as time permits. Keep optional features separate and traceable.

## Acceptance checks

- Unit checks for all energy/cost/carbon/water conversions, horizon discounting and monotonicity; doubling workload doubles outcomes in a fixed-PUE/WUE case.
- Pareto tests for domination, ties, tradeoffs, tolerance and ordering; CVaR tests against hand calculations and degenerate distributions.
- Seed reproducibility, shared-draw consistency, candidate ordering invariance and deterministic-input collapse to deterministic outputs.
- Join checks: FIPS leading zeros, duplicates, CRS, boundary candidates, station distances, basin mixtures, missing source codes and geography vintages.
- Scenario checks: valid ranges, dependency behavior, disclosed weights, plausible trajectories and convergence/error reporting.
- Endpoint/config validation, failed-source handling, frozen-input offline run, output schema, provenance and completeness.
- A real-data report identifying what is known, assumed and still unverified. If insufficient data exists, return a coverage-limited comparison rather than a confident site recommendation.

## Required final handoff

Provide reproducible commands, dependency lock, source/download manifest, processed-data dictionary, example run config, documented API/JSON contracts, test results, sensitivity/convergence evidence, an example real-data comparison and a list of missing local inputs. Explain why each frontier candidate remains competitive and the assumptions that would change that result. Do not claim verified parcel suitability, objective pathway probabilities or quantified full sustainability benefits beyond modeled boundaries.
