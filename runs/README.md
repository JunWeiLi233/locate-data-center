# runs/ — model run folders

Each model run writes to its own folder here (`python -m dc_locator <stage> --output runs/<name>`).
Run folders are git-ignored; only this index is tracked. Folders marked as evidence are cited by path,
often with file hashes, in `docs/phase_records/`, or they are read by the frontend. Never move, rename,
edit or delete them.

## Start here

| Folder | What it is |
|---|---|
| `national_grid_v1/` | New fixed-origin 50 km CONUS grid: 3,384 cells, all 48 contiguous states plus DC. Grid summary and native boundary provenance are retained. |
| `national_discovery_v2/` | Current national exploratory baseline (`configs/run_national_exploratory.yaml`). 5,514 rankable conditional alternatives, 122 design regions at 61 distinct geographic geometries. Preferred by the frontend over historical development runs. |
| `national_strict_v1/` | National STRICT run (`configs/run_national.yaml`). Zero ranked alternatives/regions: every alternative retains critical UNKNOWN requirements. |
| `national_repeat_v1/` | Independent repeat of the national exploratory baseline. All 38 compared files match substantively; 37 are byte-identical and only the geographic tile-resume diagnostic differs. |
| `national_audit_v1/` | National acceptance evidence: model/API audits, repeat comparison, test evidence, exact executable/config hashes and browser proof. |
| `example/` | Historical real STRICT run (`configs/run.yaml`), recorded as the accepted Phase 7 `final_default_run`. It covers 42 Texas development cells and has an intentionally empty ranking because critical requirements are UNKNOWN. Preserved and loadable. |
| `phase7/root_v2_exploratory/` | Historical accepted exploratory run (`configs/run_exploratory.yaml`) with 84 conditional alternatives and 2 Texas search regions. Preserved and loadable. |
| `frontend_service/` | Owned by the frontend API (`frontend/server`). Holds request `configurations/`, `jobs/`, `model_runs/`, `response_cache/` and `registry.json`. `server_test_tmp/` is the documented pytest temp folder for `frontend/server_tests`. |

## Accepted phase evidence (read-only)

| Folder | Phase | Contents |
|---|---|---|
| `phase3/` | 3 | Screening and annual physical-model outputs, plus an `exploratory/` variant |
| `phase4/` | 4 | First decision locator: `strict/`, `exploratory/` and their repeats |
| `phase5/` | 5 | Native-source, future-scenario and lifecycle integration (`integrated/`, `native/`, repeats, `root_final_audit.json`) |
| `phase6/` | 6 | Validation: immutable pre-holdout `freeze/`, `inputs/`, `final/`, repeats, reviews and audits |
| `phase7/` | 7 | Executable delivery: `executable_freeze_v2.json`, which hash-binds `src/` and `configs/`. Also strict/exploratory/synthetic runs and repeats by the implementer (`primary_*`), the independent reviewer (`review_*`) and the lead (`root_*`), plus artifact audits |
| `orchestrator_phase*` | 2–6 | The lead's independent repeat executions, used to check each phase's reproducibility before acceptance |
| `phase7_draft_*` | 7 | Pre-freeze Phase 7 drafts, kept as history |

The pipeline preflight blocks delivery outputs in `runs/phase1`–`runs/phase7`
(`src/dc_locator/run_config.py`, `preflight`). Project policy also protects accepted
`runs/orchestrator_*` and `runs/example`; existing immutable run bindings reject changed inputs.

Model CLI defaults use `configs/run_national.yaml` and a new `runs/national_default_v1/` folder.
If code or inputs have changed since that folder was created, supply another new output folder.

## Submission alignment evidence

| Folder | Contents and status |
|---|---|
| `submission_alignment_v1/` | Superseded pre-review draft of the six-deliverable national brief. Retained as history; use v2 for the current submission. |
| `submission_alignment_v2/` | Accepted additive Phase 10 presentation: real six-deliverable HTML/Markdown/JSON, verified national input/output hashes, implementation freeze and review/test/browser audit. Archived national scoring is unchanged; unresolved engineering and wider mission benefits remain explicit UNKNOWNs. |

## Cleanview diagnostic and land-support evidence

