"""Delivery metadata and evidence-based search-area reports."""
from __future__ import annotations

import json
import subprocess
import uuid
from datetime import datetime,timezone

import pandas as pd

from dc_locator.geography.sources.ingestion import file_digest
from dc_locator.model.enhanced import peak_working_set_bytes
from dc_locator.model.metrics import clean


INTERPRETATION='These geographic regions deserve further investigation under the stated facility requirements, datasets, constraints, assumptions, and decision preferences.'


def scope_warning(pipeline):
    """Keep legacy bytes while describing the additive national revision honestly."""
    if pipeline.config.schema_version=='2.0.0':
        return 'Development subset only; national feature/model execution is unsupported'
    if pipeline.config.data_mode.value=='synthetic':
        return 'Explicit synthetic software fixture; no geographic discovery evidence'
    if pipeline.config.study_area.lower() in {'conus','national'}:
        return 'CONUS discovery on the declared grid resolution; inspect per-metric source coverage and UNKNOWN evidence before local investigation'
    return f'Declared analysis scope: {pipeline.config.study_area}; inspect per-metric source coverage'


def resource_diagnostics(root):
    """Observe current project cache totals; these never enter model/cache identity."""
    return {'scope':'current project cache, measured for this execution including cached-stage runs',
        'raw_total_bytes_including_manifests':sum(p.stat().st_size for p in (root/'data/raw').rglob('*') if p.is_file()),
        'interim_total_bytes_including_extracted_copies':sum(p.stat().st_size for p in (root/'data/interim').rglob('*') if p.is_file())}


def run_metadata(pipeline,stage):
    try:
        base=subprocess.run(['git','rev-parse','HEAD'],cwd=pipeline.root,capture_output=True,text=True,check=True).stdout.strip()
    except (OSError,subprocess.CalledProcessError):base=None
    stages={path.stem:json.loads(path.read_text(encoding='utf-8')) for path in sorted((pipeline.output/'stage_manifests').glob('*.json'))}
    current={name:value for name,value in stages.items() if value.get('stage_identity')==pipeline.identity}
    reports={}
    for name in ('screening_summary','validation_report','source_coverage'):
        path=pipeline.output/(name+'.json')
        if path.exists():reports[name]=json.loads(path.read_text(encoding='utf-8'))
    phase_records={}
    for number in range(1,7):
        path=pipeline.root/f'docs/phase_records/phase_{number}.json'
        record=json.loads(path.read_text(encoding='utf-8'))
        phase_records[str(number)]={'record_sha256':file_digest(path),'status':record.get('status','accepted'),'evidence_scope':'historical accepted revision; not current-run validation'}
    delivery_acceptance={'status':'awaiting_root_acceptance','revision':pipeline.config.delivery_version}
    accepted=pipeline.root/'docs/phase_records/phase_7.json'
    if accepted.exists():
        record=json.loads(accepted.read_text(encoding='utf-8'))
        if record.get('status')=='accepted' and record.get('delivery_version')==pipeline.config.delivery_version and record.get('code_hashes')==pipeline.model_hashes:
            delivery_acceptance={'status':'accepted','revision':pipeline.config.delivery_version,'record_sha256':file_digest(accepted)}
        else:delivery_acceptance['canonical_record_status']='stale_for_current_working_code'
    output_hashes={str(p.relative_to(pipeline.output).as_posix()):file_digest(p) for p in sorted(pipeline.output.rglob('*'))
        if p.is_file() and p.name!='run_metadata.json' and 'geography_core' not in p.parts}
    return {'schema_version':'2.0.0','delivery_version':pipeline.config.delivery_version,'run_id':pipeline.run_id,
        'execution_id':str(uuid.uuid4()),'created_at_utc':datetime.now(timezone.utc).isoformat(),'requested_stage':stage,
        'actual_working_code_sha256':pipeline.model_hashes,'git_base_commit':base,
        'git_base_is_working_code_proof':False,'stage_identity':pipeline.identity,'config_hashes':pipeline.config_hashes,
        'configuration':pipeline.config.model_dump(mode='json'),'source_checksums':pipeline.source_hashes,
        'source_versions_and_access':pipeline.source_document.get('declared_sources',{}),'environment':pipeline.environment,
        'scope':pipeline.scope,'random_seed':pipeline.config.random_seed,'completed_current_stages':sorted(current),
        'configured_grid':{'path':str(pipeline.path(pipeline.config.grid_path)),'sha256':pipeline.config_hashes[str(pipeline.path(pipeline.config.grid_path))]},
        'phase_completion':{**phase_records,'7':delivery_acceptance},
        'source_coverage_and_checks':reports,'output_hashes':output_hashes,'cache_hits':sorted(set(pipeline.cache_hits)),
        'observed_process_lifetime_peak_working_set_bytes':peak_working_set_bytes(),
        'resource_diagnostics':resource_diagnostics(pipeline.root),
        'determinism':{'substantive_outputs':'Identical current model/config/source/grid/environment inputs produce identical bytes',
            'intentional_execution_metadata':['run_metadata.json','stage_manifests/* execution diagnostics','geography_core/coverage_report.json and data_manifest.json diagnostics']},
        'warnings':[scope_warning(pipeline),
            'STRICT critical UNKNOWN produces no accepted ranking; exploratory rankings remain conditional',
            'Constant annual PUE/WUE and historical-static electricity factor are declared scenarios, not forecasts',
            'Native future water contexts are separate; unsupported2040 is UNKNOWN, NASA context is independent',
            'Search regions are not approved parcels; geographic proximity does not establish supply capacity',
            'No compatible independent physical validation or overall accuracy estimate is available'],
        'blockers':['Parcel/contiguous-land/power/water/fiber evidence unresolved','WRC source packing/mask unresolved',
            'NSRDB unacquired; CWNS/GEM/EC3 access or native exports unavailable; FCC/RAPT/FAF integration incomplete'],
        'interpretation':INTERPRETATION}


