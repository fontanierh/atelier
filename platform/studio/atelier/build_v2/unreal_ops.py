"""Bounded Unreal job bodies for the existing scratch-project worker.

Declare this file as a job's entry script and project code. ``params.op`` selects
``raw_import`` or ``finish``; the controller owns keys, dependencies, admission,
output inventory and installation. These bodies never invoke a build scheduler.
"""
import hashlib
import json
from pathlib import Path
import re
import sys


_PACKAGE = re.compile(r'/Game/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+\Z')
_KINDS = {'static_mesh': 'StaticMesh', 'skeletal_mesh': 'SkeletalMesh',
          'animation': 'AnimSequence', 'texture': 'Texture2D', 'sound': 'SoundWave'}


def _fields(value, required, optional=()):
    if not isinstance(value, dict) or set(value) - set(required) - set(optional) or set(required) - set(value):
        raise ValueError('Missing or unknown Unreal operation parameters')


def _package(value):
    if not isinstance(value, str) or not _PACKAGE.fullmatch(value):
        raise ValueError('Expected a canonical /Game package path')
    return value


def _input(context, name, *, package=False):
    if not isinstance(name, str) or name not in context.inputs or context.inputs[name] is None:
        raise ValueError('Missing declared Unreal input')
    value = context.inputs[name]
    if package:
        packages = context.packages.get(name)
        if isinstance(packages, str):
            packages = [packages]
        if not packages:
            raise ValueError('Expected a declared package content input')
        selected = context.params.get('package_sources', {}).get(name)
        if selected is None and len(packages) == 1:
            selected = packages[0]
        if selected not in packages:
            raise ValueError('Package selection must name exactly one declared package content input')
        return _package(selected)
    path = Path(value)
    if not path.is_absolute() or not path.is_relative_to(Path(context.job_dir)):
        raise ValueError('Expected a staged regular source input')
    member = context.params.get('source_member') if name == context.params.get('source') else None
    if member is not None:
        if (not isinstance(member, str) or not member or Path(member).is_absolute() or '\\' in member
                or any(part in ('', '.', '..') for part in member.split('/')) or not path.is_dir()):
            raise ValueError('Source member requires an exact relative member of a declared directory')
        selected = path.joinpath(*member.split('/'))
        if selected.resolve() != selected or not selected.is_relative_to(path) or selected.is_symlink():
            raise ValueError('Source member traverses an alias')
        path = selected
    if path.is_dir():
        # A produced source Item is a complete source file + original public
        # export receipt, never a guessed first member of a directory.
        receipt_path = path / 'export.json'
        if receipt_path.is_symlink() or not receipt_path.is_file():
            raise ValueError('Source Item has no regular export receipt')
        receipt = json.loads(receipt_path.read_bytes())
        primary = receipt.get('primary')
        if (not isinstance(primary, str) or Path(primary).name != primary
                or sorted(member.name for member in path.iterdir()) != sorted([primary, 'export.json'])):
            raise ValueError('Source Item differs from its complete export receipt')
        path = path / primary
        if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
            raise ValueError('Source Item member is linked or missing')
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != receipt.get('sha256'):
            raise ValueError('Source Item bytes differ from its export receipt')
    if path.is_symlink() or not path.is_file():
        raise ValueError('Expected a staged regular source input')
    return str(path)


def _output(context, value):
    value = _package(value)
    if value not in context.outputs:
        raise ValueError('Operation destination is not a declared output package')
    return value


def _editor_value(value):
    if isinstance(value, dict) and set(value) == {'unreal_type', 'args'}:
        import unreal
        if value['unreal_type'] not in ('Vector4', 'Vector', 'LinearColor') or not isinstance(value['args'], list):
            raise ValueError('Unsupported authored Unreal property type')
        return getattr(unreal, value['unreal_type'])(*value['args'])
    if isinstance(value, dict) and set(value) == {'unreal_enum'}:
        import unreal
        owner, separator, member = value['unreal_enum'].partition('.')
        if not separator or owner not in ('TextureMipGenSettings', 'TextureGroup', 'CollisionTraceFlag', 'FBXNormalImportMethod',
                                     'VertexColorImportOption', 'FBXAnimationLengthImportType'):
            raise ValueError('Unsupported authored Unreal enum')
        return getattr(getattr(unreal, owner), member)
    return value


def _set(target, values):
    if not isinstance(values, dict):
        raise ValueError('Expected explicit editor properties')
    for name, value in values.items():
        if not isinstance(name, str) or not re.fullmatch('[a-z][a-z0-9_]*', name):
            raise ValueError('Invalid editor property name')
        target.set_editor_property(name, _editor_value(value))


