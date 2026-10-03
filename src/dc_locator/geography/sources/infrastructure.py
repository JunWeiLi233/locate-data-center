"""Mapped EIA infrastructure minimum polygon distance; never available capacity."""
import numpy as np
import shapely


def distances_to_infrastructure(cells,infrastructure):
    if infrastructure is None or infrastructure.empty:
        return np.full(len(cells),np.nan)
    infra=infrastructure.to_crs(5070)
    tree=shapely.STRtree(infra.geometry.values)
    pairs,distance=tree.query_nearest(cells.geometry.values,return_distance=True,all_matches=False)
    result=np.full(len(cells),np.nan)
    result[pairs[0]]=distance/1000.
    return result
