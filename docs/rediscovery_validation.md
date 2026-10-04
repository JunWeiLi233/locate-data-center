# Rediscovery check: blind national candidates versus existing U.S. data centers

**Question.** Can infrastructure and geographic data independently rediscover existing U.S. data-center hubs,
while also identifying potentially overlooked locations for future development?

> These geographic regions deserve further investigation under the stated facility requirements, datasets,
> constraints, assumptions, and decision preferences. They are NOT proven buildable parcels and NOT
> "America's objectively best place to build a data center." The comparison with existing facilities provides
> an external sanity check on the geographic suitability model. It is not proof that the model is right.

This is a post-hoc validation layer. It is not a model for locating existing data centers. Existing facilities
never enter the score. They are revealed only after the model's candidates are generated and hashed.

## Components

| Path | Role |
|---|---|
| `src/dc_rediscovery/` | Separate read-only package. `dc_locator` never imports it. It lives outside the hash-bound `src/dc_locator/**` inventory (`Pipeline.verify_binding`), following the `src/dc_locator_fast.py` precedent. |
| `configs/rediscovery.yaml` | Declared configuration. Every threshold has a basis and rationale. |
| `runs/rediscovery_v1/` | Analysis outputs and checksum ledger (`rediscovery_manifest.json`). |
| `frontend/server/rediscovery.py`, `frontend/server/app.py` | Read-only API: `GET /api/rediscovery`, `/api/rediscovery/{id}`, `/api/rediscovery/{id}/surface.png`. |
| `frontend/src/components/rediscovery/`, `frontend/src/map/overlays.ts` | The **Rediscovery check** view (header switch), map layers, dashboard, details and guided demo. |
| `tests/test_rediscovery_*.py`, `frontend/server_tests/test_rediscovery_api.py`, `frontend/src/**/rediscovery*.test.ts(x)`, `ViewSwitch.test.tsx` | Tests. |

## Commands (project root, PowerShell)

```powershell
.venv\Scripts\python.exe -m dc_rediscovery acquire                     # pinned public inventory → data/raw/im3_datacenter_atlas/ (once, verified)
.venv\Scripts\python.exe -m dc_rediscovery run --output runs/rediscovery_v1   # ~1.5 min, peak ~1 GB; reuses a verified identical folder
.venv\Scripts\python.exe -m pytest tests/test_rediscovery_geodesy.py tests/test_rediscovery_validation.py tests/test_rediscovery_baselines.py tests/test_rediscovery_robustness.py tests/test_rediscovery_explain.py tests/test_rediscovery_leakage.py tests/test_rediscovery_pipeline.py frontend/server_tests/test_rediscovery_api.py -q -p no:cacheprovider --basetemp=.pytest-work/rediscovery-tests
```

The view needs the local API restarted once so that it loads the new routes. Restart it only when no
search job is RUNNING (`GET /api/jobs/{id}`). Then open `http://127.0.0.1:5173/?view=rediscovery`, or use
**Rediscovery check** in the header.

## Data sources

