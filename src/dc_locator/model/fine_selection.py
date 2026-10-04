"""Score the national 1 km screening surface with the declared profile and select refinement parents.

The surface reproduces the regional decision value of each 1 km cell/design/scenario alternative from
national fine features: the profile's fixed-reference normalization and resolved weights, with any metric
Unknown (missing or below its declared minimum coverage) leaving the alternative unscored, never zero.
Screening is not applied here; selected parents are re-screened in full by regional refinement.
"""
from __future__ import annotations

import json
import numpy as np
import pandas as pd

from dc_locator.model.decision import _weights
from dc_locator.model.mcda import user_weights
from dc_locator.model.metrics import ScoringProfile, json_text
from dc_locator.model.normalization import normalize_values

FINE_SELECTION_VERSION = 'national-fine-selection-v2'
# Coverage evidence per profile source, as in geography/features.py coverage resolution.
COVERAGE = {'potentially_suitable_land_frac': 'nlcd_coverage_frac',
            'baseline_water_stress_score': 'baseline_water_stress_score_coverage_frac',
            'grid_carbon_intensity_kg_per_mwh': 'egrid_coverage_frac', 'c_electricity_tonnes': 'egrid_coverage_frac'}
PERFORMANCE_COLUMNS = {'c_electricity_tonnes', 'w_site_m3'}


def profile_weights(profile: ScoringProfile) -> dict[str, float]:
    """The decision weights regional ranking resolves for this profile; inconsistent AHP is refused."""
    weights, _, ahp_result, _ = _weights(profile, pd.DataFrame(columns=['raw_' + metric.metric_id for metric in profile.metrics]))
    if ahp_result is not None and ahp_result.get('status') == 'REVIEW_REQUIRED':
        raise ValueError('AHP preferences require review; the national fine surface cannot rank parents')
    return user_weights(weights, profile.metric_ids)


def design_constants(performance: pd.DataFrame) -> pd.DataFrame:
    """Per design/scenario facility energy and site water from national physics, required location independent.

    Annual PUE and WUE are scenario constants, so facility energy and direct site water do not vary by cell;
    carbon then scales with grid intensity alone. Any location dependence refuses the fast surface.
    """
    rows = []
    for (design, scenario), group in performance.groupby(['design_id', 'scenario_id'], sort=True):
        record = {'design_id': design, 'scenario_id': scenario}
        for column in ('e_facility_mwh', 'w_site_m3'):
            values = pd.to_numeric(group[column], errors='coerce')
            distinct = values.dropna().unique()
            if len(distinct) > 1 or (len(distinct) == 1 and values.isna().any()):
                raise ValueError(f'{column} varies by location for {design}/{scenario}; the national fine surface requires location-independent design physics')
            record[column] = float(distinct[0]) if len(distinct) else np.nan
            metadata = [json.loads(value).get(column, {}) for value in group.get('metric_metadata_json', pd.Series(['{}'] * len(group)))]
            for field in ('status', 'confidence', 'unit'):
                evidence = {item.get(field) for item in metadata}
                record[column + '_' + field] = next(iter(evidence)) if len(evidence) == 1 else None
        # The fine geography factor must agree with the declared external scenario's source year.
        years = {json.loads(value).get('external_scenario', {}).get('carbon_data_year')
                 for value in group.get('assumptions_json', pd.Series(['{}'] * len(group)))}
        record['carbon_data_year'] = next(iter(years)) if len(years) == 1 else None
        rows.append(record)
    if not rows:
        raise ValueError('National physics provides no design/scenario alternatives')
    return pd.DataFrame(rows)


