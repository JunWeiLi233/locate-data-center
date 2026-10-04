# One-minute cached regional Grid evaluation

The user authorized fixed cached nationwide 1 km regional evidence as the default
fast search, retaining a separately selectable longer nationwide rediscovery.
The target is a changed facility request completed and ready to display in under
60 seconds after the fixed input cache has been prepared. Preparation time must
be recorded separately. A saved result load alone does not meet this target.

## Implementation decision

The active independent scientific delivery binds the file set under
`src/dc_locator/`. Leave that package, configuration files and accepted outputs
unchanged. Add production cached-cohort orchestration in `src/dc_locator_fast.py`;
record its own content binding and the exact existing model functions/policies it
uses in each new run. This module is a new delivery revision and is not an
alteration of the in-flight package binding or an implementation of mathematics
in the frontend transport.

Use all 152,500 cached native cells from `runs/cleanview_regional_v2`, retaining
stable grid IDs, 1 km resolution, native source provenance, UNKNOWN states,
hard-failure exclusion and maximum 20 km projected region spans. Recompute
facility-dependent physics through accepted functions, then normalization,
preferences, exact global ranks/Pareto and region clustering. Reuse screening
only where its dependency invariance is explicitly checked. Broad diagnostic
reruns are not part of this mode and must be marked not assessed.

The API uses a separate bounded fast execution path, exact request deduplication
and checksum-bound completed outputs. It discloses a fixed cached regional
ranking universe. The page defaults to this mode when supported and exposes
full rediscovery as a longer option. Preserve the County model and economic
filters, existing saved-run loading, and selected-window geographic layers.

## Verification

1. Compare changed-input outputs with accepted model functions on native samples,
   including missing evidence, strict empty results and changed preferences.
2. Check full-cohort cell count, deterministic output, native geometry limits,
   provenance/cache corruption handling and output lineage.
3. Benchmark a fresh changed facility over the complete cohort and include API
   materialization, compressed transfer and browser readiness in the live timing.
4. Run model and API regressions, all frontend tests and a production build.
5. Preserve before/after scientific bindings, timing logs, live request/response
   evidence and the actual page screenshot in `runs/grid_one_minute_v1/`.
6. Update the handoff/contracts/run index and remove owned scratch.
