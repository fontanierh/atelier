"""Finish exactly one house or lot mesh with import_houses.py's slot, collision and scale policy.

The source facts are the piece's own export receipt and selected MeshIR payload (never the assembled
houses/manifest.json or build-identity.json): the receipt must equal the decoded payload's triangles, bounds, slots,
UV channels and UCX hull count. The finish then keeps the original checks (slot names equal the source slots,
convex elements at least the source hulls, bounding-box max Z within 0.5 cm of the source) and adds native
triangles, one UV set and the produced module's cooked collision validation, before and after its primary save.
"""
import hashlib
import json
from pathlib import Path

from atelier.build_v2.blender_validate import decode_mesh_payload
from atelier.export_manifest import validate as validate_export
from island_finish_v2 import _identity, _pairs, _selected
from village_atomic_products import ground_native_count

DESTINATION = '/Game/Japan/Assets'
MATERIALS = {'Village': '/Game/Japan/Materials/M_Village', 'Ground': '/Game/Japan/Materials/MI_Ground'}
HOUSES = ('House_A', 'House_B', 'House_C')
LOTS = tuple(f'HouseLot_{i}' for i in range(1, 6))


def _path(context, slot, *, directory):
    value = context.inputs.get(slot)
    if value is None or context.packages.get(slot) not in ([], ()):
        raise ValueError('Houses source role must be a declared Data Item: ' + str(slot))
    path = Path(value)
    if (not path.is_absolute() or not path.is_relative_to(Path(context.job_dir)) or path.resolve() != path
            or path.is_symlink() or (not path.is_dir() if directory else not path.is_file())):
        raise ValueError('Houses source must be an independent regular job-local Item')
    return path


