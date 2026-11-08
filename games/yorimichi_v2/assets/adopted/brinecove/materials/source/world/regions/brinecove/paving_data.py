"""Complete explicit paving inputs for the separately constructed final coast ground."""
import json
import math
from pathlib import Path

from atelier.export_manifest import real_directory

OWNERS = ('Rocks', 'Harbor', 'TownLower', 'Market', 'TownUpper', 'Landmarks', 'Ships', 'Props', 'Understory')


def read_all(paths):
    """@cc [owner:fontanierh,label:correctness] complete-coastal-paving-owners
    Require exactly one current explicit rectangle projection from every procedural
    owner before ground finishing. Do not execute sibling constructors or inspect their
    exported meshes. Unknown, duplicate, missing, linked or malformed projections MUST
    refuse before the ground planner writes its output.
    """
    selected = {}
    for raw in paths:
        path = Path(raw)
        real_directory(path.parent)
        if path.is_symlink() or not path.is_file():
            raise ValueError('Paving inputs must be regular and unlinked')
        value = json.loads(path.read_text())
        if (set(value) != {'schema', 'owner', 'rectangles'} or type(value['schema']) is not int
                or value['schema'] != 1 or value['owner'] not in OWNERS or value['owner'] in selected
                or type(value['rectangles']) is not list or len(value['rectangles']) > 100_000):
            raise ValueError('Foreign or duplicate coastal paving projection')
        rows = value['rectangles']
        if any(type(row) is not list or len(row) != 5
               or any(type(v) not in (int, float) or not math.isfinite(v) for v in row)
               or row[0] > row[1] or row[2] > row[3] for row in rows):
            raise ValueError('Malformed coastal paving rectangles')
        selected[value['owner']] = rows
    if set(selected) != set(OWNERS):
        raise ValueError('Incomplete coastal paving owner inventory')
    return [row for owner in OWNERS for row in selected[owner]]
