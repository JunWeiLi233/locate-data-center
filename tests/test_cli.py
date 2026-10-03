"""Tests for dc_locator.cli: the command surface (AGENTS.md section 5; phase1.md.txt step 8).

Only `build-grid`'s *wiring* (argument parsing) is covered here cheaply;
its end-to-end behaviour against real downloaded data is exercised by the
`real_data`-marked test in tests/test_cli_build_grid_real.py, since a true
run regenerates data/processed/us_grid*.parquet and takes minutes at the
national scale (see docs/limitations.md).
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from dc_locator.cli import _DELIVERY_COMMANDS, build_parser, main


def test_version_flag(capsys: pytest.CaptureFixture) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0
    assert "dc_locator" in capsys.readouterr().out


def test_no_command_errors() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args([])


@pytest.mark.parametrize("name", _DELIVERY_COMMANDS)
def test_delivery_commands_execute_actual_handler(name,monkeypatch,capsys) -> None:
    import dc_locator.pipeline as pipeline
    calls=[]
    monkeypatch.setattr(pipeline,'execute_stage',lambda stage,config,output: calls.append((stage,config,output)) or {'stage':stage})
    assert main([name,'--config','configs/run_synthetic.yaml','--output','runs/phase7_cli'])==0
    assert calls==[(name,'configs/run_synthetic.yaml','runs/phase7_cli')]
    assert name in capsys.readouterr().out


def test_build_grid_subcommand_registered() -> None:
    parser = build_parser()
    args = parser.parse_args(["build-grid", "--national-only", "--skip-download"])
    assert args.command == "build-grid"
    assert args.national_only is True
    assert args.skip_download is True
    assert args.func.__name__ == "_cmd_build_grid"


def test_module_entrypoint_shows_help_without_crashing() -> None:
    # python -m dc_locator --help must not raise ModuleNotFoundError (the
    # exact failure mode the original broken `dc-locator` console script had).
    result = subprocess.run(
        [sys.executable, "-m", "dc_locator", "--help"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0
    assert "build-grid" in result.stdout
