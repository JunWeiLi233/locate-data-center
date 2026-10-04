"""Scenario-separated raw-objective frontier with bounded comparison memory.

No worse: other >= candidate-tolerance in every higher-is-better objective;
strictly better: other > candidate+tolerance in at least one. This tolerance
rule does not claim physical equivalence. Dominated rows remain in output.
"""
import numpy as np
import pandas as pd
import numbers
from dataclasses import dataclass


def _block_dominated(values,tolerances,relative_tolerance,block_size):
    """Original bounded all-pairs implementation, retained as an exact oracle."""
    dominated = np.zeros(len(values),dtype=bool)
    for start in range(0,len(values),block_size):
        targets = values[start:start+block_size]
        found = np.zeros(len(targets),dtype=bool)
        for other_start in range(0,len(values),block_size):
            other = values[other_start:other_start+block_size]
            delta = other[:,None,:]-targets[None,:,:]
            tol = tolerances + relative_tolerance*np.maximum(np.abs(other[:,None,:]),np.abs(targets[None,:,:]))
            found |= ((delta >= -tol).all(axis=2) & (delta > tol).any(axis=2)).any(axis=0)
            if found.all(): break
        dominated[start:start+len(targets)] = found
    return dominated


@dataclass(slots=True)
class _ObjectiveNode:
    lower: np.ndarray
    upper: np.ndarray
    indices: np.ndarray | None = None
    left: '_ObjectiveNode | None' = None
    right: '_ObjectiveNode | None' = None


def _objective_tree(values,indices,leaf_size,depth=0):
    lower=values[indices].min(axis=0);upper=values[indices].max(axis=0)
    if len(indices)<=leaf_size:
        return _ObjectiveNode(lower,upper,indices=indices)
    # Cyclic axes and stable median splits change traversal only, never policy.
    dimensions=values.shape[1]
    axis=next((depth+i)%dimensions for i in range(dimensions) if lower[(depth+i)%dimensions]!=upper[(depth+i)%dimensions])
    ordered=indices[np.argsort(values[indices,axis],kind='stable')]
    middle=len(ordered)//2
    return _ObjectiveNode(lower,upper,
        left=_objective_tree(values,ordered[:middle],leaf_size,depth+1),
        right=_objective_tree(values,ordered[middle:],leaf_size,depth+1))


def _tree_dominated(values,tolerances,relative_tolerance,block_size):
    """Conservative node pruning followed by the unchanged exact pair formula.

    All comparable vectors remain potential witnesses, including dominated
    vectors: tolerance dominance is not transitive. Only exact duplicates share
    calculations. Bounds support every accepted nonnegative relative tolerance.
    """
    if values.shape[1]==0 or len(values)==0:
        return np.zeros(len(values),dtype=bool)
    unique,inverse=np.unique(values,axis=0,return_inverse=True)
    if len(unique)==1:
        return np.zeros(len(values),dtype=bool)
    tree=_objective_tree(unique,np.arange(len(unique)),min(block_size,128))
    dominated=np.zeros(len(unique),dtype=bool)
    for start in range(0,len(unique),block_size):
        targets=unique[start:start+block_size]
        found=np.zeros(len(targets),dtype=bool)
        pending=[(tree,np.arange(len(targets)))]
        while pending:
            node,active=pending.pop()
            active=active[~found[active]]
            if not len(active):continue
            selected=targets[active]
            delta_max=node.upper-selected
            max_abs=np.maximum(np.abs(node.lower),np.abs(node.upper))
            min_abs=np.where((node.lower<=0)&(node.upper>=0),0.,np.minimum(np.abs(node.lower),np.abs(node.upper)))
            tol_upper=tolerances+relative_tolerance*np.maximum(max_abs,np.abs(selected))
            tol_lower=tolerances+relative_tolerance*np.maximum(min_abs,np.abs(selected))
            possible=(delta_max>=-tol_upper).all(axis=1)&(delta_max>tol_lower).any(axis=1)
            active=active[possible]
            if not len(active):continue
            if node.indices is None:
                pending.append((node.left,active))
                pending.append((node.right,active))
                continue
            other=unique[node.indices]
            selected=targets[active]
            delta=other[:,None,:]-selected[None,:,:]
            tol=tolerances+relative_tolerance*np.maximum(np.abs(other[:,None,:]),np.abs(selected[None,:,:]))
            found[active]|=((delta>=-tol).all(axis=2)&(delta>tol).any(axis=2)).any(axis=0)
        dominated[start:start+len(targets)]=found
    return dominated[inverse]


def pareto_frontier(frame, metric_ids, directions, absolute_tolerances, *, relative_tolerance=0., block_size=256, algorithm='auto'):
    if len(metric_ids) != len(directions) or len(metric_ids) != len(absolute_tolerances) or any(d not in {'minimize','maximize'} for d in directions): raise ValueError('Objective declarations disagree')
    if any(isinstance(v,(bool,np.bool_)) or not isinstance(v,numbers.Real) for v in [*absolute_tolerances,relative_tolerance]): raise ValueError('Tolerances must be numeric, not booleans/strings')
    tolerances = np.asarray(absolute_tolerances,dtype=float)
    if not np.isfinite(tolerances).all() or (tolerances < 0).any() or not np.isfinite(relative_tolerance) or relative_tolerance < 0 or type(block_size) is not int or block_size < 1: raise ValueError('Invalid tolerance/block size')
    if algorithm not in {'auto','block','tree'}:raise ValueError('Unknown Pareto comparison algorithm')
    result = frame.copy()
    result['is_pareto_optimal'] = pd.Series(pd.NA,index=result.index,dtype='boolean')
    result['pareto_status'] = 'NOT_ASSESSED'
    result['pareto_rank'] = pd.Series(pd.NA,index=result.index,dtype='Int64')
    signs = np.array([-1 if d == 'minimize' else 1 for d in directions])
    valid = result.rankable & np.isfinite(result[metric_ids].to_numpy(dtype=float)).all(axis=1)
    for _,group in result.loc[valid].groupby('scenario_id',sort=True):
        values = group[metric_ids].to_numpy(dtype=float)*signs
        compare=_tree_dominated if algorithm=='tree' or (algorithm=='auto' and len(values)>2048) else _block_dominated
        dominated=compare(values,tolerances,relative_tolerance,block_size)
        result.loc[group.index,'is_pareto_optimal'] = ~dominated
        result.loc[group.index,'pareto_status'] = np.where(dominated,'DOMINATED','FRONTIER')
        result.loc[group.index[~dominated],'pareto_rank'] = 0
    return result
