"""Independent source models consumed by Brinecove's placement/export assembly."""
import hashlib
import json
import math
from pathlib import Path

from brinecove.foliage_names import name, definitions


def load(root):
    """@cc [owner:fontanierh,label:correctness] complete-independent-plant-library
    Every declared model MUST have its own complete generated source product, independent of
    placements and terrain. Assembly MUST verify its declared model bytes and stable logical
    name; missing, linked, changed or extra model members MUST fail, never regenerate inline.
    """
    root = Path(root)
    result = {}
    for definition in definitions():
        prototype = definition.stem
        folder = root / prototype
        if (root.is_symlink() or folder.is_symlink() or not folder.is_dir()
                or {p.name for p in folder.iterdir()} != {'model.glb', 'model.json'}):
            raise ValueError('Incomplete independent foliage model: ' + prototype)
        paths = [folder / 'model.glb', folder / 'model.json']
        if any(p.is_symlink() or not p.is_file() for p in paths):
            raise ValueError('Invalid foliage model members: ' + prototype)
        model = json.loads(paths[1].read_text())
        if (not isinstance(model, dict)
                or set(model) != {'name', 'sha256', 'triangles', 'bounds_m', 'slots', 'collision', 'lods'}
                or model['name'] != name(prototype)
                or type(model['triangles']) is not int or model['triangles'] <= 0
                or model['collision'] is not False or model['lods'] is not True
                or not isinstance(model['slots'], list) or not model['slots']
                or any(not isinstance(slot, str) or not slot for slot in model['slots'])
                or len(set(model['slots'])) != len(model['slots'])
                or not isinstance(model['bounds_m'], list) or len(model['bounds_m']) != 2
                or any(not isinstance(point, list) or len(point) != 3
                       or any(type(value) not in (int, float) or not math.isfinite(value) for value in point)
                       for point in model['bounds_m'])
                or any(low > high for low, high in zip(*model['bounds_m']))
                or hashlib.sha256(paths[0].read_bytes()).hexdigest() != model['sha256']):
            raise ValueError('Foliage model differs from its product: ' + prototype)
        result[prototype] = model
    if not result:
        raise ValueError('Empty foliage model library')
    return result
