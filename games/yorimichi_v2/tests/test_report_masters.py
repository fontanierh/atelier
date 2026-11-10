"""The read-only master report (unreal/Scripts/report_masters.py): its pure part on fake expressions, the output refusal,
and the 19 masters' list. The Unreal calls are not run here; the module loads against a stub `unreal`."""
import importlib.util
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'unreal' / 'Scripts' / 'report_masters.py'
LIST = ROOT / 'docs' / 'inventory' / 'small-families-masters.txt'


class Color:
    def __init__(self, r, g, b, a):
        self.r, self.g, self.b, self.a = r, g, b, a


class Texture:
    def __init__(self, path):
        self.path = path

    def get_path_name(self):
        return self.path + '.' + self.path.rsplit('/', 1)[1]


@pytest.fixture
def module(monkeypatch):
    stub = types.ModuleType('unreal')
    stub.EditorAssetLibrary = stub
    stub.log = lambda message: None
    monkeypatch.setitem(sys.modules, 'unreal', stub)
    spec = importlib.util.spec_from_file_location('report_masters_under_test', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)   # main() runs only as __main__
    return module


def test_the_parameters_come_from_their_expression_classes(module):
    graph = [
        ('MaterialExpressionScalarParameter', {'parameter_name': 'Tile', 'default_value': 4}),
        ('MaterialExpressionVectorParameter', {'parameter_name': 'Tint', 'default_value': Color(1, .5, 0, 1)}),
        ('MaterialExpressionTextureSampleParameter2D', {'parameter_name': 'Tex', 'texture': Texture('/Game/A/T_one')}),
        ('MaterialExpressionStaticSwitchParameter', {'parameter_name': 'bHasX', 'default_value': 1}),
        ('MaterialExpressionMultiply', {}),
    ]
    out = module.describe(graph)
    assert out['parameters']['scalar'] == {'Tile': 4.0}
    assert out['parameters']['vector'] == {'Tint': [1, .5, 0, 1]}
    assert out['parameters']['texture'] == {'Tex': '/Game/A/T_one'}
    assert out['parameters']['static_switch'] == {'bHasX': True}
    assert out['textures'] == ['/Game/A/T_one']


def test_a_name_is_recorded_once_with_its_first_default(module):
    graph = [('MaterialExpressionScalarParameter', {'parameter_name': 'Gloss', 'default_value': .2}),
             ('MaterialExpressionScalarParameter', {'parameter_name': 'Gloss', 'default_value': .9})]
    assert module.describe(graph)['parameters']['scalar'] == {'Gloss': .2}


def test_an_unreadable_default_is_null_not_a_guess(module):
    graph = [('MaterialExpressionScalarParameter', {'parameter_name': 'Tile', 'default_value': None})]
    assert module.describe(graph)['parameters']['scalar'] == {'Tile': None}


def test_a_texture_sample_without_a_parameter_name_adds_only_its_texture(module):
    graph = [('MaterialExpressionTextureSample', {'texture': Texture('/Game/A/T_plain')})]
    out = module.describe(graph)
    assert out['parameters']['texture'] == {} and out['textures'] == ['/Game/A/T_plain']


def test_the_output_inside_the_game_tree_is_refused(module, tmp_path):
    game = tmp_path / 'game'
    game.mkdir()
    with pytest.raises(ValueError):
        module.report_target(str(game / 'report.json'), game=str(game))
    assert module.report_target(str(tmp_path / 'outside.json'), game=str(game)).endswith('outside.json')


def test_the_package_list_is_the_nineteen_masters():
    names = LIST.read_text().split()
    assert len(names) == 19 and len(set(names)) == 19
    assert all(n.startswith('/Game/') for n in names)
    assert sum('/Hippodrome/' in n for n in names) == 5 and sum('/SkatePark/' in n for n in names) == 8
    assert sum('/FX/' in n for n in names) == 3 and sum('/SwordCamp/' in n for n in names) == 2
