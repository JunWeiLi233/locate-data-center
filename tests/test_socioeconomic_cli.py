"""The independent economic-context command keeps acquisition and vintages explicit."""
import argparse

import pytest

from dc_locator.cli import build_parser


def socioeconomic_parser():
    parser = build_parser()
    commands = next(action for action in parser._actions if isinstance(action, argparse._SubParsersAction))
    assert "socioeconomic-enrich" in commands.choices
    return parser


def test_county_context_defaults_to_config_and_never_implicitly_downloads():
    parser = socioeconomic_parser()
    args = parser.parse_args(["socioeconomic-enrich", "--grid", "runs/owned/us_grid_dataset.parquet"])
    assert args.config == "configs/socioeconomic.yaml"
    assert args.boundary_year is None
    assert args.acquire is False


@pytest.mark.parametrize("year", ["2023", "2025"])
def test_authorized_boundary_years_and_explicit_acquisition(year):
    args = socioeconomic_parser().parse_args([
        "socioeconomic-enrich", "--grid", "runs/owned/us_grid_dataset.parquet",
        "--boundary-year", year, "--acquire",
    ])
    assert args.boundary_year == int(year)
    assert args.acquire is True


def test_unsupported_vintage_is_rejected_before_source_processing():
    with pytest.raises(SystemExit) as exc:
        socioeconomic_parser().parse_args([
            "socioeconomic-enrich", "--grid", "runs/owned/us_grid_dataset.parquet",
            "--boundary-year", "2024",
        ])
    assert exc.value.code == 2
