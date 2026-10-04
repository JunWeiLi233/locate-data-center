"""Deterministic, escaped submission documents for six mission deliverables."""
from __future__ import annotations

from html import escape
import re


def _value(value):
    if value is None:return 'UNKNOWN'
    if isinstance(value,float):return format(value,',.6g')
    return str(value)


def _sections(brief: dict) -> list[tuple[str,list[str],list[tuple[list[str],list[list]]]]]:
    recommendation=brief['recommendation']
    selected=[recommendation]+brief['alternatives'] if recommendation.get('grid_id') else []
    locations=[[row['geographic_label'],row['grid_id'],row['design_id'],row['rank'],row['score'],
                f'{row["centroid"]["lat"]}, {row["centroid"]["lon"]}'] for row in selected]
    criteria=[[row['metric_id'],row['weight'],row['direction'],
               f'{row["reference_low"]}–{row["reference_high"]} {row["unit"]}',
               row['normalized_score'],row['contribution']] for row in brief['framework']['criteria']]
    sources=[[row['source_id'],row['implemented'],row['acquired'],row['analyzed'],row['analyzed_cells'],
              row['status'],row['data_year'],row['source_url']] for row in brief['evidence']['sources']]
    metrics=[[metric['id'],metric['value'],metric['unit'],metric['status'],metric['confidence'],metric['missing_reason']]
             for metric in recommendation['metrics']]
    total=brief['impact']['total_water_consumption']
    metrics.append([total['id'],total['value'],total['unit'],total['status'],total['confidence'],total['missing_reason']])
    comparison_metrics=['e_facility_mwh','c_electricity_tonnes','w_site_m3','w_electricity_m3']
    comparisons=[[row['reference_design_id'],row['alternative_design_id']]+[
        row['reference_minus_alternative'][metric] for metric in comparison_metrics]
        for row in brief['impact']['cooling_comparisons']]
    unknowns=[[row['id'],row['value'],row['missing_reason']] for row in brief['impact']['unknowns']]
    risks=[[row['requirement'],row['outcome'],row['missing_reason'],row['action']] for row in brief['risks']]
    vision=[[row['period'],row['label'],' '.join(row['actions']),row['evidence_gate']] for row in brief['implementation_vision']]
    geography=[recommendation['rationale'],brief['interpretation'],
               f'Analysis scope: {brief["scope"]}; {brief["analyzed_cell_count"]} cells; resolution {_value(brief["resolution_m"])} m. External context: {brief["scenario_id"]}.']
    if recommendation.get('grid_id'):
        geography.append(f'The recommended representative is a cell, not an approved parcel. Its separate connected search-region center is {recommendation["region_centroid"]}; '
                         f'the region contains {recommendation["region_cell_count"]} cells and {_value(recommendation["region_area_km2"])} km2. The cell center and region center serve different purposes.')
    impact_prose=[brief['impact']['boundary'],'Cooling comparison: reference minus recommended design at the same cell and scenario; positive differences are modeled reductions. Energy: MWh/year; carbon: tonnes CO2e/year; water: m3 consumed/year.',
                  'Heat-host design guidance: DOE/FEMP 2024, section 7.1, printed page 28. '+brief['impact']['heat_reuse_reference']['url']]
    heat=brief['impact'].get('heat_reuse_scenario')
    if heat:
        impact_prose += [heat['boundary']]
        metrics += [[key,heat[key]['value'],heat[key]['unit'],heat[key]['status'],heat[key]['confidence'],heat[key]['missing_reason']]
                    for key in ['available_heat_after_losses_mwh','delivered_heat_mwh','net_heating_system_avoided_co2e_tonnes']]
    return [
        ('1. Recommended geographic investigation',geography,[(['Geographic overlap','Cell','Design','Stored rank','Stored score','Cell center lat/lon'],locations)]),
        ('2. Decision framework and weighting',[brief['framework']['method'],brief['framework']['missing_data_policy'],
            f'Archived profile: {brief["framework"]["profile_id"]}; weighting method: {brief["framework"]["weighting_method"]}. Bounds and preference weights are declared policy, not regulatory facts.',
            'Excluded criteria: '+', '.join(item['criterion'] for item in brief['framework']['excluded_criteria'])],
            [(['Criterion','Leaf weight','Direction','Fixed reference bounds','Stored normalized score','Stored contribution'],criteria)]),
        ('3. Data analysis and assumptions',brief['evidence']['assumptions']+
            ['Source coverage distinguishes implementation, acquisition and analysis. Complete representative metric provenance, retrieval dates and checksums are retained in submission_brief.json.'],
            [(['Source','Implemented','Acquired','Analyzed','Cells','Status','Period','Official URL'],sources)]),
        ('4. Sustainability impact assessment',impact_prose,
            [(['Quantity','Value','Unit','Status','Confidence','Missing reason'],metrics),
             (['Reference design','Recommended design','Electricity difference','Carbon difference','Onsite consumption difference','Generation consumption difference'],comparisons),
             (['Unresolved impact','Value','Missing evidence'],unknowns)]),
        ('5. Environmental and operational risks',brief['limitations'],
            [(['Requirement','Recorded outcome','Missing reason','Next evidence/action'],risks)]),
        ('6. Implementation vision',[f'Proposed plan: opening {_value(brief["facility"].get("target_opening_year"))}; '
            f'{_value(brief["facility"].get("operating_lifetime_years"))}-year operation. Local commitments, engineering tests and measured outcomes are required.'],
            [(['Period','Workstream','Proposed actions','Evidence gate'],vision)]),
    ]


