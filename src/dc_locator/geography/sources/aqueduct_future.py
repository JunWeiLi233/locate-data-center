"""Native Aqueduct 4.0 future basin overlays, with no annual interpolation."""
from pathlib import Path
import hashlib
import json

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from dc_locator.geography.boundary import load_conus_boundary
from dc_locator.schemas import FeatureMetadata
from dc_locator.validation import validate_feature_provenance
from dc_locator.source_periods import AQUEDUCT_WINDOWS, AQUEDUCT_PATHWAYS, AQUEDUCT_GCMS
from .spatial import read_vector, region_intersections

WINDOWS, PATHWAYS, GCMS = AQUEDUCT_WINDOWS, AQUEDUCT_PATHWAYS, AQUEDUCT_GCMS
FUTURE_SOURCE_ID = 'wri_aqueduct40_future'
SOURCE_URL = 'https://www.wri.org/aqueduct/help-center/understanding-future-projections'
SUFFIXES = {'ratio': ('ratio', 'r'), 'score': ('score_0_to_5', 's'),
            'category': ('category_-1_to_4', 'c'), 'label': (None, 'l'),
            'extreme_scarcity_frac': ('frac', 'r'), 'category_shares_json': (None, 'c')}


def future_period(pathway, milestone_year):
    if pathway not in PATHWAYS or type(milestone_year) is not int:
        raise ValueError('Unknown Aqueduct pathway or invalid milestone year')
    window = WINDOWS.get(milestone_year)
    return dict(pathway=pathway, ssp_rcp=PATHWAYS[pathway], milestone_year=milestone_year,
                window_start_year=window[0] if window else None,
                window_end_year=window[1] if window else None,
                supported=window is not None, model='HYPFLOWSCI6; five-GCM median', gcms=GCMS)


def future_metric(pathway, year, suffix):
    return f'aqueduct_{pathway}_{year}_water_stress_{suffix}'


def aqueduct_future_default_input(project_root=None):
    root = Path(project_root or Path(__file__).resolve().parents[4])
    archive = root/'data/raw/wri_aqueduct40/aqueduct-4-0-water-risk-data.zip'
    log = root/'data/raw/wri_aqueduct40/download_log.json'
    cfg = dict(paths={}, layer='future_annual',
               zip_member='Aqueduct40_waterrisk_download_Y2023M07D05/GDB/Aq40_Y2023D07M05.gdb',
               data_mode='real', source_version='Aqueduct4.0 Y2023M07D05',
               retrieved_at=None, expected_sha256=None)
    if archive.is_file(): cfg['paths']['future'] = str(archive)
    if log.is_file():
        info = json.loads(log.read_text(encoding='utf-8'))['files'][0]
        cfg.update(retrieved_at=info['retrieved_at_utc'], expected_sha256=info['sha256'])
    return cfg


def _validate_polygons(frame, *, cells=False):
    if not isinstance(frame, gpd.GeoDataFrame) or frame.crs is None:
        raise ValueError('GeoDataFrame with declared CRS required for overlay')
    if cells and (frame.empty or frame.crs.to_epsg() != 5070):
        raise ValueError('Nonempty EPSG:5070 analysis cells required')
    if cells and ('grid_id' not in frame or frame.grid_id.isna().any() or frame.grid_id.duplicated().any()
                  or not frame.grid_id.map(lambda x: isinstance(x, str) and bool(x.strip())).all()):
        raise ValueError('Unique nonempty string grid IDs required')
    geometry = frame.geometry.values
    if frame.geometry.isna().any() or shapely.is_empty(geometry).any() or not shapely.is_valid(geometry).all():
        raise ValueError('Empty/missing/invalid geometry cannot be overlaid')
    if not frame.geom_type.isin(['Polygon', 'MultiPolygon']).all():
        raise ValueError('Polygonal overlay geometry required')
    if not np.isfinite(shapely.get_coordinates(geometry)).all() or not np.isfinite(shapely.area(geometry)).all() or (shapely.area(geometry) <= 0).any():
        raise ValueError('Positive-area finite geometry required')


