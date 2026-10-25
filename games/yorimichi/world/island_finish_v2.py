"""Finish one declared island raw mesh; no source import, receive loop or cache access."""
import json
from pathlib import Path
import re

from atelier.export_manifest import validate as validate_export

PACKAGE = re.compile(r'/Game/(?:[A-Za-z0-9_]+/)*[A-Za-z0-9_]+\Z')


def _package(value):
    if not isinstance(value, str) or not PACKAGE.fullmatch(value):
        raise ValueError('Expected a canonical declared /Game package')
    return value


def _selected(context, slot):
    if not isinstance(slot, str) or slot not in context.inputs or context.inputs[slot] is None:
        raise ValueError('Missing declared island package input')
    packages = context.packages.get(slot)
    if isinstance(packages, str):
        packages = [packages]
    if not isinstance(packages, (list, tuple)) or not packages:
        raise ValueError('Island input has no declared package content')
    selected = context.params.get('package_sources', {}).get(slot)
    if selected is None and len(packages) == 1:
        selected = packages[0]
    if selected not in packages:
        raise ValueError('Island package selection is absent or ambiguous')
    return _package(selected)


def _pairs(rows):
    result = {}
    for key, value in rows:
        if key in result:
            raise ValueError('Duplicate source receipt field')
        result[key] = value
    return result


