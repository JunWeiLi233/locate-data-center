"""Typed HTTP contract; the pure model validator remains the authority on bounds."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .schemas import validate_config

Numeric = int | float


class StrictModel(BaseModel):
    """Reject unknown fields and coercions such as strings or booleans as numbers."""

    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Prior(StrictModel):
    """Document bounded engineering or trajectory assumptions and their source."""

    kind: Literal["fixed", "triangular"]
    lower: Numeric
    mode: Numeric
    upper: Numeric
    units: Literal["dimensionless", "L/kWh", "fraction/year"]
    source: str


class Cooling(StrictModel):
    """Keep water boundaries explicit instead of inferring them from a value."""

    pue: Prior
    wue: Prior
    wue_basis: Literal["it", "facility"]
    water_definition: Literal["consumption"]


class Scenario(StrictModel):
    """Represent a separate structural future with optional regional rate priors."""

    id: str
    description: str
    price_growth: Prior
    carbon_decline: Prior
    regional_overrides: dict[str, dict[Literal["price_growth", "carbon_decline"], Prior]]


class Constraint(StrictModel):
    """Support documented screening thresholds, not inferred chance constraints."""

    field: Literal["water_stress_score", "grid_co2e_kg_per_mwh", "electricity_price_usd_per_mwh"]
    maximum: Numeric
    label: str


class NumericalTolerances(StrictModel):
    """Record objective-order physical tolerances for Pareto comparisons."""

    absolute: list[Numeric] = Field(min_length=3, max_length=3)
    relative: Numeric


class ConvergenceTolerances(StrictModel):
    """Expose the predeclared convergence acceptance thresholds."""

    relative_objective_mean: Numeric
    absolute_pareto_frequency: Numeric


class RunConfig(StrictModel):
    """Publish the complete existing configuration through generated OpenAPI."""

    it_nameplate_mw: Numeric
    utilization: Numeric
    annual_hours: Numeric
    opening_year: int
    analysis_horizon_years: int
    base_currency: Literal["USD"]
    base_year: Literal[2025]
    currency_convention: Literal["real", "nominal"]
    discount_rate: Numeric
    cooling: Cooling
    dependence: Literal["shared_independent_engineering", "shared_comonotonic_engineering"]
    scenario_set: list[Scenario] = Field(min_length=1, max_length=12)
    seed: int
    simulation_count: int
    feasibility_mode: Literal["exploratory", "verified"]
    hard_constraints: list[Constraint] = Field(max_length=20)
    numerical_tolerances: NumericalTolerances
    cvar_alpha: Numeric
    bootstrap_resamples: int
    convergence_tolerances: ConvergenceTolerances

    @model_validator(mode="before")
    @classmethod
    def check_model_contract(cls, value):
        """Apply identical CLI/HTTP validation before any parsing or coercion."""
        try:
            return validate_config(value)
        except (TypeError, KeyError, AttributeError):
            raise ValueError("Configuration fields have invalid types or structure") from None


class RunOptions(StrictModel):
    """Enable both audits by default; clients may explicitly skip either."""

    sensitivity: bool = True
    convergence: bool = True


class RunRequest(StrictModel):
    """Accept only model settings and bounded audit controls."""

    config: RunConfig
    options: RunOptions = Field(default_factory=RunOptions)


class ErrorDetail(StrictModel):
    """Locate a validation error without exposing raw input or internal paths."""

    field: str
    message: str


class Error(StrictModel):
    """Use the same safe error structure for HTTP failures and failed jobs."""

    code: str
    message: str
    details: list[ErrorDetail] = Field(default_factory=list)


class ErrorEnvelope(StrictModel):
    """Describe the shared HTTP error envelope in the generated OpenAPI contract."""

    api_version: Literal["1.0"] = "1.0"
    error: Error


class Job(StrictModel):
    """Keep submission and polling envelopes consistent across job states."""

    api_version: Literal["1.0"] = "1.0"
    run_id: str
    status: Literal["queued", "running", "completed", "failed"]
    cached: bool = False
    submitted_at: str
    started_at: str | None = None
    finished_at: str | None = None
    links: dict[str, str]
    warnings: list[str]
    result: dict | None = None
    error: Error | None = None


class Health(StrictModel):
    """Describe readiness responses, including the HTTP 503 health response."""

    api_version: Literal["1.0"]
    model_version: str
    ready: bool
    queue: dict[Literal["running", "queued"], int]
    warnings: list[str]


class Datasets(StrictModel):
    """Retain source-manifest and coverage schemas without fabricating missing data."""

    api_version: Literal["1.0"]
    ready: bool
    manifest: dict | None
    coverage: dict | None
    warnings: list[str]


class Candidates(StrictModel):
    """Wrap the documented frozen evidence export with API version and warnings."""

    api_version: Literal["1.0"]
    evidence: dict
    warnings: list[str]


class CandidateResult(StrictModel):
    """Publish per-run candidate evidence, outcomes and explicit exclusion reasons."""

    api_version: Literal["1.0"]
    run_id: str
    candidate_id: str
    evidence: dict
    objective_units: dict[str, str]
    scenarios: list[dict]
    exclusion_reasons: list[str]
    warnings: list[str]
    boundary_exclusions: list[str]
