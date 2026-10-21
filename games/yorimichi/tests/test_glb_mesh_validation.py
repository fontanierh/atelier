"""Historical GLB checks refuse drift without importing or changing an asset."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / 'unreal/Scripts'


class Properties:
    def __init__(self, **values): self.values = values
    def get_editor_property(self, name): return self.values[name]
    def set_editor_property(self, name, value): self.values[name] = value


@pytest.fixture
def scene(tmp_path, monkeypatch):
    class Generic(Properties):
        def __init__(self):
            super().__init__(mesh_pipeline=Properties(), animation_pipeline=Properties(),
                import_offset_translation=NS(x=0, y=0, z=0),
                import_offset_rotation=NS(pitch=0, yaw=0, roll=0), import_offset_uniform_scale=1.)
    class GLTF: pass
    class Data:
        def script_extract_filenames(self): return self.names
        def get_pipelines(self): return self.pipelines
    class Stack:
        def __init__(self): self.pipelines = []
        def add_pipeline(self, item): self.pipelines.append(item)
    source = tmp_path / 'repo/build/yorimichi/brinecove/glb/a.glb'
    source.parent.mkdir(parents=True); source.write_bytes(b'mesh')
    out = tmp_path / 'repo/build/yorimichi'
    data = Data(); data.names = [str(source)]
    generic = Generic()
    generic.values['mesh_pipeline'].values.update(import_static_meshes=True, import_skeletal_meshes=False,
                                                 combine_static_meshes_behavior='all', build_nanite=False)
    generic.values['animation_pipeline'].values['import_animations'] = False
    data.pipelines = [generic, GLTF()]
    box = NS(min=NS(x=0, y=-100, z=0), max=NS(x=100, y=0, z=100))
    mesh = Properties(asset_import_data=data, static_materials=[object()])
    mesh.get_num_triangles = lambda _: 100
    mesh.get_bounding_box = lambda: box
    tag = [dict(FileMD5=hashlib.md5(source.read_bytes()).hexdigest())]
    unreal = NS(InterchangeAssetImportData=Data, InterchangeGenericAssetsPipeline=Generic,
        InterchangeGLTFPipeline=GLTF, InterchangePipelineStackOverride=Stack, AssetImportTask=NS,
        InterchangeCombineStaticMeshesBehavior=NS(ALL='all'),
        AssetRegistryHelpers=NS(create_asset_data=lambda _: NS(get_tag_value=lambda _: json.dumps(tag))))
    monkeypatch.setitem(sys.modules, 'unreal', unreal)
    spec = importlib.util.spec_from_file_location('glb_mesh_validation', SCRIPTS/'glb_mesh_validation.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    monkeypatch.setitem(sys.modules, 'glb_mesh_validation', module)
    entry = dict(triangles=100, bounds_m=[[0, 0, 0], [1, 1, 1]])
    def valid():
        return module.validate_mesh(mesh, source, entry, 1, out=out, tolerance_cm=2., minimum_triangles=.98)
    return NS(module=module, mesh=mesh, source=source, out=out, data=data, generic=generic,
              tag=tag, entry=entry, valid=valid, unreal=unreal)


def test_current_and_relocated_product_are_read_only_matches(scene):
    assert scene.valid()
    scene.data.names = ['/another/checkout/build/yorimichi/brinecove/glb/a.glb']
    assert scene.valid()
    assert scene.mesh.values['asset_import_data'] is scene.data


@pytest.mark.parametrize('name', [
    '/another/yorimichi/brinecove/glb/b.glb', '/another/yorimichi/belmonte/glb/a.glb',
    '/another/yorimichi/brinecove/xglb/a.glb', '/another/yorimichi/xbrinecove/glb/a.glb',
    '/another/yorimichi/brinecove/../brinecove/glb/a.glb',
    '/another/yorimichi/brinecove//glb/a.glb', 'yorimichi/brinecove/glb/a.glb'])
def test_path_mismatch_with_identical_hash_misses(scene, name):
    scene.data.names = [name]
    assert not scene.valid()


@pytest.mark.parametrize('relocated', [False, True])
def test_recorded_hash_is_required_even_with_matching_path(scene, relocated):
    if relocated: scene.data.names = ['/another/yorimichi/brinecove/glb/a.glb']
    scene.tag[0]['FileMD5'] = '1'*32
    assert not scene.valid()


@pytest.mark.parametrize('defect', ['options', 'triangles', 'slots', 'bounds', 'missing', 'raises', 'pipeline', 'transform'])
def test_each_unproved_mesh_is_a_miss(scene, defect):
    if defect == 'options': scene.generic.values['mesh_pipeline'].values['build_nanite'] = True
    if defect == 'triangles': scene.mesh.get_num_triangles = lambda _: 97
    if defect == 'slots': scene.mesh.values['static_materials'] = []
    if defect == 'bounds': scene.entry['bounds_m'][1][0] += .03
    if defect == 'missing': del scene.mesh.values['asset_import_data']
    if defect == 'raises': scene.mesh.get_num_triangles = lambda _: 1/0
    if defect == 'pipeline': scene.data.pipelines.reverse()
    if defect == 'transform': scene.generic.values['import_offset_uniform_scale'] = 2.
    assert not scene.valid()


@pytest.mark.parametrize('script', ['import_belmonte.py', 'import_brinecove.py'])
def test_validator_options_equal_every_raw_import_setter(scene, script):
    """Execute the unchanged raw importer; a new/changed/removed option fails CI."""
    nodes = [n for n in ast.parse((SCRIPTS/script).read_text()).body
             if isinstance(n, ast.FunctionDef) and n.name == 'import_mesh']
    tasks = []
    namespace = dict(unreal=scene.unreal, ROOT='/Game/Test',
        AT=NS(import_asset_tasks=lambda items: tasks.extend(items)),
        REGISTRY=NS(get_assets_by_path=lambda *a, **k: [NS(package_name='/Game/Temp', asset_class_path=NS(asset_name='StaticMesh'))]),
        E=NS(rename_asset=lambda *a: True, load_asset=lambda _: scene.mesh))
    exec(compile(ast.Module(body=nodes, type_ignores=[]), script, 'exec'), namespace)
    assert namespace['import_mesh'](scene.source, 'Mesh') is scene.mesh
    generic, gltf = tasks[0].options.pipelines
    assert isinstance(gltf, scene.unreal.InterchangeGLTFPipeline)
    expected = dict(scene.module.MESH_OPTIONS, combine_static_meshes_behavior=scene.unreal.InterchangeCombineStaticMeshesBehavior.ALL)
    assert generic.values['mesh_pipeline'].values == expected
    assert generic.values['animation_pipeline'].values == scene.module.ANIMATION_OPTIONS


def test_invalid_hull_refuses_whole_belmonte_group(scene):
    script = SCRIPTS/'import_belmonte.py'
    nodes = [n for n in ast.parse(script.read_text()).body if isinstance(n, ast.FunctionDef) and n.name == 'validate_reused_mesh']
    calls = []
    helper = NS(validate_mesh=lambda mesh, *a, **k: calls.append(mesh) or mesh is scene.mesh,
                collision_entry=lambda _: (scene.entry, 1))
    namespace = dict(glb_mesh_validation=helper, OUT=scene.source.parent, Path=Path,
        yori=NS(OUT=scene.out), ROOT='/Game/Belmonte', E=NS(load_asset=lambda _: object()))
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(script), 'exec'), namespace)
    entry = dict(scene.entry, path='a.glb', name='Mesh', collision={'path':'hull.glb'})
    assert not namespace['validate_reused_mesh'](scene.mesh, entry, 1)
    assert len(calls) == 2


@pytest.mark.parametrize('defect', [None, 'changed_package', 'source', 'option', 'triangles', 'bounds', 'dirty', 'exception'])
def test_pre_receipt_warm_game_validator_and_success_only_publication(scene, monkeypatch, defect):
    """The real native adapter uses this GLB callback on old whole-task evidence."""
    import time
    from atelier import mesh_reuse, native_candidates, native_protocol, paths
    from atelier import unreal_mesh_reuse as native
    repo = scene.out.parents[1]
    monkeypatch.setattr(paths, 'REPO', repo)
    script = repo/'import.py'; script.write_text('def build(): return 1\ndef validate(mesh): return bool(mesh)\n')
    ctx = NS(out=scene.out, uproject=repo/'games/yorimichi/unreal/Game.uproject', game='yorimichi')
    package = '/Game/Region/Mesh'
    saved = ctx.uproject.parent/'Content/Region/Mesh.uasset'
    saved.parent.mkdir(parents=True); saved.write_bytes(b'previous completed mesh')
    old = dict(time=time.time(), fingerprint='a'*64, input_state={'inputs':{'<repo>/import.py':'b'*64}})
    monkeypatch.setattr(mesh_reuse, 'prior_stamp', lambda *a: old)
    monkeypatch.setattr(mesh_reuse, 'saved_source', lambda *a: 'def build(): return 1\n')
    monkeypatch.setattr(native, 'observed_environment', lambda *a: True)
    monkeypatch.setattr(native_candidates, 'load', lambda *a: None)
    monkeypatch.setattr(native, 'context', lambda _: {'engine':'observed'})
    monkeypatch.setattr(native_protocol, 'context', lambda _: {'engine':'observed'})
    monkeypatch.setenv('ATELIER_MESH_REUSE_NONCE', 'e'*24)
    scene.unreal.EditorAssetLibrary = NS(does_asset_exist=lambda _: True)
    scene.unreal.EditorLoadingAndSavingUtils = NS(get_dirty_content_packages=lambda: [])
    scene.unreal.load_asset = lambda _: scene.mesh
    if defect == 'changed_package': old['time'] = saved.stat().st_ctime - 1
    if defect == 'source': scene.tag[0]['FileMD5'] = '0'*32
    if defect == 'option': scene.generic.values['mesh_pipeline'].values['build_nanite'] = True
    if defect == 'triangles': scene.mesh.get_num_triangles = lambda _: 90
    if defect == 'bounds': scene.entry['bounds_m'][1][0] = 2
    if defect == 'dirty': scene.unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages = lambda: [NS(get_name=lambda:package)]
    if defect == 'exception': scene.data.get_pipelines = lambda: 1/0
    def new_adapter():
        return native.MeshReuse(ctx, 'unreal.region', script, ('build',), validation_functions=('validate',))
    def acquire(adapter):
        return adapter.acquire('Mesh', package, geometry=scene.entry, donor_geometry=None,
            sources=[(package, scene.source, mesh_reuse.digest(scene.source))], validator=lambda _: scene.valid())
    first = new_adapter()
    assert first.local_compatible
    if defect:
        assert acquire(first) is None  # caller proceeds through its normal import branch
        assert not first.receipts.path.exists()
        return
    assert acquire(first) is scene.mesh
    first.validated('Mesh')
    assert not first.receipts.path.exists()  # child/failed run cannot publish
    assert acquire(new_adapter()) is scene.mesh  # failure still uses historical evidence
    mesh_reuse.finalize_pending(ctx, 'unreal.region', 'e'*24)
    receipt = json.loads(first.receipts.path.read_text())['meshes']['Mesh']
    assert receipt['provenance']['kind'] == 'compatibility-only'
    before = saved.read_bytes()
    # Existing receipt is sufficient after the old whole-task evidence disappears.
    monkeypatch.setattr(mesh_reuse, 'prior_stamp', lambda *a: None)
    second = new_adapter()
    assert not second.local_compatible
    assert acquire(second) is scene.mesh
    assert saved.read_bytes() == before


def test_collision_glb_summary_uses_baked_frame_and_refuses_transforms(scene):
    from atelier.gltf import glb_pack
    doc = dict(nodes=[{'mesh':0}], meshes=[{'primitives':[{'attributes':{'POSITION':0}, 'indices':1}]}],
        accessors=[dict(min=[-1, -2, -3], max=[4, 5, 6]), dict(count=12)])
    scene.source.write_bytes(glb_pack(doc, b''))
    entry, slots = scene.module.collision_entry(scene.source)
    assert entry == dict(triangles=4, bounds_m=[[-1, -6, -2], [4, 3, 5]])
    assert slots == 1
    doc['nodes'][0]['translation'] = [1, 0, 0]
    scene.source.write_bytes(glb_pack(doc, b''))
    with pytest.raises(ValueError, match='baked'):
        scene.module.collision_entry(scene.source)
