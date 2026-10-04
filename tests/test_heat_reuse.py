"""Hand-calculated thermal scenarios; no geographic evidence or default savings."""
import pytest


def inputs(**values):
    from dc_locator.model.heat_reuse import HeatReuseInputs
    return HeatReuseInputs(grid_id='fixture',design_id='dry',scenario_id='test',
        basis='project_assumption',rationale='Explicit synthetic hand calculation.',**values)


def test_missing_host_and_factors_stay_unknown():
    from dc_locator.model.heat_reuse import evaluate_heat_reuse
    result=evaluate_heat_reuse(1000.,inputs())
    assert result['delivered_heat_mwh']['value'] is None
    assert result['net_heating_system_avoided_co2e_tonnes']['value'] is None
    assert result['delivered_heat_mwh']['missing_reason']


def test_delivered_heat_is_capped_by_demand_and_auxiliary_emissions_subtracted():
    from dc_locator.model.heat_reuse import evaluate_heat_reuse
    result=evaluate_heat_reuse(1000.,inputs(consumer_name='Synthetic greenhouse',temperature_compatible=True,
        recoverable_fraction=.6,distribution_loss_fraction=.1,annual_heat_demand_mwh=400.,
        annual_auxiliary_electricity_mwh=20.,displaced_heating_kg_co2e_per_mwh=200.,
        auxiliary_electricity_kg_co2e_per_mwh=100.))
    assert result['available_heat_after_losses_mwh']['value']==pytest.approx(540.)
    assert result['delivered_heat_mwh']['value']==400.
    assert result['net_heating_system_avoided_co2e_tonnes']['value']==78.
    assert result['delivered_heat_mwh']['status']=='calculated'
    assert result['input_basis']=='project_assumption'
    assert 'facility' in result['boundary']


def test_incompatible_temperature_is_zero_heat_but_missing_carbon_is_unknown():
    from dc_locator.model.heat_reuse import evaluate_heat_reuse
    result=evaluate_heat_reuse(1000.,inputs(consumer_name='Synthetic host',temperature_compatible=False,
        recoverable_fraction=.6,distribution_loss_fraction=.1,annual_heat_demand_mwh=400.))
    assert result['delivered_heat_mwh']['value']==0.
    assert result['net_heating_system_avoided_co2e_tonnes']['value'] is None


@pytest.mark.parametrize('values',[{'recoverable_fraction':1.1},{'annual_heat_demand_mwh':-1},
    {'recoverable_fraction':True},{'annual_auxiliary_electricity_mwh':float('nan')},
    {'distribution_loss_fraction':float('inf')}])
def test_invalid_factors_are_rejected(values):
    with pytest.raises(ValueError):
        inputs(**values)


def test_documented_factors_require_reference_and_no_false_host_claim():
    from dc_locator.model.heat_reuse import HeatReuseInputs
    with pytest.raises(ValueError,match='reference'):
        HeatReuseInputs(grid_id='a',design_id='b',scenario_id='c',basis='documented_input',rationale='Supplied factors')
