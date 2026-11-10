"""Material acceptance must retain upstream wiring even when several expressions have identical local properties."""
import copy
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / 'unreal/Scripts/master_digest.py'
SPEC = importlib.util.spec_from_file_location('v2_master_topology_digest', SCRIPT)
digest = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(digest)


class Asset:
    def __init__(self, path):
        self.path = path

    def get_path_name(self):
        return self.path


class Node(Asset):
    def __init__(self, path, props, inputs):
        super().__init__(path)
        self.props, self.inputs = props, inputs

    def get_editor_property(self, key):
        return self.props[key]


def node(cls, name, *, inputs=(), **props):
    return type(cls, (Node,), {})(name, props, list(inputs))


class Material:
    def __init__(self, nodes, roots):
        self.nodes, self.roots = nodes, roots
        self.settings = {key: False for key in digest.SETTINGS}

    def get_editor_property(self, key):
        return self.settings[key]


class Editing:
    get_material_expressions = staticmethod(lambda material: material.nodes)
    get_material_property_input_node = staticmethod(lambda material, pin: material.roots.get(pin, (None, ''))[0])
    get_material_property_input_node_output_name = staticmethod(lambda material, pin: material.roots[pin][1])
    get_inputs_for_material_expression = staticmethod(lambda material, expression: [edge[1] for edge in expression.inputs])
    get_material_expression_input_names = staticmethod(lambda expression: [edge[0] for edge in expression.inputs])

    @staticmethod
    def get_input_node_output_name_for_material_expression(expression, source):
        return next(edge[2] for edge in expression.inputs if edge[1] is source)


@pytest.fixture(autouse=True)
def engine(monkeypatch):
    properties = SimpleNamespace(**{pin: pin for pin in digest.PROPERTY_PINS})
    monkeypatch.setattr(digest, 'U', SimpleNamespace(MaterialEditingLibrary=Editing, MaterialProperty=properties))


def retail(*, swapped=False, renamed=False):
    """Two identically configured multiplies scale different texture branches, as in the retail master."""
    uv = node('MaterialExpressionTextureCoordinate', 'uv', coordinate_index=0)
    macro = node('MaterialExpressionScalarParameter', 'macro', parameter_name='MacroScale', default_value=2.0)
    detail = node('MaterialExpressionScalarParameter', 'detail', parameter_name='DetailScale', default_value=4.0)
    one = node('MaterialExpressionMultiply', 'one', const_a=0.0, const_b=1.0,
               inputs=[('A', uv, ''), ('B', detail if swapped else macro, '')])
    two = node('MaterialExpressionMultiply', 'two', const_a=0.0, const_b=1.0,
               inputs=[('A', uv, ''), ('B', macro if swapped else detail, '')])
    first = node('MaterialExpressionTextureSample', 'macro-texture', texture=Asset('/Game/Macro'),
                 inputs=[('UV', one, '')])
    second = node('MaterialExpressionTextureSample', 'detail-texture', texture=Asset('/Game/Detail'),
                  inputs=[('UV', two, '')])
    final = node('MaterialExpressionAdd', 'sum', inputs=[('A', first, 'RGB'), ('B', second, 'RGB')])
    nodes = [uv, macro, detail, one, two, first, second, final]
    if renamed:
        nodes.reverse()
        for index, expression in enumerate(nodes):
            expression.path = f'/Transient/Rebuilt/Expression_{index}'
            expression.props['desc'] = 'editor annotation only'
    return Material(nodes, {'MP_BASE_COLOR': (final, '')})


def test_swapping_scales_between_identical_multiplies_cannot_hide_in_edge_multisets():
    """@cc [owner:fontanierh,label:correctness] master-topology-retail-rewire
    Swapping MacroScale and DetailScale between identical Multiply nodes MUST reject even when all legacy edge and node
    multisets are unchanged, because the two texture branches then render different scales."""
    saved, changed = digest.read(retail()), digest.read(retail(swapped=True))
    for key in digest.LISTS:
        assert sorted(saved[key]) == sorted(changed[key])
    assert set(saved['parameters']) == set(changed['parameters'])
    assert digest.accept(saved, changed) == ['rendered topology differs at MP_BASE_COLOR']


