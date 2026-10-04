# AGENTS.md — U.S. Sustainable Data Center Location Discovery Model (`dc_locator`)

Project-wide rules for every agent (human or AI) working in this repository.
Maintained by the main orchestrator / technical lead. Phase agents may ADD rules or detail; they must not weaken
or delete rules without a recorded decision in `docs/phase_handoff.md`.

Full requirements: `docs/specs/master_prompt.md` and `docs/specs/phase1.md.txt` … `phase7.md.txt`.

---

## 1. What this system is (and is not)

- A **deterministic geospatial decision-support system** that searches the contiguous United States (CONUS:
  48 states + DC) on a regular grid and identifies **regions that deserve further investigation** for
  sustainable AI data-center development, under stated facility requirements, datasets, constraints,
  assumptions, and decision preferences.
- It is **not** proof that any parcel is buildable or objectively best. Region geometries are **search
  areas**; a centroid is never an approved construction site.
- The separately authorized frontend in `frontend/` presents deterministic model outputs. It must not
  implement model mathematics, a chatbot, or a machine-learning location predictor. No LLM ever decides
  a score, weight, threshold, coefficient, or winner.
- The analysis must never start from a manually selected list of cities. Development areas are bounding boxes
  used only to bound computation, and they never change grid IDs.

## 2. Two components — never mix them

| Component | Package | Question | Must NOT contain |
|---|---|---|---|
| geography | `src/dc_locator/geography/` | What does each part of the U.S. look like? (grid, source adapters, feature engineering) | thresholds, pass/fail, scores, weights, rankings |
| model | `src/dc_locator/model/` | Given a facility spec + decision config, which areas are promising? (screening, physics, metrics, Pareto, AHP/MCDA, clustering, scenarios, lifecycle, validation) | data downloading / source-specific parsing |

Shared infrastructure (schemas, config, provenance, IO, CLI) lives at `src/dc_locator/*.py`.

## 3. Non-negotiable rules

1. **Continue existing work** — never rebuild a completed phase; extend it through documented changes.
2. **Never fabricate** source data, geographic values, engineering coefficients, expert judgments (AHP
   comparisons), thresholds presented as scientific/regulatory facts, or validation evidence.
   Every numeric coefficient in `configs/` must cite a document (URL + table/page) or be explicitly labelled
   a user/project assumption (`basis: project_assumption`) with a rationale.
3. **UNKNOWN is never zero and never PASS.** Missing values stay null (`NaN`/`None`) with a `missing_reason`.
   No silent imputation. No candidate-specific weight renormalization when a metric is missing.
4. **Value status** on every important metric — exactly one of:
   - `observed` – taken from a dataset (possibly spatially aggregated to the cell)
   - `calculated` – derived by a documented formula from observed/scenario inputs
   - `scenario` – an explicit assumption or external scenario value (design PUE/WUE, SSP pathway, user input)
   - `proxy` – an indirect indicator standing in for something unmeasured (e.g. distance to a transmission
     line as a proxy for — NOT proof of — grid access)
   - `unknown` – not available; value is null and `missing_reason` explains why
   Confidence: `high | medium | low | unknown`.
5. **Proxies are not facts**: transmission proximity ≠ power availability/capacity; Aqueduct ≠ water-supply
   commitment; FCC availability ≠ diverse data-center fiber; climate normals ≠ hourly operating simulation;
   eGRID historical averages ≠ future or marginal emissions; queue MW ≠ future supply or emissions.
6. **Synthetic fixtures are quarantined**: synthetic data lives only in `tests/fixtures/` and in run folders
   whose `data_mode` is `synthetic`. Synthetic data must never be written to `data/processed/` and a real-data
   run must never silently fall back to synthetic data (IO helpers enforce this).
7. **Hard failures cannot be compensated** by good scores elsewhere.
8. **Determinism**: identical inputs + config ⇒ identical substantive outputs (sorted rows, stable tie-breaking
   by `grid_id` then `design_id` then `scenario_id`, fixed seeds where randomness is used at all).
9. **Record everything**: assumptions, source versions, retrieval dates, checksums, calculation methods,
   config snapshots, code revision.
10. **Tests every phase** (pytest). Hand-calculated fixtures for formulas. Never edit an expected value just to
    make a test pass — investigate first and record the reasoning.
