"""EPA historical generation-average emission rates and spatial association proxies."""
import json
import numpy as np
import pandas as pd
from .spatial import region_intersections,overlap_area


def pounds_per_mwh_to_kg_per_mwh(value):
    return value*0.45359237  # exact international avoirdupois pound definition


def read_subregion_workbook(path,*,sheet='SRL23',unit='lb_per_mwh'):
    """Find EPA machine-field header, rejecting arbitrary header or unit assumptions."""
    raw=pd.read_excel(path,sheet_name=sheet,header=None)
    headers=[i for i in range(min(12,len(raw))) if 'SRCO2RTA' in raw.iloc[i].values and 'SUBRGN' in raw.iloc[i].values]
    if len(headers)!=1:
        raise ValueError('Expected one EPA SUBRGN/SRCO2RTA field-name row')
    if unit not in {'lb_per_mwh','kg_per_mwh'}:
        raise ValueError('eGRID workbook units must be explicit')
    frame=pd.read_excel(path,sheet_name=sheet,header=headers[0])
    frame=frame.loc[frame.SUBRGN.notna(),['SUBRGN','SRCO2RTA','SRC2ERTA']].copy()
    for c in ['SRCO2RTA','SRC2ERTA']:
        frame[c]=pd.to_numeric(frame[c],errors='coerce')
    return frame.rename(columns={'SUBRGN':'subregion'})


def summarize_egrid(cells,regions,multiple=None,*,unit='lb_per_mwh'):
    pieces=region_intersections(cells,regions,'subregion')
    attributes=regions.drop_duplicates('subregion').set_index('subregion')
    if len(pieces): pieces=pieces.join(attributes[['SRCO2RTA','SRC2ERTA']],on='subregion')
    groups={key:group for key,group in pieces.groupby('grid_id',sort=False)}
    ambiguous=region_intersections(cells,multiple,'MultipleSu') if multiple is not None and 'MultipleSu' in multiple else pd.DataFrame(columns=['grid_id','MultipleSu','share_frac'])
    ambiguity_groups={key:group for key,group in ambiguous.groupby('grid_id',sort=False)}
    rows=[]
    for cell in cells.itertuples():
        p=groups.get(cell.grid_id,pieces.iloc[:0])
        q=p.loc[p.SRC2ERTA.notna() & (p.SRC2ERTA>=0)] if 'SRC2ERTA' in p else p
        val=float(np.average(q.SRC2ERTA,weights=q.area_m2)) if len(q) else np.nan
        co2=float(np.average(q.SRCO2RTA,weights=q.area_m2)) if len(q) else np.nan
        if unit=='lb_per_mwh': val=pounds_per_mwh_to_kg_per_mwh(val); co2=pounds_per_mwh_to_kg_per_mwh(co2)
        elif unit!='kg_per_mwh': raise ValueError('Explicit eGRID units required')
        shares={str(k):float(v) for k,v in zip(p.subregion,p.share_frac)}
        ambiguity=ambiguity_groups.get(cell.grid_id,ambiguous.iloc[:0])
        rows.append({'grid_id':cell.grid_id,'grid_carbon_intensity_kg_per_mwh':val,
                     'grid_co2_intensity_kg_per_mwh':co2,
                     'egrid_coverage_frac':min(1.,q.share_frac.sum()),
                     'egrid_subregion_primary':max(shares,key=lambda k:(shares[k],-list(sorted(shares)).index(k))) if shares else None,
                     'egrid_n_subregions':len(shares),'egrid_subregion_shares_json':json.dumps(shares,sort_keys=True),
                     'egrid_multiple_subregion_labels_json':json.dumps({str(k):float(v) for k,v in zip(ambiguity.MultipleSu,ambiguity.share_frac)},sort_keys=True) if multiple is not None else None,
                     'egrid_multiple_subregion_overlap_frac':overlap_area(cell.geometry,multiple)/cell.geometry.area if multiple is not None else np.nan})
    return pd.DataFrame(rows)
