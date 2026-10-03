# Environment

This file records the exact environment Phase 1 was built and tested against, and how to
recreate it. Treat `requirements.lock.txt` as the authoritative set of exact versions; the
versions below were read from that same installation with `python -c "import X; print(X.__version__)"`
immediately after installing it, so they are reproducible, not hand-typed guesses.

## Recorded versions

| Component | Version | How it was obtained |
|---|---|---|
| OS | Windows 11 Pro 10.0.26200 | `systeminfo` / session environment |
| Shell | Git Bash | project convention (see `AGENTS.md` §7) |
| Python | 3.12.10 (`tags/v3.12.10`, MSC v.1943 64 bit / AMD64) | `.venv/Scripts/python.exe -V` |
| uv | 0.11.3 | `uv --version` |
| geopandas | 1.2.0 | `geopandas.__version__` |
| shapely | 2.1.2 | `shapely.__version__` |
| pyproj | 3.8.0 | `pyproj.__version__` |
| pyogrio | 0.13.0 | `pyogrio.__version__` |
| rasterio | 1.5.2 | `rasterio.__version__` |
| GDAL (as reported by rasterio) | 3.12.2 | `rasterio.__gdal_version__` |
| GDAL (as reported by pyogrio) | 3.12.4 | `pyogrio.__gdal_version__` |
| PROJ | 9.8.1 | `pyproj.proj_version_str` |
| GEOS (as reported by shapely) | 3.13.1 | `shapely.geos_version_string` |
| numpy | 2.5.3 | `numpy.__version__` |
| pandas | 2.3.3 | `pandas.__version__` |
| pyarrow | 20.0.0 | `pyarrow.__version__` |
| scipy | 1.18.1 | `scipy.__version__` |
| pydantic | 2.13.5 | `pydantic.VERSION` |
| pyyaml | 6.0.3 | `yaml.__version__` |
| requests | 2.34.2 | `requests.__version__` |
| xarray | 2026.9.0 | `xarray.__version__` |
| h5netcdf | 1.8.1 | `h5netcdf.__version__` |
| openpyxl | 3.1.5 | `openpyxl.__version__` |
| pytest (dev) | 8.4.2 | `pytest.__version__` |
| hypothesis (dev) | 6.168.3 | `hypothesis.__version__` |

Full transitive closure (including sub-dependencies such as `affine`, `attrs`, `click`,
`pyarrow`, `python-dateutil`, …) is pinned exactly in `requirements.lock.txt`.

### Known discrepancy: GDAL version reported by rasterio vs. pyogrio

`rasterio` and `pyogrio` each ship (vendor) their own GDAL build inside their wheel on Windows,
rather than sharing one system GDAL. They reported **3.12.2** and **3.12.4** respectively in this
environment — a patch-level difference. This is expected for independently-built wheels and is not
a sign of a broken install; both are recent GDAL 3.12.x builds. If a future phase observes a
behavioral difference that could plausibly be GDAL-version-dependent (e.g. a driver quirk), record
the two versions it was tested against rather than assuming a single "the" GDAL version.

## NetCDF backend choice: h5netcdf over netCDF4

The spec allows either `h5netcdf` or `netCDF4` as the xarray NetCDF backend. This project pins
**`h5netcdf`**:

- It installs from a pure-Python + `h5py`/HDF5 wheel on Windows with no separate compiled netCDF-C
  toolchain, which keeps the environment lighter and the install more reproducible across machines.
- The NASA NEX-GDDP-CMIP6 files referenced in `docs/specs/master_prompt.md` (Phase 5) are
  HDF5-based NetCDF4-format files, which `h5netcdf` reads directly.
- Trade-off: `h5netcdf` cannot read legacy NetCDF3 ("classic"/64-bit-offset) files. If a later
  phase needs a source that only ships classic-format NetCDF, add `netCDF4` as an explicit extra
  dependency at that time rather than silently reaching for it — record the reason in this file.

## Recreating the environment

From the project root (always quoted — the path contains spaces and periods):

```bash
cd "/d/locate-data-center"
uv venv --python 3.12 .venv
uv pip install --python .venv/Scripts/python.exe -e ".[dev]"
```

