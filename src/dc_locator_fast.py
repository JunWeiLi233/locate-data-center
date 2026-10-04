"""Exact facility re-evaluation of an explicitly fixed native regional cohort.

This executor is separately hash-bound, outside the live dc_locator package's
file inventory. Native data and accepted evidence are immutable inputs. It does
not discover additional windows, download data, or assess sensitivity cases.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import time
import gc
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import yaml

from dc_locator.io import read_geoparquet, write_geoparquet, write_parquet
from dc_locator.model.cooling import CoolingDesign, PhysicalScenario
from dc_locator.model.metrics import KEYS, ScoringProfile, clean, json_text, profile_fingerprint
from dc_locator.model.normalization import normalize_values
from dc_locator.model.physics import calculate_annual, simulate
from dc_locator.model.regional_decision import prepare_batch, rank_compact
from dc_locator.model.regions import cluster_regions, screen_region_land_support
from dc_locator.model.screening import Requirement, screen
from dc_locator.provenance import DataMode
from dc_locator.schemas import CandidateRegion, FacilityConfig

VERSION = 'fixed_cohort_cached_v1'
CARBON = 'grid_carbon_intensity_kg_per_mwh'
METHOD_PATHS = ['schemas.py', 'io.py', 'provenance.py', 'model/cooling.py',
    'model/physics.py', 'model/screening.py', 'model/metrics.py', 'model/decision.py',
    'model/normalization.py', 'model/mcda.py', 'model/pareto.py', 'model/ahp.py',
    'model/regional_decision.py', 'model/regions.py']
GUARD_PATHS = ['model/enhanced.py']
INTERPRETATION = ('These geographic regions deserve further investigation under the stated facility requirements, '
    'datasets, constraints, assumptions, and decision preferences. They are not proven buildable parcels.')


def file_digest(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _digest(value):
    return hashlib.sha256(json_text(value).encode()).hexdigest()


def _document(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _emit(path, value):
    Path(path).write_text(json_text(clean(value)) + '\n', encoding='utf-8')


def verify_cache(folder, manifest):
    """Verify bytes, including corruption with unchanged length and timestamp."""
    folder = Path(folder).resolve()
    hashes = manifest.get('output_hashes')
    if not isinstance(hashes, dict) or not hashes:
        raise ValueError('Cache has no content checksums')
    for name, digest in hashes.items():
        path = (folder / name).resolve()
        if not path.is_relative_to(folder) or not path.is_file() or file_digest(path) != digest:
            raise ValueError('Cached input checksum mismatch: ' + name)


def _carbon_values(carbon, scenarios):
    if carbon.grid_id.duplicated().any():
        raise ValueError('Duplicate native carbon evidence')
    known = carbon.value.notna() & ~carbon.status.eq('unknown')
    if not carbon.loc[known, 'unit'].eq('kg_CO2e_per_mwh').all():
        raise ValueError('Carbon input must have explicit kg_CO2e_per_mwh units')
    for scenario in scenarios:
        if not carbon.loc[known, 'data_year'].eq(scenario.carbon_data_year).all():
            raise ValueError('Carbon source year disagrees with external scenario year')
    complete = carbon.coverage_frac.notna() & carbon.coverage_frac.ge(1 - 1e-6)
    return pd.to_numeric(carbon.value, errors='raise').where(known & complete)


def prepare_cached_compact(compact, carbon, facility, designs, scenarios, profile):
    """Recompute physical values using native factors, preserving validated evidence.

    Screening dependencies are checked by the executor before this pure helper.
    No saved physical quantity is divided or scaled. Each distinct source factor
    is passed through the accepted annual identities for each selected design.
    """
    selected = set(facility.cooling_designs)
    if facility.cooling_design_id:
        selected.add(facility.cooling_design_id)
    designs = [d for d in designs if not selected or d.design_id in selected]
    if selected and selected != {d.design_id for d in designs}:
        raise ValueError('Requested cooling design is absent from cached cohort')
    if not designs or not scenarios:
        raise ValueError('Nonempty cached designs/scenarios required')
    if any(d.water_basis != 'consumption' or d.peak_pue_verified for d in designs):
        raise ValueError('Fast cohort supports the frozen consumption designs with unverified peak PUE')
    if any(s.grid_water_basis != 'consumption' for s in scenarios):
        raise ValueError('Fast cohort requires the frozen consumption generation-water basis')
    factors = _carbon_values(carbon, scenarios)
    factor_index = pd.Series(factors.to_numpy(), index=carbon.grid_id)
    frame = compact.loc[compact.design_id.isin([d.design_id for d in designs])].copy().reset_index(drop=True)
    if not set(frame.grid_id) <= set(carbon.grid_id):
        raise ValueError('Cached alternative lacks native carbon evidence')
    if set(frame.scenario_id) != {s.scenario_id for s in scenarios}:
        raise ValueError('Cached external scenarios disagree with request')
    frame['facility_id'] = facility.facility_id
    frame[CARBON] = frame.grid_id.map(factor_index)
    for scenario in scenarios:
        if str(facility.target_opening_year) != scenario.carbon_data_year and not scenario.historical_static:
            raise ValueError('Historical carbon reused for another year requires historical_static scenario')
        for design in designs:
            mask = frame.design_id.eq(design.design_id) & frame.scenario_id.eq(scenario.scenario_id)
            raw = frame.loc[mask, CARBON]
            codes, unique = pd.factorize(raw, sort=True, use_na_sentinel=False)
            outputs = [calculate_annual(facility.peak_it_power_mw, facility.average_it_load_factor,
                facility.hours_in_modeled_year, design.annual_pue,
                None if pd.isna(factor) else float(factor), design.wue_l_per_it_kwh,
                scenario.grid_water_l_per_kwh) for factor in unique]
            for field in outputs[0]:
                values = np.array([np.nan if result[field] is None else result[field] for result in outputs])
                frame.loc[mask, field] = values[codes]
            frame.loc[mask, 'pue'] = design.annual_pue
            frame.loc[mask, 'wue_l_per_kwh'] = design.wue_l_per_it_kwh
    for field in ('w_site_withdrawal_m3', 'w_site_withdrawal_liters',
                  'w_electricity_withdrawal_m3', 'w_electricity_withdrawal_liters', 'peak_facility_demand_mw'):
        frame[field] = np.nan
    for field in ('target_opening_year', 'operating_lifetime_years', 'hours_in_modeled_year'):
        frame[field] = getattr(facility, field)
    for metric in profile.metrics:
        if metric.table != 'performance':
            continue
        if metric.column not in {'c_electricity_tonnes', 'w_site_m3'}:
            raise ValueError('Unsupported cached performance metric: ' + metric.column)
        raw = frame[metric.column].to_numpy(dtype=float)
        frame['raw_' + metric.metric_id] = raw
        accepted = pd.Series(raw).where(frame[metric.metric_id + '_source_valid'])
        values, flags = normalize_values(accepted, metric.reference_low, metric.reference_high, metric.direction)
        frame[metric.metric_id] = values
        frame[metric.metric_id + '_normalization_status'] = flags
    return frame


def _typed_decision_numbers(value):
    """Type numeric decision inputs consistently without coercing invalid types."""
    if type(value) in (int, float):
        return float(value)
    if isinstance(value, dict):
        return {key: _typed_decision_numbers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_typed_decision_numbers(item) for item in value]
    return value


def parse_request(request, baseline, profile):
    """Translate the exposed request; retain frozen land/design assumptions."""
    request = dict(request)
    preferences = {k: request.pop(k, None) for k in ('weighting', 'group_weights', 'ahp_matrix')}
    values = baseline.model_dump(mode='json')
    if 'average_load_percent' in request:
        required = {'peak_it_power_mw', 'average_load_percent', 'target_opening_year',
                    'lifetime_years', 'cooling', 'screening_mode'}
        if set(request) != required:
            raise ValueError('Cached facility request has missing or unexpected fields')
        for field, maximum in [('peak_it_power_mw', 1000), ('average_load_percent', 100)]:
            value = request[field]
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= maximum:
                raise ValueError('Invalid exposed facility ' + field)
        for field, low, high in [('target_opening_year', 2026, 2100), ('lifetime_years', 1, 100)]:
            value = request[field]
            if type(value) is not int or not low <= value <= high:
                raise ValueError('Invalid exposed facility ' + field)
        cooling = request['cooling']
        if type(cooling) is not str or cooling not in {'all', *baseline.cooling_designs}:
            raise ValueError('Cooling design is absent from the frozen cohort')
        values.update(peak_it_power_mw=request['peak_it_power_mw'],
            average_it_load_factor=request['average_load_percent'] / 100,
            target_opening_year=request['target_opening_year'],
            operating_lifetime_years=request['lifetime_years'],
            cooling_design_id=None, cooling_designs=baseline.cooling_designs if cooling == 'all' else [cooling],
            screening_mode=request['screening_mode'])
    else:
        if set(request) - set(FacilityConfig.model_fields):
            raise ValueError('Unknown native facility fields')
        values.update(request)
    facility = FacilityConfig.model_validate(values)
    if facility.minimum_land_area_km2 != baseline.minimum_land_area_km2:
        raise ValueError('Cached screening requires the frozen minimum-land threshold')
    if facility.hours_in_modeled_year is None:
        raise ValueError('Explicit modeled-year hours are required')
    document = profile.model_dump(mode='json')
    method = preferences['weighting'] or profile.weighting_method
    document.update(weighting_method=method, user_weights=None, ahp_judgments=None)
    if method == 'user':
        document['user_weights'] = _typed_decision_numbers(preferences['group_weights'])
    elif method == 'ahp':
        document['ahp_judgments'] = {'criteria_ids': profile.weight_criterion_ids,
            'matrix': _typed_decision_numbers(preferences['ahp_matrix'])}
    elif method != 'equal':
        raise ValueError('Unknown weighting method')
    active_profile = ScoringProfile.model_validate(document)
    canonical_facility = facility.model_dump(mode='json')
    canonical_facility.pop('facility_id')
    facility = facility.model_copy(update={'facility_id': 'cached_facility_' +
        _digest([canonical_facility, active_profile.model_dump(mode='json')])[:16]})
    return facility, active_profile


def _baseline_context(root, baseline):
    root, baseline = Path(root).resolve(), Path(baseline).resolve()
    if not baseline.is_relative_to(root / 'runs'):
        raise ValueError('Baseline must be an existing workspace run')
    metadata = _document(baseline / 'run_metadata.json')
    if metadata.get('data_mode') != 'real' or not metadata.get('run_id'):
        raise ValueError('A completed real native baseline is required')
    metadata_sha = file_digest(baseline / 'run_metadata.json')
    hashes = metadata.get('output_hashes', {})
    for name in ('config_snapshot.json', 'profile_snapshot.json', 'regional_catalog.json',
                 'regional_binding.json', 'us_grid_dataset.parquet', 'refinement_windows.parquet'):
        if hashes.get(name) != file_digest(baseline / name):
            raise ValueError('Baseline artifact checksum mismatch: ' + name)
    snapshot = _document(baseline / 'config_snapshot.json')
    catalog = _document(baseline / 'regional_catalog.json')
    binding = _document(baseline / 'regional_binding.json')
    if binding.get('land_search_scope') != 'multi_cell_region':
        raise ValueError('Cached baseline must use current multi-cell land screening')
    documents = {Path(k).name: yaml.safe_load(v) for k, v in snapshot['files'].items()}
    important = {'constraints.yaml', 'cooling_designs.yaml', 'phase3_physical_scenarios.yaml',
                 'scoring_profile_regional.yaml', 'grid_regional.yaml'}
    config_hashes = {}
    for name in important:
        paths = [Path(k) for k in snapshot['files'] if Path(k).name == name]
        if len(paths) != 1:
            raise ValueError('Missing or ambiguous frozen policy: ' + name)
        path = paths[0]
        if not path.is_relative_to(root) or metadata['config_hashes'].get(str(path)) != file_digest(path):
            raise ValueError('Current policy differs from the cached snapshot: ' + name)
        config_hashes[str(path)] = file_digest(path)
    methods = {}
    saved_methods = {str(k).replace('\\', '/'): v for k, v in metadata['actual_working_code_sha256'].items()}
    for name in METHOD_PATHS:
        path = root / 'src/dc_locator' / name
        relative = path.relative_to(root).as_posix()
        methods[relative] = file_digest(path)
        if saved_methods.get(relative) != methods[relative]:
            raise ValueError('Current calculation method differs from the cached baseline: ' + relative)
    guard_hashes = {(Path('src/dc_locator') / name).as_posix():
        file_digest(root / 'src/dc_locator' / name) for name in GUARD_PATHS}
    from dc_locator.pipeline import environment_identity
    environment = environment_identity()
    if metadata.get('environment') != environment:
        raise ValueError('Cached model environment differs from current environment')
    profile = ScoringProfile.model_validate(_document(baseline / 'profile_snapshot.json')['profile'])
    if profile.region_selection.get('maximum_extent_km') != 20.:
        raise ValueError('Cached cohort requires the declared 20 km regional extent')
    facility = FacilityConfig.model_validate(documents['facility.yaml']['facilities'][0])
    designs = [CoolingDesign.model_validate(d) for d in documents['cooling_designs.yaml']['cooling_designs']]
    scenarios = [PhysicalScenario.model_validate(s) for s in documents['phase3_physical_scenarios.yaml']['scenarios']]
    requirements = [Requirement.model_validate(r) for r in documents['constraints.yaml']['requirements']]
    if any(d.peak_pue_verified or d.water_basis != 'consumption' for d in designs):
        raise ValueError('Frozen screening dependencies are unsupported by the fast executor')
    if any(s.grid_water_basis != 'consumption' for s in scenarios):
        raise ValueError('Unsupported frozen generation-water basis')
    identity = _digest(dict(version=VERSION, baseline_sha256=metadata_sha,
        runner_sha256=file_digest(__file__), method_hashes=methods, guard_hashes=guard_hashes,
        config_hashes=config_hashes,
        environment=environment))
    return dict(root=root, baseline=baseline, metadata=metadata, snapshot=snapshot, catalog=catalog,
        facility=facility, designs=designs, scenarios=scenarios, requirements=requirements,
        profile=profile, methods=methods, guard_hashes=guard_hashes,
        config_hashes=config_hashes, environment=environment,
        identity=identity, metadata_sha=metadata_sha,
        cache=root / 'data/interim/fast_cached_regions' / identity[:24])


def _categorize(frame):
    for column in frame.select_dtypes(include='object'):
        if column not in KEYS and frame[column].nunique(dropna=False) < 100:
            frame[column] = frame[column].astype('category')
    return frame


def enrich_geographic_labels(geometry, labels):
    """Join exact native administrative labels with complete grid-ID coverage."""
    if labels.grid_id.duplicated().any() or set(labels.grid_id) != set(geometry.grid_id):
        raise ValueError('Native geographic label coverage is incomplete or duplicated')
    result = geometry.copy()
    indexed = labels.set_index('grid_id')
    for field in labels.columns:
        if field == 'grid_id':
            continue
        values = result.grid_id.map(indexed[field])
        if field in result and not result[field].fillna('<UNKNOWN>').equals(values.fillna('<UNKNOWN>')):
            raise ValueError('Existing administrative labels disagree with native evidence')
        result[field] = values
    return result


def _write(frame, path, schema, definition, *, geo=False, version='1.0.0'):
    writer = write_geoparquet if geo else write_parquet
    writer(frame, path, schema_name=schema, schema_version=version,
        data_mode=DataMode.REAL, grid_definition_id=definition)


def _status(context):
    path = context['cache'] / 'manifest.json'
    result = dict(ready=False, available=False, reason='Static native cache is not prepared',
        manifest_path=str(path), manifest_sha256=None, baseline_run_id=context['metadata']['run_id'],
        cohort_cells=context['metadata']['geographic_cells'], parent_windows=len(context['catalog']['parts']))
    if path.exists():
        manifest = _document(path)
        if manifest.get('cache_identity') != context['identity']:
            raise ValueError('Static cache identity differs from current methods/policies')
        verify_cache(context['cache'], manifest)
        result.update(ready=True, available=True, reason=None, manifest_sha256=file_digest(path))
    return result


def cached_cohort_status(root, baseline):
    """Check readiness and content integrity; never construct a cache."""
    try:
        return _status(_baseline_context(root, baseline))
    except (ValueError, FileNotFoundError, KeyError) as exc:
        return dict(ready=False, available=False, reason=str(exc), manifest_path=None,
            manifest_sha256=None, baseline_run_id=None, cohort_cells=None, parent_windows=None)


def prepare_cached_cohort(root, baseline):
    """Consolidate accepted native evidence once, with immutable byte bindings."""
    started = time.perf_counter()
    context = _baseline_context(root, baseline)
    folder, baseline = context['cache'], context['baseline']
    if _status(context)['ready']:
        return folder / 'manifest.json'
    if folder.exists() and any(folder.iterdir()):
        raise ValueError('Incomplete static cache exists; preserve it and choose a clean revision')
    folder.mkdir(parents=True, exist_ok=True)
    compact_parts, strict_parts, carbon_parts, check_parts, label_parts = [], [], [], [], []
    input_hashes = {}
    checks_columns = [*KEYS, 'requirement', 'outcome', 'value', 'unit', 'threshold', 'is_critical',
        'missing_reason', 'metric', 'reason', 'source_status', 'confidence', 'coverage_frac']
    for part in context['catalog']['parts']:
        path = baseline / part['path']
        if not path.resolve().is_relative_to(baseline / 'parts'):
            raise ValueError('Native part path escapes the accepted baseline')
        for name in ('compact.parquet', 'strict_compact.parquet', 'feature_provenance.parquet',
                     'us_grid_dataset.parquet', 'screening_results.parquet'):
            expected = part['output_hashes'].get(name)
            digest = file_digest(path / name)
            if not expected or expected != digest:
                raise ValueError('Native part checksum mismatch: ' + str(path / name))
            input_hashes[(path / name).relative_to(baseline).as_posix()] = digest
        compact_parts.append(_categorize(pd.read_parquet(path / 'compact.parquet')))
        strict_parts.append(_categorize(pd.read_parquet(path / 'strict_compact.parquet')))
        label_parts.append(pd.read_parquet(path / 'us_grid_dataset.parquet',
            columns=['grid_id', 'state_abbr_primary', 'county_name_primary']))
        carbon = pd.read_parquet(path / 'feature_provenance.parquet', filters=[('metric', '==', CARBON)])
        _carbon_values(carbon, context['scenarios'])
        carbon_parts.append(carbon)
        checks = pd.read_parquet(path / 'screening_results.parquet', columns=checks_columns)
        check_parts.append(_categorize(checks))
    definition = context['metadata']['grid_definition_id']
    geometry = enrich_geographic_labels(read_geoparquet(baseline / 'us_grid_dataset.parquet'),
        pd.concat(label_parts, ignore_index=True))
    compact = pd.concat(compact_parts, ignore_index=True).sort_values(KEYS).reset_index(drop=True)
    strict = pd.concat(strict_parts, ignore_index=True).sort_values(KEYS).reset_index(drop=True)
    carbon = pd.concat(carbon_parts, ignore_index=True).sort_values('grid_id').reset_index(drop=True)
    checks = pd.concat(check_parts, ignore_index=True).sort_values(KEYS + ['requirement']).reset_index(drop=True)
    del compact_parts, strict_parts, carbon_parts, check_parts, label_parts
    gc.collect()
    if len(geometry) != context['metadata']['geographic_cells'] or len(geometry) > 200000:
        raise ValueError('Native cohort count exceeds the accepted bounded universe')
    if geometry.crs.to_epsg() != 5070 or geometry.grid_id.duplicated().any():
        raise ValueError('Invalid cached geographic identity')
    if set(geometry.grid_id) != set(carbon.grid_id) or set(geometry.grid_id) != set(compact.grid_id):
        raise ValueError('Native cohort evidence lacks exact all-cell coverage')
    land = compact[['grid_id', 'suitable_land_area_km2']].drop_duplicates()
    if land.grid_id.duplicated().any():
        raise ValueError('Native land support differs between decision alternatives')
    if 'suitable_land_area_km2' not in geometry:
        geometry['suitable_land_area_km2'] = geometry.grid_id.map(land.set_index('grid_id').suitable_land_area_km2)
    if not compact[KEYS].equals(strict[KEYS]) or compact.duplicated(KEYS).any():
        raise ValueError('Native baseline and STRICT alternatives do not align')
    expected_designs = {d.design_id for d in context['designs']}
    expected_scenarios = {s.scenario_id for s in context['scenarios']}
    if set(compact.design_id) != expected_designs or set(compact.scenario_id) != expected_scenarios \
            or len(compact) != len(geometry) * len(expected_designs) * len(expected_scenarios):
        raise ValueError('Native cache lacks the complete all-cell alternative universe')
    if not compact['mode'].eq('EXPLORATORY').all() or not strict['mode'].eq('STRICT').all():
        raise ValueError('Invalid cached screening-mode evidence')
    if not compact.hard_fail.equals(strict.hard_fail) or not compact.critical_unknown.equals(strict.critical_unknown):
        raise ValueError('Cached STRICT cannot change native FAIL/UNKNOWN evidence')
    _write(compact, folder / 'compact.parquet', 'RegionalPreparedDecisionDataset', definition)
    _write(strict, folder / 'strict_compact.parquet', 'RegionalPreparedDecisionDataset', definition)
    _write(carbon, folder / 'carbon.parquet', 'FeatureMetadata', definition, version='1.1.0')
    _write(checks, folder / 'screening_checks.parquet', 'CachedScreeningChecks', definition)
    _write(geometry, folder / 'geometry.parquet', 'RegionalGridIndex', definition, geo=True, version='1.1.0')
    del compact, strict, carbon, checks, geometry
    gc.collect()
    manifest = dict(version=VERSION, cache_identity=context['identity'], data_mode='real',
        baseline_run_id=context['metadata']['run_id'], baseline_path=str(baseline),
        baseline_run_metadata_sha256=context['metadata_sha'], cohort_cells=context['metadata']['geographic_cells'],
        parent_windows=len(context['catalog']['parts']), grid_definition_id=definition,
        method_hashes=context['methods'], guard_hashes=context['guard_hashes'],
        config_hashes=context['config_hashes'],
        external_runner_sha256=file_digest(__file__), baseline_input_hashes=input_hashes,
        source_checksums=context['metadata']['source_checksums'],
        frozen_screening_dependencies=dict(minimum_land_area_km2=context['facility'].minimum_land_area_km2,
            peak_pue_verified=False, land_search_scope='multi_cell_region',
            explanation='Thresholds remain identical: minimum land is frozen; selected designs have unverified peak demand. Other requirements are facility-independent.'),
        consolidation_seconds=time.perf_counter()-started,
        output_hashes={p.name: file_digest(p) for p in sorted(folder.glob('*.parquet'))})
    _emit(folder / 'manifest.json', manifest)
    return folder / 'manifest.json'


def _request_identity(context, status, facility, profile, submitted):
    # Raw submitted JSON is retained in the snapshot; semantic deduplication
    # binds the validated typed facility and active decision profile.
    return _digest(dict(cache_identity=context['identity'], cache_manifest_sha256=status['manifest_sha256'],
        facility=facility.model_dump(mode='json'), profile=profile.model_dump(mode='json')))


def stable_request_identity(root, baseline, facility_dict):
    context = _baseline_context(root, baseline)
    status = _status(context)
    if not status['ready']:
        raise FileNotFoundError(status['reason'])
    facility, profile = parse_request(facility_dict, context['facility'], context['profile'])
    return _request_identity(context, status, facility, profile, facility_dict)


fast_request_identity = stable_request_identity


def _cluster_land_native(geography, ranked, policy, physical_columns, profile_id, fingerprint, minimum_land):
    regions, membership = cluster_regions(geography, ranked, policy,
        physical_columns, profile_id, fingerprint)
    if not len(regions):
        return screen_region_land_support(regions, membership, minimum_land)
    groups = membership.groupby('region_id', sort=False)
    accepted, members, audits = [], [], []
    for position, region_id in enumerate(regions.region_id):
        r, m, a = screen_region_land_support(regions.iloc[position:position+1],
            groups.get_group(region_id), minimum_land)
        accepted.append(r); members.append(m); audits.append(a)
    return (gpd.GeoDataFrame(pd.concat(accepted, ignore_index=True), geometry='geometry', crs=5070),
        pd.concat(members, ignore_index=True), pd.concat(audits, ignore_index=True))


def _cluster_group_worker(arguments):
    started = time.perf_counter()
    result = _cluster_land_native(*arguments)
    from dc_locator.model.enhanced import peak_working_set_bytes
    peak = peak_working_set_bytes()
    if peak is None or peak >= 4 * 1024**3:
        raise ValueError('Clustering worker exceeded or could not verify the 4 GiB process memory budget')
    ranked = arguments[1]
    observation = dict(design_id=str(ranked.design_id.iloc[0]), scenario_id=str(ranked.scenario_id.iloc[0]),
        process_peak_bytes=peak, elapsed_seconds=time.perf_counter()-started)
    return result, observation


def _cluster_cohort_bounded(geography, ranked, policy, physical_columns, profile_id, fingerprint,
                          minimum_land, *, max_workers=2, parallel_minimum_rows=10000, execution_report=None):
    """Run independent native design/scenario groups with at most two processes."""
    if type(max_workers) is not int or max_workers not in (1, 2):
        raise ValueError('Clustering supports only one or two bounded workers')
    started = time.perf_counter()
    indices = ranked.groupby(['design_id', 'scenario_id'], sort=True).indices
    parallel = max_workers == 2 and len(indices) > 1 and len(ranked) >= parallel_minimum_rows and ranked.rankable.any()
    report = dict(workers=2 if parallel else 1, groups=len(indices), worker_observations=[])
    if not parallel:
        result = _cluster_land_native(geography, ranked, policy, physical_columns, profile_id, fingerprint, minimum_land)
    else:
        fields = ['grid_id', 'grid_definition_id', 'row', 'col', 'geometry',
            'study_area_intersection_km2', 'suitable_land_area_km2']
        if 'cell_area_km2' in geography:
            fields.append('cell_area_km2')
        geometry = geography[fields]
        arguments = [(geometry, ranked.iloc[positions].copy(), policy, physical_columns,
            profile_id, fingerprint, minimum_land) for positions in indices.values()]
        with ProcessPoolExecutor(max_workers=2, mp_context=multiprocessing.get_context('spawn')) as executor:
            grouped = list(executor.map(_cluster_group_worker, arguments))
        report['worker_observations'] = [observation for _, observation in grouped]
        merged = []
        for position, ordering in enumerate((['region_id'], ['region_id', *KEYS], ['region_id'])):
            frames = [tables[position] for tables, _ in grouped]
            nonempty = [frame for frame in frames if len(frame)]
            frame = pd.concat(nonempty, ignore_index=True) if nonempty else frames[0]
            merged.append(frame.sort_values(ordering).reset_index(drop=True))
        result = tuple(merged)
    report['wall_seconds'] = time.perf_counter()-started
    if execution_report is not None:
        execution_report.update(report)
    return result


def evaluate_prepared_cohort(compact, carbon, geography, facility, designs, scenarios, profile, *, progress=None,
                             execution_report=None):
    """Globally evaluate every prepared alternative with accepted model functions."""
    if progress:
        progress('simulate')
    prepared = prepare_cached_compact(compact, carbon, facility, designs, scenarios, profile)
    if progress:
        progress('rank')
    fingerprint = profile_fingerprint(profile)
    ranked = rank_compact(prepared, profile, profile_hash=fingerprint)
    del prepared
    if progress:
        progress('cluster')
    # The native clusterer only consumes these columns; representatives are
    # hydrated afterward from freshly simulated native evidence.
    columns = list(dict.fromkeys([*KEYS, 'mcda_score', 'rankable', 'conditional',
        'critical_unknown', 'is_pareto_optimal', *[m.column for m in profile.metrics]]))
    regions, membership, land = _cluster_cohort_bounded(geography, ranked[columns], profile.region_selection,
        [m.column for m in profile.metrics], profile.profile_id, fingerprint,
        facility.minimum_land_area_km2, execution_report=execution_report)
    return ranked, regions, membership, land


def validate_representative_equivalence(native, ranked, profile, *, global_index=None):
    """Require fresh native evidence to agree before attaching global ranks."""
    keys = pd.MultiIndex.from_frame(native[KEYS])
    if native.duplicated(KEYS).any() or global_index is None and ranked.duplicated(KEYS).any():
        raise ValueError('Fresh representative alternative identities are not unique')
    if global_index is None:
        fields = [*KEYS, 'mcda_score', *profile.metric_ids, *['raw_' + m.metric_id for m in profile.metrics],
                  'eligible', 'conditional', 'hard_fail', 'critical_unknown']
        global_index = ranked[fields].set_index(KEYS)
    if (global_index.index.get_indexer(keys) < 0).any():
        raise ValueError('Fresh representative is absent from globally evaluated alternatives')
    columns = ['mcda_score', *profile.metric_ids, *['raw_' + m.metric_id for m in profile.metrics]]
    for column in columns:
        fresh = native[column].to_numpy(dtype=float)
        accepted = global_index[column].reindex(keys).to_numpy(dtype=float)
        if not np.array_equal(fresh, accepted, equal_nan=True):
            raise ValueError('Fresh representative metrics disagree with global cached evaluation: ' + column)
    for column in ('eligible', 'conditional', 'hard_fail', 'critical_unknown'):
        if not np.array_equal(native[column].to_numpy(), global_index[column].reindex(keys).to_numpy()):
            raise ValueError('Fresh representative screening disagrees with global cached evaluation: ' + column)


def _representatives(context, regions, ranked, facility, profile):
    """Fresh native physics/checks, with immutable geographic source lineage."""
    needed = set(regions.representative_grid_id)
    evidence_parts, screen_parts, geo_parts, prov_parts, representatives = [], [], [], [], {}
    fingerprint = profile_fingerprint(profile)
    designs = [d for d in context['designs'] if d.design_id in set(ranked.design_id)]
    ranked_index = ranked.set_index(KEYS)
    overlay = ['mcda_score', 'mcda_rank', 'rankable', 'rank_status', 'unranked_reason',
        'pareto_comparable', 'pareto_status', 'is_pareto_optimal', 'pareto_rank',
        'profile_id', 'profile_fingerprint', 'weighting_method', 'ahp_status',
        'weights_used_json', 'contribution_by_metric_json', *['contribution_' + m.metric_id for m in profile.metrics]]
    for part in context['catalog']['parts']:
        path = context['baseline'] / part['path']
        # Read only grid IDs first to avoid hydrating unused native windows.
        ids = set(pd.read_parquet(path / 'us_grid_dataset.parquet', columns=['grid_id']).grid_id) & needed
        if not ids:
            continue
        for name in ('us_grid_dataset.parquet', 'feature_provenance.parquet'):
            if file_digest(path / name) != part['output_hashes'][name]:
                raise ValueError('Native representative evidence checksum mismatch: ' + name)
        geo = gpd.read_parquet(path / 'us_grid_dataset.parquet', filters=[('grid_id', 'in', sorted(ids))])
        prov = pd.read_parquet(path / 'feature_provenance.parquet', filters=[('grid_id', 'in', sorted(ids))])
        screening, eligible, _ = screen(geo, prov, facility, designs, context['scenarios'], context['requirements'],
            mode=facility.screening_mode, land_search_scope='multi_cell_region')
        performance = simulate(geo, prov, facility, designs, context['scenarios'])
        native = prepare_batch(geo, prov, performance, eligible, profile,
            profile_hash=fingerprint, provenance_grid_definition_id=context['metadata']['grid_definition_id'])['ranked_cells']
        validate_representative_equivalence(native, ranked, profile, global_index=ranked_index)
        indices = pd.MultiIndex.from_frame(native[KEYS])
        for column in overlay:
            native[column] = ranked_index[column].reindex(indices).to_numpy()
        evidence_parts.append(native); screen_parts.append(screening); geo_parts.append(geo); prov_parts.append(prov)
        representatives.update({grid_id: part['path'] for grid_id in ids})
    if needed != set(representatives):
        raise ValueError('Fresh representative evidence is incomplete')
    if not needed:
        # Empty strict results still publish explicit typed artifacts.
        return pd.DataFrame(columns=[*KEYS, 'metric_metadata_json', 'assumptions_json', 'warnings_json']), \
            pd.DataFrame(columns=[*KEYS, 'requirement', 'outcome', 'missing_reason', 'is_critical', 'mode']), \
            gpd.GeoDataFrame(columns=['grid_id', 'geometry'], geometry='geometry', crs=5070), \
            pd.DataFrame(columns=['grid_id', 'metric', 'value', 'status', 'missing_reason']), representatives
    evidence = pd.concat(evidence_parts, ignore_index=True).sort_values(KEYS).reset_index(drop=True)
    screening = pd.concat(screen_parts, ignore_index=True).sort_values(KEYS + ['requirement']).reset_index(drop=True)
    geo = gpd.GeoDataFrame(pd.concat(geo_parts, ignore_index=True), geometry='geometry', crs=5070)
    provenance = pd.concat(prov_parts, ignore_index=True)
    indexed = evidence.set_index(KEYS)
    for position, region in enumerate(regions.itertuples()):
        key = (region.representative_grid_id, region.design_id, region.scenario_id)
        # Index keys must remain explicit in the published evidence record.
        row = indexed.loc[key].to_dict()
        row.update(zip(KEYS, key))
        regions.at[position, 'representative_json'] = json_text(clean(row))
    return evidence, screening, geo, provenance, representatives


def _physical_evidence(ranked, carbon, facility, designs, scenarios):
    """Persist all numeric physical fields with metadata from native simulation."""
    first = carbon.iloc[:1].copy()
    geo = pd.DataFrame(dict(grid_id=first.grid_id, grid_definition_id=ranked.grid_definition_id.iloc[0],
        data_mode='real'))
    geo[CARBON] = first.value.to_numpy()
    geo[CARBON + '_status'] = first.status.to_numpy()
    geo[CARBON + '_coverage_frac'] = first.coverage_frac.to_numpy()
    templates = simulate(geo, first, facility, designs, scenarios)
    schema = {}
    source_status = carbon.set_index('grid_id').status
    for template in templates.itertuples():
        mask = ranked.design_id.eq(template.design_id) & ranked.scenario_id.eq(template.scenario_id)
        metadata = json.loads(template.metric_metadata_json)
        schema[template.design_id + '/' + template.scenario_id] = {
            field: {k: value for k, value in item.items() if k not in {'source_evidence', 'status', 'confidence', 'missing_reason'}}
            for field, item in metadata.items()}
        for field, item in metadata.items():
            known = ranked.loc[mask, field].notna()
            status = 'scenario' if field in {'pue', 'wue_l_per_kwh'} else 'calculated'
            if field == CARBON:
                scenario = next(s for s in scenarios if s.scenario_id == template.scenario_id)
                statuses = ranked.loc[mask, 'grid_id'].map(source_status).astype(object)
                if str(facility.target_opening_year) != scenario.carbon_data_year:
                    statuses[:] = 'scenario'
            else:
                statuses = pd.Series(status, index=known.index)
            ranked.loc[mask, field + '_status'] = statuses.where(known, 'unknown')
            ranked.loc[mask, field + '_confidence'] = np.where(known, 'low', 'unknown')
            ranked.loc[mask, field + '_missing_reason'] = np.where(known, None, 'missing_input_or_incompatible_water_basis')
            ranked.loc[mask, field + '_unit'] = item['unit']
    return dict(schema_version='1.0.0', method='Native dc_locator.model.physics annual identities',
        template_scope='Shared units/methods only; row status/confidence/null reasons are explicit columns',
        carbon_evidence='Content-bound native carbon.parquet in input_cache; no future or marginal factors',
        metrics_by_design_scenario=schema,
        interpretation='Annual operating quantities. Lifetime is recorded without assuming lifetime totals.')


def _owned_output(root, baseline, output):
    root = Path(root).resolve()
    output = Path(output)
    output = (root / output).resolve() if not output.is_absolute() else output.resolve()
    relative = output.relative_to(root) if output.is_relative_to(root) else None
    protected = relative and relative.parts[0] == 'runs' and len(relative.parts) > 1 \
        and (relative.parts[1].startswith(('phase', 'orchestrator_')) or relative.parts[1] == 'example')
    if relative is None or len(relative.parts) < 2 or relative.parts[0] not in {'runs', '.pytest-work'} \
            or protected or output == Path(baseline).resolve() or output.exists() and any(output.iterdir()):
        raise ValueError('Choose a new owned output folder; accepted evidence cannot be replaced')
    return output


def evaluate_cached_regions(root, baseline, facility_dict, output, *, progress=None):
    """Evaluate every cached native cell; publish a separately bound completed run."""
    started = time.perf_counter()
    output = _owned_output(root, baseline, output)
    context = _baseline_context(root, baseline)
    status = _status(context)
    if not status['ready']:
        raise FileNotFoundError('Prepare the immutable native cohort before ordinary requests: ' + status['reason'])
    manifest = _document(status['manifest_path'])
    facility, profile = parse_request(facility_dict, context['facility'], context['profile'])
    identity = _request_identity(context, status, facility, profile, facility_dict)
    output.mkdir(parents=True, exist_ok=True)
    if progress:
        progress('screen')
    filename = 'strict_compact.parquet' if facility.screening_mode.value == 'STRICT' else 'compact.parquet'
    compact = pd.read_parquet(context['cache'] / filename)
    carbon = pd.read_parquet(context['cache'] / 'carbon.parquet')
    geography = read_geoparquet(context['cache'] / 'geometry.parquet')
    cluster_execution = {}
    ranked, regions, membership, land = evaluate_prepared_cohort(compact, carbon, geography,
        facility, context['designs'], context['scenarios'], profile, progress=progress,
        execution_report=cluster_execution)
    del compact
    gc.collect()
    method_times = dict(global_evaluation_seconds=time.perf_counter()-started,
        clustering_execution=cluster_execution)
    hydrate_started = time.perf_counter()
    evidence, checks, rep_geo, rep_prov, representative_parts = _representatives(context, regions, ranked, facility, profile)
    method_times['representative_hydration_seconds'] = time.perf_counter()-hydrate_started
    definition = context['metadata']['grid_definition_id']
    selected_designs = [d for d in context['designs'] if d.design_id in set(ranked.design_id)]
    physical_schema = _physical_evidence(ranked, carbon, facility, selected_designs, context['scenarios'])
    weight_info = {key: ranked.attrs.get(key) for key in ('weights', 'weighting_method', 'ahp_result', 'ahp_template')}
    ranked.attrs = {}
    for table, name, schema in [(ranked, 'ranked_cells', 'CachedRegionalRankedDataset'),
            (membership, 'region_membership', 'RegionMembership'), (land, 'region_land_screening', 'RegionLandScreening'),
            (evidence, 'representative_evidence', 'RankedCellDataset'),
            (checks, 'representative_screening', 'ScreeningResult'),
            (rep_prov, 'representative_provenance', 'FeatureMetadata')]:
        version = '1.2.0' if name == 'representative_screening' else '1.1.0' if name in {
            'representative_evidence', 'representative_provenance'} else '1.0.0'
        _write(table, output / (name + '.parquet'), schema, definition, version=version)
    _write(regions, output / 'candidate_regions.parquet', 'CandidateRegion', definition, geo=True, version='1.3.0')
    _write(rep_geo, output / 'representative_geography.parquet', 'GeographicFeatureDataset', definition, geo=True, version='1.1.0')
    shutil.copyfile(context['cache'] / 'geometry.parquet', output / 'us_grid_dataset.parquet')
    shutil.copyfile(context['cache'] / 'screening_checks.parquet', output / 'screening_checks.parquet')
    shutil.copyfile(context['baseline'] / 'refinement_windows.parquet', output / 'refinement_windows.parquet')
    features = json.loads(regions.to_crs(4326).to_json(drop_id=True))['features'] if len(regions) else []
    _emit(output / 'candidate_regions.geojson', dict(type='FeatureCollection', features=features,
        dc_locator=dict(schema='CandidateRegion', schema_version='1.3.0', data_mode='real',
            grid_definition_id=definition, maximum_extent_km=20., interpretation=INTERPRETATION)))
    _emit(output / 'physical_schema.json', physical_schema)
    _emit(output / 'weight_result.json', weight_info)
    _emit(output / 'profile_snapshot.json', dict(status='PREDECLARED_BEFORE_CURRENT_RANKING',
        profile=profile.model_dump(mode='json'), resolved_profile_fingerprint=profile_fingerprint(profile)))
    _emit(output / 'screening_summary.json', dict(mode=facility.screening_mode.value,
        n_alternatives=len(ranked), n_eligible=int(ranked.eligible.sum()), n_conditional=int(ranked.conditional.sum()),
        n_hard_fail=int(ranked.hard_fail.sum()), n_critical_unknown=int(ranked.critical_unknown.sum()),
        land_search_scope='multi_cell_region', interpretation=INTERPRETATION,
        screening_reuse='Native outcomes reused only with identical threshold dependencies; representatives freshly screened.'))
    _emit(output / 'validation_report.json', dict(status='NOT_ASSESSED',
        sensitivity_status='NOT_ASSESSED', rank_ranges_status='NOT_ASSESSED',
        reason='Fast fixed-cohort re-evaluation does not repeat full diagnostic or sensitivity cases.',
        runtime_guards='Exact native annual identities, fixed-reference validation, global Pareto/ranks, native cluster/land guards, fresh representative native evidence.'))
    configuration = {**context['metadata']['configuration'], 'delivery_version': VERSION,
        'study_area': 'cached_regional_cohort', 'screening_mode': facility.screening_mode.value,
        'weighting_method': profile.weighting_method, 'user_group_weights': profile.user_weights,
        'validation': {'enabled': False}, 'facility_specification': facility.model_dump(mode='json')}
    _emit(output / 'config_snapshot.json', dict(run=configuration, facility=facility.model_dump(mode='json'),
        profile=profile.model_dump(mode='json'), submitted_facility=facility_dict,
        files=context['snapshot']['files'], baseline_path=str(context['baseline'])))
    scope = dict(kind='fixed_cached_national_regional_cohort', data_mode='real', evaluated_cells=len(geography),
        cell_size_m=1000, parent_windows=len(context['catalog']['parts']), maximum_region_extent_km=20.,
        coverage_warning='Fixed previously evaluated nationwide regional cohort; remaining national 1 km cells unassessed; parent selection not refreshed.')
    _emit(output / 'regional_catalog.json', dict(schema_version='1.1.0', analysis_level='regional',
        selection='fixed_cached_cohort', cell_size_m=1000, grid_definition_id=definition,
        refined_cells=len(geography), refined_parent_cells=len(context['catalog']['parts']),
        maximum_region_extent_km=20., land_search_scope='multi_cell_region',
        coverage_warning=scope['coverage_warning'], baseline_path=str(context['baseline']),
        parts=context['catalog']['parts'], representative_parts=representative_parts,
        parent_footprints_path='refinement_windows.parquet', representative_evidence_path='representative_evidence.parquet'))
    for row in regions.drop(columns='geometry').to_dict('records'):
        CandidateRegion.model_validate(clean(row))
    # Detect source-method/config edits across execution without rebinding outputs.
    final_context = _baseline_context(root, baseline)
    if final_context['identity'] != context['identity']:
        raise ValueError('Current methods/policies changed during fast execution')
    verify_cache(context['cache'], manifest)
    from dc_locator.model.enhanced import peak_working_set_bytes
    peak = peak_working_set_bytes()
    if peak is not None and peak >= 4 * 1024**3:
        raise ValueError('Fast execution exceeded the 4 GiB process memory budget')
    method_times['total_seconds'] = time.perf_counter()-started
    _emit(output / 'run_metadata.json', dict(schema_version='1.0.0', delivery_version=VERSION,
        run_id='cached_regional__' + identity[:16], stage_identity=identity, data_mode='real', scope=scope,
        geographic_cells=len(geography), grid_definition_id=definition, configuration=configuration,
        created_at_utc=datetime.now(timezone.utc).isoformat(), interpretation=INTERPRETATION,
        actual_working_code_sha256=context['methods'], guard_hashes=context['guard_hashes'],
        external_runner_sha256=file_digest(__file__),
        config_hashes=context['config_hashes'], environment=context['environment'],
        source_checksums=context['metadata']['source_checksums'],
        source_versions_and_access=context['metadata']['source_versions_and_access'],
        baseline_lineage=dict(path=str(context['baseline']), run_id=context['metadata']['run_id'],
            run_metadata_sha256=context['metadata_sha']),
        input_cache=dict(manifest_path=status['manifest_path'], manifest_sha256=status['manifest_sha256'],
            output_hashes=manifest['output_hashes'], cache_identity=context['identity'],
            baseline_run_id=context['metadata']['run_id']),
        observed_process_lifetime_peak_working_set_bytes=peak, timing=method_times,
        validation_status='NOT_ASSESSED', output_hashes={p.name:file_digest(p) for p in sorted(output.iterdir()) if p.is_file()},
        completed_current_stages=['screen', 'simulate', 'rank', 'cluster'], warnings=[scope['coverage_warning'],
            'Historical static carbon is not a future or marginal forecast.', 'Sensitivity and rank ranges are not assessed.']))
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--request', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--prepare-cache', action='store_true')
    args = parser.parse_args(argv)
    if args.prepare_cache:
        print(prepare_cached_cohort(args.root, args.baseline))
    else:
        if args.request is None or args.output is None:
            parser.error('--request and --output are required for evaluation')
        print(evaluate_cached_regions(args.root, args.baseline, _document(args.request), args.output,
            progress=lambda stage: print(stage, flush=True)))


if __name__ == '__main__':
    main()