def _load(unreal, package, kind=None):
    asset = unreal.EditorAssetLibrary.load_asset(package)
    if asset is None or (kind is not None and not isinstance(asset, getattr(unreal, kind))):
        raise ValueError(f'Could not decode expected {kind or "asset"} package {package}')
    return asset


def _save(unreal, asset):
    if not unreal.EditorAssetLibrary.save_loaded_asset(asset, only_if_is_dirty=False):
        raise ValueError('Unreal did not save the produced asset')


def _gltf_skin_options(context, unreal, task, source, destination, kind):
    """@cc [owner:fontanierh,label:correctness] selected-gltf-skinned-raw-import
    GLB skin imports MUST disable material/texture production. A mesh source MUST
    contain no animation; an animation source MUST contain exactly its named clip
    and use one declared immutable Skeleton, with mesh/physics production disabled.
    Every URI MUST be embedded, and the ordinary complete native product/save checks
    MUST still run. No rename, namespace scan or input Skeleton mutation is permitted.
    """
    import json
    import struct
    data = Path(source).read_bytes()
    if (len(data) < 20 or data[:4] != b'glTF'
            or struct.unpack_from('<II', data, 4) != (2, len(data))):
        raise ValueError('Skinned GLTF import requires a complete GLB2 source')
    size, tag = struct.unpack_from('<I4s', data, 12)
    if tag != b'JSON' or size > len(data) - 20:
        raise ValueError('Skinned GLTF source has no complete JSON chunk')
    document = json.loads(data[20:20 + size])
    def embedded(value):
        if isinstance(value, dict):
            if 'uri' in value and (not isinstance(value['uri'], str) or not value['uri'].startswith('data:')):
                raise ValueError('Skinned GLTF source requires embedded resource bytes')
            for child in value.values():
                embedded(child)
        elif isinstance(value, list):
            for child in value:
                embedded(child)
    embedded(document)
    name = destination.rsplit('/', 1)[-1]
    animations = document.get('animations', [])
    if (not isinstance(animations, list) or (kind == 'skeletal_mesh' and animations)
            or (kind == 'animation' and (len(animations) != 1 or animations[0].get('name') != name))):
        raise ValueError('Skinned GLTF source must select only its declared mesh or named animation')
    p = context.params
    if 'fbx' in p or 'physics_asset' in p:
        raise ValueError('Skinned GLTF import does not accept FBX or supplied physics settings')
    if kind == 'animation' and 'skeleton' not in p:
        raise ValueError('GLTF animation requires a declared skeleton content input')
    generic = unreal.InterchangeGenericAssetsPipeline()
    generic.set_editor_property('asset_name', name if kind == 'skeletal_mesh' else '')
    generic.set_editor_property('use_source_name_for_asset', kind == 'skeletal_mesh')
    material = generic.get_editor_property('material_pipeline')
    material.set_editor_property('import_materials', False)
    material.get_editor_property('texture_pipeline').set_editor_property('import_textures', False)
    mesh = generic.get_editor_property('mesh_pipeline')
    mesh.set_editor_property('import_static_meshes', False)
    mesh.set_editor_property('import_skeletal_meshes', kind == 'skeletal_mesh')
    mesh.set_editor_property('import_morph_targets', False)
    mesh.set_editor_property('create_physics_asset', p.get('create_physics_asset', False) if kind == 'skeletal_mesh' else False)
    mesh.set_editor_property('combine_skeletal_meshes_behavior', unreal.InterchangeCombineSkeletalMeshesBehavior.BY_SKELETON)
    common = generic.get_editor_property('common_skeletal_meshes_and_animations_properties')
    common.set_editor_property('import_only_animations', kind == 'animation')
    common.set_editor_property('try_auto_select_skeleton', False)
    common.set_editor_property('add_curve_metadata_to_skeleton', False)
    if 'skeleton' in p:
        common.set_editor_property('skeleton', _load(unreal, _input(context, p['skeleton'], package=True), 'Skeleton'))
    animation = generic.get_editor_property('animation_pipeline')
    animation.set_editor_property('import_animations', kind == 'animation')
    animation.set_editor_property('use30_hz_to_bake_bone_animation', True)
    stack = unreal.InterchangePipelineStackOverride()
    stack.add_pipeline(generic)
    stack.add_pipeline(unreal.InterchangeGLTFPipeline())
    if kind == 'animation':
        # Preserve the selected animation's exact GLTF name, without SDK source-name prefixing.
        task.set_editor_property('destination_name', '')
    task.set_editor_property('options', stack)


