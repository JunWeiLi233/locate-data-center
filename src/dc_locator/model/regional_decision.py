"""Bounded evidence preparation followed by one global regional decision.

Batch scores use the same declared fixed references and complete weights as
``decide``. Global ranks and Pareto flags are intentionally unset in batches.
The compact numeric/status table carries no nested physical evidence payload;
that evidence remains in each persisted batch and the source provenance.
"""
from __future__ import annotations

import hashlib
import json
import weakref

import numpy as np
import pandas as pd

from dc_locator.model.decision import _normalize_metrics,_normalized_identity,_weights
from dc_locator.model.mcda import score_alternatives
from dc_locator.model.metrics import KEYS,assemble_metrics,clean,json_text
from dc_locator.model.normalization import normalize_values
from dc_locator.model.pareto import pareto_frontier
from dc_locator.schemas import DecisionResult


_COMPACT_FIELDS=[*KEYS,'schema_version','grid_definition_id','data_mode','facility_id',
    'eligible','conditional','hard_fail','critical_unknown','mode','rankable',
    'rank_status','unranked_reason','mcda_score','mcda_rank','pareto_comparable',
    'pareto_status','is_pareto_optimal','pareto_rank','profile_id','profile_fingerprint',
    'weighting_method','ahp_status','weights_used_json','contribution_by_metric_json']
_EVIDENCE_FIELDS=['status','confidence','coverage_frac','source_valid','missing_reason','unit','normalization_status']
# One immutable global decision is finalized batch by batch. Keep only its
# membership/identity index, outside DataFrame.attrs (which Parquet serializes).
_FINALIZATION_CACHE=None


def select_refinement_parents(grid,regions):
    """Select actual evaluated national representatives in stable grid order."""
    ids=sorted(set(regions.representative_grid_id))
    if grid.grid_id.duplicated().any() or not set(ids)<=set(grid.grid_id):
        raise ValueError('Parent representative lineage does not match national grid')
    return grid.set_index('grid_id',drop=False).loc[ids].reset_index(drop=True)


def _metric_policy(profile):
    return hashlib.sha256(json_text([metric.model_dump(mode='json') for metric in profile.metrics]).encode()).hexdigest()


def _decorate_ranked(ranked,profile,profile_hash,method,ahp_result):
    ranked['schema_version']='1.1.0'
    ranked['profile_id']=profile.profile_id
    ranked['profile_fingerprint']=profile_hash
    ranked['weighting_method']=method
    ranked['ahp_status']=ahp_result['status'] if ahp_result else 'NOT_APPLICABLE'
    return ranked


def _validate_decisions(ranked,weights):
    fields=set(DecisionResult.model_fields)
    columns=[column for column in ranked if column in fields or column=='contribution_by_metric_json']
    for start in range(0,len(ranked),1000):
        for row in ranked.iloc[start:start+1000][columns].to_dict('records'):
            canonical={key:clean(value) for key,value in row.items() if key in fields}
            canonical['weights_used']=weights
            canonical['contribution_by_metric']=json.loads(row['contribution_by_metric_json'])
            DecisionResult.model_validate(canonical)


def _comparable(ranked,metric_ids):
    return ranked[metric_ids].notna().all(axis=1)&ranked.eligible&~ranked.hard_fail&~((ranked['mode']=='STRICT')&ranked.critical_unknown)


