"""Quantity/factor and freight accounting; no invented real project inventory.

Gross kg CO2e are additive only across documented, nonoverlapping accounting
modules. Credits, densities, plant-proximity delivery distances and absent EPDs
are never inferred. A known partial subtotal is not a full lifecycle result.
"""
import json
import math

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing import Literal

from dc_locator.schemas import FutureScenarioValue, LifecycleResult
from dc_locator.validation import nullable_record

MASS_KG = {'kg': 1., 'metric_tonne': 1000., 'US_short_ton': 907.18474}
PRODUCT_UNITS = {'kg_CO2e_per_kg': ('mass', 1.),
    'kg_CO2e_per_metric_tonne': ('mass', 1000.),
    'kg_CO2e_per_US_short_ton': ('mass', 907.18474),
    'kg_CO2e_per_m3': ('volume', 1.), 'kg_CO2e_per_item': ('count', 1.)}
TRANSPORT_UNITS = {'kg_CO2e_per_metric_tonne_km': 1000.,
    'kg_CO2e_per_kg_km': 1., 'kg_CO2e_per_US_short_ton_km': 907.18474}
COMPONENTS = ('construction', 'equipment', 'operations', 'replacements', 'end_of_life')
INVENTORY_COMPONENTS = {'construction', 'equipment', 'replacements', 'end_of_life'}
MODULES = {f'A{i}' for i in range(1, 6)} | {f'B{i}' for i in range(1, 8)} | {f'C{i}' for i in range(1, 5)}
COMPONENT_BOUNDARY = {'construction': ['A1','A2','A3','A4','A5'],
    'equipment': ['A1','A2','A3','A4','A5'], 'operations_electricity': ['B6'],
    'operations_other': ['B1','B2','B3','B7'], 'replacements': ['B4','B5'],
    'end_of_life': ['C1','C2','C3','C4']}