def raw_import(context, unreal):
    """@cc [owner:fontanierh,label:correctness] v2-bounded-unreal-raw-import
    One job MUST import one declared source item, use only declared package content
    inputs for skeleton/physics references, and check the fully loaded output class
    and complete imported package membership before returning. Import materials and
    textures MUST stay disabled for FBX and selected skinned GLB imports. The worker separately verifies all package
    saves, required output files, import tables and scratch cleanup before Completed.
    """
    p = context.params
    _fields(p, {'op', 'kind', 'source', 'destination'}, {'properties', 'fbx', 'skeleton', 'physics_asset', 'create_physics_asset', 'source_member', 'package_sources', 'input_roots'})
    kind = p['kind']
    if kind not in _KINDS:
        raise ValueError('Unsupported raw import kind')
    if 'create_physics_asset' in p and (kind != 'skeletal_mesh' or type(p['create_physics_asset']) is not bool
                                      or 'physics_asset' in p):
        raise ValueError('Explicit physics creation is a skeletal-only boolean without a supplied physics asset')
    source = _input(context, p['source'])
    destination = _output(context, p['destination'])
    folder, _, name = destination.rpartition('/')
    task = unreal.AssetImportTask()
    _set(task, {'filename': source, 'destination_path': folder, 'destination_name': name,
                'automated': True, 'replace_existing': False, 'save': False})
    if kind == 'static_mesh' and Path(source).suffix.lower() in ('.glb', '.gltf'):
        if any(field in p for field in ('fbx', 'skeleton', 'physics_asset')) or context.outputs != [destination]:
            raise ValueError('Geometry-only GLTF import owns exactly one mesh package')
        sys.path.insert(0, str(Path(context.job_dir) / 'platform/studio'))
        from atelier.interchange_mesh import import_static_mesh
        asset = import_static_mesh(source, folder, name)
        _set(asset, p.get('properties', {}))
        _save(unreal, asset)
        return _load(unreal, destination, 'StaticMesh')
    if kind in ('skeletal_mesh', 'animation') and Path(source).suffix.lower() == '.glb':
        _gltf_skin_options(context, unreal, task, source, destination, kind)
    elif kind in ('static_mesh', 'skeletal_mesh', 'animation'):
        if Path(source).suffix.lower() != '.fbx':
            raise ValueError('The FBX import operation requires FBX bytes')
        options = unreal.FbxImportUI()
        _set(options, {'automated_import_should_detect_type': False, 'import_materials': False,
                       'import_textures': False, 'import_mesh': kind != 'animation',
                       'import_as_skeletal': kind != 'static_mesh', 'import_animations': kind == 'animation',
                       'mesh_type_to_import': getattr(unreal.FBXImportType, {
                           'static_mesh': 'FBXIT_STATIC_MESH', 'skeletal_mesh': 'FBXIT_SKELETAL_MESH',
                           'animation': 'FBXIT_ANIMATION'}[kind])})
        if kind == 'animation':
            if 'skeleton' not in p:
                raise ValueError('Animation imports require a declared skeleton content input')
            _set(options, {'skeleton': _load(unreal, _input(context, p['skeleton'], package=True), 'Skeleton')})
        elif 'skeleton' in p:
            if kind != 'skeletal_mesh':
                raise ValueError('Only skeletal imports accept a skeleton')
            _set(options, {'skeleton': _load(unreal, _input(context, p['skeleton'], package=True), 'Skeleton')})
        if 'physics_asset' in p:
            if kind != 'skeletal_mesh':
                raise ValueError('Only skeletal imports accept a physics asset')
            _set(options, {'create_physics_asset': False,
                           'physics_asset': _load(unreal, _input(context, p['physics_asset'], package=True), 'PhysicsAsset')})
        elif kind == 'skeletal_mesh':
            _set(options, {'create_physics_asset': p.get('create_physics_asset', True)})
        data = options.get_editor_property({'static_mesh': 'static_mesh_import_data',
                                           'skeletal_mesh': 'skeletal_mesh_import_data',
                                           'animation': 'anim_sequence_import_data'}[kind])
        if kind == 'static_mesh':
            _set(data, {'combine_meshes': True, 'generate_lightmap_u_vs': False,
                        'auto_generate_collision': False, 'convert_scene': True,
                        'convert_scene_unit': True, 'import_uniform_scale': 1.0,
                        'build_nanite': False, 'one_convex_hull_per_ucx': True,
                        'vertex_color_import_option': unreal.VertexColorImportOption.REPLACE,
                        'normal_import_method': unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS})
        _set(data, p.get('fbx', {}))
        _set(task, {'options': options})
    elif any(field in p for field in ('fbx', 'skeleton', 'physics_asset')):
        raise ValueError('Non-FBX imports do not accept FBX parameters')
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    imported = task.get_editor_property('imported_object_paths')
    actual = {str(path).split('.', 1)[0] for path in imported}
    if destination not in actual or actual != set(context.outputs):
        raise ValueError(f'Importer produced a different package set: {sorted(actual)}')
    asset = _load(unreal, destination, _KINDS[kind])
    _set(asset, p.get('properties', {}))
    # Fully decode the complete set (skeletal mesh, skeleton and physics asset are
    # one item) before any successful terminal response. Never invent sidecars.
    for package in sorted(actual):
        produced = _load(unreal, package)
        _save(unreal, produced)
    return asset


