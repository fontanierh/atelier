"""Finish one current Treehouse mesh from its selected export and original MeshIR."""
import hashlib
import json
from pathlib import Path
import re
import sys

from atelier.build_v2.blender_validate import decode_mesh_payload
from atelier.export_manifest import validate as validate_export
from island_finish_v2 import _identity, _package, _pairs, _selected


def _directory(context, slot):
    value = context.inputs.get(slot)
    if value is None:
        raise ValueError('Missing declared Treehouse selected Item')
    root = Path(value)
    job = Path(context.job_dir)
    if (not root.is_absolute() or not root.is_relative_to(job) or root.resolve() != root
            or root.is_symlink() or not root.is_dir()):
        raise ValueError('Treehouse source must be an independent job-local Item')
    return root


def source_facts(context, parent):
    """Check exact selected payload/export binding; no generated inventory is read."""
    args = context.params['args']
    source = _directory(context, args['source_export'])
    receipt_path = source / 'export.json'
    if (receipt_path.is_symlink() or not receipt_path.is_file()
            or not 0 < receipt_path.stat().st_size <= 1024 * 1024):
        raise ValueError('Missing bounded Treehouse export receipt')
    raw = receipt_path.read_bytes()
    receipt = json.loads(raw, object_pairs_hook=_pairs,
                         parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite receipt')))
    if (not isinstance(receipt, dict) or set(receipt) != {
            'schema', 'asset', 'primary', 'triangles', 'bounds', 'sha256', 'metadata'}
            or type(receipt['schema']) is not int or receipt['schema'] != 1
            or not isinstance(receipt['asset'], str) or not re.fullmatch('[A-Za-z0-9_-]+', receipt['asset'])
            or receipt['primary'] != receipt['asset'] + '.fbx'
            or {member.name for member in source.iterdir()} != {'export.json', receipt['primary']}
            or validate_export(source, key=receipt['asset']) != receipt or receipt_path.read_bytes() != raw):
        raise ValueError('Invalid complete Treehouse source export')
    payload = _directory(context, args['payload'])
    member = receipt['asset'] + '.npz'
    file = payload / member
    if ({path.name for path in payload.iterdir()} != {member} or file.is_symlink()
            or not file.is_file() or file.stat().st_nlink != 1 or file.stat().st_size > 128 * 1024 * 1024):
        raise ValueError('Invalid selected Treehouse MeshIR member')
    data = file.read_bytes()
    meta, piece, facts = decode_mesh_payload(data, expected_asset=receipt['asset'], output_format='fbx')
    expected = {'geometry_sha256': hashlib.sha256(data).hexdigest(), 'slots': meta['slots'],
                'polygons': facts['polygons'], 'collision_hulls': facts['collision_hulls'],
                'uv_channels': facts['uv_channels']}
    if (receipt['metadata'] != expected or receipt['triangles'] != facts['triangles']
            or receipt['bounds'] != [facts['min'], facts['max']]):
        raise ValueError('Treehouse source receipt differs from its selected payload')
    if parent in ('TH_Structure', 'TH_Dressing'):
        if not re.fullmatch(re.escape(parent) + r'_cell_(?:0|-?[1-9][0-9]*)_(?:0|-?[1-9][0-9]*)(?:_Piece[0-3]{1,16})?', receipt['asset']):
            raise ValueError('Foreign bounded Treehouse surface piece')
    elif receipt['asset'] != parent:
        raise ValueError('Treehouse whole owner identity differs')
    expected_uvs = ['UVMap', 'Piece1', 'Piece2', 'Piece3', 'Piece4'] if parent in ('TH_Frame', 'TH_Dressing') else ['UVMap']
    if facts['uv_channels'] != expected_uvs:
        raise ValueError('Treehouse original UV channel contract differs')
    if not parent.startswith('TH_P_') and meta['collisions']:
        raise ValueError('Treehouse surface/canopy cannot acquire authored hulls')
    return receipt, meta, piece, facts


def run(context):
    """@cc [owner:fontanierh,label:correctness] treehouse-per-piece-current-finish
    Finish MUST duplicate only the declared raw Item to its fresh original package.
    Actual source payload/export binding, triangles, bounds, original material slots,
    one LOD, all UVs/precision and exact authored convex hulls MUST be checked before
    and after saving. Complex surfaces MUST pass existing native cooked collision
    validation. Missing material/native validators MUST refuse. No receive/cache,
    main, generated plan scan, fallback or retirement action MAY execute here.
    """
    import unreal
    params = context.params
    if (set(params) - {'op', 'kind', 'source', 'destination', 'args', 'package_sources'}
            or params.get('op') != 'finish' or params.get('kind') != 'static_mesh'
            or not isinstance(params.get('args'), dict)
            or set(params['args']) != {'parent', 'source_export', 'payload', 'materials'}):
        raise ValueError('Unexpected Treehouse finish parameters')
    args, destination = params['args'], _package(params['destination'])
    parent = args['parent']
    if not isinstance(parent, str) or not re.fullmatch(r'(?:Tree_Canopy_[A-Za-z]+|TH_P_[a-z_]+|TH_(?:Structure|Frame|Trunks|Dressing))', parent):
        raise ValueError('Unknown Treehouse native family')
    receipt, meta, piece, facts = source_facts(context, parent)
    folder = ('/Game/Japan/Treehouse/StructurePieces' if parent == 'TH_Structure' else
              '/Game/Japan/Treehouse/Pieces' if parent == 'TH_Dressing' else '/Game/Japan/Assets')
    if destination != folder + '/' + receipt['asset'] or list(context.outputs) != [destination]:
        raise ValueError('Treehouse finish owns exactly its original one package')
    source = _selected(context, params['source'])
    if source == destination:
        raise ValueError('Treehouse raw input must remain independent')
    unreal.load_module('StaticMeshEditor')
    editor = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    if editor is None:
        raise ValueError('StaticMeshEditor subsystem unavailable')
    library = unreal.EditorAssetLibrary
    raw = library.load_asset(source)
    if not isinstance(raw, unreal.StaticMesh):
        raise ValueError('Treehouse raw Item is not a native StaticMesh')
    _identity(raw, source)
    mapping = args['materials']
    if not isinstance(mapping, dict):
        raise ValueError('Missing declared Treehouse materials')
    prop = parent.startswith('TH_P_')
    if (prop and set(mapping) != {'__prop__'}) or (not prop and not set(meta['slots']) <= set(mapping)):
        raise ValueError('Missing original Treehouse material role')
    materials = {}
    for name, slot in mapping.items():
        package = _selected(context, slot)
        material = library.load_asset(package)
        if not isinstance(material, unreal.MaterialInterface):
            raise ValueError('Declared Treehouse material did not load')
        _identity(material, package)
        materials[name] = material
    if library.does_asset_exist(destination):
        raise ValueError('Treehouse finish destination must be fresh')
    mesh = library.duplicate_asset(source, destination)
    if not isinstance(mesh, unreal.StaticMesh) or mesh is raw:
        raise ValueError('Treehouse raw duplicate failed')
    _identity(mesh, destination)
    actual = [str(value.get_editor_property('imported_material_slot_name')) for value in mesh.static_materials]
    used = {meta['slots'][index] for index in facts['used_material_indices']}
    if len(set(actual)) != len(actual) or not used <= set(actual) <= set(meta['slots']):
        raise ValueError('Treehouse native slots differ from actual source')
    for index, name in enumerate(actual):
        material = materials['__prop__' if prop else name]
        if mesh.get_material(index) != material:
            mesh.set_material(index, material)
    full_precision = parent in ('TH_Frame', 'TH_Dressing')
    settings = editor.get_lod_build_settings(mesh, 0)
    if settings.get_editor_property('use_full_precision_u_vs') != full_precision:
        settings.set_editor_property('use_full_precision_u_vs', full_precision)
        editor.set_lod_build_settings(mesh, 0, settings)
    complex_surface = parent in ('TH_Structure', 'TH_Frame', 'TH_Trunks')
    flag = unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE if complex_surface else unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX
    body = mesh.get_editor_property('body_setup')
    if body is None:
        raise ValueError('Treehouse mesh has no BodySetup')
    body.set_editor_property('collision_trace_flag', flag)
    # Reuse the original exact authored-hull comparator, not hull counts alone.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'unreal/Scripts'))
    from forest_native import hulls_match
    validator = getattr(getattr(unreal, 'AtelierBuildWorkerLibrary', None), 'validate_mesh_collision', None)
    if complex_surface and not callable(validator):
        raise ValueError('Required C3 cooked collision validator unavailable')
    low, high = facts['min'], facts['max']
    bounds = ([low[0] * 100., -high[1] * 100., low[2] * 100.],
              [high[0] * 100., -low[1] * 100., high[2] * 100.])
    def validate():
        current = [str(value.get_editor_property('imported_material_slot_name')) for value in mesh.static_materials]
        if (mesh.get_num_lods() != 1 or mesh.get_num_triangles(0) != facts['triangles']
                or editor.get_num_uv_channels(mesh, 0) != len(facts['uv_channels'])
                or editor.get_lod_build_settings(mesh, 0).get_editor_property('use_full_precision_u_vs') != full_precision
                or current != actual or editor.get_simple_collision_count(mesh) != 0
                or editor.get_convex_collision_count(mesh) != len(meta['collisions'])
                or not hulls_match(mesh, meta['collisions'])
                or body.get_editor_property('collision_trace_flag') != flag
                or mesh.get_editor_property('lod_for_collision') != 0
                or mesh.get_editor_property('complex_collision_mesh') is not None
                or any(mesh.get_material(i) != materials['__prop__' if prop else name] for i, name in enumerate(actual))):
            raise ValueError('Treehouse native geometry/material/UV/hull invariant failed')
        box = mesh.get_bounding_box()
        if any(abs(getattr(point, axis) - expected[i]) >= .2 for point, expected in zip((box.min, box.max), bounds)
               for i, axis in enumerate(('x', 'y', 'z'))):
            raise ValueError('Treehouse native bounds differ from selected source')
        if complex_surface and not validator(mesh, facts['triangles'], False):
            raise ValueError('Treehouse current cooked complex collision validation failed')
    validate()
    if not library.save_loaded_asset(mesh, True):
        raise ValueError('Treehouse native package save failed')
    validate()
    return mesh
