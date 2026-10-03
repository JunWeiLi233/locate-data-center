# Temporal context and lifecycle accounting

The cached official Aqueduct 4.0 archive is 261,527,511 bytes, SHA256
`bd3ed2bce88d6ff1b89191632ad134a2436e1e1d49599382f23a04d513624fc3`,
retrieved 2026-10-03T01:39:00Z. Native `future_annual` has 16,395 unique `pfaf_id`
rows, 182 CSV columns and 180 future fields. Its native GDB geometry is EPSG:4326.
The adapter reads the bounded study envelope and computes exact intersections in
EPSG:5070, using the same Census study intersection as the accepted baseline.
The boundary includes mapped water; it is not a developable-land boundary.

[WRI's future-projection documentation](https://www.wri.org/aqueduct/help-center/understanding-future-projections)
defines 2030, 2050 and 2080 as trend milestones with windows 2015–2045,
2035–2065 and 2065–2095. BAU, OPT and PES retain SSP3-RCP7.0, SSP1-RCP2.6
and SSP5-RCP8.5. The five-model median uses GFDL-ESM4, IPSL-CM6A-LR,
MPI-ESM1-2-HR, MRI-ESM2-0 and UKESM1-0-LL. These are basin-scale trend
contexts, not measurements in a single operating year. No native 2040 field
exists; requested 2040 remains UNKNOWN without interpolation or copying.

Direct native-field inspection established future NULL missingness. Positive
9999 in the raw stress ratio is retained as an extreme-scarcity area fraction,
excluded from an ordinary ratio mean. The baseline negative -9999 missing rule
is not applied blindly. Ratio, 0–5 score, native -1..4 category, label and
category shares remain separate metrics. Category uses area plurality with the
smallest-code tie rule. Coverage refers to valid source support divided by the
full study-intersection area; distinct overlapping basins exceeding that area
are rejected instead of silently normalized.

Twelve enhanced profiles were declared before the first future ranking in
`docs/phase_records/phase5_profiles_predeclared.json`. The baseline criterion
IDs, group/local/global weights, bounds, required leaves and selection policy
are unchanged. Only the water-stress source/time binding and explanatory text
change. Every pathway/window has its own composite external ID. New expanded
source context receives no automatic weights. Missing required water makes an
alternative unranked with the original full preference vector.

Annual periods use opening year through opening year + lifetime − 1. For the
illustrative opening 2030 and lifetime 25, that is exactly 2030 through 2054.
Without an explicit extension, only opening-year physical output has support.
The enabled `phase5.yaml` project assumption repeats opening-year annual
historical-static eGRID 2023 and constant PUE/WUE through those 25 modeled
years, each with 8,760 hours. This is not a future-grid forecast, marginal
emissions factor or actual-calendar leap-year simulation. Missing source
factors remain UNKNOWN. Site consumption, generation consumption and their
withdrawal counterparts remain distinct quantities.

Aqueduct windows are exported once per variable/alternative. NASA climate
context retains its own native model, member, SSP and year under the reserved
`source_context` design and an independent scenario ID. It is never silently
paired to every Aqueduct pathway or given a cooling response or weighted bonus.

Lifecycle calculation multiplies explicit quantities and compatible product
factors. Mass conversions are 1 metric tonne = 1,000 kg and 1 US short ton =
907.18474 kg. Volume and item factors require matching quantity families;
no density or product-specific EPD is inferred. Freight requires compatible
mass × distance × mode factors, with actual/scenario route basis. Volume/count
inventory can supply an independent freight mass. Product identities and
factor accounting modules must match the requested boundary exactly.

The gross accounting policy requires initial construction and equipment A1–A5,
electricity B6, other operations B1/B2/B3/B7, replacements B4/B5 and end of life
C1–C4. These labels define a disclosed bookkeeping boundary; they do not
supply quantities, factors or an engineering claim. Declaring an inventory
complete cannot fill unobserved modules. Freight already included in A4,
replacement B4 or end-of-life C2 needs a documented distinct additional leg.
Module D credits are unsupported. Typo scopes and unused inventory are rejected.

The real project has no supplied material/equipment inventory, product factors,
freight route/mode factors, replacement or end-of-life data. Those components
remain UNKNOWN. A known electricity subtotal is not complete operating
emissions: fuel, refrigerants and other operations are also missing. Full
lifecycle carbon therefore remains null. The named partial subtotal includes
known leaves once; an entirely unknown input yields null rather than zero,
while explicitly documented known-zero evidence remains zero. Synthetic
material/freight examples exist only in tests.

Direct persisted schemas check nonempty source/assumptions, units, coverage,
known/unknown value rules, exact required/null component sets, JSON structure
and arithmetic (relative tolerance 1e-10, absolute 1e-6 kg for roundoff).
The national workload is unvalidated; current native coverage and examples
refer only to the supplied 42-cell development grid.
