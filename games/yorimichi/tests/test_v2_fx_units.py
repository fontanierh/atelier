"""unreal.fx owners: sprite raw/finish per committed generator declaration, one author per saved material graph."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace as NS

import pytest
from atelier.build_v2.recipe_dependencies import extract

ROOT = Path(__file__).resolve().parents[3]
GAME = ROOT / 'games/yorimichi'
sys.path.insert(0, str(GAME))
import v2_fx_units as fx  # noqa: E402
from v2_texture_units import Unsupported  # noqa: E402

spec = importlib.util.spec_from_file_location('fx_recipe', GAME / 'build.py')
recipe = importlib.util.module_from_spec(spec); sys.modules['fx_recipe'] = recipe; spec.loader.exec_module(recipe)
spec = importlib.util.spec_from_file_location('fx_v2', GAME / 'world/fx_v2.py')
body = importlib.util.module_from_spec(spec); spec.loader.exec_module(body)


@pytest.fixture(scope='module')
def actual():
    context = NS(uproject=GAME / 'unreal/Yorimichi.uproject', out=ROOT / 'build/yorimichi')
    steps = [step for step in recipe.steps(context) if step.name in ('fx.textures', 'unreal.fx')]
    return extract(steps, checkout=ROOT, build_root=ROOT / 'build')


def complete(rows):
    """The rows with fx.textures owning its whole combat_fx ROOT (the requested one-line product)."""
    rows = deepcopy(rows)
    producer = next(row for row in rows if row['id'] == 'fx.textures')
    producer['products'] = [{'id': 'fx.textures', 'paths': [fx.SOURCE_ROOT], 'optional_paths': []}]
    return rows


def test_actual_producer_without_its_complete_root_refuses(actual):
    with pytest.raises(Unsupported, match='complete combat_fx ROOT'):
        fx.author_units(actual, checkout=ROOT)


def test_roster_comes_from_committed_generator_declarations():
    assert fx.sprites(ROOT) == ['Dust', 'Glow', 'Ring', 'Spark', 'Trail']


def test_units_per_sprite_and_saved_graph(actual):
    result = fx.author_units(complete(actual), checkout=ROOT)
    by_id = {unit['id']: unit for unit in result['units']}
    raw = by_id['unreal.fx.texture.raw.T_FX_Spark']
    assert raw['inputs'] == [{'role': 'content', 'name': 'source', 'source': {'kind': 'item', 'unit': 'fx.textures', 'item': 'product0'}}]
    assert raw['params']['source_member'] == 'T_FX_Spark.png'
    assert raw['params']['input_roots'] == {'source': {'archive_member': 'products/0-0.tree.tar', 'name': 'source'}}
    finish = by_id['unreal.fx.texture.T_FX_Spark']
    assert finish['params']['properties'] == {'srgb': False, 'lod_group': {'unreal_enum': 'TextureGroup.TEXTUREGROUP_EFFECTS'}}
    assert finish['outputs'][0]['logical_path'] == '/Game/FX/Textures/T_FX_Spark'
    materials = {u['outputs'][0]['logical_path']: u for u in result['units'] if u['op']['kind'] == 'unreal.author'}
    assert sorted(materials) == ['/Game/FX/MI_FX_Dust', '/Game/FX/MI_FX_Glow', '/Game/FX/MI_FX_Ring', '/Game/FX/MI_FX_Spark',
                                 '/Game/FX/M_FX_Additive', '/Game/FX/M_FX_Dust', '/Game/FX/M_FX_Trail']
    assert {p: u['outputs'][0]['class'] for p, u in materials.items() if '/M_' in p} == dict.fromkeys(
        ['/Game/FX/M_FX_Additive', '/Game/FX/M_FX_Dust', '/Game/FX/M_FX_Trail'], 'Material')
    spark = materials['/Game/FX/MI_FX_Spark']['params']['args']
    assert spark['parent'] == '/Game/FX/M_FX_Additive' and spark['texture'] == '/Game/FX/Textures/T_FX_Spark'
    assert sorted(spark['inputs'].values()) == ['/Game/FX/M_FX_Additive', '/Game/FX/Textures/T_FX_Glow', '/Game/FX/Textures/T_FX_Spark']
    assert materials['/Game/FX/M_FX_Additive']['params']['args']['blend'] == 'BLEND_ADDITIVE'
    assert {fx.SCRIPT, fx.ORIGINAL} <= set(materials['/Game/FX/M_FX_Trail']['code'])
    assert [d['package'] for d in result['packages']['/Game/FX/MI_FX_Spark']['dependencies']] == [
        '/Game/FX/Textures/T_FX_Glow', '/Game/FX/M_FX_Additive', '/Game/FX/Textures/T_FX_Spark']
    assert result['aliases'] == {'unreal.fx': tuple(u['id'] for u in result['units'])} and len(result['units']) == 17


@pytest.mark.parametrize('change', ['script', 'marker', 'needs', 'optional', 'natives'])
def test_reshaped_rows_refuse(actual, change):
    rows = complete(actual)
    importer = next(row for row in rows if row['id'] == 'unreal.fx')
    natives = None
    if change == 'script': importer['commands'][0]['script'] = {'path': 'x.py'}
    elif change == 'marker': importer['commands'][0]['marker'] = 'DONE'
    elif change == 'needs': importer['needs'] = []
    elif change == 'optional': rows[0 if rows[0]['id'] == 'fx.textures' else 1]['products'][0]['optional_paths'] = ['x']
    elif change == 'natives': natives = {'x': {}}
    with pytest.raises(Unsupported):
        fx.author_units(rows, checkout=ROOT, natives=natives)


# ---- bodies ---------------------------------------------------------------------------------------------------------

class Asset:
    def __init__(self, path, **props): self.path, self.props = path, dict(props)
    def get_path_name(self): return self.path + '.' + self.path.rsplit('/', 1)[1]
    def get_editor_property(self, name): return self.props[name]
    def set_editor_property(self, name, value): self.props[name] = value


class Texture2D(Asset): pass
class Material(Asset): pass
class MaterialInstanceConstant(Asset): pass


@pytest.fixture
def editor(tmp_path, monkeypatch):
    target = tmp_path / body.ORIGINAL; target.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / body.ORIGINAL, target)
    assets, graph, saves = {}, [], []
    def create(name, folder, cls, factory):
        asset = cls(folder + '/' + name); assets[asset.path] = asset; return asset
    expression = lambda cls: type(cls, (Asset,), {})
    names = ('MaterialExpressionTextureSampleParameter2D', 'MaterialExpressionPerInstanceCustomData', 'MaterialExpressionAppendVector',
             'MaterialExpressionMultiply', 'MaterialExpressionSaturate', 'MaterialExpressionVertexColor',
             'MaterialExpressionTextureSample', 'MaterialExpressionScalarParameter')
    library = NS(delete_all_material_expressions=lambda mat: graph.clear(),
                 create_material_expression=lambda mat, cls, x, y: graph.append(cls('node')) or graph[-1],
                 connect_material_expressions=lambda *a: True, connect_material_property=lambda *a: True,
                 recompile_material=lambda mat: None,
                 set_material_instance_parent=lambda mi, parent: mi.props.update(parent=parent),
                 set_material_instance_texture_parameter_value=lambda mi, name, tex: mi.props.update(sprite=tex))
    unreal = NS(Texture2D=Texture2D, Material=Material, MaterialInstanceConstant=MaterialInstanceConstant,
                MaterialFactoryNew=lambda: 'f', MaterialInstanceConstantFactoryNew=lambda: 'f',
                MaterialShadingModel=NS(MSM_UNLIT='unlit'), BlendMode=NS(BLEND_ADDITIVE='add', BLEND_TRANSLUCENT='translucent'),
                MaterialProperty=NS(MP_EMISSIVE_COLOR='emissive', MP_OPACITY='opacity'), MaterialEditingLibrary=library,
                EditorAssetLibrary=NS(load_asset=lambda p: assets.get(p.split('.', 1)[0]), does_asset_exist=lambda p: p in assets,
                                      save_loaded_asset=lambda a: saves.append(a.path) or True),
                AssetToolsHelpers=NS(get_asset_tools=lambda: NS(create_asset=create)),
                **{name: expression(name) for name in names})
    for sprite in ('Glow', 'Spark', 'Trail'):
        assets['/Game/FX/Textures/T_FX_' + sprite] = Texture2D('/Game/FX/Textures/T_FX_' + sprite)
    monkeypatch.setitem(sys.modules, 'unreal', unreal)
    return NS(assets=assets, graph=graph, saves=saves, root=tmp_path)


def job(editor, args):
    inputs = args['inputs']
    return NS(job_dir=str(editor.root), inputs=dict.fromkeys(inputs, 'x'), packages={k: [v] for k, v in inputs.items()},
              outputs=['/Game/FX/' + args['name']], params={'args': args, 'settings': []})


def test_sprite_trail_and_instance_run_original_graph_code(editor):
    additive = body.run(job(editor, {'action': 'sprite', 'name': 'M_FX_Additive', 'blend': 'BLEND_ADDITIVE',
                                     'texture': '/Game/FX/Textures/T_FX_Glow', 'inputs': {'native0': '/Game/FX/Textures/T_FX_Glow'}}))
    assert additive.props['blend_mode'] == 'add' and additive.props['used_with_instanced_static_meshes'] is True
    sprite = [n for n in editor.graph if type(n).__name__ == 'MaterialExpressionTextureSampleParameter2D']
    assert sprite[0].props == {'parameter_name': 'Sprite', 'texture': editor.assets['/Game/FX/Textures/T_FX_Glow']}
    trail = body.run(job(editor, {'action': 'trail', 'name': 'M_FX_Trail', 'texture': '/Game/FX/Textures/T_FX_Trail',
                                  'inputs': {'native0': '/Game/FX/Textures/T_FX_Trail'}}))
    intensity = [n for n in editor.graph if type(n).__name__ == 'MaterialExpressionScalarParameter']
    assert trail.props['blend_mode'] == 'add' and intensity[0].props == {'parameter_name': 'Intensity', 'default_value': 4.}
    spark = body.run(job(editor, {'action': 'instance', 'name': 'MI_FX_Spark', 'parent': '/Game/FX/M_FX_Additive',
                                  'texture': '/Game/FX/Textures/T_FX_Spark',
                                  'inputs': {'native0': '/Game/FX/Textures/T_FX_Glow', 'native1': '/Game/FX/M_FX_Additive',
                                             'native2': '/Game/FX/Textures/T_FX_Spark'}}))
    assert spark.props == {'parent': additive, 'sprite': editor.assets['/Game/FX/Textures/T_FX_Spark']}
    assert editor.saves == ['/Game/FX/M_FX_Additive', '/Game/FX/M_FX_Trail', '/Game/FX/MI_FX_Spark']


@pytest.mark.parametrize('failure', ['undeclared', 'existing', 'outputs', 'texture', 'action'])
def test_bodies_refuse_inconsistent_jobs(editor, failure):
    args = {'action': 'sprite', 'name': 'M_FX_Additive', 'blend': 'BLEND_ADDITIVE', 'texture': '/Game/FX/Textures/T_FX_Glow',
            'inputs': {'native0': '/Game/FX/Textures/T_FX_Glow'}}
    context = job(editor, args)
    if failure == 'undeclared': context.inputs['extra'] = 'x'
    elif failure == 'existing': editor.assets['/Game/FX/M_FX_Additive'] = Material('/Game/FX/M_FX_Additive')
    elif failure == 'outputs': context.outputs.append('/Game/FX/M_FX_Dust')
    elif failure == 'texture': args['texture'] = '/Game/FX/Textures/T_FX_Spark'
    elif failure == 'action': args['action'] = 'trail'
    with pytest.raises(ValueError):
        body.run(context)
