# Local deterministic model bridge

From the project root, use the existing Python environment:

```powershell
.venv\Scripts\python frontend\server\app.py --port 8787
.venv\Scripts\python -m pytest frontend\server_tests -q -p no:cacheprovider --basetemp .pytest-work/frontend-server-tests
```

The service binds only to `127.0.0.1` and accepts local browser origins. It uses
stdlib HTTP and the project's already installed scientific dependencies. It
registers existing strict and exploratory development runs and the completed
`runs/national_discovery_v2`, `runs/regional_refinement_v4` and the corrected
`runs/cleanview_regional_v2` evidence packages when complete. A completed
`runs/national_fine_regional_v1` takes priority once all seven stages and its
checksum-bound surface manifest/artifacts are available; an incomplete run leaves
the Cleanview baseline active. Older completed runs remain loadable by ID. Existing URLs pin their
explicit run until a different result is loaded. Every response reads
the analyzed extent from archived metadata and counts actual geography rows.
The completed regional baseline takes priority over saved coarse/development searches. A completed national fine baseline also takes priority over saved searches using the older parent selector; newer completed fine-mode user searches keep their priority. No network source acquisition
is performed by the bridge.

API 1.7 separately advertises `nationwide_regional_run_id` for a checksum-verified,
completed 1 km/20 km regional view chosen per national discovery region. It
prefers the completed best-fine-parent-per-region delivery, then the saved
representative refinement. The global top-window run remains accessible and
retains its own rankings. This display choice does not change request configuration
or the computation baseline. A known external per-region delivery is registered
only after all completion, artifact and CONUS lineage checks pass; already
registered runs are not reordered by repeated capability reads. Missing or
damaged candidate evidence cannot become the advertised nationwide choice.

API 1.8 adds explicit `cached_regional` and `full_rediscovery` analysis modes.
The page defaults to fast cached regional evaluation when the verified input
cache is ready. It invokes `src/dc_locator_fast.py` in a separate bounded child
process and queue, so a full rediscovery does not delay a fast request. This new
production runner calls existing mathematical functions and records its own
code, policy and cached-input identities. It evaluates the complete fixed
152,500-cell regional cohort and recomputes submitted facility physics,
preferences, global ranks/Pareto and bounded search regions. Historical source
lineage, partial regional coverage and unassessed broad diagnostics remain
explicit. Its outputs belong under `runs/frontend_service/cached_regional_runs/`.

Full rediscovery and legacy requests without an `analysis_mode` execute the
deterministic `run_regional` orchestration through the existing bounded worker queue.
Each request customizes `configs/run_national_exploratory.yaml`, the real CONUS template, then freezes the wrapper for the completed baseline's selector: `configs/run_regional_exploratory.yaml` for representative parents or `configs/run_regional_fine_surface.yaml` for national fine-surface selection, or `configs/run_regional_fine_region.yaml` for the best fine-surface parent of each national region. The wrapper references the customized parent;
missing or mis-scoped national inputs fail explicitly without reverting to Texas.

API 1.5 exposes the native selector, coverage warning and compact national surface
lineage/counts as `UNSCREENED`. National surface Parquet tables are not loaded into
the response. Screened/refined cell counts, ranks, Pareto labels and physical
metrics still come from the evaluated regional outputs. Exact completed search
reuse rechecks the entire native code/config/source/environment identity, regional
and fine stage bindings, every output checksum and parent lineage before returning
canonical adapter bytes. These checks use content, without stat-only memoization.
Disabled future execution does not require an annual-extension policy. Scenario
availability is returned separately for each loaded run and requires supported,
complete artifacts; older development future contexts remain readable.
Full rediscovery requirements create new YAML/JSON inputs only beneath
`runs/frontend_service/configurations`. Scientific outputs are stored under
`runs/frontend_service/regional_runs/<bound parent and wrapper identity>`. The orchestrator recomputes national parent selection for those facility requirements and preferences, refines selected representative parent cells at 1 km, and verifies all cached batch outputs before reuse. Prior accepted
outputs, configs, scientific source code and phase records are never rewritten.
Configuration directories include the submitted inputs, baseline template content
hashes and configuration adapter code hash. Their files are immutable; different
templates or adapter revisions create a new directory and mismatching old bytes
are rejected. Previously completed run snapshots remain readable and authoritative.
The model verifies sources, configs, working model and environment before stages.
Facility-independent geography may be copied from a prior run only when these
identities and all geographic inputs match and its stage outputs pass checksum
verification. The new build-features stage manifest records this reuse and source
run ID. Every facility-dependent stage still executes through the accepted API.

