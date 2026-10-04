"""Web-Mercator-aligned PNG of the national 1 km decision value, for the map's 'model evaluates every cell' step.

Rows are spaced uniformly in Web Mercator y, so a MapLibre image source anchored at the four corner
coordinates aligns. Each pixel averages a 2×2 supersample of the 1 km cells under it (nearest cell per
sample). Cells without a score stay transparent and are never coloured as zero. The ramp is a single-ink
sequential ramp (dark slate, opacity rising with score between declared percentiles), so the coloured
point layers stay legible above it. Ink starts at the national median score, so below-median cells stay
almost clear and the upper half is emphasized. It is a presentation image. Scores come from the persisted arrays,
not from browser computation.
"""
from __future__ import annotations

import struct
import zlib

import numpy as np
from pyproj import Transformer

BOUNDS = (-125.0, 24.0, -66.5, 49.6)  # lon_min, lat_min, lon_max, lat_max (CONUS presentation extent)
INK = (34, 52, 60)


def _mercator_y(lat):
    return np.log(np.tan(np.pi / 4 + np.radians(lat) / 2))


def _inverse_mercator(y):
    return np.degrees(2 * np.arctan(np.exp(y)) - np.pi / 2)


def png_bytes(rgba: np.ndarray) -> bytes:
    """Minimal RGBA8 PNG encoder (no external imaging dependency)."""
    height, width, _ = rgba.shape
    raw = b"".join(b"\x00" + rgba[row].astype(np.uint8).tobytes() for row in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def render(national, grid, width_px: int) -> tuple[bytes, dict]:
    lon_min, lat_min, lon_max, lat_max = BOUNDS
    y_min, y_max = _mercator_y(lat_min), _mercator_y(lat_max)
    height_px = int(round(width_px * (y_max - y_min) / np.radians(lon_max - lon_min)))
    rows, cols = int(national.row.max()) + 1, int(national.col.max()) + 1
    dense = np.full((rows, cols), np.nan, dtype=np.float32)
    dense[national.row, national.col] = national.score.astype(np.float32)
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:5070", always_xy=True)
    total = np.zeros((height_px, width_px))
    count = np.zeros((height_px, width_px))
    for dy in (0.25, 0.75):
        for dx in (0.25, 0.75):
            lon = lon_min + (np.arange(width_px) + dx) / width_px * (lon_max - lon_min)
            y = y_max - (np.arange(height_px) + dy) / height_px * (y_max - y_min)
            lon_grid, lat_grid = np.meshgrid(lon, _inverse_mercator(y))
            x5070, y5070 = transformer.transform(lon_grid.ravel(), lat_grid.ravel())
            row = np.floor((grid.origin_y_m - np.asarray(y5070)) / grid.cell_size_m).astype(np.int64)
            col = np.floor((np.asarray(x5070) - grid.origin_x_m) / grid.cell_size_m).astype(np.int64)
            inside = (row >= 0) & (row < rows) & (col >= 0) & (col < cols)
            values = np.full(row.shape, np.nan, dtype=np.float32)
            values[inside] = dense[row[inside], col[inside]]
            values = values.reshape(height_px, width_px)
            finite = np.isfinite(values)
            total[finite] += values[finite]
            count[finite] += 1
    mean = np.where(count > 0, total / np.maximum(count, 1), np.nan)
    valued = national.score[np.isfinite(national.score)]
    low, high = float(np.percentile(valued, 50)), float(valued.max())
    scaled = np.clip((mean - low) / (high - low), 0, 1)
    alpha = np.where(np.isfinite(mean), 0.04 + 0.78 * scaled ** 1.4, 0.0)
    rgba = np.zeros((height_px, width_px, 4))
    rgba[..., 0], rgba[..., 1], rgba[..., 2] = INK
    rgba[..., 3] = np.round(alpha * 255)
    legend = {"bounds": list(BOUNDS), "coordinates": [[lon_min, lat_max], [lon_max, lat_max], [lon_max, lat_min], [lon_min, lat_min]],
              "width_px": width_px, "height_px": height_px, "ink_rgb": list(INK),
              "score_low": low, "score_high": high, "opacity_low": 0.04, "opacity_high": 0.82, "gamma": 1.4,
              "low_basis": "national median of valued cells (lower values share the floor opacity)",
              "high_basis": "maximum valued score", "unvalued": "transparent (no score is never shown as zero)",
              "sampling": "2x2 supersampled nearest 1 km cell per Web Mercator pixel; presentation only"}
    return png_bytes(rgba), legend
