"""Compare immutable terminal constructors to selected constructors using frozen queries.

This source-only diagnostic executes exact original declarations with explicit query
injection. It does not execute the original exporter or waive production site validation.
All Git/source/donor validation belongs to the outer host, never this Blender process.
"""
import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import shutil
from types import SimpleNamespace

GAME = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(GAME / 'world'), str(Path(__file__).resolve().parent)]
import yori  # noqa: E402,F401
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from ferry_ship_source_control import checked, signature  # noqa: E402
from regions.ferry.terminal_sources import projections, final_world  # noqa: E402
from regions.ferry.terminal_constructor import construct, kit as selected_kit  # noqa: E402
from region_mesh_parts import capture_collision, plan as mesh_plan  # noqa: E402
import region_query  # noqa: E402


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def original_kit(path, current, site, worlds):
    """Exact original helpers/constants, with authority/query globals supplied explicitly."""
    namespace = dict(__file__=str(path), __name__='immutable_terminal_helpers',
        F=current.F, FS=SimpleNamespace(**current.FS.__dict__), WC=current.WC,
        HERE=path.parent, OUT=path.parent, SITE=site,
        SILL=site['ship']['sill_z'], GATE_W=site['ship']['gate_width'])
    namespace['FS'].load_world = lambda name: worlds[name]
    supplied = set(namespace)
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.Import) and any(alias.name == 'build' for alias in node.names): continue
        elif isinstance(node, ast.Assign):
            names = {name.id for target in node.targets for name in ast.walk(target) if isinstance(name, ast.Name)}
            if names & (supplied | {'_spec'}): continue
        elif isinstance(node, ast.FunctionDef): pass
        elif (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
              and ast.unparse(node.value.func) == 'F.MATERIALS.update'): pass
        else: continue
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), namespace)
    return SimpleNamespace(**namespace)


