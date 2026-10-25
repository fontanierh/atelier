"""One-package CraterPark author/finish bodies; original graph functions, explicit native inputs."""
import ast
from pathlib import Path
from types import SimpleNamespace

from megapark_v2 import _data, _derived, _fresh, _load, _owned, _path, _selected, _ue, source_facts

ROOT = '/Game/CraterPark'
ORIGINAL = 'games/yorimichi/unreal/Scripts/import_craterpark.py'
KINDS = ('Textured', 'Lacquer', 'World', 'Flat', 'Steel')
VERIFIER = 'games/yorimichi/world/regions/megapark/verify_import.py'
CONSTANTS = ('ROUGHNESS', 'STEEL_ROUGHNESS', 'STEEL', 'LACQUER_ROUGHNESS', 'OCCLUSION', 'CAVITY', 'SNOWY', 'TINTS')


def original(context, unreal):
    path = Path(context.job_dir) / ORIGINAL
    if path.is_symlink() or not path.is_file():
        raise ValueError('CraterPark original body is not staged keyed code')
    nodes = [node for node in ast.parse(path.read_bytes()).body
             if (isinstance(node, ast.FunctionDef) and node.name == 'parent')
             or (isinstance(node, ast.Assign) and len(node.targets) == 1
                 and isinstance(node.targets[0], ast.Name) and node.targets[0].id in CONSTANTS)]
    found = {node.name if isinstance(node, ast.FunctionDef) else node.targets[0].id for node in nodes}
    if found != {'parent', *CONSTANTS}:
        raise ValueError('Original CraterPark material body changed')
    scope = {'unreal': unreal, 'ROOT': ROOT, 'E': unreal.EditorAssetLibrary,
             'MEL': unreal.MaterialEditingLibrary, 'AT': unreal.AssetToolsHelpers.get_asset_tools()}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), ORIGINAL, 'exec'), scope)
    return scope


def material_policy(spec, restyle):
    painted = restyle['textures'].get(spec['texture']) if spec['texture'] else None
    aligned = restyle.get('world_aligned', {}).get(spec['id'])
    kind = 'Textured' if painted else 'World' if aligned else 'Flat'
    kind = 'Lacquer' if spec.get('finish') == 'lacquer' and painted else 'Steel' if spec.get('finish') == 'metal' else kind
    return kind, painted or aligned, aligned


def parent(context, unreal, args):
    kind = args['kind']
    if kind not in KINDS:
        raise ValueError('Unknown original CraterPark parent')
    package = ROOT + '/Materials/M_CP_' + kind
    _owned(context, package); _fresh(unreal, package)
    asset = original(context, unreal)['parent'](kind)
    if not isinstance(asset, unreal.Material) or _path(asset) != package:
        raise ValueError('CraterPark parent authored outside its package')
    if not unreal.EditorAssetLibrary.save_loaded_asset(asset):
        raise ValueError('CraterPark parent save failed')
    return asset


def instance(context, unreal, args):
    from craterpark_members_v2 import read_json
    scope = original(context, unreal)
    spec = args['spec']
    package = ROOT + '/Materials/MI_CP_' + spec['id']
    _owned(context, package); _fresh(unreal, package)
    if args.get('coping'):
        kind, entry, aligned = 'Steel', None, None
        colour = scope['STEEL']
    else:
        catalogue = read_json(_data(context, 'catalogue', 'materials.json'))
        if [row for row in catalogue if row['id'] == spec['id']] != [spec]:
            raise ValueError('Declared CraterPark material differs from committed source')
        restyle = _data(context, 'restyle', directory=True)
        kind, entry, aligned = material_policy(spec, read_json(restyle / 'textures.json'))
        colour = scope['TINTS'].get(spec['id'], (1., 1., 1.)) if entry else spec['baseColor']
    base = _load(unreal, context, args['parents'][kind], unreal.Material)
    if _path(base) != ROOT + '/Materials/M_CP_' + kind:
        raise ValueError('CraterPark material parent differs')
    mi = unreal.AssetToolsHelpers.get_asset_tools().create_asset(package.rsplit('/', 1)[1], ROOT + '/Materials',
        unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    if not isinstance(mi, unreal.MaterialInstanceConstant) or _path(mi) != package:
        raise ValueError('CraterPark instance creation failed')
    mel = unreal.MaterialEditingLibrary
    mel.set_material_instance_parent(mi, base)
    if entry:
        import hashlib
        from craterpark_members_v2 import _file
        path = _file(restyle, entry['png'])
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
            raise ValueError('CraterPark material restyle pixels changed')
        chosen = [row for row in _derived(args['textures']) if row['piece'] == path.stem]
        if len(chosen) != 1:
            raise ValueError('Missing actual selected CraterPark texture owner')
        texture = _load(unreal, context, chosen[0]['slot'], unreal.Texture)
        if _path(texture) != ROOT + '/Textures/T_CP_' + path.stem:
            raise ValueError('CraterPark texture package differs')
        mel.set_material_instance_texture_parameter_value(mi, 'Base', texture)
    if aligned:
        mel.set_material_instance_scalar_parameter_value(mi, 'Metres', float(aligned['metres']))
    tint = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in colour]
    mel.set_material_instance_vector_parameter_value(mi, 'Tint', unreal.LinearColor(*tint, 1.))
    mel.set_material_instance_scalar_parameter_value(mi, 'Snow', float(spec['id'] in scope['SNOWY']))
    if not args.get('coping'):
        overrides = mi.get_editor_property('base_property_overrides')
        overrides.set_editor_property('override_two_sided', True)
        overrides.set_editor_property('two_sided', spec['doubleSided'])
        mi.set_editor_property('base_property_overrides', overrides)
    mel.update_material_instance(mi)
    if not unreal.EditorAssetLibrary.save_loaded_asset(mi):
        raise ValueError('CraterPark material save failed')
    return mi


