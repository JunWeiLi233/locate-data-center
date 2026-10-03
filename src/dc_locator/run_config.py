"""Strict delivery configuration and bounded execution preflight."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

import pyarrow.parquet as pq
import yaml
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator

from dc_locator.io import read_parquet_metadata
from dc_locator.provenance import DataMode


class DeliveryConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_version: Literal['2.0.0']
    delivery_version: Literal['phase7_delivery_v1']
    run_name: str = Field(min_length=1)
    data_mode: DataMode
    grid_config: str
    grid_path: str
    grid_definition_id: str
    study_area: str
    source_registry: str
    local_sources: str
    core_source_inputs: str | None = None
    expanded_source_inputs: str | None = None
    aqueduct_source_input: str | None = None
    fixture_geography: str | None = None
    fixture_provenance: str | None = None
    expanded_features: StrictBool = True
    facility: str
    cooling_designs: str
    physical_scenarios: str
    constraints: str
    scoring_profile: str
    screening_mode: Literal['STRICT','EXPLORATORY']
    weighting_method: Literal['equal','user','ahp'] = 'equal'
    user_group_weights: dict | None = None
    ahp_input: str | None = None
    future: dict
    validation: dict
    maximum_model_cells: StrictInt = Field(default=1000,ge=1,le=10000)
    resource_policy_basis: Literal['project_assumption']
    resource_policy_rationale: str = Field(min_length=1)
    random_seed: StrictInt | None = None

    @model_validator(mode='after')
    def references(self):
        if self.data_mode == DataMode.REAL and (not self.core_source_inputs or self.fixture_geography or self.fixture_provenance):
            raise ValueError('Real execution requires native source inputs and forbids synthetic fixture references')
        if self.data_mode == DataMode.SYNTHETIC and (not self.fixture_geography or not self.fixture_provenance or self.expanded_features):
            raise ValueError('Synthetic execution requires explicit fixture geography/provenance and expanded_features=false')
        if self.weighting_method == 'user' and not self.user_group_weights:
            raise ValueError('User weighting requires complete declared group preferences')
        if self.weighting_method != 'user' and self.user_group_weights is not None:
            raise ValueError('User preferences supplied to another weighting mode')
        if self.weighting_method != 'ahp' and self.ahp_input is not None:
            raise ValueError('AHP judgments supplied to another weighting mode')
        for policy in (self.future,self.validation):
            if type(policy.get('enabled')) is not bool:
                raise ValueError('enabled must be an explicit boolean')
        if set(self.future)-{'enabled','pathways','milestone_years','profiles_directory','profile_declaration','annual_extension','lifecycle'}:
            raise ValueError('Unknown future configuration key')
        if set(self.validation)-{'enabled','validation_revision','top_k','cases','allow_synthetic','max_cases','future_contexts'}:
            raise ValueError('Unknown current validation configuration key')
        if type(self.validation.get('allow_synthetic',False)) is not bool:
            raise ValueError('allow_synthetic must be an explicit boolean')
        if self.future['enabled']:
            if not self.aqueduct_source_input or not self.expanded_features:
                raise ValueError('Future contexts require explicit native source input and enhanced geography')
            years=self.future.get('milestone_years',[]);ways=self.future.get('pathways',[])
            if not years or any(type(v) is not int for v in years) or len(set(years))!=len(years):
                raise ValueError('Future milestones require unique integer years')
            if not ways or not set(ways)<={'bau','opt','pes'} or len(set(ways))!=len(ways):
                raise ValueError('Future pathways require unique native pathway IDs')
            for field in ('profiles_directory','profile_declaration','lifecycle'):
                if not isinstance(self.future.get(field),str) or not self.future[field].strip():raise ValueError('Future context requires '+field)
            from dc_locator.model.scenarios import AnnualExtensionPolicy
            AnnualExtensionPolicy.model_validate(self.future.get('annual_extension'))
        from dc_locator.model.run_validation import CurrentValidationSettings
        settings={k:v for k,v in self.validation.items() if k not in {'enabled','future_contexts'}}
        settings['baseline_mode']=self.screening_mode
        CurrentValidationSettings.model_validate(settings)
        requested=self.validation.get('future_contexts',[])
        if not isinstance(requested,list) or any(not isinstance(v,str) or not v for v in requested) or len(requested)!=len(set(requested)):
            raise ValueError('Validation context IDs require a unique list of strings')
        available={f'{p}_{y}' for p in self.future.get('pathways',[]) for y in self.future.get('milestone_years',[])} if self.future['enabled'] else set()
        if not set(requested)<=available:raise ValueError('Requested validation contexts are not configured')
        return self


def resolve_path(root, value):
    path=Path(value)
    return path.resolve() if path.is_absolute() else (Path(root)/path).resolve()


def load_delivery_config(path):
    return DeliveryConfig.model_validate(yaml.safe_load(Path(path).read_text(encoding='utf-8')))


def load_source_document(path,root):
    """Resolve only declared path fields; URLs and native field names stay intact."""
    document=json.loads(Path(path).read_text(encoding='utf-8'))
    def walk(value,key=None):
        if isinstance(value,dict):
            return {k:({n:str(resolve_path(root,p)) for n,p in v.items()} if k=='paths' else walk(v,k)) for k,v in value.items()}
        if isinstance(value,list):return [walk(v,key) for v in value]
        if isinstance(value,str) and key in {'path','manifest','interpretation_verification_path'} and not value.startswith(('http:','https:')):
            return str(resolve_path(root,value))
        return value
    return walk(document)


def check_table_identity(path,schema,mode,definition,minimum=(1,0,0)):
    meta=read_parquet_metadata(path)
    match=re.fullmatch(r'(\d+)\.(\d+)\.(\d+)',meta.get('schema_version',''))
    if not match:raise ValueError('Missing or invalid file schema version: '+str(path))
    version=tuple(map(int,match.groups()))
    if meta.get('schema')!=schema or len(version)!=3 or version[0]!=minimum[0] or version<minimum:
        raise ValueError('Incompatible file schema/version: '+str(path))
    if meta.get('data_mode')!=mode or meta.get('grid_definition_id')!=definition:
        raise ValueError('File data_mode/grid_definition_id mismatch: '+str(path))
    return meta


def preflight(config,root,output=None):
    """Reject unsupported scope before allocating any feature table."""
    if config.study_area.lower() in {'conus','national'}:
        raise ValueError('National model execution is unsupported: acquired source coverage and national vector RAM are unvalidated. build-grid supports national geometry separately.')
    grid=resolve_path(root,config.grid_path)
    check_table_identity(grid,'GridCell',config.data_mode.value,config.grid_definition_id)
    count=pq.ParquetFile(grid).metadata.num_rows
    if count<1 or count>config.maximum_model_cells:
        raise ValueError('Configured grid exceeds bounded model resource policy or is empty')
    if output is not None:
        target=Path(output).resolve();root=Path(root).resolve()
        owned_run=target.is_relative_to(root/'runs') and target!=root/'runs'
        relative=target.relative_to(root) if target.is_relative_to(root) else None
        pytest_temp=relative is not None and relative.parts and (relative.parts[0].startswith('.tmp-phase7') or relative.parts[0]=='.pytest-work')
        if not (owned_run or pytest_temp) or any(target.is_relative_to(root/'runs'/f'phase{n}') for n in range(1,7)):
            raise ValueError('Delivery output must not overwrite source, production or historical accepted folders')
    return {'geographic_cells':count,'grid_definition_id':config.grid_definition_id,'data_mode':config.data_mode.value,'scope':config.study_area,'national_model_supported':False}
