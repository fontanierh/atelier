"""Portable island author routing and real narrow-factory boundary tests."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

GAME = Path(__file__).resolve().parents[1]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


body = load(GAME / 'world/island_materials_v2.py', 'island_material_body_test')
units = load(GAME / 'v2_island_material_units.py', 'island_declarations_body_test')
codec = __import__('atelier.build_v2.recipe_job', fromlist=['pack_root'])


class Asset:
    def __init__(self, package):
        self.package = package
    def get_path_name(self):
        return self.package + '.' + self.package.rsplit('/', 1)[-1]


def context(monkeypatch, tmp_path, spec):
    package = units.PREFIX + spec['asset']
    native = {path.rsplit('/', 1)[-1]: path for path in spec['dependencies']}
    args = {key: value for key, value in deepcopy(spec).items() if key != 'dependencies'}
    args.update(package=package, inputs=native)
    inputs, packages = {name: '/staged/' + name for name in native}, {name: [path] for name, path in native.items()}
    if spec['factory'] == 'forest':
        root = tmp_path / 'item'
        archive = root / 'products/0-1.tree.tar'
        source = tmp_path / 'north_snow.json'
        source.write_text(json.dumps({'south_join_m': 4321.25}))
        codec.pack_root(source, archive)
        inputs['north_snow'], packages['north_snow'] = str(root), []
        args['north_snow'] = {'file': 'products/0-1.tree.tar'}
    events, created, saved, loaded = [], [], [], []
    def create(factory, **kwargs):
        result = Asset(package)
        events.append((factory, kwargs)); created.append(result)
        return result
    def save(asset, *unused):
        saved.append(asset)
        return True
    def read(path):
        loaded.append(path)
        return Asset(path)
    eal = SimpleNamespace(load_asset=read, save_loaded_asset=save)
    monkeypatch.setitem(sys.modules, 'unreal', SimpleNamespace(EditorAssetLibrary=eal))
    forest = SimpleNamespace(material=lambda **kw: create('forest', **kw),
        rock_material=lambda **kw: create('rock', **kw), coast_instance=lambda **kw: create('coast', **kw))
    southwest = SimpleNamespace(sand_material=lambda: create('sand'), sea_material=lambda: create('sea'))
    assets = SimpleNamespace(instance=lambda name, parent: create('instance', parent=parent), save_material=save)
    monkeypatch.setattr(body, '_helpers', lambda: (forest, southwest, assets))
    result = SimpleNamespace(params={'args': args, 'settings': []}, inputs=inputs, packages=packages, outputs=[package])
    return result, events, created, saved, loaded


@pytest.mark.parametrize('spec', units.material_specs(), ids=lambda row: row['asset'])
def test_each_factory_writes_one_asset_and_only_loads_declared_native_inputs(monkeypatch, tmp_path, spec):
    ctx, events, created, saved, loaded = context(monkeypatch, tmp_path, spec)
    body.run(ctx)
    assert len(created) == 1 and saved == created
    assert loaded == list(ctx.params['args']['inputs'].values())
    assert events[0][0] == spec['factory']
    if spec['factory'] == 'forest':
        assert events[0][1] == {'south_join_m': 4321.25}
    elif spec['factory'] == 'rock':
        assert events[0][1]['texture'].package == units.TEXTURE
    elif spec['factory'] in ('coast', 'instance'):
        assert events[0][1]['parent'].package == units.PREFIX + spec['parent']


def test_actual_file_root_json_is_read_without_ambient_paths(tmp_path):
    source = tmp_path / 'north_snow.json'
    source.write_text('{"south_join_m":4210.5}')
    archive = tmp_path / 'north.tree.tar'
    codec.pack_root(source, archive)
    ctx = SimpleNamespace(inputs={'north_snow': str(archive)})
    assert body.snow_join(ctx, {'file': 'unused'}) == 4210.5
    source.write_text('{"south_join_m":false}')
    with pytest.raises(ValueError, match='finite'):
        body.snow_join(SimpleNamespace(inputs={'north_snow': str(source)}), {})


def test_wrong_package_or_missing_native_input_refuses_before_creation(monkeypatch, tmp_path):
    ctx, _, created, _, _ = context(monkeypatch, tmp_path, units.material_specs()[3])
    ctx.packages['T_CoastRock'] = ['/Game/Other']
    with pytest.raises(ValueError, match='dependency'):
        body.run(ctx)
    assert not created


class NativeObject:
    def __init__(self, name='expression'):
        self.name, self.properties = name, {}
    def set_editor_property(self, key, value):
        self.properties[key] = value


def narrow_forest(monkeypatch):
    """Execute the real original graph factories; all native calls stay in this fake API."""
    saved, created, loads, expressions = [], [], [], []
    textures = {name: NativeObject(name) for name in ('T_ground', 'T_ground_detail', 'T_CoastRock')}
    def read(path):
        loads.append(path)
        return textures[path.rsplit('/', 1)[-1]]
    def create(name, *args):
        result = NativeObject(name); created.append(result)
        return result
    def expression(material, cls, *args):
        result = NativeObject(); expressions.append(result)
        return result
    edit = SimpleNamespace(delete_all_material_expressions=lambda material: None,
        create_material_expression=expression, connect_material_expressions=lambda *args: True,
        connect_material_property=lambda *args: True, recompile_material=lambda material: [])
    eal = SimpleNamespace(does_asset_exist=lambda path: False, load_asset=read,
                          save_loaded_asset=lambda material: saved.append(material) or True)
    tools = SimpleNamespace(create_asset=create,
        import_asset_tasks=lambda *args: pytest.fail('explicit texture must never be imported again'))
    class NativeAPI(SimpleNamespace):
        def __getattr__(self, name):
            if name.startswith('MaterialExpression'):
                return name
            raise AttributeError(name)
    native = NativeAPI(EditorAssetLibrary=eal, MaterialEditingLibrary=edit,
        AssetToolsHelpers=SimpleNamespace(get_asset_tools=lambda: tools), Material=NativeObject,
        MaterialFactoryNew=lambda: None, CustomInput=NativeObject,
        CustomMaterialOutputType=SimpleNamespace(CMOT_FLOAT3='float3'),
        MaterialProperty=SimpleNamespace(**{name: name for name in ('MP_BASE_COLOR', 'MP_EMISSIVE_COLOR',
            'MP_ROUGHNESS', 'MP_SPECULAR', 'MP_NORMAL')}))
    def missing(*args):
        pytest.fail('explicit v2 arguments must not read ambient OUT/ASSETS')
    class Ambient:
        __truediv__ = missing
    monkeypatch.setitem(sys.modules, 'unreal', native)
    monkeypatch.setitem(sys.modules, 'yori', SimpleNamespace(OUT=Ambient(), ASSETS=Ambient()))
    monkeypatch.setitem(sys.modules, 'atmosphere', SimpleNamespace(apply=lambda material, base, glow: (base, glow)))
    monkeypatch.setitem(sys.modules, 'ground_grain', load(GAME / 'unreal/Scripts/ground_grain.py', 'ground_grain_real_test'))
    monkeypatch.setitem(sys.modules, 'coast_rock_look', load(GAME / 'unreal/Scripts/coast_rock_look.py', 'coast_look_real_test'))
    monkeypatch.setitem(sys.modules, 'material_assets', SimpleNamespace(create=create,
        save_material=lambda material: saved.append(material)))
    forest = load(GAME / 'unreal/Scripts/forest_ground.py', 'forest_real_narrow_test')
    return forest, saved, created, loads, expressions, textures


def test_real_forest_factory_uses_explicit_join_and_only_declared_textures(monkeypatch):
    forest, saved, created, loads, expressions, _ = narrow_forest(monkeypatch)
    result = forest.material(south_join_m=4321.25)
    assert created == saved == [result]
    assert loads == ['/Game/Japan/Textures/T_ground', '/Game/Japan/Textures/T_ground_detail']
    codes = [node.properties['code'] for node in expressions if 'code' in node.properties]
    assert any('smoothstep(432125.,462125.,-P.y)' in code for code in codes)


def test_real_rock_factory_does_not_import_or_save_its_finished_texture(monkeypatch):
    forest, saved, created, loads, expressions, textures = narrow_forest(monkeypatch)
    result = forest.rock_material(texture=textures['T_CoastRock'])
    assert created == saved == [result]
    assert loads == [] and textures['T_CoastRock'] not in saved
    assert result.properties['tangent_space_normal'] is False
    assert result.properties['used_with_instanced_static_meshes'] is True
    assert any('ddx(P)' in node.properties.get('code', '') for node in expressions)


def test_original_no_argument_forest_call_still_reads_its_generated_metadata(monkeypatch, tmp_path):
    forest, saved, created, _, expressions, _ = narrow_forest(monkeypatch)
    metadata = tmp_path / 'hidamari/north_snow.json'
    metadata.parent.mkdir()
    metadata.write_text('{"south_join_m":1234.5}')
    forest.yori.OUT = tmp_path
    result = forest.material()
    assert created == saved == [result]
    assert any('smoothstep(123450.,153450.,-P.y)' in node.properties.get('code', '') for node in expressions)
