"""Rook/queen connected search areas with actual evaluated representatives."""
import hashlib
import math
import numbers
import numpy as np
import geopandas as gpd
import pandas as pd
from shapely import union_all,box,equals
from dc_locator.model.metrics import KEYS,clean,json_text,region_extent_m

REGION_COLUMNS = ['schema_version','region_id','grid_definition_id','profile_id','profile_fingerprint','design_id','scenario_id','member_grid_ids','n_cells','total_area_km2','suitable_land_area_km2','centroid_lat','centroid_lon','mean_mcda_score','representative_grid_id','representative_json','metric_distributions_json','conditional','critical_unknown','interpretation','geometry']
MEMBER_COLUMNS = ['region_id',*KEYS,'mcda_score','is_pareto_optimal','conditional','critical_unknown','suitable_land_area_km2']


def screen_region_land_support(regions, membership, minimum_land_area_km2):
    """Reject inadequate total land within the actual published search geometry.

    Positive single-cell insufficiency can remain unresolved while components
    form, but the entire bounded component's known total cannot be compensated
    by its score. A sufficient sum is only plausibility, never parcel contiguity.
    Missing member support must remain null rather than a partial sum.
    """
    if (isinstance(minimum_land_area_km2, (bool, np.bool_))
            or not isinstance(minimum_land_area_km2, numbers.Real)
            or not math.isfinite(minimum_land_area_km2) or minimum_land_area_km2 <= 0):
        raise ValueError('Minimum regional land area must be positive and finite')
    if regions.region_id.duplicated().any() or not set(membership.region_id) <= set(regions.region_id):
        raise ValueError('Invalid region land-screening membership')
    rows, rejected, unknown = [], set(), set()
    for region in regions.sort_values('region_id').itertuples():
        members = membership.loc[membership.region_id.eq(region.region_id)]
        if (len(members) != region.n_cells or set(members.grid_id) != set(region.member_grid_ids)
                or not members.design_id.eq(region.design_id).all()
                or not members.scenario_id.eq(region.scenario_id).all()):
            raise ValueError('Region land screening needs exact design/scenario membership')
        values = pd.to_numeric(members.suitable_land_area_km2, errors='raise')
        if (values.dropna() < 0).any() or not np.isfinite(values.dropna()).all():
            raise ValueError('Invalid member suitable-land area')
        value = clean(values.sum(min_count=len(members)))
        if (value is None) != pd.isna(region.suitable_land_area_km2):
            raise ValueError('Region land area nullability contradicts complete member support')
        if value is not None and not math.isclose(value, region.suitable_land_area_km2, rel_tol=1e-10, abs_tol=1e-10):
            raise ValueError('Region land area disagrees with member sum')
        outcome = 'UNKNOWN' if value is None else 'PASS' if value >= minimum_land_area_km2 else 'FAIL'
        if outcome == 'FAIL': rejected.add(region.region_id)
        if outcome == 'UNKNOWN': unknown.add(region.region_id)
        rows.append(dict(schema_version='1.0.0', region_id=region.region_id,
            design_id=region.design_id, scenario_id=region.scenario_id,
            member_grid_ids=list(region.member_grid_ids), value_km2=value,
            threshold_km2=float(minimum_land_area_km2), outcome=outcome,
            status='unknown' if value is None else 'calculated', confidence='unknown' if value is None else 'low',
            missing_reason='incomplete_member_land_support' if value is None else None,
            interpretation='Total classified area within this search geometry only; no contiguous or obtainable parcel is inferred.'))
    accepted = regions.loc[~regions.region_id.isin(rejected)].copy().reset_index(drop=True)
    accepted['schema_version'] = '1.3.0'
    for flag in ('conditional', 'critical_unknown'):
        accepted.loc[accepted.region_id.isin(unknown), flag] = True
    members = membership.loc[membership.region_id.isin(accepted.region_id)].copy().reset_index(drop=True)
    audit = pd.DataFrame(rows, columns=['schema_version', 'region_id', 'design_id', 'scenario_id',
        'member_grid_ids', 'value_km2', 'threshold_km2', 'outcome', 'status', 'confidence', 'missing_reason', 'interpretation'])
    return accepted, members, audit


