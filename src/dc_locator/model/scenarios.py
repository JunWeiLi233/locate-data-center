"""Explicit annual scenario extension and native-window context, no forecasts.

Models consume documented scenario metadata; no native source is parsed here.
Cooling design choices remain separate from external scenario identities.
"""
import json
import re
from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from dc_locator.schemas import FacilityConfig, FeatureMetadata, FutureScenarioValue, SitePerformance
from dc_locator.validation import nullable_record, validate_feature_provenance
from dc_locator.source_periods import AQUEDUCT_WINDOWS, AQUEDUCT_PATHWAYS, AQUEDUCT_GCMS, AQUEDUCT_MODEL

ANNUAL_VARIABLES = {
    'e_it_mwh': 'mwh', 'e_facility_mwh': 'mwh', 'c_electricity_kg': 'kg_CO2e',
    'w_site_m3': 'm3_consumed', 'w_electricity_m3': 'm3_consumed',
    'w_site_withdrawal_m3': 'm3_withdrawn', 'w_electricity_withdrawal_m3': 'm3_withdrawn'}
WATER_VARIABLES = {
    'ratio': ('future_water_stress_ratio', 'ratio', 'r'),
    'score': ('future_water_stress_score', 'score_0_to_5', 's'),
    'category': ('future_water_stress_category', 'category_-1_to_4', 'c'),
    'label': ('future_water_stress_label', None, 'l'),
    'extreme_scarcity_frac': ('future_water_extreme_scarcity_frac', 'frac', 'r'),
    'category_shares_json': ('future_water_category_shares_json', None, 'c')}


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


