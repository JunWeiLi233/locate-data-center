# Census boundary context

The bundled map covers the 50 states and Washington, DC. The opening camera stays
on CONUS; map coverage does not imply model coverage. All coordinates are actual
Census geometry, never manually drawn borders.

What the lines mean:

- **Dark line**: the U.S. international border (Canada, Mexico, including the
  Great Lakes and border rivers).
- **Grey lines**: borders shared by two states, on land and through rivers, bays,
  sounds and lakes (for example, New York–New Jersey down the Hudson). They are not
  drawn across open ocean.
- **Pale line**: shoreline. Seaward limits of state jurisdiction (TIGER/Line state
  polygons extend about 3 nautical miles offshore) are never drawn as borders.
- **Other countries**: one plain grey fill and dashed borders between them. Their
  terrain, rivers and interior lakes are deliberately not drawn.

Files:

- `states.geojson`: topology-preserving overview of Census 2025 TIGER/Line
  administrative state polygons (labels and per-state detail bounds).
- `borders.geojson`: overview state borders, i.e. edges shared by two overview
  polygons, minus open ocean. `national.geojson`: the overview U.S. outline minus
  seaward limits, split by state.
- `land.geojson` / `shoreline.geojson`: the shoreline-clipped Census GENZ2025
  1:500,000 cartographic backdrop and its shoreline, cut along 1-degree tile edges.
  It is generalized; it is not a detailed coastline.
- `detail/<FIPS>.geojson`: original TIGER/Line state borders (shared edges) and
  international borders, every source vertex retained. Only viewport-intersecting
  states load at zoom 6 and higher.
- `land/<tile>.geojson.gz` and `land/index.json`: detailed land for zoom 9 and
  higher in the contiguous United States, DC and Hawaii. TIGER/Line state polygons
  minus TIGER/Line AREAWATER water bodies, dissolved across state lines per
  1-degree tile, with the resulting shoreline. A loaded tile replaces exactly its
  piece of the generalized backdrop. Alaska keeps the generalized backdrop.
- `foreign.geojson`: land outside the 50 states and DC (Natural Earth 1:10m land minus
  lakes on the U.S. border, minus the TIGER/Line U.S. polygon with a ~50 m margin) and
  borders between two non-U.S. countries (Natural Earth 1:10m land boundaries). It meets
  the U.S. at the TIGER/Line border without gaps; the Great Lakes stay water.
- `boundary-manifest.json`: source URLs, retrieval dates, checksums, datum,
  processing, thresholds and per-file hashes. `boundary-qa.json`: independent checks.

Sources (all public domain; Census files are U.S. Government works):

- https://www2.census.gov/geo/tiger/TIGER2025/STATE/tl_2025_us_state.zip
- https://www2.census.gov/geo/tiger/GENZ2025/shp/cb_2025_us_state_500k.zip
- https://www2.census.gov/geo/tiger/TIGER2025/AREAWATER/ (one file per county)
- https://naciscdn.org/naturalearth/10m/ (Natural Earth, public domain: `ne_10m_land`,
  `ne_10m_lakes`, `ne_10m_admin_0_boundary_lines_land`; context outside the U.S. only)

Detailed land keeps rivers from 1,000 m², bays/estuaries/sounds and ocean from
20,000 m², and lakes, ponds, reservoirs, canals and swamps from 1 km² (equal-area
EPSG:6933). It is simplified by about 5 m (0.00005°) and stored with ~1 m
coordinates, gzip-compressed and decompressed by the browser. County AREAWATER files
that Census refused to serve are recorded as `BLOCKED` in the manifest and are never
circumvented. Such a county's water is taken instead from its all-water 2020 tabulation
blocks (ALAND = 0) in the official TIGER/Line 2025 state geodatabase (Calvert County,
Maryland: 339.0 of 341.6 km² of recorded water); only if that is unavailable is the tile
left on the generalized backdrop.

TIGER/Line boundaries are vintage January 1, 2025. Source NAD83 geographic data
are converted to EPSG:4326 for MapLibre. Overview simplification and displacement
checks use EPSG:3857 metres; Mercator distances overstate ground distances at U.S.
latitudes. The overview's continuous displacement upper bound must stay below
500 projected metres; its zoom-6 switch gives a geometry error below 0.5 screen
pixels. The backdrop's *additional* displacement must stay below 100 projected
metres; that does not undo its original 1:500,000 generalization.

These are professional GIS context boundaries, not survey, legal, cadastral or
parcel feasibility certification. The application's scientific inputs and candidate
polygons are independent of these display assets.

Reproduce from the project root with the existing geospatial environment. The
AREAWATER download is about 1.1 GB, cached under `data/raw/census_frontend_boundary/`;
`land/` tiles are generated and not committed.

```powershell
.venv\Scripts\python.exe frontend/scripts/build_boundaries.py
.venv\Scripts\python.exe frontend/scripts/build_land_detail.py
.venv\Scripts\python.exe frontend/scripts/verify_boundaries.py
```

`build_land_detail.py` must run after `build_boundaries.py` (it rewrites the borders,
national line and backdrop split). To refresh only `foreign.geojson`:

```powershell
.venv\Scripts\python.exe frontend/scripts/build_land_detail.py --foreign-only
```
