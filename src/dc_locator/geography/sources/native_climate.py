"""Bounded native NEX-GDDP-CMIP6 NetCDF summaries, with explicit CF time."""
from pathlib import Path
from .ingestion import file_digest
import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
import xarray as xr


class TemperatureInterpretationError(ValueError):
    """Native temperature metadata conflicts with an unverified daily mean."""


def _verify_temperature(path, dataset, components, metadata):
    """Check the documented tas derivation without overriding the raw CF tag.

    A 0.0001 K comparison tolerance allows float32 storage/mean rounding. This
    is a numerical identity check, not a temperature quality/engineering limit.
    """
    if not components or set(components) != {'tasmax', 'tasmin'}:
        raise TemperatureInterpretationError('Conflicting tas CF cell_methods requires matching tasmax/tasmin verification')
    component_arrays=[];dependencies={}
    for variable in ['tasmax','tasmin']:
        component=Path(components[variable])
        with xr.open_dataset(component,engine='scipy') as other:
            for attr in ['cmip6_source_id','scenario','variant_label','version','resolution_id','frequency']:
                if other.attrs.get(attr)!=dataset.attrs.get(attr):
                    raise TemperatureInterpretationError('Temperature verification component identity mismatch')
            if variable not in other or other[variable].dims!=dataset.tas.dims or other[variable].attrs.get('units')!='K':
                raise TemperatureInterpretationError('Temperature verification component dimensions/units mismatch')
            if any(not np.array_equal(other[c].values,dataset[c].values) for c in ['time','lat','lon']):
                raise TemperatureInterpretationError('Temperature verification component coordinates mismatch')
            component_arrays.append(other[variable].values.astype(np.float64))
            dependencies[variable]={'sha256':file_digest(component),'bytes':component.stat().st_size,
                'cell_methods':other[variable].attrs.get('cell_methods')}
    actual=dataset.tas.values.astype(np.float64)
    expected=(component_arrays[0]+component_arrays[1])/2
    valid=np.isfinite(actual);expected_valid=np.isfinite(expected)
    if not np.array_equal(valid,expected_valid) or not valid.any():
        raise TemperatureInterpretationError('Temperature verification masks mismatch or no valid samples')
    difference=float(np.max(np.abs(actual[valid]-expected[valid])))
    tolerance=0.0001
    if difference>tolerance:
        raise TemperatureInterpretationError('Native tas does not match documented tasmax/tasmin mean')
    # Also retain the exact native float32 arithmetic comparison when applicable.
    float32_mean=(component_arrays[0].astype(np.float32)+component_arrays[1].astype(np.float32))/np.float32(2)
    metadata['temperature_derivation_verification']={
        'formula':'tas = (tasmax + tasmin) / 2','verified':True,
        'raw_cf_metadata_conflict':metadata.get('cell_methods'),
        'identity_checked':['model','scenario','member','version','resolution','frequency','time','lat','lon','units','masks'],
        'shape':list(actual.shape),'valid_sample_count':int(valid.sum()),
        'maximum_absolute_difference_k':difference,'absolute_tolerance_k':tolerance,
        'tolerance_basis':'numerical float32 storage and arithmetic rounding; not a physical quality limit',
        'float32_arithmetic_maximum_absolute_difference_k':float(np.max(np.abs(actual[valid]-float32_mean[valid]))),
        'dependencies':{'tas':{'sha256':file_digest(path),'bytes':Path(path).stat().st_size},**dependencies},
        'definition_source':'https://www.nccs.nasa.gov/wp-content/uploads/2025/06/NEX-GDDP-CMIP6-v2-Tech_Note.pdf#page=24'}


