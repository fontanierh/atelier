"""Belmonte per-package native mesh bodies over certified current GLB exports."""
import ast
from copy import copy
import hashlib
import json
from pathlib import Path
import re

from atelier import encoded_glb
from atelier.export_manifest import validate as validate_export
from atelier.unreal_mesh_reuse import lods_match
from island_finish_v2 import _identity, _selected

ROOT = '/Game/Belmonte'
ORIGINAL = 'games/yorimichi/unreal/Scripts/import_belmonte.py'
CPU = {'SM_BM_BT_Terrain_0_0', 'SM_BM_BT_Terrain_4_4'}
PLAN = ((1., 1.), (.5, .35), (.25, .15))


def _slot(value):
    if isinstance(value, str):
        return value
    descriptor = value.get('derived_items') if isinstance(value, dict) else None
    members = descriptor.get('members') if isinstance(descriptor, dict) else None
    if not isinstance(members, list) or len(members) != 1 or not isinstance(members[0].get('slot'), str):
        raise ValueError('Belmonte requires exactly its resolved selected export Item')
    return members[0]['slot']


def _data(context, slot):
    slot = _slot(slot)
    root = Path(context.inputs[slot])
    if (context.packages.get(slot) not in ([], ()) or not root.is_absolute()
            or not root.is_relative_to(Path(context.job_dir)) or root.resolve() != root
            or root.is_symlink() or not root.is_dir()):
        raise ValueError('Belmonte data must be an independent staged directory')
    return root


def source_facts(context, args):
    piece = args['piece']; root = _data(context, args['source_export'])
    receipt = validate_export(root, key=piece)
    if receipt['primary'] != piece + '.glb' or {p.name for p in root.iterdir()} != {piece + '.glb', 'export.json'}:
        raise ValueError('Belmonte source export membership differs')
    data = (root / (piece + '.glb')).read_bytes(); meta = receipt['metadata']
    role = 'collision' if args['hull'] else 'render'
    facts = encoded_glb.geometry(data, role=role)
    if (meta.get('role') != role or meta.get('geometry_sha256') != receipt['sha256']
            or facts != {'triangles': receipt['triangles'], 'bounds': receipt['bounds'], 'slots': meta.get('slots')}):
        raise ValueError('Belmonte receipt differs from its current source geometry')
    if not args['hull'] and not (piece == args['parent'] or piece.startswith(args['parent'] + '_Piece')):
        raise ValueError('Belmonte selected render belongs to another logical parent')
    if args['hull']:
        if piece != args['parent'] + '_Collision' or meta.get('parent') != args['parent']:
            raise ValueError('Belmonte whole hull belongs to another source')
    else:
        payload = _data(context, args['payload'])
        if {p.name for p in payload.iterdir()} != {piece + '.mesh'}:
            raise ValueError('Belmonte requires its exact selected encoded packet')
        path = payload / (piece + '.mesh')
        identity, original = encoded_glb.read(path, key=piece)
        if (original != data or hashlib.sha256(path.read_bytes()).hexdigest() != meta.get('payload_sha256')
                or {k: v for k, v in identity['metadata'].items() if k != 'slots'} != {k: v for k, v in meta.items() if k not in ('role', 'slots', 'geometry_sha256', 'payload_sha256')}):
            raise ValueError('Belmonte selected packet differs from exported source')
        matches = [re.fullmatch(r'BM_([0-9]+)_.+', slot) for slot in facts['slots']]
        if not all(matches):
            raise ValueError('Belmonte source lost its numeric material slots')
        indices = [int(match.group(1)) for match in matches]
        if indices != identity['metadata'].get('slots'):
            raise ValueError('Belmonte source numeric slot mapping differs')
        entry = meta.get('entry', {})
        if (entry.get('name') != piece or entry.get('triangles') != facts['triangles']
                or entry.get('bounds_m') != facts['bounds'] or entry.get('sha256') != receipt['sha256']):
            raise ValueError('Belmonte current source entry differs')
    return facts, meta, data


