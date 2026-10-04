# Hackathon mission and rubric alignment

The project addresses the challenge with an executable, deterministic national decision engine. This revision adds the missing six-deliverable presentation, recorded decision explanations, a same-cell cooling-impact comparison, an optional supplied-input heat-reuse calculation, and a proposed 25-year operating vision. It does **not** establish complete scientific coverage of every mission factor or guarantee any rubric score.

The challenge description and two rubric screenshots supplied on 2026-10-03 are assessment evidence. Their invitation to find an “optimal” location does not justify inventing feasibility, engineering factors, judgments or benefits. The model recommends an investigation priority under declared preferences.

> These geographic regions deserve further investigation under the stated facility requirements, datasets, constraints, assumptions, and decision preferences.

## Deliverables and evidence

Generate a new package from an already completed saved run:

```powershell
.venv/Scripts/python.exe -m dc_locator submission --run runs/national_discovery_v2 --output runs/submission_alignment_v2 --heat-reuse-input configs/heat_reuse_input_template.json
```

`submission_brief.html` is a standalone printable report; `submission_brief.md` contains the same six sections; `submission_brief.json` retains exact quantities, statuses, provenance, assumptions and input identities. `run_metadata.json` records archived science separately from the presentation implementation. Existing runs are read-only; output must be a new owned folder. In the frontend, load a completed run and open **Decision brief**. Older or incomplete saved contexts show an explicit unavailable reason.

| Requested deliverable | Implemented evidence | Remaining limit |
|---|---|---|
| Recommended geographic location | Stored rank-one region representative, primary county/state overlap, actual evaluated cell center, separate connected region center and alternatives | This is a conditional investigation cell; no approved parcel or nationally objective optimum |
| Decision framework and weighting | Hard screening, paired annual physics, fixed normalization references, Pareto context, actual leaf weights and recorded weighted contributions | Weights are project preferences; no fabricated expert AHP judgments |
| Data analysis | Implemented/acquired/analyzed coverage, source periods and retrieval identity, full representative provenance and config/code/checksum lineage | Acquired files do not imply analyzed features; current optional national hazards/climate are uncomputed |
| Sustainability impact assessment | Paired annual energy, carbon, onsite and generation-water outputs; same-cell design differences; optional supplied heat-host case | Total water, useful heat, full lifecycle and construction benefits remain UNKNOWN when their inputs are missing |
| Risk assessment | Recorded screening outcomes, missing reasons and evidence-to-action register | Utility capacity, water commitment, diverse fiber, ecology, contiguous land and parcel clearance are unresolved |
| 20–30 year implementation vision | Proposed diligence, commissioning, 2030–2054 operation, replacements and retirement plan | An operating vision is not a 25-year grid/climate/emissions forecast |

## Actual national recommendation and trade-offs

The accepted national baseline covers **3,384 CONUS cells** at **50 km** resolution. Its 6,768 alternatives include 5,514 conditionally rankable alternatives, 1,242 unranked for required missing metrics and 12 excluded by hard screening. There are 122 design regions at 61 geometries. The associated STRICT run exports no qualifying regions. These are findings under the preserved baseline, not results of reranking in the submission layer.

The first national investigation priority is `g50000m-r0023-c0004 / air_dry_assumed / historical_static_2023`, with stored score **95.86145330031282** and rank **1**. The cell's primary overlap is **Trinity County, California**, and its center is **40.081529, −123.288078**. It spans more than one county. Its connected region contains 155 coarse cells and 387,500 km², with a different center at 44.251273, −120.052275. The region center must not be presented as the recommended construction location. The separate regional-refinement work is a new delivery revision; this brief supports its native-part layout but does not claim that revision has been accepted.

The comparison also shows the Livingston-primary New York cell at stored rank 3 and Garfield-primary Utah cell at stored rank 24. Alternatives are selected from distinct exported representative cells in the same external scenario, retaining backend order. This is not a manually selected city shortlist. For example, the New York alternative's annual electricity carbon is lower than California's; California's slightly higher total score follows the combined declared water, land and transmission-proxy preferences. Present the trade-off rather than claiming California minimizes carbon or every resource.

The actual baseline leaf weights are:

| Criterion | Weight | Meaning |
|---|---:|---|
| Annual electricity CO2e | 25% | Annual operating comparison using historical-static eGRID intensity |
| Annual onsite consumption | 12.5% | Cooling-design scenario; excludes generation and construction water |
| Local baseline basin stress | 12.5% | Aqueduct observed score; not a water-supply commitment |
| Transmission proximity | 25% | Mapped geographic proxy; not connection capacity |
| Suitable-land fraction | 25% | Land-cover proxy; not contiguous, obtainable, low-impact or buildable land |

The California representative has annual facility electricity **840,960 MWh**, electricity emissions **164,018.322 tonnes CO2e**, and assumed dry-cooling consumption **0 m³**. The paired tower design consumes **210,240 m³/year** onsite at the same cell, with identical electricity and carbon because both configured annual PUEs are 1.20. The difference is an explicit design-scenario result, not demonstrated performance. Electricity-generation water, withdrawal and verified peak demand remain UNKNOWN; zero ideal cooling consumption does not mean zero facility-wide water use.