| Folder | Contents and status |
|---|---|
| `cleanview_revision_v1/` | Completed browser/source diagnosis and scoped model revision: independent review, execution/delivery freezes, 792 passing model/API tests, differential and repeat audits, findings and bound completion record. |
| `cleanview_baseline_comparison_v1/` | Superseded pre-review comparison draft; preserved as diagnostic history. |
| `cleanview_baseline_comparison_v2/` | Superseded comparison draft before offline reference reconstruction was added; preserved as history. |
| `cleanview_baseline_comparison_v3/` | Superseded baseline comparison with a wrong historical root-grid checksum label; input verification and scientific tables were correct. Preserved as history; use v4. |
| `cleanview_baseline_comparison_v4/` | Verified baseline comparison against `national_discovery_v2` and `regional_refinement_v4`; corrected checksum ledger, 297 public operating samples, county support only, physical accuracy null. |
| `cleanview_regional_v1/` | Incomplete, unaccepted first attempt; safely stopped at parent 5 when concurrent metric optimization changed the bound code. |
| `cleanview_regional_v2/` | Completed corrected model: 152,500 fixed 1 km cells, 304,670 conditional rankable alternatives, 2,326 region/design alternatives. Original physics/raw metrics are preserved; STRICT ranks zero. Scoped diagnostic revision accepted, without broader Phase 9 acceptance. |
| `cleanview_revised_comparison_v1/` | Verified revised-model comparison and byte-identical substantive repeat: 277 county-supported public samples nationally, 55 within the evaluated fine domain, 222 outside fine coverage, 20 unmatched. |
| `cleanview_app_v1/` | Corrected model applied to the local app: completed-run registration/default selection, historical access preserved, 107 passing API tests, all 2,326 native alternatives verified, and browser proof showing 1,163 search areas. Scientific files and saved model outputs preserved. |

## Starting a new run

Use a new, descriptive folder, e.g. `runs/2026-10-05-exploratory-check/`. Re-running into the same folder
with identical code, configuration and sources verifies and resumes it. If any of those changed, the
pipeline rejects the folder, so use a new one. Delete scratch runs when you are done. If you keep a run as
evidence for a decision, add a row to this index.

## Regional revision handover (goal paused by user)

