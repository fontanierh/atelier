"""Bounded Unreal job bodies for the existing scratch-project worker.

Declare this file as a job's entry script and project code. ``params.op`` selects
``raw_import`` or ``finish``; the controller owns keys, dependencies, admission,
output inventory and installation. These bodies never invoke a build scheduler.
"""
from pathlib import Path
import re


_PACKAGE = re.compile(r'/Game/(?:[A-Za-z0-9_]+/)*[A-Za-z0-9_]+\Z')
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
        if context.packages.get(name) != value:
            raise ValueError('Expected a declared package content input')
        return _package(value)
    path = Path(value)
    if not path.is_absolute() or not path.is_relative_to(Path(context.job_dir)) or not path.is_file():
        raise ValueError('Expected a staged regular source input')
    return str(path)


def _output(context, value):
    value = _package(value)
    if value not in context.outputs:
        raise ValueError('Operation destination is not a declared output package')
    return value


def _set(target, values):
    if not isinstance(values, dict):
        raise ValueError('Expected explicit editor properties')
    for name, value in values.items():
        if not isinstance(name, str) or not re.fullmatch('[a-z][a-z0-9_]*', name):
            raise ValueError('Invalid editor property name')
        target.set_editor_property(name, value)


def _load(unreal, package, kind=None):
    asset = unreal.EditorAssetLibrary.load_asset(package)
    if asset is None or (kind is not None and not isinstance(asset, getattr(unreal, kind))):
        raise ValueError(f'Could not decode expected {kind or "asset"} package {package}')
    return asset


def _save(unreal, asset):
    if not unreal.EditorAssetLibrary.save_loaded_asset(asset, only_if_is_dirty=False):
        raise ValueError('Unreal did not save the produced asset')


def raw_import(context, unreal):
    """@cc [owner:fontanierh,label:correctness] v2-bounded-unreal-raw-import
    One job MUST import one declared source item, use only declared package content
    inputs for skeleton/physics references, and check the fully loaded output class
    and complete imported package membership before returning. Import materials and
    textures MUST stay disabled for FBX. The worker separately verifies all package
    saves, required output files, import tables and scratch cleanup before Completed.
    """
    p = context.params
    _fields(p, {'op', 'kind', 'source', 'destination'}, {'properties', 'fbx', 'skeleton', 'physics_asset'})
    kind = p['kind']
    if kind not in _KINDS:
        raise ValueError('Unsupported raw import kind')
    source = _input(context, p['source'])
    destination = _output(context, p['destination'])
    folder, _, name = destination.rpartition('/')
    task = unreal.AssetImportTask()
    _set(task, {'filename': source, 'destination_path': folder, 'destination_name': name,
                'automated': True, 'replace_existing': False, 'save': False})
    if kind in ('static_mesh', 'skeletal_mesh', 'animation'):
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
            _set(options, {'create_physics_asset': True})
        data = options.get_editor_property({'static_mesh': 'static_mesh_import_data',
                                           'skeletal_mesh': 'skeletal_mesh_import_data',
                                           'animation': 'anim_sequence_import_data'}[kind])
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
    _fields(p, {'op', 'source', 'destination', 'kind'}, {'properties', 'materials', 'lod_build_settings'})
    if p['kind'] not in _KINDS:
        raise ValueError('Unsupported finish kind')
    source = _input(context, p['source'], package=True)
    destination = _output(context, p['destination'])
    if context.outputs != [destination] or source == destination:
        raise ValueError('Finish owns exactly one fresh destination package')
    raw = _load(unreal, source, _KINDS[p['kind']])
    asset = unreal.EditorAssetLibrary.duplicate_asset(source, destination)
    if asset is None or not isinstance(asset, type(raw)):
        raise ValueError('Could not duplicate the raw asset')
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
