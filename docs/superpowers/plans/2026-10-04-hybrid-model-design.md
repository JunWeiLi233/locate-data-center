# Hybrid grid and uncertainty model — proposed design

Status: independently reviewed and approved by the user on 2026-10-04: "Approve; make
Hybrid default." Technical review found no remaining scientific/security design blocker
after the documented corrections; implementation verification remains required.

## Objective and chosen approach

Build one hybrid workflow that uses the deterministic grid model for geographic discovery,
screening, cooling-design physics, contextual evidence and stated preferences, then applies
the county model's uncertainty, lifetime accounting, CVaR and Pareto methods to those same
grid alternatives. Preserve the existing Grid and County modes for comparison and reproducibility.
Add a Hybrid mode and make it the new default after acceptance; explicit older model URLs
continue to select their respective models.

Three approaches were considered:

| Approach | Benefit | Limitation |
|---|---|---|
| Grid alternatives with design-specific uncertainty (recommended) | Fine geography, full saved grid domain, separate cooling designs, lifetime risk and physical tradeoffs | Requires a new frozen bridge and clearly disclosed uncalibrated sensitivity assumptions |
| County-first shortlist followed by grid refinement | Small computation | Reintroduces the arbitrary 45-county coverage restriction and can exclude promising grid areas |
| Average the models' rankings/scores | Simple presentation | County has no scalar score; incomparable quantities and unknown evidence would be hidden |

The hybrid will not average scores, fit preferences to existing data-center locations, or
create a probability of buildability. Regions deserve further investigation under the stated
facility requirements, datasets, constraints, assumptions and decision preferences.

## How each model addresses the other's limitations

| Existing limitation | Hybrid correction |
|---|---|
| County model evaluates only 45 selected counties | Use every published region/design alternative in the selected completed grid run |
| County geographic averages obscure local eGRID/land/water variation | Use the exact representative native grid evidence and retain full region/member context |
| Shared absolute PUE/WUE erase cooling-design differences | Anchor each alternative to its own grid PUE/WUE; dry cooling's zero modeled consumption remains zero |
| Grid model exposes annual point calculations | Add separate lifetime price/carbon scenarios, input-sensitivity distributions and upper-tail CVaR |
| Grid preference scores can look certain despite incomplete feasibility | Preserve hard screening and critical UNKNOWN; show physical uncertainty/frontiers beside the explicitly labeled grid preference score |
| Missing costs in the grid and missing jurisdictions in county price outputs | Normalize all 51 jurisdiction price anchors from the already verified official EIA workbook |
| National-scale all-pairs Monte Carlo would exceed resources | Compress only exact physical-equivalence classes and expand results back to every alternative |

Some weaknesses require additional evidence, not model combination: utility capacity,
water commitments, parcel/zoning, diverse fiber, calibrated cooling distributions, hourly
weather response, marginal/future emissions, full TCO, embodied carbon and generation water.
They remain unknown or explicitly outside the model boundary.

## Geography, screening and candidate identity

Use native, checksum-bound grid artifacts, not the county's selected candidate list or the
frontend's representative-only JSON as scientific input. Candidate records retain region ID,
representative grid ID, grid definition, facility ID, design ID and `native_grid_scenario_id`.
Keep `rate_scenario_id` as a separate axis in every output/cache/API identity; never replace
the native scenario with a rate label. Each frontier compares alternatives within exactly
one native grid scenario × rate scenario, never across external scenarios.
Join complete keys and verify real-data/schema/configuration identity. Retain region geometry,
member IDs, all member screening/eligibility, source-valid masks, region land checks and provenance.
Unscreened national fine values never become screened hybrid candidates.

The two existing completed universes are supported separately, never silently unioned:

- `runs/cleanview_regional_v2`: 2,326 region/design alternatives, 152,500 analyzed native cells,
  61 refined parent windows; nationwide representative selection.
- `runs/national_fine_regional_v1`: 5,748 alternatives, 131,945 analyzed native cells,
  61 refined parent windows; global best-fine-window selection.

Initial Hybrid display uses the completed nationwide representative view to preserve geographic
spread; the user can select the other completed grid view. Coverage remains partial. New facility
searches go through the existing grid service and its declared selection policy, then uncertainty
analysis; a saved grid run is never reused for a mismatched facility or preference configuration.

