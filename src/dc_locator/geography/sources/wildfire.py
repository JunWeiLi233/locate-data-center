"""Wildfire Risk to Communities rasters; WHP is a separately named supplement."""
from .spatial import raster_zonal


def summarize_wildfire(paths,geometry):
    result={}
    for metric,path in paths.items():
        # BP is annual probability; CFL is native feet; WHP dimensionless index.
        z=raster_zonal(path,geometry,valid_range=(0,float('inf')),extra_nodata=(-9999,))
        if 'burn_probability' in metric and len(z.values) and z.values.max()>1:
            result[metric]=float('nan')
            result[metric+'_coverage_frac']=0.
            result[metric+'_missing_reason']='invalid_source_value'
            continue
        result[metric]=z.mean
        result[metric+'_coverage_frac']=z.coverage_frac
    return result
