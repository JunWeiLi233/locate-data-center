"""Complete fixed weights and eligibility-aware additive decision values."""
import math
import numbers
import numpy as np
import pandas as pd
from dc_locator.model.metrics import KEYS,json_text


def user_weights(weights, metric_ids):
    if set(weights) != set(metric_ids): raise ValueError('Weights must cover exactly the active IDs')
    if any(isinstance(weights[k],(bool,np.bool_)) or not isinstance(weights[k],numbers.Real) for k in metric_ids): raise ValueError('Weights must be real numeric preferences, not booleans or strings')
    values = np.array([weights[k] for k in metric_ids],dtype=float)
    if not np.isfinite(values).all() or (values < 0).any() or not math.isfinite(values.sum()) or values.sum() <= 0: raise ValueError('Weights must be finite nonnegative with positive sum')
    return dict(zip(metric_ids,(values/values.sum()).tolist()))


def equal_weights(profile):
    """Equal declared parent groups times fixed local weights, not equal leaves."""
    parents = {g['group_id']:g['equal_parent_weight'] for g in profile.groups}
    if any(not math.isclose(w,1/len(parents),abs_tol=1e-10) for w in parents.values()): raise ValueError('Equal parent groups required')
    return hierarchical_weights(profile,parents)


def hierarchical_weights(profile,parent_weights):
    """Normalize complete parent preferences once, then multiply local weights."""
    parents = user_weights(parent_weights,[g['group_id'] for g in profile.groups])
    leaves = {m.metric_id:parents[m.group_id]*m.local_weight for m in profile.metrics}
    if not math.isclose(sum(leaves.values()),1,abs_tol=1e-10): raise ValueError('Invalid local hierarchy weights')
    return leaves


def score_alternatives(frame, metric_ids, weights, *, weights_usable=True):
    weights = user_weights(weights,metric_ids)
    frame = frame.copy()
    values = frame[metric_ids].to_numpy(dtype=float)
    complete = np.isfinite(values).all(axis=1)
    if ((values[np.isfinite(values)] < 0) | (values[np.isfinite(values)] > 100)).any(): raise ValueError('Normalized values must be 0–100')
    screened = frame.eligible.astype(bool) & ~frame.hard_fail.astype(bool) & ~((frame['mode'] == 'STRICT') & frame.critical_unknown.astype(bool))
    frame['rankable'] = screened & complete & weights_usable
    frame['rank_status'] = np.where(~screened,'INELIGIBLE',np.where(~complete,'UNRANKED',np.where(not weights_usable,'WEIGHTS_REVIEW_REQUIRED',np.where(frame.conditional,'CONDITIONAL','RANKED'))))
    frame['unranked_reason'] = np.where(~screened,'screening_not_eligible',np.where(~complete,'required_metric_unavailable',np.where(not weights_usable,'inconsistent_ahp_requires_review',None)))
    contributions = values*np.array([weights[k] for k in metric_ids])
    frame['mcda_score'] = np.where(frame.rankable,contributions.sum(axis=1),np.nan)
    frame['weights_used_json'] = json_text(weights)
    frame['contribution_by_metric_json'] = [json_text(dict(zip(metric_ids,row.tolist()))) if valid else '{}' for row,valid in zip(contributions,frame.rankable)]
    for j,metric in enumerate(metric_ids): frame['contribution_'+metric] = np.where(frame.rankable,contributions[:,j],np.nan)
    frame['mcda_rank'] = pd.Series(pd.NA,index=frame.index,dtype='Int64')
    order_columns = ['scenario_id','mcda_score','grid_id','design_id']
    ranked = frame.loc[frame.rankable,order_columns].sort_values(order_columns,ascending=[True,False,True,True],kind='stable')
    for _, group in ranked.groupby('scenario_id',sort=True): frame.loc[group.index,'mcda_rank'] = np.arange(1,len(group)+1)
    return frame.sort_values(KEYS).reset_index(drop=True)
