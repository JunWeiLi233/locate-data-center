"""Model: given a facility spec and decision configuration, which areas are
promising?

This package answers the decision-analysis question -- screening, physics,
metrics, Pareto, AHP/MCDA, clustering, scenarios, lifecycle, validation
(AGENTS.md section 2). It must never download or parse source-specific data;
that is `dc_locator.geography`'s job.

Phase 3 provides cooling.py (complete design/scenario contracts),
screening.py (requirement evidence and eligibility) and physics.py (annual
energy/carbon/water calculations). Decision analysis and clustering belong
to later phases. Geography remains a read-only model input.
"""

from __future__ import annotations

__all__: list[str] = []
