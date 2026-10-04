"""Command line: ``.venv/Scripts/python -m dc_rediscovery {acquire,run} ...`` from the project root."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dc_locator.paths import project_root

from .config import load_config
from .facilities import acquire, download_record


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="dc_rediscovery", description=(
        "Blind national candidate generation from a completed dc_locator run, then post-hoc comparison with "
        "existing U.S. data centers against random baselines."))
    commands = parser.add_subparsers(dest="command", required=True)
    fetch = commands.add_parser("acquire", help="Download the pinned public facility inventory into data/raw (verified, once)")
    fetch.add_argument("--config", default="configs/rediscovery.yaml")
    execute = commands.add_parser("run", help="Run (or verify and reuse) one rediscovery analysis")
    execute.add_argument("--config", default="configs/rediscovery.yaml")
    execute.add_argument("--output", default="runs/rediscovery_v1", help="New runs/<name> folder for the outputs")
    execute.add_argument("--acquire", action="store_true", help="Permit acquiring the pinned public inventory if absent")
    args = parser.parse_args(argv)
    root = Path(project_root())
    config_path = root / args.config
    if args.command == "acquire":
        source = load_config(config_path).facilities
        path = acquire(source, root)
        record = download_record(source, root)
        print(f"Facility inventory ready: {path} ({record['bytes']:,} bytes, sha256 {record['sha256']})")
        return 0
    from .pipeline import run

    manifest = run(config_path, args.output, root=root, acquire_facilities=args.acquire)
    print(f"analysis_identity={manifest['analysis_identity']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
