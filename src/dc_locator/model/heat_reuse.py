"""Optional heat-host scenarios with supplied factors and explicit energy boundaries."""
from __future__ import annotations

import math
from numbers import Real
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class HeatReuseInputs(BaseModel):
    """A user-supplied case, never a measured local opportunity inferred by the engine."""
    model_config = ConfigDict(extra='forbid', strict=True)
    grid_id: str = Field(min_length=1)
    design_id: str = Field(min_length=1)
    scenario_id: str = Field(min_length=1)
    basis: Literal['project_assumption', 'documented_input']
    rationale: str = Field(min_length=1)
    reference: str | None = None
    reference_section: str | None = None
    consumer_name: str | None = Field(default=None, min_length=1)
    temperature_compatible: bool | None = None
    recoverable_fraction: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    distribution_loss_fraction: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    annual_heat_demand_mwh: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    annual_auxiliary_electricity_mwh: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    displaced_heating_kg_co2e_per_mwh: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    auxiliary_electricity_kg_co2e_per_mwh: float | None = Field(default=None, ge=0, allow_inf_nan=False)

    @model_validator(mode='after')
    def evidence_required(self):
        if not self.rationale.strip():
            raise ValueError('An input rationale is required')
        if self.basis=='documented_input' and not (self.reference and self.reference.strip() and
                                                   self.reference_section and self.reference_section.strip()):
            raise ValueError('Documented inputs require a reference URL/document and table/page/section')
        if self.consumer_name is not None and not self.consumer_name.strip():
            raise ValueError('Heat consumer name must be meaningful')
        return self


def evaluate_heat_reuse(e_it_mwh: float | None, inputs: HeatReuseInputs) -> dict:
    """Demand-cap delivered heat and subtract supplied auxiliary electricity emissions.

    Recoverable fraction describes IT-electricity-equivalent thermal energy.
    Auxiliary electricity includes pumping, heat pumps and other incremental
    delivery loads. A caller must supply compatible annual factors; the engine
    does not guess temperature lift, COP, seasonal matching or avoided fuel.
    """
    if e_it_mwh is not None and (isinstance(e_it_mwh,bool) or not isinstance(e_it_mwh,Real)
                                or not math.isfinite(e_it_mwh) or e_it_mwh<0):
        raise ValueError('IT energy must be finite nonnegative numeric input or null')
    thermal_inputs=[e_it_mwh,inputs.recoverable_fraction,inputs.distribution_loss_fraction]
    available=None if any(value is None for value in thermal_inputs) else (
        e_it_mwh*inputs.recoverable_fraction*(1-inputs.distribution_loss_fraction))
    missing=[]
    if not inputs.consumer_name:missing.append('matched heat consumer')
    if inputs.temperature_compatible is None:missing.append('temperature compatibility')
    if available is None:missing.append('IT energy, recoverable fraction or distribution losses')
    if inputs.annual_heat_demand_mwh is None:missing.append('compatible annual demand')
    delivered=None if missing else (0. if not inputs.temperature_compatible else
                                    min(available,inputs.annual_heat_demand_mwh))
    factors=[inputs.annual_auxiliary_electricity_mwh,inputs.displaced_heating_kg_co2e_per_mwh,
             inputs.auxiliary_electricity_kg_co2e_per_mwh]
    avoided=None if delivered is None or any(value is None for value in factors) else (
        delivered*inputs.displaced_heating_kg_co2e_per_mwh-
        inputs.annual_auxiliary_electricity_mwh*inputs.auxiliary_electricity_kg_co2e_per_mwh)/1000

    def quantity(value,unit,method,reason):
        if value is not None and not math.isfinite(value):
            raise ValueError('Heat scenario overflowed a physical output')
        return dict(value=value,unit=unit,status='unknown' if value is None else 'calculated',
                    confidence='unknown' if value is None else 'low',method=method,
                    missing_reason=reason if value is None else None)

    return dict(schema_version='1.0.0',input_basis=inputs.basis,inputs=inputs.model_dump(),
        available_heat_after_losses_mwh=quantity(available,'MWh thermal/year',
            'e_it_mwh * recoverable_fraction * (1 - distribution_loss_fraction)',
            'IT energy, recoverable fraction or distribution losses unavailable'),
        delivered_heat_mwh=quantity(delivered,'MWh thermal/year',
            'min(available_heat_after_losses_mwh, annual_heat_demand_mwh) when host and temperature match',
            '; '.join(missing)),
        net_heating_system_avoided_co2e_tonnes=quantity(avoided,'tonnes CO2e/year',
            '(delivered_heat * displaced_heating_factor - auxiliary_electricity * auxiliary_factor) / 1000',
            'Delivered heat, displaced heating baseline or complete auxiliary electricity accounting unavailable'),
        boundary='Supplied annual scenario for the heating system. Annual demand must match usable temperatures and delivery timing. '
                 'Negative net values are added emissions. This result is separate from facility electricity emissions and MCDA; '
                 'it is not automatically credited against the facility footprint, lifetime carbon or water use.')
