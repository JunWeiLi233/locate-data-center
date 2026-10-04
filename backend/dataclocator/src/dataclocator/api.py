"""Local JSON API for frozen county screening; no frontend or live data queries."""

from contextlib import asynccontextmanager
import json
import logging
import math
import os
from pathlib import Path
import re

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from . import MODEL_VERSION
from .pipeline import verify_raw_inputs, verify_processed_inputs
from .cache import CacheIntegrityError
from .http_schemas import Candidates, CandidateResult, Datasets, ErrorEnvelope, Health, Job, RunRequest
from .jobs import JobStore, QueueFull

API_VERSION = "1.0"
BODY_LIMIT = 1024 * 1024
WARNINGS = [
    "Engineering priors and future rates are conditional assumptions; demo inputs remain unconfirmed.",
    "Local power capacity, water allocation, parcel/zoning and redundant fiber remain unverified.",
    "Equal WUE yields equal direct water use; basin stress is context, not a volume or probability.",
    "Grid mapping is ambiguous for 15 counties; 2025 retail prices are preliminary state proxies and grid carbon uses 2023 averages.",
    "Reliability/Cambium, weather variability, full TCO, embodied carbon, indirect generation water and heat reuse are not modeled.",
]


def error_response(status, code, message, details=None):
    """Return one strict, sanitized error format throughout the HTTP interface."""
    return JSONResponse(status_code=status, content={"api_version": API_VERSION,
        "error": {"code": code, "message": message, "details": details or []}})


def reject_constant(value):
    """Reject JavaScript nonfinite constants before they reach model validation."""
    raise ValueError("Nonfinite JSON constant")


def finite_json_float(value):
    """Reject overflowing JSON exponents as well as explicit NaN/Infinity."""
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Nonfinite JSON number")
    return number


class StrictBodyMiddleware:
    """Bound streamed request bodies before buffering and validate JSON syntax."""

    def __init__(self, app):
        """Wrap the ASGI application without changing successful response data."""
        self.app = app

    async def __call__(self, scope, receive, send):
        """Handle chunked bodies as well as bodies declaring Content-Length."""
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"] != "/runs":
            return await self.app(scope, receive, send)
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > BODY_LIMIT:
                return await error_response(413, "BODY_TOO_LARGE", "Request body exceeds 1 MiB.")(scope, receive, send)
            if not message.get("more_body", False):
                break
        try:
            json.loads(body, parse_constant=reject_constant, parse_float=finite_json_float)
        except (ValueError, UnicodeError, RecursionError):
            return await error_response(400, "INVALID_JSON", "Supply valid finite JSON.")(scope, receive, send)

        async def replay():
            """Replay the bounded body once for FastAPI's typed request parsing."""
            return {"type": "http.request", "body": bytes(body), "more_body": False}
        await self.app(scope, replay, send)


