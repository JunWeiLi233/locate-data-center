"""Robustness interface: Monte Carlo evidence attaches to candidates without being invented.

The deterministic model answers "which locations score highest under the current assumptions?" A Monte
Carlo component answers "how robust is that when assumptions, weights or uncertain inputs change?". This
module defines the contract between the two. A provider returns, for each candidate:

- ``robustness_score``: 0–100, or null;
- ``robustness_status``: ``calculated`` or ``unknown``;
- ``robustness_method``, ``robustness_source``, ``robustness_spatial_support`` and ``robustness_details``;
- ``robustness_missing_reason`` whenever the score is null.

Providers run in their configured order, and the first one that yields a score for a candidate wins.
Without evidence the score stays null. It is never zero and never a neutral default.

Implemented providers:

- ``county_monte_carlo`` reads a completed run of the separately developed county model
  (``backend/dataclocator``). That model draws 5,000 PUE/WUE and rate quantiles per structural scenario and
  records how often each county is on the cost/CO2e/water Pareto frontier. For a candidate inside an
  evaluated county, the score is 100 × the mean Pareto-frontier frequency across the separate structural
  scenarios. Its support is the county, and it is compared only with that model's county cohort. A 1 km
  candidate inherits its county's value, which is not a property of the cell.
- ``table`` is the reserved contract for a future grid-cell Monte Carlo. It accepts a CSV, Parquet or JSON
  table keyed by ``grid_id`` with ``robustness_score`` in [0, 100] and ``method``, ``source`` and ``draws``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

import numpy as np
import pandas as pd

from dc_locator.geography.sources.ingestion import file_digest

FIELDS = ["robustness_score", "robustness_status", "robustness_provider", "robustness_method", "robustness_source",
          "robustness_spatial_support", "robustness_missing_reason", "robustness_details"]


class RobustnessProvider(Protocol):
    provider_id: str

    def describe(self) -> dict: ...

    def evaluate(self, candidates: pd.DataFrame) -> pd.DataFrame: ...


def _unknown(reason: str, provider: str | None = None) -> dict:
    return {"robustness_score": None, "robustness_status": "unknown", "robustness_provider": provider,
            "robustness_method": None, "robustness_source": None, "robustness_spatial_support": None,
            "robustness_missing_reason": reason, "robustness_details": None}


class CountyMonteCarloProvider:
    provider_id = "county_monte_carlo"

    def __init__(self, results_path: Path, root: Path, label: str):
        self.path = results_path
        self.root = root
        self.label = label
        self.available = False
        self.reason = None
        self.counties: dict[str, dict] = {}
        self.run: dict = {}
        self._load()

    def _load(self):
        if not self.path.is_file():
            self.reason = f"County Monte Carlo results not found at {self._relative(self.path)}"
            return
        integrity_path = self.path.parent / "cache_integrity.json"
        if not integrity_path.is_file():
            self.reason = "County Monte Carlo run lacks cache_integrity.json; incomplete runs are not used"
            return
        integrity = json.loads(integrity_path.read_text(encoding="utf-8"))
        digest = file_digest(self.path)
        if integrity.get("artifact_hashes", {}).get("results.json") != digest:
            self.reason = "County Monte Carlo results.json does not match its integrity record"
            return
        document = json.loads(self.path.read_text(encoding="utf-8"))
        if document.get("status") != "completed":
            self.reason = f"County Monte Carlo run status is {document.get('status')!r}, not completed"
            return
        scenarios = document.get("scenarios") or []
        if not scenarios:
            self.reason = "County Monte Carlo run has no structural scenarios"
            return
        for scenario in scenarios:
            for candidate in scenario.get("candidates", []):
                fips = str(candidate["candidate_id"]).zfill(5)
                record = self.counties.setdefault(fips, {"county_fips": fips, "name": candidate.get("name"),
                                                         "state_abbr": candidate.get("state_abbr"), "frequencies": [],
                                                         "expected_frontier": 0, "robust_frontier": 0, "scenarios": 0})
                frequency = candidate.get("pareto_frequency")
                if frequency is not None and np.isfinite(frequency):
                    record["frequencies"].append(float(frequency))
                record["expected_frontier"] += bool(candidate.get("expected_frontier"))
                record["robust_frontier"] += bool(candidate.get("robust_frontier"))
                record["scenarios"] += 1
        config = document.get("config", {})
        self.run = {"run_id": document.get("run_id"), "model_version": document.get("model_version"),
                    "results_path": self._relative(self.path), "results_sha256": digest, "seed": document.get("seed"),
                    "draws": config.get("simulation_count"), "feasibility_mode": config.get("feasibility_mode"),
                    "structural_scenarios": [scenario.get("scenario_id") for scenario in scenarios],
                    "evaluated_counties": len(self.counties),
                    "scenario_weighting": "none; scenarios are separate structural paths averaged with equal presentation weight"}
        self.available = True

    def _relative(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.root.resolve()).as_posix()
        except ValueError:
            return str(path)

    def describe(self) -> dict:
        return {"provider_id": self.provider_id, "label": self.label, "available": self.available,
                "missing_reason": self.reason, "run": self.run,
                "score_definition": "100 × mean Pareto-frontier frequency of the candidate's county across separate structural scenarios",
                "spatial_support": "county (the county Monte Carlo evaluates one representative location per county)",
                "comparison_set": f"{len(self.counties)} counties evaluated by the county Monte Carlo model",
                "limitations": ["Objectives are lifetime electricity cost, operational CO2e and direct cooling water; they differ from the grid model's criteria.",
                                "PUE/WUE priors and rate scenarios are demonstration assumptions of the county model, not calibrated forecasts.",
                                "With common engineering draws, frontier frequencies are often exactly 0 or 1; they are not probabilities of being best."]}

    def evaluate(self, candidates: pd.DataFrame) -> pd.DataFrame:
        rows = []
        for fips in candidates.county_geoid:
            if not self.available:
                rows.append(_unknown(self.reason, self.provider_id))
                continue
            record = self.counties.get(fips) if isinstance(fips, str) else None
            if record is None:
                rows.append(_unknown("The candidate's county is not in the county Monte Carlo cohort" if isinstance(fips, str)
                                     else "Candidate county is unknown, so no county Monte Carlo record can apply", self.provider_id))
                continue
            if not record["frequencies"]:
                rows.append(_unknown("County Monte Carlo record has no finite Pareto-frontier frequency", self.provider_id))
                continue
            score = 100.0 * float(np.mean(record["frequencies"]))
            rows.append({"robustness_score": score, "robustness_status": "calculated", "robustness_provider": self.provider_id,
                         "robustness_method": "county_monte_carlo_pareto_frequency",
                         "robustness_source": f"{self.run['run_id']} ({self.run['draws']} draws per scenario)",
                         "robustness_spatial_support": "county", "robustness_missing_reason": None,
                         "robustness_details": {"county_fips": fips, "county_name": record["name"], "state_abbr": record["state_abbr"],
                                                "structural_scenarios": record["scenarios"],
                                                "expected_frontier_scenarios": record["expected_frontier"],
                                                "robust_frontier_scenarios": record["robust_frontier"],
                                                "pareto_frequency_by_scenario": record["frequencies"]}})
        return pd.DataFrame(rows, columns=FIELDS)


class TableProvider:
    """Reserved contract for a future grid-cell Monte Carlo: one row per grid_id, robustness_score in [0, 100]."""
    provider_id = "table"

    def __init__(self, path: Path | None, root: Path, label: str):
        self.path, self.root, self.label = path, root, label
        self.table = None
        self.reason = None
        if path is None:
            self.reason = "No grid-cell Monte Carlo robustness table has been supplied yet"
        elif not path.is_file():
            self.reason = f"Robustness table not found: {path}"
        else:
            self.table = self._read(path)

    @staticmethod
    def _read(path: Path) -> pd.DataFrame:
        if path.suffix == ".parquet":
            table = pd.read_parquet(path)
        elif path.suffix == ".csv":
            table = pd.read_csv(path)
        elif path.suffix == ".json":
            table = pd.DataFrame(json.loads(path.read_text(encoding="utf-8")))
        else:
            raise ValueError("Robustness tables must be .parquet, .csv or .json")
        required = {"grid_id", "robustness_score", "method", "source", "draws"}
        if not required <= set(table.columns):
            raise ValueError(f"Robustness table lacks {sorted(required - set(table.columns))}")
        if table.grid_id.isna().any() or table.grid_id.duplicated().any():
            raise ValueError("Robustness table grid_id values must be unique and non-null")
        scores = pd.to_numeric(table.robustness_score, errors="coerce")
        present = table.robustness_score.notna()
        if (present & ~np.isfinite(scores)).any() or (scores[present] < 0).any() or (scores[present] > 100).any():
            raise ValueError("Robustness scores must be finite values within [0, 100] or null")
        return table.assign(robustness_score=scores).set_index("grid_id")

    def describe(self) -> dict:
        return {"provider_id": self.provider_id, "label": self.label, "available": self.table is not None,
                "missing_reason": self.reason, "path": None if self.path is None else str(self.path),
                "contract": "grid_id, robustness_score (0-100 or null), method, source, draws; one row per grid cell"}

    def evaluate(self, candidates: pd.DataFrame) -> pd.DataFrame:
        rows = []
        for grid_id in candidates.grid_id:
            if self.table is None:
                rows.append(_unknown(self.reason, self.provider_id))
                continue
            if grid_id not in self.table.index or pd.isna(self.table.at[grid_id, "robustness_score"]):
                rows.append(_unknown("Grid-cell Monte Carlo table has no value for this candidate", self.provider_id))
                continue
            record = self.table.loc[grid_id]
            rows.append({"robustness_score": float(record.robustness_score), "robustness_status": "calculated",
                         "robustness_provider": self.provider_id, "robustness_method": str(record.method),
                         "robustness_source": str(record.source), "robustness_spatial_support": "grid_cell",
                         "robustness_missing_reason": None, "robustness_details": {"draws": int(record.draws)}})
        return pd.DataFrame(rows, columns=FIELDS)


def build_providers(configs, root: Path) -> list:
    providers = []
    for config in configs:
        path = None if config.path is None else (root / config.path).resolve()
        if config.kind == "county_monte_carlo":
            providers.append(CountyMonteCarloProvider(path, root, config.label))
        else:
            providers.append(TableProvider(path, root, config.label))
    return providers


def combine(providers: list, candidates: pd.DataFrame) -> pd.DataFrame:
    """The first provider that yields a score wins, in configured order; otherwise the joined reasons explain the null."""
    if not providers:
        return pd.DataFrame([_unknown("No Monte Carlo robustness provider is configured")] * len(candidates), columns=FIELDS)
    results = [provider.evaluate(candidates).reset_index(drop=True) for provider in providers]
    rows = []
    for index in range(len(candidates)):
        chosen = next((result.iloc[index].to_dict() for result in results if result.iloc[index].robustness_status == "calculated"), None)
        if chosen is None:
            reasons = [f"{provider.provider_id}: {result.iloc[index].robustness_missing_reason}" for provider, result in zip(providers, results)]
            chosen = _unknown("; ".join(reasons))
        rows.append(chosen)
    return pd.DataFrame(rows, columns=FIELDS)
