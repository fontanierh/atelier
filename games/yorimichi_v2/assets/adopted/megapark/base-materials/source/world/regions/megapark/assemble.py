"""Gather MegaPark files and placements; render/collision geometry stays separate."""
import argparse
import json
from pathlib import Path
import sys
sys.path[:0] = [str(Path(__file__).resolve().parents[2]), str(Path(__file__).resolve().parents[1])]
import yori  # noqa: E402
from megapark import build, atomic_common  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--parent', action='append', required=True)
    args = parser.parse_args(argv)
    build.OUT = args.out / 'megapark'
    source = json.loads((build.SOURCE / 'map.json').read_text())
    groups, materials = atomic_common.assemble_files(args.out, 'megapark', args.parent)
    report = dict(source_sha256=build.sha(build.SOURCE / 'map.json'), render=[], collision=[], seam=[],
                  materials=materials, foliage_only=[], rails=[build.sample_rail(r) for r in source['rails']],
                  spawn=source['spawn'], summary=source['summary'], textures=source['textures'])
    for model in source['models']:
        parent = 'SM_MP_' + model['asset_id'][2:]
        if parent in groups:
            report['render'].extend(groups[parent])
        else:
            if any(not build.plants.is_foliage(p) and not build.cars.is_car(model, p) for p in model['meshes']):
                raise ValueError('Missing rendered logical MegaPark source')
            report['foliage_only'].append(parent)
    for section in source['collision']:
        report['collision'].extend(groups['UC_MP_' + section['id']])
    report['seam'] = groups['SM_MP_Seam'] + groups['UC_MP_Seam']
    seed = groups['SM_MP_ImportSeed']
    if len(seed) != 1 or seed[0]['name'] != 'SM_MP_ImportSeed':
        raise ValueError('Invalid park native import seed')
    build.write_fallbacks()
    atomic_json(build.OUT / 'build.json', report)
    build.write_island(report)
    print('MEGAPARK ASSEMBLY COMPLETE', len(report['render']), len(report['collision']), flush=True)


if __name__ == '__main__':
    main()
