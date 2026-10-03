"""Bounded raster zonal statistics and indexed vector intersections in EPSG:5070.

Pixel edge intersections are area weighted, not centroid assignments. Geographic
pixel edges are densified before projection (curved-edge approximation <=1 km).
Raster reads are bounded by each cell; callers process cells in resumable tiles.
"""
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
from pyproj import CRS, Transformer
import rasterio
from rasterio.features import rasterize
from rasterio.windows import Window, from_bounds
import shapely
from shapely.ops import transform


@dataclass
class ZonalResult:
    values: np.ndarray
    weights_m2: np.ndarray
    total_area_m2: float
    valid_area_m2: float
    footprint_area_m2: float
    native_resolution: str

    @property
    def coverage_frac(self):
        return min(1., self.valid_area_m2 / self.total_area_m2) if self.total_area_m2 else 0.

    def class_area(self, code):
        return float(self.weights_m2[self.values == code].sum())

    @property
    def mean(self):
        return float(np.average(self.values,weights=self.weights_m2)) if self.valid_area_m2 else np.nan


def raster_zonal(path: Path | str, geometry, *, valid_values=None,
                 valid_range=None, extra_nodata=(), max_window_pixels=4_000_000) -> ZonalResult:
    """Exact intersections for projected pixels, densified for other native CRSs.

    ``geometry`` must already be in EPSG:5070. Valid coverage denominator is the
    supplied study-intersection polygon area. Invalid values never become zero.
    """
    with rasterio.open(path) as ds:
        if ds.crs is None:
            raise ValueError('Raster source CRS is required')
        if ds.transform.b or ds.transform.d:
            raise ValueError('Rotated rasters require explicit preprocessing')
        native=CRS.from_user_input(ds.crs)
        equal_area=native.equals(CRS.from_epsg(5070),ignore_axis_order=True)
        to_native=Transformer.from_crs(5070,native,always_xy=True)
        g=geometry if equal_area else transform(to_native.transform,shapely.segmentize(geometry,1000))
        resolution=f'{abs(ds.transform.a):g} x {abs(ds.transform.e):g} '+('degrees' if native.is_geographic else 'm')+f'; {native.to_string()}'
        blank=ZonalResult(np.array([]),np.array([]),geometry.area,0.,0.,resolution)
        if not g.intersects(shapely.box(*ds.bounds)):
            return blank
        bounds=g.intersection(shapely.box(*ds.bounds)).bounds
        win=from_bounds(*bounds,ds.transform)
        c0=max(0,int(np.floor(win.col_off))); r0=max(0,int(np.floor(win.row_off)))
        c1=min(ds.width,int(np.ceil(win.col_off+win.width))); r1=min(ds.height,int(np.ceil(win.row_off+win.height)))
        if (c1-c0)*(r1-r0)>max_window_pixels:
            raise ValueError('Cell window exceeds memory limit; use a finer processing grid or pre-tile raster')
        win=Window(c0,r0,c1-c0,r1-r0); aff=ds.window_transform(win)
        data=ds.read(1,window=win,masked=True)
        touched=rasterize([(g,1)],out_shape=data.shape,transform=aff,all_touched=True,dtype='uint8').astype(bool)
        rows,cols=np.nonzero(touched)
        if len(rows)==0:
            return blank
        weights=np.zeros(data.shape,dtype='float64')
        if equal_area:
            erosion=(abs(aff.a)+abs(aff.e))/2
            interior_geom=g.buffer(-erosion)
            interior=rasterize([(interior_geom,1)],out_shape=data.shape,transform=aff,dtype='uint8').astype(bool) if not interior_geom.is_empty else np.zeros(data.shape,dtype=bool)
            weights[interior]=abs(aff.a*aff.e)
            rows,cols=np.nonzero(touched & ~interior)
        left=aff.c+cols*aff.a; top=aff.f+rows*aff.e
        pixels=shapely.box(left,top+aff.e,left+aff.a,top)
        if not equal_area:
            to_area=Transformer.from_crs(native,5070,always_xy=True)
            segment=.008 if native.is_geographic else 1000
            pixels=shapely.segmentize(pixels,segment)
            pixels=shapely.transform(pixels,to_area.transform,interleaved=False)
        weights[rows,cols]=shapely.area(shapely.intersection(pixels,geometry))
        footprint=float(weights.sum())
        valid=~np.ma.getmaskarray(data) & np.isfinite(data.data) & (weights>0)
        if extra_nodata:
            valid &= ~np.isin(data.data,list(extra_nodata))
        if valid_values is not None:
            valid &= np.isin(data.data,list(valid_values))
        if valid_range is not None:
            valid &= (data.data>=valid_range[0]) & (data.data<=valid_range[1])
        return ZonalResult(data.data[valid].astype(float),weights[valid],geometry.area,
                           float(weights[valid].sum()),footprint,resolution)


def read_vector(path, cells, *, layer=None, columns=None, bounded=True,where=None):
    """BBox-filtered native-CRS read then exact projected intersections later."""
    if isinstance(path,gpd.GeoDataFrame):
        frame=path.copy()
    else:
        info=pyogrio.read_info(path,layer=layer)
        if not info['crs']:
            raise ValueError('Vector source CRS is required')
        # Clip large source polygons to a padded native-CRS study envelope before
        # reprojection/repair. Padding covers curved transformed cell edges.
        query=cells.copy()
        query.geometry=shapely.segmentize(shapely.buffer(cells.geometry.values,100),1000)
        bbox=tuple(query.to_crs(info['crs']).total_bounds) if bounded else None
        frame=pyogrio.read_dataframe(path,layer=layer,columns=columns,bbox=bbox,where=where)
        if bbox is not None and len(frame):
            frame.geometry=shapely.make_valid(shapely.clip_by_rect(frame.geometry.values,*bbox))
    if frame.crs is None:
        raise ValueError('Vector source CRS is required')
    frame=frame.to_crs(5070)
    frame.geometry=shapely.make_valid(frame.geometry.values)
    return frame.loc[~frame.geometry.is_empty & frame.geometry.notna()].reset_index(drop=True)


def region_intersections(cells,regions,region_col):
    """Distinct region shares; duplicate geometries within a region are dissolved.

    Across-region overlaps are preserved and may sum >1 (ambiguity), never silently
    rescaled. Callers define how numeric aggregates interpret such overlapping data.
    """
    if regions.empty:
        return pd.DataFrame(columns=['grid_id',region_col,'area_m2','share_frac'])
    regions=regions.to_crs(5070).dissolve(by=region_col,as_index=False,aggfunc='first')
    pairs=regions.sindex.query(cells.geometry,predicate='intersects')
    if pairs.shape[1]==0:
        return pd.DataFrame(columns=['grid_id',region_col,'area_m2','share_frac'])
    ci,ri=pairs
    area=shapely.area(shapely.intersection(cells.geometry.values[ci],regions.geometry.values[ri]))
    positive=area>1e-8; ci=ci[positive]; ri=ri[positive]; area=area[positive]
    return pd.DataFrame({'grid_id':cells.grid_id.values[ci],region_col:regions[region_col].values[ri],
                         'area_m2':area,'share_frac':area/shapely.area(cells.geometry.values[ci])})


def overlap_area(geometry,regions):
    """Union protects against double counting duplicate/overlapping polygons."""
    if regions is None or regions.empty:
        return 0.
    ix=regions.sindex.query(geometry,predicate='intersects')
    return float(shapely.area(shapely.intersection(geometry,shapely.union_all(regions.geometry.values[ix])))) if len(ix) else 0.
