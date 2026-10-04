"""Strict location identifiers and distance helpers shared by ingestion and tests."""

import math
import pandas as pd


def validate_fips(values: pd.Series, width: int = 5) -> None:
    """Require already-correct strings; never silently repair a lossy numeric FIPS."""
    if not values.map(lambda v: isinstance(v, str) and len(v) == width and v.isascii() and v.isdigit()).all():
        raise ValueError(f"FIPS must be {width}-digit strings with leading zeros intact")
    if values.duplicated().any():
        raise ValueError("duplicate FIPS identifiers")


def haversine_km(lat: float, lon: float, station_lat, station_lon):
    """Great-circle distance to stations; angular degrees are never treated as km."""
    import numpy as np
    a, b = np.radians(station_lat), np.radians(station_lon)
    c, d = math.radians(lat), math.radians(lon)
    h = np.sin((a - c) / 2) ** 2 + np.cos(c) * np.cos(a) * np.sin((b - d) / 2) ** 2
    return 6371.0088 * 2 * np.arcsin(np.sqrt(np.clip(h, 0, 1)))


def normalize_water_value(value):
    """Map WRI no-data codes to null, retaining 9999 as severe-scarcity context."""
    if value is None or pd.isna(value) or float(value) == -9999:
        return None
    return float(value)
