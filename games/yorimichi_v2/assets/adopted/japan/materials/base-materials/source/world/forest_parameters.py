"""Strict one-species forest construction inputs, independent of other species parameters."""
import json
from pathlib import Path
import math
from atelier.export_manifest import name as mesh_name


def load(path):
    value = json.loads(Path(path).read_text())
    if set(value) != {'schema','name','args'} or value['schema'] != 1 or value['name'] != Path(path).stem:
        raise ValueError('Invalid selected forest parameters')
    name, args = mesh_name(value['name']), value['args']
    if (not name.startswith(('Tree_Tuscan_','Tree_Forest_')) or len(args) != 5 or
            type(args[1]) is not int or not isinstance(args[0], str) or not isinstance(args[-1], str) or
            any(type(v) not in (int,float) or not math.isfinite(v) or v <= 0 for v in args[2:4])):
        raise ValueError('Invalid forest construction arguments')
    return name, args