class ScopedInput(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    grid_id: str | None = None
    design_id: str | None = None
    scenario_id: str | None = None
    facility_id: str | None = None
    grid_definition_id: str | None = None
    data_mode: Literal['real','synthetic'] | None = None


class InventoryItem(ScopedInput):
    item_id: str = Field(min_length=1)
    component: Literal['construction','equipment','replacements','end_of_life']
    quantity: float | None
    quantity_unit: str
    factor_value: float | None
    factor_unit: str
    required_modules: list[str]
    factor_modules: list[str]
    accounting_modules: list[str] | None = None
    source_id: str = Field(min_length=1)
    product_id: str = Field(min_length=1)
    factor_product_id: str | None = None
    source_version: str | None = None
    reference: str | None = None
    basis: str | None = None
    rationale: str | None = None

    @field_validator('quantity','factor_value',mode='before')
    @classmethod
    def numeric(cls, value): return _number(value, 'inventory quantity/factor')


class TransportLeg(ScopedInput):
    leg_id: str = Field(min_length=1)
    inventory_item_id: str = Field(min_length=1)
    mass: float | None = None
    mass_unit: str | None = None
    distance_km: float | None
    factor_value: float | None
    factor_unit: str
    mode: str
    factor_mode: str | None = None
    source_id: str = Field(min_length=1)
    distance_basis: str = Field(min_length=1)
    separate_leg: dict | None = None
    reference: str | None = None
    source_version: str | None = None
    basis: str | None = None
    rationale: str | None = None

    @field_validator('mass','distance_km','factor_value',mode='before')
    @classmethod
    def numeric(cls, value): return _number(value, 'freight quantity/factor')

    @model_validator(mode='after')
    def paired_mass_unit(self):
        if (self.mass is None)!=(self.mass_unit is None):
            raise ValueError('independent mass and mass_unit must be supplied together; fallback uses both inventory fields')
        return self


class ComponentEvidence(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    value_kg: float = Field(ge=0)
    status: Literal['observed','calculated','scenario']
    source_id: str = Field(min_length=1)
    basis: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    accounting_modules: list[str]
    reference: str | None = None

    @field_validator('value_kg',mode='before')
    @classmethod
    def numeric(cls,value): return _number(value, 'component value_kg')


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _number(value, name):
    if value is None: return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(name+' must be finite nonnegative numeric input')
    return float(value)


def _modules(values, name):
    if not isinstance(values, (list, tuple)) or not values or len(set(values)) != len(values) or not set(values) <= MODULES:
        raise ValueError(name+' requires unique explicit A/B/C accounting modules; credits unsupported')
    return set(values)


def _result(value, method, evidence, reason=None):
    if value is not None and not math.isfinite(value):
        raise ValueError('Finite inputs overflowed lifecycle output')
    return dict(value_kg=value, unit='kg_CO2e', status='calculated' if value is not None else 'unknown',
        missing_reason=reason if value is None else None, method=method, evidence=evidence)


def material_emissions(quantity, quantity_unit, factor_value, factor_unit, *, required_modules, factor_modules):
    """Compatible physical quantity × product factor, in gross kg CO2e.

    Exact module equality prevents stripping or silently adding modules already
    included in an EPD. Quantity 0 with a missing factor remains UNKNOWN.
    """
    required, provided = _modules(required_modules, 'required_modules'), _modules(factor_modules, 'factor_modules')
    if required != provided:
        raise ValueError('Product factor system boundary does not exactly match required accounting modules')
    if factor_unit not in PRODUCT_UNITS: raise ValueError('Unsupported product factor unit')
    family, denominator = PRODUCT_UNITS[factor_unit]
    quantity_family = 'mass' if quantity_unit in MASS_KG else {'m3': 'volume', 'item': 'count'}.get(quantity_unit)
    if quantity_family != family: raise ValueError('Incompatible product quantity/factor units; no density assumed')
    quantity, factor = _number(quantity, 'quantity'), _number(factor_value, 'factor')
    evidence = dict(quantity=quantity, quantity_unit=quantity_unit, factor=factor, factor_unit=factor_unit,
        required_modules=sorted(required), factor_modules=sorted(provided))
    if quantity is None or factor is None:
        return _result(None, 'quantity × compatible product factor', evidence, 'missing_inventory_quantity_or_product_factor')
    converted = quantity * (MASS_KG[quantity_unit] if family == 'mass' else 1.) / denominator
    return _result(converted*factor, 'quantity converted to factor denominator × factor', evidence)


def transport_emissions(mass, mass_unit, distance_km, factor_value, factor_unit, *, mode,
        factor_mode=None, epd_modules=(), separate_leg=None, freight_accounting_module='A4'):
    """Freight mass × actual scenario distance × compatible mode factor.

    A source's regional freight flow or nearest plant is not a delivery route.
    Where an EPD includes A4, only a documented distinct extra leg is additive.
    """
    if mass_unit not in MASS_KG or factor_unit not in TRANSPORT_UNITS:
        raise ValueError('Compatible explicit freight mass and factor units required')
    if not isinstance(mode, str) or not mode.strip() or (factor_mode is not None and factor_mode != mode):
        raise ValueError('Freight mode disagrees with factor mode')
    if epd_modules and not set(epd_modules) <= MODULES: raise ValueError('Invalid EPD accounting modules')
    if freight_accounting_module not in {'A4','B4','C2'}: raise ValueError('Unsupported freight accounting module')
    if 'A4' in epd_modules or freight_accounting_module in epd_modules:
        included_leg = (separate_leg or {}).get('included_leg_id') or (separate_leg or {}).get('epd_a4_leg_id')
        if not isinstance(separate_leg, dict) or any(not isinstance(separate_leg.get(k), str) or not separate_leg[k].strip() for k in ('leg_id','rationale')) or not isinstance(included_leg,str) or not included_leg.strip() or separate_leg['leg_id'] == included_leg:
            raise ValueError(f'EPD/accounting boundary includes {freight_accounting_module} transport: added freight requires documented distinct separate leg')
    mass, distance, factor = _number(mass, 'mass'), _number(distance_km, 'distance_km'), _number(factor_value, 'factor')
    evidence = dict(mass=mass, mass_unit=mass_unit, distance_km=distance, factor=factor,
        factor_unit=factor_unit, mode=mode, factor_mode=factor_mode or mode,
        epd_modules=list(epd_modules), separate_leg=separate_leg, freight_accounting_module=freight_accounting_module)
    if mass is None or distance is None or factor is None:
        return _result(None, 'mass × distance × compatible mode factor', evidence, 'missing_freight_mass_distance_or_factor')
    return _result(mass*MASS_KG[mass_unit]/TRANSPORT_UNITS[factor_unit]*distance*factor,
        'mass converted to factor mass denominator × distance_km × mode factor', evidence)


def _selected(item, key):
    return all(item.get(k) is None or item[k] == v for k, v in key.items())


def calculate_lifecycle(temporal, *, opening_year, lifetime_years, inventory=None,
        transport_legs=None, complete_components=None, component_evidence=None):
    """One row per physical alternative; full total needs all required components.

    `inventory` is a list of quantity/factor items, optionally scoped by grid,
    design, scenario. `complete_components` explicitly declares which item lists
    are complete; a nonempty list alone is not proof of completeness. Explicit
    known-zero components need `component_evidence` with source/basis/rationale.
    Real runs with no inventory produce a named electricity-only partial sum.
    """
    if type(opening_year) is not int or type(lifetime_years) is not int or lifetime_years <= 0:
        raise ValueError('Explicit integer opening year and positive lifetime required')
    if temporal.empty: raise ValueError('Nonempty temporal input required')
    # Validate full rows rather than allowing malformed long-form evidence.
    records = [FutureScenarioValue.model_validate(nullable_record(r)).model_dump(mode='json') for r in temporal.to_dict('records')]
    frame = pd.DataFrame(records)
    if frame.grid_definition_id.nunique() != 1 or frame.data_mode.nunique() != 1:
        raise ValueError('Mixed temporal grid/data-mode identity')
    unique = ['grid_id','design_id','scenario_id','variable','period_kind','period_start_year','period_end_year']
    if frame.duplicated(unique).any(): raise ValueError('Duplicate temporal variable/period identity')
    annual = frame.loc[frame.period_kind.eq('annual_operating')]
    if annual.empty: raise ValueError('Annual operating alternatives required')
    years = set(range(opening_year, opening_year+lifetime_years))
    if not set(annual.period_start_year) <= years: raise ValueError('Temporal years exceed declared operating lifetime')
    items = [InventoryItem.model_validate(i).model_dump(exclude_none=True) for i in inventory or []]
    legs = [TransportLeg.model_validate(i).model_dump(exclude_none=True) for i in transport_legs or []]
    complete = set(complete_components or [])
    if not complete <= INVENTORY_COMPONENTS: raise ValueError('Invalid complete inventory component')
    if len({i['item_id'] for i in items}) != len(items) or len({i['leg_id'] for i in legs}) != len(legs):
        raise ValueError('Inventory item IDs and transport leg IDs must be unique')
    for item in items:
        if item.get('component') not in INVENTORY_COMPONENTS or not item.get('source_id') or not item.get('product_id'):
            raise ValueError('Inventory needs accounting component and product-specific source identity')
        modules = _modules(item['factor_modules'], 'factor_modules')
        if item.get('accounting_modules') is not None and _modules(item['accounting_modules'], 'accounting_modules') != modules:
            raise ValueError('Inventory accounting_modules must exactly equal the factor boundary; no absent modules may be claimed')
        allowed = {'construction': {f'A{i}' for i in range(1,6)},
            'equipment': {f'A{i}' for i in range(1,6)},
            'replacements': {f'A{i}' for i in range(1,6)} | {'B4','B5'},
            'end_of_life': {f'C{i}' for i in range(1,5)}}[item['component']]
        if not modules <= allowed:
            raise ValueError('Inventory accounting modules overlap another component; B6 electricity is accounted separately')
        if item.get('factor_product_id', item['product_id']) != item['product_id']:
            raise ValueError('Product factor identity differs from inventory product')
    for leg in legs:
        if not leg.get('source_id') or not leg.get('inventory_item_id') or not leg.get('distance_basis'):
            raise ValueError('Freight needs linked inventory, source and documented route-distance basis')
    direct = {c:ComponentEvidence.model_validate(v).model_dump(mode='json') for c,v in (component_evidence or {}).items()}
    if not set(direct) <= INVENTORY_COMPONENTS | {'operations_other'}:
        raise ValueError('Invalid direct lifecycle component')
    rows = []
    keys = ['grid_id','grid_definition_id','facility_id','design_id','scenario_id','data_mode']
    alternatives = annual[keys].drop_duplicates().to_dict('records')
    if any(not any(_selected(item,key) for key in alternatives) for item in items+legs):
        raise ValueError('Inventory/freight scope matches no physical alternative')
    for values, group in annual.groupby(keys, sort=True, dropna=False):
        key = dict(zip(keys, values)); metadata = {}; component_values = {}; known_leaves = []
        carbon = group.loc[group.variable.eq('c_electricity_kg')]
        if len(carbon) and not carbon.unit.eq('kg_CO2e').all(): raise ValueError('Operating electricity carbon must be kg_CO2e')
        known = carbon.loc[carbon.status.ne('unknown')]
        if len(known) and (known.value.isna().any() or known.value.lt(0).any()): raise ValueError('Invalid operating emissions evidence')
        for source in known.to_dict('records'):
            if source['coverage_frac'] is None or source['coverage_frac'] < 1-1e-6 or not source['source_id'] or not json.loads(source['source_json']) or not json.loads(source['assumptions_json']):
                raise ValueError('Known annual carbon requires complete source coverage, identity and documented assumptions')
        subtotal = float(known.value.sum()) if len(known) else None
        electricity = subtotal if len(known) == lifetime_years and set(known.period_start_year) == years else None
        metadata['operations_electricity'] = dict(status='calculated' if electricity is not None else 'unknown',
            known_periods=len(known), required_periods=lifetime_years, known_subtotal_kg=subtotal,
            missing_reason=None if electricity is not None else 'incomplete_annual_electricity_coverage',
            annual_sources=sorted(set(known.source_json)), annual_assumptions=sorted(set(group.assumptions_json)))
        if subtotal is not None: known_leaves.append(subtotal)
        for component in sorted(INVENTORY_COMPONENTS | {'operations_other'}):
            selected = [i for i in items if i['component'] == component and _selected(i, key)]
            calculations, covered_modules = [], set()
            for item in selected:
                calc = material_emissions(item.get('quantity'), item['quantity_unit'], item.get('factor_value'), item['factor_unit'],
                    required_modules=item['required_modules'], factor_modules=item['factor_modules'])
                calc['source'] = item
                calculations.append(calc)
                allocated = _modules(item.get('accounting_modules', item['factor_modules']), 'inventory accounting_modules')
                if not allocated <= set(COMPONENT_BOUNDARY[component]): raise ValueError('Inventory accounting modules cross component boundary')
                covered_modules |= allocated
                for leg in [l for l in legs if l['inventory_item_id'] == item['item_id'] and _selected(l, key)]:
                    if item['quantity_unit'] not in MASS_KG and (leg.get('mass') is None or leg.get('mass_unit') not in MASS_KG):
                        raise ValueError('Freight for a volume/count inventory requires explicit independent mass; no density conversion')
                    separate = leg.get('separate_leg')
                    if separate and separate.get('leg_id') != leg['leg_id']: raise ValueError('Separate freight leg identity disagrees with leg record')
                    freight_module = 'A4' if component in {'construction','equipment'} else 'B4' if component=='replacements' else 'C2'
                    freight = transport_emissions(leg.get('mass', item.get('quantity')), leg.get('mass_unit', item['quantity_unit']),
                        leg.get('distance_km'), leg.get('factor_value'), leg['factor_unit'], mode=leg['mode'],
                        factor_mode=leg.get('factor_mode'), epd_modules=sorted(set(item['factor_modules'])|allocated), separate_leg=separate,
                        freight_accounting_module=freight_module)
                    freight['source'] = leg; calculations.append(freight)
                    covered_modules.add(freight_module)
            direct_evidence = direct.get(component)
            if direct_evidence is not None:
                if selected or not isinstance(direct_evidence, dict) or any(not direct_evidence.get(k) for k in ('source_id','basis','rationale')) or direct_evidence.get('status') not in {'observed','calculated','scenario'}:
                    raise ValueError('Direct component evidence needs source/basis/rationale/status and must not duplicate inventory')
                val = _number(direct_evidence.get('value_kg'), 'component value_kg')
                if val is None: raise ValueError('Known direct component requires explicit value')
                calculations = [_result(val, 'explicit component evidence', direct_evidence)]
                covered_modules = _modules(direct_evidence['accounting_modules'], 'direct accounting_modules')
                if not covered_modules <= set(COMPONENT_BOUNDARY[component]): raise ValueError('Direct accounting modules cross component boundary')
            known_parts = [c['value_kg'] for c in calculations if c['value_kg'] is not None]
            known_leaves.extend(known_parts)
            missing_modules = set(COMPONENT_BOUNDARY[component])-covered_modules
            full = bool(calculations) and all(c['value_kg'] is not None for c in calculations) and not missing_modules and (component in complete or direct_evidence is not None)
            component_values[component] = sum(known_parts) if full else None
            metadata[component] = dict(status='calculated' if full else 'unknown', inventory_complete=component in complete,
                missing_reason=None if full else 'missing_or_incomplete_inventory_component', items=calculations,
                required_accounting_modules=COMPONENT_BOUNDARY[component], missing_accounting_modules=sorted(missing_modules),
                known_subtotal_kg=sum(known_parts) if known_parts else None)
        matched_items = {i['item_id'] for i in items if _selected(i, key)}
        if any(_selected(l, key) and l['inventory_item_id'] not in matched_items for l in legs):
            raise ValueError('Freight leg is orphaned or has incompatible alternative scope')
        operations_other = component_values.pop('operations_other')
        operations = None if electricity is None or operations_other is None else electricity+operations_other
        component_values['operations'] = operations
        metadata['operations'] = dict(status='calculated' if operations is not None else 'unknown',
            components=['operations_electricity','operations_other'], interpretation='Electricity alone excludes fuel, refrigerants and other operating emissions')
        unknown = [c for c in COMPONENTS if component_values[c] is None]
        total = None if unknown else sum(component_values.values())
        partial = sum(known_leaves) if known_leaves else None
        if any(v is not None and not math.isfinite(v) for v in [subtotal,total,partial,*component_values.values()]):
            raise ValueError('Lifecycle sum overflowed finite outputs')
        row = LifecycleResult(**key, opening_year=opening_year, lifetime_years=lifetime_years,
            operations_electricity_kg=electricity, operations_electricity_known_subtotal_kg=subtotal,
            operations_other_kg=operations_other, total_lifecycle_kg=total, known_subtotal_partial_kg=partial,
            known_leaf_count=len(known_leaves), required_components_json=_json(COMPONENTS),
            unknown_components_json=_json(unknown), component_metadata_json=_json(metadata),
            accounting_boundary_json=_json(dict(policy='Explicit gross accounting boundary; no moduleD credits',
                basis='project_assumption', rationale='Disjoint operating/replacement/end-of-life modules; initial construction and equipment inventories kept distinct',
                component_modules=COMPONENT_BOUNDARY, completeness='Inventory declaration plus evidence for every required module')),
            status='unknown' if unknown else 'calculated', confidence='unknown' if unknown else 'low',
            missing_reason='missing_required_lifecycle_components' if unknown else None,
            **{k+'_kg': v for k,v in component_values.items()})
        rows.append(row.model_dump(mode='json'))
    result = pd.DataFrame(rows).sort_values(['grid_id','design_id','scenario_id']).reset_index(drop=True)
    result.attrs.update(grid_definition_id=frame.grid_definition_id.iloc[0], data_mode=frame.data_mode.iloc[0])
    return result
