"""Current per-piece Brinecove finishing; no legacy receiver or reuse admission."""
import ast
import hashlib
import json
from pathlib import Path
import re

from atelier import encoded_glb
from atelier.build_v2.blender_validate import decode_mesh_payload
from atelier.export_manifest import validate as validate_export
from atelier.gltf import glb_parts
from island_finish_v2 import _identity, _pairs, _selected

LOD_PLAN = ((1., 1.), (.45, .3), (.2, .12), (.08, .04))


def _item(context, slot):
    value = context.inputs.get(slot)
    if value is None:
        raise ValueError('Missing selected Brinecove source Item')
    root = Path(value)
    if (not root.is_absolute() or not root.is_relative_to(Path(context.job_dir))
            or root.resolve() != root or root.is_symlink() or not root.is_dir()):
        raise ValueError('Brinecove source must be an independent job-local Item')
    return root


def source_facts(context):
    args = context.params['args']
    root = _item(context, args['source_export'])
    path = root / 'export.json'
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 1024 * 1024:
        raise ValueError('Missing bounded Brinecove export receipt')
    receipt = json.loads(path.read_bytes(), object_pairs_hook=_pairs,
                         parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite source receipt')))
    if (not isinstance(receipt, dict) or set(receipt) != {'schema', 'asset', 'primary', 'triangles', 'bounds', 'sha256', 'metadata'}
            or receipt['primary'] != receipt['asset'] + '.glb' or not re.fullmatch('SM_BC_[A-Za-z0-9_]+', receipt['asset'])
            or {p.name for p in root.iterdir()} != {'export.json', receipt['primary']}
            or validate_export(root, key=receipt['asset']) != receipt):
        raise ValueError('Invalid complete Brinecove export Item')
    payload = _item(context, args['payload'])
    names = [p.name for p in payload.iterdir()]
    if len(names) != 1 or names[0] not in (receipt['asset'] + '.npz', receipt['asset'] + '.mesh'):
        raise ValueError('Brinecove requires exactly its selected source payload')
    selected = payload / names[0]
    if selected.is_symlink() or not selected.is_file() or selected.stat().st_nlink != 1 or selected.stat().st_size > 128 * 1024 * 1024:
        raise ValueError('Invalid selected Brinecove payload')
    raw = selected.read_bytes(); digest = hashlib.sha256(raw).hexdigest()
    primary = (root / receipt['primary']).read_bytes()
    metadata = receipt['metadata']
    if not isinstance(metadata, dict):
        raise ValueError('Brinecove receipt metadata must be an object')
    policy = metadata.get('native_policy')
    geometry_metadata = {key: value for key, value in metadata.items() if key != 'native_policy'}
    if names[0].endswith('.mesh'):
        identity, actual = encoded_glb.decode(raw, key=receipt['asset'])
        if (identity['role'] != 'render' or primary != actual or receipt['triangles'] != identity['triangles']
                or receipt['bounds'] != identity['bounds'] or geometry_metadata != {key: value for key, value in identity['metadata'].items() if key != 'native_policy'} | {
                    'role': 'render', 'slots': identity['slots'], 'geometry_sha256': identity['sha256'], 'payload_sha256': digest}):
            raise ValueError('Brinecove encoded receipt/payload differ')
        slots, low_high = identity['slots'], identity['bounds']
        original_policy = identity['metadata'].get('native_policy', identity['metadata'])
        if policy is None:
            policy = original_policy
        elif policy != original_policy:
            raise ValueError('Brinecove receipt policy differs from selected encoded metadata')
    else:
        meta, _, facts = decode_mesh_payload(raw, expected_asset=receipt['asset'], output_format='glb')
        if (meta['collisions'] or receipt['triangles'] != facts['triangles'] or receipt['bounds'] != [facts['min'], facts['max']]
                or geometry_metadata != {'geometry_sha256': digest, 'slots': meta['slots'], 'polygons': facts['polygons'],
                    'collision_hulls': 0, 'uv_channels': facts['uv_channels']}):
            raise ValueError('Brinecove MeshIR receipt differs from actual selected source')
        slots, low_high = meta['slots'], [facts['min'], facts['max']]
    if (not isinstance(policy, dict) or type(policy.get('collision')) is not bool
            or type(policy.get('lods')) is not bool
            or not isinstance(policy.get('material_kinds'), dict)
            or set(policy['material_kinds']) != set(slots)
            or any(value not in ('terrain', 'opaque', 'masked', 'translucent', 'emissive')
                   for value in policy['material_kinds'].values())):
        raise ValueError('Brinecove source lacks explicit keyed collision/LOD policy')
    doc, _ = glb_parts(primary)
    primitives = [p for mesh in doc['meshes'] for p in mesh['primitives']]
    uv_sets = [{a for a in p['attributes'] if a.startswith('TEXCOORD_')} for p in primitives]
    if not uv_sets or any(uv != uv_sets[0] for uv in uv_sets):
        raise ValueError('Brinecove primitives disagree on original UV channels')
    return {'asset': receipt['asset'], 'triangles': receipt['triangles'], 'bounds': low_high,
            'slots': slots, 'material_kinds': policy['material_kinds'], 'uv_channels': len(uv_sets[0]), 'collision': policy['collision'], 'lods': policy['lods']}


def _originals():
    source = Path(__file__).resolve().parents[1] / 'unreal/Scripts/import_brinecove.py'
    functions = [node for node in ast.parse(source.read_bytes()).body
                 if isinstance(node, ast.FunctionDef) and node.name == 'generate_lods']
    if len(functions) != 1 or functions[0].decorator_list:
        raise ValueError('Original Brinecove LOD generator missing')
    import unreal
    namespace = {'unreal': unreal}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), 'exec'), namespace)
    return namespace['generate_lods']


