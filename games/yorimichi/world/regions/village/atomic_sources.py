"""Explicit selected Village inputs and immutable original random-state contexts."""
import argparse
import ast
import json
from pathlib import Path
import random
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import yori  # noqa: E402,F401
import numpy as np  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import real_directory  # noqa: E402
from village.layout import BUILDINGS  # noqa: E402
from village.catalogue import ASSETS  # noqa: E402

HERE = Path(__file__).resolve().parent
HEIGHTS = {'Village_Garden', 'Village_Ground', 'Village_Edges', 'Village_Planting'}


def contexts(path=yori.ASSETS / 'village/construction-contexts.json'):
    path = Path(path)
    real_directory(path.parent)
    if path.is_symlink() or not path.is_file(): raise ValueError('Missing immutable Village source contexts')
    value = json.loads(path.read_text())
    if (value.get('schema') != 1 or value.get('seed') != 76 or value.get('complete') is not True
            or set(value.get('contexts', {})) != set(ASSETS)):
        raise ValueError('Incomplete original Village random-state inventory')
    for entry in value['contexts'].values():
        restore(random.Random(), entry['state'])
        keys = entry.get('palette_keys')
        if (not isinstance(keys, list) or not keys or keys != sorted(set(keys))
                or any(not isinstance(key, str) or not key for key in keys)):
            raise ValueError('Missing exact Village palette consumption')
    return value['contexts']


def restore(rng, state):
    """Full Mersenne Twister state retains choice/getrandbits as well as uniform draws."""
    if (not isinstance(state, list) or len(state) != 3 or state[0] != 3
            or not isinstance(state[1], list) or len(state[1]) != 625
            or any(type(v) is not int or not 0 <= v < 2**32 for v in state[1][:-1])
            or type(state[1][-1]) is not int or not 0 <= state[1][-1] <= 624
            or state[2] is not None):
        raise ValueError('Invalid complete Village random state')
    rng.setstate((state[0], tuple(state[1]), state[2]))


def current_palette():
    """Read the current source's literal colour table without importing Blender."""
    tree = ast.parse((HERE / 'mesh.py').read_text())
    values = [node.value for node in tree.body if isinstance(node, ast.Assign)
              and any(isinstance(target, ast.Name) and target.id == 'PALETTE' for target in node.targets)]
    if len(values) != 1: raise ValueError('Village needs one explicit source palette')
    result = ast.literal_eval(values[0])
    if (not isinstance(result, dict) or not result or any(not isinstance(key, str) or not key for key in result)
            or any(not isinstance(value, (list, tuple)) or len(value) != 3
                   or any(type(v) not in (int, float) or not np.isfinite(v) for v in value) for value in result.values())):
        raise ValueError('Invalid explicit Village colour table')
    return result


def project(world, random_contexts, *, palette=None):
    """@cc [owner:fontanierh,label:correctness;performance] independent-village-logical-inputs
    Each selected logical constructor MUST consume only its actual geometry parameters,
    final heightmap and immutable predecessor random state. Never reconstruct a sibling
    just to advance a random stream. Placements and unrelated decoration fields MUST NOT
    enter independent building geometry. Random palette values remain current source policy.
    """
    if set(random_contexts) != set(ASSETS): raise ValueError('Village constructor context is incomplete')
    palette = current_palette() if palette is None else palette
    result = {}
    sizes = {row[0]: dict(width=row[3], depth=row[4]) for row in BUILDINGS}
    if tuple(sizes) != ASSETS[:5]: raise ValueError('Village building/source roster differs')
    for key in ASSETS:
        selected = {}
        fields = ('paths',) if key == 'Village_Edges' else (
            ('paths', 'buildings') if key == 'Village_Ground' else
            ('buildings',) if key == 'Village_Details' else
            ('paths', 'buildings', 'planting_beds') if key == 'Village_Planting' else ())
        if fields:
            selected['village'] = {field: world['village'][field] for field in fields}
        if key == 'Village_Ground': selected.update(road=world['road'], road_width=world['road_width'])
        result[key] = dict(schema=1, asset=key, world=selected, parameters=sizes.get(key, {}),
                           random_state=random_contexts[key]['state'],
                           palette={colour: palette[colour] for colour in random_contexts[key]['palette_keys']})
    return json.loads(json.dumps(result, allow_nan=False))


def publish(world, heightmap, output, random_contexts):
    output = real_directory(output, create=True)
    expected = {*(key + '.json' for key in ASSETS), 'heightmap.npy', 'inventory.json', 'placements.json'}
    for path in output.iterdir():
        if path.name not in expected or path.is_symlink() or not path.is_file():
            raise ValueError('Foreign Village source data member')
    if heightmap.ndim != 2 or heightmap.shape[0] != heightmap.shape[1] or not np.isfinite(heightmap).all():
        raise ValueError('Village requires the complete final square heightmap')
    values = project(world, random_contexts)
    for key, value in values.items(): atomic_json(output / (key + '.json'), value)
    temporary = output / '.heightmap.npy.tmp'
    with temporary.open('wb') as stream: np.save(stream, heightmap, allow_pickle=False)
    temporary.replace(output / 'heightmap.npy')
    placements = {key: world['instances'][key] for key in ASSETS}
    atomic_json(output / 'placements.json', dict(schema=1, instances=placements))
    atomic_json(output / 'inventory.json', dict(schema=1, assets=list(ASSETS)))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--world', type=Path, required=True)
    parser.add_argument('--heightmap', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    for path in (args.world, args.heightmap):
        real_directory(path.parent)
        if path.is_symlink() or not path.is_file(): raise ValueError('Village input must be an unlinked regular file')
    publish(json.loads(args.world.read_text()), np.load(args.heightmap, allow_pickle=False), args.output, contexts())


if __name__ == '__main__': main()
