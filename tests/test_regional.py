"""Regional delivery contracts; synthetic fixtures remain quarantined."""
from pathlib import Path

import pytest
import pandas as pd
import yaml

from dc_locator.paths import project_root

ROOT = project_root()


def document():
    return yaml.safe_load((ROOT/'configs/run_regional_exploratory.yaml').read_text())


def test_approved_regional_configuration():
    from dc_locator.regional import RegionalConfig
    config = RegionalConfig.model_validate(document())
    assert config.maximum_batch_cells == 2500
    assert config.maximum_region_extent_km == 20
    assert config.selection == 'representative_parent_cells'


@pytest.mark.parametrize('changes', [
    {'maximum_refined_cells': True}, {'maximum_batch_cells': 2501},
    {'maximum_region_extent_km': 0}, {'selection': 'selected_cities'},
    {'basis': 'scientific_threshold'}, {'rationale': ''},
])
def test_regional_rejects_invalid_policy(changes):
    from dc_locator.regional import RegionalConfig
    with pytest.raises(ValueError):
        RegionalConfig.model_validate(dict(document(), **changes))


def test_regional_output_protects_evidence():
    from dc_locator.regional import owned_output
    for path in ['runs/phase7/new', 'runs/orchestrator_new', 'runs/example/new', 'data/processed/refined']:
        with pytest.raises(ValueError):
            owned_output(ROOT, Path(path))
    assert owned_output(ROOT, Path('runs/regional_new')) == ROOT/'runs/regional_new'


def test_regional_cli_uses_approved_wrapper():
    from dc_locator.cli import build_parser
    args = build_parser().parse_args(['refine-regions'])
    assert args.config == 'configs/run_regional_exploratory.yaml'


def test_native_reconciliation_preserves_nullable_integer_global_ranks():
    from dc_locator.regional import _reconcile
    wide = pd.DataFrame(dict(grid_id=['b','a'],design_id=['dry','dry'],scenario_id=['current','current'],
        grid_definition_id=['fine','fine'],mcda_rank=pd.Series([pd.NA,pd.NA],dtype='Int64'),
        metric_metadata_json=['native-b','native-a']))
    global_rows = pd.DataFrame(dict(grid_id=['a','b'],design_id=['dry','dry'],scenario_id=['current','current'],
        grid_definition_id=['fine','fine'],mcda_rank=pd.Series([1,pd.NA],dtype='Int64')))
    actual = _reconcile(wide,global_rows)
    assert str(actual.mcda_rank.dtype) == 'Int64'
    assert actual.mcda_rank.isna().tolist() == [True,False]
    assert actual.mcda_rank.iloc[1] == 1
    assert actual.metric_metadata_json.tolist() == ['native-b','native-a']
