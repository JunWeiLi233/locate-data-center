# Sustainable data center screening backend

This is the imported existing county backend. See [repository integration setup](../../docs/county-backend-integration.md) for separate packaging, frontend selection and current integration validation. Historical `outputs/` links below describe generated artifacts; acquire/preprocess/run locally to create them.

Tasks 2–4 collect and join official regional data, verify physical accounting, compare 45 counties using reproducible Monte Carlo scenarios and exact expected/robust Pareto frontiers, and expose a bounded JSON API. No frontend is included.

Use Python 3.13. Exact runtime/test dependencies are in `requirements.lock`.

```sh
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
export PYTHONPATH=src
.venv/bin/python -m dataclocator.cli acquire
.venv/bin/python -m dataclocator.cli preprocess
.venv/bin/python -m dataclocator.cli verify
.venv/bin/python -m dataclocator.cli report
.venv/bin/python -m dataclocator.cli simulate --config configs/monte-carlo-demo.json
.venv/bin/python -m pytest -q --junitxml=outputs/task3-tests.xml
```

Start the HTTP backend with `.venv/bin/python -m dataclocator.cli serve --port 8000 --cors-origin http://localhost:3000`. Submit settings to `POST /runs` and poll `GET /runs/{run_id}`. See the [API documentation](docs/api.md), [OpenAPI schema](docs/openapi.json), [example request](docs/api-request-example.json) and [polling client](examples/api_client.py). Run all model/API checks with `.venv/bin/python -m pytest -q --junitxml=outputs/task4-tests.xml`.

Generated output examples and test records are local runtime artifacts, intentionally omitted from this checkout. Run the documented smoke configuration to reproduce a complete JSON response. HTTP integration passed with in-process ASGI transport; this development sandbox blocks live local socket binding, so TCP/curl verification must run outside it.

`acquire` downloads only missing files from the pinned manifest. If a mutable public URL has changed, acquisition fails rather than overwriting a frozen release. Preserve the original archives or deliberately review and pin a new release. All other commands run from local files without live queries. Simulation artifacts are stored under `outputs/run_<hash>/`, with the exact config, model version and dataset/input hashes defining each run. The command prints its report path.

The demonstration uses proposed, unconfirmed PUE/WUE bounds and rate assumptions recorded in [monte-carlo-demo.json](configs/monte-carlo-demo.json), not measured cooling curves or predicted futures. It runs 5,000 draws per each of nine separate rate scenarios, with 20/30-year, tariff-sector, dependence, grid-assignment and verified-feasibility sensitivities. Convergence compares 1,000/5,000/10,000 draws against predeclared tolerances. Run `configs/monte-carlo-smoke.json` with `--skip-convergence --skip-sensitivity` for a quick 500-draw check.

- [Completed Monte Carlo report](outputs/run_67709232ad31aba9/report.md), [results JSON](outputs/run_67709232ad31aba9/results.json), and [frontier plot](outputs/run_67709232ad31aba9/frontiers.png)
- [Run configuration and JSON interface](docs/monte-carlo-interface.md)

- [Regional evidence report](outputs/task2/report.md)
- [Joined candidate JSON](outputs/task2/candidates.json) and [CSV](outputs/task2/candidates.csv)
- [Coverage and geographic caveats](outputs/task2/coverage.json)
- [Download/provenance manifest](data/source_manifest.json)
- [Processed-data dictionary](docs/data-dictionary.md)
- [Accounting verification](outputs/task2/accounting_verification.json)
- [Required engineering input template](configs/accounting-template.json)

Raw downloads live under `data/raw/<source>/<release>/`; normalized Parquet tables live in `data/processed/`. Both are ignored by Git. The fixed sample is 45 counties selected for geographic breadth before outcomes, with Census FIPS kept as strings. Candidate JSON includes source references, feasibility, coverage and boundary exclusions, and is returned as `evidence` by `GET /candidates`. Jobs freeze their own evidence and rates, with atomic JSON persistence and cache reuse across restarts.

No water stress score is turned into consumption, and no location is certified buildable. The main demo identifies cost/carbon tradeoffs among San Juan (NM), Yakima (WA), Richland (SC), and Oneida (NY); tariff and supplier-map sensitivity cases produce different frontiers. Shared WUE gives equal direct cooling water use, and shared design uncertainty cannot validate a location even when its conditional Pareto frequency is 1.