def cluster_regions(geography, ranked, policy, physical_columns, profile_id, profile_hash):
    """Select ceil(fraction*N) in each design/scenario, then connected components.

    Row/column lattice is checked against EPSG:5070 geometry before adjacency.
    Equal scores use grid_id then design_id then scenario_id. Centroids only
    describe unioned search geometries; representatives remain evaluated cells.
    """
    if geography.crs is None or geography.crs.to_epsg() != 5070: raise ValueError('Region adjacency requires EPSG:5070')
    if geography.geometry.isna().any() or geography.geometry.is_empty.any() or not geography.geometry.is_valid.all() or not (geography.geometry.geom_type == 'Polygon').all(): raise ValueError('Grid geometries must be valid nonempty square polygons')
    indices = geography[['row','col']].to_numpy(dtype=float)
    if not np.isfinite(indices).all() or not np.equal(indices,np.floor(indices)).all() or (indices < 0).any(): raise ValueError('Grid row/col must be finite nonnegative integers')
    if geography.grid_id.duplicated().any() or geography[['row','col']].duplicated().any(): raise ValueError('Duplicate grid locations')
    if geography.grid_definition_id.nunique() != 1: raise ValueError('Mixed grid definitions')
    bounds = geography.geometry.bounds
    if not equals(geography.geometry.to_numpy(),box(bounds.minx.to_numpy(),bounds.miny.to_numpy(),bounds.maxx.to_numpy(),bounds.maxy.to_numpy())).all(): raise ValueError('Grid geometry must equal its full bounding square')
    width,height = bounds.maxx-bounds.minx,bounds.maxy-bounds.miny
    if len(geography):
        size = float(width.iloc[0])
        if size <= 0 or not np.allclose(width,size,atol=1e-6,rtol=1e-10) or not np.allclose(height,size,atol=1e-6,rtol=1e-10): raise ValueError('Grid must retain full equal-size squares')
        if not np.allclose(bounds.minx-geography.col*size,(bounds.minx-geography.col*size).iloc[0],atol=1e-5,rtol=0) or not np.allclose(bounds.maxy+geography.row*size,(bounds.maxy+geography.row*size).iloc[0],atol=1e-5,rtol=0): raise ValueError('Row/column indices disagree with square lattice')
        area = geography.geometry.area/1e6
        if 'cell_area_km2' in geography and not np.allclose(geography.cell_area_km2,area,atol=1e-8,rtol=1e-10): raise ValueError('Declared cell area disagrees with geometry')
        study_area = geography.study_area_intersection_km2.to_numpy(dtype=float)
        if not np.isfinite(study_area).all() or (study_area <= 0).any() or (study_area > area.to_numpy()+1e-8).any(): raise ValueError('Invalid study-intersection area')
    if ranked.duplicated(KEYS).any() or not set(ranked.grid_id) <= set(geography.grid_id): raise ValueError('Invalid evaluated alternative membership')
    if policy.get('adjacency') not in {'rook','queen'} or isinstance(policy['top_fraction'],(bool,np.bool_)) or not isinstance(policy['top_fraction'],numbers.Real) or not math.isfinite(policy['top_fraction']) or not 0 < policy['top_fraction'] <= 1 or type(policy['minimum_cells']) is not int or policy['minimum_cells'] < 1 or type(policy.get('require_pareto')) is not bool: raise ValueError('Invalid region policy types/values')
    maximum_extent=region_extent_m(policy)
    partition_edge=None
    if maximum_extent is not None and len(geography):
        partition_edge=math.floor(maximum_extent/size)
        if partition_edge<1:raise ValueError('Maximum region extent cannot be smaller than a grid cell')
    geo = geography.set_index('grid_id')
    offsets = [(0,1),(0,-1),(1,0),(-1,0)]
    if policy['adjacency'] == 'queen': offsets += [(1,1),(1,-1),(-1,1),(-1,-1)]
    records,members = [],[]
    for (design,scenario),group in ranked.loc[ranked.rankable].groupby(['design_id','scenario_id'],sort=True):
        group = group.sort_values(['mcda_score',*KEYS],ascending=[False,True,True,True],kind='stable')
        if policy.get('require_pareto'): group = group.loc[group.is_pareto_optimal.fillna(False)]
        selected = group.head(math.ceil(len(group)*policy['top_fraction'])).set_index('grid_id',drop=False)
        locations = {(int(geo.loc[gid,'row']),int(geo.loc[gid,'col'])):gid for gid in selected.index}
        unseen = set(locations)
        while unseen:
            start = min(unseen)
            partition=(start[0]//partition_edge,start[1]//partition_edge) if partition_edge else None
            unseen.remove(start)
            stack,ids = [start],[]
            while stack:
                location = stack.pop()
                ids.append(locations[location])
                for dr,dc in offsets:
                    neighbor = (location[0]+dr,location[1]+dc)
                    same_partition=partition is None or (neighbor[0]//partition_edge,neighbor[1]//partition_edge)==partition
                    if neighbor in unseen and same_partition: unseen.remove(neighbor); stack.append(neighbor)
            ids.sort()
            if len(ids) < policy['minimum_cells']: continue
            rows = selected.loc[ids].reset_index(drop=True).sort_values(['mcda_score',*KEYS],ascending=[False,True,True,True],kind='stable')
            representative = clean(rows.iloc[0].to_dict())
            identity = json_text([profile_hash,design,scenario,ids])
            region_id = 'region_'+hashlib.sha256(identity.encode()).hexdigest()[:20]
            geometry = union_all(geo.loc[ids].geometry.to_numpy())
            centroid = gpd.GeoSeries([geometry.centroid],crs=5070).to_crs(4326).iloc[0]
            distributions = {}
            for column in ['mcda_score',*physical_columns]:
                if column not in rows: continue
                values = pd.to_numeric(rows[column],errors='coerce').dropna()
                distributions[column] = dict(n_known=len(values),minimum=clean(values.min()),p25=clean(values.quantile(.25)),median=clean(values.median()),p75=clean(values.quantile(.75)),maximum=clean(values.max()))
            record = dict(schema_version='1.2.0' if maximum_extent is not None else '1.1.0',region_id=region_id,grid_definition_id=str(geography.grid_definition_id.iloc[0]),profile_id=profile_id,profile_fingerprint=profile_hash,design_id=design,scenario_id=scenario,member_grid_ids=ids,n_cells=len(ids),total_area_km2=float(geo.loc[ids,'study_area_intersection_km2'].sum()),suitable_land_area_km2=clean(geo.loc[ids,'suitable_land_area_km2'].sum(min_count=len(ids))),centroid_lat=centroid.y,centroid_lon=centroid.x,mean_mcda_score=float(rows.mcda_score.mean()),representative_grid_id=representative['grid_id'],representative_json=json_text(representative),metric_distributions_json=json_text(distributions),conditional=bool(rows.conditional.any()),critical_unknown=bool(rows.critical_unknown.any()),interpretation='These geographic regions deserve further investigation under the stated facility requirements, datasets, constraints, assumptions, and decision preferences. Geometry is a search zone; suitable area is a noncontiguous geographic proxy, not a confirmed parcel.',geometry=geometry)
            records.append(record)
            for row in rows.to_dict('records'):
                members.append(dict(region_id=region_id,**{k:row[k] for k in KEYS},mcda_score=row['mcda_score'],is_pareto_optimal=clean(row.get('is_pareto_optimal')),conditional=row['conditional'],critical_unknown=row['critical_unknown'],suitable_land_area_km2=clean(geo.loc[row['grid_id'],'suitable_land_area_km2'])))
    regions = gpd.GeoDataFrame(records,columns=REGION_COLUMNS,geometry='geometry',crs=5070).sort_values('region_id').reset_index(drop=True)
    membership = pd.DataFrame(members,columns=MEMBER_COLUMNS).sort_values(['region_id',*KEYS]).reset_index(drop=True)
    return regions,membership
