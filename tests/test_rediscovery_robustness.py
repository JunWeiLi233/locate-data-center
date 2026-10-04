"""Robustness interface: Monte Carlo evidence attaches without invention, and nulls carry reasons."""
import hashlib
import json

import pandas as pd
import pytest

from dc_rediscovery.robustness import CountyMonteCarloProvider, TableProvider, combine


def _county_run(folder, status="completed", tamper=False):
    """A synthetic county Monte Carlo result in the dataclocator results contract (test fixture only)."""
    folder.mkdir(parents=True)
    scenarios = []
    for scenario, frequencies in (("s1", {"36065": 1.0, "23019": 0.0}), ("s2", {"36065": 0.5, "23019": 0.0})):
        scenarios.append({"scenario_id": scenario, "candidates": [
            {"candidate_id": fips, "name": "County " + fips, "state_abbr": "NY" if fips == "36065" else "ME",
             "pareto_frequency": value, "expected_frontier": value == 1.0, "robust_frontier": value == 1.0}
            for fips, value in frequencies.items()]})
    document = {"status": status, "run_id": "run_test", "model_version": "0.2.1", "seed": 42,
                "config": {"simulation_count": 100, "feasibility_mode": "exploratory"}, "scenarios": scenarios}
    results = folder / "results.json"
    results.write_text(json.dumps(document), encoding="utf-8")
    digest = hashlib.sha256(results.read_bytes()).hexdigest()
    (folder / "cache_integrity.json").write_text(json.dumps({"artifact_hashes": {"results.json": "0" * 64 if tamper else digest}}), encoding="utf-8")
    return results


CANDIDATES = pd.DataFrame({"grid_id": ["g1", "g2", "g3"], "county_geoid": ["36065", "23019", "51107"]})


def test_county_monte_carlo_scores_only_evaluated_counties(tmp_path):
    provider = CountyMonteCarloProvider(_county_run(tmp_path / "run"), tmp_path, "County MC")
    result = provider.evaluate(CANDIDATES)
    assert result.robustness_score.tolist()[:2] == pytest.approx([75.0, 0.0])  # 100 × mean(1.0, 0.5); a real zero stays zero
    assert result.robustness_spatial_support.tolist()[:2] == ["county", "county"]
    assert pd.isna(result.robustness_score.iloc[2]) and result.robustness_status.iloc[2] == "unknown"
    assert "not in the county Monte Carlo cohort" in result.robustness_missing_reason.iloc[2]
    assert result.robustness_details.iloc[0]["expected_frontier_scenarios"] == 1


@pytest.mark.parametrize("status,tamper,reason", [("running", False, "not completed"), ("completed", True, "integrity")])
def test_incomplete_or_tampered_runs_are_not_used(tmp_path, status, tamper, reason):
    provider = CountyMonteCarloProvider(_county_run(tmp_path / "run", status, tamper), tmp_path, "County MC")
    assert not provider.available and reason in provider.reason
    assert provider.evaluate(CANDIDATES).robustness_score.isna().all()


def test_table_contract_and_precedence(tmp_path):
    path = tmp_path / "grid_mc.csv"
    pd.DataFrame({"grid_id": ["g3"], "robustness_score": [62.5], "method": ["weight_dirichlet"], "source": ["test"], "draws": [500]}).to_csv(path, index=False)
    table = TableProvider(path, tmp_path, "Grid MC")
    county = CountyMonteCarloProvider(_county_run(tmp_path / "run"), tmp_path, "County MC")
    combined = combine([table, county], CANDIDATES)
    assert combined.robustness_provider.tolist() == ["county_monte_carlo", "county_monte_carlo", "table"]
    assert combined.robustness_score.tolist() == pytest.approx([75.0, 0.0, 62.5])
    missing = combine([TableProvider(None, tmp_path, "Grid MC")], CANDIDATES)
    assert missing.robustness_score.isna().all()
    assert missing.robustness_missing_reason.str.contains("No grid-cell Monte Carlo robustness table has been supplied").all()


def test_table_rejects_out_of_range_scores(tmp_path):
    path = tmp_path / "bad.csv"
    pd.DataFrame({"grid_id": ["g1"], "robustness_score": [140], "method": ["x"], "source": ["y"], "draws": [1]}).to_csv(path, index=False)
    with pytest.raises(ValueError):
        TableProvider(path, tmp_path, "Grid MC")