To reproduce the *exact* pinned environment instead of re-resolving compatible ranges:

```bash
uv pip install --python .venv/Scripts/python.exe -r requirements.lock.txt
uv pip install --python .venv/Scripts/python.exe -e . --no-deps
```

### Verifying the install

```bash
.venv/Scripts/python.exe -c "
import geopandas, rasterio, pyogrio, pyproj, shapely
print('geopandas', geopandas.__version__)
print('rasterio', rasterio.__version__, 'GDAL', rasterio.__gdal_version__)
print('pyogrio', pyogrio.__version__, 'GDAL', pyogrio.__gdal_version__)
print('pyproj', pyproj.__version__, 'PROJ', pyproj.proj_version_str)
print('shapely', shapely.__version__, 'GEOS', shapely.geos_version_string)
"
```

### Regenerating `requirements.lock.txt` after a dependency change

```bash
uv pip install --python .venv/Scripts/python.exe -e ".[dev]"
uv pip freeze --python .venv/Scripts/python.exe | grep -v '^-e ' > requirements.lock.txt
```

### Running the test suite

```bash
.venv/Scripts/python.exe -m pytest
```

This runs the full suite, including the `real_data`-marked tests (they need the Census cartographic
boundary files already cached under `data/raw/census_cartographic_boundary/` -- run
`dc-locator build-grid` once, or call `dc_locator.geography.boundary.download_conus_boundary_sources()`
directly, to populate that cache first). To run only the fast, fully offline tests during iterative
development:

```bash
.venv/Scripts/python.exe -m pytest -m "not real_data and not network"
```

`pyproject.toml` registers three markers: `real_data` (needs the cached boundary files), `network` (makes
an actual HTTP request -- a no-op cache hit if the files are already present), and `slow`. None of them
skip by default; AGENTS.md section 10 requires every phase's tests, including `real_data` ones, to
actually execute as part of phase acceptance.

## Memory and compute constraints (see `AGENTS.md` §7)

The development machine has 16 cores and 31 GB RAM shared with other work; keep any single
`dc_locator` process under roughly 4 GB resident, and prefer windowed raster reads, chunked vector
processing, and spatial indexes over loading national datasets wholesale. ~700 GB free disk was
available at the time of writing, which is ample for cached raw downloads in `data/raw/` as long as
each source's download volume is estimated first (see `docs/sources.md`).

## Phase 6 reproducibility boundary

Run the full pre-freeze verification with a project-local temporary directory and no pytest cache, then
write `runs/phase6/software_verification.json` with the exact command, counts and source/config/test hashes.
Create and independently verify the immutable snapshot before any prospective feature build:

```bash
.venv/Scripts/python.exe -m pytest -q --basetemp=.pytest-work/phase6-full-final -p no:cacheprovider
.venv/Scripts/python.exe -m dc_locator.model.validation.freeze --config configs/phase6.yaml --output-dir runs/phase6/freeze/v1
.venv/Scripts/python.exe -m dc_locator.model.validation.freeze --verify runs/phase6/freeze/v1/freeze_manifest.json
```

The prospective builder must name that freeze ID and produce byte-identical primary/repeat artifacts.
The final validator is exposed through `dc_locator.model.validation.run_phase6` and its module CLI. Use
`--preflight` to recompute the accepted 42-cell cases without reading holdout files; omit it only with a
verified freeze and freeze-bound prospective inputs.

## Phase7 executable acceptance boundary

Current delivery is `phase7_delivery_v1`. Use the venv and fresh project-local pytest temporary paths,
with `-p no:cacheprovider`. `runs/phase7/executable_freeze.json` binds the current source/dependency and
configuration hashes; independent full-suite and real/synthetic CLI results belong to the Phase7 record.
The Phase6 command/evidence above is historical and remains unchanged. Current code intentionally
fails comparison to old tested code rather than relabeling its439 tests as current evidence.

Actual run metadata records package versions/platform, native input checksums, current code/config/grid
identity and observed process-lifetime peak working set. A GDAL `organizePolygons` warning for native
multipart polygons was observed during real reads; it is a processing warning, not a failed source
identity or a reason to alter valid geometry. No national feature/model memory claim is made.