| Folder | Contents and status |
|---|---|
| `regional_geography_v1/` | Completed real source-only geography: 61 parent windows, 152,500 fixed 1 km cells; independent geography audit passed. |
| `regional_refinement_v3/` | Failed, unaccepted full attempt: final process peak exceeded 4 GiB; no completion metadata published. Preserved for diagnosis. |
| `regional_repeat_v1/` | Failed, unaccepted repeat attempt under the same old validation memory behavior. |
| `regional_strict_v1/` | Completed earlier strict empty-result check; historical code binding superseded, not the current regional delivery. |
| `regional_refinement_v4/` | Completed real regional baseline: 152,500 fixed 1 km cells, 61 of 690 shortlisted parent windows, 2,286 region/cooling alternatives. Every region spans at most 20 km per projected axis. Loaded by the local page; broader Phase 9 acceptance remains unpublished. |
| `regional_strict_v2/` | Completed strict execution: no eligible cells or candidate regions because required critical evidence remains UNKNOWN. |
| `regional_audit_v1/` | Source audit, failed-attempt diagnosis, 3.169 GiB full validation benchmark, 664 backend/API and 110 frontend passing checks/build, exact implementation binding, runnable-delivery status, reproducible scripts and UI handover screenshot. Phase 9 acceptance is not published. |
| `frontend_service/regional_runs/c434de47ebaefb62f21e1fac667ad486b937043bbccb19d5647a9ae6a26f8177/` | Failed live attempt under the old memory behavior; no completion metadata, preserved unaccepted. |
| `regional_page_v1/` | Bounded page delivery: completed fine geometry/API verification, 30 focused UI and 12 cache checks, production build, restart/cache proof and actual regional-map screenshot. The improvement goal remains paused. |
| `frontend_service/regional_runs/8f9455cec021973f48bf666b21c0f1a15b31600eed353e051df32fca072fe2cf/` | Superseded duplicate page execution, interrupted after the identical-facility v4 baseline completed. Partial artifacts are unaccepted; `regional_page_v1/superseded_duplicate_job.json` records the replacement. |
| `regional_speed_v1/` | Bounded calculation/service/transport speed work: real metric preparation took 30.8% less time with exact baseline/STRICT tables and bytes; cold response 82.9 → 21.9 s with exact JSON equality; compressed live response 5.34 MB in 0.94 s; 98 API and 80 model checks passed. Completed-default reuse refuses changed scientific bindings. No new full scientific run or Phase 9 acceptance. |
| `regional_speed_v2/` | Further bounded speed work: metric preparation took another 17.9% less time with exact tables/bytes; transmission layer preparation 24.4 → 2.0 s with exact JSON; live 2,500-cell grid in 1.81 s. 104 API checks and 108 related model checks passed. Model files held stable for the separately authorized comparison run. No new full scientific execution or phase acceptance by this task. |
| `cleanview_coverage_audit_v1/` | Completed existing-center area audit and applied delivery: all 277 matched samples across 99 counties have unscreened national 1 km score ranges. Complete 7,829,373-cell/54,805,611-provenance replay, component explanations, 830 regression tests, preserved failed preflight/resource/verifier attempts, successful native resume, exact live API proof and screenshot. Completion record binds the actual 115-file implementation and output evidence. |
| `fine_surface_preflight_v1/` | Bounded real native-source review of two deterministic 1 km parent windows and eight clipped cells. Failed confidence-parity checks are preserved alongside revisions; numeric values/scores and known/UNKNOWN masks passed within stated tolerances. This is not nationwide or phase acceptance. |
| `national_fine_regional_v1/` | Completed real Phase 11 run `regional_refinement__b1638f307a9c7316` (2026-10-04): national fine surface valued 7,829,373 CONUS 1 km cells (15,536,290 of 15,658,746 cell/design alternatives scored, 54.8M FeatureMetadata rows, 26.5 min), ranked 3,373 parents and refined the 61 best in full (131,945 cells, 20 coast/border parents; 5,748 region/design alternatives). Selected parents concentrate in NY (50), CA (5), VT (4), PA and NJ (1 each); only 1 is shared with `cleanview_regional_v2`. Peak working set 3.456 GiB in the resumed refinement process. Applied to the app: 2,874 conditional geographic areas with 20 km limits per projected axis and exact live evidence verification. |
| `national_fine_region_v1/` | Failed first attempt of the Phase 11 region-best run (2026-10-04): national discovery and the national fine surface completed, then the first parent stopped on the geography-cache code-domain regression introduced with `geography/sources/saipe.py`. Partial output of a superseded revision, preserved as the binding check requires; not a result. |
| `national_fine_region_v2/` | Completed real Phase 11 region-best run `regional_refinement__0c70bb571549abe5` (2026-10-04), selection `national_fine_region_parents`: national fine surface valued 7,829,373 cells (32.3 min, child process peak 2.452 GiB); the best fine parent of each national region refined in full: 61 parents, 152,500 cells, 29 primary states, 2,218 region/design alternatives, regional process peak 3.699 GiB. 54 parents equal `cleanview_regional_v2`; 7 moved to a better member (mean +0.94, max +3.43 decision points); top 1,000 alternatives identical. Effectiveness scorecard 67.9 (representative 61.6, global top 61.0). Published: latest and nationwide regional run of the app. |
| `national_fine_region_evidence_v1/` | Evidence for the region-best run and its failed first attempt: run logs, cache-reuse check, three-run comparison, the 7 changed regions, and the one-off effectiveness scorecard with its reproducing scripts (scores 61.6 / 61.0 / 67.9). Not a model output. |
| `cleanview_fine_comparison_v1/` | Official diagnostic comparison against the completed national/fine regional run: 277 samples supported nationally, 10 in the fully checked regional domain, 267 outside that regional domain and 20 unmatched labels. Seven output hashes and 57 input hashes verified; no facility coordinates, physical-accuracy estimate or fitted model preferences. |
| `county_socioeconomic_layer_v1/` | Separate 2024 Census SAIPE county economic map/context delivery with authorized cached 2023/2025 cartographic geometry. Contains build/audit/test evidence and implementation report; canonical county/grid relationships are in the bound `data/processed/socioeconomic/` caches. Technical native outputs are preserved. |
| `county_socioeconomic_filters_v2/` | User-requested filter-only correction: poverty, income and both supplied county percentiles filter saved candidate areas; county map overlays are suppressed. Contains regression, real-filter audit and browser evidence. Retains 2024 SAIPE with selectable 2023/2025 boundaries and the existing technical model. |
| `nationwide_map_coverage_v1/` | Page coverage correction: independently verified completed national representative refinement, 1,163 saved search geometries / 2,326 cooling alternatives, 152,500 native 1 km cells, 61 windows across 30 primary states, all region spans <=20 km. API 1.7 advertises a separate completed nationwide regional view and the page loads it without another search; global top-window evidence and ongoing native delivery are preserved. Includes regression, native checksum/span audit and live-page evidence. |
| `pr1_merge_v1/` | Merged PR #1: isolated 45-county Monte Carlo model and visible Model selector, grid default preserved. Reviewed cache/input lineage and Windows UTF-8 fixes; 19 official inputs; backend 113, current frontend 178 and isolated PR frontend 83 tests passed, both builds passed, real-data API/UI flows and live screenshot. Git merge/completion identities and original dirty-worktree snapshot retained. |

| `grid_one_minute_v1/` | Applied API 1.8 fast Grid default: fresh 134 MW result in 56.28 s through gzip delivery; all 152,500 cached native 1 km cells / 305,000 alternatives / 61 nationwide regional windows, <=20 km spans per projected axis. 112 model, 191 API, 194 frontend checks passed plus build; one optional County test skipped. Final code/cache binding, independent native audit, all 19 serial/parallel artifact hashes identical and actual browser proof; earlier 66 s stress result preserved; full rediscovery remains selectable. |
| `rediscovery_v1/` | Rediscovery check (2026-10-04): blind separated Top-250 candidates from the `national_fine_regional_v1` national 1 km surface (exact `score_window` reproduction), hashed before revealing 1,472 IM3 Open Source Data Center Atlas facilities (PNNL, ODbL). Hit rates vs 1,000 seeded random controls, tie sensitivity, AUC 0.717, classes, county Monte Carlo robustness, explanations and a score-surface image; manifest binds config/code/inputs/outputs. Not accepted phase evidence; see `docs/rediscovery_validation.md`. |
