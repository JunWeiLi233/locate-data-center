"""Census SAIPE county estimates; dataset estimates, not household measurements.

The public API currently requires a key. The official fixed-width state/county
file is a public alternative. Its documented 90% confidence bounds are retained;
half their rounded width is explicitly calculated, not the API's direct MOE.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

from .ingestion import download_public

SOURCE_ID = 'census_saipe'
SOURCE_URL = 'https://www2.census.gov/programs-surveys/saipe/datasets/{year}/{year}-state-and-county/est{short}all.txt'
LAYOUT_URL = 'https://www2.census.gov/programs-surveys/saipe/technical-documentation/file-layouts/state-county/{year}-estimate-layout.txt'
EXCLUDED_STATES = frozenset({'00','02','15','60','66','69','72','78'})
CONUS_STATES = frozenset({'01','04','05','06','08','09','10','11','12','13','16','17','18','19',
    '20','21','22','23','24','25','26','27','28','29','30','31','32','33','34','35','36','37',
    '38','39','40','41','42','44','45','46','47','48','49','50','51','53','54','55','56'})
FISCAL_FIELDS = ('county_own_source_revenue','county_property_tax_revenue','county_population',
    'estimated_dc_tax_revenue','tax_incentives','public_cost','net_local_fiscal_revenue','fiscal_significance')
FIELDS = {'poverty_count': (7,15, 'people'), 'poverty_rate':(34,38,'percent'),
          'median_household_income':(133,139,'USD/year')}
INTERVALS = {'poverty_count':((16,24),(25,33)), 'poverty_rate':((39,43),(44,48)),
             'median_household_income':((140,146),(147,153))}
MOE_METHOD = '(upper_90 - lower_90) / 2; rounded source interval half-width'
PERCENTILE_METHOD = '100 * (average_rank - 1) / (valid_count - 1); singleton=50'
SOURCE_FIELDS = {'poverty_count':'positions 8-15; SAEPOVALL_PT equivalent',
    'poverty_rate':'positions 35-38; SAEPOVRTALL_PT equivalent',
    'median_household_income':'positions 134-139; SAEMHI_PT equivalent',
    'poverty_count_moe':'positions 17-24 and 26-33; SAEPOVALL_LB90/UB90 equivalents',
    'poverty_rate_moe':'positions 40-43 and 45-48; SAEPOVRTALL_LB90/UB90 equivalents',
    'median_household_income_moe':'positions 141-146 and 148-153; SAEMHI_LB90/UB90 equivalents'}


def source_paths(root, year=2024):
    folder = Path(root)/'data/raw'/SOURCE_ID/str(year)
    return folder/f'est{year % 100:02d}all.txt', folder/f'{year}-estimate-layout.txt'


def acquire_saipe(root, *, year=2024):
    if year != 2024:
        raise ValueError('Only verified SAIPE source year 2024 is supported')
    data, layout = source_paths(root,year)
    for path,url in [(data,SOURCE_URL.format(year=year,short=f'{year % 100:02d}')),
                     (layout,LAYOUT_URL.format(year=year))]:
        download_public(url,path.resolve(),raw_dir=(Path(root)/'data/raw').resolve(),
            source_id=SOURCE_ID,version=f'SAIPE{year}',
            license_note='U.S. Census Bureau public government data; no account or click-through license')
    return data,layout


def _number(text):
    text=text.strip()
    if text.casefold() in {'','.','-','**','***','d','n','na','n/a','null'}:
        return np.nan
    try:
        number=float(text)
    except ValueError as exc:
        raise ValueError(f'Unexpected SAIPE numeric field: {text!r}') from exc
    return number if np.isfinite(number) and number >= 0 else np.nan


def _evidence(frame,metric,*,unit,status='observed',method='official fixed-width source estimate'):
    valid=frame[metric].notna()
    frame[metric+'_status']=np.where(valid,status,'unknown')
    # Qualitative confidence is a project assessment of county-scale model
    # estimates; the independent statistical90% interval remains in raw fields.
    frame[metric+'_confidence']=np.where(valid,'medium','unknown')
    frame[metric+'_missing_reason']=np.where(valid,None,'source_suppressed_or_missing')
    frame[metric+'_unit']=unit
    frame[metric+'_source_id']=SOURCE_ID
    frame[metric+'_source_url']=SOURCE_URL.format(year=2024,short='24')
    frame[metric+'_source_field']=SOURCE_FIELDS[metric]
    frame[metric+'_data_year']=frame['socioeconomic_year']
    frame[metric+'_method']=method


def parse_saipe(text: str, *, year=2024) -> pd.DataFrame:
    """Parse documented1-based field positions and verify every record's tag year."""
    if year != 2024:
        raise ValueError('Only verified SAIPE source year 2024 is supported')
    rows=[]
    for line in text.splitlines():
        if not line.strip():
            continue
        tag=re.search(r'est(\d{2})all\.txt',line[242:],re.IGNORECASE)
        if not tag or int(tag.group(1)) != year % 100:
            raise ValueError('SAIPE record source year mismatch or absent source tag')
        state,county=line[:2].strip(),line[3:6].strip()
        if not re.fullmatch(r'\d{2}',state) or not re.fullmatch(r'\d{1,3}',county):
            raise ValueError('Invalid SAIPE state/county FIPS')
        county=county.zfill(3)
        if state in EXCLUDED_STATES or county=='000':
            continue
        if state not in CONUS_STATES:
            raise ValueError('Invalid SAIPE state FIPS outside recognized CONUS/territory codes')
        row={'county_geoid':state+county,'state_fips':state,'county_fips':county,
             'saipe_county_name':line[193:238].strip(),'socioeconomic_year':year}
        for metric,(start,end,_) in FIELDS.items():
            row[metric]=_number(line[start:end])
            lo,hi=INTERVALS[metric]
            lower,upper=_number(line[slice(*lo)]),_number(line[slice(*hi)])
            if np.isfinite(lower) and np.isfinite(upper) and (lower>upper or
                (np.isfinite(row[metric]) and not lower<=row[metric]<=upper)):
                raise ValueError('Invalid SAIPE 90% confidence interval')
            if metric=='poverty_rate' and any(v>100 for v in (row[metric],lower,upper) if np.isfinite(v)):
                raise ValueError('SAIPE poverty rate outside 0–100 percent')
            row[metric+'_lower_90']=lower
            row[metric+'_upper_90']=upper
            row[metric+'_moe']=(upper-lower)/2 if np.isfinite(row[metric]) and np.isfinite(lower) and np.isfinite(upper) else np.nan
        rows.append(row)
    if not rows:
        raise ValueError('No CONUS county estimates in SAIPE source')
    frame=pd.DataFrame(rows).sort_values('county_geoid').reset_index(drop=True)
    if frame.county_geoid.duplicated().any():
        raise ValueError('SAIPE duplicate county GEOID')
    for metric,(_,_,unit) in FIELDS.items():
        _evidence(frame,metric,unit=unit)
        _evidence(frame,metric+'_moe',unit='percentage_points' if metric=='poverty_rate' else unit,
                  status='calculated',method=MOE_METHOD)
        frame.loc[frame[metric].notna() & frame[metric+'_moe'].isna(),metric+'_moe_missing_reason']='source_interval_missing'
    for metric in FISCAL_FIELDS:
        frame[metric]=np.nan
        frame[metric+'_status']='unknown'
        frame[metric+'_confidence']='unknown'
        frame[metric+'_missing_reason']='future_fiscal_inputs_not_acquired'
        frame[metric+'_unit']='people' if metric=='county_population' else ('fraction' if metric=='fiscal_significance' else 'USD/year')
    return add_percentiles(frame)


