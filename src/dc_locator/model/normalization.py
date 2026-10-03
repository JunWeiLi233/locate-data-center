"""Fixed-reference 0–100 values; constants retain their declared value."""
import numpy as np
import numbers


def normalize_values(values, low, high, direction):
    if any(isinstance(v,(bool,np.bool_)) or not isinstance(v,numbers.Real) for v in (low,high)) or not np.isfinite([low,high]).all() or low >= high or not np.isfinite(high-low) or direction not in {'minimize','maximize'}:
        raise ValueError('Finite increasing references and valid direction are required')
    values = np.asarray(values,dtype=float)
    finite = np.isfinite(values)
    clipped = np.clip(values,low,high)
    normalized = 100*(clipped-low)/(high-low)
    if direction == 'minimize': normalized = 100-normalized
    normalized[~finite] = np.nan
    status = np.full(values.shape,'within_reference',dtype=object)
    status[values < low] = 'clipped_low'
    status[values > high] = 'clipped_high'
    status[~finite] = 'missing'
    return normalized,status
