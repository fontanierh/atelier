"""Actual crater-cloud declaration and original staged graph, without Unreal jobs."""
import ast
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest
from atelier.build_v2.recipe_dependencies import extract

ROOT = Path(__file__).resolve().parents[3]
GAME = ROOT / 'games/yorimichi'
sys.path.insert(0, str(GAME))
import v2_cloud_units as units  # noqa: E402


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result


body = module(GAME / 'world/cloud_v2.py', 'cloud_body_test')


@pytest.fixture
def rows():
    path = GAME / 'build.py'
    recipe = module(path, 'cloud_recipe_test')
    # Evaluate the actual one Step constructor, avoiding unrelated compile/engine discovery.
    call = next(n for n in ast.walk(ast.parse(path.read_bytes())) if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name) and n.func.id == 'Step' and n.args
                and isinstance(n.args[0], ast.Constant) and n.args[0].value == 'unreal.crater_cloud')
    step = eval(compile(ast.Expression(call), str(path), 'eval'), vars(recipe))
    return extract([step], checkout=ROOT, build_root=ROOT / 'build')


def test_actual_declaration_has_two_exact_owners_and_keyed_closure(rows):
    before = deepcopy(rows)
    result = units.author_units(rows, checkout=ROOT)
    assert rows == before
    assert len(result['units']) == 2
    assert result['aliases'] == {'unreal.crater_cloud': [u['id'] for u in result['units']]}
    assert result['content_slots'] == {}
    for unit, name in zip(result['units'], units.NAMES):
        package = units.FOLDER + '/' + name
        assert unit['op'] == {'kind': 'unreal.author', 'version': '1'}
        assert unit['inputs'] == [] and unit['params'] == {'args': {'asset': name}, 'settings': []}
        assert result['staged_inputs'][unit['id']] == {}
        assert {units.SCRIPT, units.ORIGINAL, units.SAVE, units.SCRIPTS + 'atmosphere.py',
                units.SCRIPTS + 'sea_look.py'} <= set(unit['code'])
        assert all((ROOT / p).is_file() for p in unit['code'])
        item, = unit['outputs']
        assert item['logical_path'] == package and item['class'] == 'Material' and item['destination'] == 'checkout'
        assert item['files'] == [{'path': 'content/Game/CraterPark/Cloud/' + name + ext,
                                 'install_path': 'games/yorimichi/unreal/Content/CraterPark/Cloud/' + name + ext,
                                 'required': ext == '.uasset'} for ext in units.SIDECARS]
        assert result['packages'][package] == {'unit': unit['id'], 'item': 'asset', 'package': package}


@pytest.mark.parametrize('damage', ['output', 'script', 'marker', 'args', 'duplicate'])
def test_changed_original_declaration_refuses(rows, damage):
    if damage == 'output': rows[0]['outputs'].pop()
    elif damage == 'duplicate': rows *= 2
    else: rows[0]['commands'][0][damage] = 'changed'
    with pytest.raises(units.Unsupported): units.author_units(rows, checkout=ROOT)
    assert units.author_units([], checkout=ROOT)['aliases'] == {}


class Asset:
    def __init__(self, path='node'): self.path, self.props = path, {}
    def set_editor_property(self, key, value): self.props[key] = value
    def get_path_name(self): return self.path + '.' + self.path.rsplit('/', 1)[-1]


class Material(Asset): pass


@pytest.fixture
def editor(tmp_path, monkeypatch):
    for relative in (units.ORIGINAL, units.SAVE, units.SCRIPTS + 'atmosphere.py', units.SCRIPTS + 'sea_look.py'):
        target = tmp_path / relative; target.parent.mkdir(parents=True, exist_ok=True)
        # Any execution of the source top level would fail, including original main.
        target.write_text((ROOT / relative).read_text() + ('\nraise AssertionError("top level ran")\n' if relative != units.SAVE else ''))
    content = tmp_path / 'Content'; content.mkdir()
    assets, nodes, links, properties = {}, [], [], []
    def create(name, folder, cls, factory):
        result = cls(folder + '/' + name); assets[result.path] = result; return result
    def node(mat, cls, x, y):
        result = Asset(cls); nodes.append(result); return result
    def save(asset, only_if_is_dirty=False):
        path = content / (asset.path.removeprefix('/Game/') + '.uasset')
        path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'package'); return True
    def link(a, out, b, into): links.append((a, out, b, into)); return True
    unreal = NS(Material=Material, MaterialFactoryNew=lambda: None, CustomInput=Asset,
                LinearColor=lambda *v: v,
                EditorAssetLibrary=NS(does_asset_exist=lambda p: p in assets, load_asset=assets.get, save_loaded_asset=save),
                AssetToolsHelpers=NS(get_asset_tools=lambda: NS(create_asset=create)),
                MaterialEditingLibrary=NS(delete_all_material_expressions=lambda mat: None,
                    create_material_expression=node, connect_material_expressions=link,
                    connect_material_property=lambda a, out, prop: properties.append((a, out, prop)) or True,
                    recompile_material=lambda mat: None),
                CustomMaterialOutputType=NS(CMOT_FLOAT1=1, CMOT_FLOAT2=2, CMOT_FLOAT3=3),
                BlendMode=NS(BLEND_TRANSLUCENT='translucent'), MaterialShadingModel=NS(MSM_UNLIT='unlit'),
                MaterialSceneAttributeInputMode=NS(OFFSET_FRACTION='offset'),
                MaterialProperty=NS(MP_EMISSIVE_COLOR='emissive', MP_OPACITY='opacity'))
    for name in ('Custom', 'VectorParameter', 'ScalarParameter', 'WorldPosition', 'CameraPositionWS', 'VertexNormalWS',
                 'PixelDepth', 'SceneDepth', 'Time', 'ViewSize', 'Multiply', 'Constant2Vector', 'SceneColor'):
        setattr(unreal, 'MaterialExpression' + name, name)
    monkeypatch.setitem(sys.modules, 'unreal', unreal)
    # Global modules must not influence the staged keyed closure.
    monkeypatch.setitem(sys.modules, 'atmosphere', NS(SHARE='WRONG'))
    monkeypatch.setitem(sys.modules, 'sea_look', NS(HAZE_CM=-1))
    return NS(root=tmp_path, content=content, assets=assets, nodes=nodes, links=links,
              properties=properties, unreal=unreal)


