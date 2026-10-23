"""Compare the actual legacy Harbor FBX cut with direct source-data atomic exports."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import sys

import bpy
from mathutils import Matrix

GAME = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(GAME / 'world'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'native'))
import yori  # noqa: E402,F401
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.blender.fbx import export_fbx  # noqa: E402
from atelier.build_inputs import local_imports  # noqa: E402
from atelier.export_manifest import real_directory, sha  # noqa: E402
from fbx_corners import read as corners, polygon_cycles  # noqa: E402
from mesh_pieces import create_mesh  # noqa: E402
from region_mesh_parts import validate  # noqa: E402
from region_plan_files import files as source_files  # noqa: E402
import source_geometry  # noqa: E402

OPTIONS = dict(use_selection=True, apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL',
               axis_forward='-Y', axis_up='Z', object_types={'MESH'}, mesh_smooth_type='FACE',
               bake_anim=False, use_custom_props=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--site', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    root = real_directory(args.output)
    if os.path.lexists(root): raise ValueError('Harbor cut proof requires a fresh root')
    real_directory(args.site.parent)
    if args.site.is_symlink() or not args.site.is_file(): raise ValueError('Cut proof requires regular site parameters')
    region = GAME / 'world/regions/hidamari'
    files = {Path(__file__), Path(corners.__code__.co_filename), args.site,
             *(args.source / relative for relative in source_files(args.source))}
    for script in (region / 'plan_harbor.py', GAME / 'world/export_region_piece.py'):
        files.update(local_imports(script, (GAME / 'world', GAME / 'world/regions')))
    def identities(): return {str(path): sha(path) for path in sorted(files)}
    before = identities()
    source = source_geometry.read(args.source, owner='HD_Harbor')
    site = json.loads(args.site.read_text())
    assert site['pass'] is True
    cuts = site['hidamari']['berth']['world_cuts']
    bpy.ops.wm.read_factory_settings(use_empty=True)
    source['slots'] = [bpy.data.materials.new(label) for label in source['slots']]
    obj = bpy.data.objects.new('HD_Harbor', create_mesh('HD_Harbor', source))
    bpy.context.collection.objects.link(obj); obj.matrix_world = Matrix(source['matrix'])
    obj.select_set(True); bpy.context.view_layer.objects.active = obj
    root.mkdir(parents=True)
    # Deliberately whole diagnostic control, excluded from production membership.
    export_fbx(filepath=str(root / 'raw-control.fbx'), **OPTIONS)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(root / 'raw-control.fbx'))
    objects = [o for o in bpy.data.objects if o.type == 'MESH']
    assert len(objects) == 1
    from hidamari.ferry_cut import cut_object
    control = cut_object(objects[0], cuts)
    assert control['failures'] == [] and control['triangles'] == {'before': 190920, 'after': 190896}
    export_fbx(filepath=str(root / 'final-control.fbx'), **OPTIONS)
    expected = corners(root / 'final-control.fbx')
    cut_data = root / 'cut-data.json'
    atomic_json(cut_data, dict(schema=1, owner='HD_Harbor', stage='final', cuts=cuts))
    from hidamari.plan_harbor import main as planner
    planner(['--source', str(args.source), '--cut-data', str(cut_data), '--output', str(root / 'planned'),
             '--query-output', str(root / 'query.npz'), '--proof-output', str(root / 'cut.json')])
    actual_cut = json.loads((root / 'cut.json').read_text())
    assert actual_cut['triangles'] == control['triangles'] and actual_cut['cuts'] == control['cuts']
    value = validate(root / 'planned')
    actual = dict(render=Counter(), collision=Counter())
    from export_region_piece import main as exporter
    for row in value['pieces']:
        folder = root / 'exports' / row['name']
        exporter(['--input', str(root / 'planned' / row['payload']), '--output', str(folder)])
        emitted = corners(folder / (row['name'] + '.fbx'))
        for kind in actual: actual[kind].update(emitted[kind])
        print('FINAL HARBOR ATOMIC EXPORT', row['name'], flush=True)
    assert polygon_cycles(actual) == polygon_cycles(expected), 'Final Harbor complete serialized polygon/corner/material/UV/colour conservation differs'
    assert identities() == before
    atomic_json(root / 'result.json', dict(complete=True, source_triangles=190920, final_triangles=190896,
        pieces=len(value['pieces']), exact_exported_corners=True, exact_cut_controls=True, inputs=before,
        scope='exact exported polygon cycles, preserving winding and values; full ferry sweep/native receiving/traversal pending'))
    print('HARBOR SOURCE DATA CUT CANARY COMPLETE', flush=True)


if __name__ == '__main__': main()
