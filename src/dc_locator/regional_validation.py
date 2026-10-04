"""Stream configured regional sensitivity across one explicitly ranked universe."""
from __future__ import annotations

import re
import hashlib
import warnings
import gc
import numpy as np
import pandas as pd

from dc_locator.io import write_parquet
from dc_locator.model.metrics import KEYS, clean, profile_fingerprint
from dc_locator.model.run_validation import CurrentSensitivityCase, _weighted_profile
from dc_locator.model.validation.analysis import compare_ranked_cases, summarize_fixed_regions, stable_top_k
from dc_locator.pipeline import emit


_SUMMARY_COLUMNS=[*KEYS,'grid_definition_id','facility_id','data_mode','eligible',
    'rankable','hard_fail','critical_unknown','conditional','mcda_rank','mcda_score',
    'profile_id','is_pareto_optimal','mode']


def validate_regional(compact, strict_compact, ranked, membership, representative_ids,
                      profile, settings, output, identity, mode):
    """Weights reuse unchanged physical inputs; strict inputs were natively rescreened.

    Every case has complete globally ranked compact evidence. Small API sensitivity
    extracts cover evaluated region representatives; streamed numeric comparisons
    and rank ranges cover every alternative. No independent batch rank is reused.
    """
    from dc_locator.model.regional_decision import rank_compact
    if set(strict_compact['mode'])!={'STRICT'}:
        raise ValueError('STRICT case requires natively screened STRICT compact inputs')
    compact_keys=pd.MultiIndex.from_frame(compact[KEYS])
    strict_keys=pd.MultiIndex.from_frame(strict_compact[KEYS])
    if not compact_keys.is_unique or not strict_keys.is_unique or len(strict_keys)!=len(compact_keys) or (strict_keys.get_indexer(compact_keys)<0).any():
        raise ValueError('STRICT compact input must preserve the complete evaluated alternative domain')
    del compact_keys,strict_keys
    if (strict_compact.critical_unknown & (strict_compact.eligible | strict_compact.conditional)).any():
        raise ValueError('STRICT input violates critical UNKNOWN exclusion')
    definition = str(ranked.grid_definition_id.iloc[0])
    def write(frame, name, schema):
        write_parquet(frame, output/(name+'.parquet'), schema_name=schema,
                      schema_version='1.0.0', data_mode=mode, grid_definition_id=definition)
    fresh = rank_compact(compact, profile, profile_hash=profile_fingerprint(profile))
    pd.testing.assert_frame_equal(ranked, fresh)
    del fresh
    gc.collect()
    baseline_keys=ranked[KEYS]
    baseline_ranks=pd.to_numeric(ranked.mcda_rank,errors='coerce').to_numpy(dtype=float,na_value=np.nan)
    counts = np.zeros(len(ranked), dtype=np.int64)
    minimum = np.full(len(ranked), np.inf)
    maximum = np.full(len(ranked), -np.inf)
    extracts, summaries, fixed = [], [], []
    cases = [('baseline', None)] + [(item['case_id'], CurrentSensitivityCase.model_validate(item)) for item in settings.get('cases', [])]
    if any(not re.fullmatch(r'[A-Za-z0-9_-]+',case_id) for case_id,_ in cases):
        raise ValueError('Sensitivity case IDs must be safe artifact names')
    validation_id = 'regional-'+hashlib.sha256(identity.encode()).hexdigest()[:16]
    for case_id, case in cases:
        active = profile
        assumptions = {'basis':'current_configured_run','rationale':'Fresh batch physics/screening and exact global baseline recomputation.'}
        category = 'baseline'
        if case is None:
            result = ranked
        else:
            category = case.category
            assumptions = case.model_dump(mode='json')
            if category == 'weights':
                active, parents = _weighted_profile(profile, case)
                assumptions['normalized_group_weights'] = parents
                result = rank_compact(compact, active, profile_hash=profile_fingerprint(active))
            elif category == 'screening' and case.mode == 'STRICT':
                result = rank_compact(strict_compact, active, profile_hash=profile_fingerprint(active))
            else:
                raise ValueError('Regional validation supports declared weights and STRICT cases only')
        # Global ranking always sorts canonical keys; compare that contract before
        # using positional arrays instead of duplicating every evidence column.
        pd.testing.assert_frame_equal(result[KEYS],baseline_keys)
        write(result, 'validation_cases/'+case_id+'/ranked_cells', 'RegionalRankedCellDataset')
        emit(output/'validation_cases'/case_id/'assumptions.json', assumptions)
        ranks = pd.to_numeric(result.mcda_rank, errors='coerce').to_numpy(dtype=float, na_value=np.nan)
        known = np.isfinite(ranks)
        counts += known
        minimum = np.minimum(minimum, np.where(known, ranks, np.inf))
        maximum = np.maximum(maximum, np.where(known, ranks, -np.inf))
        numeric = result[KEYS+['rankable','eligible','hard_fail','critical_unknown','conditional','mcda_rank','mcda_score','is_pareto_optimal']].reset_index(drop=True)
        numeric.rename(columns={c:'case_'+c for c in numeric if c not in KEYS}, inplace=True)
        numeric['case_id'] = case_id
        numeric['baseline_scenario_id'] = numeric.scenario_id
        numeric['rank_change'] = ranks-baseline_ranks
        deltas = np.stack([(result['contribution_'+m].to_numpy(dtype=float)-ranked['contribution_'+m].to_numpy(dtype=float)) for m in profile.metric_ids],axis=1)
        absolute = np.abs(deltas)
        # Equal drivers break by metric ID, matching the existing analysis helper.
        order = sorted(range(len(profile.metric_ids)), key=lambda i:profile.metric_ids[i])
        safe = np.nan_to_num(absolute[:,order], nan=-1.)
        winners = np.argmax(safe, axis=1)
        magnitudes = safe[np.arange(len(safe)), winners]
        numeric['main_driver'] = [profile.metric_ids[order[i]] if v > 1e-15 else None for i,v in zip(winners,magnitudes)]
        numeric['driver_abs_contribution_change'] = np.where(magnitudes>1e-15,magnitudes,np.nan)
        write(numeric, 'validation_cases/'+case_id+'/comparison', 'RegionalSensitivityDataset')
        del numeric,deltas,absolute,safe,winners,magnitudes
        for scenario in sorted(ranked.scenario_id.unique()):
            scope=ranked.scenario_id.eq(scenario).to_numpy()
            scenario_base = ranked[_SUMMARY_COLUMNS].loc[scope]
            scenario_case = result[_SUMMARY_COLUMNS].loc[scope]
            top_base, top_case = stable_top_k(scenario_base, settings.get('top_k',10)), stable_top_k(scenario_case, settings.get('top_k',10))
            match = scenario_base.rankable.to_numpy() & scenario_case.rankable.to_numpy()
            left = pd.to_numeric(scenario_base.mcda_rank,errors='coerce').to_numpy(dtype=float,na_value=np.nan)[match]
            right = pd.to_numeric(scenario_case.mcda_rank,errors='coerce').to_numpy(dtype=float,na_value=np.nan)[match]
            correlation = float(np.corrcoef(left,right)[0,1]) if len(left)>1 else None
            summaries.append(dict(case_id=case_id,case_category=category,scenario_id=scenario,
                alternatives=len(scenario_case),rankable=int(scenario_case.rankable.sum()),eligible=int(scenario_case.eligible.sum()),
                hard_failures=int(scenario_case.hard_fail.sum()),critical_unknown=int(scenario_case.critical_unknown.sum()),
                rank_correlation=clean(correlation),top_k_overlap_count=len(top_base&top_case),
                top_k_jaccard=len(top_base&top_case)/len(top_base|top_case) if top_base|top_case else None))
            wanted = scope&ranked.grid_id.isin(representative_ids).to_numpy()
            if wanted.any():
                extract = compare_ranked_cases(ranked.loc[wanted],result.loc[wanted],
                    evaluation_version='phase9_regional_v1',freeze_id=validation_id,case_id=case_id,
                    case_category=category,k=settings.get('top_k',10),case_metadata=assumptions)
                extract['base_top_k'] = [tuple(row) in top_base for row in extract[['grid_id','design_id']].to_numpy()]
                extract['case_top_k'] = [tuple(row) in top_case for row in extract[['grid_id','design_id']].to_numpy()]
                extract['current_run_id'] = identity
                extracts.append(extract)
                del extract
            selected = membership.loc[membership.scenario_id.eq(scenario)]
            if len(selected):
                fixed.append(summarize_fixed_regions(selected,scenario_case,evaluation_version='phase9_regional_v1',
                    freeze_id=validation_id,case_id=case_id,baseline_scenario_id=scenario))
            del scenario_base,scenario_case,scope,match,left,right,wanted,selected,top_base,top_case
        del result,ranks,known
        gc.collect()
    ranges = baseline_keys.rename(columns={'scenario_id':'baseline_scenario_id'})
    ranges['base_rank'] = ranked.mcda_rank
    ranges['evaluated_cases'] = len(cases)
    ranges['ranked_cases'] = counts
    ranges['unranked_cases'] = len(cases)-counts
    ranges['minimum_rank'] = np.where(counts,minimum,np.nan)
    ranges['maximum_rank'] = np.where(counts,maximum,np.nan)
    ranges['rank_range'] = ranges.maximum_rank-ranges.minimum_rank
    ranges['scope'] = 'All evaluated refined alternatives; separate external scenarios; no unrefined cells ranked.'
    write(ranges,'alternative_rank_ranges','RegionalRankRangeDataset')
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore',message='The behavior of DataFrame concatenation with empty or all-NA entries is deprecated',category=FutureWarning)
        extract = pd.concat(extracts,ignore_index=True) if extracts else pd.DataFrame()
        fixed_table = pd.concat(fixed,ignore_index=True) if fixed else pd.DataFrame()
    write(extract,'sensitivity_results','SensitivityDataset')
    write(fixed_table,'fixed_region_summary','FixedRegionSummaryDataset')
    pd.DataFrame(summaries).to_csv(output/'robustness_summary.csv',index=False,lineterminator='\n')
    report = dict(schema_version='1.1.0',validation_revision='phase9_regional_v1',validation_id=validation_id,
        run_id=identity,validation_scope='all_evaluated_refined_alternatives',
        runtime_contracts=dict(status='PASSED',baseline_fresh_recomputation_exact=True,
            all_alternatives_retained=True,hard_fail_never_ranked=True,strict_critical_unknown_never_ranked=True,
            candidate_specific_missing_weight_redistribution=False),
        ranking_stability=dict(cases=len(cases),case_scenario_summaries=summaries),
        sensitivity_extract_scope='Evaluated region representatives; complete numeric comparisons in validation_cases/*/comparison.parquet',
        accuracy='No independent compatible parcel/utility/facility measurements; no overall industrial accuracy estimate.')
    emit(output/'validation_report.json',report)
    emit(output/'model_validation_summary.json',report)
    return report