def summarize_future_water_stress(cells, water, *, pathway, milestone_year):
    _validate_polygons(cells, cells=True)
    if water is not None: _validate_polygons(water)
    return _summarize(cells, water, pathway=pathway, milestone_year=milestone_year)


def _summarize(cells, water, *, pathway, milestone_year, intersections=None):
    info = future_period(pathway, milestone_year)
    blank = {future_metric(pathway, milestone_year, s): None for s in SUFFIXES}
    blank.update({k+'_coverage_frac': 0.0 for k in list(blank)})
    if not info['supported'] or water is None:
        return pd.DataFrame([dict(grid_id=k, **blank) for k in cells.grid_id])
    fields = {s: f'{pathway}{str(milestone_year)[-2:]}_ws_x_{t}' for s, (_, t) in SUFFIXES.items()}
    required = {'pfaf_id', *fields.values()}
    if not required <= set(water.columns):
        raise ValueError('Native future_annual fields missing: '+str(sorted(required-set(water.columns))))
    water = water.loc[water.pfaf_id.notna()].copy()
    for field, low, high, integral in [(fields['ratio'], 0, None, False),
            (fields['score'], 0, 5, False), (fields['category'], -1, 4, True)]:
        numeric = pd.to_numeric(water[field], errors='raise')
        valid = numeric.notna()
        if ((~np.isfinite(numeric[valid])) | (numeric[valid] < low)).any() or (high is not None and (numeric[valid] > high).any()) or (integral and (numeric[valid] != np.floor(numeric[valid])).any()):
            raise ValueError('Invalid native future value in '+field+'; NULL is missing, not baseline sentinel handling')
        water[field] = numeric
    for field in sorted(set(fields.values())):
        if (water.groupby('pfaf_id')[field].nunique(dropna=False) > 1).any():
            raise ValueError('Conflicting native attributes within pfaf_id')
    pieces = region_intersections(cells, water, 'pfaf_id') if intersections is None else intersections.copy()
    attributes = water.drop_duplicates('pfaf_id').set_index('pfaf_id')
    if not pieces.empty: pieces = pieces.join(attributes[sorted(set(fields.values()))], on='pfaf_id')
    groups = {k: p for k, p in pieces.groupby('grid_id', sort=False)}
    rows = []
    for cell in cells.itertuples():
        p = groups.get(cell.grid_id, pieces.iloc[:0])
        if p.share_frac.sum() > 1+1e-6:
            raise ValueError('Aqueduct distinct basin overlap exceeds study-intersection area')
        row = dict(grid_id=cell.grid_id, **blank)
        if not len(p): rows.append(row); continue
        for suffix in ('ratio', 'score'):
            field = fields[suffix]
            valid = p[field].notna()
            if suffix == 'ratio': valid &= p[field] != 9999
            q = p.loc[valid]
            name = future_metric(pathway, milestone_year, suffix)
            row[name] = float(np.average(q[field], weights=q.area_m2)) if len(q) else None
            row[name+'_coverage_frac'] = min(1.0, float(q.share_frac.sum()))
        q = p.loc[p[fields['category']].notna()]
        areas = q.groupby(fields['category']).area_m2.sum().sort_index()
        category = int(areas.idxmax()) if len(areas) else None
        category_coverage = min(1.0, float(q.share_frac.sum()))
        for suffix in ('category', 'category_shares_json'):
            name = future_metric(pathway, milestone_year, suffix)
            row[name] = category if suffix == 'category' else (json.dumps({str(int(k)): float(v/cell.geometry.area) for k, v in areas.items()}, sort_keys=True) if len(areas) else None)
            row[name+'_coverage_frac'] = category_coverage
        name = future_metric(pathway, milestone_year, 'label')
        labels = q.loc[(q[fields['category']] == category) & q[fields['label']].notna()]
        row[name] = sorted(labels[fields['label']].astype(str))[0] if len(labels) else None
        row[name+'_coverage_frac'] = min(1.0, float(p.loc[p[fields['label']].notna() & p[fields['category']].notna(), 'share_frac'].sum()))
        name = future_metric(pathway, milestone_year, 'extreme_scarcity_frac')
        q = p.loc[p[fields['ratio']].notna()]
        row[name] = float(q.loc[q[fields['ratio']] == 9999, 'share_frac'].sum()) if len(q) else None
        row[name+'_coverage_frac'] = min(1.0, float(q.share_frac.sum()))
        rows.append(row)
    return pd.DataFrame(rows)


