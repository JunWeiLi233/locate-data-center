"""Read-only, hash-bound presentation of saved decisions; no new ranking policy."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import yaml

from dc_locator.io import read_parquet, read_parquet_metadata
from dc_locator.model.metrics import clean
from dc_locator.paths import project_root
from dc_locator.reporting import INTERPRETATION

REQUIRED_TABLES = ('ranked_cells', 'site_performance', 'candidate_regions',
                   'us_grid_dataset', 'screening_results', 'feature_provenance')
REQUIRED_DOCUMENTS = ('profile_snapshot', 'weight_result', 'config_snapshot',
                      'source_coverage', 'validation_report')
OPTIONAL_ARTIFACTS = ('regional_catalog.json', 'lifecycle_results.parquet')
KEYS = ['grid_id', 'design_id', 'scenario_id']
PHYSICAL = {
    'e_it_mwh': 'MWh/year', 'e_facility_mwh': 'MWh/year',
    'c_electricity_tonnes': 'tonnes CO2e/year', 'w_site_m3': 'm3 consumed/year',
    'w_electricity_m3': 'm3 consumed/year', 'peak_facility_demand_mw': 'MW',
    'pue': 'annual ratio', 'wue_l_per_kwh': 'L consumed/IT kWh',
}
HEAT_GUIDE_URL = 'https://www.energy.gov/sites/default/files/2024-07/best-practice-guide-data-center-design.pdf'


def digest(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            checksum.update(block)
    return checksum.hexdigest()


def _object(value) -> dict:
    if value is None or (not isinstance(value, (dict, str)) and pd.isna(value)):
        return {}
    result = json.loads(value) if isinstance(value, str) else value
    if not isinstance(result, dict):
        raise ValueError('Expected an evidence object')
    return result


def _quantity(row: dict, metric: str, unit: str) -> dict:
    value = clean(row.get(metric))
    evidence = _object(row.get('metric_metadata_json')).get(metric, {})
    status = evidence.get('status') or ('unknown' if value is None else
        'scenario' if metric in {'pue', 'wue_l_per_kwh'} else 'calculated')
    if status == 'unknown' and value is not None:
        raise ValueError(f'UNKNOWN {metric} contains a non-null value')
    return dict(id=metric, value=value, unit=unit, status='unknown' if value is None else status,
                confidence='unknown' if value is None else evidence.get('confidence', 'low'),
                missing_reason=(evidence.get('missing_reason') or 'No compatible saved input was supplied')
                    if value is None else None,
                method=evidence.get('method'), source_evidence=evidence.get('source_evidence'))


def _unknown(metric: str, reason: str) -> dict:
    return dict(id=metric, value=None, status='unknown', confidence='unknown', missing_reason=reason)


def _roadmap(facility: dict) -> list[dict]:
    opening = facility.get('target_opening_year')
    lifetime = facility.get('operating_lifetime_years')
    end = opening + lifetime - 1 if opening is not None and lifetime is not None else None
    return [
        dict(period=f'Before {opening}' if opening else 'Before opening', label='Diligence and ecosystem design',
             actions=['Verify obtainable contiguous parcels, zoning and ecology with local records and surveys.',
                      'Obtain serving-utility capacity, connection timing, tariff and outage evidence; verify diverse fiber routes.',
                      'Compare contracted clean power, water supply and drought restrictions with complete system boundaries.',
                      'Engage residents, workforce partners and local authorities; document water, noise, land and ratepayer effects.',
                      'Request material quantities and product-specific EPDs; compare reuse of existing infrastructure.',
                      'Find a willing heat host and verify temperature, seasonal demand, pipe route, losses and auxiliary energy.'],
             evidence_gate='Project plan: unresolved critical requirements block construction commitment.'),
        dict(period=str(opening) if opening else 'Opening', label='Commission and measure',
             actions=['Commission independent power and cooling redundancy, including backup heat rejection when a heat host is unavailable.',
                      'Meter IT/facility energy, direct water consumption and withdrawal, and exported useful heat separately.',
                      'Validate design-day peak load, cooling performance and emergency operation against engineering tests.'],
             evidence_gate='Replace design assumptions with compatible commissioning evidence before claiming achieved benefits.'),
        dict(period=f'{opening}–{end}' if end is not None else 'Operating life', label='Operate, adapt and renew',
             actions=['Review annual PUE/WUE, electricity carbon, water source restrictions and supply contracts with consistent accounting boundaries.',
                      'Refresh hazard and climate evidence; test contingency operation and reassess expansion before committing additional capacity.',
                      'Evaluate efficient IT, modular cooling upgrades, heat reuse and flexible workloads against measured reliability constraints.',
                      'Record replacement inventories and emissions; publish measured local resource effects and respond to community concerns.'],
             evidence_gate='This is a proposed operating vision, not a grid/climate forecast or a fixed lifetime emissions estimate.'),
        dict(period=f'{end} and end of life' if end is not None else 'End of life', label='Reuse and accountable retirement',
             actions=['Assess continued safe reuse of equipment and buildings; document material recovery and waste handling.',
                      'Account for replacements, end-of-life activities, land restoration and remaining community obligations.'],
             evidence_gate='Close lifecycle accounting with real quantities and compatible product/process factors.'),
    ]


def _risk_action(requirement: str) -> str:
    token = requirement.lower()
    actions = [('power', 'Obtain a serving-utility study of capacity, connection timing and design-day peak load.'),
               ('fiber', 'Verify independent carrier routes, entry points, capacity and service agreements.'),
               ('water', 'Verify source-specific consumption/withdrawal, committed supply and drought restrictions.'),
               ('flood', 'Obtain current site-level flood maps and engineering clearance.'),
               ('wildfire', 'Obtain valid local wildfire exposure and protection evidence; do not substitute an incompatible proxy.'),
               ('land', 'Survey contiguous obtainable land, zoning and ecological clearance.'),
               ('parcel', 'Survey parcel boundaries, ownership, zoning and ecological clearance.'),
               ('ecolog', 'Verify protected habitats, permitting and local ecological impacts.'),
               ('peak', 'Verify peak electrical and thermal design performance under local design-day conditions.')]
    return next((action for key, action in actions if key in token),
                'Obtain compatible local evidence and independently verify this requirement before commitment.')


def assemble_submission_brief(metadata: dict, tables: dict[str, pd.DataFrame],
                              documents: dict, scenario_id: str | None = None) -> dict:
    """Present stored ranks and quantities in one explicitly selected external context."""
    ranked, performance, regions, geo, screening, provenance = (tables[name] for name in REQUIRED_TABLES)
    for label, frame in [('ranked', ranked), ('performance', performance)]:
        if frame.duplicated(KEYS).any():
            raise ValueError(f'Duplicate {label} alternative keys')
        if 'data_mode' in frame and set(frame.data_mode.dropna()) != {metadata['data_mode']}:
            raise ValueError('Table data mode disagrees with run metadata')
        if 'grid_definition_id' in frame and set(frame.grid_definition_id.dropna()) != {metadata['grid_definition_id']}:
            raise ValueError('Table grid identity disagrees with run metadata')
    scenarios = sorted(ranked.scenario_id.unique())
    if scenario_id is None:
        if len(scenarios) != 1:
            raise ValueError('Select an explicit scenario; the report never chooses an external scenario')
        scenario_id = scenarios[0]
    if scenario_id not in scenarios:
        raise ValueError(f'Unavailable scenario: {scenario_id}')
    selected = ranked.loc[ranked.scenario_id.eq(scenario_id)]
    selected_regions = regions.loc[regions.scenario_id.eq(scenario_id)] if len(regions) else regions
    if geo.grid_id.duplicated().any():
        raise ValueError('Duplicate geographic grid IDs')
    candidates = []
    for region in selected_regions.to_dict('records'):
        matches = selected.loc[selected.grid_id.eq(region['representative_grid_id']) & selected.design_id.eq(region['design_id'])]
        if len(matches) != 1:
            raise ValueError('Region representative does not match one saved ranked alternative')
        row = matches.iloc[0].to_dict()
        if not row['rankable'] or row['hard_fail'] or pd.isna(row['mcda_rank']):
            raise ValueError('A region representative is unranked or has a hard failure')
        candidates.append((row, region))
    candidates.sort(key=lambda pair: (pair[0]['mcda_rank'], pair[0]['grid_id'], pair[0]['design_id'], pair[0]['scenario_id']))
    chosen = candidates[0][0] if candidates else None
    assumption_row = chosen or (selected.iloc[0].to_dict() if len(selected) else {})
    assumptions = _object(assumption_row.get('assumptions_json'))
    facility = assumptions.get('facility', {})
    profile = documents['profile_snapshot']['profile']
    weights = documents['weight_result']['weights']
    contributions = _object(chosen.get('contribution_by_metric_json')) if chosen else {}
    criteria = []
    for metric in profile['metrics']:
        metric_id = metric['metric_id']
        criteria.append(dict(metric_id=metric_id, label=metric.get('definition', metric_id),
            unit=metric['unit'], direction=metric['direction'], weight=weights.get(metric_id),
            reference_low=metric.get('reference_low'), reference_high=metric.get('reference_high'),
            role=metric.get('role'), basis=metric.get('basis'), rationale=metric.get('rationale'),
            normalized_score=chosen.get(metric_id) if chosen else None,
            contribution=contributions.get(metric_id, chosen.get('contribution_'+metric_id)) if chosen else None))

    def representative(row, region):
        geographic_rows = geo.loc[geo.grid_id.eq(row['grid_id'])]
        if len(geographic_rows) != 1:
            raise ValueError('Missing unique representative geography')
        location = geographic_rows.iloc[0].to_dict()
        name = ', '.join(str(location[k]) for k in ['county_name_primary','state_abbr_primary']
                         if k in location and pd.notna(location[k])) or row['grid_id']
        return dict(status='CONDITIONAL_INVESTIGATION' if row.get('conditional') else 'QUALIFYING_INVESTIGATION',
            rationale='First investigation priority among exported region representatives in this scenario, using persisted MCDA ranks and declared preferences.',
            geographic_label=name+' (primary geographic overlap; evaluated cell may span multiple counties)',
            region_id=region['region_id'], grid_id=row['grid_id'], design_id=row['design_id'],
            scenario_id=scenario_id, rank=row['mcda_rank'], score=row['mcda_score'],pareto_status=row.get('pareto_status'),
            centroid=dict(lat=location.get('centroid_lat'),lon=location.get('centroid_lon')),
            region_centroid=dict(lat=region.get('centroid_lat'),lon=region.get('centroid_lon')),
            region_area_km2=region.get('total_area_km2'),region_cell_count=region.get('n_cells'),
            metrics=[_quantity(row, metric, unit) for metric, unit in PHYSICAL.items()])

    recommendation = representative(*candidates[0]) if candidates else dict(status='NO_QUALIFYING_REGION',
        rationale='No qualifying region was exported. STRICT excludes critical UNKNOWN evidence; no winner is invented.', metrics=[])
    alternatives, seen = [], {chosen['grid_id']} if chosen else set()
    for row, region in candidates[1:]:
        if row['grid_id'] not in seen:
            alternatives.append(representative(row, region)); seen.add(row['grid_id'])
        if len(alternatives) == 2:
            break
    cooling_comparisons = []
    if chosen:
        paired = performance.loc[performance.grid_id.eq(chosen['grid_id']) & performance.scenario_id.eq(scenario_id)]
        proposed = paired.loc[paired.design_id.eq(chosen['design_id'])]
        if len(proposed) != 1:
            raise ValueError('Recommended alternative lacks unique persisted performance')
        target = proposed.iloc[0].to_dict()
        for reference in paired.sort_values('design_id').to_dict('records'):
            if reference['design_id'] == chosen['design_id']:
                continue
            delta = {}
            metric_results = {}
            for metric in ['e_facility_mwh','c_electricity_tonnes','w_site_m3','w_electricity_m3']:
                first, second = _quantity(reference, metric, PHYSICAL[metric]), _quantity(target, metric, PHYSICAL[metric])
                delta[metric] = None if first['value'] is None or second['value'] is None else first['value']-second['value']
                metric_results[metric]=dict(value=delta[metric],unit=PHYSICAL[metric],
                    status='unknown' if delta[metric] is None else 'calculated',
                    confidence='unknown' if delta[metric] is None else 'low',
                    missing_reason='; '.join(str(q['missing_reason']) for q in [first,second] if q['value'] is None)
                        if delta[metric] is None else None)
            cooling_comparisons.append(dict(grid_id=chosen['grid_id'],scenario_id=scenario_id,
                reference_design_id=reference['design_id'],alternative_design_id=chosen['design_id'],
                reference_minus_alternative=delta,status='calculated',confidence='low',
                metric_results=metric_results,
                basis='Difference of saved paired annual scenarios at the same cell. A positive difference is a modeled reduction, not measured savings.'))
    risk_rows = screening.loc[screening.scenario_id.eq(scenario_id)]
    if chosen:
        risk_rows = risk_rows.loc[risk_rows.grid_id.eq(chosen['grid_id']) & risk_rows.design_id.eq(chosen['design_id'])]
    risk_columns = [k for k in ['requirement','outcome','missing_reason'] if k in risk_rows]
    risks = [dict(**row,action=_risk_action(row['requirement'])) for row in
             risk_rows[risk_columns].drop_duplicates().sort_values(risk_columns,na_position='last').to_dict('records')]
    coverage_document = documents['source_coverage']
    coverage = coverage_document.get('core', coverage_document).get('sources', {})
    source_versions = metadata.get('source_versions_and_access', {})
    sources = [dict(source_id=source_id,**{k:values.get(k) for k in
        ['implemented','acquired','analyzed','analyzed_cells','status']},
        **{k:source_versions.get(source_id,{}).get(k) for k in
        ['source_url','source_version','data_year','retrieved_at']}) for source_id,values in sorted(coverage.items())]
    cell_evidence = provenance.loc[provenance.grid_id.eq(chosen['grid_id'])].to_dict('records') if chosen and len(provenance) else []
    grid_path = documents['config_snapshot'].get('run',{}).get('grid_config')
    resolution = documents.get('regional_catalog',{}).get('cell_size_m')
    for path, content in documents['config_snapshot'].get('files',{}).items():
        if resolution is None and grid_path and str(path).replace('\\','/').endswith(grid_path.replace('\\','/')):
            resolution = yaml.safe_load(content).get('cell_size_m',resolution)
    unknowns = [_unknown(metric,reason) for metric,reason in [
        ('total_water_consumption_m3','Electricity-generation consumption remains unavailable; direct and indirect boundaries cannot be summed.'),
        ('total_lifecycle_co2e_tonnes','No complete matching construction, equipment, replacement and end-of-life inventory/factor accounting is available.'),
        ('useful_heat_mwh','No matched heat consumer, temperature, recoverable fraction, distribution-loss and demand inputs were supplied.'),
        ('heat_reuse_avoided_co2e_tonnes','No displaced heating baseline and auxiliary-energy accounting were supplied.'),
        ('construction_resource_benefit','No real bill of materials or product-specific EPD comparison was supplied.'),
        ('community_economic_benefit','No verified workforce, tariff, capital/operating cost, local impact or benefit agreement was supplied.')]]
    if chosen:
        site, upstream = (_quantity(chosen,k,PHYSICAL[k])['value'] for k in ['w_site_m3','w_electricity_m3'])
        if site is not None and upstream is not None:
            unknowns = [item for item in unknowns if item['id']!='total_water_consumption_m3']
    validation = documents['validation_report']
    return clean(dict(schema_version='1.0.0',run_id=metadata['run_id'],data_mode=metadata['data_mode'],
        scenario_id=scenario_id,interpretation=INTERPRETATION,scope=metadata.get('study_area', 'recorded run scope'),
        analyzed_cell_count=metadata.get('geographic_cells',len(geo)),resolution_m=resolution,facility=facility,
        recommendation=recommendation,alternatives=alternatives,
        framework=dict(profile_id=profile['profile_id'],weighting_method=documents['weight_result'].get('weighting_method'),
            criteria=criteria,excluded_criteria=profile.get('excluded_criteria',[]),
            missing_data_policy='Hard failures cannot be compensated. UNKNOWN is neither zero nor PASS. Required missing metrics remain UNRANKED with no candidate-specific weight redistribution.',
            method='Hard screening → paired annual physics → fixed clipped linear normalization → separate-scenario Pareto analysis → declared weighted sum → adjacent search regions. Ranking is copied from saved outputs.'),
        evidence=dict(sources=sources,representative_provenance=cell_evidence,
            assumptions=[f'{key}: {value.get("basis", "recorded input")}; {value.get("rationale", "See saved configuration")}'
                for key,value in assumptions.items() if isinstance(value,dict)],
            input_hashes=metadata.get('output_hashes',{}),config_hashes=metadata.get('config_hashes',{}),
            source_checksums=metadata.get('source_checksums',{}),archived_code_hashes=metadata.get('actual_working_code_sha256',{})),
        impact=dict(cooling_comparisons=cooling_comparisons,unknowns=unknowns,
            total_water_consumption_m3=(site+upstream if site is not None and upstream is not None else None) if chosen else None,
            total_water_consumption=dict(id='total_water_consumption_m3',
                value=(site+upstream if site is not None and upstream is not None else None) if chosen else None,
                unit='m3 consumed/year',status='calculated' if chosen and site is not None and upstream is not None else 'unknown',
                confidence='low' if chosen and site is not None and upstream is not None else 'unknown',
                missing_reason=None if chosen and site is not None and upstream is not None else
                    'Both direct and electricity-generation consumption must be available with compatible boundaries.'),
            boundary='Annual electricity CO2e uses an explicit historical-static scenario. Ideal dry cooling water excludes sanitary/construction water. Deltas preserve one cell/design/scenario pair. No annual result is multiplied into an unsupported 25-year forecast.',
            heat_reuse_reference=dict(url=HEAT_GUIDE_URL,section='7.1, printed page 28',
                basis='Design guidance only; no numerical coefficient or confirmed local heat host inferred.')),
        risks=risks,implementation_vision=_roadmap(facility),
        limitations=['Search areas and representative centroids require parcel investigation; no buildability or national optimum is established.',
            'Finer analytical grids do not improve native source accuracy; the saved scope and grid remain authoritative.',
            'Transmission proximity is a proxy, not available utility capacity; basin stress is not committed water; mapped broadband is not diverse fiber.',
            'Climate/hazard, future clean power, heat reuse, embodied impacts and community economics are not silently inserted into the scored profile.',
            f'Independent physical validation: {validation.get("external_validation",{}).get("status", "UNAVAILABLE")}; overall accuracy: UNKNOWN.',
            'Operating vision is a proposed project plan. Numeric benefits are scenario calculations, not commissioned performance.']))


def build_submission_brief(run_path: Path | str, scenario_id: str | None = None) -> dict:
    """Read verified archived artifacts without revalidating their science as current code."""
    root = project_root().resolve()
    path = Path(run_path).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Saved run must be inside the project')
    metadata_path = path/'run_metadata.json'
    metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
    scope = metadata.get('scope', {})
    if isinstance(scope, dict):
        metadata = {**metadata, **{key:metadata.get(key,scope.get(key)) for key in
                    ['data_mode','grid_definition_id','geographic_cells']},
                    'study_area':metadata.get('study_area',scope.get('scope'))}
    if not {'rank','cluster','validate'}.issubset(metadata.get('completed_current_stages', [])):
        raise ValueError('A completed ranked, clustered and validated saved run is required')
    hashes = metadata.get('output_hashes',{})
    regional = (path/'regional_catalog.json').is_file()
    root_tables = ('ranked_cells','candidate_regions') if regional else REQUIRED_TABLES
    names = [name+'.parquet' for name in root_tables]+[name+'.json' for name in REQUIRED_DOCUMENTS]
    names += [name for name in OPTIONAL_ARTIFACTS if (path/name).is_file()]
    input_hashes = {'run_metadata.json':digest(metadata_path)}
    def verify(name):
        artifact = (path/name).resolve()
        if not artifact.is_relative_to(path):
            raise ValueError('Artifact escapes the saved run')
        if name not in hashes or digest(artifact)!=hashes[name]:
            raise ValueError(f'Saved output checksum/hash mismatch: {name}')
        input_hashes[name]=hashes[name]
        if name.endswith('.parquet'):
            file_meta = read_parquet_metadata(artifact)
            if file_meta.get('data_mode')!=metadata['data_mode'] or file_meta.get('grid_definition_id')!=metadata['grid_definition_id']:
                raise ValueError(f'Saved table data mode/grid identity mismatch: {name}')
        return artifact
    for name in names:verify(name)
    tables = {name:read_parquet(path/(name+'.parquet')) for name in root_tables}
    documents = {name:json.loads((path/(name+'.json')).read_text(encoding='utf-8')) for name in REQUIRED_DOCUMENTS}
    if 'regional_catalog.json' in names:
        catalog=json.loads((path/'regional_catalog.json').read_text(encoding='utf-8'))
        documents['regional_catalog']=catalog
        ranked=tables['ranked_cells']
        scenarios=sorted(ranked.scenario_id.unique())
        if scenario_id is None and len(scenarios)!=1:
            raise ValueError('Select an explicit scenario; the report never chooses an external scenario')
        scenario_id=scenario_id or scenarios[0]
        if scenario_id not in scenarios:raise ValueError(f'Unavailable scenario: {scenario_id}')
        regions=tables['candidate_regions']
        choices=regions.loc[regions.scenario_id.eq(scenario_id)].merge(
            ranked[KEYS+['mcda_rank']],left_on=['representative_grid_id','design_id','scenario_id'],
            right_on=KEYS,validate='many_to_one')
        choices=choices.sort_values(['mcda_rank','grid_id','design_id','scenario_id'])
        selected_ids=choices.drop_duplicates('grid_id').head(3).grid_id.tolist()
        if not selected_ids and len(ranked):selected_ids=[ranked.iloc[0].grid_id]
        selected_parts=sorted({catalog['representative_parts'][grid_id] for grid_id in selected_ids
                               if grid_id in catalog['representative_parts']})
        if not selected_parts and catalog.get('parts'):selected_parts=[catalog['parts'][0]['path']]
        accumulators={name:[] for name in REQUIRED_TABLES if name!='candidate_regions'}
        for part_name in selected_parts:
            for table_name in accumulators:
                relative=(Path(part_name)/(table_name+'.parquet')).as_posix()
                artifact=verify(relative)
                frame=read_parquet(artifact)
                if len(frame):frame=frame.loc[frame.grid_id.isin(selected_ids)]
                accumulators[table_name].append(frame)
        for table_name,frames in accumulators.items():
            tables[table_name]=pd.concat(frames,ignore_index=True) if frames else pd.DataFrame(columns=KEYS)
        # Part ranked tables contain reconciled global ranks and full physical evidence.
        part_ranked=tables['ranked_cells']
        if len(part_ranked):
            comparison=part_ranked[KEYS+['mcda_rank','mcda_score']].merge(
                ranked[KEYS+['mcda_rank','mcda_score']],on=KEYS,suffixes=('_part','_global'),validate='one_to_one')
            if len(comparison)!=len(part_ranked) or any(not (
                comparison[key+'_part'].eq(comparison[key+'_global']) |
                (comparison[key+'_part'].isna() & comparison[key+'_global'].isna())).all()
                for key in ['mcda_rank','mcda_score']):
                raise ValueError('Regional part ranks/scores do not match the complete global universe')
        tables['candidate_regions']=regions.loc[regions.representative_grid_id.isin(selected_ids)]
        metadata['geographic_cells']=catalog.get('refined_cells',metadata.get('geographic_cells'))
    brief=assemble_submission_brief(metadata,tables,documents,scenario_id)
    if regional and documents['regional_catalog'].get('coverage_warning'):
        brief['limitations'].append(documents['regional_catalog']['coverage_warning'])
    brief['evidence']['input_hashes']=input_hashes
    brief['evidence']['saved_run_path']=path.relative_to(root).as_posix()
    return brief


def write_submission(run_path: Path | str, output: Path | str, scenario_id: str | None = None,
                     heat_reuse_input: Path | str | None = None) -> Path:
    """Write a new presentation run; never overwrite model evidence or existing folders."""
    root=project_root().resolve()
    target=Path(output).resolve()
    source=Path(run_path).resolve()
    if target.exists():
        raise ValueError('Submission output already exists; use a new folder')
    if not (target.is_relative_to(root/'runs') or target.is_relative_to(root/'.pytest-work')) or target.is_relative_to(source):
        raise ValueError('Submission output must be a new owned runs/ or .pytest-work/ folder')
    relative=target.relative_to(root)
    if relative.parts[0]=='runs' and (len(relative.parts)<2 or relative.parts[1].startswith(('phase','orchestrator_')) or relative.parts[1]=='example'):
        raise ValueError('Accepted evidence folders are protected')
    brief=build_submission_brief(source,scenario_id)
    if heat_reuse_input:
        from dc_locator.model.heat_reuse import evaluate_heat_reuse, HeatReuseInputs
        heat_path=Path(heat_reuse_input).resolve()
        if not heat_path.is_relative_to(root):
            raise ValueError('Heat input must stay inside the project')
        heat=HeatReuseInputs.model_validate_json(heat_path.read_text(encoding='utf-8'))
        recommendation=brief['recommendation']
        if any(getattr(heat,key)!=recommendation.get(key) for key in KEYS):
            raise ValueError('Heat reuse inputs must match the recommended saved alternative')
        quantities={metric['id']:metric['value'] for metric in recommendation['metrics']}
        brief['impact']['heat_reuse_scenario']=evaluate_heat_reuse(quantities.get('e_it_mwh'),heat)
        heat_quantities=brief['impact']['heat_reuse_scenario']
        for metric,key in [('useful_heat_mwh','delivered_heat_mwh'),
                           ('heat_reuse_avoided_co2e_tonnes','net_heating_system_avoided_co2e_tonnes')]:
            quantity=heat_quantities[key]
            if quantity['value'] is not None:
                brief['impact']['unknowns']=[item for item in brief['impact']['unknowns'] if item['id']!=metric]
            else:
                for item in brief['impact']['unknowns']:
                    if item['id']==metric:item['missing_reason']=quantity['missing_reason']
        brief['evidence']['input_hashes'][heat_path.relative_to(root).as_posix()]=digest(heat_path)
    from dc_locator.submission_rendering import render_html, render_markdown
    rendered={'submission_brief.json':json.dumps(brief,indent=2,sort_keys=True,allow_nan=False)+'\n',
              'submission_brief.md':render_markdown(brief),'submission_brief.html':render_html(brief)}
    target.mkdir(parents=True)
    for name,content in rendered.items():
        (target/name).write_text(content,encoding='utf-8')
    manifest=dict(schema_version='1.0.0',delivery_version='submission_alignment_v1',data_mode=brief['data_mode'],
        source_run_id=brief['run_id'],source_run_path=source.relative_to(root).as_posix(),scenario_id=brief['scenario_id'],
        input_hashes=brief['evidence']['input_hashes'],presentation_code_hashes={
            name:digest(root/'src'/'dc_locator'/name) for name in ['submission.py','submission_rendering.py','model/heat_reuse.py']
            if (root/'src'/'dc_locator'/name).is_file()},
        output_hashes={name:digest(target/name) for name in rendered},interpretation=INTERPRETATION,
        scientific_status='Presentation of verified archived outputs; no new ranking or independent scientific validation.')
    (target/'run_metadata.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    return target
