"""Slice declarations and the original narrow map body, without starting Unreal."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tarfile
from types import SimpleNamespace

import pytest

GAME = Path(__file__).resolve().parents[1]


def load(relative, name):
    spec = importlib.util.spec_from_file_location(name, GAME / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


units = load('v2_map_units.py', 'v2_map_units_test')
body = load('world/map_v2.py', 'v2_map_body_test')


def reference(package, **extra):
    return {'unit': package.rsplit('/', 1)[-1] + '.finish', 'item': 'asset', 'package': package, **extra}


def declaration(**overrides):
    values = {'world': {'unit': 'world.plan', 'item': 'world', 'file': 'world.json'},
              'painterly': reference('/Game/Japan/Materials/M_Painterly'),
              'terrain': {'Land': [reference('/Game/Japan/Island/Land/Piece', piece='Piece')], 'Sea': []}}
    values.update(overrides)
    return units.author_units(**values)


def test_map_has_one_exact_umap_owner_and_all_actual_inputs():
    result = declaration()
    unit, = result['units']
    assert unit['op'] == {'kind': 'unreal.author', 'version': '1'}
    assert [row['source'] for row in unit['inputs']] == [
        {'kind': 'item', 'unit': 'world.plan', 'item': 'world'},
        {'kind': 'item', 'unit': 'M_Painterly.finish', 'item': 'asset'},
        {'kind': 'item', 'unit': 'Piece.finish', 'item': 'asset'}]
    output, = unit['outputs']
    assert output['logical_path'] == body.PACKAGE and output['class'] == 'Map'
    assert output['files'][0] == {'path': 'content/Game/Japan/Maps/Slice.umap',
        'install_path': 'games/yorimichi/unreal/Content/Japan/Maps/Slice.umap', 'required': True}
    assert not any(row['required'] for row in output['files'][1:])
    assert set(unit['code']) == set(units.CODE)
    assert set(result['staged_inputs'][unit['id']]) == {'world', 'painterly', 'terrain_1'}
    assert not any(result['content_slots'].values())
    assert 'Sea' not in unit['params']['args']['terrain']


def test_native_follower_descriptor_is_preserved_for_normal_before_key_expansion():
    descriptor = {'derived_items': {'root': 'build/v2-derived/island/Land', 'templates': [
        {'producer': 'land.plan', 'group': 'geometry', 'unit_prefix': 'land.export', 'follower': 1, 'item': 'asset'}]}}
    result = declaration(terrain={'Land': descriptor})
    assert result['units'][0]['params']['args']['terrain'] == {'Land': descriptor}
    assert len(result['units'][0]['inputs']) == 2
    descriptor['derived_items']['templates'][0]['follower'] = 0
    assert result['units'][0]['params']['args']['terrain']['Land']['derived_items']['templates'][0]['follower'] == 1


@pytest.mark.parametrize('overrides', [
    {'world': {'unit': 'w', 'item': 'world', 'file': '../world.json'}},
    {'painterly': reference('/Game/AtelierRaw/NotFinished')},
    {'terrain': {}},
    {'terrain': {'Land': {'derived_items': {'root': 'pieces', 'templates': [
        {'producer': 'p', 'group': 'g', 'unit_prefix': 'u'}]}}}},
])
def test_missing_or_unfinished_references_refuse(overrides):
    with pytest.raises(ValueError):
        declaration(**overrides)


class Node:
    def __init__(self):
        self.properties = {}
    def __getattr__(self, name):
        if name in ('light_component', 'component', 'settings', 'static_mesh_component'):
            child = Node()
            setattr(self, name, child)
            return child
        return lambda *args, **kwargs: True
    def set_editor_property(self, key, value):
        self.properties[key] = value
    def get_editor_property(self, key):
        return self.properties[key]


class Mesh(Node):
    pass


def context(tmp_path, *, dynamic=False):
    unit = declaration()['units'][0]
    args = unit['params']['args']
    data = tmp_path / 'world.json'
    data.write_text(json.dumps({'player_start': [1, 2, 3, 45]}))
    slot = 'terrain_1'
    if dynamic:
        del args['native'][slot]
        args['terrain']['Land'] = {'derived_items': {'root': 'derived/Land', 'members': [
            {'piece': 'Piece', 'root': 'derived/Land/Piece', 'slot': 'derived_0'}]}}
        slot = 'derived_0'
    return SimpleNamespace(params=unit['params'], outputs=[body.PACKAGE],
        inputs={'world': str(data), 'painterly': '/Game/Japan/Materials/M_Painterly', slot: '/Game/Japan/Island/Land/Piece'},
        packages={'world': [], 'painterly': ['/Game/Japan/Materials/M_Painterly'], slot: ['/Game/Japan/Island/Land/Piece']})


def fake_unreal(monkeypatch, *, save=True, blanks=(object(), object())):
    calls = []
    worlds = iter(blanks)
    def blank(flag):
        calls.append(('blank', flag))
        return next(worlds)
    def save_map(world, package):
        calls.append(('save', package))
        return save
    def load_asset(package):
        calls.append(('load', package))
        return Mesh() if '/Island/' in package else Node()
    fake = SimpleNamespace(log=lambda value: calls.append(('log', value)), StaticMesh=Mesh,
        EditorAssetLibrary=SimpleNamespace(load_asset=load_asset), EditorActorSubsystem=object,
        get_editor_subsystem=lambda _: SimpleNamespace(spawn_actor_from_class=lambda *args: Node()),
        EditorLoadingAndSavingUtils=SimpleNamespace(new_blank_map=blank, save_map=save_map))
    for name in ('StaticMeshActor', 'DirectionalLight', 'SkyLight', 'ExponentialHeightFog', 'PostProcessVolume', 'PlayerStart'):
        setattr(fake, name, type(name, (), {}))
    for name in ('Vector', 'Vector4', 'Rotator', 'LinearColor', 'Name', 'ExponentialHeightFogData', 'WeightedBlendables', 'WeightedBlendable'):
        setattr(fake, name, lambda *args, **kwargs: (args, kwargs))
    fake.ComponentMobility = SimpleNamespace(STATIC=1, MOVABLE=2)
    fake.AutoExposureMethod = SimpleNamespace(AEM_HISTOGRAM=1)
    fake.DynamicGlobalIlluminationMethod = SimpleNamespace(LUMEN=1)
    monkeypatch.setitem(sys.modules, 'unreal', fake)
    return calls


@pytest.mark.parametrize('dynamic', [False, True])
def test_original_builder_executes_from_declared_inputs_and_releases_world(tmp_path, monkeypatch, dynamic):
    calls = fake_unreal(monkeypatch)
    body.run(context(tmp_path, dynamic=dynamic))
    assert [call for call in calls if call[0] == 'save'] == [('save', body.PACKAGE)]
    assert [call for call in calls if call[0] == 'blank'] == [('blank', False), ('blank', False)]
    assert calls[-1] == ('blank', False)
    assert not (tmp_path / 'setup_report.txt').exists()
    assert 'setup_project' not in sys.modules


@pytest.mark.parametrize('save,blanks', [(False, (object(),)), (True, (None,)), (True, (object(), None))])
def test_original_save_and_blank_world_failures_refuse(tmp_path, monkeypatch, save, blanks):
    fake_unreal(monkeypatch, save=save, blanks=blanks)
    with pytest.raises(RuntimeError):
        body.run(context(tmp_path))


def test_undeclared_or_raw_terrain_refuses_before_native_loading(tmp_path, monkeypatch):
    calls = fake_unreal(monkeypatch)
    value = context(tmp_path)
    value.packages['terrain_1'] = ['/Game/AtelierRaw/Piece']
    with pytest.raises(ValueError):
        body.run(value)
    assert not any(call[0] == 'save' for call in calls)


def test_actual_selected_world_root_payload_and_finite_player_start(tmp_path):
    data = json.dumps({'player_start': [1, 2, 3, 4]}).encode()
    source = tmp_path / 'world.tree.tar'
    manifest = {'version': 1, 'kind': 'file', 'entries': [['', 'file', len(data), 420, hashlib.sha256(data).hexdigest()]]}
    with tarfile.open(source, 'w') as archive:
        for name, payload in [('atelier-root.json', json.dumps(manifest).encode()), ('root', data)]:
            header = tarfile.TarInfo(name)
            header.size = len(payload)
            archive.addfile(header, io.BytesIO(payload))
    value = SimpleNamespace(inputs={'world': str(source)})
    assert body.world_data(value, {'file': 'products/world.tree.tar'})['player_start'] == [1, 2, 3, 4]
    with pytest.raises(ValueError):
        body.world_data(value, {'file': source.name, 'member': 'missing.json'})
    plain = tmp_path / 'invalid.json'
    plain.write_text('{"player_start": [1, 2, 3, NaN]}')
    with pytest.raises(ValueError):
        body.world_data(SimpleNamespace(inputs={'world': str(plain)}), {'file': plain.name})
