"""Nine executable commands over the accepted geographic and model APIs.

build-grid retains its original flags; configured delivery stages verify
current input, output, code and environment identities before reuse.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dc_locator import __version__
from dc_locator.config import ConfigValidationError, load_grid_config
from dc_locator.paths import ProjectRootNotFoundError, configs_dir, processed_dir, project_root

_DELIVERY_COMMANDS = ("ingest", "build-features", "screen", "simulate", "rank", "cluster", "validate", "run")


def _sha256_of_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cmd_build_grid(args: argparse.Namespace) -> int:
    # Imported lazily: these pull in geopandas/shapely/pyproj, which every
    # other subcommand does not need merely to parse arguments.
    from dc_locator.geography.boundary import download_conus_boundary_sources, load_conus_boundary
    from dc_locator.geography.grid import select_study_area
    from dc_locator.geography.grid import generate_national_grid

    grid_config_path = Path(args.grid_config) if args.grid_config else configs_dir() / "grid.yaml"
    try:
        grid_config = load_grid_config(grid_config_path)
    except (ConfigValidationError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    out_dir = (Path(args.output_dir) if args.output_dir else processed_dir()).resolve()
    root=project_root().resolve()
    if not out_dir.is_relative_to(root) or any(out_dir.is_relative_to(root/'runs'/f'phase{n}') for n in range(1,7)):
        raise ValueError('Grid output must stay inside the project and preserve historical accepted run folders')
    if not args.skip_download:
        download_conus_boundary_sources()
    boundary = load_conus_boundary()

    print(f"Generating national grid ({grid_config.grid_definition_id()}) ...", file=sys.stderr)
    national_grid, stats = generate_national_grid(grid_config, boundary)
    print(f"  retained {stats['n_retained']:,} cells.", file=sys.stderr)

    out_dir.mkdir(parents=True, exist_ok=True)

    from dc_locator.io import write_geoparquet
    from dc_locator.provenance import DataMode

    national_path = out_dir / "us_grid.parquet"
    write_geoparquet(
        national_grid,
        national_path,
        schema_name="GridCell",
        schema_version="1.1.0",
        data_mode=DataMode.REAL,
        grid_definition_id=grid_config.grid_definition_id(),
    )
    print(f"  wrote {national_path}", file=sys.stderr)

    dev_outputs = {}
    if not args.national_only:
        for name, bbox in grid_config.study_areas.items():
            dev_grid = select_study_area(national_grid, bbox)
            dev_path = out_dir / f"us_grid__{name}.parquet"
            write_geoparquet(
                dev_grid,
                dev_path,
                schema_name="GridCell",
                schema_version="1.1.0",
                data_mode=DataMode.REAL,
                grid_definition_id=grid_config.grid_definition_id(),
            )
            dev_outputs[name] = {"path": str(dev_path), "n_cells": int(len(dev_grid))}
            print(f"  wrote {dev_path} ({len(dev_grid)} cells)", file=sys.stderr)

    summary = {
        "grid_definition_id": grid_config.grid_definition_id(),
        "crs": grid_config.crs,
        "origin_x_m": grid_config.origin_x_m,
        "origin_y_m": grid_config.origin_y_m,
        "cell_size_m": grid_config.cell_size_m,
        "boundary_source_id": boundary.source_id,
        "boundary_vintage": boundary.vintage,
        "boundary_state_zip_sha256": boundary.state_zip_sha256,
        "boundary_county_zip_sha256": boundary.county_zip_sha256,
        "generation_stats": stats,
        "total_study_area_intersection_km2": float(national_grid["study_area_intersection_km2"].sum()),
        "total_cell_area_km2": float(national_grid["cell_area_km2"].sum()),
        "per_state_cell_counts": national_grid["state_fips_primary"].value_counts().sort_index().to_dict(),
        "files": {
            "national": {"path": national_path.name, "n_cells": int(stats["n_retained"]), "sha256": _sha256_of_file(national_path)},
            **{
                name: {"path": f"us_grid__{name}.parquet", "n_cells": info["n_cells"], "sha256": _sha256_of_file(Path(info["path"]))}
                for name, info in dev_outputs.items()
            },
        },
    }
    summary_path = out_dir / "us_grid_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"  wrote {summary_path}", file=sys.stderr)

    print(json.dumps({"national": {"path": str(national_path), "n_cells": stats["n_retained"]}, "development_areas": dev_outputs, "summary_path": str(summary_path), "stats": stats}, indent=2))
    return 0


def _cmd_delivery(args: argparse.Namespace) -> int:
    from dc_locator.pipeline import execute_stage
    result=execute_stage(args.command,args.config,args.output)
    print(json.dumps(result,sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dc-locator", description="U.S. Sustainable Data Center Location Discovery Model.")
    parser.add_argument("--version", action="version", version=f"dc_locator {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_grid = subparsers.add_parser("build-grid", help="Generate the national grid and configured development-area subsets (Phase 1).")
    build_grid.add_argument("--grid-config", default=None, help="Path to grid.yaml (default: configs/grid.yaml).")
    build_grid.add_argument("--output-dir", default=None, help="Output directory (default: data/processed/).")
    build_grid.add_argument("--national-only", action="store_true", help="Skip generating development-area subsets.")
    build_grid.add_argument("--skip-download", action="store_true", help="Skip the boundary-source download step (use the existing data/raw/ cache as-is).")
    build_grid.set_defaults(func=_cmd_build_grid)

    for name in _DELIVERY_COMMANDS:
        sub = subparsers.add_parser(name, help=f"Execute configured {name} with verified current inputs.")
        sub.add_argument('--config',default='configs/run.yaml',help='Delivery run YAML; paths resolve from the project root.')
        sub.add_argument('--output',default='runs/example',help='Owned run folder; use a new folder after model/config/source changes.')
        sub.set_defaults(func=_cmd_delivery)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        project_root()
    except ProjectRootNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    try:return args.func(args)
    except (ValueError,FileNotFoundError,RuntimeError) as exc:
        print(f'error: {exc}',file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())


__all__ = ["main", "build_parser"]