Every hard FAIL remains excluded before uncertainty evaluation. A saved grid run's screening
mode is immutable; a STRICT request binds a matching completed STRICT grid run, never relabels
an EXPLORATORY run under the same identity. STRICT excludes critical UNKNOWN and legitimately
yields an empty result. The initial saved view is explicitly EXPLORATORY and conditional.
Monte Carlo cannot turn
missing utility/parcel evidence into PASS. An alternative missing a required physical anchor
retains its grid context with assessment `NOT_ASSESSED`, null uncertainty outputs, a missing
reason, and no physical frontier membership. Retain every published source alternative in
the output, including physically excluded alternatives. Report comparison-domain count and
all exclusions explicitly; unranked native cells are not published hybrid alternatives.

## State prices and historical anchors

Read the representative cell's native part-table `state_fips_primary`, `state_abbr_primary`,
`state_share_primary_frac`, `state_fips_all` and `n_states`, preserving source/method evidence.
Require a unique row keyed by representative grid ID. Do not infer state from a region centroid,
region label, first county string or rolled-up frontend response. Bind the official GENZ2023
1:500,000 state archive/hash and attribution method: largest full-cell intersection area in
EPSG:5070, with lowest-FIPS tie-breaking. Retain cross-state/member-state ambiguity and use
the label **representative-grid primary-state 2025 industrial retail-price proxy**. Expose
cross-state representative flags (currently 12/2,326 nationwide and 18/5,748 latest). Sector
is industrial; any future selectable sector must enter input and equivalence-class identity.

The existing official EIA `monthly.xlsx` checksum is
`f50ac9dcdcb1b8656e543927e9301bbb87288b1821c1d00ffa52e0902e77e4a0`.
It contains all 50 states and DC with 12 valid 2025 industrial months, all marked Preliminary.
Normalize the full-state, sales-weighted annual USD/MWh baseline independently; existing county
processed tables omit CT/NJ/RI/DC. State code mapping comes from verified official Census
geographic identifiers. No new download or negotiated utility-price claim is needed. These
are 51 jurisdictions, not 51 states; Alaska and Hawaii remain normalized but unused by the
CONUS candidate domain.

Use only `grid_carbon_intensity_kg_per_mwh` as each alternative's historical EPA eGRID 2023
carbon anchor, including exact shares, coverage and ambiguity. Recompute sampled facility
energy × the intensity/pathway. Do not use already-PUE-adjusted annual `c_electricity_kg`
or tonnes as an intensity or multiply them by PUE again. Preserve the native proxy status,
source year, coverage, shares and ambiguity. Preserve source years independently: prices extrapolate from 2025,
carbon from 2023, and discount timing follows the declared 2025 currency base. The 2025
observed nominal price is the base-year anchor; the default demonstration scenario treats
subsequent growth and the discount rate as real rates in constant 2025 USD. This is an
explicit scenario convention, not an inflation forecast. Nominal scenarios require nominal
growth/discount rates and separately named output units. Derivations
are calculated from historical/proxy/scenario inputs, not observed future quantities.
Do not compound a decline rate on an already decarbonized future factor. Initial support
requires the historical-static native grid context; independently transformed grid futures
are rejected until their annual paths can be composed without double counting.

## Design-specific uncertainty and assumptions

Grid annual PUE/WUE are retained as nominal scenario inputs. Use the county engine's named,
seeded latent draws and inverse-CDF sampling. The proposed default is a clearly labeled
**uncalibrated engineering sensitivity** using its existing demonstration priors. This is a
new declared project assumption about transferring those priors, not a sourced calibration.

For nominal grid PUE P and WUE W, the sensitivity transformation is:

\[P^{(s)}=1+(P-1)\frac{P_{ref}^{(s)}-1}{P_{ref,mode}-1},\qquad
W^{(s)}=W\frac{W_{ref}^{(s)}}{W_{ref,mode}}.\]

Reference distributions come from the existing explicitly unconfirmed county configuration.
This applies uncertainty to cooling overhead, keeps PUE >= 1, preserves each design's nominal
values at the reference mode, and keeps W=0 exactly zero. Validate denominator/domain rules;
reject an unusable reference prior instead of clamping or silently imputing. Also provide a
fixed-design mode and explicit per-design priors; preserve WUE's IT/facility energy basis and
consumption/withdrawal boundary. Source/status/confidence must describe the transformation.

