# Phase 7 Delivery Implementation Plan

> **For agentic workers:** Execute this authorized plan inline with checkpoints; the current-run validator is delegated to its assigned owner. No git mutations are authorized.

**Goal:** Make every CLI stage and the configured end-to-end locator executable with honest real, synthetic, strict and conditional outputs.

**Architecture:** Delivery configuration and stage orchestration wrap accepted geographic and model APIs. Reports and current-run validation bind actual source, configuration, code and environment identities; Phase 6 evidence remains historical.

**Tech Stack:** Python 3.12, argparse, pydantic, GeoParquet/Parquet, existing geopandas/numpy/pandas APIs.

### Task 1: Configuration, source loading and resource preflight

Files: create `src/dc_locator/run_config.py`, `configs/local_sources.json`, source-input JSON references, and strict/exploratory/synthetic run configurations; test `tests/test_pipeline.py`.

- [ ] Add tests rejecting national model requests before feature allocation, forged file metadata, missing real files, numeric booleans and synthetic output under `data/processed`.
- [ ] Implement a strict delivery config, file/version/hash checks, normalized project-relative references, and a source loader that verifies every acquired input against its declared manifest.
- [ ] Run `.venv\Scripts\python.exe -m pytest -q tests/test_pipeline.py --basetemp=.tmp-phase7-config -p no:cacheprovider`.

The intended guard is tested with:

```python
with pytest.raises(ValueError, match="national"):
    preflight(config.model_copy(update={"study_area": "conus"}), root)
```

### Task 2: Actual stage orchestration and CLI

Files: create `src/dc_locator/pipeline.py`; modify `src/dc_locator/cli.py`, `tests/test_cli.py`; create quarantined fixture files under `tests/fixtures/phase7`.

- [ ] Replace obsolete stub assertions with stage argument and failure-behavior tests.
- [ ] Implement ingest, features, screening, simulation, ranking, explicit clustering, validation and run functions. Preserve build-grid flags and national geometry support.
- [ ] Write each stage manifest with current configuration/code/environment/source/grid hashes and output hashes. Reuse only verified matching outputs; reject stale upstream stages.
- [ ] Call existing temporal/lifecycle APIs per configured external context with matched source profiles. Retain unsupported 2040 UNKNOWN records.
- [ ] Execute every command against synthetic fixtures and the supported 42-cell real dataset.

The executable acceptance entry is:

```powershell
.venv\Scripts\python.exe -m dc_locator run --config configs/run.yaml --output runs/example
```

### Task 3: Current validation, reports and delivery evidence

Files: create `src/dc_locator/reporting.py`; integrate the delegated pure `validate_current_run` API; update README, AGENTS and shared documentation; write `docs/phase_records/phase_7_pending.json`.

- [ ] Test current facility/profile/config identity binding, empty strict reports, conditional actual representatives, and byte-identical substantive outputs across isolated repeats.
- [ ] Migrate only the obsolete Phase 6 preflight test to an explicit current fixture with absent software evidence; keep immutable freeze verification tests and historical results intact.
- [ ] Export source dates/coverage/UNKNOWNs, actual representative performance/contributions and local-verification/sensitivity details for each region.
- [ ] Run a fresh complete suite with a unique project-root basetemp and no cache provider.
- [ ] Run strict, exploratory and synthetic packages twice; compare substantive hashes and monitor process peaks below 4 GB.
- [ ] Record all commands, hashes, tests, source blockers and the unsupported national model scope for independent review and root acceptance.

No approved science or historical acceptance/freeze artifact is rewritten. Production geography may be copied into reproducible run packages; synthetic outputs remain confined to fixtures or synthetic run folders.
