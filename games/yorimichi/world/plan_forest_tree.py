"""Plan one selected forest level; all authored level geometry remains separate."""
import argparse
import json
from pathlib import Path
import sys
sys.path[:0] = [str(Path(__file__).resolve().parent), str(Path(__file__).resolve().parent / 'regions')]
import yori  # noqa: E402,F401
from atelier.atomic_files import atomic_json  # noqa: E402
from region_mesh_parts import plan  # noqa: E402
from forest_parameters import load  # noqa: E402
import forest_source as source  # noqa: E402

OPTIONS = dict(apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL', axis_forward='-Y', axis_up='Z',
               mesh_smooth_type='FACE', path_mode='STRIP', embed_textures=False, use_tspace=False, colors_type='SRGB')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parameters', type=Path, required=True)
    parser.add_argument('--level', type=int, choices=range(5), required=True)
    parser.add_argument('--frame', type=Path)
    parser.add_argument('--proxy', type=Path)
    parser.add_argument('--record', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--') + 1:])
    name, parameters = load(args.parameters)
    bark = source.initialize(name, parameters)
    record = dict(name=name, level=args.level)
    if args.level == 0:
        obj = source.base(name, parameters)
        record.update(source.bounds(obj))
    else:
        frame = json.loads(args.frame.read_text())
        if frame.get('name') != name or frame.get('level') != 0:
            raise ValueError('Foreign canonical forest bounds')
        if args.level in (1,2):
            obj = source.detail(name, parameters, args.level, frame)
        elif args.level == 3:
            proxy = json.loads(args.proxy.read_text())
            if proxy.get('name') != name:
                raise ValueError('Foreign impostor view geometry')
            obj = source.forest_impostors.mesh(name, proxy['record'], source.A.MATS[bark])
        else:
            obj, record['crown'] = source.crown(name, parameters, frame)
    collisions = source.trunk(obj) if args.level == 0 else []
    value = plan(obj, args.output, collisions=collisions, options=OPTIONS)
    if args.level == 0:
        record['trunk_hulls'] = collisions
    if len(value['pieces']) != 1 or value['pieces'][0]['name'] != obj.name:
        raise ValueError('An authored HISM LOD must remain one bounded primary; change requires coordinated LOD membership')
    record['triangles'] = value['source_triangles']
    atomic_json(args.record, record)
    print('FOREST LOGICAL COMPLETE', obj.name, record['triangles'], flush=True)


if __name__ == '__main__':
    main()
