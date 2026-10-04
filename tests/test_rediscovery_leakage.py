"""Existing-facility locations must never reach the model or blind candidate generation."""
import ast
import inspect
from pathlib import Path

import dc_rediscovery.surface as surface

ROOT = Path(__file__).resolve().parents[1]
FACILITY_MARKERS = ("dc_rediscovery", "im3_datacenter_atlas", "datacenter-atlas", "existing_facilities.parquet")


def test_model_package_never_imports_or_reads_the_validation_inventory():
    offenders = []
    for path in sorted((ROOT / "src" / "dc_locator").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        offenders += [f"{path.relative_to(ROOT)}: {marker}" for marker in FACILITY_MARKERS if marker in text]
    assert offenders == []


def test_blind_generation_takes_no_facility_input():
    for function in (surface.load_model_run, surface.score_national_surface, surface.select_candidates, surface.candidate_table):
        parameters = inspect.signature(function).parameters
        assert not any("facilit" in name or "existing" in name for name in parameters), function.__name__
    tree = ast.parse(Path(surface.__file__).read_text(encoding="utf-8"))
    imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert not {"facilities", "validation", "baselines", "robustness"} & {name.split(".")[-1] for name in imported}


def test_pipeline_hashes_blind_candidates_before_opening_the_inventory():
    source = Path(surface.__file__).with_name("pipeline.py").read_text(encoding="utf-8")
    assert source.index('"candidates_blind.parquet"') < source.index("load_inventory(")
    assert source.index("blind_sha = file_digest") < source.index("download_record(source, root)")