def run(context):
    """@cc [owner:fontanierh,label:correctness] brinecove-current-piece-finish
    Finish MUST mutate only a fresh duplicate of the declared raw Item and own one
    original mesh package. Selected payload/export bytes MUST supply actual geometry
    and keyed collision/LOD policy. Preserve original ordered material assignment,
    full UV policy, double-sided complex collision and original LOD generation.
    Validate 98–100 percent source triangles, two-centimetre bounds and current
    collision/LOD/UV/material state before and after saving. No old main/reuse/cache.
    """
    import unreal
    from atelier.unreal_mesh_reuse import lods_match
    params = context.params
    if (set(params) - {'op', 'kind', 'source', 'destination', 'package_sources', 'args'}
            or params.get('op') != 'finish' or params.get('kind') != 'static_mesh'
            or not isinstance(params.get('args'), dict)
            or set(params['args']) != {'materials', 'source_export', 'payload'}):
        raise ValueError('Unexpected Brinecove finish parameters')
    facts = source_facts(context)
    destination = '/Game/Brinecove/Meshes/' + facts['asset']
    if params['destination'] != destination or list(context.outputs) != [destination]:
        raise ValueError('Brinecove finish owns exactly its one original mesh')
    source = _selected(context, params['source'])
    if source == destination:
        raise ValueError('Brinecove raw must remain independent')
    E = unreal.EditorAssetLibrary
    raw = E.load_asset(source)
    if not isinstance(raw, unreal.StaticMesh):
        raise ValueError('Brinecove raw Item is not a StaticMesh')
    _identity(raw, source)
    materials = []
    for name in facts['slots']:
        key = name.removeprefix('BC_')
        slot = params['args']['materials'].get(key)
        package = _selected(context, slot)
        if package != '/Game/Brinecove/Materials/MI_BC_' + key:
            raise ValueError('Brinecove material role differs from original slot')
        material = E.load_asset(package)
        if not isinstance(material, unreal.MaterialInterface):
            raise ValueError('Missing original Brinecove native material')
        _identity(material, package); materials.append(material)
    if E.does_asset_exist(destination):
        raise ValueError('Brinecove destination must be fresh')
    mesh = E.duplicate_asset(source, destination)
    if not isinstance(mesh, unreal.StaticMesh) or mesh is raw:
        raise ValueError('Brinecove native raw duplicate failed')
    _identity(mesh, destination)
    source_slots = [str(value.get_editor_property('imported_material_slot_name')) for value in mesh.static_materials]
    if len(mesh.static_materials) != len(materials) or source_slots != facts['slots']:
        raise ValueError('Brinecove native source material slots differ')
    for index, material in enumerate(materials):
        if mesh.get_material(index) != material:
            mesh.set_material(index, material)
    unreal.load_module('StaticMeshEditor')
    editor = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    if editor is None:
        raise ValueError('Native StaticMeshEditor unavailable')
    full = not facts['lods'] and any(kind != 'terrain' for kind in facts['material_kinds'].values())
    if full:
        settings = editor.get_lod_build_settings(mesh, 0)
        if not settings.get_editor_property('use_full_precision_u_vs'):
            settings.set_editor_property('use_full_precision_u_vs', True)
            editor.set_lod_build_settings(mesh, 0, settings)
    body = mesh.get_editor_property('body_setup')
    if body is None:
        raise ValueError('Brinecove mesh has no BodySetup')
    if facts['collision']:
        body.set_editor_property('collision_trace_flag', unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
        body.set_editor_property('double_sided_geometry', True)
    if facts['lods']:
        _originals()(mesh)
    validator = getattr(getattr(unreal, 'AtelierBuildWorkerLibrary', None), 'validate_mesh_collision', None)
    if facts['collision'] and not callable(validator):
        raise ValueError('Required generic C3 collision validator unavailable')
    low, high = facts['bounds']
    expected = [low[0] * 100, -high[1] * 100, low[2] * 100, high[0] * 100, -low[1] * 100, high[2] * 100]
    def validate():
        triangles = mesh.get_num_triangles(0)
        box = mesh.get_bounding_box()
        actual = [box.min.x, box.min.y, box.min.z, box.max.x, box.max.y, box.max.z]
        if (not facts['triangles'] * .98 <= triangles <= facts['triangles']
                or any(abs(a-b) >= 2. for a, b in zip(actual, expected))
                or len(mesh.static_materials) != len(materials)
                or [str(value.get_editor_property('imported_material_slot_name')) for value in mesh.static_materials] != source_slots
                or any(mesh.get_material(i) != material for i, material in enumerate(materials))
                or editor.get_num_uv_channels(mesh, 0) != facts['uv_channels']
                or (full and not editor.get_lod_build_settings(mesh, 0).get_editor_property('use_full_precision_u_vs'))
                or (facts['lods'] and not lods_match(mesh, LOD_PLAN))
                or (not facts['lods'] and mesh.get_num_lods() != 1)):
            raise ValueError('Brinecove current geometry/material/UV/LOD invariant failed')
        if facts['collision'] and (body.get_editor_property('collision_trace_flag') != unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE
                or not body.get_editor_property('double_sided_geometry') or not validator(mesh, triangles, False)):
            raise ValueError('Brinecove current native complex collision validation failed')
    validate()
    if not E.save_loaded_asset(mesh, True):
        raise ValueError('Brinecove native save failed')
    validate()
    return mesh
