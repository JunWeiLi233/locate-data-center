"""A region must contain enough total land support after cell-boundary screening."""
import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box

from dc_locator.model.regions import cluster_regions


def clustered(areas, cols=None):
    n = len(areas)
    cols = list(range(n)) if cols is None else cols
    geo = gpd.GeoDataFrame(dict(grid_id=[f"g{i}" for i in range(n)], grid_definition_id=["synthetic"]*n,
        row=[0]*n, col=cols, study_area_intersection_km2=[1.]*n, suitable_land_area_km2=areas),
        geometry=[box(c*1000, 0, (c+1)*1000, 1000) for c in cols], crs=5070)
    ranked = pd.DataFrame(dict(grid_id=geo.grid_id, design_id=["dry"]*n, scenario_id=["historical"]*n,
        mcda_score=[95.]*n, rankable=[True]*n, conditional=[True]*n, critical_unknown=[True]*n,
        is_pareto_optimal=[True]*n))
    return cluster_regions(geo, ranked, dict(top_fraction=1., adjacency="rook", minimum_cells=1,
        require_pareto=False, maximum_extent_km=20., extent_basis="project_assumption",
        extent_rationale="Synthetic bounded fixture"), [], "synthetic", "synthetic")


def test_singleton_with_known_insufficient_region_land_is_excluded():
    from dc_locator.model.regions import screen_region_land_support
    regions, membership = clustered([.30])
    assert len(regions) == 1 and regions.iloc[0].suitable_land_area_km2 < .40468564224
    accepted, members, audit = screen_region_land_support(regions, membership, .40468564224)
    assert accepted.empty and members.empty
    assert audit.outcome.tolist() == ["FAIL"]


def test_adjacent_adequate_sum_is_only_total_area_plausibility():
    from dc_locator.model.regions import screen_region_land_support
    regions, membership = clustered([.30, .30])
    accepted, members, audit = screen_region_land_support(regions, membership, .40468564224)
    assert len(accepted) == 1 and len(members) == 2
    assert audit.outcome.tolist() == ["PASS"]
    assert accepted.conditional.all() and accepted.critical_unknown.all()
    assert accepted.schema_version.tolist() == ["1.3.0"]


def test_disconnected_insufficient_areas_cannot_compensate_each_other():
    from dc_locator.model.regions import screen_region_land_support
    regions, membership = clustered([.30, .30], cols=[0, 2])
    accepted, members, audit = screen_region_land_support(regions, membership, .40468564224)
    assert accepted.empty and members.empty
    assert audit.outcome.tolist() == ["FAIL", "FAIL"]


def test_partial_aggregate_area_is_unknown_not_partial_sum_pass():
    from dc_locator.model.regions import screen_region_land_support
    regions, membership = clustered([.5, np.nan])
    accepted, members, audit = screen_region_land_support(regions, membership, .40468564224)
    assert audit.outcome.tolist() == ["UNKNOWN"]
    assert audit.value_km2.isna().all()
    assert accepted.conditional.all() and accepted.critical_unknown.all()
    assert len(members) == 2


@pytest.mark.parametrize("threshold", [True, 0., -1., np.inf, np.nan])
def test_invalid_region_land_threshold_rejected(threshold):
    from dc_locator.model.regions import screen_region_land_support
    with pytest.raises(ValueError):
        screen_region_land_support(*clustered([.5]), threshold)
