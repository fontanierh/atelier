"""Project each island constructor's consumed data before any render export."""
import argparse
import json
from pathlib import Path

import numpy as np

from atelier.atomic_files import atomic_json, managed_temporary_parent
from atelier.export_manifest import real_directory

ASSETS = ('Terrain', 'Road', 'Lane', 'Guardrail', 'Wires', 'FarHills', 'Sea')
WORLD_KEYS = dict(Terrain=('n', 'size'), Road=('road', 'road_width'),
                  Lane=('n', 'size', 'southwest'), Guardrail=('rail_runs',),
                  Wires=('anchors',), FarHills=(), Sea=())


def project(world, *, city):
    """@cc [owner:fontanierh,label:correctness;performance] island-constructor-input-projection
    Explicit constructor data MUST precede rendered exports. Each projection MUST contain
    only the selected constructor's consumed world fields and mode; no sibling source SHA,
    export path or revision may enter it. Height and final-ground query owners MUST remain
    independent of rendered piece inventories. Optional lane/rail absence MUST be explicit.
    """
    if type(city) is not bool:
        raise ValueError('Island terrain requires an explicit city mode')
    result = {}
    for key in ASSETS:
        data = json.loads(json.dumps({field: world[field] for field in WORLD_KEYS[key] if field in world},
                                     allow_nan=False))
        if key == 'Lane' and data.get('southwest'):
            data['southwest'] = dict(lane=data['southwest']['lane'])
        enabled = not ((key == 'Lane' and not data.get('southwest'))
                       or (key == 'Guardrail' and not data.get('rail_runs')))
        result[key] = dict(schema=1, asset=key, enabled=enabled, world=data,
                           **({'city': city} if key in ('FarHills', 'Sea') else {}))
    return result


def publish(world, heightmap, output, *, city):
    output = real_directory(output, create=True)
    values = project(world, city=city)
    expected = {'inventory.json', *(key + '.json' for key in ASSETS), 'heightmap.npy'}
    # This is one fixed exclusive data projection. Refuse links/foreign paths before writing.
    for path in output.iterdir():
        if path.name not in expected or path.is_symlink() or not path.is_file():
            raise ValueError('Foreign island source projection member')
    if heightmap.shape != (world['n'], world['n']) or not np.isfinite(heightmap).all():
        raise ValueError('Island heightmap does not match its declared lattice')
    for key, value in values.items():
        atomic_json(output / (key + '.json'), value)
    temporary = managed_temporary_parent(output / 'heightmap.npy') / '.heightmap.npy.tmp'
    with temporary.open('wb') as stream:
        np.save(stream, heightmap, allow_pickle=False)
    temporary.replace(output / 'heightmap.npy')
    atomic_json(output / 'inventory.json', dict(schema=1, assets=[key for key in ASSETS if values[key]['enabled']]))
    return values


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--world', required=True, type=Path)
    parser.add_argument('--heightmap', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--no-city', action='store_true')
    args = parser.parse_args(argv)
    for path in (args.world, args.heightmap):
        real_directory(path.parent)
        if path.is_symlink() or not path.is_file():
            raise ValueError('Island source data must be regular files')
    publish(json.loads(args.world.read_text()), np.load(args.heightmap, allow_pickle=False),
            args.output, city=not args.no_city)


if __name__ == '__main__':
    main()
