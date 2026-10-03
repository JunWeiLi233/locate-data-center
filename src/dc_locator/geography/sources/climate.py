"""NOAA 1991-2020 gridded normals, already Celsius; no daily extremes implied."""
from .spatial import raster_zonal


def summarize_temperature(paths,geometry):
    result={}
    for metric,path in paths.items():
        z=raster_zonal(path,geometry,valid_range=(-100,80),extra_nodata=(-9999,))
        result[metric]=z.mean
        result[metric+'_coverage_frac']=z.coverage_frac
    return result
