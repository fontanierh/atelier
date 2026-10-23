"""Narrow immutable-original kit proof: full source channels and serialized FBX.

Host must first freeze the original closure with a receipt. No Git or child
process is invoked in this native stage. This is not Unreal/runtime acceptance.
"""
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
GAME = HERE.parents[2]
WORLD = GAME / 'world'
sys.path[:0] = [str(HERE), str(WORLD), str(GAME / 'tools')]
import yori  # noqa: E402,F401
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier import mesh_ir  # noqa: E402
from atelier.blender.fbx import export_atomic_fbx  # noqa: E402
from mesh_pieces import capture, create_mesh  # noqa: E402
from region_mesh_parts import plan  # noqa: E402
import atomic_equivalence as eq  # noqa: E402
from commands import replay  # noqa: E402

OPTIONS = dict(apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL', axis_forward='-Y',
               axis_up='Z', mesh_smooth_type='EDGE', use_custom_props=False)


def verify_bindings(root, receipt):
    for relative, expected in receipt['files'].items():
        path = root / relative
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('Immutable Gondola closure changed: ' + relative)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frozen', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--sources', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--') + 1:])
    receipt = json.loads(args.receipt.read_text())
    if receipt['baseline'] != '283329c07ea04bee34587022a3d43827468c66d7':
        raise ValueError('Wrong immutable original Gondola authority')
    verify_bindings(args.frozen, receipt)
    frozen_kit = args.frozen / HERE.relative_to(GAME.parents[1])
    frozen_world = args.frozen / WORLD.relative_to(GAME.parents[1])
    # These original modules are loaded only from the host-frozen immutable closure.
    sys.path[:0] = [str(frozen_kit), str(frozen_world)]
    import params as P
    import solid
    from cabin import Cabin
    from tower import Tower
    from stations import STATIONS
    for module in (P, solid, sys.modules['cabin'], sys.modules['tower'], sys.modules['stations'], sys.modules['solid_mesh']):
        if not Path(module.__file__).is_relative_to(args.frozen.resolve()):
            raise ValueError('Original constructor escaped frozen authority: ' + module.__name__)
    p = dict(P.DEFAULTS); d = P.derived(p)
    c = Cabin(p,d); originals, _ = c.build()
    collisions = {'GD_Cabin_Collision': c.proxies()}
    for height in p['tower_heights']:
        t = Tower(p,height); m = t.build(); originals[m.name] = m
        collisions[m.name+'_Collision'] = t.proxies()
    for key in ('valley', 'rim', 'crater'):
        station = STATIONS[key](key,p,d); originals.update(station.make())
        collisions[f'GD_Station{station.NAME}_Collision'] = station.proxies + station.platform_proxies()
    expected = set(P.asset_names()) - {key for key in P.asset_names() if key.endswith('_Collision')}
    if set(originals) != expected: raise ValueError('Incomplete original kit source census')
    args.output.mkdir(parents=True, exist_ok=True)
    results = {}
    for index, (key, before) in enumerate(originals.items()):
        value = json.loads((args.sources / (key + '.json')).read_text())
        if value['asset'] != key: raise ValueError('Foreign source stream')
        after = replay(value, solid.Mesh)
        reports = [solid.closed(mesh) for mesh in (before, after)]
        for report in reports:
            if any(report[field] for field in ('open_edges', 'misoriented_edges', 'degenerate_faces')):
                raise ValueError('Original closure gate failed')
        for field in ('verts', 'faces', 'mats', 'parts', 'fgrain', 'origins'):
            if json.dumps(getattr(before,field)) != json.dumps(getattr(after,field)):
                raise ValueError(key + ': source differs in ' + field)
        bpy.ops.wm.read_factory_settings(use_empty=True)
        mats = solid.make_materials({})
        obj, slots = solid.to_object(before,mats)
        baseline = args.output / 'baseline' / (key + '.fbx')
        baseline.parent.mkdir(parents=True, exist_ok=True)
        solid.export_fbx([obj], baseline)
        bpy.data.objects.remove(obj, do_unlink=True)
        obj, _ = solid.to_object(after,mats)
        logical = args.output / 'plans' / key
        logical.mkdir(parents=True, exist_ok=True)
        manifest = plan(obj, logical, options=OPTIONS)
        bpy.data.objects.remove(obj, do_unlink=True)
        full = dict(render=Counter(), collision=Counter()); triangles = 0
        for row in manifest['pieces']:
            meta, piece = mesh_ir.decode((logical / row['payload']).read_bytes())
            piece['slots'] = [mats[name] for name in piece['slots']]
            mesh = create_mesh(row['name'], piece)
            child = bpy.data.objects.new(row['name'], mesh)
            bpy.context.collection.objects.link(child)
            bpy.ops.object.select_all(action='DESELECT'); child.select_set(True)
            bpy.context.view_layer.objects.active = child
            target = args.output / 'actual' / (row['name'] + '.fbx')
            target.parent.mkdir(parents=True, exist_ok=True)
            export_atomic_fbx(filepath=str(target), use_selection=True, object_types={'MESH'}, bake_anim=False, **OPTIONS)
            bpy.data.objects.remove(child, do_unlink=True)
            counters, count = eq.fbx_counter(target)
            for channel in full: full[channel].update(counters[channel])
            triangles += count
        base_counters, base_triangles = eq.fbx_counter(baseline)
        if base_triangles != triangles or full != base_counters:
            raise ValueError(key + ': full serialized FBX counters differ')
        results[key] = dict(source_exact=True, serialized_fbx_exact=True, triangles=triangles,
            pieces=[row['name'] for row in manifest['pieces']], slots=slots)
        print('GONDOLA EXACT KIT PROOF', index + 1, '/', len(originals), key, triangles, flush=True)
    for key, proxies in collisions.items():
        value = json.loads((args.sources / (key+'.json')).read_text())
        if value.get('asset') != key or json.dumps(value['proxies'],sort_keys=True) != json.dumps(proxies,sort_keys=True):
            raise ValueError(key+': original authored collision proxies differ')
        baseline = args.output / 'baseline' / (key+'.fbx')
        actual = args.output / 'actual' / (key+'.fbx')
        solid.export_collision(proxies,baseline,key)
        solid.export_collision(value['proxies'],actual,key)
        before,count = eq.fbx_counter(baseline); after,other = eq.fbx_counter(actual)
        if before != after or count != other: raise ValueError(key+': full collision FBX differs')
        results[key] = dict(source_proxies_exact=True,serialized_fbx_exact=True,convex_hulls=len(proxies),triangles=count,pieces=[key])
        print('GONDOLA EXACT COLLISION PROOF',key,len(proxies),flush=True)
    verify_bindings(args.frozen, receipt)
    atomic_json(args.output / 'proof.json' , dict(schema=1, baseline=receipt['baseline'],
        original_files=receipt['files'], scope='kit render/collision source/FBX only; no native Unreal/runtime acceptance', assets=results))
    print('GONDOLA EXACT KIT SOURCE FBX COMPLETE', len(results), flush=True)


if __name__ == '__main__': main()
