"""Prepared Japan surface graphs traced against donor 7eec0f98dd, without running Unreal.

The pins below were produced from the original donor functions and helpers, including the fresh see-through pass, not from the port. Only
asset creation/loading/saving/compilation calls are excluded; graph calls and material settings remain.
The port is compared to those traces. Native before/after acceptance is still the controller's work.
"""
import hashlib
import inspect
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/content'))
sys.path.insert(0, str(ROOT / 'tools/migrate'))
sys.path.insert(0, str(ROOT / 'unreal/Scripts'))
import records  # noqa: E402
import master_records as planner  # noqa: E402
import master_sources  # noqa: E402

FAMILY = planner.load_families()['japan_surfaces']
MASTERS = {row['builder']: row for row in FAMILY['masters']}
sources = planner.builder_sources(FAMILY)
with master_sources.builder(sources, 'painted_material') as entry:
    builders = sys.modules[entry.__module__]


class Recorder:
    """Record calls using stable symbol names, never a process-dependent object representation."""

    def __init__(self, name, log, answers):
        self._name, self._log, self._answers = name, log, answers

    def __getattr__(self, name):
        if name.startswith('__'):
            raise AttributeError(name)
        return Recorder(name, self._log, self._answers)

    def __call__(self, *args):
        self._log.append((self._name, tuple(show(arg) for arg in args)))
        return self._answers.get(self._name, Recorder(f'{self._name}()', self._log, self._answers))


def show(value):
    if isinstance(value, Recorder):
        return f'<{value._name}>'
    if isinstance(value, list):
        return '[' + ', '.join(show(v) for v in value) + ']'
    return repr(value)


PLUMBING = {'get_asset_tools', 'save_loaded_asset', 'load_asset', 'load_object', 'does_asset_exist',
            'MaterialFactoryNew', 'create_asset', 'delete_all_material_expressions', 'recompile_material'}
DONOR_TRACES = {'painted_material': (124, '8233a82fb754ee9f343dd3e979c13437123f2ac525910741471e48df035a34bd'),
 'foliage_material': (295, '3336c19126a014377724872abd42f2a63861b3b9485fba1b35815c245cb85c9f'),
 'grass_material': (277, '15003655adb512ad2e1ff5b214fcaa94d4cc3f8435b03ddde7b960c7e47d17e4'),
 'village_material': (61, 'cf0793f695f3463deae3b3ce5608c13817d6b1428bb5fa46eb29c6a7a7191c20')}
VALUES = {'white': 'WHITE', 'wind': 'WIND', 'coverage': 'COVERAGE', 'see_through': 'SEE_THROUGH'}


def trace(name, missing=None):
    row = MASTERS[name]
    loaded = {path: VALUES[key] for key, path in row['arguments'].items()}
    if missing is not None:
        loaded.pop(missing)
    log = []
    original = builders.unreal
    answers = {'does_asset_exist': False, 'recompile_material': None}
    if name == 'painted_material':
        answers['get_material_property_input_node'] = None
    builders.unreal = Recorder('unreal', log, answers)
    try:
        getattr(builders, name)(row['package'], loaded, **row['arguments'])
    finally:
        builders.unreal = original
    return log


def named(log, method):
    return [args for name, args in log if name == method]


def test_family_names_exactly_the_four_reserved_masters_and_all_reads_have_owners():
    assert {row['package'].rsplit('/', 1)[1] for row in MASTERS.values()} == {
        'M_Painted', 'M_Foliage', 'M_Grass', 'M_Village'}
    assert FAMILY['helpers'] == ['master_haze.py']
    assert not set(FAMILY['keeps']) & {row['package'] for row in MASTERS.values()}
    for row in MASTERS.values():
        inspect.signature(getattr(builders, row['builder'])).bind(row['package'], {}, **row['arguments'])
        owned = {out.package for source in row['inputs']
                 for out in records.load_asset(ROOT / 'assets' / source / 'asset.toml').outputs}
        assert {p for p in row['reads'] if p.startswith('/Game/')} <= owned
        assert set(row['arguments'].values()) == set(row['reads'])