def render_markdown(brief: dict) -> str:
    def cell(value):
        return re.sub(r'([\\`*_{}\[\]()#+.!|>~-])',r'\\\1',escape(_value(value),quote=False)).replace('\n',' ')
    lines=['# Where should the next sustainable AI data center be investigated?','',
        '**DEMO DATA — synthetic software fixture**' if brief['data_mode']=='synthetic' else '**Evidence-based conditional investigation brief**',
        '',f'Saved run: {cell(brief["run_id"])} · scenario: {cell(brief["scenario_id"])}','']
    for heading,paragraphs,tables in _sections(brief):
        lines += ['## '+heading,'']
        for paragraph in paragraphs:lines += [cell(paragraph),'']
        for headers,rows in tables:
            if not rows:continue
            lines += ['| '+' | '.join(headers)+' |','| '+' | '.join('---' for _ in headers)+' |']
            lines += ['| '+' | '.join(cell(value) for value in row)+' |' for row in rows]
            lines += ['']
    lines += ['All claims are bound to the saved run. See `submission_brief.json` and `run_metadata.json` for exact input hashes and the presentation revision.','']
    return '\n'.join(lines)


def render_html(brief: dict) -> str:
    def text(value):return escape(_value(value),quote=True)
    sections=[]
    for heading,paragraphs,tables in _sections(brief):
        section='<section><h2>'+text(heading)+'</h2>'+''.join('<p>'+text(paragraph)+'</p>' for paragraph in paragraphs)
        for headers,rows in tables:
            if not rows:continue
            section+='<div class="table-scroll"><table><thead><tr>'+''.join('<th scope="col">'+text(value)+'</th>' for value in headers)+'</tr></thead><tbody>'
            section+=''.join('<tr>'+''.join('<td>'+text(value)+'</td>' for value in row)+'</tr>' for row in rows)
            section+='</tbody></table></div>'
        sections.append(section+'</section>')
    title='Where should America’s next sustainable AI data center be investigated?'
    label='DEMO DATA — synthetic software fixture' if brief['data_mode']=='synthetic' else 'Conditional investigation · transparent evidence'
    return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'+\
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'"><title>'+text(title)+'</title><style>'+\
        'body{margin:0;background:#f4f3ed;color:#172d29;font:16px/1.55 system-ui,sans-serif}main{max-width:1180px;margin:auto;padding:50px 28px}'+\
        'header{border-bottom:3px solid #315f4f;padding-bottom:28px}h1{font-size:clamp(2rem,4vw,3.4rem);line-height:1.1;max-width:900px}'+\
        '.eyebrow{font-weight:700;color:#315f4f;letter-spacing:.04em}section{background:#fffef9;border:1px solid #d9ded6;padding:24px;margin:26px 0}'+\
        'h2{margin:0 0 16px;font-size:1.5rem}p{max-width:100ch}.table-scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:.85rem;margin:16px 0}'+\
        'th,td{text-align:left;vertical-align:top;padding:10px;border-bottom:1px solid #d9ded6;overflow-wrap:anywhere}th{background:#eaf0e8}footer{font-size:.85rem}'+\
        '@media print{body{background:white;font-size:10pt}main{padding:0}section{break-inside:auto;border:0;padding:8px 0}h2{break-after:avoid}tr{break-inside:avoid}.table-scroll{overflow:visible}h1{font-size:24pt}th,td{padding:5px}}'+\
        '</style></head><body><main><header><p class="eyebrow">'+text(label)+'</p><h1>'+text(title)+'</h1><p>Saved analysis '+text(brief['run_id'])+' · '+text(brief['scenario_id'])+'</p></header>'+\
        ''.join(sections)+'<footer>Six submission deliverables. Exact evidence and input hashes: submission_brief.json and run_metadata.json. '+text(brief['interpretation'])+'</footer></main></body></html>\n'
