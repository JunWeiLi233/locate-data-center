"""Offline real-data artifact and cache checks without live data substitution."""

import copy
import json
import socket
from pathlib import Path

import pytest

from dataclocator.experiments import run_experiment

ROOT = Path(__file__).resolve().parents[1]
# Pure-function tests still work on fresh checkouts without the official archives.
pytestmark = pytest.mark.skipif(not (ROOT / "data/processed/grid_regions.parquet").exists(), reason="acquire/preprocess required")


def test_frozen_offline_run_and_cache(tmp_path, monkeypatch):
    """Network-disabled runs export finite JSON and reuse completed artifacts."""
    def network_forbidden(*args, **kwargs):
        """Unexpected live connections fail instead of substituting synthetic data."""
        raise AssertionError("offline run attempted network access")
    monkeypatch.setattr(socket, "create_connection", network_forbidden)
    # Read original frozen files through symlinks without copying 485 MB of archives.
    (tmp_path / "data").symlink_to(ROOT / "data", target_is_directory=True)
    (tmp_path / "outputs/task2").mkdir(parents=True)
    (tmp_path / "outputs/task2/candidates.json").symlink_to(ROOT / "outputs/task2/candidates.json")
    config = copy.deepcopy(json.loads((ROOT / "configs/monte-carlo-demo.json").read_text()))
    config["simulation_count"] = 32
    config["analysis_horizon_years"] = 3
    config["scenario_set"] = config["scenario_set"][:1]
    config["bootstrap_resamples"] = 20
    result = run_experiment(tmp_path, config, with_convergence=False, with_sensitivity=False)
    directory = tmp_path / "outputs" / result["run_id"]
    for name in ["results.json", "config.json", "run_identity.json", "samples.npz", "common_draws.npz",
                 "annual_trajectories.csv", "candidates.csv", "report.md", "frontiers.png", "frontiers.svg"]:
        assert (directory / name).is_file()
    assert result["status"] == "completed" and len(result["scenarios"][0]["candidates"]) == 45
    assert len(result["dataset_hashes"]) == 20
    def reject_constant(value):
        """Strict consumers must never encounter NaN or Infinity in result JSON."""
        raise ValueError(value)
    exported = json.loads((directory / "results.json").read_text(), parse_constant=reject_constant)
    assert exported["run_id"] == result["run_id"]
    # Reusing the completed marker must avoid simulation and plot recomputation.
    def recomputation_forbidden(*args, **kwargs):
        """Identical configuration and hashes must hit the completed cache."""
        raise AssertionError("cache miss for identical configuration")
    monkeypatch.setattr("dataclocator.experiments.simulate", recomputation_forbidden)
    cached = run_experiment(tmp_path, config, with_convergence=False, with_sensitivity=False)
    assert cached == result
