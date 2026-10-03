"""Phase 6 model validation API."""

from dc_locator.model.validation.config import Phase6Config, load_phase6_config


def run_phase6(*args, **kwargs):
    from dc_locator.model.validation.runner import run_phase6 as _run_phase6
    return _run_phase6(*args, **kwargs)

__all__ = ["Phase6Config", "load_phase6_config", "run_phase6"]
