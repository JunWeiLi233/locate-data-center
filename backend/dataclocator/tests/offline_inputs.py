"""Mount byte-identical local evidence without Windows symlink privileges."""

import os
from pathlib import Path
import shutil


def _link_or_copy(source, target):
    """Share read-only test inputs on one volume, copying bytes when links are unavailable."""
    try:
        os.link(source, target)
    except OSError:
        # Different volumes/filesystems can still verify the same frozen evidence.
        shutil.copy2(source, target)
    return target


def mount_offline_inputs(root: Path, target: Path):
    """Keep test outputs isolated while reusing unchanged official source/derived bytes."""
    # These tests never write input artifacts; deleting scratch removes only its links.
    shutil.copytree(root / "data", target / "data", copy_function=_link_or_copy)
    shutil.copytree(root / "outputs/task2", target / "outputs/task2", copy_function=_link_or_copy)
    (target / "configs").mkdir()
    shutil.copy2(root / "configs/candidates.json", target / "configs/candidates.json")
