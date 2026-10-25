"""Original board graph, inert import and the existing generic author ABI."""
import ast
from copy import deepcopy
import importlib.util
from pathlib import Path
import runpy
import shutil
import sys
from types import SimpleNamespace as NS

import pytest
from atelier.build_v2.recipe_dependencies import extract

ROOT = Path(__file__).resolve().parents[3]
GAME = ROOT / 'games/yorimichi'
sys.path.insert(0, str(GAME))
import v2_board_units as units  # noqa: E402


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result


body = module(ROOT / units.SCRIPT, 'board_generic_body_test')


@pytest.fixture
def rows():
    path = GAME / 'build.py'
    recipe = module(path, 'board_recipe_test')
    call = next(n for n in ast.walk(ast.parse(path.read_bytes())) if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name) and n.func.id == 'Step' and n.args
                and isinstance(n.args[0], ast.Constant) and n.args[0].value == 'unreal.skate_board')
    step = eval(compile(ast.Expression(call), str(path), 'eval'), vars(recipe))
    return extract([step], checkout=ROOT, build_root=ROOT / 'build')


def test_actual_row_becomes_one_material_with_complete_closure_and_existing_call_abi(rows):
    before = deepcopy(rows)
    result = units.author_units(rows, checkout=ROOT)
    assert rows == before
    unit, = result['units']
    assert unit['id'] == units.UNIT and unit['op'] == {'kind': 'unreal.author', 'version': '1'}
    assert unit['script'] == units.SCRIPT and unit['inputs'] == []
    assert {units.SCRIPT, units.ORIGINAL} <= set(unit['code'])
    assert all((ROOT / path).is_file() for path in unit['code'])
    assert unit['params'] == {'args': {'module': units.ORIGINAL, 'function': 'build', 'arguments': [],
                                     'keyword_arguments': {}, 'expected_package': units.PACKAGE}, 'settings': []}
    assert result['staged_inputs'] == {units.UNIT: {}} and result['content_slots'] == {}
    assert result['aliases'] == {'unreal.skate_board': [units.UNIT]}
    assert result['packages'] == {units.PACKAGE: {'unit': units.UNIT, 'item': 'asset', 'package': units.PACKAGE}}
    output, = unit['outputs']
    assert output == {'id': 'asset', 'logical_path': units.PACKAGE, 'class': 'Material', 'destination': 'checkout',
                      'files': [{'path': 'content/Game/SkatePark/Board/M_BoardDissolve' + ext,
                                 'install_path': 'games/yorimichi/unreal/Content/SkatePark/Board/M_BoardDissolve' + ext,
                                 'required': ext == '.uasset'} for ext in units.SIDECARS]}


@pytest.mark.parametrize('damage', ['outputs', 'script', 'marker', 'args', 'duplicate'])
def test_changed_original_source_declaration_refuses(rows, damage):
    if damage == 'outputs': rows[0]['outputs'] = []
    elif damage == 'duplicate': rows *= 2
    else: rows[0]['commands'][0][damage] = 'changed'
    with pytest.raises(units.Unsupported): units.author_units(rows, checkout=ROOT)
    assert units.author_units([], checkout=ROOT)['aliases'] == {}


class Asset:
    def __init__(self, path='node'): self.path, self.props = path, {}
    def set_editor_property(self, name, value): self.props[name] = value
    def get_path_name(self): return self.path + '.' + self.path.rsplit('/', 1)[-1]


class Material(Asset): pass


