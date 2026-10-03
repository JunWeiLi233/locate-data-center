"""USGS Annual NLCD classes (valid classes only), including explicit land proxy.

Suitable-land is a descriptive non-water/non-ice/non-wetland class-area proxy,
not a buildability test. Developed, cultivated and forested land are retained.
"""
import numpy as np
from .spatial import raster_zonal

CLASSES={11:'water',12:'ice_snow',21:'developed_open',22:'developed_low',
         23:'developed_medium',24:'developed_high',31:'barren',41:'deciduous_forest',
         42:'evergreen_forest',43:'mixed_forest',52:'shrub',71:'grassland',
         81:'pasture',82:'cultivated',90:'woody_wetland',95:'emergent_wetland'}


def summarize_land_cover(path,geometry):
    z=raster_zonal(path,geometry,valid_values=set(CLASSES))
    a=z.valid_area_m2
    result={f'land_cover_{name}_frac':z.class_area(code)/a if a else np.nan for code,name in CLASSES.items()}
    result['nlcd_coverage_frac']=z.coverage_frac
    result['nlcd_observed_area_km2']=a/1e6 if a else np.nan
    result['nlcd_water_area_km2']=z.class_area(11)/1e6 if a else np.nan
    result['nlcd_land_area_km2']=(a-z.class_area(11))/1e6 if a else np.nan
    suitable=sum(z.class_area(c) for c in CLASSES if c not in {11,12,90,95})
    result['potentially_suitable_land_frac']=suitable/a if a else np.nan
    result['suitable_land_area_km2']=suitable/1e6 if a else np.nan
    return result
