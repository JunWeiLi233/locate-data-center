"""Geography: what does each part of the United States look like?

This package answers purely geographic/data questions -- grid generation,
source adapters, feature engineering (AGENTS.md section 2). It must never
contain thresholds, pass/fail logic, scores, or weights; that is
`dc_locator.model`'s job.

Phase 1 modules:

- `boundary`: authoritative CONUS boundary acquisition and loading.
- `grid`: the configurable national grid and development-area selection.
- `distance`: geodesic and projected-CRS distance helpers.
"""

from __future__ import annotations

__all__: list[str] = []
