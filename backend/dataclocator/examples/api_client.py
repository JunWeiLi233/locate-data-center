"""Submit a documented local request, poll its bounded job, and save full JSON."""

import argparse
import json
from pathlib import Path
import time

import requests


def main():
    """Keep all model assumptions in the input file and bound the polling deadline."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--request", type=Path, default=Path("docs/api-smoke-request.json"))
    parser.add_argument("--output", type=Path, default=Path("outputs/api-client-result.json"))
    parser.add_argument("--timeout", type=float, default=600, help="maximum polling seconds")
    args = parser.parse_args()
    # Submission returns a run ID promptly; computation happens outside the request.
    response = requests.post(args.url.rstrip("/") + "/runs", json=json.loads(args.request.read_text()), timeout=30)
    response.raise_for_status()
    job = response.json()
    deadline = time.monotonic() + args.timeout
    while job["status"] in {"queued", "running"}:
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Run {job['run_id']} still pending; poll its self link later")
        time.sleep(.5)
        response = requests.get(args.url.rstrip("/") + job["links"]["self"], timeout=30)
        response.raise_for_status()
        job = response.json()
    if job["status"] == "failed":
        raise RuntimeError(json.dumps(job["error"]))
    # Persist the complete response, including provenance and warnings, for review.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(job, indent=2, allow_nan=False) + "\n")
    print(f"{job['run_id']}: {job['result']['status']}; saved {args.output}")


if __name__ == "__main__":
    # The example is a CLI integration client, never a product frontend.
    main()