def context(editor, name):
    return NS(job_dir=str(editor.root), content=str(editor.content), inputs={}, packages={},
              outputs=[units.FOLDER + '/' + name], params={'args': {'asset': name}, 'settings': []})


@pytest.mark.parametrize('name', units.NAMES)
def test_selected_original_graph_only_builds_and_saves_its_own_package(editor, name):
    result = body.run(context(editor, name))
    assert list(editor.assets) == [units.FOLDER + '/' + name]
    assert result.props == {'blend_mode': 'translucent', 'shading_model': 'unlit', 'two_sided': True,
                            'use_translucency_vertex_fog': False, 'output_translucent_velocity': False}
    assert (editor.content / ('CraterPark/Cloud/' + name + '.uasset')).is_file()
    params = {n.props['parameter_name']: n.props['default_value'] for n in editor.nodes if 'parameter_name' in n.props}
    assert params['Centre'] == (86000., -244000., 76250., 1.)
    assert params['Opacity'] == (.07, .55, 0., 1.) and params['Soft'] == 4500.
    assert len([n for n in editor.nodes if n.path == 'SceneColor']) == (9 if name.endswith('Veil') else 0)
    codes = [n.props['code'] for n in editor.nodes if 'code' in n.props]
    assert any('900000.0' in code and 'float3(0.0932,0.2301,0.5328)' in code for code in codes)
    assert any('nz/=tot;' in code and 'Tm*Dr' in code for code in codes)
    assert {p[2] for p in editor.properties} == {'emissive', 'opacity'}
    source = body.original(context(editor, name), editor.unreal, editor.unreal.EditorAssetLibrary)
    assert 'main' not in source and source['build'].__code__.co_filename == str(editor.root / units.ORIGINAL)
    assert len(source['TAPS']) == 9


@pytest.mark.parametrize('damage', ['sibling', 'input', 'package', 'existing', 'name'])
def test_output_and_input_ownership_refuse_before_build(editor, damage):
    case = context(editor, units.NAMES[0])
    if damage == 'sibling': case.outputs.append(units.FOLDER + '/' + units.NAMES[1])
    elif damage == 'input': case.inputs['native'] = 'x'
    elif damage == 'package': case.packages['native'] = ['/Game/Other']
    elif damage == 'existing': editor.assets[case.outputs[0]] = Material(case.outputs[0])
    else: case.params['args']['asset'] = 'Other'
    with pytest.raises(ValueError): body.run(case)
    assert editor.nodes == []


def test_missing_staged_support_refuses_instead_of_import_fallback(editor):
    (editor.root / (units.SCRIPTS + 'sea_look.py')).unlink()
    with pytest.raises(ValueError, match='staged keyed code'):
        body.run(context(editor, units.NAMES[0]))
    assert editor.assets == {}


def test_staged_sea_and_atmosphere_constants_drive_original_shader(editor):
    path = editor.root / (units.SCRIPTS + 'sea_look.py')
    path.write_text(path.read_text().replace('HAZE_CM = 900000.0', 'HAZE_CM = 123456.0'))
    body.run(context(editor, units.NAMES[0]))
    assert any('123456.0' in n.props.get('code', '') for n in editor.nodes)


@pytest.mark.parametrize('reported', [False, True])
def test_save_failure_or_missing_primary_cannot_complete(editor, reported):
    editor.unreal.EditorAssetLibrary.save_loaded_asset = lambda *a, **kw: reported
    with pytest.raises(RuntimeError, match='save failed|regular primary'):
        body.run(context(editor, units.NAMES[0]))
