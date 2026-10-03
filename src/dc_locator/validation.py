"""Strict long-feature identity validation for additive integrations."""
import math
import re

import pandas as pd

from dc_locator.schemas import FeatureMetadata


def nullable_record(record):
    """Convert table null scalars to None without modifying the input table."""
    return {k: None if v is None or (pd.api.types.is_scalar(v) and pd.isna(v)) else v
            for k, v in record.items()}


def validate_feature_provenance(provenance, *, grid_ids, data_mode,
        grid_definition_id, provenance_grid_definition_id=None):
    """Validate every row, exact domain and file/grid binding; preserve raw rows.

    File readers must put the verified Parquet grid identity into attrs, or pass
    it explicitly. A matching set of legacy grid IDs alone cannot prove identity.
    """
    identity = provenance_grid_definition_id or provenance.attrs.get('grid_definition_id')
    if not identity or identity != grid_definition_id:
        raise ValueError('Provenance grid_definition_id metadata missing or mismatched')
    if provenance_grid_definition_id and provenance.attrs.get('grid_definition_id', identity) != identity:
        raise ValueError('Explicit provenance identity conflicts with attrs')
    if provenance.attrs.get('data_mode', data_mode) != data_mode or provenance.attrs.get('schema','FeatureMetadata') != 'FeatureMetadata':
        raise ValueError('Provenance file attrs schema/data_mode mismatch')
    if provenance.empty or not {'grid_id', 'metric'} <= set(provenance):
        raise ValueError('Nonempty FeatureMetadata provenance is required')
    if provenance.duplicated(['grid_id', 'metric']).any():
        raise ValueError('Duplicate provenance (grid_id, metric)')
    if set(provenance.grid_id) != set(grid_ids):
        raise ValueError('Provenance grid-id domain differs from geography')
    for row in provenance.to_dict('records'):
        model = FeatureMetadata.model_validate(nullable_record(row))
        version = re.fullmatch(r'1\.(\d+)\.(\d+)', model.schema_version)
        if not version or int(version.group(1)) < 1:
            raise ValueError('FeatureMetadata compatible with 1.1.0 required')
        if model.data_mode.value != data_mode:
            raise ValueError('Provenance data_mode differs from geography')
        if model.value is not None and not math.isfinite(model.value):
            raise ValueError('FeatureMetadata numeric values must be finite')
    return provenance
