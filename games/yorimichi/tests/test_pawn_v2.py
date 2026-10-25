"""Pawn author body and registration writer against a fake editor; no Unreal launch."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

ROOT = Path(__file__).resolve().parents[3]
WORLD = ROOT / 'games/yorimichi/world'
sys.path.insert(0, str(ROOT / 'games/yorimichi'))


def load(name):
    spec = importlib.util.spec_from_file_location(name, WORLD / (name + '.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


body, registration = load('pawn_v2'), load('character_registration_v2')
import v2_pawn_units as pawns  # noqa: E402
CAIRO = pawns._definition(ROOT).load('cairo')
BLUEPRINT, DEFAULTS, COMPONENTS, RECORD = pawns.values(CAIRO)


class Vector:
    def __init__(self, x, y, z): self.x, self.y, self.z = x, y, z


class Props:
    def __init__(self, **values): self.values = dict(values)
    def get_editor_property(self, name): return self.values[name]
    def set_editor_property(self, name, value): self.values[name] = value


class MoverCharacter(Props):
    @staticmethod
    def static_class(): return 'MoverCharacter'


class Asset:
    def __init__(self, path): self.path = path
    def get_path_name(self): return self.path + '.' + self.path.rpartition('/')[2]


@pytest.fixture
def case(tmp_path, monkeypatch):
    record = tmp_path / 'inputs/adventure'; record.mkdir(parents=True)
    (record / 'adventure.json').write_text('{"moves": []}')
    move_set = CAIRO.adventure['definition']
    assets = {move_set: Asset(move_set)}
    events = []
    state = NS(assets=assets, events=events, save_ok=True, drift=None, parent=MoverCharacter)
    cdo_holder = {}
    class Blueprint(Asset):
        def modify(self): events.append(('modify', self.path))
    def create(name, path, cls, factory):
        events.append(('create', path + '/' + name, factory.values['parent_class']))
        bp = Blueprint(path + '/' + name); assets[bp.path] = bp
        cdo = state.parent(**{key: None for key in DEFAULTS}, capsule_component=Props(), character_movement=Props(), mesh=Props())
        cdo_holder[bp.path] = cdo
        return bp
    generated = lambda bp: NS(bp=bp, get_path_name=lambda: bp.get_path_name() + '_C')
    def default_object(cls):
        cdo = cdo_holder[cls.bp.path]
        if state.drift and events and events[-1][0] == 'save':
            cdo.values[state.drift] = 'drifted'
        return cdo
    def save(path, only_if_is_dirty):
        events.append(('save', path)); assert only_if_is_dirty is False; return state.save_ok
    unreal = NS(Vector=Vector, MoverCharacter=MoverCharacter, Blueprint=Blueprint,
                BlueprintFactory=lambda: Props(), get_default_object=default_object,
                BlueprintEditorLibrary=NS(compile_blueprint=lambda bp: events.append(('compile', bp.path)),
                                          generated_class=generated),
                AssetToolsHelpers=NS(get_asset_tools=lambda: NS(create_asset=create)),
                EditorAssetLibrary=NS(load_asset=lambda path: assets.get(path), does_asset_exist=lambda path: path in assets,
                                      save_asset=save))
    monkeypatch.setitem(sys.modules, 'unreal', unreal)
    context = NS(job_dir=str(tmp_path), inputs={'definition': str(tmp_path / 'inputs/definition'), 'adventure': str(record)},
                 packages={'definition': [move_set], 'adventure': []}, outputs=[BLUEPRINT],
                 params={'settings': [], 'args': {'character': 'cairo', 'blueprint': BLUEPRINT, 'pawn': CAIRO.pawn,
                         'definition': DEFAULTS['definition_path'], 'defaults': deepcopy(DEFAULTS),
                         'components': deepcopy(COMPONENTS), 'inputs': {'definition': 'definition', 'adventure': 'adventure'}}})
    return state, context, cdo_holder


def test_blueprint_is_created_applied_compiled_saved_and_read_back(case):
    state, context, cdos = case
    bp = body.run(context)
    assert bp.path == BLUEPRINT
    assert [event[0] for event in state.events] == ['create', 'compile', 'modify', 'compile', 'save']
    assert state.events[0][2] == 'MoverCharacter'
    cdo = cdos[BLUEPRINT]
    assert cdo.values['definition_path'] == DEFAULTS['definition_path'] == '/Game/CairoAdventure/DA_CairoAdventure.DA_CairoAdventure'
    assert cdo.values['hair_spring_morphs'] == ['head_Hair_fore', 'head_Hair_side']
    assert cdo.values['capsule_component'].values == {'capsule_radius': 22.0, 'capsule_half_height': 74.0}
    location = cdo.values['mesh'].values['relative_location']
    assert (location.x, location.y, round(location.z, 6)) == (0.0, 0.0, -74.65)


@pytest.mark.parametrize('failure', ['outputs', 'existing', 'definition_missing', 'definition_other', 'record',
                                     'readback', 'save', 'parent', 'pawn', 'unknown_arg', 'defaults_definition'])
def test_invalid_inputs_or_native_state_refuse(case, failure, tmp_path):
    state, context, _ = case
    args = context.params['args']
    if failure == 'outputs': context.outputs = [BLUEPRINT, '/Game/Cairo/Other']
    elif failure == 'existing': state.assets[BLUEPRINT] = Asset(BLUEPRINT)
    elif failure == 'definition_missing': del state.assets[CAIRO.adventure['definition']]
    elif failure == 'definition_other': context.packages['definition'] = ['/Game/Paul/DA_Paul']
    elif failure == 'record': (tmp_path / 'inputs/adventure/adventure.json').unlink()
    elif failure == 'readback': state.drift = 'bike_rig'
    elif failure == 'save': state.save_ok = False
    elif failure == 'parent': state.parent = Props
    elif failure == 'pawn': args['pawn'] = '/Game/Cairo/BP_Other.BP_Other_C'
    elif failure == 'unknown_arg': args['extra'] = True
    elif failure == 'defaults_definition': args['defaults']['definition_path'] = '/Game/X/DA_X.DA_X'
    with pytest.raises(ValueError):
        body.run(context)
    if failure not in ('readback',):
        assert ('save', BLUEPRINT) not in state.events or failure == 'save'


def test_registration_writes_the_original_record_only_after_the_blueprint(tmp_path):
    blueprint = tmp_path / 'BP_Cairo.uasset'
    output = tmp_path / 'Data/cairo/character.json'
    text = json.dumps(RECORD)
    with pytest.raises(ValueError, match='produced Blueprint'):
        registration.main(['--record', text, '--blueprint', str(blueprint), '--output', str(output)])
    assert not output.exists()
    blueprint.write_bytes(b'\xc1\x83\x2a\x9e package')
    registration.main(['--record', text, '--blueprint', str(blueprint), '--output', str(output)])
    assert output.read_text() == json.dumps(RECORD, indent=1) + '\n'
    assert json.loads(output.read_text())['class'] == '/Game/Cairo/BP_Cairo.BP_Cairo_C'
    assert not (output.parent / 'character.json.partial').exists()


@pytest.mark.parametrize('change', ['field', 'order', 'default', 'class', 'path', 'magic', 'other_blueprint'])
def test_registration_refuses_reshaped_records_or_blueprints(tmp_path, change):
    blueprint = tmp_path / 'BP_Cairo.uasset'; blueprint.write_bytes(b'\xc1\x83\x2a\x9e package')
    output = tmp_path / 'Data/cairo/character.json'
    record = dict(RECORD)
    if change == 'field': record['extra'] = 1
    elif change == 'order': record = dict(reversed(list(record.items())))
    elif change == 'default': record['default'] = 'yes'
    elif change == 'class': record['class'] = '/Game/Cairo/BP_Cairo.BP_Cairo'
    elif change == 'path': output = tmp_path / 'Data/paul/character.json'
    elif change == 'magic': blueprint.write_bytes(b'not a package')
    elif change == 'other_blueprint':
        blueprint = tmp_path / 'BP_Paul.uasset'; blueprint.write_bytes(b'\xc1\x83\x2a\x9e package')
    with pytest.raises(ValueError):
        registration.main(['--record', json.dumps(record), '--blueprint', str(blueprint), '--output', str(output)])
    assert not output.exists()
