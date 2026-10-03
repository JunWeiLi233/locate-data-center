"""Aqueduct 4 baseline bws ratio, score and categorical area shares remain distinct."""
import json
import numpy as np
import pandas as pd
from .spatial import region_intersections


def summarize_water_stress(cells,water):
    water=water.loc[water.pfaf_id.notna()].copy()
    pieces=region_intersections(cells,water,'pfaf_id')
    attributes=water.drop_duplicates('pfaf_id').set_index('pfaf_id')
    if not pieces.empty:
        pieces=pieces.join(attributes[['bws_raw','bws_score','bws_cat']],on='pfaf_id')
    groups={key:group for key,group in pieces.groupby('grid_id',sort=False)}
    rows=[]
    for cell in cells.itertuples():
        p=groups.get(cell.grid_id,pieces.iloc[:0])
        row={'grid_id':cell.grid_id}
        for column,field in [('baseline_water_stress_ratio','bws_raw'),('baseline_water_stress_score','bws_score')]:
            v=p[field] if field in p else pd.Series(dtype=float)
            valid=v.notna() & (v!=-9999)
            # 9999 is valid extreme-scarcity flag, excluded from ordinary-ratio mean.
            if field=='bws_raw': valid &= v!=9999
            q=p.loc[valid]
            row[column]=np.average(q[field],weights=q.area_m2) if len(q) else np.nan
            row[column+'_coverage_frac']=min(1.,q.share_frac.sum())
        valid=p.bws_cat.notna() & (p.bws_cat!=-9999) if 'bws_cat' in p else pd.Series(False,index=p.index)
        q=p.loc[valid]
        areas=q.groupby('bws_cat').area_m2.sum().sort_index()
        row['baseline_water_stress_category']=int(areas.idxmax()) if len(areas) else np.nan
        row['baseline_water_stress_category_coverage_frac']=min(1.,q.share_frac.sum())
        row['baseline_water_stress_category_shares_json']=json.dumps({str(int(k)):float(v/cell.geometry.area) for k,v in areas.items()},sort_keys=True)
        valid=p.bws_raw.notna() & (p.bws_raw!=-9999) if 'bws_raw' in p else pd.Series(False,index=p.index)
        row['baseline_water_stress_extreme_scarcity_frac']=float(p.loc[p.bws_raw==9999,'share_frac'].sum()) if valid.any() else np.nan
        row['aqueduct_coverage_frac']=min(1.,p.loc[valid,'share_frac'].sum())
        row['aqueduct_n_subbasins']=len(p)
        row['aqueduct_subbasin_shares_json']=json.dumps({str(k):float(v) for k,v in zip(p.pfaf_id,p.share_frac)},sort_keys=True)
        rows.append(row)
    return pd.DataFrame(rows)
