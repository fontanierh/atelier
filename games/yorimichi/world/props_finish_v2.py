"""Finish exactly one world prop with setup_project.py's material and collision policy.

setup_project.py binds every imported slot by name (the slot's key before any '.') to MI_<key> and gives only
Pole, Pole_Lamp, Guardrail, Lantern and Torii a complex-as-simple trace; every other prop keeps the trace its raw
import produced. The source facts are the piece's own export receipt and selected MeshIR payload: its palette
slots, triangles, bounds, UV sets and any authored UCX hulls. The finish binds them to the existing native
validators (exact triangles, Blender-to-Unreal bounds, UCX vertices and, for the five complex props, cooked
collision) before and after its primary save. No triangle may be dropped: native triangles equal the source.
"""
import hashlib
import json
from pathlib import Path

import numpy as np
from atelier.build_v2.blender_validate import decode_mesh_payload
from atelier.conventions import to_unreal
from atelier.export_manifest import validate as validate_export
from city_tile_products import collision_matches, native_bounds
from island_finish_v2 import _identity, _pairs, _selected

DESTINATION = '/Game/Japan/Assets'
RAW = '/Game/_Raw/Props'
MATERIALS = '/Game/Japan/Materials/MI_'
COMPLEX = ('Guardrail', 'Lantern', 'Pole', 'Pole_Lamp', 'Torii')
PROPS = ('BirdBody', 'BirdWingL', 'BirdWingR', 'Guardrail', 'Lantern', 'Leaf', 'Litter', 'Pole', 'Pole_Lamp',
         'Rock_A', 'Rock_B', 'Rock_C', 'SkyDome', 'Torii')


def _path(context, slot, *, directory):
    value = context.inputs.get(slot)
    if value is None or context.packages.get(slot) not in ([], ()):
        raise ValueError('World prop source role must be a declared Data Item: ' + str(slot))
    path = Path(value)
    if (not path.is_absolute() or not path.is_relative_to(Path(context.job_dir)) or path.resolve() != path
            or path.is_symlink() or (not path.is_dir() if directory else not path.is_file())):
        raise ValueError('World prop source must be an independent regular job-local Item')
    return path


def _key(slot):
    return str(slot).split('.')[0]


