# runs/ — model run folders

Each model run writes to its own folder here (`python -m dc_locator <stage> --output runs/<name>`).
Run folders are git-ignored; only this index is tracked. Folders marked as evidence are cited by path,
often with file hashes, in `docs/phase_records/`, or they are read by the frontend. Never move, rename,
edit or delete them.

## Start here

| Folder | What it is |
|---|---|
| `example/` | Default real STRICT run (`configs/run.yaml`), recorded as the accepted Phase 7 `final_default_run`. It covers 42 Texas development cells and has an intentionally empty ranking, because critical requirements are UNKNOWN. Read by the frontend. |
| `phase7/root_v2_exploratory/` | Accepted exploratory run (`configs/run_exploratory.yaml`) with 84 conditional alternatives and 2 search regions. Provides the frontend's baseline map results. |
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

The pipeline refuses to write delivery outputs into `runs/phase1`–`runs/phase6`
(`src/dc_locator/run_config.py`, `preflight`).

## Starting a new run

Use a new, descriptive folder, e.g. `runs/2026-10-05-exploratory-check/`. Re-running into the same folder
with identical code, configuration and sources verifies and resumes it. If any of those changed, the
pipeline rejects the folder, so use a new one. Delete scratch runs when you are done. If you keep a run as
evidence for a decision, add a row to this index.
