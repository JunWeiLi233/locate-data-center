# U.S. basemap boundary accuracy

The frontend's 6,000 m independently simplified 2023 state outline is unsuitable
for detailed geographic inspection. Replace it without changing model inputs.

Acceptance requirements:

- Use checksum-recorded Census 2025 TIGER/Line state administrative boundaries
  for political borders and Census 2025 1:500,000 cartographic boundaries for the
  separately identified shoreline-clipped land backdrop. Cover 50 states and DC;
  the initial analysis camera remains CONUS.
- Preserve shared state borders, islands, holes, longitude/latitude order and
  valid polygon topology. Draw the dissolved national boundary separately.
- Measure overview simplification against its source in a stated metric CRS.
  Bound its display error before switching to detailed geometry. Detailed
  geometry retains source coordinates without geometric simplification.
- Load detail only for states intersecting the zoomed viewport. Reuse cached
  data, cancel obsolete fetches, and disclose failed detail loads.
- Record source URLs, dates, hashes, datum, processing, limits and QA. Source
  positional accuracy must not be invented; this is a GIS context layer, not
  survey or parcel certification.
- Verify border fidelity, shared-edge topology, source/state coverage and browser
  rendering at national, regional and close zooms on desktop and mobile.
- Keep current model/configuration/tests/evidence bytes unchanged. Keep scratch
  only in `.pytest-work/us-boundary/` and remove it after retaining QA evidence.
