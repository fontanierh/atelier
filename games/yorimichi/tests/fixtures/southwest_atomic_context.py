"""Compare real Southwest constructors and serialized leaves with the immutable original production order."""
import argparse
import ast
from collections import Counter
import hashlib
import importlib
import json
from pathlib import Path
import sys

import bpy

GAME = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(GAME/'world'), str(GAME/'world/regions'), str(Path(__file__).resolve().parent),
               str(Path(__file__).resolve().parents[1]/'native')]
import yori  # noqa: E402,F401
from atelier import export_manifest, mesh_ir  # noqa: E402
from atelier.blender.fbx import export_fbx  # noqa: E402
from atomic_mesh_export import corners  # noqa: E402
from fbx_corners import read as exported_corners  # noqa: E402
from mesh_pieces import capture, subset  # noqa: E402
from random_stream import Counted  # noqa: E402
from region_mesh_parts import plan  # noqa: E402
import export_region_piece  # noqa: E402
import source_geometry  # noqa: E402


MODELS = 'stand,fisher_house_a,fisher_house_b,boat_shed,stairs,dock,boat,drying_rack,temple,island,boulder_a,boulder_b,boulder_c,stone_wall,pine_lean_a,pine_lean_b'.split(',')


def captured(source, material):
    obj = source.object(material)
    value = capture(obj.data)
    piece = subset(value, tuple(range(len(value['counts']))))
    piece['slots'] = [slot.name for slot in piece['slots']]
    return obj, dict(rows=corners(piece), matrix=[list(row) for row in obj.matrix_world],
        diagnostic_boxes=[(tuple(c),tuple(s)) for c,s in source.colliders], triangles=piece['triangles'],
        selection=piece['selection'], polygons=len(source.faces), vertices=len(source.vertices))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--legacy', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    root = export_manifest.real_directory(args.output)
    if root.exists(): raise ValueError('Southwest comparison requires fresh output')
    root.mkdir(parents=True)
    source_files = [*sorted(args.legacy.glob('*.py')), GAME/'world/regions/village/mesh.py',
        *sorted((GAME/'world/regions/southwest').glob('*.py')),
        *sorted((GAME/'world/regions/southwest/contexts').glob('*.json')), Path(__file__),
        GAME/'world/mesh_pieces.py',GAME/'world/region_mesh_parts.py',GAME/'world/export_region_piece.py',
        GAME/'world/region_query.py',GAME/'world/source_geometry.py',GAME/'tests/native/fbx_corners.py']
    def hashes():
        result = {}
        for path in source_files:
            export_manifest.real_directory(path.parent)
            if path.is_symlink() or not path.is_file(): raise ValueError('Linked/missing conservation input')
            result[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        return result
    before = hashes()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.unit_settings.system = 'METRIC'
    sys.path.insert(0,str(args.legacy))
    tree = ast.parse((args.legacy/'build.py').read_text())
    assert ast.unparse(tree.body[-1]) == 'main()'; tree.body.pop()
    original = {'__file__':str(args.legacy/'build.py'),'__name__':'immutable_southwest_original'}
    exec(compile(tree,str(args.legacy/'build.py'),'exec'),original)
    streams = {key: original[key] for key in ('stand','fishing','temple')}
    streams['village'] = importlib.import_module('village.mesh')
    seeds = dict(stand=11,fishing=23,temple=41,village=76)
    counts = {key:Counted(module.R) for key,module in streams.items()}
    for stream in counts.values(): stream.__enter__()
    references, controls, contexts = {}, {}, {}
    material = original['material']()
    for model in MODELS:
        context = {key:counter.context(seeds[key]) for key,counter in counts.items()}
        source = original['MODELS'][model](); obj, reference = captured(source,material)
        source_geometry.write(root/'original-source'/source.name,capture(obj.data),owner=source.name,
            slots=[slot.name for slot in obj.data.materials],matrix=[list(row) for row in obj.matrix_world],collisions=())
        contexts[source.name] = dict(schema=1,model=model,asset=source.name,contexts=context)
        bpy.ops.object.select_all(action='DESELECT'); obj.select_set(True);bpy.context.view_layer.objects.active=obj
        control = root/'controls'/(source.name+'.fbx');control.parent.mkdir(exist_ok=True)
        export_fbx(filepath=str(control), use_selection=True, apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL',
            axis_forward='-Y',axis_up='Z',mesh_smooth_type='FACE',colors_type='SRGB',bake_anim=False)
        references[source.name] = reference; controls[source.name] = exported_corners(control)
        bpy.data.objects.remove(obj,do_unlink=True)
        print('SOUTHWEST ORIGINAL',source.name,reference['triangles'],flush=True)
    for stream in counts.values(): stream.__exit__()
    # A current constructor cannot accidentally import the original standalone mesh module.
    sys.path.remove(str(args.legacy))
    from southwest import models
    from southwest.mesh import material as current_material
    import region_query
    results = {}
    for model in MODELS:
        asset = models.MODELS[model][2]
        context_path = GAME/'world/regions/southwest/contexts'/(asset+'.json')
        assert json.loads(context_path.read_text()) == contexts[asset], (asset,'measured original state differs')
        bpy.ops.wm.read_factory_settings(use_empty=True)
        source = models.construct(model,context_path);obj, actual = captured(source,current_material())
        assert actual == references[asset], (asset,'original whole geometry/corner/material/frame/diagnostic boxes differ')
        query = root/'queries'/(asset+'.npz')
        region_query.save(query,[region_query.capture(obj)],owner=asset,stage='final')
        original_triangles = region_query.triangles([region_query.capture(obj)])
        assert (region_query.triangles(region_query.load(query,owner=asset,stage='final')) == original_triangles).all()
        plan_root = root/'plans'/asset
        value = plan(obj,plan_root,partition='spatial' if asset == 'SW_Island' else 'whole',collisions=(),options=dict(apply_unit_scale=True,apply_scale_options='FBX_SCALE_ALL',
            axis_forward='-Y',axis_up='Z',mesh_smooth_type='FACE',colors_type='SRGB'))
        observed = Counter(); emitted = dict(render=Counter(),collision=Counter())
        for row in value['pieces']:
            meta,piece = mesh_ir.decode((plan_root/row['payload']).read_bytes())
            assert piece['selection'] == actual['selection'] and meta['collisions'] == []
            assert 0 < row['triangles'] <= 32768
            observed.update(corners(piece))
            output = root/'exports'/row['name']
            export_region_piece.main(['--input',str(plan_root/row['payload']),'--output',str(output)])
            current = exported_corners(output/(row['name']+'.fbx'))
            for kind in emitted: emitted[kind].update(current[kind])
        assert observed == references[asset]['rows'], (asset,'source corner conservation')
        assert emitted == controls[asset], (asset,'actual exported FBX corner conservation')
        results[asset] = dict(triangles=value['source_triangles'],polygons=value['source_polygons'],
            pieces=len(value['pieces']),maximum_triangles=max(row['triangles'] for row in value['pieces']),exported_hulls=0)
        print('SOUTHWEST ATOMIC CONSERVATION',asset,results[asset],flush=True)
    assert hashes() == before, 'Southwest conservation inputs changed'
    (root/'result.json').write_text(json.dumps(dict(complete=True,legacy_revision='283329c07',assets=results,
        exact_original_source_conservation=True,actual_fbx_corner_conservation=True,final_query_conservation=True,
        native_receiving=False,inputs=before),indent=2)+'\n')
    print('SOUTHWEST ATOMIC CONSERVATION COMPLETE',flush=True)


if __name__ == '__main__': main()