Shared latent quantiles are a disclosed dependence assumption for paired alternatives, not
measured correlation. PUE/WUE factor-dependence settings are distinct from cross-area
dependence. The initial default shares each factor's named stream across alternatives.
Independent per-area streams are deferred from the initial implementation. Do not add
independent area noise to manufacture ranking variation. PUE-versus-WUE independence or
comonotonicity remains a selectable declared assumption, shared across all alternatives.
The same workload/hours/lifetime must match the grid snapshot exactly: 100 MW IT,
load 0.80, 8,760 h/year, `target_opening_year=2030`, `operating_lifetime_years=25` for the
current saved universes. County demonstration values 2027/0.85 never enter. No peak-demand,
temperature-response or generation-water probability is invented.

Every representative native grid in both saved universes currently has null temperature
normals with status `unknown`, coverage zero and missing reason `not_computed`. Preserve
this as unavailable. Do not transfer county-station temperature onto grid alternatives or
infer a cold-climate benefit, hourly cooling response or temperature-conditioned PUE/WUE.

Use separate existing price-growth/carbon-decline structural scenarios without mixture weights.
The initial selected pathway is `price00_carbon00`, the no-change control compatible with
the historical-static baseline. The other eight are individually selectable sensitivities.
Clearly distinguish conditional input intervals from Monte Carlo estimator intervals, CVaR
from a failure probability, and frontier frequency from a probability of being best.
Physical objectives remain discounted lifetime electricity expenditure (not full TCO),
undiscounted lifetime operational electricity CO2e, and direct cooling-water consumption.

For annual IT energy E, opening year o, lifetime L, sampled PUE P and IT-based WUE W,
state price anchor c, local carbon anchor b, price growth g, carbon decline r and discount
rate d, the accounting is explicit:

\[
E=\mathrm{IT\ MW}\times\mathrm{load\ fraction}\times\mathrm{annual\ hours},\quad
C=EP\sum_{y=o}^{o+L-1}\frac{c(1+g)^{y-2025}}{(1+d)^{y-2025+1}},\quad
B=\frac{EP}{1000}\sum_{y=o}^{o+L-1}b(1-r)^{y-2023},\quad
Q=EW L.
\]

E is MWh/year, C is discounted 2025 USD under the default real convention, B is tonnes
CO2e and Q is m3 of direct consumption. Facility-based WUE uses EP in place of E for Q.
The existing demonstration settings (5% real discount, 95% upper-tail CVaR, nine separate
0/1/2% price-growth × 0/2/5% carbon-decline sensitivities, 5,000 draws, seed 42, and the
existing numerical tolerances) remain explicitly labeled project assumptions and user
adjustable; 5% real discount is a declared project assumption, not an observed rate or an
inference from EIA. Grid workload replaces the county demonstration's 85% load; the accepted
saved grid workload is 80%, yielding 700,800 IT MWh/year. Nothing is fitted to existing sites.
Baseline water stress remains context only. Never multiply direct WUE consumption by stress
or treat stress as a supply commitment. Q is identical across areas within a design under
the current assumptions and distinguishes cooling designs only.

With the current shared factor streams and constant scenario rates, each objective is a
positive common scaling of its underlying anchor. Dominance is consequently invariant
across draws, except possible numerical absolute-tolerance effects. Current dry and tower
designs both assume PUE 1.2; dry water is zero and tower water is positive, so the dry twin
dominates the tower twin on these three objectives. Expected and CVaR frontiers should
coincide and per-draw frontier frequencies should be 0/1 under exact dominance. Disclose
this consequence and test it. Frequencies and estimator intervals are conditional numerical
summaries, never site/rank confidence; varied values caused only by tolerance are labeled
numerical effects. Distributions and CVaR still quantify the stated input sensitivity.

## Exact computation and resource limits

Screen individual alternatives first. Group only exact physical-equivalent inputs: numeric
workload/design/anchor values, anchor years/currency, effective per-design priors, resolved
rate scenarios/overrides, dependence and named latent streams. No rounding, bins, approximate
spatial averages or preferred-area truncation. Geometry, IDs, screening and per-alternative
provenance stay separate and are never replaced by a class representative's evidence.

The measured existing-input class counts are 140 for 2,326 nationwide alternatives and 54 for
5,748 global fine alternatives when state/eGRID-share/source ambiguity is retained. Final
counts also include price/prior/pathway identity and are measured, not assumed.

Evaluate all unique classes for each separate external scenario. Exact duplicate outcomes have
identical dominance relations under the county's symmetric numerical tolerances; expanding
class outcomes preserves all area/design results and estimator summaries. Candidate-block and
draw-block comparisons accumulate global dominated flags across every block. Never union
independent block frontiers or prune intermediate dominated classes: tolerance dominance may
be nontransitive. Stream scenarios and bounded class arrays; enforce the ~4 GiB process budget.

