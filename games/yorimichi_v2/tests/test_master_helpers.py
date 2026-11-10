"""The helper group's material-master builders (Sword Camp and Hidamari city) and their families.

The builders run against the same recording stand-in for unreal as test_master_importer.py. Each builder's traced calls are
pinned by a sha256 of the trace, and those traces were produced by running the donor functions (games/yorimichi at the
baseline 7eec0f98dd, import_swordcamp.py and city_material.py) through the same stand-in, call for call. The donor is not in
this tree, so the pins are the record of that check. Nothing here runs Unreal and nothing reads the donor checkout."""
import hashlib
import importlib.util
import inspect
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'unreal/Scripts'
sys.path.insert(0, str(ROOT / 'tools' / 'content'))
sys.path.insert(0, str(ROOT / 'tools' / 'migrate'))
import records  # noqa: E402
import master_records as planner  # noqa: E402

FAMILIES = planner.load_families()
SWORD = FAMILIES['swordcamp']
CITY = FAMILIES['hidamari_city']
GAME = ROOT


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


source_loader = _load_module('v2_master_sources', SCRIPTS / 'master_sources.py')


def _load_family(family):
    with source_loader.builder(planner.builder_sources(family), family['masters'][0]['builder']) as builder:
        # Retain the module object for the existing traces, without leaving it in the process import cache.
        return sys.modules[builder.__module__]


sword = _load_family(SWORD)
city = _load_family(CITY)


# --- the recording stand-in, as in test_master_importer.py -----------------------------------------------------------------

class Recorder:
    """Every attribute is a stand-in and every call is logged as (method name, shown arguments). A call returns a stand-in,
    except the names given in `answers`."""

    def __init__(self, name, log, answers):
        self._name, self._log, self._answers = name, log, answers

    def __getattr__(self, name):
        if name.startswith('__'):
            raise AttributeError(name)
        return Recorder(name, self._log, self._answers)

    def __call__(self, *args):
        self._log.append((self._name, tuple(show(a) for a in args)))
        return self._answers.get(self._name, Recorder(f'{self._name}()', self._log, self._answers))


def show(value):
    if isinstance(value, Recorder):
        return f'<{value._name}>'
    if isinstance(value, list):
        return '[' + ', '.join(show(v) for v in value) + ']'
    return repr(value)


# asset plumbing, not graph: the donor loads or creates the material and saves it; the builder only reads or creates it
PLUMBING = {'get_asset_tools', 'save_loaded_asset', 'load_asset'}


def trace(module, builder, *args, **kwargs):
    log = []
    original = module.unreal
    module.unreal = Recorder('unreal', log, {'does_asset_exist': False})
    try:
        getattr(module, builder)(*args, **kwargs)
    finally:
        module.unreal = original
    return [entry for entry in log if entry[0] not in PLUMBING]


def digest(log):
    return hashlib.sha256(repr(log).encode()).hexdigest()


def named(log, method):
    return [args for name, args in log if name == method]


CAMP = '/Game/SwordCamp/Materials/M_SwordCamp'
RONIN = '/Game/SwordCamp/Materials/M_RoninBody'
ATLAS = '/Game/SwordCamp/Textures/T_SwordCampAtlas'
HDCITY = '/Game/Japan/Hidamari/Materials/M_HDCity'
PLASTER = '/Game/Japan/Hidamari/Textures/T_HD_plaster'

# the haze strings, as the donor's atmosphere.py builds them from sea_look.py (HAZE_CM 900000.0, START_CM 3000.0, FAR .74)
HAZE_BASE = 'return (B)*(1-saturate(1-exp(-max(D-3000.0,0)/900000.0)));'
HAZE_GLOW = ('float h=saturate(1-exp(-max(D-3000.0,0)/900000.0)); '
             'return (E)*(1-h)+float3(0.0932,0.2301,0.5328)*h;')

# the traced donor calls, pinned by sha256 (see the module docstring)
CAMP_TRACE = '90c93082edf27e81390cab4c2f49fec1c8e808e2803ba8a1b59ed0af1c392394'
RONIN_TRACE = 'f564c737d7c2a5549a3ce521e38fff2bc34822fafd38812622cb226f54705be4'
CITY_TRACE = '1f2eb0c6a5b07d4128c0ddf4e14eac1988264ab154eadc114aa4fd819b3f35bd'


# --- the builders -----------------------------------------------------------------------------------------------------------