## Coverage of the wider ecosystem

| Mission factor | Current national evidence | Required next evidence |
|---|---|---|
| Energy and carbon | eGRID operating factor and annual facility energy; transmission geography | Contracted clean energy, hourly matching, serving-utility capacity and defensible future grid scenarios |
| Heat recovery and reuse | New optional annual heat-host input/calculation contract; unfilled input stays UNKNOWN | Willing host, usable temperatures, compatible seasonal demand, recoverable fraction, pipe route/losses, auxiliary energy and displaced heating baseline |
| Water | Aqueduct baseline stress and direct design consumption; physical model supports supplied generation factors | Committed source, restrictions, withdrawal/blowdown, generation mix/geography consumption factors and long-term security |
| Climate resilience | Screening retains UNKNOWN hazard/parcel gates; historical expanded tools exist separately | Actual bounded flood, wildfire, storm, drought, extreme-heat and future-climate analysis for the shortlisted area |
| Grid and infrastructure | Mapped transmission/plant/pipeline proxies | Serving utility reliability, upgrade timing, tariff, peak capacity, independent carriers and transport feasibility |
| Land, materials and biodiversity | NLCD land cover; independent ecology gates; lifecycle interfaces | Ownership/zoning/contiguity, ecological survey, real quantities, product EPDs, freight routes and replacement/end-of-life inventories |
| Community and economics | Explicit proposed diligence and operating actions; no fabricated scores | Workforce and training partners, resident input, noise/water/land/ratepayer effects, local benefit agreements, actual tariff/CAPEX/OPEX |

Fuel cells and carbon capture are not presumed low-carbon resources. Assess fuel supply, system boundaries, reliability and compatible emissions evidence before adding any such decision alternative. A vendor mention in the challenge is not an efficiency coefficient or permission to bypass dataset access controls.

The next substantive scientific expansion should bind bounded hazard/climate and protected-land evidence to completed refined areas, then acquire compatible generation-water inputs and local engineering/heat/community evidence. Existing documented manual-acquisition paths remain necessary for sources requiring forms, accounts or click-through licenses. There is no silent substitution or synthetic fallback.

## Rubric readiness

| Category | What judges can inspect now | Honest boundary |
|---|---|---|
| Technology | Reproducible geospatial pipeline, source hashes, physical calculations, Pareto/AHP/MCDA, sensitivity and interactive map | No independent overall physical accuracy claim |
| Presentation | One six-section printable decision brief; actual explanations/contributions; cell/region distinction; comparison and risks | Clarity does not make incomplete evidence complete |
| Innovation / creativity | Joint geography/design decisions, transparent UNKNOWNs, heat-host scenario with demand/loss/auxiliary-energy accounting, ecosystem implementation gates | No claim of unprecedented novelty or achieved heat savings without a host |
| Execution | Regression-tested CLI, API and UI; deterministic export, protected archived artifacts and old-run fallback | Completed software is distinct from engineering/permitting feasibility |
| Theme | Carbon, direct/indirect water boundary, land, heat, risks, materials/community actions and a 25-year vision | Materials/community economic benefits and future security are still qualitative or UNKNOWN |

An “Excellent” grade is a judge's assessment, not a numeric model output. No self-awarded 20/20 claim is made.

## Suggested live demonstration

1. Explain the problem: building AI infrastructure commits energy, water, land and local communities for decades.
2. Show national analyzed coverage and the recorded grid resolution. Load the actual saved exploratory run; also explain why STRICT has no accepted locations.
3. Open the decision brief. Identify the primary Trinity/California cell and distinguish its center from the large connected region. Explain that this is where investigation starts.
4. Show the five actual weights and contributions, then compare the New York alternative. Explain why lower carbon alone does not determine the preference ranking.
5. Show the paired cooling-water difference and UNKNOWN generation/total water. Explain the supplied-input heat-reuse contract without claiming a local heat host.
6. End with the 2030–2054 plan: verify utility/water/parcel/fiber, commission and measure, adapt to refreshed risk evidence, record replacement impacts and retire responsibly.

Useful pitch: “We built a reproducible decision framework for deciding where to investigate sustainable AI infrastructure. It searches geographic cells, evaluates complete cooling alternatives, makes preferences visible, and shows the evidence still needed before a commitment.”

## Heat-reuse input boundary

The model uses `min(IT electricity × supplied recoverable fraction × (1 − supplied losses), supplied compatible heat demand)`. It subtracts supplied auxiliary-electricity emissions from displaced-heating emissions for a **separate heating-system scenario**. Missing host/temperature/demand/factors remain null. A negative net result is added emissions. No heat result changes the original facility electricity footprint, MCDA score or lifetime inventory.

The [DOE/FEMP 2024 design guide](https://www.energy.gov/sites/default/files/2024-07/best-practice-guide-data-center-design.pdf), section 7.1, printed page 28, describes the need for a nearby heat host, suitable temperature and backup cooling when the host is unavailable. It is design guidance, not a site-specific coefficient or partner confirmation. The generated operating vision is the project's proposed plan.
