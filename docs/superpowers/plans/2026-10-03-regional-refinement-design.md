# Regional refinement design — approved 1 km resolution

## Requested behavior and measured problem

The user wants regional data-center investigation areas with finer geographic precision. The accepted
national scope correction searches all CONUS, but its 50 km cells are too coarse for that purpose.
Unrestricted rook-connected clustering also joins selected cells into multi-state corridors; the
largest current component has a 1,000 × 1,400 km bounding box. This is model behavior, independent of
map zoom. Changing map styling or subdividing an existing polygon without recalculation cannot fix it.

## Recommended refinement

1. Retain the national discovery pass, recomputed for the submitted facility and preferences.
2. Identify the actual evaluated representative parent cells from every resulting geographic region;
   deduplicate parent IDs across cooling designs. Refine each selected parent in full on a 1 km lattice.
3. Recompute source aggregation, hard screening, physics, normalized metrics and decisions for every
   child. Use existing fixed scoring references and coefficients. UNKNOWN stays null and hard failures
   remain excluded. Every child has globally stable EPSG:5070 row/column IDs, independent of zoom/window.
4. Form regional search polygons with a declared maximum projected bounding-box span of 20 km in each
   direction. Use deterministic lattice-based partitioning followed by connected components. The span
   is a project search-area assumption, not a scientific or regulatory threshold. Record its rationale.
5. Show refined regional polygons as the final search results. Show the national discovery extent,
   refined parent footprints, actual refined coverage and remaining unrefined coverage separately.

The user approved 1 km regional cells on 2026-10-03. The 20 km extent is a declared project search-area
assumption in the implementation. A 1 km cell is an analytical
geographic unit; it is unrelated to web-map tiles or display zoom. Native 30 m NLCD remains 30 m;
basin-level Aqueduct and eGRID subregions retain their native spatial meaning. Source resolution,
status, coverage and missing reasons remain available beside every metric.

## Declared initial refinement coverage

Current national results contain 690 shortlisted 50 km cells, 61 distinct geographic components and
61 distinct representative parent cells. These counts will be recomputed for each request.

| Option | Current maximum 1 km cells | Coverage implication |
|---|---:|---|
| Recommended: full representative parent cells | 152,500 | Refines about 8.84% of the current shortlisted parent area, without treating a coarse cell center as a verified industrial opportunity. |
| Faster focused preview: 20 × 20 km windows centered on representatives | 24,400 | Refines about 1.41%; can miss suitable locations elsewhere in the representative parent or larger component. |
| Broad expansion: all shortlisted parent cells | 1,725,000 | Covers the complete current national shortlist at 1 km; substantially more computation and stored evidence. |

Neither representative strategy is exhaustive national 1 km analysis. The interface and reports must
state that partial scope. The workflow should support further parent refinement without rebuilding
completed windows. There are no state quotas, manually chosen cities, or favorable-source substitutions.

## Engineering boundaries and resource policy

Geography adds direct bounded grid generation. Building the entire 1 km CONUS bounding lattice first
would create 13,404,864 candidate squares, beyond the existing five-million guard. Enumerate global
row/column ranges only in the selected windows, deduplicate overlaps, and reuse CONUS/state/county
attribution. Full square geometry and CONUS intersection fields remain invariant; window lineage is
stored separately. Prepared containment handles interior cells; exact intersections handle edges.

Model code chooses parents/windows using deterministic evaluated outputs. Geography receives their
geometries and contains no scoring policy. Shared infrastructure orchestrates existing pipeline stages
and records parent run/config/source/output hashes, parent IDs, child definition, selection policy,
evaluated area, omitted coverage and ranking universe. New delivery/configuration revisions preserve
accepted Phase-7 and Phase-8 code-bound evidence and run folders.

Execute fine geography/physics/provenance in bounded parent batches (at most 2,500 cells per current
50 km parent), with a bounded number of workers and measured peak working sets below 4 GiB per process.
Do not concatenate all fine provenance or retain six wide decision results in memory. Persist batch
tables; aggregate compact numeric decision records and stream sensitivity comparisons. Source caches
remain checksum-verified and reusable. A more precise public official boundary input may be needed for
future coastal windows; audit those cases and preserve area-consistency guards instead of silently
clamping fractions. The present 1:500,000 boundary cannot be presented as parcel precision.

Scores remain based on the existing fixed normalization references. Global ranks and Pareto labels
must describe the explicitly evaluated refined universe. Independently calculated batch ranks/frontiers
cannot be relabeled global. If the larger universe needs an exact Pareto accelerator, retain every
comparable row as a possible dominator, preserve the accepted tolerance pair formula, and verify the
complete output against the current implementation. Tolerance dominance is not transitive.

The service recomputes national discovery and fine decisions for facility/preference changes. It may
reuse only verified facility-independent geography. Frontend requests active-window indicator features
to preserve the 10,000-feature bound; zoom changes presentation, never the model resolution or outcomes.
Keep legacy run loading and per-run supported scenarios intact. Region details retain separate cooling
design and external-scenario identities and show exact lineage and refined-universe validation.

## Acceptance evidence

- Failed-first tests for bounded generation equivalence, stable IDs across windows/order, duplicate
  windows, coastal attribution, no coverage relabeling and unchanged accepted artifacts.
- Clustering fixtures proving the declared extent bound, connected membership, deterministic splitting,
  and actual recomputed representative scores; map zoom cannot alter model results.
- Exact compact/global decision and optional Pareto equivalence tests, including ties, missing values,
  tolerance boundaries, cycles, scenarios and row permutations.
- Full backend/API and frontend checks, measured fine-run peak memory, real regional runs across the
  national-selected parents, strict exclusion, repeat determinism and live new-search/browser checks.
- New phase acceptance record, source/config/code hashes, updated handoff, source and coverage limits,
  retained evidence index and cleanup of owned scratch.

These geographic regions deserve further investigation under the stated facility requirements,
datasets, constraints, assumptions, and decision preferences. Finer cells improve regional examination;
parcel buildability, contiguous land, utility capacity, water commitment and fiber remain unverified
until compatible authoritative evidence is supplied.
