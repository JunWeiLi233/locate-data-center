# Cleanview diagnosis and model revision

User-authorized goal (2026-10-03): inspect Cleanview in the browser, compare
existing operating data centers with the current model, identify supported
strengths/defects, and deliver a better model through autoresearch:debug/fix.

Continue current national and regional implementations. Preserve all existing
dirty-tree work and accepted evidence. Store iteration logs under
`runs/cleanview_revision_v1/debug/` and `fix/` rather than the skill's default
top-level `autoresearch/`; repository hygiene takes precedence. Do not make
experiment commits that could include unrelated changes. Record file hashes,
test commands and new-run identities instead.

1. Inspect national public listing, operating detail and Virginia listing through
   the Codex browser. Acquire only the same visible public summaries/cards and
   visible CONUS state links, with raw manifests and capacity-sample limitations.
2. Preserve model-output hashes before diagnosis; compare exact Census-matched
   county support, retaining whole-cell ranges, unknown point locations and
   explicit fine-grid coverage. No physical error/accuracy without observations
   with matching engineering boundaries.
3. Test falsifiable hypotheses about UNKNOWN, units, constant cooling assumptions,
   transmission-support resolution, parent selection and land-boundary screening.
4. Fix confirmed regional land fragmentation: positive insufficient classified
   land in a single cell does not disprove cross-cell search support. Mark only
   the dedicated plausibility requirement UNKNOWN for multi-cell regional runs.
   Keep zero-area and other real failures, STRICT exclusion and standalone
   single-cell behavior. Reject land demand above the projected regional area
   ceiling. Version the changed screening semantics and catalog.
5. Independently review patches; run scoped red/green regressions and the full
   backend suite. Recompute a new regional run from unchanged official sources,
   retaining fresh physics/screening checks and deterministic global decisions.
6. Produce baseline/revision reference comparisons, deterministic repeat checks,
   immutable implementation/input/output bindings, findings, limitations and a
   handoff. No weight or cooling coefficient is fitted to existing locations.

Completed: browser inspection, 49 public-page acquisition/lineage checks,
ten debug hypotheses, scoped repairs, independent review, 792 passing tests,
full revised execution, exact scientific differential and comparison repeat.
The model execution freeze is v2; delivery freeze v3 records only the subsequent
comparison checksum-label repair. Final findings/completion records are in
`runs/cleanview_revision_v1/`, the corrected model in `cleanview_regional_v2/`,
and verified baseline/revised comparisons in `cleanview_baseline_comparison_v4/`
and `cleanview_revised_comparison_v1/`. Earlier attempts remain explicit history.

These geographic regions deserve further investigation under the stated facility
requirements, datasets, constraints, assumptions, and decision preferences.
They are not approved construction parcels. This post-inspection revision does
not constitute an untouched prospective holdout or independent facility validation.
