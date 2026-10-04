"""Normalize frozen official releases; fail loudly on unexpected source schemas."""

import json
import tarfile
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from .geography import validate_fips, haversine_km, normalize_water_value


def require_columns(frame: pd.DataFrame, columns: list[str]) -> None:
    """Stop on changed source layouts rather than fabricate or guess field names."""
    missing = set(columns) - set(frame.columns)
    if missing:
        raise ValueError(f"missing official source columns: {sorted(missing)}")


def read_counties(root: Path, selection: dict) -> pd.DataFrame:
    """Read Census's actual pipe-delimited 2025 release with string identifiers."""
    with zipfile.ZipFile(root / "data/raw/census/2025/counties.zip") as archive:
        frame = pd.read_csv(archive.open("2025_Gaz_counties_national.txt"), sep="|", dtype={"GEOID": str})
    require_columns(frame, ["GEOID", "USPS", "NAME", "INTPTLAT", "INTPTLONG", "ALAND"])
    validate_fips(frame.GEOID)
    frame = frame.rename(columns={"GEOID": "county_fips", "USPS": "state_abbr", "NAME": "name",
                                  "INTPTLAT": "lat", "INTPTLONG": "lon", "ALAND": "land_area_m2"})
    # Freeze the cohort before outcomes; a missing selected FIPS is an error.
    selected = selection["county_fips"]
    validate_fips(pd.Series(selected))
    if set(selected) - set(frame.county_fips):
        raise ValueError("selected counties are missing from Census vintage")
    frame = frame.set_index("county_fips").loc[sorted(selected)].reset_index()
    if frame.state_abbr.isin(["AK", "HI", "PR"]).any():
        raise ValueError("initial cohort must lie in the contiguous United States")
    frame["state_fips"] = frame.county_fips.str[:2]
    frame["candidate_id"] = frame.county_fips
    return frame[["candidate_id", "county_fips", "state_fips", "state_abbr", "name", "lat", "lon", "land_area_m2"]]


def read_prices(root: Path, counties: pd.DataFrame) -> pd.DataFrame:
    """Preserve monthly EIA industrial/commercial prices and measured data status.

    Multirow headers are verified against the published workbook. Numeric cells
    are cents/kWh; EIA's zero-price cells with zero sales are missing, not free power.
    """
    path = root / "data/raw/eia/2026-09/monthly.xlsx"
    raw = pd.read_excel(path, sheet_name="Monthly-States", header=None)
    if (raw.iloc[0, 8] != "COMMERCIAL" or raw.iloc[0, 12] != "INDUSTRIAL"
            or raw.iloc[2, 11] != "Cents/kWh" or raw.iloc[2, 15] != "Cents/kWh"):
        raise ValueError("EIA multirow header layout has changed")
    frames = []
    states = counties[["state_abbr", "state_fips"]].drop_duplicates()
    for sector, price_col, sales_col in [("industrial", 15, 13), ("commercial", 11, 9)]:
        data = raw.iloc[3:, [0, 1, 2, 3, price_col, sales_col]].copy()
        data.columns = ["year", "month", "state_abbr", "status", "cents_per_kwh", "sector_sales_mwh"]
        data = data[data.state_abbr.isin(states.state_abbr)].copy()
        for column in ["year", "month", "cents_per_kwh", "sector_sales_mwh"]:
            data[column] = pd.to_numeric(data[column], errors="coerce")
        data = data.dropna(subset=["year", "month"])
        data[["year", "month"]] = data[["year", "month"]].astype(int)
        data = data[data.year >= 2020].merge(states, on="state_abbr", validate="many_to_one")
        # Positive reported sales distinguish a genuine tariff proxy from no sales.
        data.loc[(data.sector_sales_mwh <= 0) | (data.cents_per_kwh <= 0), "cents_per_kwh"] = np.nan
        data["electricity_price_usd_per_mwh"] = data.cents_per_kwh * 10
        data["sector"], data["provenance"] = sector, "eia_monthly"
        data["units"], data["uncertainty_source"] = "USD/MWh (nominal observation year)", "not estimated"
        if data.duplicated(["state_fips", "year", "month"]).any():
            raise ValueError("duplicate monthly EIA records")
        frames.append(data)
    return pd.concat(frames, ignore_index=True).sort_values(["state_fips", "sector", "year", "month"])


