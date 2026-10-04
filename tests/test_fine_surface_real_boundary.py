"""Real CONUS boundary: fine-surface cell retention equals the grid generator on coast and border parents."""
import numpy as np
import pytest
import shapely

from dc_locator.config import load_grid_config
from dc_locator.fine_surface import _study_piece
from dc_locator.geography.boundary import load_conus_boundary
from dc_locator.geography.fine_features import window_cells
from dc_locator.geography.grid import generate_bounded_grid
from dc_locator.paths import project_root

X0, Y0, PARENT_M = -2_500_000.0, 3_400_000.0, 50_000.0
# Arizona-Mexico border sliver, Gulf coast, Great Lakes shore and Pacific coast (study fractions 0.02-0.95).
BOUNDARY_PARENTS = [(44, 15), (51, 63), (14, 66), (20, 4)]


@pytest.fixture(scope='module')
def boundary():
    try:
        return load_conus_boundary()
    except Exception as error:  # boundary zips are cached data, not part of the repository
        pytest.skip(f'CONUS boundary not cached: {error}')


@pytest.mark.parametrize('row,col', BOUNDARY_PARENTS)
def test_border_parent_cells_equal_generated_grid(boundary, row, col):
    grid_config = load_grid_config(project_root() / 'configs' / 'grid_regional.yaml')
    box = shapely.box(X0 + col * PARENT_M, Y0 - (row + 1) * PARENT_M, X0 + (col + 1) * PARENT_M, Y0 - row * PARENT_M)
    expected, _ = generate_bounded_grid(grid_config, boundary, [box])
    parts = shapely.get_parts(boundary.boundary)
    cells = window_cells(grid_config, row, col, 50, _study_piece(parts, shapely.STRtree(parts), box))
    assert sorted(cells.grid_id) == sorted(expected.grid_id)
    joined = cells.merge(expected[['grid_id', 'study_area_intersection_km2', 'is_boundary_cell']], on='grid_id', suffixes=('', '_grid'))
    np.testing.assert_allclose(joined.study_area_intersection_km2, joined.study_area_intersection_km2_grid, rtol=0, atol=1e-9)
    assert (~joined.full_cell == joined.is_boundary_cell).all()
