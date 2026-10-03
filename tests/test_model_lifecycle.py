import importlib
import importlib.util

import pandas as pd
import pytest
from dc_locator.schemas import FutureScenarioValue, LifecycleResult


def temporal_fixture(value=100):
    return pd.DataFrame([FutureScenarioValue(grid_id='g',grid_definition_id='fixture',design_id='dry',scenario_id='explicit_static',facility_id='fixture',data_mode='synthetic',model='fixture',period_kind='annual_operating',period_start_year=y,period_end_year=y,variable='c_electricity_kg',value=value,status='calculated' if value is not None else 'unknown',confidence='low' if value is not None else 'unknown',missing_reason=None if value is not None else 'missing_fixture',unit='kg_CO2e',source_id='fixture',coverage_frac=1,source_json='{"source":"synthetic_fixture"}',assumptions_json='{"basis":"project_assumption","rationale":"Synthetic complete annual fixture"}').model_dump(mode='json') for y in range(2030,2055)])


def module():
    assert importlib.util.find_spec('dc_locator.model.lifecycle') is not None
    return importlib.import_module('dc_locator.model.lifecycle')


def test_material_and_transport_hand_units_are_compatible():
    assert module().material_emissions(2,'metric_tonne',1.5,'kg_CO2e_per_kg',required_modules=['A1','A2','A3'],factor_modules=['A1','A2','A3'])['value_kg']==3000
    assert module().material_emissions(3,'m3',100,'kg_CO2e_per_m3',required_modules=['A1','A2','A3'],factor_modules=['A1','A2','A3'])['value_kg']==300
    assert module().transport_emissions(2000,'kg',100,.1,'kg_CO2e_per_metric_tonne_km',mode='fixture_rail')['value_kg']==20
    assert module().transport_emissions(1,'US_short_ton',100,1,'kg_CO2e_per_metric_tonne_km',mode='fixture_road')['value_kg']==pytest.approx(90.718474)


@pytest.mark.parametrize('call,args,kwargs',[
    ('material_emissions',(2,'m3',1,'kg_CO2e_per_kg'),dict(required_modules=['A1'],factor_modules=['A1'])),
    ('material_emissions',(2,'kg',1,'kg_CO2e_per_kg'),dict(required_modules=['A1','A3'],factor_modules=['A1'])),
    ('material_emissions',(-2,'kg',1,'kg_CO2e_per_kg'),dict(required_modules=['A1'],factor_modules=['A1'])),
    ('material_emissions',(2,'kg',float('inf'),'kg_CO2e_per_kg'),dict(required_modules=['A1'],factor_modules=['A1'])),
    ('transport_emissions',(1,'m3',100,1,'kg_CO2e_per_metric_tonne_km'),dict(mode='fixture_rail')),
    ('transport_emissions',(1,'kg',100,1,'kg_CO2e_per_metric_tonne_km'),dict(mode='fixture_rail',factor_mode='fixture_road')),
])
def test_incompatible_units_boundaries_nonfinite_and_modes_fail(call,args,kwargs):
    with pytest.raises(ValueError): getattr(module(),call)(*args,**kwargs)


def test_missing_factor_stays_unknown_even_for_zero_quantity():
    result=module().material_emissions(0,'kg',None,'kg_CO2e_per_kg',required_modules=['A1'],factor_modules=['A1'])
    assert result['status']=='unknown' and result['value_kg'] is None


def test_epd_a4_transport_double_count_requires_documented_separate_leg():
    with pytest.raises(ValueError,match='A4'):
        module().transport_emissions(1000,'kg',100,.1,'kg_CO2e_per_metric_tonne_km',mode='fixture_rail',epd_modules=['A1','A2','A3','A4'])
    separate=dict(leg_id='extra_factory_transfer',epd_a4_leg_id='factory_to_site',rationale='Synthetic additional transfer; EPD A4 covers only factory_to_site')
    assert module().transport_emissions(1000,'kg',100,.1,'kg_CO2e_per_metric_tonne_km',mode='fixture_rail',epd_modules=['A1','A2','A3','A4'],separate_leg=separate)['value_kg']==10
    separate['leg_id']='factory_to_site'
    with pytest.raises(ValueError): module().transport_emissions(1000,'kg',100,.1,'kg_CO2e_per_metric_tonne_km',mode='fixture_rail',epd_modules=['A4'],separate_leg=separate)


