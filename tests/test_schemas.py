"""Tests for dc_locator.schemas: the 8 versioned data contracts (phase1.md.txt step 3)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError
from shapely.geometry import LineString, Polygon, box

from dc_locator.provenance import AHPStatus, Confidence, DataMode, ScreeningMode, ScreeningOutcome, ValueStatus
from dc_locator.schemas import (
    CandidateRegion,
    DecisionResult,
    FacilityConfig,
    FeatureMetadata,
    GridCell,
    RunManifest,
    ScreeningResult,
    SitePerformance,
)


def _valid_grid_cell_kwargs(**overrides) -> dict:
    kwargs = dict(
        grid_id="g10000m-r0001-c0001",
        grid_definition_id="conus-epsg5070-ox-2500000-oy3400000-s10000m-v1",
        row=1,
        col=1,
        tile_id="t25-tr0000-tc0000",
        geometry=box(0, 0, 10000, 10000),
        cell_area_km2=100.0,
        study_area_intersection_km2=80.0,
        study_area_frac=0.8,
        is_boundary_cell=True,
        centroid_x_m=5000.0,
        centroid_y_m=5000.0,
        centroid_lat=40.0,
        centroid_lon=-100.0,
        rep_point_lat=40.0,
        rep_point_lon=-100.0,
        state_fips_primary="48",
        state_abbr_primary="TX",
        state_share_primary_frac=1.0,
        state_fips_all="48",
        n_states=1,
        county_geoid_primary="48201",
        county_name_primary="Harris",
        county_share_primary_frac=1.0,
        county_geoid_all="48201",
        n_counties=1,
        data_mode=DataMode.REAL,
    )
    kwargs.update(overrides)
    return kwargs


class TestGridCell:
    def test_valid_cell_constructs(self) -> None:
        cell = GridCell(**_valid_grid_cell_kwargs())
        assert cell.schema_version == "1.1.0"
        assert cell.grid_id == "g10000m-r0001-c0001"

    def test_rejects_non_polygon_geometry(self) -> None:
        with pytest.raises(ValidationError, match="Polygon"):
            GridCell(**_valid_grid_cell_kwargs(geometry=LineString([(0, 0), (1, 1)])))

    def test_rejects_invalid_polygon(self) -> None:
        bowtie = Polygon([(0, 0), (1, 1), (1, 0), (0, 1), (0, 0)])  # self-intersecting
        with pytest.raises(ValidationError, match="valid Polygon"):
            GridCell(**_valid_grid_cell_kwargs(geometry=bowtie))

    def test_rejects_intersection_exceeding_cell_area(self) -> None:
        with pytest.raises(ValidationError, match="exceeds cell_area_km2"):
            GridCell(**_valid_grid_cell_kwargs(cell_area_km2=10.0, study_area_intersection_km2=50.0))

    def test_rejects_extra_field(self) -> None:
        with pytest.raises(ValidationError):
            GridCell(**_valid_grid_cell_kwargs(), unexpected_field=123)  # type: ignore[arg-type]

    def test_county_presence_must_match_n_counties(self) -> None:
        with pytest.raises(ValidationError, match="n_counties"):
            GridCell(**_valid_grid_cell_kwargs(county_geoid_primary=None, n_counties=1))
        with pytest.raises(ValidationError, match="n_counties"):
            GridCell(**_valid_grid_cell_kwargs(n_counties=0))  # county_geoid_primary is set

    def test_allows_null_county_with_n_counties_zero(self) -> None:
        cell = GridCell(**_valid_grid_cell_kwargs(
            county_geoid_primary=None, county_name_primary=None,
            county_share_primary_frac=None, county_geoid_all=None, n_counties=0,
        ))
        assert cell.n_counties == 0
        assert cell.county_geoid_primary is None


class TestFeatureMetadata:
    def test_is_a_provenance_record_with_schema_version(self) -> None:
        fm = FeatureMetadata(
            grid_id="g10000m-r0001-c0001",
            metric="land_cover_developed_frac",
            value=0.42,
            unit="frac",
            source_id="usgs_annual_nlcd",
            status=ValueStatus.OBSERVED,
            confidence=Confidence.HIGH,
            data_mode=DataMode.REAL,
        )
        assert fm.schema_version == "1.1.0"
        assert fm.missing_reason is None

    def test_inherits_unknown_requires_null_value(self) -> None:
        with pytest.raises(ValidationError, match="must be null when status is UNKNOWN"):
            FeatureMetadata(
                grid_id="g1", metric="m", value=0.0, source_id="s",
                status=ValueStatus.UNKNOWN, confidence=Confidence.UNKNOWN, data_mode=DataMode.REAL,
            )


def test_facility_config_valid_and_bounds() -> None:
    fc = FacilityConfig(
        facility_id="illustrative_default",
        peak_it_power_mw=100.0,
        average_it_load_factor=0.7,
        target_opening_year=2030,
        operating_lifetime_years=15,
    )
    assert fc.schema_version == "1.1.0"
    with pytest.raises(ValidationError):
        FacilityConfig(facility_id="x", peak_it_power_mw=-1.0, average_it_load_factor=0.7, target_opening_year=2030, operating_lifetime_years=15)
    with pytest.raises(ValidationError):
        FacilityConfig(facility_id="x", peak_it_power_mw=1.0, average_it_load_factor=1.5, target_opening_year=2030, operating_lifetime_years=15)


@pytest.mark.parametrize("field", [
    "peak_it_power_mw", "average_it_load_factor", "hours_in_modeled_year",
    "minimum_land_area_km2", "target_opening_year", "operating_lifetime_years",
])
def test_facility_config_rejects_boolean_numeric_fields(field) -> None:
    values=dict(facility_id="typed",peak_it_power_mw=100,average_it_load_factor=.8,
        target_opening_year=2030,operating_lifetime_years=25,hours_in_modeled_year=8760,
        minimum_land_area_km2=0)
    values[field]=True
    with pytest.raises(ValidationError,match="numeric|integer"):
        FacilityConfig.model_validate(values)


def test_facility_config_preserves_allowed_numeric_zero() -> None:
    value=FacilityConfig(facility_id="zero",peak_it_power_mw=100,average_it_load_factor=0,
        target_opening_year=2030,operating_lifetime_years=25,minimum_land_area_km2=0)
    assert value.average_it_load_factor==0 and value.minimum_land_area_km2==0


def test_screening_result_unknown_outcome() -> None:
    sr = ScreeningResult(
        grid_id="g1", design_id="d1", scenario_id="s1",
        requirement="min_transmission_proximity_km",
        outcome=ScreeningOutcome.UNKNOWN,
        mode=ScreeningMode.STRICT,
        missing_reason="source_not_acquired",
    )
    assert sr.value is None
    assert sr.is_critical is True


def test_site_performance_rejects_negative_energy() -> None:
    with pytest.raises(ValidationError):
        SitePerformance(grid_id="g1", design_id="d1", scenario_id="s1", e_it_mwh=-5.0)


def test_decision_result_hard_fail_and_optional_scores() -> None:
    dr = DecisionResult(grid_id="g1", design_id="d1", scenario_id="s1", hard_fail=True)
    assert dr.is_pareto_optimal is None
    assert dr.mcda_score is None


class TestCandidateRegion:
    def _kwargs(self, **overrides):
        kwargs = dict(
            region_id="r1", design_id="d1", scenario_id="s1",
            member_grid_ids=["g1", "g2", "g3"], n_cells=3,
            total_area_km2=300.0, centroid_lat=40.0, centroid_lon=-100.0,
        )
        kwargs.update(overrides)
        return kwargs

    def test_valid(self) -> None:
        region = CandidateRegion(**self._kwargs())
        assert region.n_cells == 3

    def test_rejects_duplicate_members(self) -> None:
        with pytest.raises(ValidationError, match="duplicates"):
            CandidateRegion(**self._kwargs(member_grid_ids=["g1", "g1", "g2"]))

    def test_rejects_n_cells_mismatch(self) -> None:
        with pytest.raises(ValidationError, match="n_cells"):
            CandidateRegion(**self._kwargs(n_cells=99))

    def test_rejects_empty_members(self) -> None:
        with pytest.raises(ValidationError):
            CandidateRegion(**self._kwargs(member_grid_ids=[], n_cells=0))


class TestRunManifest:
    def _kwargs(self, **overrides):
        kwargs = dict(
            run_id="phase1_dev-20261002",
            created_at=datetime.now(timezone.utc),
            config_snapshot_hash="a" * 64,
            grid_definition_id="conus-epsg5070-ox-2500000-oy3400000-s10000m-v1",
            grid_resolution_m=10000.0,
            data_mode=DataMode.REAL,
        )
        kwargs.update(overrides)
        return kwargs

    def test_valid(self) -> None:
        rm = RunManifest(**self._kwargs())
        assert rm.warnings == []
        assert rm.blockers == []

    def test_rejects_naive_datetime(self) -> None:
        with pytest.raises(ValidationError, match="timezone-aware"):
            RunManifest(**self._kwargs(created_at=datetime(2026, 10, 2)))

    def test_ahp_status_enum_roundtrip(self) -> None:
        rm = RunManifest(**self._kwargs())
        assert rm.source_coverage is None
        assert AHPStatus.NOT_APPLICABLE.value == "NOT_APPLICABLE"  # sanity: enum imported/used correctly elsewhere
