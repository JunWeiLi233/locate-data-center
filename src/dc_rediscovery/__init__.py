"""Post-hoc rediscovery validation of the deterministic model against existing U.S. data centers.

The package is a read-only consumer of ``dc_locator``. It scores the model's completed national 1 km
fine surface with the model's own functions, selects separated Top-N candidates, and only afterwards
loads an external inventory of existing facilities to measure geographic agreement against random
baselines.

Leakage rule: existing-facility locations are never a model feature. ``dc_locator`` must never import this
package. Candidate generation (``surface``) receives no facility input. Its blind output is hashed before
the facility inventory is opened.

It lives outside ``src/dc_locator`` so that the hash-bound model inventory (``Pipeline.verify_binding``)
is unchanged.

These geographic regions deserve further investigation under the stated facility requirements, datasets,
constraints, assumptions, and decision preferences. They are not proven buildable parcels and not
America's objectively best places to build a data center. Existing facilities are an external sanity
check, not ground truth.
"""

__version__ = "1.0.0"
SCHEMA_VERSION = "1.0.0"
