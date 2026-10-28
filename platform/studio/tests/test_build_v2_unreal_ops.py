"""Job-body membership, input decoding and finish separation; no native admission."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier.build_v2 import unreal_ops as ops


class Asset:
    def __init__(self):
        self.properties = {}

    def set_editor_property(self, name, value):
        self.properties[name] = value

    def get_editor_property(self, name):
        return self.properties[name]


class Mesh(Asset):
    pass


class Texture(Asset):
    pass


class FakeUnreal:
    StaticMesh = Mesh
    Texture2D = Texture
    AssetImportTask = Asset

    def __init__(self, imported, decoded=None, *, saved=True):
        self.imported = imported
        self.assets = decoded if decoded is not None else {p.split('.')[0]: Texture() for p in imported}
        self.saved = []
        self.save_result = saved
        self.AssetToolsHelpers = SimpleNamespace(get_asset_tools=lambda: self)
        self.EditorAssetLibrary = SimpleNamespace(load_asset=self.assets.get, save_loaded_asset=self.save,
                                                  duplicate_asset=self.duplicate)

    def import_asset_tasks(self, tasks):
        tasks[0].properties['imported_object_paths'] = self.imported

    def save(self, asset, **kwargs):
        self.saved.append(asset)
        return self.save_result

    def duplicate(self, source, destination):
        value = type(self.assets[source])()
        self.assets[destination] = value
        return value


def context(tmp_path, **params):
    source = tmp_path / 'source.png'
    source.write_bytes(b'input decoded by native importer')
    return SimpleNamespace(job_dir=tmp_path, inputs={'source': str(source)}, packages={},
                           outputs=['/Game/Raw/T_Test'],
                           params={'op': 'raw_import', 'kind': 'texture', 'source': 'source',
                                   'destination': '/Game/Raw/T_Test', **params})


def test_import_fails_on_empty_extra_or_wrong_class_native_result(tmp_path):
    ctx = context(tmp_path)
    for result in ([], ['/Game/Else.T'], ['/Game/Raw/T_Test.T_Test', '/Game/Unexpected.A']):
        with pytest.raises(ValueError, match='different package set'):
            ops.raw_import(ctx, FakeUnreal(result))
    with pytest.raises(ValueError, match='decode expected Texture2D'):
        ops.raw_import(ctx, FakeUnreal(['/Game/Raw/T_Test.T_Test'], {'/Game/Raw/T_Test': Mesh()}))


def test_import_checks_save_failure_and_saves_only_fully_loaded_declared_set(tmp_path):
    ctx = context(tmp_path, properties={'srgb': False})
    unreal = FakeUnreal(['/Game/Raw/T_Test.T_Test'])
    asset = ops.raw_import(ctx, unreal)
    assert asset.properties == {'srgb': False}
    assert unreal.saved == [asset]
    with pytest.raises(ValueError, match='did not save'):
        ops.raw_import(ctx, FakeUnreal(['/Game/Raw/T_Test.T_Test'], saved=False))


def test_ambient_or_absent_inputs_and_undeclared_destinations_refuse(tmp_path):
    ctx = context(tmp_path)
    ctx.inputs['source'] = str(tmp_path.parent / 'outside.png')
    with pytest.raises(ValueError, match='staged regular'):
        ops.raw_import(ctx, FakeUnreal([]))
    ctx = context(tmp_path, destination='/Game/Unowned/T')
    with pytest.raises(ValueError, match='not a declared output'):
        ops.raw_import(ctx, FakeUnreal([]))
    ctx = context(tmp_path, skeleton='missing')
    with pytest.raises(ValueError, match='Non-FBX'):
        ops.raw_import(ctx, FakeUnreal([]))


def test_finish_decodes_content_and_duplicates_without_mutating_input(tmp_path):
    raw = Texture()
    ctx = SimpleNamespace(inputs={'raw': '/Game/Raw/T'}, packages={'raw': '/Game/Raw/T'},
                          outputs=['/Game/Runtime/T'], params={'op': 'finish', 'kind': 'texture',
                          'source': 'raw', 'destination': '/Game/Runtime/T', 'properties': {'srgb': False}})
    unreal = FakeUnreal([], {'/Game/Raw/T': raw})
    finished = ops.finish(ctx, unreal)
    assert raw.properties == {}
    assert finished is not raw and finished.properties == {'srgb': False}
    assert unreal.saved == [finished]
    ctx.packages = {}
    with pytest.raises(ValueError, match='package content input'):
        ops.finish(ctx, unreal)


@pytest.mark.parametrize('value', ['/Game/A/../B', '/Engine/A', '/Game/A.A', '/Game/A//B', '/Game/A\\B'])
def test_noncanonical_logical_packages_refuse(value):
    with pytest.raises(ValueError, match='canonical'):
        ops._package(value)


def test_animation_requires_a_decoded_declared_skeleton_and_disables_mesh_import(tmp_path):
    class Options(Asset):
        def __init__(self):
            super().__init__()
            self.properties['anim_sequence_import_data'] = Asset()

    class Animation(Asset):
        pass

    class Skeleton(Asset):
        pass

    source = tmp_path / 'clip.fbx'
    source.write_bytes(b'fbx source')
    ctx = context(tmp_path, kind='animation', skeleton='rig')
    ctx.inputs.update(source=str(source), rig='/Game/Raw/Skeleton')
    ctx.packages['rig'] = '/Game/Raw/Skeleton'
    skeleton = Skeleton()
    unreal = FakeUnreal(['/Game/Raw/T_Test.T_Test'], {'/Game/Raw/T_Test': Animation(), '/Game/Raw/Skeleton': skeleton})
    unreal.FbxImportUI = Options
    unreal.FBXImportType = SimpleNamespace(FBXIT_ANIMATION='animation')
    unreal.AnimSequence = Animation
    unreal.Skeleton = Skeleton
    observed = []
    original = unreal.import_asset_tasks

    def import_tasks(tasks):
        observed.append(tasks[0].properties['options'].properties)
        original(tasks)

    unreal.import_asset_tasks = import_tasks
    ops.raw_import(ctx, unreal)
    assert observed[0]['skeleton'] is skeleton
    assert observed[0]['import_mesh'] is False
    assert observed[0]['import_materials'] is False and observed[0]['import_textures'] is False
    ctx.packages.clear()
    with pytest.raises(ValueError, match='declared package content'):
        ops.raw_import(ctx, unreal)


def test_produced_mesh_item_requires_exact_receipt_membership_and_bytes(tmp_path):
    import hashlib
    import json
    root = tmp_path / 'item'
    root.mkdir()
    mesh = root / 'Tree.fbx'
    mesh.write_bytes(b'fbx')
    (root / 'export.json').write_text(json.dumps({'primary': mesh.name,
        'sha256': hashlib.sha256(mesh.read_bytes()).hexdigest()}))
    ctx = SimpleNamespace(job_dir=tmp_path, inputs={'source': str(root)}, packages={}, params={})
    assert ops._input(ctx, 'source') == str(mesh)
    mesh.write_bytes(b'changed')
    with pytest.raises(ValueError, match='bytes differ'):
        ops._input(ctx, 'source')
    (root / 'foreign').write_bytes(b'unknown')
    with pytest.raises(ValueError, match='complete export receipt'):
        ops._input(ctx, 'source')


@pytest.mark.parametrize('create', [True, False])
def test_skeletal_import_preserves_explicit_physics_creation(tmp_path, create):
    class Options(Asset):
        def __init__(self):
            super().__init__()
            self.properties['skeletal_mesh_import_data'] = Asset()
    class Skeletal(Asset):
        pass
    source = tmp_path / 'mesh.fbx'
    source.write_bytes(b'fbx')
    ctx = context(tmp_path, kind='skeletal_mesh', create_physics_asset=create)
    ctx.inputs['source'] = str(source)
    unreal = FakeUnreal(['/Game/Raw/T_Test.T_Test'], {'/Game/Raw/T_Test': Skeletal()})
    unreal.FbxImportUI = Options
    unreal.FBXImportType = SimpleNamespace(FBXIT_SKELETAL_MESH='skeletal')
    unreal.SkeletalMesh = Skeletal
    captured = []
    original = unreal.import_asset_tasks
    def importing(tasks):
        captured.append(tasks[0].properties['options'].properties['create_physics_asset'])
        original(tasks)
    unreal.import_asset_tasks = importing
    ops.raw_import(ctx, unreal)
    assert captured == [create]
    ctx.params['create_physics_asset'] = 1
    with pytest.raises(ValueError, match='skeletal-only boolean'):
        ops.raw_import(ctx, unreal)


def test_original_fbx_enum_properties_are_explicit_tokens(monkeypatch):
    import sys
    fake = SimpleNamespace(FBXNormalImportMethod=SimpleNamespace(FBXNIM_IMPORT_NORMALS=object()),
        VertexColorImportOption=SimpleNamespace(REPLACE=object()),
        FBXAnimationLengthImportType=SimpleNamespace(FBXALIT_EXPORTED_TIME=object()))
    monkeypatch.setitem(sys.modules, 'unreal', fake)
    for owner, member in [('FBXNormalImportMethod', 'FBXNIM_IMPORT_NORMALS'),
                          ('VertexColorImportOption', 'REPLACE'),
                          ('FBXAnimationLengthImportType', 'FBXALIT_EXPORTED_TIME')]:
        assert ops._editor_value({'unreal_enum': owner + '.' + member}) is getattr(getattr(fake, owner), member)
    with pytest.raises(ValueError, match='Unsupported authored Unreal enum'):
        ops._editor_value({'unreal_enum': 'Foreign.RUN'})


def test_raw_source_member_selects_only_the_explicit_declared_file(tmp_path):
    root = tmp_path / 'textures'
    root.mkdir()
    (root / 'chosen.png').write_bytes(b'pixel data')
    (root / 'other.png').write_bytes(b'other pixels')
    ctx = context(tmp_path, source_member='chosen.png')
    ctx.inputs['source'] = str(root)
    assert ops._input(ctx, 'source') == str(root / 'chosen.png')
    for member in ('../source.png', '/source.png', './chosen.png', 'missing.png'):
        ctx.params['source_member'] = member
        with pytest.raises(ValueError):
            ops._input(ctx, 'source')
    (root / 'linked.png').symlink_to(root / 'chosen.png')
    ctx.params['source_member'] = 'linked.png'
    with pytest.raises(ValueError, match='alias'):
        ops._input(ctx, 'source')


def glb(path, document):
    import json
    import struct
    payload = json.dumps({'asset': {'version': '2.0'}, **document}).encode()
    payload += b' ' * (-len(payload) % 4)
    path.write_bytes(struct.pack('<4sIII4s', b'glTF', 2, 20 + len(payload), len(payload), b'JSON') + payload)


@pytest.fixture
def gltf_native():
    class Skin(Asset):
        pass
    class Skeleton(Asset):
        pass
    class Animation(Asset):
        pass
    class Pipeline(Asset):
        def __init__(self):
            super().__init__()
            self.properties.update({key: Asset() for key in ('material_pipeline', 'mesh_pipeline',
                'common_skeletal_meshes_and_animations_properties', 'animation_pipeline')})
            self.properties['material_pipeline'].properties['texture_pipeline'] = Asset()
    class Stack:
        def __init__(self):
            self.pipelines = []
        def add_pipeline(self, pipeline):
            self.pipelines.append(pipeline)
    unreal = FakeUnreal([])
    unreal.SkeletalMesh, unreal.Skeleton, unreal.AnimSequence = Skin, Skeleton, Animation
    unreal.InterchangeGenericAssetsPipeline = Pipeline
    unreal.InterchangePipelineStackOverride = Stack
    unreal.InterchangeGLTFPipeline = Asset
    unreal.InterchangeCombineSkeletalMeshesBehavior = SimpleNamespace(BY_SKELETON='by_skeleton')
    unreal.tasks = []
    def execute(tasks):
        unreal.tasks.extend(tasks)
        tasks[0].properties['imported_object_paths'] = unreal.imported
    unreal.import_asset_tasks = execute
    return unreal


@pytest.mark.parametrize('kind', ['skeletal_mesh', 'animation'])
def test_selected_glb_skin_roles_keep_exact_products_and_disable_other_native_factories(tmp_path, gltf_native, kind):
    source = tmp_path / 'selected.glb'
    glb(source, {'animations': [{'name': 'T_Test'}]} if kind == 'animation' else {})
    ctx = context(tmp_path, kind=kind, **({'skeleton': 'rig'} if kind == 'animation' else {'create_physics_asset': False}))
    ctx.inputs['source'] = str(source)
    unreal = gltf_native
    asset = unreal.AnimSequence() if kind == 'animation' else unreal.SkeletalMesh()
    unreal.assets['/Game/Raw/T_Test'] = asset
    ctx.outputs = ['/Game/Raw/T_Test']
    if kind == 'skeletal_mesh':
        ctx.outputs.append('/Game/Raw/T_Test_Skeleton')
        unreal.assets[ctx.outputs[-1]] = unreal.Skeleton()
    else:
        ctx.inputs['rig'] = '/Game/Rig/Skeleton'
        ctx.packages['rig'] = '/Game/Rig/Skeleton'
        unreal.assets[ctx.inputs['rig']] = unreal.Skeleton()
    unreal.imported = [path + '.' + path.rsplit('/', 1)[-1] for path in ctx.outputs]
    assert ops.raw_import(ctx, unreal) is asset
    task, = unreal.tasks
    pipeline = task.properties['options'].pipelines[0]
    material = pipeline.properties['material_pipeline']
    assert material.properties['import_materials'] is False
    assert material.properties['texture_pipeline'].properties['import_textures'] is False
    mesh = pipeline.properties['mesh_pipeline'].properties
    assert mesh['import_static_meshes'] is False and mesh['create_physics_asset'] is False
    assert mesh['import_skeletal_meshes'] is (kind == 'skeletal_mesh')
    common = pipeline.properties['common_skeletal_meshes_and_animations_properties'].properties
    assert common['import_only_animations'] is (kind == 'animation')
    assert common['add_curve_metadata_to_skeleton'] is False
    if kind == 'animation':
        assert common['skeleton'] is unreal.assets['/Game/Rig/Skeleton']
        assert task.properties['destination_name'] == ''
    assert len(unreal.saved) == len(ctx.outputs)


@pytest.mark.parametrize('document,kind', [
    ({'buffers': [{'uri': '../outside.bin'}]}, 'skeletal_mesh'),
    ({'images': [{'uri': 'https://example.invalid/image.png'}]}, 'skeletal_mesh'),
    ({'animations': [{'name': 'Other'}]}, 'animation'),
    ({'animations': [{'name': 'T_Test'}, {'name': 'Other'}]}, 'animation'),
    ({'animations': [{'name': 'T_Test'}]}, 'skeletal_mesh'),
])
def test_glb_skin_external_bytes_or_unselected_clips_refuse_before_any_native_import(tmp_path, gltf_native, document, kind):
    source = tmp_path / 'selected.glb'; glb(source, document)
    ctx = context(tmp_path, kind=kind, skeleton='rig')
    ctx.inputs['source'] = str(source)
    with pytest.raises(ValueError):
        ops.raw_import(ctx, gltf_native)
    assert gltf_native.tasks == []