def price_baseline(prices: pd.DataFrame, year: int = 2025) -> pd.DataFrame:
    """Use a fixed complete calendar year, sales-weighted, for each sector proxy.

    An incomplete year remains null. This is not a forecast or a negotiated tariff.
    """
    records = []
    for (state, sector), group in prices[prices.year == year].groupby(["state_fips", "sector"]):
        valid = group.dropna(subset=["electricity_price_usd_per_mwh", "sector_sales_mwh"])
        complete = len(valid) == 12 and set(valid.month) == set(range(1, 13))
        value = float(np.average(valid.electricity_price_usd_per_mwh, weights=valid.sector_sales_mwh)) if complete else None
        records.append({"state_fips": state, "sector": sector, "baseline_year": year,
                        "valid_months": len(valid), "electricity_price_usd_per_mwh": value,
                        "source_status": ", ".join(sorted(group.status.dropna().unique()))})
    return pd.DataFrame(records)


def read_grid(root: Path) -> pd.DataFrame:
    """Read EPA's documented SRL23 total-output CO2e field, converting lb to kg.

    Excel resource-mix cells are stored as fractions even though displayed as %.
    Their stored fractions are preserved; this is historical average generation.
    """
    frame = pd.read_excel(root / "data/raw/egrid/2023-rev2/egrid.xlsx", sheet_name="SRL23", header=1)
    require_columns(frame, ["YEAR", "SUBRGN", "SRC2ERTA", "SRNGENAN", "SRTRPR", "SRCLPR", "SRGSPR"])
    frame = frame[["YEAR", "SUBRGN", "SRC2ERTA", "SRNGENAN", "SRTRPR", "SRCLPR", "SRGSPR"]].rename(columns={
        "YEAR": "data_year", "SUBRGN": "grid_region", "SRC2ERTA": "grid_co2e_lb_per_mwh",
        "SRNGENAN": "annual_generation_mwh", "SRTRPR": "renewable_generation_fraction",
        "SRCLPR": "coal_generation_fraction", "SRGSPR": "gas_generation_fraction"})
    if frame.grid_region.duplicated().any() or not frame.data_year.eq(2023).all():
        raise ValueError("invalid eGRID release or duplicate region")
    frame["grid_co2e_kg_per_mwh"] = frame.grid_co2e_lb_per_mwh * 0.45359237
    frame["provenance"] = "egrid_data"
    return frame


def read_polygons(root: Path, counties: pd.DataFrame) -> gpd.GeoDataFrame:
    """Select compatible 2025 TIGER county polygons, preserving the original CRS."""
    polygons = gpd.read_file("zip://" + str(root / "data/raw/census/2025/polygons.zip"))
    require_columns(polygons, ["GEOID", "geometry"])
    validate_fips(polygons.GEOID)
    if polygons.crs is None:
        raise ValueError("Census polygons lack a CRS")
    polygons = polygons[polygons.GEOID.isin(counties.county_fips)][["GEOID", "geometry"]].rename(columns={"GEOID": "county_fips"})
    if len(polygons) != len(counties):
        raise ValueError("county polygon coverage mismatch")
    return polygons.to_crs(4326)


def read_water(root: Path, scratch: Path) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Extract WRI's geodatabase into a working cache, never altering raw archives."""
    with zipfile.ZipFile(root / "data/raw/aqueduct/4.0/aqueduct.zip") as archive:
        for member in archive.namelist():
            # Only the official geodatabase is needed; reject archive path traversal.
            if "/GDB/" in member:
                target = (scratch / member).resolve()
                if not target.is_relative_to(scratch.resolve()):
                    raise ValueError("unsafe archive path")
                archive.extract(member, scratch)
    path = scratch / "Aqueduct40_waterrisk_download_Y2023M07D05/GDB/Aq40_Y2023D07M05.gdb"
    baseline_columns = ["string_id", "pfaf_id", "gid_0", "bws_raw", "bws_score", "bws_cat", "bws_label", "bwd_raw", "bwd_score"]
    baseline = gpd.read_file(path, layer="baseline_annual", bbox=(-125, 24, -66, 50), columns=baseline_columns)
    require_columns(baseline, baseline_columns)
    baseline = baseline[baseline.gid_0 == "USA"].copy()
    future_columns = ["pfaf_id"] + [f"{s}{y}_ws_x_{kind}" for s in ["bau", "opt", "pes"] for y in [30, 50] for kind in ["r", "s", "l"]]
    future = gpd.read_file(path, layer="future_annual", bbox=(-125, 24, -66, 50), columns=future_columns)
    require_columns(future, future_columns)
    for frame in [baseline, future]:
        if frame.crs is None:
            raise ValueError("water geometries lack CRS")
        # Repairs are logged by the pipeline; original geometries remain frozen.
        frame.attrs["invalid_geometry_count"] = int((~frame.geometry.is_valid).sum())
        frame.geometry = frame.geometry.make_valid()
    return baseline.to_crs(4326), future.to_crs(4326)