def finish(context, unreal):
    """Finish one asset by duplicating its raw content input to its runtime path.

    Input and output paths differ deliberately: C3 keeps input packages read-only.
    Material slots and parent references are declared *content* package inputs.
    """
    p = context.params
    _fields(p, {'op', 'source', 'destination', 'kind'}, {'properties', 'materials', 'lod_build_settings', 'package_sources', 'partners', 'input_roots'})
    if p['kind'] not in _KINDS:
        raise ValueError('Unsupported finish kind')
    source = _input(context, p['source'], package=True)
    destination = _output(context, p['destination'])
    partners = p.get('partners', {})
    if not isinstance(partners, dict) or set(partners) - {'skeleton', 'physics_asset'}:
        raise ValueError('Unknown skeletal finish partner')
    if partners and p['kind'] != 'skeletal_mesh':
        raise ValueError('Only skeletal finish accepts partner packages')
    owned = {destination, *(_output(context, value) for value in partners.values())}
    if set(context.outputs) != owned or source in owned:
        raise ValueError('Finish owns exactly its fresh destination package bundle')
    raw = _load(unreal, source, _KINDS[p['kind']])
    asset = unreal.EditorAssetLibrary.duplicate_asset(source, destination)
    if asset is None or not isinstance(asset, type(raw)):
        raise ValueError('Could not duplicate the raw asset')
    for role, target in partners.items():
        property_name = 'skeleton' if role == 'skeleton' else 'physics_asset'
        raw_partner = raw.get_editor_property(property_name)
        if raw_partner is None:
            raise ValueError('Missing skeletal source partner')
        original_path = str(raw_partner.get_path_name()).split('.', 1)[0]
        declared_packages = {value for values in context.packages.values()
                             for value in ([values] if isinstance(values, str) else values)}
        if original_path not in declared_packages:
            raise ValueError('Skeletal source partner is not a declared content input')
        partner = unreal.EditorAssetLibrary.duplicate_asset(original_path, _output(context, target))
        expected = 'Skeleton' if role == 'skeleton' else 'PhysicsAsset'
        if partner is None or not isinstance(partner, getattr(unreal, expected)):
            raise ValueError('Could not duplicate skeletal partner')
        asset.set_editor_property(property_name, partner)
        partner.set_editor_property('preview_skeletal_mesh', asset)
        _save(unreal, partner)
    if p['kind'] == 'skeletal_mesh':
        for role in ('skeleton', 'physics_asset'):
            value = raw.get_editor_property(role)
            if value is not None and role not in partners:
                raise ValueError('Skeletal finish must own every mutable raw partner')
    _set(asset, p.get('properties', {}))
    if 'materials' in p:
        if p['kind'] != 'static_mesh' or not isinstance(p['materials'], list):
            raise ValueError('Material slots require a static mesh and an ordered input list')
        if len(asset.get_editor_property('static_materials')) != len(p['materials']):
            raise ValueError('Material input count differs from the imported slot count')
        for index, name in enumerate(p['materials']):
            material = _load(unreal, _input(context, name, package=True), 'MaterialInterface')
            asset.set_material(index, material)
    if 'lod_build_settings' in p:
        settings = p['lod_build_settings']
        if p['kind'] != 'static_mesh' or not isinstance(settings, list) or len(settings) != asset.get_num_lods():
            raise ValueError('Build settings must cover exactly the static mesh LODs')
        editor = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
        for index, properties in enumerate(settings):
            value = editor.get_lod_build_settings(asset, index)
            _set(value, properties)
            editor.set_lod_build_settings(asset, index, value)
    _save(unreal, asset)
    _load(unreal, destination, _KINDS[p['kind']])
    return asset


def run(context):
    import unreal
    operations = {'raw_import': raw_import, 'finish': finish}
    if not isinstance(context.params, dict) or context.params.get('op') not in operations:
        raise ValueError('Unsupported Unreal operation')
    operations[context.params['op']](context, unreal)
