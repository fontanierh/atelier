"""Compose explicit coastal query geometry and placements without opening mesh exports."""
import argparse
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import yori  # noqa: E402,F401
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import name, real_directory, sha  # noqa: E402


def snapshot(out, *, parents, heroes):
    """@cc [owner:fontanierh,label:correctness;performance] coastal-query-data-before-exports
    Ferry/clearance query data MUST use complete final constructor query surfaces
    and original logical instance transforms before any GLB is exported. Every
    selected geometry owner and hero placement MUST be explicit and complete.
    No generated mesh export, Blender scene or region-wide render assembly may
    supply query geometry. This data composition MUST NOT join native meshes.
    """
    import region_query
    from brinecove import region
    from brinecove.runtime_data import IDENTITY
    from brinecove.plan_hero import key as hero_key
    parents, heroes = tuple(parents), tuple(heroes)
    if (not parents or len({name(parent).casefold() for parent in parents}) != len(parents)
            or not heroes or len(set(heroes)) != len(heroes)
            or any(not name(parent).startswith('SM_BC_') for parent in parents)):
        raise ValueError('Coastal query inventory requires explicit unique owners')
    placements = out / 'brinecove-data/placements.json'
    real_directory(placements.parent)
    if placements.is_symlink() or not placements.is_file():
        raise ValueError('Coastal queries require complete current placements')
    data = json.loads(placements.read_text())
    if data.get('schema') != 1 or set(data['heroes']) != set(heroes):
        raise ValueError('Coastal query hero placements differ from their complete owners')
    hero_names = {hero_key(slug): slug for slug in heroes}
    if len({key.casefold() for key in hero_names}) != len(heroes) or not set(hero_names) <= set(parents):
        raise ValueError('Coastal query source roster omits hero geometry')
    rows = []
    for parent in parents:
        relative = 'brinecove/query-data/' + parent + '.npz'
        path = out / relative
        region_query.load(path, owner=parent, stage='final')
        transforms = data['heroes'][hero_names[parent]] if parent in hero_names else [IDENTITY]
        if not transforms:
            raise ValueError('Coastal query source lacks its logical placements')
        for transform in transforms:
            sizes = {'translation_cm': 3, 'rotation_xyzw': 4, 'scale': 3}
            if (not isinstance(transform, dict) or set(transform) != set(sizes)
                    or any(not isinstance(transform[key], list) or len(transform[key]) != size
                           or any(type(v) not in (int, float) or not math.isfinite(v) for v in transform[key])
                           for key, size in sizes.items())
                    or any(v == 0 for v in transform['scale'])
                    or abs(sum(v * v for v in transform['rotation_xyzw']) - 1) > 1e-3):
                raise ValueError('Invalid coastal logical query placement')
        rows.append(dict(owner=parent, path=relative, sha256=sha(path), transforms=transforms))
    return dict(schema=1, stage='final', origin_cm=[region.ORIGIN[0] * 100., -region.ORIGIN[1] * 100., region.ORIGIN[2] * 100.],
                models=rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--parent', action='append', required=True)
    parser.add_argument('--hero', action='append', required=True)
    args = parser.parse_args(argv)
    value = snapshot(args.out, parents=args.parent, heroes=args.hero)
    real_directory(args.output.parent)
    if args.output.is_symlink() or (args.output.exists() and not args.output.is_file()):
        raise ValueError('Coastal query publication requires a regular owned file')
    atomic_json(args.output, value)
    print('COASTAL QUERY DATA COMPLETE', len(value['models']), flush=True)


if __name__ == '__main__': main()
