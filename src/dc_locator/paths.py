"""Project-root discovery and the canonical directory layout.

Every module that needs a filesystem path goes through this module, so
there is exactly one definition of "where is the project root" and "where do
configs / data / runs / docs / tests live" (AGENTS.md section 5).

Root discovery deliberately does *not* cache its result: a cached root would
go stale under `monkeypatch.chdir(...)` in tests or any other mid-process
working-directory change, and the filesystem walk this performs is a few
`is_file()` checks -- cheap enough to repeat on every call.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional


class ProjectRootNotFoundError(RuntimeError):
    """No `pyproject.toml` was found walking up from any search start point."""


_MARKER_FILE = "pyproject.toml"


def find_project_root(start: Optional[Path] = None) -> Path:
    """Return the project root: the nearest ancestor directory containing
    `pyproject.toml`.

    Search order:

    1. If `start` is given, walk up from it only (deterministic for tests).
    2. Otherwise, walk up from the current working directory first (so
       running a command from any subdirectory of a checkout works), then
       fall back to walking up from this file's own location (so an
       editable install still resolves correctly even if invoked with a
       working directory outside the checkout).
    """
    search_starts: list[Path] = []
    if start is not None:
        search_starts.append(Path(start).resolve())
    else:
        search_starts.append(Path.cwd().resolve())
        search_starts.append(Path(__file__).resolve().parent)

    seen: set[Path] = set()
    for base in search_starts:
        for candidate in (base, *base.parents):
            if candidate in seen:
                continue
            seen.add(candidate)
            if (candidate / _MARKER_FILE).is_file():
                return candidate

    raise ProjectRootNotFoundError(
        f"Could not find {_MARKER_FILE} walking up from any of {[str(s) for s in search_starts]}; "
        "dc_locator must be run from within its project checkout."
    )


def project_root() -> Path:
    """Convenience wrapper over `find_project_root()` with default search."""
    return find_project_root()


def ensure_dir(path: Path) -> Path:
    """Create `path` (and parents) if missing, and return it unchanged."""
    path.mkdir(parents=True, exist_ok=True)
    return path


# --------------------------------------------------------------------------
# Canonical directories (AGENTS.md section 5)
# --------------------------------------------------------------------------


def configs_dir() -> Path:
    return project_root() / "configs"


def data_dir() -> Path:
    return project_root() / "data"


def raw_dir() -> Path:
    """Cached original downloads. Git-ignored; see AGENTS.md section 4."""
    return data_dir() / "raw"


def interim_dir() -> Path:
    """Resumable per-tile intermediate results. Git-ignored."""
    return data_dir() / "interim"


def processed_dir() -> Path:
    """Real-data geography outputs ONLY. `dc_locator.io` refuses to write
    `data_mode=synthetic` anywhere under this directory."""
    return data_dir() / "processed"


def runs_dir() -> Path:
    return project_root() / "runs"


def run_dir(run_name: str) -> Path:
    return runs_dir() / run_name


def docs_dir() -> Path:
    return project_root() / "docs"


def tests_dir() -> Path:
    return project_root() / "tests"


def fixtures_dir() -> Path:
    """Synthetic fixtures live ONLY here (AGENTS.md section 3.6)."""
    return tests_dir() / "fixtures"


def source_raw_dir(source_id: str) -> Path:
    return raw_dir() / source_id


def source_interim_dir(source_id: str) -> Path:
    return interim_dir() / source_id


__all__ = [
    "ProjectRootNotFoundError",
    "find_project_root",
    "project_root",
    "ensure_dir",
    "configs_dir",
    "data_dir",
    "raw_dir",
    "interim_dir",
    "processed_dir",
    "runs_dir",
    "run_dir",
    "docs_dir",
    "tests_dir",
    "fixtures_dir",
    "source_raw_dir",
    "source_interim_dir",
]