def read_nex(path,variable,*,model='ACCESS-CM2',scenario='ssp245',year=2030,member='r1i1p1f1',expected_version='2.0',max_values=5000000,temperature_components=None):
    """NetCDF3 local input, daily 0.25-degree native cells; no interpolation.

    Complete Gregorian annual time coverage is required for annual summaries.
    Unsupported calendars reject rather than convert 360-day/noleap arbitrarily.
    Temperature K -> C; precipitation kg m-2 s-1 -> mm/day (1 kg/m² = 1 mm).
    Raster-cell edges are densified before projection into EPSG:5070.
    """
    with xr.open_dataset(path,engine='scipy',decode_times=False) as raw:
        if raw.attrs.get('cmip6_source_id')!=model or raw.attrs.get('scenario')!=scenario or raw.attrs.get('variant_label')!=member:
            raise ValueError('Native NEX model/scenario/member identity mismatch')
        if raw.attrs.get('version')!=expected_version:raise ValueError('Native NEX version mismatch')
        if raw.attrs.get('resolution_id')!='0.25 degree' or raw.attrs.get('frequency')!='day':
            raise ValueError('Native NEX daily 0.25 degree resolution required')
        cal=raw.time.attrs.get('calendar','standard')
        if cal not in {'standard','gregorian','proleptic_gregorian'}: raise ValueError('Unsupported native NEX calendar')
        if variable not in raw or raw[variable].dims!=('time','lat','lon'): raise ValueError('Native NEX variable/dimension mismatch')
        if raw[variable].size>max_values: raise ValueError('NEX local subset exceeds bounded array budget')
        units=raw[variable].attrs.get('units')
        if units!=({'tas':'K','pr':'kg m-2 s-1'}.get(variable)): raise ValueError('Native NEX variable units mismatch')
        d=xr.decode_cf(raw).load()
        metadata={'model':model,'scenario':scenario,'member':member,'year':year,
                  'version':raw.attrs.get('version'),'calendar':cal,'native_units':units,
                  'cell_methods':raw[variable].attrs.get('cell_methods'),'cmip6_license':raw.attrs.get('cmip6_license')}
    if variable=='tas' and 'time: maximum' in (metadata['cell_methods'] or ''):
        _verify_temperature(path,d,temperature_components,metadata)
    dates=pd.DatetimeIndex(d.time.values)
    expected=pd.date_range(f'{year}-01-01',f'{year}-12-31',freq='D')
    days=dates.normalize()
    if days.duplicated().any() or not days.is_monotonic_increasing or not days.isin(expected).all():
        raise ValueError('NEX native dates must be unique ordered within declared year')
    coverage=len(days)/len(expected)
    data=d[variable].values.astype(float)
    # CF _FillValue/missing_value are decoded by xarray; native valid range is
    # honored when provided. No undocumented physical upper cutoff is imposed.
    attrs=d[variable].attrs
    lower=attrs.get('valid_min');upper=attrs.get('valid_max')
    if 'valid_range' in attrs:lower,upper=attrs['valid_range']
    if lower is not None:data=np.where(data>=lower,data,np.nan)
    if upper is not None:data=np.where(data<=upper,data,np.nan)
    data=np.where(np.isfinite(data),data,np.nan)
    data=data-273.15 if variable=='tas' else data*86400
    lat=d.lat.values.astype(float);native_lon=d.lon.values.astype(float)
    def valid_axis(a):
        return a.ndim==1 and len(a)>=2 and np.isfinite(a).all() and len(np.unique(a))==len(a) and (np.all(np.diff(a)>0) or np.all(np.diff(a)<0))
    if not valid_axis(lat) or not valid_axis(native_lon) or not (abs(lat)<=90).all():raise ValueError('NEX coordinate axes must be finite unique strictly monotonic')
    lon=(native_lon+180)%360-180
    if not valid_axis(lon):raise ValueError('NEX longitude wrap discontinuity unsupported; request bounded tiles')
    if not np.allclose(np.abs(np.diff(lat)),.25) or not np.allclose(np.abs(np.diff(lon)),.25):
        raise ValueError('Native NEX coordinate spacing must be 0.25 degree')
    # A missing day/pixel cannot appear as a complete annual value.
    valid=np.isfinite(data).all(axis=0)&(coverage==1)
    means=np.divide(np.nansum(data,axis=0),len(days),out=np.full(valid.shape,np.nan),where=valid) if len(days) else np.full(valid.shape,np.nan)
    x,y=np.meshgrid(lon,lat)
    polygons=shapely.box(x.ravel()-.125,y.ravel()-.125,x.ravel()+.125,y.ravel()+.125)
    polygons=shapely.segmentize(polygons,.008)
    frame=gpd.GeoDataFrame({'pixel_id':np.arange(len(polygons)),'value':means.ravel(),
      'temporal_coverage_frac':np.isfinite(data).sum(axis=0).ravel()/len(expected)},geometry=polygons,crs=4326).to_crs(5070)
    metadata['observed_days']=len(days);metadata['expected_days']=len(expected);metadata['time_coverage_frac']=coverage
    return frame,metadata