def add_percentiles(frame: pd.DataFrame) -> pd.DataFrame:
    """Each metric's universe is all valid CONUS SAIPE counties, before grid joins."""
    frame=frame.copy()
    for metric,name in [('poverty_rate','poverty_percentile'),('median_household_income','income_percentile')]:
        valid=frame[metric].notna()
        n=int(valid.sum())
        frame[name]=np.nan
        if n:
            frame.loc[valid,name]=50. if n==1 else 100*(frame.loc[valid,metric].rank(method='average')-1)/(n-1)
        frame[name+'_status']=np.where(valid,'calculated','unknown')
        frame[name+'_confidence']=np.where(valid,'medium','unknown')
        frame[name+'_missing_reason']=np.where(valid,None,'underlying_source_value_unknown')
        frame[name+'_unit']='percentile'
        frame[name+'_source_id']=SOURCE_ID
        frame[name+'_source_url']=SOURCE_URL.format(year=2024,short='24')
        frame[name+'_method']=PERCENTILE_METHOD
        frame[name+'_source_field']=metric+' across all valid CONUS SAIPE counties'
    frame['low_income_percentile']=100-frame['income_percentile']
    for suffix in ('status','confidence','missing_reason','unit','source_id','source_url'):
        frame['low_income_percentile_'+suffix]=frame['income_percentile_'+suffix]
    frame['low_income_percentile_method']='100 - income_percentile'
    frame['low_income_percentile_source_field']='median_household_income across all valid CONUS SAIPE counties'
    return frame
