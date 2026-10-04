# Regional Refinement Implementation Plan

> **For agentic workers:** Use the repository's delegated IMPLEMENT → REVIEW → TEST → FIX → ACCEPT → HANDOFF gate. Steps use checkbox syntax for tracking.

**Goal:** Recalculate selected national parent areas on a fixed 1 km grid and return connected regional investigation areas whose projected extent is at most 20 km on each axis.

**Architecture:** National discovery chooses evaluated representative parent cells for the submitted facility. Geography enumerates only those full parent windows, preserving national lattice IDs. Batch evidence stays on disk; compact records are ranked globally across all evaluated children and hydrated representatives support the existing map API.

**Tech Stack:** Python 3.12, GeoPandas/Shapely 2, NumPy/pandas, GeoParquet, existing deterministic physics/screening/MCDA, standard-library HTTP bridge, React/MapLibre.

## Task1: Bounded geographic generation

Files: `src/dc_locator/geography/grid.py`, `tests/test_bounded_grid.py`.

- [x] Write and run failed-first tests comparing bounded output with the corresponding national lattice subset, including overlapping windows, ordering and coast intersections.
- [x] Add `generate_bounded_grid(grid_config, boundary, windows_5070)` returning `(grid, stats)`; enumerate only positive-intersection candidate ranges, deduplicate global row/col pairs, retain full squares and exact CONUS intersection areas.
- [x] Run `.venv/Scripts/python -m pytest -q tests/test_bounded_grid.py tests/test_grid.py --basetemp=.pytest-work/regional-grid` and preserve legacy semantics.

## Task2: Exact compact global decisions and bounded regions

Files: `src/dc_locator/model/{regional_decision,pareto,regions,metrics,decision}.py`, focused tests in `tests/`.

- [x] Write failed-first fixtures proving whole-universe score/rank/Pareto equivalence to existing `decide`, plus tolerance cycles and deterministic connected extent splitting.
- [x] Implement `prepare_batch(...)` → wide scored records, normalized metrics and compact records; `rank_compact(...)` → exact global decisions; `finalize_normalized(...)` → global constant-column annotations.
- [x] Add an exact spatial-objective tree with conservative pruning and retain the block comparison oracle. Every comparable row remains a potential dominator.
- [x] Add `maximum_extent_km`, `extent_basis`, `extent_rationale` to region policy; partition global lattice indices before connectivity. Emit CandidateRegion1.2.0 only for bounded profiles.
- [x] Run targeted model tests using `.pytest-work/regional-model`; compare complete outputs to the oracle rather than approximate frontiers.

## Task3: Bound orchestrated evidence and validation

Files: new `src/dc_locator/regional.py`, `configs/{grid_regional,run_regional_exploratory,scoring_profile_regional}.yaml`, CLI, run configuration, pipeline region writer, reporting, `tests/test_regional.py`.

- [x] Write failed-first configuration, lineage, stale-output rejection and batch/global validation tests.
- [x] Configure a wrapper schema3.0.0, phase9_regional_v1, full representative parent selection, 1km grid, 200000child execution budget and 2500cell batch budget. Every new numeric policy cites `basis: project_assumption` and its rationale.
- [x] Implement `run_regional(config_path, output, *, root=None, progress=None)`; execute current national pipeline, deduplicate representatives and generate each full selected parent. Do not choose cities or redistribute state results.
- [x] Verify native source/code/config hashes, write batch geography/provenance/physics/screening evidence and compact records, rank once globally, persist canonical global compact tables and hydrate actual evaluated representatives.
- [x] Validate fresh baseline equality per batch and global decisions; stress four declared preference cases and strict screening across the same fine universe. Stream comparisons and persist per-case outputs without retaining wide frames.
- [x] Write a checksum-bound `regional_catalog.json` with part paths, representative lookup, parent lineage, fine coverage, ranking universe and the fixed extent policy. Publish completion metadata only after validation succeeds.

## Task4: Service and map integration

Files: `frontend/server/{service,serialization}.py`, API/types/App/map layer routing, existing frontend tests.

- [x] Write failed-first regional catalog/API fixtures and legacy compatibility tests.
- [x] Route new searches through a customized national parent followed by the regional wrapper. Persist standard small snapshot/profile/weight/summary files.
- [x] Read representative evidence using filtered Parquet reads, with catalog lookup rather than whole-universe wide tables. Overlay exact global ranks/Pareto flags.
- [x] Request at most10000indicator cells from the selected region's parent window. Show 1km resolution, bounded partial coverage and 20km extent; map zoom never changes analysis outcomes.
- [x] Run backend bridge tests, frontend tests and production build.

## Task5: Real acceptance and immutable evidence

Files: new owned `runs/regional_refinement_v3/`, indexed audit/repeat runs, required docs and a new phase completion record.

- [ ] Run the full current selected-parent refinement on authoritative cached sources; measure process memory below4GiB and audit coast attribution without clamping.
- [ ] Audit each polygon extent, lineage, null UNKNOWN values, hard failure exclusion, native representative/global rank equivalence, strict empty results where evidence is unavailable, all output hashes and repeat determinism.
- [ ] Run full backend/API tests and frontend build; inspect a fresh live search and selected-window layers in the browser.
- [ ] Record exact code/config/source/output hashes, commands, test counts and remaining industrial evidence limitations. Update handoff/index/contracts with the new revision and remove only owned scratch.

Accepted Phase7/8 evidence and other simultaneous workspace edits remain immutable. This shared checkout retains existing source caches; no worktree copy or unrelated commit is part of this delivery.
