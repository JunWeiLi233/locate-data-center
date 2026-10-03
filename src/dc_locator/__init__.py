"""dc_locator: U.S. Sustainable Data Center Location Discovery Model.

A deterministic geospatial decision-support system that searches the
contiguous United States (CONUS) on a regular grid and identifies regions
that deserve further investigation for sustainable AI data-center
development, under stated facility requirements, datasets, constraints,
assumptions, and decision preferences.

This package is intentionally split into two components (see AGENTS.md
section 2):

- ``dc_locator.geography`` answers "what does each part of the U.S. look
  like" (grid, source adapters, feature engineering). It must never contain
  thresholds, pass/fail logic, scores, or weights.
- ``dc_locator.model`` answers "given a facility spec and decision
  configuration, which areas are promising" (screening, physics, scoring,
  clustering, validation). It must never download or parse source-specific
  data.

Interpretation of every output of this package (AGENTS.md section 8):
these geographic regions deserve further investigation under the stated
facility requirements, datasets, constraints, assumptions, and decision
preferences. They are NOT proven buildable parcels and NOT "America's
objectively best place to build a data center."
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
