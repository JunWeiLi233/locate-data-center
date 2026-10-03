# Local deterministic model bridge

From the project root, use the existing Python environment:

```powershell
.venv\Scripts\python frontend\server\app.py --port 8787
.venv\Scripts\python -m pytest frontend\server_tests -q -p no:cacheprovider --basetemp runs/frontend_service/server_test_tmp
```

The service binds only to `127.0.0.1` and accepts local browser origins. It uses
stdlib HTTP and the project's already installed scientific dependencies. It
registers the accepted strict and exploratory development runs; every response
states that only 42 development cells were analyzed. No network source acquisition
is performed by the bridge.

Searches execute the accepted `Pipeline` stages through one bounded worker queue.
Submitted requirements create new YAML/JSON inputs only beneath
`runs/frontend_service/configurations`. Scientific outputs are stored under
`runs/frontend_service/model_runs/<complete Pipeline identity>`. Prior accepted
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
Response cache identity includes adapter revision, scientific stage identity and
checksums of the actual serialization inputs. Scientific outputs are retained for
audit rather than deleted automatically.

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