def test_the_modules_import_without_the_editor_and_define_the_builders():
    assert sword.unreal is None and city.unreal is None
    for module, names in ((sword, ('build_material', 'build_ronin_body_material')), (city, ('city_parent',))):
        for name in names:
            assert callable(getattr(module, name))


def test_the_haze_is_the_donor_haze_for_the_sea_look_constants():
    assert sword.haze.FAR_COLOUR == city.haze.FAR_COLOUR == (0.0932, 0.2301, 0.5328)
    assert sword.haze.code_base() == city.haze.code_base() == HAZE_BASE
    assert sword.haze.code_glow() == city.haze.code_glow() == HAZE_GLOW


def test_the_camp_material_traces_as_the_donor_build_material():
    log = trace(sword, 'build_material', CAMP, {ATLAS: 'ATLAS'}, texture=ATLAS)
    assert len(log) == 66 and digest(log) == CAMP_TRACE
    # the vertex-colour fill, the haze's base and emissive nodes, then the wind offset, in the donor's order
    codes = [args[1] for args in named(log, 'set_editor_property') if args[0] == "'code'"]
    assert codes == ["'return C*(.06+saturate(G)*.95);'", repr(HAZE_BASE), repr(HAZE_GLOW),
                     "'float phase=T*2.1+P.x*.003+P.y*.004; return float3(sin(phase)*2.4,cos(phase*.85)*1.6,sin(phase*1.4)*.5)*W*W;'"]
    settings = [args for args in named(log, 'set_editor_property') if args[0] in ("'two_sided'", "'used_with_static_lighting'")]
    assert settings == [("'two_sided'", 'True'), ("'used_with_static_lighting'", 'False')]
    constants = [args for args in named(log, 'set_editor_property') if args[0] == "'r'"]
    assert constants == [("'r'", '0.92'), ("'r'", '0.04')]
    assert log[-1][0] == 'recompile_material'


def test_the_ronin_body_traces_as_the_donor_build_ronin_body_material():
    log = trace(sword, 'build_ronin_body_material', RONIN, {ATLAS: 'ATLAS'}, texture=ATLAS)
    assert len(log) == 40 and digest(log) == RONIN_TRACE
    settings = [(args[0], args[1]) for args in named(log, 'set_editor_property')
                if args[0] in ("'blend_mode'", "'two_sided'", "'used_with_skeletal_mesh'", "'used_with_static_lighting'")]
    assert settings == [("'blend_mode'", '<BLEND_OPAQUE>'), ("'two_sided'", 'False'), ("'used_with_skeletal_mesh'", 'True'),
                        ("'used_with_static_lighting'", 'False')]
    constants = [args for args in named(log, 'set_editor_property') if args[0] == "'r'"]
    assert constants == [("'r'", '0.7'), ("'r'", '0.0'), ("'r'", '0.3')]
    assert named(log, 'LinearColor') == [('0.16', '0.3', '0.62', '1.0')]


def test_the_city_parent_traces_as_the_donor_parent():
    log = trace(city, 'city_parent', HDCITY, {PLASTER: 'DEFAULT'}, texture=PLASTER)
    assert len(log) == 91 and digest(log) == CITY_TRACE
    parameters = [args for args in named(log, 'set_editor_property') if args[0] in ("'parameter_name'", "'default_value'")]
    assert parameters == [("'parameter_name'", "'Tex'"), ("'parameter_name'", "'Tile'"), ("'default_value'", '1.5'),
                          ("'parameter_name'", "'Strength'"), ("'default_value'", '1.0'),
                          ("'parameter_name'", "'Macro'"), ("'default_value'", '0.5'),
                          ("'parameter_name'", "'Gain'"), ("'default_value'", '1.0')]
    assert ("'texture'", "'DEFAULT'") in named(log, 'set_editor_property')
    assert named(log, 'set_editor_property').count(("'used_with_instanced_static_meshes'", 'True')) == 1
    constants = [args for args in named(log, 'set_editor_property') if args[0] == "'r'"]
    assert constants == [("'r'", '0.87'), ("'r'", '0.12')]


def test_each_builder_has_the_same_arguments_as_its_family_entry():
    for family in (SWORD, CITY):
        for master in family['masters']:
            module = sword if master['builder'] in ('build_material', 'build_ronin_body_material') else city
            inspect.signature(getattr(module, master['builder'])).bind(
                master['package'], {r: object() for r in master['reads']}, **master['arguments'])