## Runtime, cache and interfaces

Create an additive hybrid backend within `backend/`, with separate geography, model and service
responsibilities. Reuse the installed county package's pure draw/statistics/Pareto kernels in
its Python 3.13 environment. Grid search stays in Python 3.12. Exchange versioned immutable
data, not dependency environments; keep legacy grid and county APIs/contracts unchanged.

The hybrid coordinator accepts one facility/preferences/uncertainty request, waits for a valid
matching grid run when needed, freezes the native evidence and evaluates uncertainty. The UI
performs presentation and transport only. Hybrid run outputs go under new owned `runs/` paths;
full-state derived price geography goes in an isolated real-data `data/processed/` namespace.
Client base-run inputs are opaque server-registered completed run IDs, never arbitrary
filesystem paths. Resolve only within allowlisted run roots and verify completion, native
freeze and artifact hashes before reading. Enforce existing validated draw/scenario limits.

Hybrid identity binds grid geometry/definition/membership/native artifact checksums, source
records, cooling/facility/preferences, anchor years, priors/rates/dependence, seed/draw count,
tolerances/audit flags, and hybrid/shared-kernel/environment hashes. Freeze inputs before enqueue.
Write completion last; validate identity, frozen evidence and every required output hash on reuse,
polling and exports. Missing/corrupt/shared input and per-run corruption return distinct useful
errors. Retain deterministic ordering and prefix-stable named streams.

## Application behavior

One Hybrid workspace displays grid polygons and evidence together with the added lifetime
distributions, expected/CVaR physical frontiers and conditional frontier frequency. Keep the
original score explicitly labeled **grid preference score**, with its original weights and
exclusions. No blended hybrid scalar score or new automatic weighting is added. Optional
physical-frontier filters help the user compare tradeoffs without redefining geographic screening.
Frontier/risk filters default OFF so the current dry-dominated tower designs remain inspectable.

Preserve grid land/water/infrastructure context, existing county economic filters, geometry,
native coverage notices, source inspection and scenario-specific cooling alternatives.
Economic data use the existing independent grid service's county context transport, preserving
its estimate vintage, geography mapping and unavailable values. Economic display filters
do not change physical frontiers, grid scores, technical screening or decision weights.
Every hybrid response exposes its bound `source_grid_run_id`. The hybrid API proxies the
grid economic endpoint using that exact source ID; a hybrid run ID is never passed as a grid
run ID. Reject stale/mismatched context and disable unavailable economic layers.
Unsupported quantified risk remains unavailable. Changing model/base run/scenario resets
bound selections and prevents stale responses from crossing workspaces. Grid and County
remain selectable, and explicit URLs retain their existing behavior.

## Acceptance criteria

1. Hand-calculated fixed-prior/no-change fixtures reproduce annual grid physics, workload,
   water basis, lifetime sums and declared discount timing. Dry and tower designs remain distinct.
2. Missing anchors remain null; FAIL/critical UNKNOWN/STRICT behavior cannot be compensated;
   invalid IDs, duplicate joins, mixed facilities/scenarios, units and source years are rejected.
3. Full-state EIA normalization reproduces official monthly-to-annual math, complete-year
   requirements, Preliminary status and CT/NJ/RI/DC coverage with pinned raw/source metadata.
4. Compressed/expanded summaries and exact global frontiers equal uncompressed hand/synthetic
   fixtures for ties, zero water, nonzero tolerances, permutation and prefix draws. Blocked
   results match the original kernel, including nontransitive tolerance cases. The current
   common-factor fixture has invariant exact frontiers and dry dominates its tower twin;
   null temperatures never affect engineering calculations.
5. Deterministic cache tamper, stale source/code/config, cross-run adoption, interrupted writes
   and process restart checks pass; real-data mode never falls back to synthetic data.
6. Real runs cover all published alternatives in both completed grid views, retain geometry,
   scores/critical UNKNOWN and source evidence, and record actual class counts/runtime/memory.
7. Full relevant backend/frontend regression tests and production build pass. Browser proof
   shows the hybrid applied with cooling differences, uncertainty, source years and conditional
   feasibility. Existing grid/scenario/economic-filter behavior remains reviewable.
8. New revision/source/schema documentation, independent review, phase handoff/completion record,
   run index, source/output hashes and owned-scratch cleanup are complete.

## Approved decision

The user approved this written design, including Hybrid as the new default and the explicitly
labeled uncalibrated sensitivity transformation. Proceed through implementation, review,
verification and application; preserve the legacy comparison modes.