@pytest.fixture
def editor(monkeypatch):
    calls, nodes, links, properties, assets = [], [], [], [], {}
    def record(name, result=None):
        def call(*args): calls.append((name, args)); return result
        return call
    def create(name, folder, cls, factory):
        calls.append(('create', (name, folder))); asset = cls(folder + '/' + name); assets[asset.path] = asset; return asset
    def node(mat, cls, x, y):
        result = Asset(cls); nodes.append(result); return result
    def link(a, out, b, pin): links.append((a, out, b, pin)); return True
    unreal = NS(Material=Material, MaterialFactoryNew=lambda: None, CustomInput=Asset, LinearColor=lambda *v: v,
                EditorAssetLibrary=NS(make_directory=record('directory'), does_asset_exist=lambda p: p in assets,
                    load_asset=assets.get, save_loaded_asset=record('save', True)),
                AssetToolsHelpers=NS(get_asset_tools=lambda: NS(create_asset=create)),
                MaterialEditingLibrary=NS(delete_all_material_expressions=record('clear'), create_material_expression=node,
                    connect_material_expressions=link, recompile_material=record('compile'),
                    connect_material_property=lambda a, out, prop: properties.append((a, out, prop)) or True),
                CustomMaterialOutputType=NS(CMOT_FLOAT1=1, CMOT_FLOAT3=3), BlendMode=NS(BLEND_MASKED='masked'),
                MaterialProperty=NS(MP_BASE_COLOR='base', MP_ROUGHNESS='roughness', MP_SPECULAR='specular',
                    MP_OPACITY_MASK='mask', MP_EMISSIVE_COLOR='emissive'),
                MaterialPositionTransformSource=NS(TRANSFORMPOSSOURCE_WORLD='world', TRANSFORMPOSSOURCE_LOCAL='local'),
                log=record('log'))
    for name in ('Custom', 'VertexColor', 'PixelDepth', 'Constant3Vector', 'LinearInterpolate', 'Constant',
                 'LocalPosition', 'WorldPosition', 'TransformPosition', 'ScalarParameter'):
        setattr(unreal, 'MaterialExpression' + name, name)
    monkeypatch.setitem(sys.modules, 'unreal', unreal)
    return NS(unreal=unreal, calls=calls, nodes=nodes, links=links, properties=properties, assets=assets)


def test_import_is_inert_even_without_unreal(monkeypatch):
    monkeypatch.setitem(sys.modules, 'unreal', None)
    source = module(ROOT / units.ORIGINAL, 'inert_board_source_test')
    assert callable(source.build) and source.PATH == units.PACKAGE
    assert 'mat' not in vars(source)


@pytest.mark.parametrize('local', [True, False])
def test_named_build_retains_vertex_haze_local_noise_mask_and_glow(editor, local):
    source = module(ROOT / units.ORIGINAL, 'named_board_source_test')
    assert editor.calls == [] and editor.nodes == []
    if not local: del editor.unreal.MaterialExpressionLocalPosition
    result = source.build()
    assert result is editor.assets[units.PACKAGE]
    assert result.props == {'blend_mode': 'masked', 'opacity_mask_clip_value': .5}
    assert {row[2] for row in editor.properties} == {'base', 'roughness', 'specular', 'mask', 'emissive'}
    codes = [n.props['code'] for n in editor.nodes if n.path == 'Custom']
    assert len(codes) == 5
    assert 'return lerp(C/12.92,pow((C+0.055)/1.055,2.4),step(0.04045,C));' in codes
    assert 'return saturate((D-7000.)/220000.)*.5;' in codes
    assert 'return N-(D*1.1-.05)+.5;' in codes
    assert 'return C*.06+float3(2.5,2.2,1.6)*(1-saturate((Mask-.5)/.06))*step(.001,D);' in codes
    assert any('for (int o=0;o<2;o++)' in code and 'return n/t;' in code for code in codes)
    assert any(n.props.get('constant') == (.64, .68, .76, 1) for n in editor.nodes)
    assert any(n.props == {'parameter_name': 'Dissolve', 'default_value': 0.} for n in editor.nodes)
    assert [n.path for n in editor.nodes].count('TransformPosition') == (0 if local else 1)
    assert len(editor.links) == (11 if local else 12)
    assert [call[0] for call in editor.calls] == ['directory', 'create', 'clear', 'compile', 'save', 'log']
    assert editor.calls[-1] == ('log', ('BOARD DISSOLVE MATERIAL COMPLETE',))


def test_main_retains_original_script_entry(editor):
    runpy.run_path(str(ROOT / units.ORIGINAL), run_name='__main__')
    assert list(editor.assets) == [units.PACKAGE]
    assert len([row for row in editor.calls if row[0] == 'create']) == 1


def test_declared_abi_executes_actual_staged_original_through_existing_body(rows, editor, tmp_path):
    unit, = units.author_units(rows, checkout=ROOT)['units']
    target = tmp_path / units.ORIGINAL; target.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / units.ORIGINAL, target)
    context = NS(job_dir=tmp_path, outputs=[units.PACKAGE], inputs={}, packages={}, params=unit['params'])
    before = list(sys.path)
    body.run(context)
    assert sys.path == before and list(editor.assets) == [units.PACKAGE]
    assert len([row for row in editor.calls if row[0] == 'create']) == 1
    # The source retains its original save; the generic body validates its final save too.
    assert len([row for row in editor.calls if row[0] == 'save']) == 2