def test_a_builder_makes_no_engine_call_when_a_read_it_needs_is_missing():
    # the reads are the only assets a builder receives: a missing one raises before the material is touched
    log = []
    original = sword.unreal
    sword.unreal = Recorder('unreal', log, {'does_asset_exist': False})
    try:
        with pytest.raises(KeyError):
            sword.build_material(CAMP, {}, texture=ATLAS)
    finally:
        sword.unreal = original
    assert log == []


# --- the families ---------------------------------------------------------------------------------------------------------

def test_the_planner_loads_both_new_families_with_their_keys():
    assert {'swordcamp', 'hidamari_city', 'hippodrome'} <= set(FAMILIES)
    for family in (SWORD, CITY):
        assert planner.FAMILY_KEYS <= set(family) <= planner.FAMILY_KEYS | planner.OPTIONAL_KEYS
        assert (planner.BUILDERS / family['builder']).is_file()
        assert family['fallback'] in {m['id'] for m in family['masters']}


def test_each_master_has_its_keys_and_a_builder_with_donor_lines():
    for family in (SWORD, CITY):
        for master in family['masters']:
            assert set(master) == planner.MASTER_KEYS
            assert master['builder'] in family['donor_lines']


def test_both_families_are_done_and_the_city_keeps_its_generator_record():
    """Sword Camp retired its adopted record; the Hidamari record holds the region generator's pinned sources, so it stays
    as a generator record that owns no package."""
    for family in (SWORD, CITY):
        assert planner.state(GAME, family) == 'done'
        assert planner.claim_ops(GAME, family) == {'writes': {}, 'deletes': []}
    assert not (GAME / f'assets/{SWORD["adopted"]}/asset.toml').exists()
    generator = records.load_asset(GAME / f'assets/{CITY["adopted"]}/asset.toml')
    assert generator.kind == 'generator' and generator.outputs == [] and generator.sources
    assert CITY['generator'] and 'generator' not in SWORD


def test_every_read_is_an_output_of_a_record_the_master_names_as_input():
    for family in (SWORD, CITY):
        for master in family['masters']:
            outputs = set()
            for dep in master['inputs']:
                asset = records.load_asset(GAME / f'assets/{dep}/asset.toml')
                outputs |= {o.package for o in asset.outputs}
            assert set(master['reads']) <= outputs, master['id']


@pytest.mark.parametrize('family', [SWORD, CITY], ids=['swordcamp', 'hidamari_city'])
def test_the_planned_record_text_is_a_valid_material_master_with_the_pinned_builder(family, tmp_path):
    sha = planner.builder_sha(family)
    for master in family['masters']:
        path = tmp_path / f'{master["id"].replace("/", "_")}.toml'
        path.write_text(planner.record_text(family, master, sha))
        asset = records.load_asset(path)
        assert asset.kind == 'material-master' and asset.authority == 'generated'
        assert [(s.path, s.sha256) for s in asset.sources] == [
            (f'src/{source.name}', hashlib.sha256(source.read_bytes()).hexdigest())
            for source in planner.builder_sources(family)]
        assert records.material_master_reads(asset) == master['reads']
        assert asset.recipe['settings']['builder'] == master['builder']
        outputs_of = {dep: set(master['reads']) for dep in master['inputs']}
        assert records.material_input_problems(asset, outputs_of) == []
        assert [o.package for o in asset.outputs] == [master['package']]


def test_the_swordcamp_references_point_at_the_camp_master():
    pointing = [p for p in records.record_paths(GAME) if 'master/swordcamp/camp' in records.load_asset(p).references]
    assert len(pointing) == 14
    for path in records.record_paths(GAME):
        asset = records.load_asset(path)
        assert SWORD['adopted'] not in asset.references + asset.input_dependencies, path


def test_the_hidamari_records_keep_referencing_their_generator_and_the_plaster_feeds_the_city_master():
    """The generator record stays, so the 56 props and surfaces keep referencing it (no prop names M_HDCity); the plaster
    record is an input of the master and gains no mention of what it feeds."""
    referencing = [p for p in records.record_paths(GAME) if CITY['adopted'] in records.load_asset(p).references]
    assert len(referencing) == 56
    assert not any('master/hidamari/city' in records.load_asset(p).references + records.load_asset(p).input_dependencies
                   for p in records.record_paths(GAME))
    assert CITY['masters'][0]['inputs'] == ['adopted/japan/hidamari/surface-plaster']
