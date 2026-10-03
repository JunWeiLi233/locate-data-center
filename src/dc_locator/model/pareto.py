"""Scenario-separated raw-objective frontier with bounded comparison memory.

No worse: other >= candidate-tolerance in every higher-is-better objective;
strictly better: other > candidate+tolerance in at least one. This tolerance
rule does not claim physical equivalence. Dominated rows remain in output.
"""
import numpy as np
import pandas as pd
import numbers


def pareto_frontier(frame, metric_ids, directions, absolute_tolerances, *, relative_tolerance=0., block_size=256):
    if len(metric_ids) != len(directions) or len(metric_ids) != len(absolute_tolerances) or any(d not in {'minimize','maximize'} for d in directions): raise ValueError('Objective declarations disagree')
    if any(isinstance(v,(bool,np.bool_)) or not isinstance(v,numbers.Real) for v in [*absolute_tolerances,relative_tolerance]): raise ValueError('Tolerances must be numeric, not booleans/strings')
    tolerances = np.asarray(absolute_tolerances,dtype=float)
    if not np.isfinite(tolerances).all() or (tolerances < 0).any() or not np.isfinite(relative_tolerance) or relative_tolerance < 0 or type(block_size) is not int or block_size < 1: raise ValueError('Invalid tolerance/block size')
    result = frame.copy()
    result['is_pareto_optimal'] = pd.Series(pd.NA,index=result.index,dtype='boolean')
    result['pareto_status'] = 'NOT_ASSESSED'
    result['pareto_rank'] = pd.Series(pd.NA,index=result.index,dtype='Int64')
    signs = np.array([-1 if d == 'minimize' else 1 for d in directions])
    valid = result.rankable & np.isfinite(result[metric_ids].to_numpy(dtype=float)).all(axis=1)
    for _,group in result.loc[valid].groupby('scenario_id',sort=True):
        values = group[metric_ids].to_numpy(dtype=float)*signs
        dominated = np.zeros(len(group),dtype=bool)
        for start in range(0,len(group),block_size):
            targets = values[start:start+block_size]
            found = np.zeros(len(targets),dtype=bool)
            for other_start in range(0,len(group),block_size):
                other = values[other_start:other_start+block_size]
                delta = other[:,None,:]-targets[None,:,:]
                tol = tolerances + relative_tolerance*np.maximum(np.abs(other[:,None,:]),np.abs(targets[None,:,:]))
                found |= ((delta >= -tol).all(axis=2) & (delta > tol).any(axis=2)).any(axis=0)
                if found.all(): break
            dominated[start:start+len(targets)] = found
        result.loc[group.index,'is_pareto_optimal'] = ~dominated
        result.loc[group.index,'pareto_status'] = np.where(dominated,'DOMINATED','FRONTIER')
        result.loc[group.index[~dominated],'pareto_rank'] = 0
    return result
