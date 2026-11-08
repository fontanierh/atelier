"""Pose selection shared by capture_runtime.py and compare.py: `--only` picks a subset of a poses file by name.

    --only 'w07_*'                    one world row (fnmatch glob on the pose name)
    --only 'w07_*,w12_crater_*'       several globs, comma separated
    --only w07_clock_hall --only ...  or the option repeated

Every glob must match at least one pose, so a typo cannot quietly capture or compare nothing.
"""
from __future__ import annotations

import fnmatch
import json
from pathlib import Path


def load_poses(path: Path) -> list[dict]:
    return json.loads(Path(path).read_text())['poses']


def select(poses: list[dict], only) -> list[dict]:
    """The poses matching any glob in `only` (a string, a list of strings, or None for all), in file order."""
    if not only:
        return poses
    patterns = [part.strip() for item in ([only] if isinstance(only, str) else only) for part in item.split(',')]
    patterns = [pattern for pattern in patterns if pattern]
    unmatched = [p for p in patterns if not any(fnmatch.fnmatchcase(pose['name'], p) for pose in poses)]
    if unmatched:
        raise ValueError(f'--only matches no pose: {", ".join(unmatched)}')
    return [pose for pose in poses if any(fnmatch.fnmatchcase(pose['name'], p) for p in patterns)]