The durable registry records jobs and completed runs. Restarted incomplete jobs
become an explicit error; resubmission resumes deterministic stage caches. An
abandoned browser does not cancel or change model work. The request queue holds
at most eight pending jobs, configuration storage holds at most 64 configurations,
the registry and memory retain at most 100 completed/error jobs plus active jobs,
and serialized response caches hold at most 24 files / eight in-memory responses.
Each durable response is capped at 64 MiB. This is an operational transport
allowance for completed regional geometry/evidence payloads that can exceed the
former 16 MiB limit, so subsequent readers reuse the verified response instead of
repeating a slow serialization. Larger responses skip durable caching. The byte
allowance does not change scientific cell budgets, geometry or returned values.
Response cache identity includes adapter revision, scientific stage identity and
checksums of the actual serialization inputs. Scientific outputs are retained for
audit rather than deleted automatically.

Warm run responses return the verified canonical JSON bytes directly. Clients that
accept gzip receive JSON bodies of at least 1 KiB compressed at level 1, with
`Content-Encoding: gzip` and `Vary: Accept-Encoding, Origin` for local browser
origins. Compression preserves decoded response bytes and schema 1.8.0. Required
artifacts and content identity are still checked on every read. Regional rank-range
and sensitivity evidence is filtered to representatives and indexed once.

Before creating a duplicate default configuration, the worker can reuse the
registered completed regional baseline when the exact request and current complete
model/config/source file sets, environment, binding, output inventory/checksums and
parent lineage match. A scientific revision change requires calculation under a
new identity. Corrupt completed evidence returns an error. Completion verifies the
canonical response before reporting `COMPLETE`; `baseline_reuse_reason` records the
reuse decision in the job registry.

Regions preserve representative alternative rank/score and separate region mean.
Raw measures retain nested performance metadata or geographic provenance, including
units, source years, status, confidence, missing reason and calculation method.
Unknown values become JSON null, never zero. The water factor is a documented
display aggregation of already normalized accepted water leaves using archived
local weights. It does not alter MCDA, leaf normalization or ranking. Climate,
heat reuse and community scores remain unavailable. Layer geometry comprises
actual analyzed grid polygons; mapped transmission distance never becomes a line
inventory or a capacity claim. Future water contexts remain separate from current
physical assumptions; 2040 is explicitly unavailable with no interpolation.

Only allowlisted model artifacts can be downloaded through export URLs. URL run
identifiers resolve through the registry and cannot name filesystem paths. All API
errors use `{schema_version, error: {code, message}}`. Job progress reports actual
stage names without fabricated percentage estimates. AHP uses the four accepted
parent groups and backend consistency review, with no automatic override.

Missing required completed-run artifacts return `422 missing_artifact`, including
after a response was cached. Only successfully read, empty scientific output is
presented as `EMPTY`; corrupted or incomplete storage is not a scientific finding.

The fast input cohort must be prepared once from the completed real baseline.
Use the existing environment from the project root:

```powershell
.venv\Scripts\python.exe src/dc_locator_fast.py --root D:\locate-data-center --baseline D:\locate-data-center\runs\cleanview_regional_v2 --prepare-cache
```

Preparation consolidates and verifies 152,500 native cells in 61 nationwide
windows under `data/interim/fast_cached_regions/`. It is outside the changed
facility timing; the final preparation took 24.49 seconds on this machine.
The UI advertises fast mode only when the current method/configuration cache is
ready. Future scientific method or policy changes require a newly bound cache;
unavailable or corrupt inputs never fall back to fabricated geography.
Cached searches reuse that fixed geographic domain, recompute annual physics,
normalization, preferences, Pareto ranks and bounded regions, and freshly check
representative evidence against the accepted native model. Sensitivity, rank
stability, full submission diagnostics and future contexts remain NOT_ASSESSED.

See `runs/grid_one_minute_v1/README.md` for real changed-request timing, independent
artifact equality, native cell/region bounds, process-memory and test evidence.