def generate_terrain_lods(context, mesh, unreal):
    path = Path(context.job_dir) / ORIGINAL
    if path.is_symlink() or not path.is_file():
        raise ValueError('Original Belmonte LOD body is not staged keyed code')
    nodes = [n for n in ast.parse(path.read_bytes()).body if isinstance(n, ast.FunctionDef) and n.name == 'generate_terrain_lods']
    if len(nodes) != 1:
        raise ValueError('Original Belmonte LOD function changed')
    scope = {'unreal': unreal}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), ORIGINAL, 'exec'), scope)
    scope['generate_terrain_lods'](mesh)


def run(context):
    """@cc [owner:fontanierh,label:correctness] belmonte-current-native-mesh
    Finish MUST duplicate only its declared raw package at its single original
    destination. Current source GLB/packet, slot bindings, triangles, bounds,
    separate hull association, terrain LODs and exact CPU-access policy MUST
    validate before and after a real primary save. Hull distance fields MUST be
    zero; hulls bind Ground. No importer main, retirement or ambient scan may run.
    """
    import unreal
    p = context.params
    if 'op' not in p:
        return author(context, unreal)
    if p.get('op') == 'raw_import':
        from atelier.build_v2.unreal_ops import raw_import
        selected = _slot(p['source'])
        wrapper = copy(context); wrapper.params = dict(p, source=selected)
        return raw_import(wrapper, unreal)
    if (p.get('op') != 'finish' or p.get('kind') != 'static_mesh'
            or set(p) - {'op', 'kind', 'source', 'destination', 'package_sources', 'args', 'settings'}):
        raise ValueError('Unsupported Belmonte operation')
    args = p['args']; piece = args['piece']
    if (not re.fullmatch(r'SM_BM_[A-Za-z0-9_]+', piece) or type(args['hull']) is not bool
            or set(args) != {'piece', 'parent', 'source_export', 'hull', 'native_inputs', 'native_extra', 'bindings', 'collision', *([] if args['hull'] else ['payload'])}):
        raise ValueError('Unsupported Belmonte finish arguments')
    native = args['native_inputs']
    expected = {'raw', _slot(args['source_export']), *native}
    for token in args.get('native_extra', []):
        expected.update(row['slot'] for row in _derived(token))
    if not args['hull']:
        expected.add(args['payload'])
    if args['collision']:
        expected.add('collision')
    if set(context.inputs) != expected or set(context.packages) != expected:
        raise ValueError('Belmonte finish input membership differs')
    facts, meta, data = source_facts(context, args)
    source = _selected(context, 'raw'); destination = ROOT + '/Meshes/' + piece
    if (p['source'] != 'raw' or source != '/Game/_Raw/Belmonte/' + piece
            or p['destination'] != destination or list(context.outputs) != [destination]):
        raise ValueError('Belmonte finish must own exactly its original selected package')
    library = unreal.EditorAssetLibrary; raw = library.load_asset(source)
    if not isinstance(raw, unreal.StaticMesh):
        raise ValueError('Belmonte raw package is not a StaticMesh')
    _identity(raw, source)
    from glb_mesh_validation import options_match
    if not options_match(raw):
        raise ValueError('Belmonte raw import options differ from its original Interchange policy')
    materials = {}
    for slot, package in native.items():
        if _selected(context, slot) != package:
            raise ValueError('Belmonte native dependency differs')
        asset = library.load_asset(package)
        if asset is None:
            raise ValueError('Belmonte native dependency failed to load')
        _identity(asset, package); materials[package] = asset
    for token in args.get('native_extra', []):
        for row in _derived(token):
            package = _selected(context, row['slot'])
            if package != ROOT + '/Textures/' + row['piece'] or not isinstance(library.load_asset(package), unreal.Texture):
                raise ValueError('Belmonte material transitive texture dependency differs')
    wanted = [ROOT + '/Materials/MI_BM_Ground'] if args['hull'] else []
    if not args['hull']:
        indices = []
        for slot in facts['slots']:
            match = re.fullmatch(r'BM_([0-9]+)_.+', slot)
            if not match:
                raise ValueError('Belmonte source lost its numeric material slot')
            indices.append(int(match.group(1)))
        wanted = [args['bindings'][str(i)] for i in indices]
    if any(not isinstance(materials.get(path), unreal.MaterialInterface) for path in wanted):
        raise ValueError('Belmonte material binding is not a supplied MaterialInterface')
    collision = None
    if not args['hull'] and meta['entry'].get('collision'):
        if not args['collision'] or _selected(context, 'collision') != args['collision']:
            raise ValueError('Missing declared whole Belmonte collision package')
        if args['collision'] != ROOT + '/Meshes/' + Path(meta['entry']['collision']['path']).stem:
            raise ValueError('Belmonte source names a different whole hull')
        collision = library.load_asset(args['collision'])
        if not isinstance(collision, unreal.StaticMesh):
            raise ValueError('Belmonte collision package is not a StaticMesh')
        _identity(collision, args['collision'])
    unreal.load_module('StaticMeshEditor')
    editor = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    if editor is None or library.does_asset_exist(destination):
        raise ValueError('Belmonte finish requires StaticMeshEditor and a fresh destination')
    mesh = library.duplicate_asset(source, destination)
    if not isinstance(mesh, unreal.StaticMesh) or mesh is raw:
        raise ValueError('Belmonte raw duplicate failed')
    _identity(mesh, destination)
    slots = mesh.get_editor_property('static_materials')
    if not args['hull'] and len(slots) != len(wanted):
        raise ValueError('Belmonte native material slot count differs')
    if not args['hull'] and [str(s.get_editor_property('imported_material_slot_name')) for s in slots] != facts['slots']:
        raise ValueError('Belmonte native material slot order differs')
    for i in range(len(slots)):
        mesh.set_material(i, materials[wanted[0] if args['hull'] else wanted[i]])
    if args['hull']:
        settings = editor.get_lod_build_settings(mesh, 0)
        settings.set_editor_property('distance_field_resolution_scale', 0.)
        editor.set_lod_build_settings(mesh, 0, settings)
    else:
        mesh.set_editor_property('complex_collision_mesh', collision)
        if piece.startswith('SM_BM_BT_Terrain_'):
            mesh.set_editor_property('allow_cpu_access', piece in CPU)
            if facts['triangles'] > 12000:
                generate_terrain_lods(context, mesh, unreal)
        body = mesh.get_editor_property('body_setup')
        if body is None:
            raise ValueError('Belmonte mesh has no BodySetup')
        body.set_editor_property('collision_trace_flag', unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
        body.set_editor_property('double_sided_geometry', True)
    low, high = facts['bounds']
    bounds = [low[0]*100, -high[1]*100, low[2]*100, high[0]*100, -low[1]*100, high[2]*100]
    def check():
        box = mesh.get_bounding_box()
        actual = [box.min.x, box.min.y, box.min.z, box.max.x, box.max.y, box.max.z]
        count = mesh.get_num_triangles(0)
        if (not facts['triangles'] * (.98 if args['hull'] else 1.) <= count <= facts['triangles']
                or max(abs(a-b) for a, b in zip(actual, bounds)) >= 1.
                or any(mesh.get_material(i) != materials[wanted[0] if args['hull'] else wanted[i]] for i in range(len(slots)))):
            raise ValueError('Belmonte current geometry, bounds or material validation failed')
        if args['hull']:
            if editor.get_lod_build_settings(mesh, 0).get_editor_property('distance_field_resolution_scale') != 0.:
                raise ValueError('Belmonte hull distance fields were not disabled')
        else:
            if (mesh.get_editor_property('complex_collision_mesh') is not collision
                    or body.get_editor_property('collision_trace_flag') != unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE
                    or not body.get_editor_property('double_sided_geometry')):
                raise ValueError('Belmonte collision policy differs')
            if piece.startswith('SM_BM_BT_Terrain_'):
                if mesh.get_editor_property('allow_cpu_access') != (piece in CPU):
                    raise ValueError('Belmonte terrain CPU-access policy differs')
                if facts['triangles'] > 12000 and not lods_match(mesh, PLAN):
                    raise ValueError('Belmonte terrain LOD validation failed')
    check()
    if not library.save_loaded_asset(mesh, only_if_is_dirty=True):
        raise ValueError('Belmonte primary save failed')
    primary = Path(context.content_dir) / (destination.removeprefix('/Game/') + '.uasset')
    if not primary.is_file() or any(p.is_symlink() for p in (primary, *primary.parents)):
        raise ValueError('Belmonte primary save did not publish a regular package')
    check()
    report_path = 'data/reports/' + piece + '.json'
    if set(context.data_outputs) != {report_path}:
        raise ValueError('Belmonte current native report output differs')
    box = mesh.get_bounding_box()
    actual = [box.min.x, box.min.y, box.min.z, box.max.x, box.max.y, box.max.z]
    report = {'name': piece, 'hull': args['hull'], 'triangles': mesh.get_num_triangles(0),
              'bounds_cm': actual, 'bounds_error_cm': max(abs(a-b) for a,b in zip(actual,bounds))}
    target = Path(context.job_dir) / 'output' / report_path
    target.parent.mkdir(parents=True, exist_ok=True); target.write_text(json.dumps(report, sort_keys=True) + '\n')
    return mesh


def _derived(value):
    if not isinstance(value, dict) or set(value) != {'derived_items'} or set(value['derived_items']) != {'root', 'members'}:
        raise ValueError('Belmonte native membership is unresolved')
    rows = value['derived_items']['members']
    if not isinstance(rows, list) or not rows or len({r['slot'] for r in rows}) != len(rows):
        raise ValueError('Belmonte native membership is empty or aliased')
    return rows


def author(context, unreal):
    """One package, keyed original graph bodies and exact selected generated spec/pixels."""
    import importlib.util
    import sys
    sys.path.insert(0, str(Path(context.job_dir) / 'games/yorimichi/unreal/Scripts'))
    args = context.params['args']; action = args['action']
    package = ('/Game/Racing/M_RacingTv' if action == 'tv' else ROOT + '/Materials/' +
        {'parent': 'M_Belmonte', 'join_parent': 'M_BelmonteJoin', 'instance': args.get('name', '')}.get(action, ''))
    lib = unreal.EditorAssetLibrary
    if action not in ('parent', 'join_parent', 'instance', 'tv') or list(context.outputs) != [package] or lib.does_asset_exist(package):
        raise ValueError('Belmonte author requires one fresh original package')
    def support(name):
        path = Path(context.job_dir) / ('games/yorimichi/unreal/Scripts/' + name + '.py')
        if path.resolve() != path or not path.is_file(): raise ValueError('Missing keyed original support')
        spec = importlib.util.spec_from_file_location(name, path); module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module
    if action == 'tv':
        if context.inputs: raise ValueError('Racing TV author has no project native inputs')
        path = Path(context.job_dir) / 'games/yorimichi/unreal/Scripts/racing_tv_material.py'
        if path.resolve() != path or not path.is_file(): raise ValueError('Missing keyed original TV body')
        # This script owns exactly one package; all graph statements are the original body.
        exec(compile(path.read_bytes(), str(path), 'exec'), {'__name__': 'belmonte_racing_tv'})
        asset = lib.load_asset(package)
    else:
        path = Path(context.job_dir) / ORIGINAL
        if path.resolve() != path or not path.is_file(): raise ValueError('Missing keyed Belmonte material body')
        wanted = 'parent' if action == 'parent' else 'join_parent' if action == 'join_parent' else 'surfaces'
        functions = [n for n in ast.parse(path.read_bytes()).body if isinstance(n, ast.FunctionDef) and n.name == wanted]
        if len(functions) != 1: raise ValueError('Original Belmonte material declaration changed')
        scope = {'unreal': unreal, 'ROOT': ROOT, 'E': lib, 'AT': unreal.AssetToolsHelpers.get_asset_tools(),
                 'MEL': unreal.MaterialEditingLibrary, 'atmosphere': support('atmosphere'), 'ground_grain': support('ground_grain')}
        if action in ('parent', 'join_parent'):
            exec(compile(ast.Module(body=functions, type_ignores=[]), ORIGINAL, 'exec'), scope)
            if action == 'parent':
                if context.inputs: raise ValueError('Belmonte parent may only read engine defaults')
                asset = scope['parent']()
            else:
                rows = _derived(args['texture'])
                if len(rows) != 1 or set(context.inputs) != {rows[0]['slot']}:
                    raise ValueError('Belmonte join parent requires exactly its current ground texture')
                texture = lib.load_asset(_selected(context, rows[0]['slot']))
                if not isinstance(texture, unreal.Texture): raise ValueError('Belmonte ground dependency is not a Texture')
                asset = scope['join_parent'](texture)
        else:
            spec_slot = _slot(args['spec']); root = _data(context, spec_slot)
            filename = args['name'] + '.json'
            if {p.name for p in root.iterdir()} != {filename}: raise ValueError('Belmonte material selected spec differs')
            value = json.loads((root / filename).read_bytes()); spec = value['spec']
            if value['source'] != args['source_name'] or spec['name'] != args['name']:
                raise ValueError('Belmonte material selected identity differs')
            parent = lib.load_asset(_selected(context, 'parent'))
            if not isinstance(parent, unreal.MaterialInterface) or _selected(context, 'parent') != args['parent_package']:
                raise ValueError('Belmonte material parent differs')
            expected = {'parent', spec_slot}; images = {}
            for token in args.get('parent_dependencies', []):
                for row in _derived(token):
                    expected.add(row['slot'])
                    package_path = _selected(context, row['slot'])
                    if package_path != ROOT + '/Textures/' + row['piece'] or not isinstance(lib.load_asset(package_path), unreal.Texture):
                        raise ValueError('Belmonte instance parent texture dependency differs')
            if args['texture'] is not None:
                texture_slot = _slot(args['texture']); expected.add(texture_slot)
                texture = lib.load_asset(_selected(context, texture_slot))
                if not isinstance(texture, unreal.Texture) or _selected(context, texture_slot) != ROOT + '/Textures/' + Path(spec['texture']).stem:
                    raise ValueError('Belmonte material current texture differs')
                images[spec['texture']] = texture
            elif spec['texture']:
                raise ValueError('Belmonte material omitted its texture dependency')
            if set(context.inputs) != expected: raise ValueError('Belmonte material input membership differs')
            # Execute the unchanged original loop for exactly this one instance.
            loops = [n for n in functions[0].body if isinstance(n, ast.For)]
            if len(loops) != 1: raise ValueError('Original Belmonte instance loop changed')
            scope.update(report={'materials': {value['source']: spec}}, master=parent, join=parent, images=images)
            exec(compile(ast.Module(body=loops, type_ignores=[]), ORIGINAL, 'exec'), scope)
            asset = lib.load_asset(package)
    if asset is None: raise ValueError('Belmonte author did not produce its native package')
    _identity(asset, package)
    if not lib.save_loaded_asset(asset, only_if_is_dirty=False): raise ValueError('Belmonte author primary save failed')
    primary = Path(context.content_dir) / (package.removeprefix('/Game/') + '.uasset')
    if primary.resolve() != primary or not primary.is_file(): raise ValueError('Belmonte author primary package is missing')
    return asset