def _source(context, slot):
    if not isinstance(slot, str) or slot not in context.inputs or context.inputs[slot] is None:
        raise ValueError('Missing declared island source_export Item')
    root = Path(context.inputs[slot])
    job = Path(context.job_dir)
    if (not root.is_absolute() or not root.is_relative_to(job) or root.resolve() != root
            or root.is_symlink() or not root.is_dir()):
        raise ValueError('Island source export must be an independent job-local Item directory')
    path = root / 'export.json'
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 1024 * 1024:
        raise ValueError('Missing bounded source export receipt')
    raw = path.read_bytes()
    receipt = json.loads(raw, object_pairs_hook=_pairs,
                         parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite source receipt')))
    if (not isinstance(receipt, dict) or type(receipt.get('schema')) is not int
            or set(receipt) != {'schema', 'asset', 'primary', 'triangles', 'bounds', 'sha256', 'metadata'}):
        raise ValueError('Unexpected source receipt fields')
    if {member.name for member in root.iterdir()} != {'export.json', receipt['primary']}:
        raise ValueError('Island source Item has foreign members')
    checked = validate_export(root, key=receipt['asset'])
    if checked != receipt or path.read_bytes() != raw:
        raise ValueError('Source receipt changed during validation')
    meta = receipt['metadata']
    if (not isinstance(meta, dict) or not isinstance(meta.get('slots'), list) or not meta['slots']
            or any(not isinstance(name, str) or not name for name in meta['slots'])
            or len(set(meta['slots'])) != len(meta['slots'])
            or not isinstance(meta.get('geometry_sha256'), str)
            or not re.fullmatch('[0-9a-f]{64}', meta['geometry_sha256'])):
        raise ValueError('Source receipt has no complete original material/geometry identity')
    if Path(receipt['primary']).suffix == '.fbx':
        if (type(meta.get('collision_hulls')) is not int or meta['collision_hulls'] != 0 or meta.get('uv_channels') != ['UVMap']
                or type(meta.get('polygons')) is not int or not 0 < meta['polygons'] <= receipt['triangles']):
            raise ValueError('Island FBX receipt must have one UV channel and no authored hulls')
        used = set(meta['slots'])
    else:
        from atelier import encoded_glb
        from atelier.gltf import glb_parts
        data = (root / receipt['primary']).read_bytes()
        facts = encoded_glb.geometry(data)
        if (meta.get('role') != 'render' or meta['geometry_sha256'] != receipt['sha256']
                or not isinstance(meta.get('payload_sha256'), str)
                or not re.fullmatch('[0-9a-f]{64}', meta['payload_sha256'])
                or facts != {'triangles': receipt['triangles'], 'bounds': receipt['bounds'], 'slots': meta['slots']}):
            raise ValueError('Island GLB receipt differs from its actual exported geometry')
        doc, _ = glb_parts(data)
        primitives = [primitive for mesh in doc['meshes'] for primitive in mesh['primitives']]
        if any({key for key in primitive['attributes'] if key.startswith('TEXCOORD_')} != {'TEXCOORD_0'}
               for primitive in primitives):
            raise ValueError('Island GLB requires exactly one source UV channel')
        used = {meta['slots'][primitive['material']] for primitive in primitives}
    lower, upper = receipt['bounds']
    bounds = ([lower[0] * 100., -upper[1] * 100., lower[2] * 100.],
              [upper[0] * 100., -lower[1] * 100., upper[2] * 100.])
    return receipt, used, bounds


def _identity(asset, package):
    if asset.get_path_name().split('.', 1)[0] != package:
        raise ValueError('Native island asset resolves outside its declared package')


def run(context):
    """@cc [owner:fontanierh,label:correctness;performance] c3-island-current-finish
    Expected geometry MUST come only from the complete declared source export and
    verified receipt. Mutations MUST affect a fresh duplicate at the sole declared
    destination, never raw inputs. Bind every native original material slot through
    declared package inputs. Require one LOD, exact triangles, original native bounds,
    one half-precision UV channel, zero simple/convex hulls and actual cooked complex
    LOD0 validation before and after saving. Missing native validation MUST refuse;
    no importer, whole receiver, cache, retirement or fallback may run here.
    """
    import unreal
    params = context.params
    if (set(params) - {'op', 'kind', 'source', 'destination', 'args', 'package_sources'}
            or not {'op', 'kind', 'source', 'destination', 'args'} <= set(params)
            or params['op'] != 'finish' or params['kind'] != 'static_mesh'
            or not isinstance(params['args'], dict) or set(params['args']) != {'source_export', 'materials'}
            or not isinstance(params.get('package_sources', {}), dict)):
        raise ValueError('Unexpected island finish parameters')
    destination = _package(params['destination'])
    if list(context.outputs) != [destination]:
        raise ValueError('Island finish owns exactly one declared output package')
    source = _selected(context, params['source'])
    if source == destination:
        raise ValueError('Island raw input and finished destination must differ')
    receipt, used, bounds = _source(context, params['args']['source_export'])
    mapping = params['args']['materials']
    if not isinstance(mapping, dict) or not set(receipt['metadata']['slots']) <= set(mapping):
        raise ValueError('Island material bindings differ from the original source table')
    validator = getattr(getattr(unreal, 'AtelierBuildWorkerLibrary', None), 'validate_mesh_collision', None)
    if not callable(validator):
        raise ValueError('Required native mesh collision validator is unavailable')
    unreal.load_module('StaticMeshEditor')
    editor = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    if editor is None:
        raise ValueError('Required native StaticMeshEditor subsystem is unavailable')
    library = unreal.EditorAssetLibrary
    raw = library.load_asset(source)
    if not isinstance(raw, unreal.StaticMesh):
        raise ValueError('Island raw input is not a native StaticMesh')
    _identity(raw, source)
    materials = {}
    for original, slot in mapping.items():
        package = _selected(context, slot)
        material = library.load_asset(package)
        if not isinstance(material, unreal.MaterialInterface):
            raise ValueError('Declared island material did not load as MaterialInterface')
        _identity(material, package)
        materials[original] = material
    if library.does_asset_exist(destination):
        raise ValueError('Island finish destination must be fresh')
    mesh = library.duplicate_asset(source, destination)
    if not isinstance(mesh, unreal.StaticMesh) or mesh is raw:
        raise ValueError('Island raw duplicate failed')
    _identity(mesh, destination)
    if mesh.get_num_triangles(0) != receipt['triangles'] or mesh.get_num_lods() != 1:
        raise ValueError('Island current native render geometry differs from source')
    actual = []
    for index, value in enumerate(mesh.static_materials):
        name = str(value.get_editor_property('imported_material_slot_name'))
        if name not in receipt['metadata']['slots'] or name not in materials or name in actual:
            raise ValueError('Island native material slot identity differs from source')
        actual.append(name)
        if mesh.get_material(index) != materials[name]:
            mesh.set_material(index, materials[name])
    if not used <= set(actual):
        raise ValueError('Island native mesh lost a consumed original material slot')
    settings = editor.get_lod_build_settings(mesh, 0)
    if settings.get_editor_property('use_full_precision_u_vs'):
        settings.set_editor_property('use_full_precision_u_vs', False)
        editor.set_lod_build_settings(mesh, 0, settings)
    body = mesh.get_editor_property('body_setup')
    if body is None:
        raise ValueError('Island mesh has no native BodySetup')
    collision = unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE
    if body.get_editor_property('collision_trace_flag') != collision:
        body.set_editor_property('collision_trace_flag', collision)
    if editor.get_simple_collision_count(mesh) or editor.get_convex_collision_count(mesh):
        if not editor.remove_collisions(mesh):
            raise ValueError('Island stale simple/convex collision removal failed')
    def validate():
        native = mesh.get_bounding_box()
        current_slots = [str(value.get_editor_property('imported_material_slot_name')) for value in mesh.static_materials]
        if (mesh.get_num_triangles(0) != receipt['triangles'] or mesh.get_num_lods() != 1
                or editor.get_simple_collision_count(mesh) != 0 or editor.get_convex_collision_count(mesh) != 0
                or editor.get_num_uv_channels(mesh, 0) != 1
                or editor.get_lod_build_settings(mesh, 0).get_editor_property('use_full_precision_u_vs')
                or current_slots != actual
                or any(mesh.get_material(i) != materials[name] for i, name in enumerate(actual))):
            raise ValueError('Island current native geometry/material/UV/collision invariant failed')
        for axis, low, high in zip(('x', 'y', 'z'), *bounds):
            if not abs(getattr(native.min, axis) - low) < .2 or not abs(getattr(native.max, axis) - high) < .2:
                raise ValueError('Island current native bounds differ from source')
        if not validator(mesh, receipt['triangles'], False):
            raise ValueError('Island native cooked complex LOD0 surface validation failed')
    validate()
    if not library.save_loaded_asset(mesh, True):
        raise ValueError('Island native package save failed')
    validate()
    return mesh
