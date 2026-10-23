"""Actual tree outline controls versus complete independently exported lower-level pieces."""
import sys
sys.dont_write_bytecode = True
import argparse
from collections import Counter
from pathlib import Path
import os

import bpy

GAME = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(GAME/'world'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'native'))
import yori  # noqa: E402,F401
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.blender.fbx import export_fbx  # noqa: E402
from atelier.build_inputs import local_imports  # noqa: E402
from atelier.export_manifest import real_directory, sha  # noqa: E402
from fbx_corners import read as corners, polygon_cycles  # noqa: E402
from hidamari import source_context  # noqa: E402
from hidamari.tree_policy import TREES  # noqa: E402
from hidamari.plan_asset import main as base_plan  # noqa: E402
from hidamari.plan_tree_lod import main as lod_plan  # noqa: E402
from region_mesh_parts import validate  # noqa: E402
from export_region_piece import main as exporter  # noqa: E402

OPTIONS = dict(use_selection=True, apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL',
               axis_forward='-Y', axis_up='Z', object_types={'MESH'}, mesh_smooth_type='FACE',
               bake_anim=False, use_custom_props=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    root = real_directory(args.output)
    if os.path.lexists(root): raise ValueError('Tree LOD proof requires fresh output')
    region = GAME/'world/regions/hidamari'
    inputs = {Path(__file__), Path(corners.__code__.co_filename)}
    for script in (region/'plan_asset.py', region/'plan_tree_lod.py', GAME/'world/export_region_piece.py'):
        inputs.update(local_imports(script, (GAME/'world', GAME/'world/regions')))
    for key in TREES:
        parameters = GAME/'assets/hidamari/export-parameters'/(key+'.json')
        inputs.update(source_context.inputs(parameters, key))
        inputs.update(local_imports(region/'logical'/(key+'.py'), (GAME/'world', GAME/'world/regions')))
    before = {str(path): sha(path) for path in sorted(inputs)}
    root.mkdir(parents=True)
    results = {}
    for key in TREES:
        parameters = GAME/'assets/hidamari/export-parameters'/(key+'.json')
        base_root = root/'base'/key
        base_plan(['--asset',key,'--context',str(parameters),'--output',str(base_root)])
        base = validate(base_root)
        results[key] = dict(base_pieces=len(base['pieces']), source_triangles=base['source_triangles'], levels={})
        for level in (1,2):
            planned = root/'planned'/(key+'_LOD'+str(level))
            lod_plan(['--asset',key,'--level',str(level),'--base',str(base_root),
                      '--context',str(parameters),'--output',str(planned)])
            value = validate(planned)
            control = root/(key+'_control_LOD'+str(level)+'.fbx')
            obj = bpy.data.objects[key+'_LOD'+str(level)]
            bpy.ops.object.select_all(action='DESELECT'); obj.select_set(True)
            bpy.context.view_layer.objects.active = obj
            # Whole diagnostic control only; excluded from production export membership.
            export_fbx(filepath=str(control), **OPTIONS)
            expected = corners(control)
            actual = dict(render=Counter(), collision=Counter())
            for row in value['pieces']:
                folder = root/'exports'/row['name']
                exporter(['--input',str(planned/row['payload']),'--output',str(folder)])
                emitted = corners(folder/(row['name']+'.fbx'))
                for kind in actual: actual[kind].update(emitted[kind])
            assert polygon_cycles(actual) == polygon_cycles(expected), (key, level, 'complete lower-level corner conservation')
            assert [row['source_faces'] for row in value['pieces']] == [row['source_faces'] for row in base['pieces']]
            results[key]['levels'][str(level)] = dict(pieces=len(value['pieces']), triangles=value['source_triangles'])
            print('ATOMIC TREE LOD EXPORTED',key,level,len(value['pieces']),value['source_triangles'],flush=True)
    assert {str(path): sha(path) for path in sorted(inputs)} == before
    atomic_json(root/'result.json',dict(complete=True, exact_exported_corners=True,
        exact_base_payloads=True, exact_base_face_membership=True, sources=results, inputs=before,
        scope='complete numeric exported polygon/corner/UV/colour/material conservation and exact base payload proof; native receiving/runtime pending'))
    print('ATOMIC CITY TREE LOD CANARY COMPLETE',flush=True)


if __name__ == '__main__': main()