def recommendation_report(pipeline,baseline,validation,contexts,*,profile_override=None,external_context=None):
    g,p=pipeline.geography();ranked=baseline['ranked_cells'];regions=baseline['candidate_regions']
    profile=profile_override or pipeline.profile()
    facility,_,_,_=pipeline.inputs()
    lines=['# Potential-region investigation report','',INTERPRETATION,'',
        'Region geometries are search areas. An actual evaluated representative cell/design is reported; no centroid or parcel is approved.',
        '',f'Delivery revision: `{pipeline.config.delivery_version}`. Stable analysis ID: `{pipeline.run_id}`.',
        f'Scope: **{pipeline.config.study_area}**, {len(g)} real cells.' if pipeline.config.data_mode.value=='real' else f'Scope: **explicit synthetic software fixture**, {len(g)} cells.',
        f'Screening: **{pipeline.config.screening_mode}**. {len(ranked)} diagnostic alternatives; {int(ranked.rankable.sum())} rankable; {len(regions)} candidate regions.',
        '',f"Ranking basis: `{profile.profile_id}`; fixed criterion bounds, declared parent/local weights and clipping are in `profile_snapshot.json`. Every contribution is exported. External scenarios are evaluated separately.",
        f'Modeled annual physical period: opening year {facility.target_opening_year}, {facility.hours_in_modeled_year} configured hours. Annual PUE is a constant scenario and does not verify peak demand.']
    method=baseline['weighting_method']
    ahp_status=sorted(set(ranked.ahp_status)) if len(ranked) else []
    lines += [f'Actual weighting method: **{method}**; AHP status: {", ".join(ahp_status) or "not evaluated"}. Requested method: {profile.weighting_method}. Unsupplied AHP judgments use equal baseline and an empty elicitation template; no expert judgments are generated.',
        'Alternative decision statuses: '+json.dumps(ranked.rank_status.value_counts().sort_index().to_dict(),sort_keys=True)+'.']
    if external_context is not None:
        lines += ['',f'External source context: `{external_context.scenario_id}`; pathway {external_context.pathway}; {external_context.ssp_rcp}; native window {external_context.window_start_year}–{external_context.window_end_year}; supported={external_context.supported}. This source window is not an individual operating year.']
    if regions.empty:
        lines+=['','No candidate region qualifies under this configuration. The decision-status counts above explain strict UNKNOWN, required missing metrics or weight-review exclusions. Unknown evidence is retained; no winner is invented.']
    physical=['e_it_mwh','e_facility_mwh','c_electricity_kg','c_electricity_tonnes','w_site_m3','w_electricity_m3','pue','wue_l_per_kwh']
    for region in regions.itertuples():
        rep=json.loads(region.representative_json)
        lines+=['',f'## Search region {region.region_id}','',
            f'Actual representative: `{region.representative_grid_id}` / `{region.design_id}` / `{region.scenario_id}`.',
            f'{region.n_cells} cells; {region.total_area_km2:.3f} km² study intersection; {region.suitable_land_area_km2:.3f} km² suitable-land proxy. This does not establish contiguous, obtainable or buildable land.',
            f"Screening status: {rep.get('rank_status')}; conditional={rep.get('conditional')}; critical UNKNOWN={rep.get('critical_unknown')}; hard failure={rep.get('hard_fail')}. Pareto: {rep.get('pareto_status')}. Score: {rep.get('mcda_score')}; scenario rank: {rep.get('mcda_rank')}.",
            '', '| Annual physical quantity | Unit | Value |','|---|---|---:|']
        units={'e_it_mwh':'MWh/year','e_facility_mwh':'MWh/year','c_electricity_kg':'kg CO2e/year','c_electricity_tonnes':'tonnes CO2e/year','w_site_m3':'m³ consumed/year','w_electricity_m3':'m³ consumed/year','pue':'ratio, annual scenario','wue_l_per_kwh':'L consumed/IT kWh'}
        lines += [f'| {name} | {units[name]} | {rep.get(name) if rep.get(name) is not None else "UNKNOWN"} |' for name in physical]
        lines.append(f'| peak_facility_demand_mw | MW, verified design-day demand | {rep.get("peak_facility_demand_mw") if rep.get("peak_facility_demand_mw") is not None else "UNKNOWN"} |')
        contributions=json.loads(rep.get('contribution_by_metric_json','{}'))
        lines+=['','| Criterion | Raw quantity | Score 0–100 | Weighted contribution |','|---|---:|---:|---:|']
        for metric in profile.metrics:
            lines.append(f'| {metric.metric_id} ({metric.unit}) | {rep.get("raw_"+metric.metric_id)} | {rep.get(metric.metric_id)} | {contributions.get(metric.metric_id)} |')
        evidence=p.loc[p.grid_id.eq(region.representative_grid_id)]
        lines+=['','Source dates and coverage for the representative are recorded below; complete metric evidence remains in feature_provenance.parquet.','',
            '| Source | Source period/year | Retrieval UTC | Known metric rows | Coverage range |','|---|---|---|---:|---|']
        for source,rows in evidence.groupby('source_id',sort=True):
            known=rows.value.notna()|rows.value_text.notna();cover=rows.coverage_frac.dropna()
            dates='; '.join(sorted(set(rows.data_year.dropna().astype(str))))
            retrieved='; '.join(sorted(set(rows.retrieved_at.dropna().astype(str))))
            lines.append(f'| {source} | {dates} | {retrieved} | {int(known.sum())}/{len(rows)} | {cover.min():.6g}–{cover.max():.6g} |' if len(cover) else f'| {source} | {dates} | {retrieved} | {int(known.sum())}/{len(rows)} | not an areal coverage metric |')
        unknown=evidence.loc[evidence.status.eq('unknown'),['metric','missing_reason']]
        lines+=['','Important unavailable metrics: '+('; '.join(f'{row.metric}: {row.missing_reason}' for row in unknown.itertuples()) or 'none in source table; parcel requirements still need separate review'),
            '', 'Member distributions and actual membership are exported in candidate_regions.geojson and region_membership.parquet. Required local verification: parcel rights/contiguous usable land; flood/fire engineering; utility connection and available capacity; water commitment and permits; diverse fiber; cooling design-day demand; product-specific inventories and lifecycle boundaries.',
            '', 'Sensitivity for this fixed baseline region:']
        if external_context is not None:
            lines.append('This future search region is not a fixed baseline region; no matched-region stability claim is available. Current case-wide and corresponding grid/design sensitivity are in sensitivity_results.parquet, robustness_summary.csv and alternative_rank_ranges.parquet.')
            continue
        fixed=validation.fixed_region_summary
        selected=fixed.loc[fixed.region_id.eq(region.region_id)] if 'region_id' in fixed else pd.DataFrame()
        if len(selected):
            names=[name for name in selected.columns if name not in {'case_metadata_json','region_id','grid_definition_id','facility_id','validation_id','validation_revision'}]
            lines += ['| '+' | '.join(names)+' |','| '+' | '.join('---' for _ in names)+' |']
            lines += ['| '+' | '.join(str(clean(row[name])) for name in names)+' |' for row in selected.to_dict('records')]
        else:lines.append('No configured comparable fixed-member cases; no stability claim.')
    lines+=['','## Separate external contexts','', '| Context | Supported native window | Rankable | Regions |','|---|---|---:|---:|']
    context_links=[]
    for c in contexts:
        s=c['external_scenario'];result=c['result']
        lines.append(f'| {c["case_id"]} | {str(s.window_start_year)+"–"+str(s.window_end_year) if s.supported else "UNKNOWN; no interpolation"} | {int(result["ranked_cells"].rankable.sum())} | {len(result["candidate_regions"])} |')
        target=pipeline.output/'future_contexts'/c['case_id']/'recommendation_report.md'
        target.write_text(recommendation_report(pipeline,result,validation,[],profile_override=c['profile'],external_context=s),encoding='utf-8')
        context_links.append(f'- [{c["case_id"]}: representatives, contributions, source coverage and verification requirements](future_contexts/{c["case_id"]}/recommendation_report.md).')
    lines+=['']+context_links
    lines+=['','NASA model/member/SSP/year context is independent; it does not modify PUE/WUE or attach to every water pathway. Annual historical electricity reuse is an explicit constant scenario, not a future-grid forecast. Unknown construction/equipment/replacement/end-of-life components keep total lifecycle emissions UNKNOWN.',
        '', '## Current-run validation and limits','',
        'validation_report.json and validation_report.md bind this facility, profile, source/config hashes and working model revision. Phase 6 freeze/results are preserved historical evidence and do not prove the current delivery code is an untouched holdout model.',
        '', 'Sensitivity results show responses to stated assumptions and preferences. No independent compatible facility measurements are available, so no overall physical accuracy or nationally optimal site is claimed. '+('National model coverage/runtime remains unsupported.' if pipeline.config.schema_version=='2.0.0' else scope_warning(pipeline)+'.'),'']
    return '\n'.join(lines)
