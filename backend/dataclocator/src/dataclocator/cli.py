"""Small CLI for frozen acquisition, county preprocessing and accounting evidence."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from .accounting import annual_accounting
from .pipeline import preprocess, verify_raw_inputs, write_json
from .reporting import generate_report


def acquire(root: Path) -> None:
    """Fetch only absent pinned files, rejecting payloads that differ from the lock.

    Mutable publisher links may have changed. That needs a deliberate new release
    review and new manifest, not replacement of a frozen release in place.
    """
    manifest = json.loads((root / "data/source_manifest.json").read_text())
    for source in manifest["sources"]:
        target = root / source["local_path"]
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".partial")
        try:
            # Argument lists prevent source URLs from being evaluated as shell code.
            subprocess.run(["curl", "-fL", "--retry", "2", "--max-time", "180",
                            source["resolved_file_url"], "-o", str(temporary)], check=True)
            with temporary.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if digest != source["sha256"]:
                raise ValueError(f"source changed or corrupt: {source['source_id']}; frozen release not replaced")
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    verify_raw_inputs(root)


def verify_accounting(root: Path) -> dict:
    """Export a hand-computed test fixture, clearly separated from real-site claims."""
    inputs = dict(it_mw=100, utilization=0.85, annual_hours=8760, pue=1.2,
                  wue_l_per_kwh=0.2, price_usd_per_mwh=50, grid_kg_per_mwh=400)
    # These values test arithmetic only; they are not default engineering priors.
    expected = {"it_energy_mwh": 744600, "facility_energy_mwh": 893520,
                "electricity_cost_usd": 44676000, "operational_co2e_tonnes": 357408,
                "direct_water_consumption_m3": 148920, "indirect_water_consumption_m3": None}
    actual = annual_accounting(**inputs)
    if actual != expected:
        raise AssertionError(f"hand-calculated accounting mismatch: {actual}")
    result = {"fixture_only": True, "inputs": inputs, "expected": expected, "actual": actual,
              "status": "passed", "note": "PUE/WUE and price/carbon fixture values do not substantiate a location recommendation."}
    write_json(root / "outputs/task2/accounting_verification.json", result)
    return result


def main() -> None:
    """Dispatch explicit actions; preprocessing always works without live queries."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["acquire", "preprocess", "verify", "check-inputs", "report", "simulate", "serve"])
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--config", type=Path, help="explicit JSON run configuration, required for simulate")
    parser.add_argument("--skip-sensitivity", action="store_true", help="omit additional assumption comparisons")
    parser.add_argument("--skip-convergence", action="store_true", help="omit the 1k/5k/10k convergence audit")
    parser.add_argument("--no-cache", action="store_true", help="recompute a run with the same identity")
    # Serving configuration is explicit; model assumptions still come only from requests.
    parser.add_argument("--host", default="127.0.0.1", help="API bind address, defaults to localhost")
    parser.add_argument("--port", type=int, default=8000, help="API port")
    parser.add_argument("--cors-origin", action="append", default=None, help="explicit allowed origin; repeat for multiple origins")
    parser.add_argument("--queue-size", type=int, default=4, help="maximum waiting API jobs, with one active worker")
    args = parser.parse_args()
    root = args.root.resolve()
    if args.command == "serve":
        # One process owns the local file queue; multiple Uvicorn workers are unsupported.
        import uvicorn
        from .api import create_app
        uvicorn.run(create_app(root, cors_origins=args.cors_origin, queue_size=args.queue_size), host=args.host, port=args.port)
    elif args.command == "acquire":
        acquire(root)
        print("Frozen sources acquired and verified.")
    elif args.command == "preprocess":
        print(json.dumps(preprocess(root), indent=2))
    elif args.command == "verify":
        print(json.dumps(verify_accounting(root), indent=2))
    elif args.command == "report":
        generate_report(root)
        print("Regional report, accounting coefficients and dictionary exported.")
    elif args.command == "simulate":
        # Pure simulation functions remain independent of this file-based interface.
        if args.config is None:
            parser.error("simulate requires --config; engineering assumptions are not defaulted")
        from .experiments import run_experiment
        config_path = args.config if args.config.is_absolute() else root / args.config
        config = json.loads(config_path.read_text())
        result = run_experiment(root, config, with_sensitivity=not args.skip_sensitivity,
                                with_convergence=not args.skip_convergence, use_cache=not args.no_cache)
        print(f"{result['status']}: {root / 'outputs' / result['run_id'] / 'report.md'}")
    else:
        manifest = verify_raw_inputs(root)
        print(f"Verified {len(manifest['sources'])} frozen input checksums.")


if __name__ == "__main__":
    # Support python -m dataclocator.cli without requiring an editable installation.
    main()