def score_window(features: pd.DataFrame, profile: ScoringProfile, weights: dict[str, float], constants: pd.DataFrame) -> pd.DataFrame:
    """Decision value of every cell alternative in one window; NaN when any required metric is Unknown."""
    unknown_columns = {metric.column for metric in profile.metrics} - PERFORMANCE_COLUMNS - set(features.columns)
    if unknown_columns:
        raise ValueError(f'The national fine surface cannot compute profile columns {sorted(unknown_columns)}')
    frames = []
    for constant in constants.itertuples(index=False):
        raw = {'c_electricity_tonnes': constant.e_facility_mwh * features.grid_carbon_intensity_kg_per_mwh.to_numpy() / 1000.0,
               'w_site_m3': np.full(len(features), constant.w_site_m3)}
        score = np.zeros(len(features))
        known = np.ones(len(features), dtype=bool)
        reasons = np.full(len(features), '', dtype=object)
        for metric in profile.metrics:
            values = raw[metric.column] if metric.column in raw else features[metric.column].to_numpy(dtype=float)
            normalized, _ = normalize_values(values, metric.reference_low, metric.reference_high, metric.direction)
            available = np.isfinite(normalized)
            source_column = 'grid_carbon_intensity_kg_per_mwh' if metric.column == 'c_electricity_tonnes' else metric.column
            if metric.table == 'geography' or metric.column == 'c_electricity_tonnes':
                def companion(field):
                    return features.get(source_column + '_' + field, pd.Series(None, index=features.index, dtype=object))
                source_status = companion('status')
                available &= companion('confidence').isin(['high', 'medium', 'low']).to_numpy()
                available &= companion('missing_reason').isna().to_numpy()
                allowed = ['observed', 'calculated', 'scenario', 'proxy'] if metric.column == 'c_electricity_tonnes' else metric.allowed_statuses
                available &= source_status.isin(allowed).to_numpy()
                available &= companion('unit').eq('kg_CO2e_per_mwh' if metric.column == 'c_electricity_tonnes' else metric.unit).to_numpy()
                if metric.source_id:
                    available &= companion('source_id').eq(metric.source_id).to_numpy()
                if metric.source_field:
                    available &= companion('source_field').eq(metric.source_field).to_numpy()
            if metric.table == 'performance':
                input_column = 'e_facility_mwh' if metric.column == 'c_electricity_tonnes' else 'w_site_m3'
                available &= (getattr(constant, input_column + '_status', None) == 'calculated'
                    and getattr(constant, input_column + '_confidence', None) in {'high', 'medium', 'low'}
                    and getattr(constant, input_column + '_unit', None) == ('mwh' if input_column == 'e_facility_mwh' else metric.unit)
                    and 'calculated' in metric.allowed_statuses)
                if metric.column == 'c_electricity_tonnes':
                    available &= companion('data_year').eq(getattr(constant, 'carbon_data_year', None)).to_numpy()
                    # Native annual physics refuses partially covered carbon even with a weaker decision policy.
                    available &= features.egrid_coverage_frac.ge(1 - 1e-6).to_numpy()
            if metric.minimum_coverage_frac is not None:
                coverage = features[COVERAGE[metric.column]].to_numpy(dtype=float) if metric.column in COVERAGE else np.zeros(len(features))
                available &= np.isfinite(coverage) & (coverage >= metric.minimum_coverage_frac)
            known &= available  # mcda.score_alternatives ranks only alternatives with every metric known
            reasons = np.where(available, reasons, reasons + metric.metric_id + ';')
            score += weights[metric.metric_id] * np.where(available, normalized, 0.0)
        frames.append(pd.DataFrame({'design_id': constant.design_id, 'scenario_id': constant.scenario_id,
                                    'fine_score': np.where(known, score, np.nan),
                                    'unscored_reason': pd.Series(reasons, index=features.index).str.rstrip(';').replace('', None)}, index=features.index))
    return pd.concat(frames)


def summarize_window(parent_grid_id: str, grid_ids: pd.Series, scores: pd.DataFrame) -> pd.DataFrame:
    """Best scored cell, scored count and 90th-percentile value per parent alternative (ties: smallest grid_id)."""
    rows = []
    for (design, scenario), group in scores.groupby(['design_id', 'scenario_id'], sort=True):
        values = group.fine_score.to_numpy()
        scored = np.isfinite(values)
        record = dict(parent_grid_id=parent_grid_id, design_id=design, scenario_id=scenario, cells=int(len(values)),
                      scored_cells=int(scored.sum()), best_fine_score=np.nan, best_grid_id=None, p90_fine_score=np.nan)
        if scored.any():
            ids = grid_ids.loc[group.index].to_numpy()[scored]
            order = np.lexsort((ids, -values[scored]))
            record.update(best_fine_score=float(values[scored][order[0]]), best_grid_id=str(ids[order[0]]),
                          p90_fine_score=float(np.percentile(values[scored], 90)))
        rows.append(record)
    return pd.DataFrame(rows)


