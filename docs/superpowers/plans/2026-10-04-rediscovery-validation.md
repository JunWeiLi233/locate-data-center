# Rediscovery validation against existing U.S. data centers: implementation plan (2026-10-04)

User request: generate national candidate sites from the existing deterministic model, then compare them with
real existing data centers that the model never sees. Compute hit rates against random baselines, classify
candidates as validated, emerging or unresolved, integrate Monte Carlo robustness where it exists, and present
all of this in the map frontend with a guided demo.

## Findings from the architecture inspection

| Need | Existing component reused |
|---|---|
| National evaluation of every CONUS location | `runs/national_fine_regional_v1/national_fine_surface/`: 7,829,373 CONUS 1 km cells with native features. `dc_locator.model.fine_selection.score_window` is the model's own decision value. Recomputing it exactly reproduces every persisted parent best score and best cell (6,746 parent/design pairs, max difference 0.0). |
| Factor definitions and weights | The run's `profile_snapshot.json` (`reduced_geography_annual_regional_v1`). It has five criteria in four equal groups: grid CO2e (eGRID), site water and basin stress (Aqueduct), transmission proximity (EIA) and suitable land (NLCD). |
| Declared weight sensitivity | The run's `config_snapshot.json` `run.validation.cases`: energy, water, infrastructure and land focus. |
| Grid / IDs / CRS | Fixed EPSG:5070 1 km grid (`grid_regional.yaml`). Cell centres use the grid contract, and `grid_id` order equals `(row, col)` order. |
| Monte Carlo | The separately developed county model `backend/dataclocator` has 45 counties, nine structural scenarios and completed runs with Pareto-frontier frequencies. There is no grid-cell Monte Carlo yet. |
| Map | `frontend/src/map/CandidateMap.tsx` handles the basemap, globe, camera and errors. A small overlay hook adds point layers. |
| API | The `frontend/server/app.py` loopback bridge gets two read-only routes. |

Constraints found:

- Another agent is running a regional pipeline in this checkout. `Pipeline.verify_binding()` fails a running
  job if any `src/dc_locator/**/*.py` file is added or changed. The new code therefore lives in a separate
  package, `src/dc_rediscovery/`. This follows the precedent of `src/dc_locator_fast.py`: it imports the
  model read-only, and the model never imports it. This also enforces the no-leakage rule.
- Nothing may be installed into `.venv`, because the environment identity is bound.
- Memory is shared, with about 4.5 GB free. Stream the 59 row groups and keep compact arrays, with a peak
  of about 1 GB.

## Existing data-center dataset

IM3 Open Source Data Center Atlas v2026.02.09 (PNNL, DOE), DOI 10.57931/3017294, ODbL, derived from OpenStreetMap.
MSD-LIVE file downloads need a login, so that route is not used. The publisher's own repository
`IMMM-SFA/datacenter-atlas` has the same database at commit `74ab37d5b9d200400a01639f9ffc3c3a8b716314`:
`data_center_database/im3_us_data_center_locations.gpkg`, 843,776 bytes. That commit message is
"Updated existing dc db, citation, doi link". It is pinned by commit and SHA-256 under
`data/raw/im3_datacenter_atlas/`. The file holds 1,479 rows and 1,474 unique OSM ids. After the CONUS filter,
1,472 facilities remain. Fields are name, operator, county, state, lat/lon, footprint type and sqft. There is
no city field, so city stays null.

## Method

1. Candidate generation (no facility input). Score every valued 1 km cell with `score_window`. Per-criterion
   normalized values come from one-hot weight calls of the same function, and their weighted sum is checked
   against the direct score in every row group. Each cell keeps its best cooling design. Cells are ranked by
   score, with ties broken by `grid_id`. Greedy non-maximum suppression with a configurable
   `min_candidate_distance_km` (default 25, haversine) keeps the strongest representative. The resulting
   lists are prefix-consistent, so Top-10/50/100/250 are prefixes of one list.
2. Spatial validation. Distance to the nearest facility uses haversine (spherical, R = 6371.0088 km) on unit
   vectors with an exact chord-to-arc conversion. HitRate(r, N) is computed for r = 10/25/50/100 km and
   N = 10/50/100/250. Facility recall and hub recall are computed too. Hubs are single-linkage clusters of
   facilities. A presence–background check reports each facility cell's score percentile and the AUC
   against all valued cells.
3. Baselines. These are repeated seeded draws with the same separation rule:
   - `uniform_conus`: area-uniform over valued cells.
   - `infrastructure_plausible`: mapped transmission within 10 km and suitable land of at least 0.5. Both
     thresholds are declared assumptions.

   Each comparison reports the mean, a 95% interval, lift and the one-sided empirical p value
   (1 + #draws ≥ model) / (1 + draws).
4. Classification, with configurable thresholds: validated ≤ 25 km, emerging > 50 km, otherwise unresolved.
5. Robustness. A provider interface supplies `robustness_score` (0–100) or null with a reason:
   - A county Monte Carlo adapter reads a completed `dataclocator` run. Its support is county level and it
     is labeled as such.
   - A table contract is reserved for a future grid Monte Carlo.

   Deterministic declared weight-case retention is reported separately and is not Monte Carlo.
6. Explanations. Text is generated in the backend from the factor normalized values and their national
   percentiles. Unscored factors (fiber, climate, hazards, energy cost) are listed with reasons, never as
   zero.
7. Artifacts go to `runs/rediscovery_v1/`: candidates, facilities, summary JSON, baseline draws, a report and
   a manifest with input and output hashes. `GET /api/rediscovery` and `GET /api/rediscovery/{id}` serve them.
8. Frontend. A "Rediscovery check" view reuses the map. It has blue existing data centers, red candidates,
   purple validated and orange emerging points with toggles, candidate details with a factor breakdown and
   the generated explanation, a validation dashboard (hit rates, baseline chart, counts, Top-10 table) and a
   guided 10-step demo. A mockup is approved first (user preference).
9. Tests cover hand-calculated haversine, suppression, hit rates, baselines, classification, explanations,
   providers and a leakage guard. Frontend vitest covers the parser and components. Docs cover sources,
   methodology, limitations, the dictionary, the handoff, `runs/README` and the API contract.

## Interpretation guardrails

Candidates deserve further investigation under the stated assumptions. They are not buildable parcels or
optimal sites. Existing facilities are imperfect, incomplete ground truth: OSM is crowd-sourced, and siting
reflects history, markets, latency, tax and company factors this model does not capture. A candidate far from
existing facilities is not shown to be suitable, and one near them is not shown to be correct.