def source_facts(context):
    args = context.params['args']; parent = args['parent']
    if parent not in HOUSES + LOTS or args['lot'] is not (parent in LOTS):
        raise ValueError('Unknown houses logical parent')
    root = _path(context, args['source_export'], directory=True)
    receipt_path = root / 'export.json'
    if receipt_path.is_symlink() or not receipt_path.is_file() or not 0 < receipt_path.stat().st_size <= 1024 * 1024:
        raise ValueError('Houses export Item has no bounded receipt')
    receipt = json.loads(receipt_path.read_bytes(), object_pairs_hook=_pairs,
                         parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite houses receipt')))
    if (not isinstance(receipt, dict) or set(receipt) != {'schema', 'asset', 'primary', 'triangles', 'bounds', 'sha256', 'metadata'}
            or receipt['asset'] != parent or receipt['primary'] != parent + '.fbx'
            or {p.name for p in root.iterdir()} != {'export.json', receipt['primary']}
            or validate_export(root, key=parent) != receipt):
        raise ValueError('Houses export Item differs from its exact selected source')
    payload = _path(context, args['payload'], directory=True)
    members = list(payload.iterdir())
    if (len(members) != 1 or members[0].name != parent + '.npz' or members[0].is_symlink()
            or not members[0].is_file() or not 0 < members[0].stat().st_size <= 128 * 1024 * 1024):
        raise ValueError('Houses require exactly the selected bounded MeshIR payload')
    raw = members[0].read_bytes(); digest = hashlib.sha256(raw).hexdigest()
    metadata, piece, facts = decode_mesh_payload(raw, expected_asset=parent, output_format='fbx')
    slots = ['Village'] if parent in HOUSES else ['Ground', 'Village']
    if (sorted(facts['slots']) != slots or len(facts['uv_channels']) != 1
            or receipt['triangles'] != facts['triangles'] or receipt['bounds'] != [facts['min'], facts['max']]
            or receipt['metadata'] != {'geometry_sha256': digest, 'slots': facts['slots'], 'polygons': facts['polygons'],
                'collision_hulls': facts['collision_hulls'], 'uv_channels': facts['uv_channels']}):
        raise ValueError('Houses source receipt differs from its selected geometry, slots or UV set')
    # The same installed legacy FBX triangle-removal rule applies to these
    # triangular lot faces; never accept arbitrary missing native geometry.
    facts['native_triangles'] = ground_native_count(metadata, piece)['native_triangles']
    return receipt, facts


def run(context):
    """@cc [owner:fontanierh,label:correctness] current-houses-native-piece
    Only a fresh duplicate of the declared raw Item MAY be mutated, at the original
    /Game/Japan/Assets/<parent>. Its own export and MeshIR MUST prove its slots,
    triangles, bounds, UV set and hull count. Slots bind Village->M_Village and
    Ground->MI_Ground from the supplied closure; houses are simple-and-complex and
    lots complex-as-simple. The original checks, native triangles/UV, produced-module
    collision validation and a real primary save MUST hold before and after save.
    """
    import unreal
    p = context.params
    if (set(p) - {'op', 'kind', 'source', 'destination', 'package_sources', 'args', 'settings'}
            or p.get('op') != 'finish' or p.get('kind') != 'static_mesh' or not isinstance(p.get('args'), dict)
            or set(p['args']) != {'parent', 'lot', 'payload', 'source_export', 'materials', 'native_inputs'}):
        raise ValueError('Unsupported houses finish parameters')
    args = p['args']; native = args['native_inputs']; bindings = args['materials']
    if (not isinstance(native, dict) or not isinstance(bindings, dict) or set(bindings) != set(MATERIALS)
            or any(native.get(slot) != MATERIALS[name] for name, slot in bindings.items())
            or set(context.inputs) != {'raw', args['source_export'], args['payload'], *native}
            or set(context.packages) != set(context.inputs)):
        raise ValueError('Houses finish input membership differs from its declared sources/native closure')
    receipt, facts = source_facts(context)
    parent, lot = args['parent'], args['lot']
    destination = DESTINATION + '/' + parent
    source = _selected(context, p['source'])
    if (p['source'] != 'raw' or p['destination'] != destination or list(context.outputs) != [destination]
            or source != '/Game/_Raw/Houses/' + parent):
        raise ValueError('Houses finish must own exactly its selected original package')
    library = unreal.EditorAssetLibrary
    raw = library.load_asset(source)
    if not isinstance(raw, unreal.StaticMesh):
        raise ValueError('Houses raw Item is not a StaticMesh')
    _identity(raw, source)
    loaded = {}
    for slot, package in native.items():
        if _selected(context, slot) != package:
            raise ValueError('Houses native dependency differs')
        asset = library.load_asset(package)
        if asset is None:
            raise ValueError('Houses declared material dependency did not load')
        _identity(asset, package); loaded[slot] = asset
    materials = {name: loaded[slot] for name, slot in bindings.items()}
    if not all(isinstance(material, unreal.MaterialInterface) for material in materials.values()):
        raise ValueError('Houses materials must be their supplied MaterialInterfaces')
    validation = getattr(unreal, 'CitySurfaceValidation', None)
    if not callable(getattr(validation, 'validate_collision', None)):
        raise ValueError('Required produced houses collision validation module is unavailable')
    unreal.load_module('StaticMeshEditor')
    editor = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    if editor is None:
        raise ValueError('Native StaticMeshEditor unavailable')
    if library.does_asset_exist(destination):
        raise ValueError('Houses destination must be fresh')
    mesh = library.duplicate_asset(source, destination)
    if not isinstance(mesh, unreal.StaticMesh) or mesh is raw:
        raise ValueError('Houses raw duplicate failed')
    _identity(mesh, destination)
    names = [str(s.get_editor_property('imported_material_slot_name')).split('.')[0] for s in mesh.static_materials]
    if sorted(names) != sorted(facts['slots']):
        raise ValueError(f'{parent}: material slots {names} differ from the source')
    for index, name in enumerate(names):
        mesh.set_material(index, materials[name])
    body = mesh.get_editor_property('body_setup')
    if body is None:
        raise ValueError('Houses mesh has no BodySetup')
    trace = (unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE if lot
             else unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AND_COMPLEX)
    body.set_editor_property('collision_trace_flag', trace)
    def validate():
        box = mesh.get_bounding_box()
        convex = len(body.get_editor_property('agg_geom').get_editor_property('convex_elems'))
        triangles = mesh.get_num_triangles(0)
        if (convex < receipt['metadata']['collision_hulls'] or abs(box.max.z - receipt['bounds'][1][2] * 100) >= .5
                or [mesh.get_material(i) for i in range(len(names))] != [materials[n] for n in names]
                or body.get_editor_property('collision_trace_flag') != trace or mesh.get_num_lods() != 1
                or editor.get_num_uv_channels(mesh, 0) != 1
                or triangles != facts['native_triangles']):
            raise ValueError(f'{parent}: current geometry/material/UV/collision invariant failed')
        if not validation.validate_collision(mesh, triangles, not lot):
            raise ValueError(f'{parent}: original cooked LOD0 collision validation failed')
    validate()
    if not library.save_loaded_asset(mesh, True):
        raise ValueError('Houses dirty-only native save failed')
    primary = Path(context.content_dir) / (destination.removeprefix('/Game/') + '.uasset')
    if any(part.is_symlink() for part in (primary, *primary.parents)) or not primary.is_file():
        raise ValueError('Houses native save did not leave its actual regular primary package')
    validate()
    return mesh
