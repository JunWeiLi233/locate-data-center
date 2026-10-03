"""FEMA effective NFHL: mapped T/F coverage is independent from SFHA union area.

U, D, OPEN WATER and unmapped areas are undetermined. A zero only exists in a
cell with known map coverage. Hazard fractions use full study-intersection area;
classification coverage and surveyed footprint are separate. FIRM outlines never imply hazard
classification coverage (a panel can contain unmapped/undetermined areas).
"""
import numpy as np
import pandas as pd
from .spatial import overlap_area


def summarize_flood(cells,hazards,surveyed=None,*,hazard_query=None,surveyed_query=None):
    known=hazards.loc[hazards.SFHA_TF.isin(['T','F'])].copy() if hazards is not None else None
    if known is not None and 'FLD_ZONE' in known:
        known=known.loc[~known.FLD_ZONE.isin(['D','OPEN WATER'])]
    high=known.loc[known.SFHA_TF=='T'] if known is not None else None
    rows=[]
    for cell in cells.itertuples():
        area=overlap_area(cell.geometry,known)
        hazard=overlap_area(cell.geometry,high)
        hq=cell.geometry.intersection(hazard_query).area/cell.geometry.area if hazard_query is not None else (1. if hazards is not None else 0.)
        sq=cell.geometry.intersection(surveyed_query).area/cell.geometry.area if surveyed_query is not None else (1. if surveyed is not None else 0.)
        queried=hq>=1-1e-6
        rows.append({'grid_id':cell.grid_id,'flood_coverage_frac':area/cell.geometry.area if queried else np.nan,
                     'flood_hazard_query_coverage_frac':min(1.,hq),
                     'flood_surveyed_query_coverage_frac':min(1.,sq),
                     'flood_surveyed_coverage_frac':overlap_area(cell.geometry,surveyed)/cell.geometry.area if surveyed is not None and sq>=1-1e-6 else np.nan,
                     'flood_overlap_frac':hazard/cell.geometry.area if area and queried else np.nan,
                     'flood_sfha_area_km2':hazard/1e6 if area and queried else np.nan,
                     'flood_surveyed_coverage_frac_missing_reason':'outside_source_coverage' if sq<1-1e-6 else None,
                     **{metric+'_missing_reason':'outside_source_coverage' if not queried else None for metric in ['flood_overlap_frac','flood_coverage_frac','flood_sfha_area_km2']}})
    return pd.DataFrame(rows)
