"""Complete declared north-query inputs, independent of any rendered Stable exports."""
import json

import yori
from atelier.model_files import member
from craterpark.v2 import v4_config


def generated():
    return ('world.json', 'heightmap.npy', 'farhills.npy', 'megapark/trail.json',
            'treehouse/trees/trees.json',
            *(('craterpark/v2/geometry.npz',) if v4_config.selected() else ()))


def committed():
    result = {yori.ASSETS / 'vehicles/belmonte-train/line.json'}
    root = yori.ASSETS / 'megapark'; manifest = root / 'map.json'; result.add(manifest)
    value = json.loads(manifest.read_text())
    for row in [*value['models'], *value['collision']]: result.add(root / member(row['npz']))
    if v4_config.selected(): result.update(v4_config.input_paths())
    else:
        root = yori.ASSETS / 'craterpark'
        result.update((root / 'scene.json', root / 'drop-in.json'))
        def arrays(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    if key == 'npz': result.add(root / member(child))
                    else: arrays(child)
            elif isinstance(value, list):
                for child in value: arrays(child)
        arrays(json.loads((root / 'scene.json').read_text()))
    return sorted(result)