def create_app(root=None, *, cors_origins=None, queue_size=4, runner=None):
    """Create an isolated app with explicit data root and allowed CORS origins."""
    root = Path(root or os.environ.get("DATACLOCATOR_ROOT", Path.cwd())).resolve()
    origins = cors_origins if cors_origins is not None else [
        item.strip() for item in os.environ.get("DATACLOCATOR_CORS_ORIGINS", "").split(",") if item.strip()]
    if "*" in origins:
        raise ValueError("Configure explicit CORS origins; wildcard is unsupported")
    store_options = {"runner": runner} if runner is not None else {}
    store = JobStore(root, WARNINGS, queue_size=queue_size, **store_options)

    @asynccontextmanager
    async def lifespan(app):
        """Verify frozen sources at startup; missing data remains inspectable."""
        app.state.input_error = None
        try:
            manifest = verify_raw_inputs(root)
            verify_processed_inputs(root, manifest)
            for name in ["outputs/task2/candidates.json", "outputs/task2/coverage.json", "data/processed/grid_regions.parquet"]:
                if not (root / name).is_file():
                    raise FileNotFoundError(name)
        except (OSError, ValueError, KeyError):
            logging.exception("Frozen input readiness check failed")
            app.state.input_error = "Required frozen inputs are missing, invalid or have changed checksums; acquire/preprocess them before running."
        # A process lock prevents two HTTP processes from racing on shared job artifacts.
        store.start()
        try:
            yield
        finally:
            store.close()

    app = FastAPI(title="DataCLocator screening API", version=API_VERSION, lifespan=lifespan,
                  responses={code: {"model": ErrorEnvelope} for code in [400, 404, 409, 413, 422, 503, 500]},
                  description="Conditional county tradeoffs, with provenance and unverified feasibility exposed.")
    app.state.root = root
    app.state.jobs = store
    app.add_middleware(StrictBodyMiddleware)
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        """Publish field locations and validation messages without raw inputs."""
        details = [{"field": ".".join(str(part) for part in error["loc"] if part != "body"),
                    "message": error["msg"]} for error in exc.errors()]
        return error_response(422, "VALIDATION_ERROR", "The request contains invalid settings.", details)

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        """Normalize unknown paths and method errors to the agreed JSON envelope."""
        return error_response(exc.status_code, "NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR", str(exc.detail))

    @app.exception_handler(Exception)
    async def unexpected_error(request, exc):
        """Log internal failures but return no traceback or absolute filesystem path."""
        logging.exception("Unexpected API failure", exc_info=exc)
        return error_response(500, "INTERNAL_ERROR", "Unexpected server failure; consult server logs.")

    def unavailable():
        """Map unavailable frozen inputs to a reviewable service-readiness error."""
        return error_response(503, "INPUTS_UNAVAILABLE", app.state.input_error)

    @app.get("/health", response_model=Health, responses={503: {"model": Health}})
    def health():
        """Report readiness independently of model feasibility or missing optional data."""
        return JSONResponse(status_code=503 if app.state.input_error else 200, content={
            "api_version": API_VERSION, "model_version": MODEL_VERSION,
            "ready": app.state.input_error is None, "queue": store.counts(),
            "warnings": WARNINGS + ([app.state.input_error] if app.state.input_error else [])})

    @app.get("/datasets", response_model=Datasets)
    def datasets():
        """Expose pinned releases, coverage and gaps even when acquisition is incomplete."""
        manifest_path, coverage_path = root / "data/source_manifest.json", root / "outputs/task2/coverage.json"
        return {"api_version": API_VERSION, "ready": app.state.input_error is None,
                "manifest": json.loads(manifest_path.read_text()) if manifest_path.exists() else None,
                "coverage": json.loads(coverage_path.read_text()) if coverage_path.exists() else None,
                "warnings": WARNINGS + ([app.state.input_error] if app.state.input_error else [])}

    @app.get("/candidates", response_model=Candidates)
    def candidates():
        """Return actual county evidence and provenance; never substitute fixtures."""
        path = root / "outputs/task2/candidates.json"
        if not path.exists():
            return unavailable()
        return {"api_version": API_VERSION, "evidence": json.loads(path.read_text()), "warnings": WARNINGS}

    @app.post("/runs", response_model=Job, status_code=202, responses={200: {"model": Job}})
    def submit(body: RunRequest):
        """Validate/freeze settings and return immediately after bounded enqueueing."""
        if app.state.input_error:
            return unavailable()
        try:
            record = store.submit(body.config.model_dump(), body.options.model_dump())
        except QueueFull:
            return error_response(503, "QUEUE_FULL", "The run queue is full; retry after a pending job completes.")
        except CacheIntegrityError:
            # A damaged run cache must not disable unrelated healthy input datasets.
            return error_response(409, "CACHE_INTEGRITY_FAILED", "Cached run evidence is missing, damaged or differs from its frozen identity; review it before explicit recomputation.")
        except (FileNotFoundError, OSError):
            app.state.input_error = "Required frozen inputs became unavailable; acquire/preprocess and restart the server."
            return error_response(503, "INPUTS_UNAVAILABLE", "Required frozen inputs are unavailable; acquire/preprocess them.")
        except ValueError as exc:
            # Override geography is request-dependent; checksum/data failures are readiness errors.
            if "regional override" in str(exc):
                return error_response(422, "VALIDATION_ERROR", "The request contains invalid settings.",
                    [{"field": "config.scenario_set.regional_overrides", "message": str(exc)}])
            logging.exception("Frozen inputs rejected at submission")
            app.state.input_error = "Frozen inputs became invalid or changed checksums; restore/review them and restart the server."
            return error_response(503, "INPUTS_UNAVAILABLE", "Frozen inputs are invalid or their checksums have changed.")
        return JSONResponse(status_code=200 if record["cached"] else 202, content=Job.model_validate(record).model_dump())

    @app.get("/runs/{run_id}", response_model=Job)
    def poll(run_id: str):
        """Return persisted status, full results or a sanitized failure explanation."""
        record = store.get(run_id)
        return record if record is not None else error_response(404, "NOT_FOUND", "Unknown run ID.")

    @app.get("/runs/{run_id}/candidates/{candidate_id}", response_model=CandidateResult)
    def candidate_result(run_id: str, candidate_id: str):
        """Join frozen per-run evidence with scenario outcomes or exclusion reasons."""
        record = store.get(run_id)
        if record is None:
            return error_response(404, "NOT_FOUND", "Unknown run ID.")
        evidence = json.loads((root / "outputs" / run_id / "candidate_evidence.json").read_text())
        candidate = next((row for row in evidence["candidates"] if row["candidate_id"] == candidate_id), None)
        if not re.fullmatch(r"[0-9]{5}", candidate_id) or candidate is None:
            return error_response(404, "NOT_FOUND", "Unknown candidate ID.")
        if record["status"] != "completed":
            return error_response(409, "RESULTS_UNAVAILABLE", "Candidate results require a completed run.")
        result = record["result"]
        scenarios = [{"scenario_id": scenario["scenario_id"], "outcome": next(
            (row for row in scenario["candidates"] if row["candidate_id"] == candidate_id), None)} for scenario in result["scenarios"]]
        return {"api_version": API_VERSION, "run_id": run_id, "candidate_id": candidate_id,
                "evidence": candidate, "objective_units": result["objective_units"], "scenarios": scenarios,
                "exclusion_reasons": next((row["reasons"] for row in result["excluded_candidates"] if row["candidate_id"] == candidate_id), []),
                "warnings": result["warnings"], "boundary_exclusions": result["boundary_exclusions"]}

    return app


# Uvicorn imports a lightweight factory result; actual checks occur during lifespan.
app = create_app()