def prepare_batch(geography,provenance,performance,eligibility,profile,*,profile_hash,provenance_grid_definition_id):
    """Validate native evidence and prepare fixed-reference batch score tables.

    The caller owns the persisted evidence and input bindings. Neither local
    ranks nor local frontiers are presented as global. Source validity and
    nullability are retained in compact records, including ineligible rows.
    """
    frame,normalized=assemble_metrics(geography,provenance,performance,eligibility,profile,
        provenance_grid_definition_id=provenance_grid_definition_id)
    frame,normalized=_normalize_metrics(frame,normalized,profile)
    weights,method,ahp_result,template=_weights(profile,frame)
    ranked=score_alternatives(frame,profile.metric_ids,weights,
        weights_usable=ahp_result is None or ahp_result['status']!='REVIEW_REQUIRED')
    ranked['mcda_rank']=pd.Series(pd.NA,index=ranked.index,dtype='Int64')
    ranked['pareto_comparable']=_comparable(ranked,profile.metric_ids)
    ranked['is_pareto_optimal']=pd.Series(pd.NA,index=ranked.index,dtype='boolean')
    ranked['pareto_status']='NOT_ASSESSED'
    ranked['pareto_rank']=pd.Series(pd.NA,index=ranked.index,dtype='Int64')
    ranked=_decorate_ranked(ranked,profile,profile_hash,method,ahp_result)
    _validate_decisions(ranked,weights)
    normalized=_normalized_identity(normalized,geography,profile,profile_hash)
    geo=geography.set_index('grid_id')
    for metric in profile.metrics:
        if metric.table=='geography':ranked[metric.column]=ranked.grid_id.map(geo[metric.column])
    if 'suitable_land_area_km2' in geo and 'suitable_land_area_km2' not in ranked:
        ranked['suitable_land_area_km2']=ranked.grid_id.map(geo.suitable_land_area_km2)
    columns=list(dict.fromkeys([*_COMPACT_FIELDS,*profile.metric_ids,
        *['raw_'+metric.metric_id for metric in profile.metrics],
        *['contribution_'+metric.metric_id for metric in profile.metrics],
        *[metric.column for metric in profile.metrics],'suitable_land_area_km2']))
    compact=ranked[[column for column in columns if column in ranked]].copy()
    row_keys=pd.MultiIndex.from_frame(compact[KEYS])
    for metric in profile.metrics:
        evidence=normalized.loc[normalized.metric_id.eq(metric.metric_id)].set_index(KEYS).reindex(row_keys)
        for field in _EVIDENCE_FIELDS:
            compact[metric.metric_id+'_'+field]=evidence[field].to_numpy()
    compact['prepared_metric_policy_sha256']=_metric_policy(profile)
    return dict(ranked_cells=ranked,normalized_metrics=normalized,compact=compact,
        weights=weights,weighting_method=method,ahp_result=ahp_result,ahp_template=template)