11. **Update `docs/phase_handoff.md` after every phase** (commands run, outputs, tests, assumptions, blockers,
    next-phase inputs) and write a phase completion record (§10).
12. Production logic lives in `src/`, never only in notebooks.

## 4. Data-access policy

- Use only authoritative/official sources listed in `docs/specs/master_prompt.md`; any additional source must
  be justified in `docs/sources.md`. Never silently substitute a weaker proxy for a requested source.
- Cache raw downloads under `data/raw/<source_id>/` and record each file in the download manifest
  (URL, retrieved_at UTC, bytes, sha256, license/terms note, version). Never re-download a cached, verified file.
- Batch processing only: no per-cell HTTP requests. Estimate download volume before large downloads and support
  bounded (study-area / tile) processing.
- **Never bypass access controls**: no account creation, no logins, no CAPTCHA/bot-challenge circumvention, no
  browser-UA impersonation to defeat a block, no filling personal-data forms, no accepting click-through
  licenses on the user's behalf. If a source needs any of these, mark it `BLOCKED` (or `PARTIAL`), implement
  a local-file input path (`data/raw/<source_id>/manual/…`), and document exact manual-acquisition steps.
- Credentials only via environment variables (e.g. `NREL_API_KEY`); never written to configs, logs, or git.
- **Download authorization (user, in chat, 2026-10-02):** public datasets from the official sources named in
  `docs/specs/master_prompt.md` may be downloaded into `data/raw/` up to **~60 GB in total for the project**
  (no logins, forms, CAPTCHAs). Track cumulative bytes in each source's manifest; before any single download that
  would push the project total past 60 GB, stop and report instead of downloading.
- **Never modify anything outside the project root** — no edits to `~/.claude/` settings, global configs,
  CLAUDE.md files, environment variables, or other user files. Model/tooling configuration is the orchestrator's
  and the user's business, not a phase task.
- Source/adapter status vocabulary: `READY | PARTIAL | BLOCKED` (plus `NOT_IMPLEMENTED` for planned adapters).
  Coverage reporting must distinguish **implemented** (code exists) vs **acquired** (data downloaded) vs
  **analyzed** (features computed for cells).

## 5. Repository layout

```
AGENTS.md  README.md  pyproject.toml  requirements.lock.txt
configs/            grid.yaml sources.yaml facility.yaml cooling_designs.yaml constraints.yaml
                    scoring.yaml scenarios.yaml run.yaml (+ examples)
src/dc_locator/     __init__.py __main__.py cli.py schemas.py config.py provenance.py io.py paths.py
  geography/        boundary.py grid.py sources/<source_id>.py features.py …
  model/            screening.py physics.py cooling.py metrics.py normalization.py pareto.py ahp.py mcda.py
                    clustering.py scenarios.py lifecycle.py validation/ …
data/raw/<source_id>/        cached original downloads (git-ignored)
data/interim/<source_id>/    resumable per-tile intermediate results (git-ignored)
data/processed/              real-data geography outputs ONLY (git-ignored except small manifests)
runs/<run_name>/             model outputs of one run + run_metadata.json (git-ignored)
tests/  tests/fixtures/      pytest suite; synthetic fixtures only here
docs/                        methodology, data_contracts, data_dictionary, sources, limitations, phase_handoff,
                             phase_records/, specs/
```

Geography outputs go to `data/processed/`. Model outputs (screening, performance, rankings, regions,
validation) go to a run folder `runs/<run_name>/`.

Phase7 delivery clarification authorized by the root/user: geography production remains separate,
while reproducible real geographic/provenance copies and intermediate geographic builds may also live
in an owned `runs/<run_name>/` final package. Explicit synthetic geography stays in `tests/fixtures/`
or synthetic run folders, never `data/processed/`. Workspace-local pytest temporary folders are permitted
for verification. This additive path clarification is recorded in the handoff.

## 6. Shared technical contracts (authoritative detail in `docs/data_contracts.md`)

- **CRS**: grid geometry, areas and adjacency in **EPSG:5070** (NAD83 / CONUS Albers Equal Area, metres).
  Lat/lon outputs in EPSG:4326. Never compute km from degrees. Distances: projected EPSG:5070 metres (document
  the scale-error bound) or geodesic (`pyproj.Geod`) — state which.
- **Grid**: fixed national origin and cell size from `configs/grid.yaml`; `row`/`col` are counted from that
  origin, so IDs never depend on processing order or on the selected development area. `grid_id` and
  `grid_definition_id` are deterministic functions of the grid definition + row/col.
