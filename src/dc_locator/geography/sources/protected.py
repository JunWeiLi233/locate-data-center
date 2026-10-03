"""PAD-US GAP 1/2/3/4 fractions; high ecological protection is GAP 1+2 union.

USGS flattened analysis vectors remove overlapping ownership records. RastDrop
records excluded per the USGS rasterization flag. GAP4 is not GAP1 protection.
"""
import numpy as np
import pandas as pd
from .spatial import overlap_area


def summarize_protected(cells,areas):
    areas=areas.copy()
    if 'RastDrop' in areas:
        areas=areas.loc[pd.to_numeric(areas.RastDrop,errors='coerce')!=1]
    areas['gap']=pd.to_numeric(areas.GAP_Sts,errors='coerce')
    rows=[]
    for cell in cells.itertuples():
        known=overlap_area(cell.geometry,areas.loc[areas.gap.isin([1,2,3,4])])
        row={'grid_id':cell.grid_id,'padus_coverage_frac':known/cell.geometry.area}
        for gap in [1,2,3,4]:
            row[f'padus_gap{gap}_frac']=overlap_area(cell.geometry,areas.loc[areas.gap==gap])/cell.geometry.area if known else np.nan
        row['protected_overlap_frac']=overlap_area(cell.geometry,areas.loc[areas.gap.isin([1,2])])/cell.geometry.area if known else np.nan
        rows.append(row)
    return pd.DataFrame(rows)