def mesh(context, unreal, args):
    """@cc [owner:fontanierh,label:correctness] craterpark-selected-current-native-finish
    Duplicate only the declared raw mesh. Require exact selected-source triangles,
    material slots, native axis/origin bounds, one LOD, original full precision UVs,
    no degeneracy removal, no distance field, CPU access only for collision, zero
    simple hulls and actual cooked complex LOD0 validation before and after save.
    Native triangle audits MUST be produced from the current mesh, never receipts.
    """
    from atelier import mesh_ir
    from atelier.export_manifest import validate
    package = context.params['destination']; piece = args['piece']
    source = _selected(context, 'raw')
    collision = args['collision']
    if (type(collision) is not bool or package != ROOT + '/Meshes/' + piece
            or source != '/Game/_Raw/CraterPark/Meshes/' + piece
            or not piece.startswith('UC_CP_' if collision else 'SM_CP_') or piece == 'SM_CP_ImportSeed'):
        raise ValueError('CraterPark finish identity differs from its selected source')
    _owned(context, package); _fresh(unreal, package)
    info = _data(context, 'metadata', directory=True) / (piece + '.json')
    wrapper = SimpleNamespace(inputs={**context.inputs, 'metadata': info}, packages=context.packages, job_dir=context.job_dir)
    entry = source_facts(wrapper, {**args, 'parent': piece}, piece)
    receipt = validate(_data(context, 'source_export', directory=True), key=piece)
    meta, decoded = mesh_ir.decode((_data(context, 'payload', directory=True) / (piece + '.npz')).read_bytes())
    if [channel[0] for channel in meta['uvs']] != receipt['metadata']['uv_channels']:
        raise ValueError('CraterPark source UV roster differs')
    materials = {name: _load(unreal, context, slot, unreal.MaterialInterface) for name, slot in args['materials'].items()}
    if any(_path(value) != ROOT + '/Materials/MI_CP_' + name for name, value in materials.items()):
        raise ValueError('CraterPark original material package differs')
    lib = unreal.EditorAssetLibrary
    raw = _load(unreal, context, 'raw', unreal.StaticMesh)
    asset = lib.duplicate_asset(source, package)
    if not isinstance(asset, unreal.StaticMesh) or asset is raw or _path(asset) != package:
        raise ValueError('CraterPark raw duplicate failed')
    unreal.load_module('StaticMeshEditor')
    editor = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    if asset.get_num_lods() != 1:
        raise ValueError('CraterPark source must retain one LOD')
    settings = editor.get_lod_build_settings(asset, 0)
    for key, value in {'use_full_precision_u_vs': True, 'remove_degenerates': False, 'distance_field_resolution_scale': 0.}.items():
        settings.set_editor_property(key, value)
    editor.set_lod_build_settings(asset, 0, settings)
    asset.set_editor_property('allow_cpu_access', collision)
    body = asset.get_editor_property('body_setup')
    body.set_editor_property('collision_trace_flag', unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    body.set_editor_property('double_sided_geometry', collision and not entry['one_sided'])
    slots = list(asset.static_materials)
    found = [str(slot.get_editor_property('imported_material_slot_name')) for slot in slots]
    if len(set(found)) != len(found) or set(found) != set(entry['materials']):
        raise ValueError('CraterPark native slots differ from source')
    if not collision:
        for slot, name in zip(slots, found):
            if name not in materials:
                raise ValueError('Missing declared original CraterPark material')
            slot.set_editor_property('material_interface', materials[name])
        asset.set_editor_property('static_materials', slots)
    validator = getattr(getattr(unreal, 'AtelierBuildWorkerLibrary', None), 'validate_mesh_collision', None)
    if not callable(validator):
        raise ValueError('Required current native collision validator is unavailable')
    def check():
        box = asset.get_bounding_box()
        low = [a - b for a, b in zip(_ue(entry['minimum']), _ue(entry['origin']))]
        high = [a - b for a, b in zip(_ue(entry['maximum']), _ue(entry['origin']))]
        error = max(sum((getattr(point, axis) - value) ** 2 for axis, value in zip('xyz', values)) ** .5
                    for point, values in ((box.min, low), (box.max, high)))
        current = editor.get_lod_build_settings(asset, 0)
        if (asset.get_num_lods() != 1 or asset.get_num_triangles(0) != entry['triangles'] or error >= .05
                or editor.get_num_uv_channels(asset, 0) != len(meta['uvs'])
                or not current.get_editor_property('use_full_precision_u_vs')
                or current.get_editor_property('remove_degenerates')
                or current.get_editor_property('distance_field_resolution_scale') != 0.
                or asset.get_editor_property('allow_cpu_access') != collision
                or editor.get_simple_collision_count(asset) or editor.get_convex_collision_count(asset)
                or body.get_editor_property('double_sided_geometry') != (collision and not entry['one_sided'])
                or [str(slot.get_editor_property('imported_material_slot_name')) for slot in asset.static_materials] != found
                or (not collision and any(asset.get_material(i) != materials[name] for i, name in enumerate(found)))
                or not validator(asset, entry['triangles'], False)):
            raise ValueError('CraterPark current native geometry/material/collision invariant failed')
        return error
    error = check()
    if not lib.save_loaded_asset(asset):
        raise ValueError('CraterPark mesh save failed')
    check()
    binary, report = 'data/geometry/' + piece + '.bin', 'data/reports/' + piece + '.json'
    if set(context.data_outputs) != {binary, report}:
        raise ValueError('CraterPark current audit outputs differ')
    observer = getattr(getattr(unreal, 'MeshImportAudit', None), 'dump_mesh_triangles', None)
    if not callable(observer) or not observer(asset, unreal.Vector(*_ue(entry['origin'])), str(Path(context.job_dir) / 'output' / binary)):
        raise ValueError('Required produced native CraterPark triangle observer failed')
    from collections import defaultdict
    from itertools import product
    import numpy as np
    path = Path(context.job_dir) / VERIFIER
    if path.is_symlink() or not path.is_file():
        raise ValueError('Original native triangle verifier is not staged keyed code')
    nodes = [node for node in ast.parse(path.read_bytes()).body
             if (isinstance(node, ast.FunctionDef) and node.name == 'compare')
             or (isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'TOLERANCE' for t in node.targets))]
    if len(nodes) != 2 or any(len(face) != 3 for face in decoded['faces']):
        raise ValueError('CraterPark source/verifier differs from its triangle-only route')
    vertices = decoded['positions'][:, [0, 2, 1]].astype('f8'); vertices[:, 2] *= -1
    vertices += np.asarray(entry['origin'])
    # Bind the original comparator's fixed file lookup to this exact declared native dump.
    class SelectedDump:
        def __truediv__(self, name):
            if name != 'imported-geometry':
                raise ValueError('Original comparator requested an unknown path')
            return Path(context.job_dir) / 'output/data/geometry'
    scope = {'np': np, 'defaultdict': defaultdict, 'product': product, 'OUT': SelectedDump()}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), VERIFIER, 'exec'), scope)
    scope['compare']({'name': piece}, vertices[np.asarray(decoded['faces'])])
    return {report: {'name': piece, 'triangles': entry['triangles'], 'bounds_error_cm': error,
                     'collision': collision, 'uv_channels': editor.get_num_uv_channels(asset, 0)}}


def run(context):
    import unreal
    args = context.params.get('args', {})
    action = args.get('action')
    if action == 'mesh':
        if context.params.get('op') != 'finish' or context.params.get('kind') != 'static_mesh':
            raise ValueError('CraterPark meshes require the native finish operation')
        return mesh(context, unreal, args)
    if action not in ('parent', 'instance') or set(context.params) - {'args', 'settings', 'input_roots'}:
        raise ValueError('Unsupported CraterPark author operation')
    return {'parent': parent, 'instance': instance}[action](context, unreal, args)