@pytest.mark.parametrize('name', list(MASTERS))
def test_surface_graph_call_trace_matches_the_original_donor(name):
    log = trace(name)
    graph = [entry for entry in log if entry[0] not in PLUMBING]
    assert (len(graph), hashlib.sha256(repr(graph).encode()).hexdigest()) == DONOR_TRACES[name]
    calls = {method for method, _ in log}
    assert not calls & {'save_asset', 'save_loaded_asset', 'import_asset_tasks', 'load_asset', 'load_object'}
    assert 'recompile_material' in calls


@pytest.mark.parametrize(('name', 'missing'), [(row['builder'], path) for row in MASTERS.values() for path in row['reads']])
def test_missing_declared_read_refuses_before_material_creation(name, missing, monkeypatch):
    row = MASTERS[name]
    loaded = {path: VALUES[key] for key, path in row['arguments'].items() if path != missing}
    log = []
    monkeypatch.setattr(builders, 'unreal', Recorder('unreal', log, {}))
    with pytest.raises(KeyError):
        getattr(builders, name)(row['package'], loaded, **row['arguments'])
    assert log == []


def test_grass_keeps_upward_normals_temporal_coverage_and_gentle_wind():
    """@cc [owner:fontanierh,label:correctness] japan-grass-keeps-coverage-and-normal
    The prepared grass graph carries the donor normal mode, upward constant, temporal coverage function and wind scale.
    These are graph checks; native before/after acceptance is required separately.
    """
    log = trace('grass_material')
    properties = named(log, 'set_editor_property')
    assert ("'tangent_space_normal'", 'False') in properties
    assert ("'dithered_lod_transition'", 'True') in properties
    assert ('0', '0', '1', '1') in named(log, 'LinearColor')
    assert named(log, 'set_material_function') == [("'COVERAGE'",)]
    assert ("'const_b'", '0.28') in properties
    assert any(args[-1] == '<MP_WORLD_POSITION_OFFSET>' for args in named(log, 'connect_material_property'))


def test_foliage_keeps_the_wind_collection_and_both_parameter_names():
    properties = named(trace('foliage_material'), 'set_editor_property')
    assert properties.count(("'collection'", "'WIND'")) == 2
    assert ("'parameter_name'", "'Wind'") in properties
    assert ("'parameter_name'", "'PlayerPos'") in properties
    assert ("'opacity_mask_clip_value'", '0.4') in properties


def test_haze_keeps_the_donor_depth_and_colours():
    assert builders.haze.code_base() == 'return (B)*(1-saturate(1-exp(-max(D-3000.0,0)/900000.0)));'
    assert builders.haze.code_glow() == ('float h=saturate(1-exp(-max(D-3000.0,0)/900000.0)); '
                                    'return (E)*(1-h)+float3(0.0932,0.2301,0.5328)*h;')


def test_camera_fade_keeps_shared_collection_and_per_instance_mode():
    for name in ('painted_material', 'foliage_material', 'grass_material'):
        log = trace(name)
        props = named(log, 'set_editor_property')
        assert ("'parameter_name'", "'FadeMode'") in props
        assert ("'use_custom_primitive_data'", 'True') in props
        assert ("'primitive_data_index'", '0') in props
        assert ("'collection'", "'SEE_THROUGH'") in props
        assert ("'parameter_name'", "'CutScale'") in props
        assert named(log, 'connect_material_property')[-1][-1] == '<MP_OPACITY_MASK>'
        classes = [args[1] for args in named(log, 'create_material_expression')]
        assert '<MaterialExpressionShadowReplace>' in classes
        assert ('<MaterialExpressionVertexInterpolator>' in classes) == (name != 'grass_material')
