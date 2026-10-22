"""A failed later source preserves a prior unit without publishing a game registry."""
import ast
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import sys
from types import SimpleNamespace

import pytest

from atelier import mesh_geometry as G

GAME = Path(__file__).resolve().parents[1]
SCRIPT = GAME/'unreal/Scripts/build_foliage_system.py'


@pytest.mark.parametrize('corrupt_hint', [None, 'geometry', 'metadata'])
@pytest.mark.parametrize('module_change', [None, 'Yorimichi', 'YorimichiImport', 'YorimichiFoliagePreparation'])
def test_partial_source_resumes_only_after_current_validation(tmp_path, monkeypatch, corrupt_hint, module_change):
    spec = importlib.util.spec_from_file_location('unit_resume_foliage_kernel', GAME/'foliage_system.py')
    kernel = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(kernel)
    game = tmp_path/'game'
    content = game/'unreal/Content'
    owner = game/'unreal/Scripts/build_foliage_system.py'
    owner.parent.mkdir(parents=True)
    owner.write_text(SCRIPT.read_text())
    for relative in ('unreal/Source/YorimichiImport/FoliageBuilder.cpp',
                     'unreal/Source/YorimichiImport/FoliageBuilder.h',
                     'unreal/Source/YorimichiImport/MeshGeometrySnapshot.cpp',
                     'unreal/Source/YorimichiFoliagePreparation/FoliageSourceWriter.cpp',
                     'unreal/Source/YorimichiFoliagePreparation/FoliageSourceWriter.h',
                     'unreal/Source/YorimichiFoliagePreparation/FoliageGeometryReader.cpp',
                     'unreal/Source/YorimichiFoliagePreparation/FoliageGeometryReader.h',
                     'foliage_unit_policy_witness.json',
                     'unreal/Scripts/foliage_material.py', 'unreal/Scripts/foliage_variant_validation.py'):
        path = game/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('fixture support')
    support = tmp_path/'support.py'
    support.write_text('fixture material graph')
    out = tmp_path/'build/foliage_system'
    (out.parent/'unreal-modules').mkdir(parents=True)
    for module in ('Yorimichi', 'YorimichiImport', 'YorimichiFoliagePreparation'):
        (out.parent/'unreal-modules'/f'{module}.json').write_text('fixture binary')
    sources = ['/Game/Fixture/Mixed_1', '/Game/Fixture/Mixed_2']
    assets = {}
    outputs = {}
    exports, builds, readbacks = [], [], []
    failure = {'enabled': True}

    class Asset:
        def __init__(self, path):
            self.path = path

        def get_path_name(self):
            return self.path+'.'+self.get_name()

        def get_name(self):
            return self.path.rsplit('/', 1)[-1]

        def get_material(self, index):
            return 'source material'

        def get_editor_property(self, key):
            assert key == 'static_materials'
            return ['source slot']

        def get_num_triangles(self, index):
            return 1

    for source in sources:
        assets[source] = Asset(source)
        key = kernel.asset_id(assets[source].get_path_name())
        outputs[source] = {}
        for role, suffix in (('optimized', ''), ('shadow', '_Shadow'), ('patch', '_Patch')):
            destination = kernel.ROOT+'/Meshes/'+key+suffix
            outputs[source][role] = Asset(destination)
            assets[destination] = outputs[source][role]
        for package in (source, *(asset.path for asset in outputs[source].values())):
            path = content/(package.removeprefix('/Game/')+'.uasset')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(package.encode())
    prepared = dict(uv_channels=1, materials=[dict(path='/Game/Fixture/Leaves', foliage=True)],
                    vertices=[dict(p=p, n=[0., 0., 1.], c=[.5, .6, .2, 1.], uv=[0., 0.])
                              for p in ([0., 0., 0.], [1., 0., 0.], [0., 1., 0.])],
                    faces=[dict(v=[0, 1, 2], s=0, foliage=True)])

    def export(mesh, slots, classification, kind, path):
        exports.append(mesh.path)
        if mesh.path == sources[1] and failure['enabled']:
            return False
        Path(path).write_text(json.dumps(dict(deepcopy(prepared), path=mesh.get_path_name(),
                                             classification=classification, kind=kind)))
        return True

    original_build = kernel.build

    def build(source):
        builds.append(source['path'])
        return original_build(source)

    monkeypatch.setattr(kernel, 'build', build)

    def saved(mesh, destinations, replacements, canopies, row, geometry, key):
        readbacks.append(mesh.path)
        assert set(geometry) == {'optimized', 'shadow', 'patch'}
        assert all(len(value) == 64 for value in geometry.values())
        assert list(destinations.values()) == [asset.path for asset in outputs[mesh.path].values()]
        return dict(outputs[mesh.path])

    def unexpected_rebuild(*args):
        pytest.fail('A currently verified saved variant must not call BuildVariant')

    registry = SimpleNamespace(search_all_assets=lambda **k: None,
        get_assets_by_path=lambda *a, **k: [SimpleNamespace(package_name=source,
            asset_class_path=SimpleNamespace(asset_name='StaticMesh')) for source in sources])
    unreal = SimpleNamespace(load_module=lambda name: None, log=lambda text: None,
        AssetRegistryHelpers=SimpleNamespace(get_asset_registry=lambda: registry),
        SystemLibrary=SimpleNamespace(get_engine_version=lambda: 'fixture 5.8'),
        YorimichiFoliageSourceWriter=SimpleNamespace(export_source=export),
        YorimichiFoliageBuilder=SimpleNamespace(collect_unused=lambda: None,
                                               build_variant=unexpected_rebuild))
    namespace = dict(__file__=str(owner), Path=Path, F=kernel, G=G, U=unreal, OUT=out,
        E=SimpleNamespace(load_asset=assets.__getitem__, does_asset_exist=lambda path: path in assets),
        yori=SimpleNamespace(GAME=game), atmosphere=SimpleNamespace(__file__=str(support)),
        see_through=SimpleNamespace(__file__=str(support)), hashlib=hashlib, json=json, platform=platform, sys=sys,
        unit_policy=SimpleNamespace(__file__=str(support),legacy_policies=lambda *a,**k: ()),
        native_environment=lambda ctx: dict(engine='fixture', platform='fixture'),
        native_context=lambda name: None, runtime_files=lambda: (),
        classify=lambda *a: ([0], 'material'), source_identity=lambda *a: '1'*64,
        canopy_material=lambda *a, **k: 'current canopy', blend_material=lambda value: value,
        saved_variants=saved)
    functions = [node for node in ast.parse(SCRIPT.read_text()).body
                 if isinstance(node, ast.FunctionDef) and node.name in ('digest', 'write_representations', 'main')]
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(SCRIPT), 'exec'), namespace)
    with pytest.raises(AssertionError, match='Mixed_2'):
        namespace['main']()
    units = list((out/'units').glob('*.json'))
    assert len(units) == 1
    assert not (out/'report.json').exists()
    assert not (content/'Data/foliage_system/registry.json').exists()
    if corrupt_hint:
        hint = json.loads(units[0].read_text())
        del hint[corrupt_hint]['patch']
        units[0].write_text(json.dumps(hint))
    if module_change:
        (out.parent/'unreal-modules'/f'{module_change}.json').write_text('changed actual compiled binary')
    hint_miss = bool(corrupt_hint or module_change in ('YorimichiImport', 'YorimichiFoliagePreparation'))
    failure['enabled'] = False
    namespace['main']()
    expected = 2 if hint_miss else 1
    assert exports.count(sources[0]) == builds.count(assets[sources[0]].get_path_name()) == expected
    assert readbacks.count(sources[0]) == 2
    report = json.loads((out/'report.json').read_text())
    assert report == json.loads((content/'Data/foliage_system/registry.json').read_text())
    counts = json.loads((out/'preparation-counts.json').read_text())
    assert len(report['assets']) == 2 and counts['built_variants'] == 0
    assert counts['unit_hits'] == (0 if hint_miss else 1)


def test_owner_bootstraps_studio_without_installed_atelier(tmp_path):
    """Commandlet Python has no editable venv package or ambient repository path."""
    import subprocess
    code = r"""
import ast, importlib.util, sys, types
from pathlib import Path
assert importlib.util.find_spec('atelier') is None
sys.modules['unreal'] = types.ModuleType('unreal')
script = Path(sys.argv[1])
prefix = []
for node in ast.parse(script.read_text()).body:
    prefix.append(node)
    if isinstance(node, ast.ImportFrom) and node.module == 'atelier.native_protocol':
        break
exec(compile(ast.Module(body=prefix, type_ignores=[]), str(script), 'exec'), {'__file__': str(script)})
from atelier import mesh_geometry
assert Path(mesh_geometry.__file__).resolve().is_relative_to(script.parents[4] / 'platform/studio')
"""
    subprocess.run([sys.executable, '-I', '-S', '-c', code, str(SCRIPT)], cwd=tmp_path,
                   check=True, capture_output=True, text=True, timeout=10)
