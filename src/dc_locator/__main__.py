"""Enables `python -m dc_locator ...` as an alternative to the `dc-locator` console script."""

from __future__ import annotations

import sys

from dc_locator.cli import main

if __name__ == "__main__":
    sys.exit(main())
