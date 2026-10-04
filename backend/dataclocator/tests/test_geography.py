"""Location checks independent of live endpoints and mutable publisher releases."""

import pandas as pd
import pytest
import geopandas as gpd
from shapely.geometry import box, Point

from dataclocator.geography import validate_fips, haversine_km, normalize_water_value
from dataclocator.pipeline import point_assignments, area_overlaps
from dataclocator.ingest import price_baseline


def test_fips_preserves_leading_zero():
    """FIPS is a location string; loss of leading zero is a schema error."""
    validate_fips(pd.Series(["01001", "36065"]))
    for values in [[1001], ["1001"], ["01001", "01001"], [None], ["１２３４５"]]:
        with pytest.raises(ValueError):
            validate_fips(pd.Series(values))


def test_distance_and_water_missing_codes():
    """Check physical station distance and Aqueduct's two distinct special codes."""
    assert haversine_km(0, 0, [0], [1])[0] == pytest.approx(111.19508, abs=0.001)
    assert normalize_water_value(-9999) is None
    assert normalize_water_value(float("nan")) is None
    assert normalize_water_value(9999) == 9999
    assert normalize_water_value(0) == 0


def test_boundary_point_retains_all_regions():
    """A point on a shared border cannot be assigned silently to the first region."""
    points = gpd.GeoDataFrame({"county_fips": ["01001"]}, geometry=[Point(-100, 40)], crs=4326)
    regions = gpd.GeoDataFrame({"region": ["a", "b"]}, geometry=[box(-101, 39, -100, 41), box(-100, 39, -99, 41)], crs=4326)
    assert point_assignments(points, regions, "region") == {"01001": ["a", "b"]}


def test_area_shares_do_not_hide_missing_coverage():
    """A half-covered county retains a fraction near 0.5, with no renormalization."""
    counties = gpd.GeoDataFrame({"county_fips": ["01001"]}, geometry=[box(-100, 40, -98, 41)], crs=4326)
    regions = gpd.GeoDataFrame({"region": ["a"]}, geometry=[box(-100, 40, -99, 41)], crs=4326)
    result = area_overlaps(counties, regions, ["region"])
    assert result.county_area_fraction.iloc[0] == pytest.approx(0.5, abs=0.01)


def test_price_baseline_requires_full_year():
    """An incomplete calendar year cannot masquerade as the frozen annual baseline."""
    frame = pd.DataFrame({"state_fips": ["01"] * 11, "sector": ["industrial"] * 11,
                          "year": [2025] * 11, "month": list(range(1, 12)),
                          "status": ["Preliminary"] * 11,
                          "electricity_price_usd_per_mwh": [50.] * 11, "sector_sales_mwh": [10.] * 11})
    assert pd.isna(price_baseline(frame).electricity_price_usd_per_mwh.iloc[0])


def test_price_weighting_is_sales_weighted():
    """A high-sales month influences the baseline more than a low-sales month."""
    frame = pd.DataFrame({"state_fips": ["01"] * 12, "sector": ["industrial"] * 12,
                          "year": [2025] * 12, "month": list(range(1, 13)),
                          "status": ["Preliminary"] * 12,
                          "electricity_price_usd_per_mwh": [10.] * 11 + [100.],
                          "sector_sales_mwh": [1.] * 11 + [11.]})
    assert price_baseline(frame).electricity_price_usd_per_mwh.iloc[0] == 55
