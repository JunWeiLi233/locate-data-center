# National discovery revision

The reported Texas concentration comes from two measured coverage restrictions: every frontend
search copied the 42-cell `dev_tiny` template, and the required NLCD land metric covered only the
development area. The two displayed regions were cooling alternatives at the same geometry.
No Texas-specific score or marker-coordinate bug was found.

The new revision extends existing delivery schema 2.1.0 rather than rebuilding accepted phases.
It uses a 50 km fixed-origin CONUS grid (3,384 cells, all 49 states/DC jurisdictions), retaining
the original scoring profile, numeric weights, hard requirements and annual physical scenarios.
The resolution and 5,000-cell execution cap are documented project resource assumptions.

Official Annual NLCD 2024 CU C1V1 native mosaic: 1,442,142,769-byte ZIP from
https://www.mrlc.gov/downloads/sciweb1/shared/mrlc/data-bundles/Annual_NLCD_LndCov_2024_CU_C1V1.zip.
Acquisition uses the existing bounded public downloader and project authorization. The source is
extracted once and reprojected from native WGS84 Albers to EPSG:5070 at 30 m using nearest neighbor,
one GDAL thread and bounded memory. Source, extracted and derived identities are recorded.

National vector preparation uses spatial envelopes capped at 250 km and 625 cells. Full nearest
infrastructure inventories and eGRID workbook attributes load once; verified geographic tile
caches are shared across national facilities/screening modes. Optional cached hazards/climate and
expanded future contexts are explicitly not computed in this initial baseline: their metrics
remain null/UNKNOWN, acquired and analyzed reporting stays separate, and strict screening remains.

Frontend searches use the national template; scope and cell counts come from each run. All
candidate centroids receive badges, including representatives with alternative ranks above 20.
Per-run scenario availability prevents the national baseline from borrowing development future
evidence. Existing development outputs remain loadable and preserved.

Verification: failed-first regressions for national defaults, false national scope, native categorical
preparation/cache checksums, bounded vector preparation/equal scientific outputs, geographic cache
reuse, dynamic frontend scope/scenarios and region badges. Then full pytest, UI tests/build, a real
national run, strict rerun, substantive determinism, artifact audit and real API/browser checks.

These geographic regions deserve further investigation under the stated facility requirements,
datasets, constraints, assumptions, and decision preferences. They are not proven buildable parcels.