def test_real_style_missing_inventory_yields_only_named_partial_subtotal():
    temporal=temporal_fixture()
    row=module().calculate_lifecycle(temporal,opening_year=2030,lifetime_years=25).iloc[0]
    assert row.operations_electricity_kg==2500
    assert pd.isna(row.operations_kg) and pd.isna(row.construction_kg)
    assert pd.isna(row.total_lifecycle_kg)
    assert row.known_subtotal_partial_kg==2500
    assert row.status=='unknown' and row.known_leaf_count==1
    temporal.loc[0,'value']=None; temporal.loc[0,'status']='unknown'
    temporal.loc[0,'confidence']='unknown'; temporal.loc[0,'missing_reason']='missing_fixture'
    row=module().calculate_lifecycle(temporal,opening_year=2030,lifetime_years=25).iloc[0]
    assert pd.isna(row.operations_electricity_kg)
    assert row.operations_electricity_known_subtotal_kg==2400
    assert row.known_subtotal_partial_kg==2400


def test_empty_missing_all_components_never_reports_known_zero():
    with pytest.raises(ValueError): module().calculate_lifecycle(pd.DataFrame(),opening_year=2030,lifetime_years=25)
    row=module().calculate_lifecycle(temporal_fixture(None),opening_year=2030,lifetime_years=25).iloc[0]
    assert pd.isna(row.known_subtotal_partial_kg) and pd.isna(row.total_lifecycle_kg)
    assert row.known_leaf_count==0 and row.status=='unknown'


def test_explicit_known_zero_electricity_is_retained_as_known_leaf():
    row=module().calculate_lifecycle(temporal_fixture(0),opening_year=2030,lifetime_years=25).iloc[0]
    assert row.operations_electricity_kg==0 and row.known_subtotal_partial_kg==0
    assert row.known_leaf_count==1 and pd.isna(row.total_lifecycle_kg)


def inventory_fixture():
    item=dict(item_id='concrete_fixture',component='construction',quantity=3,quantity_unit='m3',factor_value=100,factor_unit='kg_CO2e_per_m3',required_modules=['A1','A2','A3'],factor_modules=['A1','A2','A3'],source_id='synthetic_epd',product_id='fixture_concrete')
    leg=dict(leg_id='fixture_factory_to_site',inventory_item_id=item['item_id'],mass=2000,mass_unit='kg',distance_km=100,factor_value=.1,factor_unit='kg_CO2e_per_metric_tonne_km',mode='fixture_rail',source_id='synthetic_freight',distance_basis='Synthetic hand calculation route')
    return item,leg


def test_volume_product_with_explicit_independent_freight_mass_and_complete_accounting():
    item,leg=inventory_fixture()
    zeros={c:dict(value_kg=0,status='scenario',source_id='synthetic_known_zero',basis='project_assumption',rationale='Synthetic complete fixture explicitly asserts zero',accounting_modules=module().COMPONENT_BOUNDARY[c]) for c in ['equipment','operations_other','replacements','end_of_life']}
    item['required_modules']=item['factor_modules']=['A1','A2','A3','A5']
    row=module().calculate_lifecycle(temporal_fixture(),opening_year=2030,lifetime_years=25,inventory=[item],transport_legs=[leg],complete_components=['construction'],component_evidence=zeros).iloc[0]
    assert row.construction_kg==320 and row.operations_kg==2500
    assert row.total_lifecycle_kg==2820 and row.status=='calculated'
    del leg['mass']
    with pytest.raises(ValueError,match='independent mass'):
        module().calculate_lifecycle(temporal_fixture(),opening_year=2030,lifetime_years=25,inventory=[item],transport_legs=[leg])


def test_inventory_cannot_duplicate_operating_electricity_or_mix_products():
    item,_=inventory_fixture(); item['required_modules']=item['factor_modules']=['B6']
    with pytest.raises(ValueError,match='B6'):
        module().calculate_lifecycle(temporal_fixture(),opening_year=2030,lifetime_years=25,inventory=[item])
    item,_=inventory_fixture(); item['factor_product_id']='different_product'
    with pytest.raises(ValueError,match='Product factor identity'):
        module().calculate_lifecycle(temporal_fixture(),opening_year=2030,lifetime_years=25,inventory=[item])


def test_duplicate_temporal_and_overflow_fail_loud():
    t=temporal_fixture()
    with pytest.raises(ValueError,match='Duplicate'):
        module().calculate_lifecycle(pd.concat([t,t]),opening_year=2030,lifetime_years=25)
    with pytest.raises(ValueError,match='overflow'):
        module().material_emissions(1e308,'metric_tonne',1e308,'kg_CO2e_per_kg',required_modules=['A1'],factor_modules=['A1'])