def mesh_records(kit, meshes, anchor):
    materials = kit.F.make_materials()
    records = {}
    for key, mesh in meshes.items():
        mesh.verts[:] = [(x - anchor[0], y - anchor[1], z - anchor[2]) for x, y, z in mesh.verts]
        kit.F.check(mesh)
        obj, _ = kit.F.to_object(mesh, materials)
        records[key] = signature(obj)
    return records


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--authority', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--audit-fixture', action='store_true')
    parser.add_argument('--fbx-fixture', action='store_true')
    args = parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--') + 1:])
    authority = json.loads(args.authority.read_text())
    paths = {key: checked(row) for key, row in authority['files'].items()}
    current = load('current_ferry_terminal_helpers', GAME / 'assets/vehicles/ferry/terminals/build.py')
    site = json.loads(paths['site'].read_text())
    worlds = {key: current.FS.load_world(key, out=paths['world_' + key].parent) for key in ('hidamari', 'brinecove')}
    baseline = original_kit(paths['original_kit'], current, site, worlds)
    current.SITE = site; current.SILL = site['ship']['sill_z']; current.GATE_W = site['ship']['gate_width']
    current.FS.load_world = lambda name: worlds[name]
    selected = SimpleNamespace(**current.__dict__)
    packets = projections(site, worlds)
    final = dict(worlds, hidamari=final_world(worlds['hidamari'], region_query.load(paths['harbor_query'], owner='HD_Harbor', stage='final')))
    if packets != projections(site, final): raise ValueError('Final Harbor changes consumed original terminal queries')
    # Native planners receive serialized explicit products, including exact scalar query values.
    packets = json.loads(json.dumps(packets))
    fixture = args.output.with_suffix('')
    packet_root = fixture / 'sources'
    for key, value in packets.items(): atomic_json(packet_root / (key + '.json'), value)
    planner = load('terminal_production_planner_control', GAME / 'world/regions/ferry/plan_terminal.py')
    results = {}
    for owner in ('hidamari', 'brinecove'):
        original = load('immutable_terminal_' + owner, paths['original_' + owner])
        actual = load('selected_terminal_' + owner, GAME / 'world/regions' / owner / 'ferry_terminal.py')
        bpy.ops.wm.read_factory_settings(use_empty=True)
        baseline.COL.clear(); baseline.BROW_COL.clear()
        original_meshes, original_walk = original.assemble(baseline)
        before = mesh_records(baseline, original_meshes, original_walk['anchor'])
        original_hulls = json.dumps(dict(fixed=baseline.COL, moving=baseline.BROW_COL))
        bpy.ops.wm.read_factory_settings(use_empty=True)
        after, metadata, fixed, moving = {}, {}, [], []
        for key in actual.CONSTRUCTORS:
            bpy.ops.wm.read_factory_settings(use_empty=True)
            context, mesh, data = construct(packets[key], packets[key]['primitives'])
            metadata.update(data); fixed.extend(context.COL); moving.extend(context.BROW_COL)
            anchor = packets[key]['anchor']
            after.update(mesh_records(context, {key: mesh}, anchor))
            obj = bpy.data.objects.get(key)
            hulls = context.collision_objects(key, anchor, context.BROW_COL) if key.endswith('_Brow') else []
            destination = args.output.with_suffix('') / 'plans' / key
            mesh_plan(obj, destination, collisions=[capture_collision(hull) for hull in hulls], options=dict(
                apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL', axis_forward='-Y',
                axis_up='Z', mesh_smooth_type='EDGE', use_custom_props=False))
            planner.main(['--asset', key, '--source', str(packet_root / (key + '.json')),
                '--queries', str(fixture / 'queries' / (key + '.json')),
                '--output', str(destination)])
        context, _ = selected_kit(packets['primitives'], packets[owner + '_collision'])
        namespace = dict(math=__import__('math'))
        exec(packets[owner + '_collision']['program'], namespace)
        namespace['fixed_collision'](context, packets[owner + '_collision']['parameters'])
        fixed.extend(context.COL)
        context, _ = selected_kit(packets['primitives'], packets[owner + '_walk'])
        exec(packets[owner + '_walk']['program'], namespace)
        walk = namespace['walk_plan'](context, packets[owner + '_walk']['parameters'], metadata['stair'], metadata['brow'])
        walk_equal = json.dumps(walk, sort_keys=True) == json.dumps(original_walk, sort_keys=True)
        if before != after or not walk_equal or original_hulls != json.dumps(dict(fixed=fixed, moving=moving)):
            atomic_json(args.output, dict(complete=False, owner=owner, baseline=before, selected=after,
                walk_equal=walk_equal, hulls_equal=original_hulls == json.dumps(dict(fixed=fixed, moving=moving))))
            raise ValueError('Terminal exact constructor/query/walk/collision equality failed: ' + owner)
        results[owner] = dict(meshes=after, fixed_hulls=len(fixed), moving_hulls=len(moving))
        print('FERRY TERMINAL SOURCE EXACT', owner, len(after), flush=True)
    fixture_result = None
    fbx_results = []
    if args.audit_fixture:
        from regions.ferry.ship_sources import project as ship_project
        from regions.ferry.plan_ship import construct as ship_construct
        ship_packets = ship_project((GAME / 'assets/vehicles/ferry/build.py').read_text())
        from regions.ferry.ship_sources import BUILDERS
        for key in BUILDERS:
            bpy.ops.wm.read_factory_settings(use_empty=True)
            _, row = ship_construct(key, ship_packets[key])
            row['triangles'] = sum(len(face)-2 for face in row['faces'])
            atomic_json(fixture / 'ship-query-data' / (key + '.json'), row)
        terminal_root = fixture / 'terminals'; terminal_root.mkdir()
        for owner in ('hidamari', 'brinecove'):
            shutil.copyfile(paths['world_' + owner], terminal_root / ('world_' + owner + '.npz'))
        auditor = load('terminal_original_audit_control', GAME / 'world/regions/ferry/terminal_audit.py')
        original_load = auditor.load
        def fixture_load(name, path):
            module = original_load(name, path)
            if name == 'ferry_terminal_current_audit':
                def explicit_fixture_site():
                    module.SITE = site; module.SILL = site['ship']['sill_z']; module.GATE_W = site['ship']['gate_width']
                    return site
                module.configure_site = explicit_fixture_site
            return module
        auditor.load = fixture_load
        bpy.ops.wm.read_factory_settings(use_empty=True)
        manifest, walks, collisions = auditor.audit(terminal_root, packet_root, fixture / 'queries', paths['harbor_query'])
        atomic_json(fixture / 'audit.json', manifest); atomic_json(fixture / 'walk.json', walks)
        for owner, row in collisions.items(): atomic_json(fixture / (owner + '-collision-data.json'), row)
        fixture_result = dict(complete=True, production_site_validation=False, failures=manifest['failures'])
    if args.fbx_fixture:
        if not args.audit_fixture: raise ValueError('FBX control requires the completed explicit audit fixture')
        from atomic_equivalence import fbx_counter
        exporter = load('terminal_atomic_export_control', GAME / 'world/export_region_piece.py')
        collision_exporter = load('terminal_atomic_collision_control', GAME / 'world/regions/ferry/export_terminal_collision.py')
        for owner in ('hidamari', 'brinecove'):
            bpy.ops.wm.read_factory_settings(use_empty=True)
            baseline.COL.clear(); baseline.BROW_COL.clear()
            original = load('immutable_export_terminal_' + owner, paths['original_' + owner])
            meshes, walk = original.assemble(baseline)
            destination = fixture / 'original-fbx' / owner
            (destination / 'assets').mkdir(parents=True)
            baseline.export.__globals__['OUT'] = destination
            baseline.export(meshes, walk['anchor'], baseline.F.make_materials(), [])
            key = 'FT_' + ('HD' if owner == 'hidamari' else 'BC')
            baseline.export_collision(key, walk['anchor'])
            for name in meshes:
                plan_root = fixture / 'plans' / name
                value = json.loads((plan_root / 'plan.json').read_text())
                if len(value['pieces']) != 1: raise ValueError('Control requires the current original small terminal mesh')
                export_root = fixture / 'atomic-fbx' / name
                exporter.main(['--input', str(plan_root / value['pieces'][0]['payload']), '--output', str(export_root), '--format', '.fbx'])
            collision_exporter.main(['--input', str(fixture / (owner + '-collision-data.json')),
                '--primitives', str(packet_root / 'primitives.json'), '--output', str(fixture / 'atomic-fbx' / (key + '_Collision'))])
            for name in [*meshes, key + '_Collision']:
                original_path = destination / 'assets' / (name + '.fbx')
                actual_path = fixture / 'atomic-fbx' / name / (name + '.fbx')
                original_values, original_triangles = fbx_counter(original_path)
                actual_values, actual_triangles = fbx_counter(actual_path)
                if original_triangles != actual_triangles or original_values != actual_values:
                    raise ValueError('Actual immutable serialized FBX equality failed: ' + name)
                fbx_results.append(dict(asset=name, triangles=actual_triangles,
                    baseline=dict(path=str(original_path.absolute()), sha256=hashlib.sha256(original_path.read_bytes()).hexdigest()),
                    actual=dict(path=str(actual_path.absolute()), sha256=hashlib.sha256(actual_path.read_bytes()).hexdigest())))
                print('FERRY TERMINAL FBX EXACT', name, actual_triangles, flush=True)
    for row in authority['files'].values(): checked(row)
    atomic_json(args.output, dict(schema=1, complete=True, coverage='source_mesh_and_queries_only', authority=authority,
                                 terminals=results, audit_fixture=fixture_result, fbx=fbx_results))
    print('FERRY TERMINAL SOURCE CONTROL COMPLETE', flush=True)


if __name__ == '__main__': main()