def source_facts(context):
    args = context.params['args']; parent = args['parent']
    if parent not in PROPS or args['collision'] != ('complex_as_simple' if parent in COMPLEX else 'original'):
        raise ValueError('Unknown world prop or changed collision policy')
    root = _path(context, args['source_export'], directory=True)
    receipt_path = root / 'export.json'
    if receipt_path.is_symlink() or not receipt_path.is_file() or not 0 < receipt_path.stat().st_size <= 1024 * 1024:
        raise ValueError('World prop export Item has no bounded receipt')
    receipt = json.loads(receipt_path.read_bytes(), object_pairs_hook=_pairs,
                         parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite world prop receipt')))
    if (not isinstance(receipt, dict) or set(receipt) != {'schema', 'asset', 'primary', 'triangles', 'bounds', 'sha256', 'metadata'}
            or receipt['asset'] != parent or receipt['primary'] != parent + '.fbx'
            or {p.name for p in root.iterdir()} != {'export.json', receipt['primary']}
            or validate_export(root, key=parent) != receipt):
        raise ValueError('World prop export Item differs from its exact selected source')
    payload = _path(context, args['payload'], directory=True)
    members = list(payload.iterdir())
    if (len(members) != 1 or members[0].name != parent + '.npz' or members[0].is_symlink()
            or not members[0].is_file() or not 0 < members[0].stat().st_size <= 128 * 1024 * 1024):
        raise ValueError('World prop requires exactly the selected bounded MeshIR payload')
    raw = members[0].read_bytes(); digest = hashlib.sha256(raw).hexdigest()
    metadata, _piece, facts = decode_mesh_payload(raw, expected_asset=parent, output_format='fbx')
    if (not facts['slots'] or not {_key(s) for s in facts['slots']} <= set(args['materials']) or not facts['uv_channels']
            or receipt['triangles'] != facts['triangles'] or receipt['bounds'] != [facts['min'], facts['max']]
            or receipt['metadata'] != {'geometry_sha256': digest, 'slots': facts['slots'], 'polygons': facts['polygons'],
                'collision_hulls': facts['collision_hulls'], 'uv_channels': facts['uv_channels']}):
        raise ValueError('World prop source receipt differs from its selected geometry, palette or UV sets')
    hulls = []
    for hull in metadata['collisions']:
        transform = np.asarray(hull['matrix'])
        vertices = np.asarray(hull['vertices']) @ transform[:3, :3].T + transform[:3, 3]
        hulls.append([[float(v) for v in to_unreal(point)] for point in vertices])
    return facts, hulls


def run(context):
    """@cc [owner:fontanierh,label:correctness] current-world-prop-native-piece
    Only a fresh duplicate of the declared raw Item MAY be mutated, at the original
    /Game/Japan/Assets/<parent>. Its own export and MeshIR MUST prove the palette
    slots, exact triangles, bounds, UV sets and authored hulls. Every slot binds the
    supplied MI_<key> by name. Only the five original props become complex-as-simple;
    the rest keep the raw trace. The checks and a real primary save MUST hold before
    and after save. No source import, cache or retirement MAY run.
    """
    import unreal
    p = context.params
    if (set(p) - {'op', 'kind', 'source', 'destination', 'package_sources', 'args', 'settings'}
            or p.get('op') != 'finish' or p.get('kind') != 'static_mesh' or not isinstance(p.get('args'), dict)
            or set(p['args']) != {'parent', 'collision', 'payload', 'source_export', 'materials', 'native_inputs'}):
        raise ValueError('Unsupported world prop finish parameters')
    args = p['args']; native = args['native_inputs']; materials = args['materials']
    if (not isinstance(native, dict) or not isinstance(materials, dict) or not materials
            or any(native.get(slot) != MATERIALS + key for key, slot in materials.items())
            or set(context.inputs) != {'raw', args['source_export'], args['payload'], *native}
            or set(context.packages) != set(context.inputs)):
        raise ValueError('World prop finish input membership differs from its declared sources/native closure')
    facts, hulls = source_facts(context)
    parent, complex_ = args['parent'], args['collision'] == 'complex_as_simple'
    destination = DESTINATION + '/' + parent
    source = _selected(context, p['source'])
    if (p['source'] != 'raw' or p['destination'] != destination or list(context.outputs) != [destination]
            or source != RAW + '/' + parent):
        raise ValueError('World prop finish must own exactly its selected original package')
    library = unreal.EditorAssetLibrary
    raw = library.load_asset(source)
    if not isinstance(raw, unreal.StaticMesh):
        raise ValueError('World prop raw Item is not a StaticMesh')
    _identity(raw, source)
    loaded = {}
    for slot, package in native.items():
        if _selected(context, slot) != package:
            raise ValueError('World prop native dependency differs')
        asset = library.load_asset(package)
        if asset is None:
            raise ValueError('World prop declared material dependency did not load')
        _identity(asset, package); loaded[slot] = asset
    bound = {key: loaded[slot] for key, slot in materials.items()}
    if not all(isinstance(material, unreal.MaterialInterface) for material in bound.values()):
        raise ValueError('World prop materials must be their supplied MaterialInterfaces')
    validation = getattr(unreal, 'CitySurfaceValidation', None)
    if not all(callable(getattr(validation, name, None)) for name in ('validate_collision', 'collision_vertices')):
        raise ValueError('Required produced world prop collision validation module is unavailable')
    unreal.load_module('StaticMeshEditor')
    editor = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    if editor is None:
        raise ValueError('Native StaticMeshEditor unavailable')
    if library.does_asset_exist(destination):
        raise ValueError('World prop destination must be fresh')
    mesh = library.duplicate_asset(source, destination)
    if not isinstance(mesh, unreal.StaticMesh) or mesh is raw:
        raise ValueError('World prop raw duplicate failed')
    _identity(mesh, destination)
    slots = [_key(m.get_editor_property('imported_material_slot_name')) for m in mesh.static_materials]
    if sorted(slots) != sorted(_key(s) for s in facts['slots']):
        raise ValueError(f'{parent}: imported material slots differ from the selected palette slots')
    for index, key in enumerate(slots):
        mesh.set_material(index, bound[key])
    body = mesh.get_editor_property('body_setup')
    if body is None:
        raise ValueError('World prop mesh has no BodySetup')
    if complex_:
        body.set_editor_property('collision_trace_flag', unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    trace = body.get_editor_property('collision_trace_flag')
    low, high = native_bounds({'min': facts['min'], 'max': facts['max']})
    row, tile = {'source_collision_vertices': hulls}, {'collision_hulls': len(hulls)}
    def validate():
        box = mesh.get_bounding_box()
        if (mesh.get_num_triangles(0) != facts['triangles'] or mesh.get_num_lods() != 1
                or any(mesh.get_material(i) != bound[key] for i, key in enumerate(slots))
                or body.get_editor_property('collision_trace_flag') != trace
                or editor.get_num_uv_channels(mesh, 0) != len(facts['uv_channels'])
                or not collision_matches(mesh, row, tile, read_vertices=validation.collision_vertices)
                or any(not abs(getattr(box.min, axis) - a) < .2 or not abs(getattr(box.max, axis) - b) < .2
                       for axis, a, b in zip(('x', 'y', 'z'), low, high))):
            raise ValueError(f'{parent}: current geometry/material/UV/collision invariant failed')
        # The produced validator covers the five complex-as-simple props; the original raw trace has no cooked check.
        if complex_ and not validation.validate_collision(mesh, facts['triangles'], False):
            raise ValueError(f'{parent}: original cooked collision validation failed')
    validate()
    if not library.save_loaded_asset(mesh, True):
        raise ValueError('World prop dirty-only native save failed')
    primary = Path(context.content_dir) / (destination.removeprefix('/Game/') + '.uasset')
    if any(part.is_symlink() for part in (primary, *primary.parents)) or not primary.is_file():
        raise ValueError('World prop native save did not leave its actual regular primary package')
    validate()
    return mesh