def test_engine_enumeration_names_and_editor_annotations_do_not_change_acceptance():
    assert digest.accept(digest.read(retail()), digest.read(retail(renamed=True))) == []


@pytest.mark.parametrize('channel', ['g', 'b', 'a'])
def test_component_mask_channel_changes_reject(channel):
    mask = node('MaterialExpressionComponentMask', 'mask', r=True, g=False, b=False, a=False)
    material = Material([mask], {'MP_BASE_COLOR': (mask, '')})
    saved = digest.read(material)
    mask.props[channel] = True
    assert digest.accept(saved, digest.read(material))


@pytest.mark.parametrize('setting', ['is_sky', 'blendable_location', 'dithered_lod_transition',
                                     'tangent_space_normal', 'compute_fog_per_pixel'])
def test_upcoming_render_settings_are_compared(setting):
    material = retail()
    saved = digest.read(material)
    material.settings[setting] = True
    assert any(problem.startswith(setting + ':') for problem in digest.accept(saved, digest.read(material)))


@pytest.mark.parametrize(('prop', 'before', 'after'), [
    ('scene_texture_id', 'PPI_SceneColor', 'PPI_WorldNormal'),
    ('collection', Asset('/Game/Wind'), Asset('/Game/OtherWind')),
    ('material_function', Asset('/Game/Atmosphere'), Asset('/Game/OtherAtmosphere')),
    ('use_custom_primitive_data', False, True),
    ('primitive_data_index', 0, 1),
])
def test_upcoming_expression_inputs_are_compared(prop, before, after):
    expression = node('MaterialExpressionInput', 'input', **{prop: before})
    material = Material([expression], {'MP_BASE_COLOR': (expression, '')})
    saved = digest.read(material)
    expression.props[prop] = after
    assert digest.accept(saved, digest.read(material))


@pytest.mark.parametrize('legacy', [None, {'version': 1, 'roots': {}}, {'version': 2}])
def test_lossy_or_incomplete_reports_need_new_reads(legacy):
    saved = digest.read(retail())
    old = copy.deepcopy(saved)
    if legacy is None:
        del old['topology']
    else:
        old['topology'] = legacy
    for left, right in [(old, saved), (saved, old), (old, old)]:
        assert 'collect a new read-only report' in digest.accept(left, right)[0]


def test_input_order_and_output_selection_are_part_of_the_rooted_graph():
    material = retail()
    saved = digest.read(material)
    root = material.roots['MP_BASE_COLOR'][0]
    root.inputs.reverse()
    assert saved['topology'] != digest.read(material)['topology']
    root.inputs.reverse()
    name, source, _ = root.inputs[0]
    root.inputs[0] = (name, source, 'R')
    assert saved['topology'] != digest.read(material)['topology']


def test_a_cycle_is_unreadable_and_never_accepted():
    expression = node('MaterialExpressionMultiply', 'cycle')
    expression.inputs = [('A', expression, '')]
    failed = digest.read(Material([expression], {'MP_BASE_COLOR': (expression, '')}))
    assert 'cycle' in failed['error']
    assert digest.accept(failed, failed)


def test_an_api_that_cannot_distinguish_repeated_source_outputs_refuses():
    source = node('MaterialExpressionTextureSample', 'texture', texture=Asset('/Game/Texture'))
    mix = node('MaterialExpressionAdd', 'mix', inputs=[('A', source, 'R'), ('B', source, 'G')])
    failed = digest.read(Material([source, mix], {'MP_BASE_COLOR': (mix, '')}))
    assert 'cannot read distinct output selections' in failed['error']
    assert digest.accept(failed, failed)
