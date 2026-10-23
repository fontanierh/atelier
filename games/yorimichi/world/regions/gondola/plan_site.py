"""Plan one fitted Gondola mesh, retaining coordinated three-LOD rope children."""
import argparse
import json
from pathlib import Path
import sys

WORLD = Path(__file__).resolve().parents[2]
KIT = WORLD.parent / 'assets/vehicles/gondola'
sys.path[:0] = [str(KIT),str(WORLD)]
import yori  # noqa: E402,F401
import bpy  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import TRIANGLE_LIMIT,name  # noqa: E402
from region_mesh_parts import plan  # noqa: E402
from regions.gondola.plan_kit import source,FIELDS,OPTIONS  # noqa: E402
from commands import replay  # noqa: E402
import solid  # noqa: E402


def rope_groups(key,faces,count):
    """Preserve every original face once, with one stable child roster for all LODs."""
    if type(count) is not int or count <= 0: raise ValueError('Invalid logical Gondola rope component count')
    if count == 1: return [(key,tuple(range(len(faces))))]
    weights = [len(face)-2 for face in faces]; total = sum(weights)
    groups = [[] for _ in range(count)]; accumulated = 0
    for index,weight in enumerate(weights):
        owner = min(count-1,accumulated*count//total)
        groups[owner].append(index); accumulated += weight
    if any(not group or sum(weights[index] for index in group)>TRIANGLE_LIMIT for group in groups):
        raise ValueError('Gondola rope LOD cannot fit its coordinated bounded roster')
    return [(key+f'_Piece{index:02d}',tuple(group)) for index,group in enumerate(groups)]


def construct(value):
    if not name(value['asset']).startswith('GD_'): raise ValueError('Unknown selected Gondola site mesh')
    mesh = replay(value,solid.Mesh)
    report = solid.closed(mesh)
    if any(report[key] for key in ('open_edges','misoriented_edges','degenerate_faces')):
        raise ValueError('Original fitted Gondola closure gate failed')
    obj,slots = solid.to_object(mesh,solid.make_materials({}))
    group = value.get('rope_group')
    groups = None if group is None else rope_groups(mesh.name,mesh.faces,group['components'])
    query = dict(schema=1,asset=mesh.name,mesh={field:getattr(mesh,field) for field in FIELDS},
                 report=report,materials=slots)
    return obj,query,groups


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset',required=True)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--queries',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--')+1:])
    selected = source(args.source,args.asset)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    obj,query,groups = construct(selected)
    value = plan(obj,args.output,options=OPTIONS,face_groups=groups)
    query['triangles'] = value['source_triangles']
    atomic_json(args.queries,query)
    print('GONDOLA SITE LOGICAL PLAN COMPLETE',args.asset,len(value['pieces']),flush=True)


if __name__ == '__main__': main()
