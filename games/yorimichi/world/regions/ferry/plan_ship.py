"""Construct exactly one ferry ship part and publish its complete pre-export queries."""
import argparse
import json
from pathlib import Path
import sys

WORLD = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORLD))
import yori  # noqa: E402,F401
import bpy  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import real_directory  # noqa: E402
from region_mesh_parts import plan  # noqa: E402
from regions.ferry.ship_sources import BUILD, BUILDERS  # noqa: E402

OPTIONS = dict(apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL', axis_forward='-Y',
               axis_up='Z', mesh_smooth_type='EDGE', use_custom_props=False)


def source(path, asset):
    real_directory(path.parent)
    if path.is_symlink() or not path.is_file():
        raise ValueError('Ferry source must be a regular data product')
    value = json.loads(path.read_text())
    if (value.get('schema') != 1 or value.get('asset') != asset
            or not isinstance(value.get('program'), str)):
        raise ValueError('Foreign selected ferry constructor program')
    return value


def construct(asset, selected):
    if asset not in BUILDERS or selected['constructor'] != BUILDERS[asset]:
        raise ValueError('Foreign ferry constructor selection')
    namespace = dict(__file__=str(BUILD), __name__='ferry_selected_constructor')
    exec(compile(selected['program'], str(BUILD), 'exec'), namespace)
    for key in ('SEATS', 'BLOCKS', 'BOAT_FACES'):
        namespace.setdefault(key, [])
    materials = namespace['make_materials']()
    mesh = namespace['Mesh'](asset)
    namespace[BUILDERS[asset]](mesh)
    report = namespace['check'](mesh)
    if report['open_edges']:
        raise ValueError(f'{asset}: original closure gate failed: {report}')
    obj, slots = namespace['to_object'](mesh, materials)
    query = dict(schema=1, asset=asset, vertices=mesh.verts, faces=mesh.faces,
                 seats=namespace['SEATS'], blocks=namespace['BLOCKS'], boat_faces=namespace['BOAT_FACES'],
                 materials=slots, report=report)
    return obj, query


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset', choices=BUILDERS, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--queries', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--') + 1:])
    selected = source(args.source, args.asset)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    obj, query = construct(args.asset, selected)
    value = plan(obj, args.output, options=OPTIONS)
    query['triangles'] = value['source_triangles']
    query['min'] = [round(min(v[i] for v in query['vertices']), 3) for i in range(3)]
    query['max'] = [round(max(v[i] for v in query['vertices']), 3) for i in range(3)]
    atomic_json(args.queries, query)
    print('FERRY SHIP LOGICAL PLAN COMPLETE', args.asset, len(value['pieces']), flush=True)


if __name__ == '__main__': main()