def select_parents_by_surface(parent_grid, summary: pd.DataFrame, limit: int):
    """The ``limit`` parents with the highest best fine score (ties: grid_id), returned in grid order."""
    if limit < 1:
        raise ValueError('The refinement budget admits no full parent window')
    if summary.scenario_id.isna().any() or summary.scenario_id.nunique() != 1:
        raise ValueError('Current national fine selection requires one external scenario; optimizers cannot choose a scenario')
    best = summary.dropna(subset=['best_fine_score']).sort_values(
        ['best_fine_score', 'parent_grid_id', 'design_id', 'scenario_id'], ascending=[False, True, True, True], kind='stable')
    best = best.drop_duplicates('parent_grid_id').head(limit).reset_index(drop=True)
    if best.empty:
        raise ValueError('The national fine surface scored no parent window')
    best['fine_selection_rank'] = np.arange(1, len(best) + 1)
    chosen = best.rename(columns={'parent_grid_id': 'grid_id', 'design_id': 'fine_best_design_id', 'scenario_id': 'fine_best_scenario_id',
                                  'best_grid_id': 'fine_best_grid_id'})[['grid_id', 'fine_selection_rank', 'best_fine_score', 'fine_best_grid_id',
                                                                         'fine_best_design_id', 'fine_best_scenario_id']]
    if not set(chosen.grid_id) <= set(parent_grid.grid_id):
        raise ValueError('Fine surface parents do not match the national grid')
    selected = parent_grid.merge(chosen, on='grid_id', how='inner', validate='one_to_one')
    return selected.sort_values('grid_id').reset_index(drop=True)


def select_region_best_parents(parent_grid, summary: pd.DataFrame, regions: pd.DataFrame, membership: pd.DataFrame):
    """One parent per national region: the member with the highest best fine value, returned in grid order.

    National discovery regions stay the unit of choice, so refinement keeps their geographic spread. Within a
    region the fine surface replaces the 50 km representative with the member parent whose 1 km alternatives
    score highest; ties keep the representative, and a region without a scored member keeps it too. Regions
    are grouped by representative, which merges the cooling-design variants of one national region.
    """
    if summary.scenario_id.isna().any() or summary.scenario_id.nunique() != 1:
        raise ValueError('Current national fine selection requires one external scenario; optimizers cannot choose a scenario')
    best = summary.dropna(subset=['best_fine_score']).sort_values(
        ['best_fine_score', 'parent_grid_id', 'design_id', 'scenario_id'], ascending=[False, True, True, True], kind='stable')
    best = best.drop_duplicates('parent_grid_id').set_index('parent_grid_id')
    groups = membership[['region_id', 'grid_id']].merge(regions[['region_id', 'representative_grid_id']], on='region_id', validate='many_to_one')
    choices = {}
    for representative, group in groups.groupby('representative_grid_id', sort=True):
        scores = best.best_fine_score.reindex(sorted(set(group.grid_id) | {representative})).dropna()
        tied = sorted(scores.index[scores == scores.max()]) if len(scores) else []
        choice = representative if not tied or representative in tied else tied[0]
        basis = 'representative_unscored' if not tied else 'representative' if choice == representative else 'fine_surface'
        record = choices.setdefault(choice, dict(grid_id=choice, fine_region_representative=representative,
                                                 fine_region_selection_basis=basis, region_ids=set()))
        record['region_ids'] |= set(group.region_id)
    if not choices:
        raise ValueError('National discovery supplied no regions for fine parent selection')
    chosen = pd.DataFrame([{**{key: value for key, value in record.items() if key != 'region_ids'},
                            'national_region_ids_json': json_text(sorted(record['region_ids']))} for record in choices.values()])
    if not set(chosen.grid_id) <= set(parent_grid.grid_id):
        raise ValueError('Fine region parents do not match the national grid')
    fine = best.reindex(chosen.grid_id)
    chosen['best_fine_score'] = fine.best_fine_score.to_numpy()
    chosen['fine_best_grid_id'] = fine.best_grid_id.to_numpy()
    chosen['fine_best_design_id'] = fine.design_id.to_numpy()
    chosen['fine_best_scenario_id'] = fine.scenario_id.to_numpy()
    order = chosen.sort_values(['best_fine_score', 'grid_id'], ascending=[False, True], na_position='last', kind='stable').index
    chosen.loc[order, 'fine_selection_rank'] = np.arange(1, len(chosen) + 1)
    chosen['fine_selection_rank'] = chosen.fine_selection_rank.astype(int)
    selected = parent_grid.merge(chosen, on='grid_id', how='inner', validate='one_to_one')
    return selected.sort_values('grid_id').reset_index(drop=True)