- **Units**: explicit in column names (`_km2`, `_km`, `_mwh`, `_kg_per_mwh`, `_frac` for 0–1 fractions,
  `_pct` for 0–100) and in `docs/data_dictionary.md`.
- **Tables**: Parquet/GeoParquet. Every written table carries file metadata keys `dc_locator.schema`,
  `dc_locator.schema_version` (semver), `dc_locator.data_mode` (`real|synthetic`),
  `dc_locator.grid_definition_id`, `dc_locator.created_by`. Use the helpers in `dc_locator.io`.
- **Long-form provenance** (`feature_provenance.parquet`): one row per `grid_id × metric` with value, unit,
  source id/name/URL/field, data year/period, retrieved_at, native spatial resolution, aggregation method,
  coverage fraction, status, confidence, missing_reason, data_mode.
- **Status enums**: value status (§3.4); screening outcome `PASS | FAIL | UNKNOWN`; screening modes
  `STRICT | EXPLORATORY`; source status (§4); AHP status `ACCEPTED | REVIEW_REQUIRED |
  PROVISIONAL_OVERRIDE | NOT_APPLICABLE`.
- **Records**: one performance record per `grid_id × design_id × scenario_id`; never mix the best electricity
  result of one cooling design with the best water result of another.
- **Decision alternatives vs external scenarios**: cooling design is a decision (`design_id`); climate/grid/
  water futures are external scenarios (`scenario_id`). Optimizers never "choose" a scenario.

## 7. Environment and engineering conventions

- Windows 11, PowerShell or Git Bash. The project root is `D:\locate-data-center`
  (`"/d/locate-data-center"` in Git Bash). Quote paths supplied to commands.
- Python 3.12 virtualenv at `.venv` managed with `uv`. Run everything with the venv interpreter:
  `.venv/Scripts/python -m pytest`, `.venv/Scripts/python -m dc_locator …`.
- Pinned dependencies in `pyproject.toml` + `requirements.lock.txt`; record the environment in docs.
- Memory budget: the machine has 31 GB RAM shared with other work — keep any single process under ~4 GB.
  Use windowed/block raster reads, chunked vector processing, spatial indexes; never load a national 30 m
  raster into memory at once.
- Vectorize (numpy/pandas/shapely 2/geopandas); no per-cell Python loops over national data when avoidable.
- Prefer clear, typed, documented functions; keep comments sparse and meaningful.

## 8. Interpretation language (use in every report)

> "These geographic regions deserve further investigation under the stated facility requirements, datasets,
> constraints, assumptions, and decision preferences."
> They are NOT proven buildable parcels and NOT "America's objectively best place to build a data center."

## 9. Phase process (gate)

DELEGATE → IMPLEMENT → REVIEW → TEST → FIX → ACCEPT → HANDOFF → NEXT PHASE.
A phase is accepted only by the technical lead after inspecting code and outputs and running the test suite.
Later phases must not silently change an earlier phase's meaning; schema changes require a migration note in
`docs/data_contracts.md` (changelog) and a schema-version bump.

## 10. Phase completion records

After acceptance, `docs/phase_records/phase_<N>.json` records: phase, accepted_at, code revision (git commit),
schema versions, data versions (source ids + versions + checksums), tests (counts passed/failed/skipped),
known limitations, blockers.

## 11. Required documentation

`AGENTS.md`, `README.md`, `docs/methodology.md`, `docs/data_contracts.md`, `docs/data_dictionary.md`,
`docs/sources.md`, `docs/limitations.md`, `docs/phase_handoff.md`.

## 12. Additional county model (user-authorized PR #1, 2026-10-04)

`backend/dataclocator/` is an additive, separately packaged Python 3.13 county Monte Carlo model.
Its source instructions and dependency lock apply within that package. Its data and output roots
remain isolated; it does not replace the geography/model separation or accepted evidence of
`src/dc_locator`. The frontend offers an explicit Model choice, with the grid model as default.
The 45 selected counties are a bounded comparison cohort, not national discovery or approved sites.
This authorized layout extension and its verification are recorded in `docs/phase_handoff.md`;
local integration evidence lives in `runs/pr1_merge_v1/`. Keep generated county data, outputs,
environments and secrets excluded from Git.
