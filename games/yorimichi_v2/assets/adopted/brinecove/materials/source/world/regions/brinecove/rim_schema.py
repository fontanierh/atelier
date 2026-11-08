"""Strict receiving of an explicit final coastal boundary projection."""
import math
from brinecove import region

SIDES = {'south', 'north', 'west', 'east'}


def read(value):
    if (set(value) != {'schema', 'owner', 'stage', 'city', 'sides', 'world'}
            or value['schema'] != 1 or value['owner'] != 'FarHills'
            or value['stage'] != 'final' or value['city'] is not True
            or set(value['sides']) != SIDES or set(value['world']) != SIDES):
        raise ValueError('Invalid final coast boundary identity')
    for table, size in ((value['sides'], 2), (value['world'], 3)):
        for rows in table.values():
            if (not isinstance(rows, list) or len(rows) < 2
                    or any(len(row) != size or not all(math.isfinite(v) for v in row) for row in rows)):
                raise ValueError('Incomplete or nonfinite final coast boundary')
    sides = {name: [tuple(row) for row in rows] for name, rows in value['sides'].items()}
    if any(rows != sorted(rows) for rows in sides.values()):
        raise ValueError('Unordered final coast boundary')
    return region.Rim(sides), {name: [tuple(row) for row in rows] for name, rows in value['world'].items()}