@pytest.mark.parametrize('fault',['coverage','source','assumptions','typo_scope','unmatched_scope'])
def test_lifecycle_rejects_forged_temporal_or_unused_inventory(fault):
    t=temporal_fixture(); item,_=inventory_fixture()
    if fault=='coverage': t['coverage_frac']=0
    elif fault=='source': t['source_id']=None
    elif fault=='assumptions': t['assumptions_json']='{}'
    elif fault=='typo_scope': item['desgin_id']='typo'
    else: item['design_id']='not_evaluated'
    with pytest.raises(ValueError): module().calculate_lifecycle(t,opening_year=2030,lifetime_years=25,inventory=[item])


def test_complete_inventory_flag_does_not_fill_missing_accounting_modules():
    item,_=inventory_fixture(); item['required_modules']=item['factor_modules']=['A1']
    row=module().calculate_lifecycle(temporal_fixture(),opening_year=2030,lifetime_years=25,inventory=[item],complete_components=['construction']).iloc[0]
    assert pd.isna(row.construction_kg) and pd.isna(row.total_lifecycle_kg)
    assert 'A5' in row.component_metadata_json and 'component_modules' in row.accounting_boundary_json


@pytest.mark.parametrize('component,accounting',[('replacements','B4'),('end_of_life','C2')])
def test_replacement_and_end_of_life_freight_cannot_duplicate_included_module(component,accounting):
    item,leg=inventory_fixture();item.update(component=component,quantity_unit='kg',factor_unit='kg_CO2e_per_kg',required_modules=[accounting],factor_modules=[accounting])
    with pytest.raises(ValueError,match='distinct separate leg'):
        module().calculate_lifecycle(temporal_fixture(),opening_year=2030,lifetime_years=25,inventory=[item],transport_legs=[leg])


@pytest.mark.parametrize('fault',['bad_boundary_json','wrong_unknown','wrong_required','wrong_subtotal','wrong_operations'])
def test_persisted_lifecycle_schema_rejects_forged_accounting(fault):
    row=module().calculate_lifecycle(temporal_fixture(),opening_year=2030,lifetime_years=25).iloc[0].to_dict()
    if fault=='bad_boundary_json':row['accounting_boundary_json']='not-json'
    elif fault=='wrong_unknown':row['unknown_components_json']='[]'
    elif fault=='wrong_required':row['required_components_json']='[]'
    elif fault=='wrong_subtotal':row['known_subtotal_partial_kg']=1
    else:row['operations_kg']=999
    from dc_locator.validation import nullable_record
    with pytest.raises(ValueError):LifecycleResult.model_validate(nullable_record(row))


def test_complete_persisted_lifecycle_total_and_partial_must_match_components():
    zeros={c:dict(value_kg=0,status='scenario',source_id='synthetic_known_zero',basis='project_assumption',rationale='Synthetic complete fixture explicitly asserts zero',accounting_modules=module().COMPONENT_BOUNDARY[c]) for c in ['construction','equipment','operations_other','replacements','end_of_life']}
    row=module().calculate_lifecycle(temporal_fixture(),opening_year=2030,lifetime_years=25,component_evidence=zeros).iloc[0].to_dict()
    assert row['total_lifecycle_kg']==2500
    for key in ['total_lifecycle_kg','known_subtotal_partial_kg']:
        bad=dict(row);bad[key]=1
        with pytest.raises(ValueError):LifecycleResult.model_validate(bad)


@pytest.mark.parametrize('fault',['unit_without_mass','mass_without_unit'])
def test_freight_mass_and_unit_fallback_are_an_inseparable_pair(fault):
    item,leg=inventory_fixture();item.update(quantity=1000,quantity_unit='kg',factor_unit='kg_CO2e_per_kg')
    if fault=='unit_without_mass':leg.pop('mass');leg['mass_unit']='metric_tonne'
    else:leg.pop('mass_unit')
    with pytest.raises(ValueError,match='supplied together'):
        module().calculate_lifecycle(temporal_fixture(),opening_year=2030,lifetime_years=25,inventory=[item],transport_legs=[leg])


def test_inventory_accounting_override_cannot_claim_uncovered_factor_modules():
    item,_=inventory_fixture();item['required_modules']=item['factor_modules']=['A1']
    item['accounting_modules']=['A1','A2','A3','A4','A5']
    with pytest.raises(ValueError,match='exactly equal the factor boundary'):
        module().calculate_lifecycle(temporal_fixture(),opening_year=2030,lifetime_years=25,inventory=[item],complete_components=['construction'])


def test_component_evidence_rejects_boolean_emissions_and_preserves_known_zero():
    evidence=dict(value_kg=True,status='scenario',source_id='fixture',basis='project_assumption',rationale='Synthetic explicit component evidence',accounting_modules=['A1'])
    with pytest.raises(ValueError):module().ComponentEvidence.model_validate(evidence)
    evidence['value_kg']=0
    assert module().ComponentEvidence.model_validate(evidence).value_kg==0