def read_hazards(root: Path) -> pd.DataFrame:
    """Verify both pages against official total; keep hazard quantities distinct."""
    directory = root / "data/raw/fema/1.20"
    frames = []
    for offset in [0, 2000]:
        page = json.loads((directory / f"page-{offset}.json").read_text())
        if "error" in page or not page.get("features"):
            raise ValueError("FEMA query failed")
        frames.append(pd.DataFrame([f["attributes"] for f in page["features"]]))
    frame = pd.concat(frames, ignore_index=True)
    total = json.loads((directory / "count.json").read_text())["count"]
    if len(frame) != total or frame.OBJECTID.duplicated().any():
        raise ValueError("FEMA pagination is incomplete")
    frame = frame.rename(columns={"STCOFIPS": "county_fips"})
    validate_fips(frame.county_fips)
    if not frame.county_fips.str[:2].eq(frame.STATEFIPS).all():
        raise ValueError("FEMA state/county identifiers disagree")
    frame["provenance"] = "fema_counties"
    return frame


def assign_climate(root: Path, counties: pd.DataFrame, max_distance_km: float = 100) -> tuple[pd.DataFrame, list[dict]]:
    """Choose the nearest station with 12 valid temperature/CDD months, within 100km.

    Inspect actual station CSVs before accepting: precipitation-only stations are
    excluded. Elevation is retained; county/parcel elevation is unavailable, so an
    elevation suitability check remains unverified and this is context only.
    """
    inventory = pd.read_fwf(root / "data/raw/noaa/1991-2020/inventory.txt",
                            colspecs=[(0, 11), (12, 20), (21, 30), (31, 37)],
                            names=["station_id", "lat", "lon", "elevation_m"], dtype={"station_id": str})
    inventory = inventory.dropna(subset=["lat", "lon"])
    inventory = inventory[inventory.station_id.str.startswith("US")].reset_index(drop=True)
    selected, metadata, cache = [], [], {}
    with tarfile.open(root / "data/raw/noaa/1991-2020/monthly.tar.gz") as archive:
        members = {Path(m.name).stem: m for m in archive.getmembers() if m.isfile() and m.name.endswith(".csv")}
        for county in counties.itertuples():
            distances = haversine_km(county.lat, county.lon, inventory.lat.to_numpy(), inventory.lon.to_numpy())
            chosen = None
            for index in np.argsort(distances):
                distance = float(distances[index])
                if distance > max_distance_km:
                    break
                station = inventory.iloc[index]
                station_id = station.station_id
                if station_id not in members:
                    continue
                if station_id not in cache:
                    data = pd.read_csv(archive.extractfile(members[station_id]))
                    needed = ["STATION", "LATITUDE", "LONGITUDE", "ELEVATION", "month", "MLY-TAVG-NORMAL", "MLY-CLDD-NORMAL"]
                    if not set(needed).issubset(data.columns):
                        cache[station_id] = None
                    else:
                        data = data[needed + [c for c in data if c.startswith(("comp_flag_MLY-TAVG", "years_MLY-TAVG", "meas_flag_MLY-TAVG", "comp_flag_MLY-CLDD", "years_MLY-CLDD", "meas_flag_MLY-CLDD"))]].copy()
                        values = data[["MLY-TAVG-NORMAL", "MLY-CLDD-NORMAL"]].apply(pd.to_numeric, errors="coerce")
                        good = len(data) == 12 and set(data.month) == set(range(1, 13)) and values.notna().all().all() and (values != -9999).all().all()
                        cache[station_id] = data if good else None
                data = cache[station_id]
                if data is not None:
                    # Frozen metadata and file coordinates must agree before joining.
                    if abs(float(data.LATITUDE.iloc[0]) - station.lat) > 0.01 or abs(float(data.LONGITUDE.iloc[0]) - station.lon) > 0.01:
                        continue
                    chosen = station_id
                    copy = data.copy()
                    copy["county_fips"] = county.county_fips
                    copy["temperature_c"] = (copy["MLY-TAVG-NORMAL"] - 32) * 5 / 9
                    copy["cooling_degree_days_f_base65"] = copy["MLY-CLDD-NORMAL"]
                    copy["provenance"] = "noaa_monthly"
                    selected.append(copy)
                    metadata.append({"county_fips": county.county_fips, "climate_station_id": station_id,
                                     "climate_station_distance_km": distance,
                                     "climate_station_elevation_m": float(data.ELEVATION.iloc[0]),
                                     "climate_elevation_check": "unverified: no county/parcel elevation"})
                    break
            if chosen is None:
                metadata.append({"county_fips": county.county_fips, "climate_station_id": None,
                                 "climate_station_distance_km": None, "climate_station_elevation_m": None,
                                 "climate_elevation_check": "no suitable station within threshold"})
    return pd.concat(selected, ignore_index=True) if selected else pd.DataFrame(), metadata