def build_aqueduct_future_features(geography, baseline_provenance, source_input=None, *,
        pathways=('bau', 'opt', 'pes'), milestone_years=(2030, 2050, 2080), study_geometry=None,
        provenance_grid_definition_id=None):
    """Append native future features/provenance; original columns/rows are untouched.

    No acquisition occurs here. Read one bounded future_annual geometry set then
    reuse basin intersections. Every source period remains a trend window.
    """
    _validate_polygons(geography, cells=True)
    if not {'grid_definition_id', 'data_mode', 'study_area_intersection_km2'} <= set(geography):
        raise ValueError('Geographic grid identity and study-intersection area required')
    if geography.grid_definition_id.isna().any() or geography.data_mode.isna().any() or geography.grid_definition_id.nunique() != 1 or geography.data_mode.nunique() != 1:
        raise ValueError('Mixed grid or data-mode identity')
    identity, mode = geography.grid_definition_id.iloc[0], geography.data_mode.iloc[0]
    validate_feature_provenance(baseline_provenance, grid_ids=geography.grid_id,
        data_mode=mode, grid_definition_id=identity,
        provenance_grid_definition_id=provenance_grid_definition_id)
    if not pathways or not milestone_years or len(set(pathways)) != len(pathways) or len(set(milestone_years)) != len(milestone_years):
        raise ValueError('Unique nonempty Aqueduct pathway/year sets required')
    periods = [future_period(p, y) for p in pathways for y in milestone_years]
    cfg = aqueduct_future_default_input() if source_input is None else source_input
    if cfg.get('data_mode', 'real') != geography.data_mode.iloc[0]: raise ValueError('Source data mode differs from geography')
    study_geometry = load_conus_boundary().boundary if study_geometry is None else study_geometry
    cells = geography.copy()
    cells.geometry = shapely.intersection(geography.geometry.values, study_geometry)
    _validate_polygons(cells, cells=True)
    if not np.allclose(cells.geometry.area, geography.study_area_intersection_km2*1e6, rtol=1e-7, atol=.05):
        raise ValueError('Aqueduct analysis geometry differs from recorded study-intersection area')
    native = cfg.get('paths', {}).get('future')
    source_hash = None
    water = None
    if native is not None:
        if isinstance(native, gpd.GeoDataFrame):
            source_hash = hashlib.sha256(pd.util.hash_pandas_object(native.drop(columns='geometry'), index=False).values.tobytes()+b''.join(native.geometry.to_wkb())).hexdigest()
            water = read_vector(native, cells)
        else:
            path = Path(native)
            h = hashlib.sha256()
            with path.open('rb') as stream:
                for block in iter(lambda: stream.read(1024*1024), b''): h.update(block)
            source_hash = h.hexdigest()
            if cfg.get('expected_sha256') and source_hash != cfg['expected_sha256']: raise ValueError('Cached Aqueduct source checksum differs from manifest')
            source_path = '/vsizip/'+path.resolve().as_posix()+'/'+cfg['zip_member'] if path.suffix == '.zip' else str(path)
            water = read_vector(source_path, cells, layer=cfg.get('layer', 'future_annual'))
    if water is not None: _validate_polygons(water)
    intersections = region_intersections(cells, water.loc[water.pfaf_id.notna()], 'pfaf_id') if water is not None else None
    result = geography.copy()
    records, columns = [], {}
    for info in periods:
        p, y = info['pathway'], info['milestone_year']
        summary = _summarize(cells, water, pathway=p, milestone_year=y, intersections=intersections).set_index('grid_id')
        for suffix, (unit, native_suffix) in SUFFIXES.items():
            metric = future_metric(p, y, suffix)
            if metric in result or (not baseline_provenance.empty and baseline_provenance.metric.eq(metric).any()):
                raise ValueError('Future metric already exists: '+metric)
            values, statuses, confidences, coverages = [], [], [], []
            for grid_id in result.grid_id:
                value = summary.loc[grid_id, metric]
                value = None if pd.isna(value) else value
                coverage = float(summary.loc[grid_id, metric+'_coverage_frac'])
                present = value is not None
                status, confidence = ('scenario', 'low') if present else ('unknown', 'unknown')
                field = f'{p}{str(y)[-2:]}_ws_x_{native_suffix}' if info['supported'] else None
                period = f'{y} milestone; {info["window_start_year"]}-{info["window_end_year"]} trend window; {info["ssp_rcp"]}' if info['supported'] else f'unsupported requested{y}; {info["ssp_rcp"]}; no native field/window or interpolation'
                method = json.dumps(dict(**info, gcm_aggregation='five-GCM median', annual_interpolation=False,
                    spatial_method='study-intersection EPSG:5070 area-weighted overlay; distinct pfaf_id',
                    raw_9999_policy='positive9999 retained only as extreme-scarcity fraction, excluded from ordinary ratio mean',
                    category_policy='plurality area; lowest code tie; native label retained'), sort_keys=True)
                record = FeatureMetadata(grid_id=grid_id, metric=metric, value=None if isinstance(value, str) else value,
                    value_text=value if isinstance(value, str) else None, unit=unit, source_id=FUTURE_SOURCE_ID,
                    source_name='WRI Aqueduct4.0 future_annual', source_url=SOURCE_URL, source_field=field,
                    source_version=cfg.get('source_version', 'Aqueduct4.0 Y2023M07D05'), data_year=period,
                    retrieved_at=cfg.get('retrieved_at'), spatial_resolution='HydroBASINS Level6 subbasin polygons',
                    aggregation_method='plurality area; lowest code tie' if suffix in {'category', 'label'} else 'study-intersection area-weighted overlay',
                    coverage_frac=coverage, status=status, confidence=confidence,
                    missing_reason=None if present else ('unsupported_source_period' if not info['supported'] else 'source_nodata' if native is not None else 'source_not_acquired'),
                    method=method, data_mode=result.data_mode.iloc[0])
                records.append(record.model_dump(mode='json'))
                values.append(value); statuses.append(status); confidences.append(confidence); coverages.append(coverage)
            for name, vals in ((metric, values), (metric+'_status', statuses), (metric+'_confidence', confidences), (metric+'_coverage_frac', coverages)):
                columns[name] = vals
    result = gpd.GeoDataFrame(pd.concat([result, pd.DataFrame(columns, index=result.index)], axis=1), geometry=geography.geometry.name, crs=geography.crs)
    result.attrs = dict(geography.attrs, grid_definition_id=identity, data_mode=mode)
    added = pd.DataFrame(records).sort_values(['grid_id', 'metric']).reset_index(drop=True)
    # Preserve baseline table scalar/dtype semantics, including all-null columns.
    added = added.astype(baseline_provenance.dtypes.to_dict())
    provenance = pd.concat([baseline_provenance, added], ignore_index=True)
    provenance.attrs = dict(baseline_provenance.attrs, grid_definition_id=identity, data_mode=mode)
    coverage = dict(analyzed_cells=len(result), future_metric_rows=len(added), known_scenario_rows=int(added.status.eq('scenario').sum()),
                    unsupported_years=[y for y in milestone_years if y not in WINDOWS],
                    metrics={k: dict(known=int(q.status.eq('scenario').sum()), unknown=int(q.status.eq('unknown').sum()), mean_coverage_frac=float(q.coverage_frac.mean())) for k, q in added.groupby('metric', sort=True)})
    manifest = dict(source=dict(source_id=FUTURE_SOURCE_ID, implemented=True, acquired=native is not None,
        analyzed=native is not None, status='READY' if native is not None else 'PARTIAL', sha256=source_hash,
        source_version=cfg.get('source_version', 'Aqueduct4.0 Y2023M07D05'), retrieved_at=cfg.get('retrieved_at'),
        source_url=SOURCE_URL, source_layer='future_annual', license='CC BY4.0; World Resources Institute2023'),
        periods=periods, baseline_columns_preserved=True, original_provenance_rows_preserved=True,
        spatial_aggregation_version='aqueduct-future-study-overlay-v1', interpretation='Basin-scale scenario context, not committed water supply or an annual measurement')
    return result, provenance, coverage, manifest
