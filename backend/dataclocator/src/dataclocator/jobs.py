"""Bounded, persistent local jobs; one API process owns the file-backed queue."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import os
import json
import logging
from pathlib import Path
import re
import threading

from .experiments import prepare_run, run_experiment
from .pipeline import write_json

RUN_PATTERN = re.compile(r"run_[0-9a-f]{16}\Z")


def claim_owner_file(stream):
    """Lock one byte on Windows or the file on Unix; closing releases ownership.

    This transport-only portability change leaves simulation and cache math intact.
    Windows locking requires an existing byte and a consistent file position.
    """
    if os.name == "nt":
        import msvcrt
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write("0")
            stream.flush()
        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)


class QueueFull(Exception):
    """Signal saturation without enqueueing or creating partial job metadata."""


def utc_now():
    """Use timezone-explicit UTC timestamps in every persisted job transition."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class JobStore:
    """Serialize submissions, deduplicate runs and bound pending computation."""

    def __init__(self, root, warnings, *, workers=1, queue_size=4, runner=run_experiment):
        """Allow an injected test runner while production always uses the real model."""
        if workers != 1 or queue_size < 0:
            raise ValueError("MVP supports one model worker and a nonnegative waiting queue")
        self.root, self.warnings = Path(root), warnings
        self.workers, self.queue_size, self.runner = workers, queue_size, runner
        self.directory = self.root / "outputs/api-jobs"
        self.records, self.lock = {}, threading.RLock()
        self.executor = None
        self.owner_file = None

    def start(self):
        """Claim exclusive process ownership and mark interrupted work as failed."""
        self.directory.mkdir(parents=True, exist_ok=True)
        self.owner_file = (self.directory / ".owner.lock").open("a")
        try:
            claim_owner_file(self.owner_file)
        except OSError:
            self.owner_file.close()
            self.owner_file = None
            raise RuntimeError("This data root already has an API owner; use a single Uvicorn worker") from None
        try:
            for path in self.directory.glob("run_*.json"):
                if not RUN_PATTERN.fullmatch(path.stem):
                    continue
                record = json.loads(path.read_text())
                if record["run_id"] != path.stem:
                    raise ValueError("Job record identity mismatch")
                if record["status"] in {"queued", "running"}:
                    record.update(status="failed", finished_at=utc_now(), error={"code": "RUN_INTERRUPTED",
                        "message": "The server stopped before this run completed; resubmit to retry.", "details": []})
                    self._save(record)
                self.records[path.stem] = record
            self.executor = ThreadPoolExecutor(max_workers=self.workers, thread_name_prefix="dataclocator-model")
        except Exception:
            self.owner_file.close()
            self.owner_file = None
            raise

    def close(self):
        """Drain accepted jobs on graceful shutdown and release process ownership."""
        if self.executor is not None:
            self.executor.shutdown(wait=True)
        if self.owner_file is not None:
            self.owner_file.close()
            self.owner_file = None

    def _save(self, record):
        """Atomically persist metadata so readers never observe a partial JSON file."""
        write_json(self.directory / (record["run_id"] + ".json"), record)

    def counts(self):
        """Report actual states, counting a just-submitted job as queued until started."""
        with self.lock:
            return {state: sum(record["status"] == state for record in self.records.values()) for state in ["running", "queued"]}

    def get(self, run_id, *, cached=None):
        """Load completed results only at polling time, keeping persisted metadata small."""
        if not RUN_PATTERN.fullmatch(run_id):
            return None
        with self.lock:
            if run_id not in self.records:
                return None
            record = json.loads(json.dumps(self.records[run_id]))
            if cached is not None:
                record["cached"] = cached
            if record["status"] == "completed":
                record["result"] = json.loads((self.root / "outputs" / run_id / "results.json").read_text())
            return record

    def submit(self, config, options):
        """Freeze validated bytes before accepting and reuse identical pending jobs."""
        frozen = prepare_run(self.root, config, with_sensitivity=options["sensitivity"], with_convergence=options["convergence"])
        run_id = frozen["run_id"]
        with self.lock:
            old = self.records.get(run_id)
            if old and old["status"] in {"queued", "running", "completed"}:
                return self.get(run_id, cached=old["status"] == "completed")
            directory = self.root / "outputs" / run_id
            completed = (directory / "results.json").is_file()
            if not completed and sum(self.counts().values()) >= self.workers + self.queue_size:
                raise QueueFull()
            # Capture evidence at submission, not when a waiting worker starts.
            if not (directory / "candidate_evidence.json").exists() or not completed:
                write_json(directory / "candidate_evidence.json", frozen["evidence"])
            write_json(directory / "input_snapshot.json", frozen)
            record = {"api_version": "1.0", "run_id": run_id, "status": "completed" if completed else "queued",
                      "cached": completed, "submitted_at": utc_now(), "started_at": None,
                      "finished_at": utc_now() if completed else None,
                      "links": {"self": f"/runs/{run_id}", "candidates": f"/runs/{run_id}/candidates/{{candidate_id}}"},
                      "warnings": self.warnings, "result": None, "error": None}
            self.records[run_id] = record
            self._save(record)
            if not completed:
                self.executor.submit(self._execute, frozen, options)
            return self.get(run_id, cached=completed)

    def _execute(self, frozen, options):
        """Run only the captured inputs; convert internal exceptions to safe job errors."""
        run_id = frozen["run_id"]
        with self.lock:
            record = self.records[run_id]
            record.update(status="running", started_at=utc_now())
            self._save(record)
        try:
            result = self.runner(self.root, frozen["identity"]["config"],
                with_sensitivity=options["sensitivity"], with_convergence=options["convergence"], prepared=frozen)
            if result["run_id"] != run_id:
                raise ValueError("Model result identity does not match the accepted job")
            # The real runner already commits its artifacts; test runners use this marker too.
            write_json(self.root / "outputs" / run_id / "results.json", result)
            with self.lock:
                record.update(status="completed", finished_at=utc_now())
                self._save(record)
        except Exception:
            logging.exception("Model job %s failed", run_id)
            with self.lock:
                record.update(status="failed", finished_at=utc_now(), error={"code": "RUN_FAILED",
                    "message": "Run computation failed; consult server logs and resubmit to retry.", "details": []})
                self._save(record)