| Role | Source | Version and identity | Notes |
|---|---|---|---|
| Model evaluation (input to candidates) | Completed run `runs/national_fine_regional_v1` national 1 km fine surface | `fine_surface_cells.parquet` sha256 `0954e3c5…`, profile `reduced_geography_annual_regional_v1`, scenario `historical_static_2023` | 7,829,373 CONUS 1 km cells; 7,768,145 have a score. Criteria: EPA eGRID 2023 carbon, WRI Aqueduct 4.0 basin stress, EIA mapped transmission, USGS Annual NLCD 2024 land cover. |
| External validation only | **IM3 Open Source Data Center Atlas**, PNNL / DOE | v2026.02.09, doi:[10.57931/3017294](https://doi.org/10.57931/3017294). File `im3_us_data_center_locations.gpkg` from [IMMM-SFA/datacenter-atlas@74ab37d](https://github.com/IMMM-SFA/datacenter-atlas/commit/74ab37d5b9d200400a01639f9ffc3c3a8b716314), 843,776 bytes, sha256 `1c0d8c20…cc9f4`, retrieved 2026-10-04 | ODbL 1.0, derived from OpenStreetMap (attribution: © OpenStreetMap contributors; IM3/PNNL). MSD-LIVE file downloads need a login, so they were not used. The publisher's repository commit, "Updated existing dc db, citation, doi link", has the same release, and its About page cites this DOI. 1,479 rows (point 105, building 1,239, campus 135); 1,474 OSM ids; 1,472 CONUS records after excluding 2 in Puerto Rico. |
| Presentation labels | Census cartographic county boundaries 2025, 1:500,000 | already cached, `data/raw/census_frontend_boundary/areawater/cb_2025_us_county_500k.zip` (manifest-verified) | Labels only, such as "Clinton County, NY". They are not evidence. |
| Robustness (Monte Carlo) | County model `backend/dataclocator` run `run_cd852d91e1161103` | 5,000 draws, 9 structural scenarios, exploratory, integrity-verified `results.json` | 45 counties. The value is county-level. |

Coverage and limits of the inventory:

- It is crowd-sourced, so absence is not evidence.
- A campus and its buildings can both appear.
- Records range from small colocation rooms to hyperscale campuses.
- Capacity, operating status and opening date are not provided.
- It has no city field. City stays null and is never inferred.

## Method

1. **Blind candidate generation** (`surface.py`). This step has no facility input.
   - Each of the 59 row groups is scored once with the model's own `score_window`, using the run's
     archived profile, weights and design constants.
   - Per-criterion normalized values come from the model's `normalize_values` on the same raw quantities.
     The pipeline refuses to continue unless, in every row group, their weighted sum equals the direct
     score. Measured maximum difference: 0.0.
   - Per-parent best scores are compared with the persisted `fine_surface_parents.parquet`: 3,373 parents,
     maximum difference 0.0.
   - Each cell keeps its best cooling design (ties go to the lexically first design). Cells are ranked by
     score, with ties broken by `grid_id`, the model's convention.
2. **Geographic deduplication.** Greedy non-maximum suppression walks the ranked cells and keeps a cell only
   when it is at least `min_candidate_distance_km` (25 km) from every cell already kept.
   - The first cell of each neighbourhood, which is the strongest, is the representative.
   - The procedure is prefix-consistent, so Top 10/50/100 are prefixes of the 250-candidate list.
   - Distances are haversine on a sphere of R = 6371.0088 km. Against WGS84 the error is at most about 0.5%,
     and a test checks this bound.
   - `candidates_blind.parquet` is written and hashed at this point, before the inventory is opened. The
     manifest timeline proves the order.
3. **Spatial validation** (`validation.py`). Each candidate gets its nearest facility (k-d tree on unit
   vectors, exact haversine), the facility counts within each radius, and:
   - **HitRate(r, N)**: the share of the first N candidates within r km (inclusive), for r = 10/25/50/100
     and N = 10/50/100/250.
   - Facility recall and hub recall. A hub is 5 or more records linked by gaps of 10 km or less.
   - Presence–background statistics: the score percentile of each unique 1 km cell that holds a facility,
     and the AUC against all valued cells (Mann–Whitney, ties count ½).
4. **Baselines** (`baselines.py`). Each control uses 1,000 seeded draws with the same N, the same
   separation and prefixes of one draw.
   - `uniform_conus`: area-weighted over valued cells.
   - `infrastructure_plausible`: mapped transmission within 10 km and suitable land of at least 0.5. These
     thresholds are declared assumptions. This control is the "geographically reasonable" null.
   - Each comparison reports the mean, the 95% range, lift and a one-sided empirical
     p = (1 + #draws ≥ model)/(1 + draws).
5. **Tie sensitivity** (`ties.py`). 855 cells share the maximum score, so the Top-N order inside that block
   is arbitrary. Selection is repeated over 200 seeded random tie orders. The published ranks are unchanged.
6. **Classification.** Validated means the nearest facility is 25 km or less away. Emerging means it is more
   than 50 km away. Anything else is unresolved. The thresholds are configurable.
7. **Robustness** (`robustness.py`). A provider returns `robustness_score` 0–100 or null with a reason.
   - The `county_monte_carlo` provider gives 100 × the mean Pareto-frontier frequency of the candidate's
     county across separate structural scenarios. The value is county-level, comes from that model's
     45-county cohort and uses different objectives (cost, CO2e, water).
   - The `table` provider is the reserved contract for a future grid-cell Monte Carlo: `grid_id`,
     `robustness_score`, `method`, `source` and `draws`.
   - Without evidence the value stays null. It is never invented.
   - Separately, *declared weight-case retention* counts how many of the run's pre-declared weighting cases
     (energy, water, infrastructure and land focus) also select a candidate within 25 km in the same Top-N
     bucket. This is a deterministic sensitivity check, not Monte Carlo.
8. **Explanations** (`explain.py`). Text is generated from each candidate's own normalized criteria.
   - A criterion is a strength at 80 or more and a weakness at 50 or less (declared presentation rule).
     Strengths are ordered by contribution.
   - The cooling-design water term is stated as a design assumption, not a property of the place.
   - Fiber, climate, hazards and energy cost are stated as not scored.

## Results (`runs/rediscovery_v1`, analysis identity `c890d8e7…`)

The published order (grid_id tie order) gives these hit rates:

| Top N | ≤ 10 km | ≤ 25 km | ≤ 50 km | ≤ 100 km |
|---|---|---|---|---|
| 10 | 0.0% | 0.0% | 0.0% | 0.0% |
| 50 | 6.0% | 20.0% | 40.0% | 62.0% |
| 100 | 3.0% | 11.0% | 25.0% | 61.0% |
| 250 | 3.2% | 8.0% | 17.6% | 48.4% |

The same Top 100 against the random controls (mean over 1,000 draws, one-sided p):

| Within | Model | Random CONUS | Random near-transmission land |
|---|---|---|---|
| 10 km | 3.0% | 1.4% (p 0.158) | 1.9% (p 0.278) |
| 25 km | 11.0% | 5.8% (p 0.021) | 7.5% (p 0.133) |
| 50 km | 25.0% | 16.8% (p 0.027) | 20.8% (p 0.185) |
| 100 km | 61.0% | 43.7% (p 0.001) | 50.5% (p 0.025) |

- **Classification of the Top 100:** 11 validated, 14 unresolved, 75 emerging. For the Top 50 it is 10, 10
  and 30. For the Top 10 it is 0, 0 and 10.
- **Tie sensitivity:** the first 73 candidates come from the 855-cell maximum-score block in upstate New
  York. With random tie order, Top-10 HitRate@25 km averages 22.2% (range 10–40%). The published order
  gives 0%, because grid_id order runs north first, toward the Canadian border. The Top 100 is insensitive
  to tie order: 10.5% (8–13%) against 11%.
- **Presence–background:** the 774 valued 1 km cells that hold a facility have a median score percentile of
  72.4 and an AUC of 0.717 (chance 0.5). 81% of them lie above the national median. Under the declared
  infrastructure-focus weights the AUC is 0.774; under water focus it is 0.651.
- **Hubs:** none of the 50 hubs (1,098 records) is within 50 km of the Top 50. One is within 50 km of the
  Top 100 and two of the Top 250. Northern Virginia, Silicon Valley, Phoenix, Dallas and Columbus are not
  near the model's top tier.
- **Robustness:** 2 of the Top 100 fall in a county the Monte Carlo model evaluated (Oneida County, NY,
  frontier in 9 of 9 scenarios, so 100). The rest are null with reasons. All Top-10 candidates are retained
  under all 4 declared weighting cases.

**Interpretation.** The model was never shown where data centers are, yet it ranks the places that hold
facilities clearly above typical U.S. land (AUC ≈ 0.72). Its Top 50–100 also lie near existing facilities
two to three times more often than random CONUS locations. That advantage shrinks against random
near-transmission land, so part of the alignment comes from basic infrastructure plausibility. The model's
top tier is driven by a low-carbon, low-water-stress grid region (eGRID NYUP) where transmission proximity
and land saturate, and it points to upstate New York. That region has little existing development: these
are the *emerging* candidates. The model does **not** rediscover the major existing hubs in its top tier.
Those hubs reflect latency, markets, fiber, tax policy and history, which this model does not score. An
emerging candidate deserves engineering, economic, regulatory and site-level due diligence. It is not shown
to be suitable for construction.

## Limitations

- Candidates come from the **unscreened** national 1 km valuation. Parcel availability and zoning, utility
  capacity and interconnection, committed water, diverse fiber and hazard clearance remain unverified.
- Regional proxies (eGRID subregion carbon, Aqueduct basin stress) create large tie blocks. The published
  tie order is arbitrary, and the tie-sensitivity table shows how much it matters.
- Existing facilities are an incomplete, crowd-sourced (OpenStreetMap-derived) reference with mixed sizes.
  They are not ground truth for suitability. Hit rates are agreement statistics, not accuracy.
- The controls account for spatial chance and for transmission/land plausibility, but not for population,
  fiber, land price or incentives.
- Monte Carlo robustness is county-level, covers 45 selected counties and uses different objectives. Grid-cell
  Monte Carlo has not been supplied, so those values stay null.
- Candidate coordinates are 1 km cell centres. A coastal or border cell's centre can fall outside land, and
  such a candidate takes the nearest county label within 5 km.