def rank_compact(compact,profile,*,profile_hash):
    """Score and compare the entire explicitly evaluated fine-grid universe.

    Weight-only preferences may change. Metric definitions and fixed references
    must match the already validated native batch evidence. Global scores use
    all required metrics with no candidate-specific weight redistribution.
    """
    required={*_COMPACT_FIELDS,'prepared_metric_policy_sha256',*profile.metric_ids,
        *['raw_'+metric.metric_id for metric in profile.metrics],
        *[metric.metric_id+'_'+field for metric in profile.metrics for field in _EVIDENCE_FIELDS]}
    if not required.issubset(compact):raise ValueError('Compact decision table lacks required evidence fields')
    if compact.duplicated(KEYS).any():raise ValueError('Duplicate compact alternative IDs')
    if len(compact) and set(compact.prepared_metric_policy_sha256)!={_metric_policy(profile)}:
        raise ValueError('Compact metric policy differs from the declared profile')
    for field in ('grid_definition_id','data_mode','facility_id','mode'):
        if len(compact) and (compact[field].nunique(dropna=False)!=1 or compact[field].isna().any()):
            raise ValueError('Mixed or missing compact '+field)
    flags=['eligible','conditional','hard_fail','critical_unknown',
        *[metric.metric_id+'_source_valid' for metric in profile.metrics]]
    for field in flags:
        if not compact[field].map(lambda value:isinstance(value,(bool,np.bool_))).all():
            raise ValueError('Compact '+field+' must contain booleans')
    # Evidence validation is read-only; the scorer owns the single mutable copy.
    frame=compact
    for metric in profile.metrics:
        valid=frame[metric.metric_id+'_source_valid']
        accepted=pd.to_numeric(frame['raw_'+metric.metric_id],errors='coerce').where(valid)
        normalized,_=normalize_values(accepted,metric.reference_low,metric.reference_high,metric.direction)
        if not np.array_equal(normalized,frame[metric.metric_id].to_numpy(dtype=float),equal_nan=True):
            raise ValueError('Compact normalized value differs from validated fixed references')
        if (valid&(~frame[metric.metric_id+'_status'].isin(metric.allowed_statuses)
                |~frame[metric.metric_id+'_confidence'].isin(['high','medium','low'])
                |frame[metric.metric_id+'_unit'].ne(metric.unit)
                |frame[metric.metric_id+'_missing_reason'].notna())).any():
            raise ValueError('Compact source validity contradicts required metric evidence')
        if metric.minimum_coverage_frac is not None:
            coverage=pd.to_numeric(frame[metric.metric_id+'_coverage_frac'],errors='coerce')
            if (valid&(~np.isfinite(coverage)|(coverage<metric.minimum_coverage_frac))).any():
                raise ValueError('Compact source coverage contradicts required metric evidence')
    weights,method,ahp_result,template=_weights(profile,frame)
    ranked=score_alternatives(frame,profile.metric_ids,weights,
        weights_usable=ahp_result is None or ahp_result['status']!='REVIEW_REQUIRED')
    raw=ranked[[*KEYS,*profile.metric_ids]].copy()
    for metric in profile.metrics:raw[metric.metric_id]=ranked['raw_'+metric.metric_id]
    raw['rankable']=_comparable(ranked,profile.metric_ids)
    ranked['pareto_comparable']=raw['rankable']
    pareto=pareto_frontier(raw,profile.metric_ids,[metric.direction for metric in profile.metrics],
        [profile.pareto['absolute_tolerances'][metric.metric_id] for metric in profile.metrics],
        relative_tolerance=profile.pareto['relative_tolerance'])
    for column in ('is_pareto_optimal','pareto_status','pareto_rank'):ranked[column]=pareto[column]
    ranked=_decorate_ranked(ranked,profile,profile_hash,method,ahp_result)
    _validate_decisions(ranked,weights)
    ranked.attrs.update(weights=weights,weighting_method=method,ahp_result=ahp_result,
        ahp_template=template,constant_observed_columns={metric:ranked[metric].dropna().nunique()<=1 for metric in profile.metric_ids})
    return ranked


def _finalization_index(global_ranked):
    global _FINALIZATION_CACHE
    if _FINALIZATION_CACHE is not None and _FINALIZATION_CACHE[0]() is global_ranked:
        return _FINALIZATION_CACHE[1:]
    keys=pd.MultiIndex.from_frame(global_ranked[KEYS])
    if not keys.is_unique:raise ValueError('Duplicate globally ranked alternative IDs')
    identities={}
    for field in ('profile_id','profile_fingerprint','grid_definition_id','data_mode'):
        if len(global_ranked):
            values=global_ranked[field].drop_duplicates()
            if len(values)!=1:raise ValueError('Mixed global normalized identity '+field)
            identities[field]=values.iloc[0]
    _FINALIZATION_CACHE=(weakref.ref(global_ranked),keys,identities)
    return keys,identities


def finalize_normalized(normalized,global_ranked):
    """Reconcile batch diagnostics against an immutable global decision table."""
    result=normalized.copy()
    global_keys,identities=_finalization_index(global_ranked)
    if len(global_ranked) and (global_keys.get_indexer(pd.MultiIndex.from_frame(result[KEYS]))<0).any():
        raise ValueError('Normalized batch is outside the globally ranked universe')
    constants=global_ranked.attrs.get('constant_observed_columns',{})
    for metric in result.metric_id.unique():
        if metric not in global_ranked:raise ValueError('Global decision lacks normalized metric '+metric)
        constant=constants[metric] if metric in constants else global_ranked[metric].dropna().nunique()<=1
        result.loc[result.metric_id.eq(metric),'constant_observed_column']=constant
    for field,value in identities.items():result[field]=value
    return result.sort_values(KEYS+['metric_id']).reset_index(drop=True)