class AnnualExtensionPolicy(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: StrictBool = False
    method: Literal['repeat_opening_year_annual_scenario'] = 'repeat_opening_year_annual_scenario'
    basis: Literal['project_assumption', 'user_assumption', 'no_extension']
    rationale: str = Field(min_length=1)
    reference: str | None = None

    @model_validator(mode='after')
    def explicit_extension(self):
        if not self.rationale.strip() or (self.enabled and self.basis == 'no_extension'):
            raise ValueError('Enabled annual extension requires explicit user/project assumption and rationale')
        return self


class ExternalScenario(BaseModel):
    model_config = ConfigDict(extra='forbid')
    scenario_id: str = Field(min_length=1)
    physical_scenario_id: str = Field(min_length=1)
    pathway: str = Field(min_length=1)
    ssp_rcp: str = Field(min_length=1)
    milestone_year: int
    window_start_year: int | None
    window_end_year: int | None
    supported: StrictBool
    model: str = Field(min_length=1)
    gcms: list[str] = Field(min_length=1)

    @model_validator(mode='after')
    def validate_window(self):
        native = AQUEDUCT_WINDOWS.get(self.milestone_year)
        if self.pathway not in AQUEDUCT_PATHWAYS or self.ssp_rcp != AQUEDUCT_PATHWAYS[self.pathway] or self.model != AQUEDUCT_MODEL or self.gcms != AQUEDUCT_GCMS:
            raise ValueError('External water scenario differs from verified native pathway/model/GCM identity')
        if self.supported != (native is not None) or (native is not None and (self.window_start_year,self.window_end_year) != native):
            raise ValueError('External scenario must preserve exact native milestone trend window')
        if self.supported:
            if self.window_start_year is None or self.window_end_year is None or self.window_end_year < self.window_start_year:
                raise ValueError('Supported scenario requires its native source window')
        elif self.window_start_year is not None or self.window_end_year is not None:
            raise ValueError('Unsupported requested milestone cannot invent a source window')
        return self


def make_external_scenarios(physical_scenario_id, periods):
    """Stable combined identities; a water window is not annual weather."""
    if not isinstance(physical_scenario_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', physical_scenario_id):
        raise ValueError('Stable physical scenario ID required')
    results = []
    for period in periods:
        ssp = re.sub(r'[^A-Za-z0-9]+', '_', period['ssp_rcp']).strip('_')
        window = f'w{period["window_start_year"]}_{period["window_end_year"]}' if period['supported'] else 'UNSUPPORTED'
        scenario_id = f'{physical_scenario_id}__aqueduct_{period["pathway"]}_{period["milestone_year"]}_{window}_{ssp}'
        results.append(ExternalScenario(scenario_id=scenario_id, physical_scenario_id=physical_scenario_id, **period))
    if not results or len({s.scenario_id for s in results}) != len(results):
        raise ValueError('Unique nonempty external scenario definitions required')
    return results


def build_temporal_scenarios(performance, facility: FacilityConfig, scenario_defs, *,
        extension_policy=None, context_provenance=None, provenance_grid_definition_id=None):
    """Build exact annual rows and separate source-window rows for every design.

    By default only opening-year physical outputs have temporal support. An
    explicitly enabled repeat policy carries that modeled annual assumption
    forward; it never promotes a historical factor to an observed forecast.
    Aqueduct context remains one native window row per variable and alternative.
    """
    policy = AnnualExtensionPolicy.model_validate(extension_policy or dict(enabled=False,
        basis='no_extension', rationale='No future annual source coverage or extension authorized'))
    scenarios = [ExternalScenario.model_validate(s.model_dump() if isinstance(s, ExternalScenario) else s) for s in scenario_defs]
    if not scenarios or len({s.scenario_id for s in scenarios}) != len(scenarios):
        raise ValueError('Unique nonempty scenario definitions required')
    if performance.empty or not {'grid_id', 'design_id', 'scenario_id'} <= set(performance) or performance.duplicated(['grid_id', 'design_id', 'scenario_id']).any():
        raise ValueError('Nonempty unique physical alternative table required')
    if set(performance.scenario_id) != {s.scenario_id for s in scenarios}:
        raise ValueError('Physical rows must exactly match supplied external scenarios')
    if len(performance) != performance.grid_id.nunique()*performance.design_id.nunique()*len(scenarios):
        raise ValueError('Physical alternatives must cover exact grid × design × external scenario Cartesian product')
    records = [SitePerformance.model_validate(nullable_record(r)).model_dump(mode='json') for r in performance.to_dict('records')]
    identities = {r['grid_definition_id'] for r in records}; modes = {r['data_mode'] for r in records}
    if len(identities) != 1 or None in identities or len(modes) != 1 or None in modes:
        raise ValueError('Temporal input requires one known grid/data-mode identity')
    identity, mode = next(iter(identities)), next(iter(modes))
    context = {}
    if context_provenance is not None:
        validate_feature_provenance(context_provenance, grid_ids=performance.grid_id,
            data_mode=mode, grid_definition_id=identity,
            provenance_grid_definition_id=provenance_grid_definition_id)
        context = {(r['grid_id'], r['metric']): FeatureMetadata.model_validate(nullable_record(r)).model_dump(mode='json') for r in context_provenance.to_dict('records')}
    definitions = {s.scenario_id: s for s in scenarios}
    rows = []
    for record in sorted(records, key=lambda r: (r['grid_id'], r['design_id'], r['scenario_id'])):
        if record['facility_id'] != facility.facility_id or record['target_opening_year'] != facility.target_opening_year or record['operating_lifetime_years'] != facility.operating_lifetime_years or record['hours_in_modeled_year'] != facility.hours_in_modeled_year:
            raise ValueError('Physical output disagrees with configured facility/year/lifetime/hours')
        scenario = definitions[record['scenario_id']]
        metadata = json.loads(record['metric_metadata_json'] or '{}')
        original_assumptions = json.loads(record['assumptions_json'] or '{}')
        if not isinstance(metadata, dict) or not isinstance(original_assumptions, dict):
            raise ValueError('Physical metric metadata and assumptions must be objects')
        original_external = original_assumptions.get('external_scenario', {})
        if original_external.get('scenario_id') != scenario.physical_scenario_id:
            raise ValueError('Composite external scenario disagrees with original physical scenario assumption identity')
        assumptions = _json(dict(physical=original_assumptions, external_context=scenario.model_dump(mode='json'),
            annual_extension=policy.model_dump(mode='json'), hours_policy='fixed_modeled_year_hours',
            calendar_leap_year_adjustment=False, physical_climate_response='none; constant PUE/WUE assumptions',
            projection_window_policy='native window context only; no annual interpolation'))
        common = dict(grid_id=record['grid_id'], grid_definition_id=identity, facility_id=facility.facility_id,
            design_id=record['design_id'], scenario_id=scenario.scenario_id, data_mode=mode,
            milestone_year=scenario.milestone_year, ssp_rcp=scenario.ssp_rcp, assumptions_json=assumptions)
        for variable, unit in ANNUAL_VARIABLES.items():
            value, evidence = record.get(variable), metadata.get(variable, {})
            if value is not None and (evidence.get('unit') != unit or evidence.get('status') not in {'observed','calculated','scenario','proxy'} or evidence.get('confidence') not in {'high','medium','low'}):
                raise ValueError('Known annual value requires matching unit/status/confidence evidence: '+variable)
            if value is None and evidence.get('status') not in {None, 'unknown'}:
                raise ValueError('Null annual value contradicts known evidence: '+variable)
            source = evidence.get('source_evidence', {}) or {}
            if value is not None and variable == 'c_electricity_kg' and (source.get('coverage_frac') is None or source['coverage_frac'] < 1-1e-6):
                raise ValueError('Known annual carbon requires complete source coverage')
            source_json = _json(evidence)
            for year in range(facility.target_opening_year, facility.target_opening_year+facility.operating_lifetime_years):
                supported = year == facility.target_opening_year or policy.enabled
                present = supported and value is not None
                reason = None if present else ('missing_period_coverage_without_explicit_extension' if not supported else evidence.get('missing_reason', 'missing_physical_input'))
                row = FutureScenarioValue(**common, model='constant-annual-physical-scenario-v1',
                    period_kind='annual_operating', period_start_year=year, period_end_year=year,
                    variable=variable, unit=unit, value=value if present else None,
                    source_id=source.get('source_id') or 'dc_locator_physics_v1', source_year=source.get('data_year') or str(facility.target_opening_year), source_json=source_json,
                    status=evidence['status'] if present else 'unknown', confidence=evidence['confidence'] if present else 'unknown',
                    coverage_frac=(source.get('coverage_frac',1.0) if variable=='c_electricity_kg' else 1.0) if present else 0,
                    missing_reason=reason, hours_in_modeled_year=facility.hours_in_modeled_year)
                rows.append(row.model_dump(mode='json'))
        for suffix, (variable, unit, native_suffix) in WATER_VARIABLES.items():
            metric = f'aqueduct_{scenario.pathway}_{scenario.milestone_year}_water_stress_{suffix}'
            evidence = context.get((record['grid_id'], metric))
            present = scenario.supported and evidence is not None and evidence['status'] != 'unknown'
            if present:
                expected_field = f'{scenario.pathway}{str(scenario.milestone_year)[-2:]}_ws_x_{native_suffix}'
                if evidence['source_id'] != 'wri_aqueduct40_future' or evidence['source_field'] != expected_field or evidence['unit'] != unit or evidence['status'] != 'scenario' or evidence['coverage_frac'] is None or evidence['coverage_frac'] <= 0:
                    raise ValueError('Future water evidence source/status/unit/coverage differs from scenario binding')
            reason = None if present else ('unsupported_source_milestone_no_interpolation' if not scenario.supported else evidence['missing_reason'] if evidence else 'missing_future_context')
            row = FutureScenarioValue(**common, model=scenario.model,
                period_kind='source_projection_window' if scenario.supported else 'unsupported_requested_period',
                period_start_year=scenario.window_start_year, period_end_year=scenario.window_end_year,
                variable=variable, unit=unit, value=evidence['value'] if present else None,
                value_text=evidence['value_text'] if present else None,
                source_id='wri_aqueduct40_future', source_year=evidence.get('data_year') if evidence else None,
                source_json=_json(evidence or {}), status='scenario' if present else 'unknown',
                confidence=evidence['confidence'] if present else 'unknown',
                coverage_frac=evidence['coverage_frac'] if present else 0, missing_reason=reason)
            rows.append(row.model_dump(mode='json'))
    result = pd.DataFrame(rows).sort_values(['grid_id','design_id','scenario_id','variable','period_start_year'], na_position='last').reset_index(drop=True)
    result.attrs.update(grid_definition_id=identity, data_mode=mode)
    return result


def build_climate_source_context(provenance, *, grid_ids, grid_definition_id, data_mode, facility_id):
    """Export native climate under its own identity, independent of water/design.

    Source adapters expose verified model/ensemble/SSP/period metadata in `method`.
    These rows are context only, with reserved design_id='source_context', and
    never enter physical performance, lifecycle electricity or decision weights.
    """
    validate_feature_provenance(provenance, grid_ids=grid_ids, data_mode=data_mode,
        grid_definition_id=grid_definition_id)
    rows = []
    for raw in provenance.loc[provenance.source_id.eq('nasa_nex_gddp_cmip6')].to_dict('records'):
        evidence = FeatureMetadata.model_validate(nullable_record(raw)).model_dump(mode='json')
        method = json.loads(evidence['method'] or '{}')
        required = {'model','ensemble','ssp','period_start_year','period_end_year','variable','temporal_coverage_frac'}
        if not required <= set(method) or any(not method[k] for k in ('model','ensemble','ssp','variable')):
            raise ValueError('Climate source context lacks native model/ensemble/SSP/period identity')
        start,end = method['period_start_year'],method['period_end_year']
        if type(start) is not int or type(end) is not int or end < start:
            raise ValueError('Climate native period must use explicit integer bounds')
        temporal = method['temporal_coverage_frac']
        if temporal is not None and (type(temporal) not in {int,float} or not 0 <= temporal <= 1):
            raise ValueError('Climate temporal coverage must be finite fraction')
        identifier = '_'.join(re.sub(r'[^A-Za-z0-9]+','_',str(method[k])).strip('_') for k in ('model','ensemble','ssp'))
        scenario_id = f'source_context_nex_{identifier}_{start}_{end}'
        row = FutureScenarioValue(grid_id=evidence['grid_id'], grid_definition_id=grid_definition_id,
            facility_id=facility_id, design_id='source_context', scenario_id=scenario_id,
            model=method['model']+'; '+method['ensemble'], period_kind='source_projection_window',
            period_start_year=start,period_end_year=end,ssp_rcp=method['ssp'],variable=evidence['metric'],
            value=evidence['value'],value_text=evidence['value_text'],unit=evidence['unit'],
            source_id=evidence['source_id'],source_year=evidence['data_year'],source_json=_json(evidence),
            assumptions_json=_json(dict(source_context_only=True,native_identity=method,
                paired_aqueduct_scenario=False,physical_cooling_response=False,
                interpretation='Single-model source context; no annual/lifetime extension or preference weight')),
            status=evidence['status'],confidence=evidence['confidence'],coverage_frac=evidence['coverage_frac'],
            missing_reason=evidence['missing_reason'],data_mode=data_mode)
        rows.append(row.model_dump(mode='json'))
    return pd.DataFrame(rows, columns=list(FutureScenarioValue.model_fields)).sort_values(['grid_id','scenario_id','variable']).reset_index(drop=True)
