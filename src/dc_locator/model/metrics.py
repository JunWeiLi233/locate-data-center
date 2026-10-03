"""Declared decision profiles and strict evidence checks; no source parsing."""
from __future__ import annotations

import hashlib
import json
import math
import numbers
import numpy as np
from pathlib import Path
from datetime import datetime,timezone
from typing import Literal

import pandas as pd
import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

KEYS = ['grid_id', 'design_id', 'scenario_id']


def json_text(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def clean(value):
    """Convert pandas missing/scalar objects before JSON/schema validation."""
    if isinstance(value, dict): return {k: clean(v) for k,v in value.items()}
    if isinstance(value, (list, tuple,np.ndarray)): return [clean(v) for v in value]
    if isinstance(value,datetime): return value.astimezone(timezone.utc).isoformat() if value.tzinfo is not None else value.isoformat()
    if value is None or (not isinstance(value, str) and pd.isna(value)): return None
    if hasattr(value, 'item'): return value.item()
    return value


class MetricDefinition(BaseModel):
    model_config = ConfigDict(extra='forbid')
    metric_id: str = Field(min_length=1)
    column: str
    table: Literal['performance','geography']
    definition: str
    unit: str
    direction: Literal['minimize','maximize']
    normalization: Literal['fixed_linear']
    reference_low: float
    reference_high: float
    basis: Literal['project_assumption','published_source_scale']
    reference: str | None = None
    rationale: str = Field(min_length=1)
    role: Literal['decision_metric','informational_proxy']
    group_id: str
    local_weight: float = Field(ge=0)
    required: Literal[True] = True
    allowed_statuses: list[Literal['observed','calculated','scenario','proxy']]
    source_id: str | None = None
    source_field: str | None = None
    minimum_coverage_frac: float | None = Field(default=None,ge=0,le=1)
    double_count_family: str

    @model_validator(mode='before')
    @classmethod
    def numeric_types(cls,value):
        for field in ('reference_low','reference_high','local_weight','minimum_coverage_frac'):
            coefficient = value.get(field)
            if coefficient is not None and (isinstance(coefficient,(bool,np.bool_)) or not isinstance(coefficient,numbers.Real)):
                raise ValueError(field+' must be numeric, not a boolean or string')
        return value

    @model_validator(mode='after')
    def check(self):
        if not all(math.isfinite(v) for v in (self.reference_low,self.reference_high,self.reference_high-self.reference_low,self.local_weight)) or self.reference_low >= self.reference_high:
            raise ValueError('Metric bounds/weights must be finite and low < high')
        if not self.allowed_statuses or (self.basis == 'published_source_scale' and not self.reference):
            raise ValueError('Status requirements and published scale reference are required')
        if self.minimum_coverage_frac is not None and not math.isfinite(self.minimum_coverage_frac):
            raise ValueError('Coverage must be finite')
        return self


class ScoringProfile(BaseModel):
    model_config = ConfigDict(extra='forbid')
    profile_id: str
    profile_version: str
    description: str
    weighting_method: Literal['equal','user','ahp']
    weight_scope: Literal['groups','leaves'] = 'groups'
    user_weights: dict | None = None
    ahp_judgments: dict | None = None
    groups: list[dict]
    metrics: list[MetricDefinition] = Field(min_length=1)
    excluded_criteria: list[dict]
    pareto: dict
    region_selection: dict
    ahp: dict

    @property
    def metric_ids(self): return [m.metric_id for m in self.metrics]

    @property
    def weight_criterion_ids(self): return [g['group_id'] for g in self.groups] if self.weight_scope == 'groups' else self.metric_ids

    @model_validator(mode='before')
    @classmethod
    def policy_types(cls,value):
        pareto = value.get('pareto',{})
        region = value.get('region_selection',{})
        ahp = value.get('ahp',{})
        coefficients = list(pareto.get('absolute_tolerances',{}).values())+[pareto.get('relative_tolerance',0),region.get('top_fraction'),ahp.get('consistency_threshold'),ahp.get('reciprocal_tolerance')]
        if any(isinstance(v,(bool,np.bool_)) or not isinstance(v,numbers.Real) or not math.isfinite(v) for v in coefficients): raise ValueError('Decision policy coefficients must be finite numeric values, not booleans or strings')
        if type(region.get('require_pareto')) is not bool: raise ValueError('require_pareto must be a boolean, not quoted text')
        if type(region.get('minimum_cells')) is not int: raise ValueError('minimum_cells must be an integer, not a boolean')
        if ahp['consistency_threshold'] < 0 or ahp['reciprocal_tolerance'] < 0: raise ValueError('AHP tolerances must be nonnegative')
        return value

    @model_validator(mode='after')
    def check(self):
        if len(set(self.metric_ids)) != len(self.metrics): raise ValueError('Duplicate metric IDs')
        if len({m.double_count_family for m in self.metrics}) != len(self.metrics): raise ValueError('Duplicate scoring family; double counting requires a new documented profile')
        gids = [g['group_id'] for g in self.groups]
        if len(set(gids)) != len(gids) or set(gids) != {m.group_id for m in self.metrics}: raise ValueError('Groups must exactly match active metric groups')
        for gid in gids:
            if not math.isclose(sum(m.local_weight for m in self.metrics if m.group_id == gid), 1, abs_tol=1e-10): raise ValueError('Local weights must sum to one in each group')
        weights = [g['equal_parent_weight'] for g in self.groups]
        if any(isinstance(w,bool) or not isinstance(w,numbers.Real) or not math.isfinite(w) or w < 0 for w in weights) or not math.isclose(sum(weights),1,abs_tol=1e-10): raise ValueError('Parent weights must be finite nonnegative and sum to one')
        if self.weighting_method == 'equal' and any(not math.isclose(w,1/len(weights),abs_tol=1e-10) for w in weights): raise ValueError('Equal mode requires equal parent groups')
        if self.weight_scope == 'leaves' and (len(self.groups) != len(self.metrics) or any(m.local_weight != 1 for m in self.metrics)): raise ValueError('Flat-leaf weighting needs explicit single-leaf groups; do not silently discard a declared hierarchy')
        if self.pareto.get('objective_space') != 'raw_metrics' or set(self.pareto['absolute_tolerances']) != set(self.metric_ids): raise ValueError('Pareto needs every raw metric tolerance')
        tolerances = list(self.pareto['absolute_tolerances'].values()) + [self.pareto.get('relative_tolerance',0)]
        if any(not math.isfinite(t) or t < 0 for t in tolerances): raise ValueError('Invalid Pareto tolerance')
        policy = self.region_selection
        if policy.get('rule') != 'top_fraction_per_design_scenario' or policy.get('adjacency') not in {'rook','queen'} or not math.isfinite(policy['top_fraction']) or not 0 < policy['top_fraction'] <= 1 or not isinstance(policy['minimum_cells'],int) or policy['minimum_cells'] < 1: raise ValueError('Invalid region selection policy')
        return self


def load_profile(path) -> ScoringProfile:
    return ScoringProfile.model_validate(yaml.safe_load(Path(path).read_text(encoding='utf-8')))


def profile_fingerprint(profile):
    return hashlib.sha256(json_text(profile.model_dump(mode='json')).encode()).hexdigest()


def assemble_metrics(geography, provenance, performance, eligibility, profile, *, provenance_grid_definition_id=None):
    """Keep all diagnostics; validate values against explicit units/status/source coverage.

    Geography evidence is long-form provenance. Derived physical outputs carry
    nested source_evidence (e.g. carbon) and consumption/withdrawal units.
    Invalid/missing evidence removes rankability, never an individual weight.
    """
    from dc_locator.schemas import FeatureMetadata,ScreeningEligibility, SitePerformance
    for row in provenance.to_dict('records'): FeatureMetadata.model_validate(clean(row))
    for table,schema in ((performance,SitePerformance),(eligibility,ScreeningEligibility)):
        if table.duplicated(KEYS).any(): raise ValueError('Duplicate alternative IDs')
        for row in table.to_dict('records'): schema.model_validate(clean(row))
    for field in ('eligible','conditional','hard_fail','critical_unknown'):
        if any(not isinstance(v,(bool,np.bool_)) for v in eligibility[field]): raise ValueError('Eligibility flags must be booleans')
    if set(map(tuple,performance[KEYS].to_numpy())) != set(map(tuple,eligibility[KEYS].to_numpy())): raise ValueError('Performance and eligibility alternatives differ')
    if geography.grid_id.duplicated().any() or provenance.duplicated(['grid_id','metric']).any(): raise ValueError('Duplicate geographic/provenance IDs')
    if not set(performance.grid_id) <= set(geography.grid_id): raise ValueError('Alternative has no geographic cell')
    provenance_definition = provenance_grid_definition_id or provenance.attrs.get('grid_definition_id')
    if provenance_definition != geography.grid_definition_id.iloc[0]: raise ValueError('Explicit provenance grid_definition_id is required and must match geography')
    for field in ('grid_definition_id','data_mode'):
        if geography[field].nunique() != 1: raise ValueError('Mixed geographic identity')
        identity = geography[field].iloc[0]
        for table in (performance,eligibility):
            if table[field].nunique() != 1 or table[field].iloc[0] != identity: raise ValueError('Incompatible '+field)
        if field == 'data_mode' and (provenance[field].nunique() != 1 or provenance[field].iloc[0] != identity): raise ValueError('Incompatible provenance '+field)
    if eligibility['mode'].nunique() != 1: raise ValueError('Mixed screening modes')
    matched = performance[KEYS+['facility_id']].merge(eligibility[KEYS+['facility_id']],on=KEYS)
    if (matched.facility_id_x != matched.facility_id_y).any(): raise ValueError('Incompatible facility identity')
    frame = performance.merge(eligibility.drop(columns=['schema_version','grid_definition_id','data_mode','facility_id'],errors='ignore'),on=KEYS,validate='one_to_one')
    geo = geography.set_index('grid_id')
    evidence = {(r['grid_id'],r['metric']):clean(r) for r in provenance.to_dict('records')}
    metadata = [json.loads(s) for s in frame.metric_metadata_json]
    long = []
    for metric in profile.metrics:
        raw = pd.to_numeric(frame[metric.column] if metric.table == 'performance' else frame.grid_id.map(geo[metric.column]),errors='coerce').to_numpy(dtype=float)
        accepted = []
        for i,row in enumerate(frame.to_dict('records')):
            record = clean(metadata[i].get(metric.column,{})) if metric.table == 'performance' else evidence.get((row['grid_id'],metric.column),{})
            source = record.get('source_evidence') or record
            reasons = []
            if not math.isfinite(raw[i]): reasons.append('missing_or_nonfinite_value')
            if record.get('unit') != metric.unit: reasons.append('incompatible_unit')
            if record.get('status') not in metric.allowed_statuses: reasons.append('unsupported_value_status')
            if record.get('confidence') not in {'high','medium','low'}: reasons.append('unknown_confidence')
            if metric.source_id and source.get('source_id') != metric.source_id: reasons.append('source_identity_mismatch')
            if metric.source_field and source.get('source_field') != metric.source_field: reasons.append('source_field_mismatch')
            coverage = source.get('coverage_frac')
            if metric.minimum_coverage_frac is not None and (coverage is None or not math.isfinite(coverage) or coverage < metric.minimum_coverage_frac): reasons.append('insufficient_source_coverage')
            if metric.table == 'geography' and math.isfinite(raw[i]) and (record.get('value') is None or not math.isclose(raw[i],float(record['value']),rel_tol=1e-10,abs_tol=1e-12)): reasons.append('value_provenance_mismatch')
            if metric.table == 'geography':
                for companion,field in (('status','status'),('confidence','confidence'),('coverage_frac','coverage_frac')):
                    column = metric.column+'_'+companion
                    if column in geo:
                        wide,long_value = clean(geo.loc[row['grid_id'],column]),record.get(field)
                        if wide != long_value: reasons.append(companion+'_provenance_mismatch')
            if metric.table == 'performance' and metric.unit == 'm3_consumed':
                assumptions = json.loads(row['assumptions_json'])
                if assumptions.get('design',{}).get('water_basis') != 'consumption': reasons.append('incompatible_water_basis')
            valid = not reasons
            accepted.append(raw[i] if valid else float('nan'))
            long.append(dict(**{k:row[k] for k in KEYS},metric_id=metric.metric_id,physical_column=metric.column,raw_value=clean(raw[i]),unit=metric.unit,status=record.get('status','unknown'),confidence=record.get('confidence','unknown'),coverage_frac=coverage,source_valid=valid,missing_reason=';'.join(reasons) or None,evidence_json=json_text(record)))
        frame['raw_'+metric.metric_id] = raw
        frame[metric.metric_id] = accepted
    return frame, pd.DataFrame(long)
