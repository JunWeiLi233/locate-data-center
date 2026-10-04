# County economic layer and filters

The supplied specification, amended in chat to permit both cached 2023 and 2025
county boundaries, defines this delivery. The user confirmed that estimates
remain 2024 SAIPE. Poverty/income are independent economic context. Technical
screening, scores, ranks and accepted run files stay unchanged. Fiscal inputs
remain null with explicit reasons.

## Current architecture and integration

Geography production lives in `src/dc_locator/geography/`; deterministic model
decisions live in `src/dc_locator/model/`. The CLI invokes production APIs. The
frontend and local server present saved results. Ranked alternatives are
`grid_id × design_id × scenario_id`; their geographic unit is a fixed-origin
EPSG:5070 grid cell. The active saved run `runs/national_fine_regional_v1/` has
131,945 1 km cells in `us_grid_dataset.parquet`. CandidateRegion polygons are
derived search areas. `region_membership.parquet` links regions to their cells.

The reusable geography cache attaches every positive-area county intersection
to `candidate_id = grid_id`. Region metadata uses these records and stored
membership, without centroid assignment. Areas are calculated in EPSG:5070.
Uncovered coastal/boundary fractions are reported and never renormalized away.

## Source and vintage decisions

- Reuse `data/raw/census_cartographic_boundary/cb_2023_us_county_500k.zip`.
- Reuse `data/raw/census_frontend_boundary/areawater/cb_2025_us_county_500k.zip`.
- Both are generalized Census cartographic boundaries at 1:500,000.
- Boundary2025 is the default; boundary2023 is selectable. Estimate year2024
  is distinct, with a visible mixed-vintage/generalization notice.
- Cache one official national2024SAIPE acquisition through existing download
  manifests and byte guard. HTTP presentation never downloads.
- GEOIDs remain five-character strings. Percentiles use the stated CONUS valid
  county universe, average ranks for ties. Missing values stay null. No blended
  need score or speculative fiscal model is introduced.

## Ownership and implementation

1. Geography agent: SAIPE source adapter, validated config, vectorized crosswalk,
   evidence/coverage contracts, reusable cache and failed-first geography tests.
2. Backend agent: additive API1.6, independent socioeconomic context endpoint,
   national county layers, all-county region relationships and transport tests.
3. Frontend agent: boundary selector, poverty/income/percentile layers, optional
   minimum-poverty/maximum-income display filters, county details and tests.
   All active conditions must match the same overlapping county. Any such
   county retains a region. Unknown values do not satisfy an active filter.
4. Root: reproducible CLI, source/docs integration, real builds for both years,
   single/split-county spot checks, unchanged-native evidence verification,
   regression/build review, live page proof and handoff.

## Verification and delivery

Verify split counties, leading zeros, source years, incomplete coverage, missing
values, percentile ties, cache integrity, year validation, unchanged technical
results and same-county filter semantics. Run model/API regression and frontend
tests/build. Write new geography under `data/processed/socioeconomic/`, and audit
evidence under `runs/county_socioeconomic_layer_v1/`. Report hashes, schema,
counts, join rates, coverage exceptions and examples for each boundary year.
Refresh the idle local API after checks pass; verify the layer/filter in the
user's page and save a screenshot. Remove owned `.pytest-work/county-socioeconomic/`.