## Independent county economic context

API 1.6 adds `GET /api/socioeconomic?run_id=...&boundary_year=2025&scenario=current` and national
`community_economic` layers, labeled County economic need (2024 SAIPE). Boundary
years 2023 and 2025 use the acquired Census generalized 1:500000 Cartographic
files. SAIPE estimates remain 2024, with separate years, source URLs, rounded 90%
confidence bounds, calculated interval-half-width MOEs, status and missing reasons.
Local revenue and service pressure remain unknown. This context never changes
technical scores/ranks/screening/weights or supplies a technical community score.
`scenario_id` binds county relations to the exact loaded saved current/future
region membership. Supported future contexts retain 2024 economic estimates;
unsupported or damaged contexts never substitute baseline region IDs. Browser
context cache identities include run ID, scenario ID and boundary year.

Native member grid IDs join every positive grid–county overlap; no centroid or
primary-county shortcut is used. Fractions retain full saved cell area and any
uncovered coastal area. The response contains county/region relations rather than
the full grid crosswalk. Layer sublayers `poverty`, `income`, `poverty_percentile`
and `low_income_percentile` use `metric@2025` or `metric@2023`; the suffix is a year,
and national layer loading does not require selecting a regional window.

Explicit `socioeconomic_enabled: true` and acquired local official sources are
required. Source inventory capability checks are cheap and do not claim verified
crosswalk readiness. HTTP uses the geography helpers with `acquire=False`; it may
prepare/cache a bounded saved evaluated grid locally, never the 7.8 million-cell
national fine surface. The HTTP bound is 200,000 saved cells. Missing local sources
produce an unavailable context; corrupted bound evidence produces an error.
Prewarm both years through the project's `socioeconomic-enrich` CLI when desired.
Independent geography caches live under `data/processed/socioeconomic/`; accepted
run artifacts and existing run registration remain unchanged.

## Verified submission presentation

API 1.3 optionally includes the read-only saved-run decision brief from `dc_locator.submission`. The adapter calls the builder on the selected current/future artifact folder, writes no scientific outputs, and returns null with a reason when legacy evidence cannot be verified. A separate context ID prevents confusing the UI external context with the stored physical scenario. Cache identity includes the builder's declared inputs and presentation source identity. Region explanations expose stored positive contributions with proxy limitations. API 1.2 regional fields retain their meaning.

## Regional evidence and layers

API 1.2 reads `regional_catalog.json` for actual refined cells/area, shortlisted and refined parent counts, resolution, region extent policy and parent run lineage. Catalog part paths must remain inside the output. The adapter reads representative geography/provenance/performance/screening with Parquet grid-ID filters, then combines hydrated records with authoritative global compact rank/Pareto values. It does not load all fine-grid evidence into memory to serialize regions.

Optional indicator layers require a selected region or parent window using `indicator@region_id` or `indicator@parent_grid_id` in the sublayer parameter. Each response reads that bounded batch only and enforces the 10,000-feature limit. Selecting another region replaces the active indicator window. Browser zoom cannot change grid resolution, parent selection or the recorded maximum region span. Unrefined shortlisted cells remain outside the fine ranking universe. Resolution does not establish industrial zoning, utility capacity or parcel buildability.

Layer presentation indexes stored alternatives and screening checks once per request.
Categorical grid status does not deserialize unrelated geographic metric provenance;
indicator provenance uses a Parquet predicate for its selected metric. Table cache
keys include the metric selection and freshly checked file content. Required
artifact presence, native geometry, status/reason ordering, nulls and unavailable
indicator errors retain their prior behavior. The bounded V2 check returned exact
before-response bytes for 2,500 grid and transmission-distance features; see
`runs/regional_speed_v2/README.md` for component timings and verification.

Regional adapter verification (2026-10-03): 45 server tests passed, including two loopback HTTP tests rerun with socket access after the sandbox denied localhost. The new transport fixture copies accepted evidence privately and verifies filtered representative reads, exact global ranks/physical values, window selection, path containment, missing-artifact handling, layer budgets and customized-parent orchestration. Frontend verification passed 88 tests and the production build; the existing bundle-size advisory remains. Real regional artifact integration is checked after the scientific run completes.
