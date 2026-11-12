"""The japan base family (adopted/japan/materials/base-materials): thirteen masters, their builders traced against a recording
stand-in for unreal, the planner's view of the family, and the fourteen packages that stay in the record. Nothing here runs
Unreal: the builders run against the Recorder, and the planner reads the records as they are on disk."""
import importlib.util
import inspect
import sys
from pathlib import Path

import json
import tomllib
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'unreal/Scripts'
sys.path.insert(0, str(ROOT / 'tools' / 'content'))
sys.path.insert(0, str(ROOT / 'tools' / 'migrate'))
import records  # noqa: E402
import master_records as planner  # noqa: E402

FAMILIES = planner.load_families()
FAMILY = FAMILIES['japan_base']
MASTERS = {m['package']: m for m in FAMILY['masters']}

spec = importlib.util.spec_from_file_location('v2_japan_base_masters', SCRIPTS / 'material_masters' / 'japan_base_masters.py')
builders = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builders)

# The twelve packages the record keeps: MPC_Wind is a MaterialParameterCollection (not a Material), and the others have a
# donor helper (atmosphere, painterly_kernel, the craterpark build outputs) that is not yet ported. M_Sea and M_HarborWater,
# the sea_look pair, moved on to the japan_sea family (test_master_japansea.py).
KEPT = {
    '/Game/Japan/Materials/MPC_Wind', '/Game/Japan/Materials/M_CoastRock', '/Game/Japan/Materials/M_Foliage',
    '/Game/Japan/Materials/M_ForestGround', '/Game/Japan/Materials/M_ForestImpostor', '/Game/Japan/Materials/M_Grass',
    '/Game/Japan/Materials/M_NorthGate', '/Game/Japan/Materials/M_NorthMountains',
    '/Game/Japan/Materials/M_Painted', '/Game/Japan/Materials/M_Painterly',
    '/Game/Japan/Materials/M_Sky', '/Game/Japan/Materials/M_Village',
}
SEA = {'/Game/Japan/Materials/M_Sea', '/Game/Japan/Materials/M_HarborWater'}
ADOPTED_PACKAGES = KEPT | SEA | set(MASTERS)
# The packages later families sharing the record moved out of it (japan_sea, the terrain, sky and surface families).
LATER = {m['package'] for name, f in FAMILIES.items() if name != 'japan_base' and f['adopted'] == FAMILY['adopted']
         for m in f['masters']}


class Recorder:
    """Every attribute is a stand-in, and every call is logged as (method name, shown arguments)."""

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
    return repr(value)


def trace(builder, *args, **kwargs):
    log = []
    original = builders.unreal
    builders.unreal = Recorder('unreal', log, {'does_asset_exist': False})
    try:
        builder(*args, **kwargs)
    finally:
        builders.unreal = original
    return log


def calls(log, name):
    return [args for method, args in log if method == name]


def connected_properties(log):
    """The property pin of every connect_material_property call, by name (MP_BASE_COLOR and so on)."""
    return [args[2].strip('<>') for args in calls(log, 'connect_material_property')]


def codes(log):
    return [args[1] for args in calls(log, 'set_editor_property') if args[0] == "'code'"]


FORBIDDEN = {'save_loaded_asset', 'save_asset', 'import_asset_tasks', 'import_asset', 'save_material', 'AssetImportTask'}


def assert_pure_build(log):
    """A builder never saves, never imports and never loads a texture: every read arrives through `reads`, and the
    importer saves the one master it accepts."""
    names = {method for method, _ in log}
    assert not (names & FORBIDDEN), names & FORBIDDEN
    assert 'recompile_material' in names


# --- every master: the family and the builders agree -------------------------------------------------------------------

def test_the_family_loads_and_its_builder_module_is_the_one_it_names():
    assert FAMILY['name'] == 'japan_base' and FAMILY['builder'] == 'japan_base_masters.py'
    assert planner.builder_path(FAMILY).is_file()
    assert {m['builder'] for m in FAMILY['masters']} <= set(FAMILY['donor_lines'])


def test_the_module_imports_without_the_editor_and_every_builder_is_a_function():
    assert builders.unreal is None
    for name in set(m['builder'] for m in FAMILY['masters']):
        assert callable(getattr(builders, name)), name


def test_each_master_arguments_and_reads_bind_to_its_builder():
    for master in FAMILY['masters']:
        builder = getattr(builders, master['builder'])
        inspect.signature(builder).bind(master['package'], {r: object() for r in master['reads']}, **master['arguments'])


def test_each_master_has_one_package_and_one_record_id():
    packages = [m['package'] for m in FAMILY['masters']]
    ids = [m['id'] for m in FAMILY['masters']]
    assert len(set(packages)) == len(packages) == 13
    assert len(set(ids)) == len(ids)
    assert not (set(packages) & KEPT), 'a kept package is also a master'


def test_the_fallback_is_one_of_the_family_masters():
    assert planner.fallback_ids(FAMILY) == ['master/japan/base/forest-lake-water']
    assert set(planner.fallback_ids(FAMILY)) <= {m['id'] for m in FAMILY['masters']}


def test_every_master_package_moved_out_and_the_adopted_record_lists_exactly_the_kept_packages():
    adopted = records.load_asset(ROOT / 'assets' / FAMILY['adopted'] / 'asset.toml')
    listed = {o.package for o in adopted.outputs}
    assert SEA <= LATER <= KEPT | SEA
    assert listed == KEPT - LATER and not set(MASTERS) & listed
    assert set(MASTERS) | listed | LATER == ADOPTED_PACKAGES, sorted((set(MASTERS) | listed | LATER) ^ ADOPTED_PACKAGES)
    for master in FAMILY['masters']:
        record = records.load_asset(ROOT / 'assets' / master['id'] / 'asset.toml')
        assert [o.package for o in record.outputs] == [master['package']]


def test_the_kept_packages_stay_in_the_slimmed_adopted_record():
    """@cc [owner:fontanierh,label:correctness] master-records-keeps
    With keeps, the claim slimmed the record's outputs and verified files to exactly the kept packages; nothing is left to
    write, and no record depends on the adopted record for a moved master."""
    assert planner.state(ROOT, FAMILY) == 'done'
    assert planner.claim_ops(ROOT, FAMILY) == {'writes': {}, 'deletes': []}
    folder = ROOT / 'assets' / FAMILY['adopted']
    files = json.loads((folder / 'verified.json').read_text())['files']
    assert {f.rsplit('.', 1)[0] for f in files} == {'unreal/Content/' + k[len('/Game/'):] for k in KEPT - LATER}
    moved = {m['id'] for m in FAMILY['masters']}
    pointing = [p for p in records.record_paths(ROOT) if set(records.load_asset(p).references) & moved]
    assert pointing


def test_every_read_is_an_output_of_an_input_record_on_disk():
    for master in FAMILY['masters']:
        owned = set()
        for dependency in master['inputs']:
            owner = records.load_asset(ROOT / 'assets' / dependency / 'asset.toml')
            owned |= {o.package for o in owner.outputs}
        assert set(master['reads']) <= owned, master['id']
        assert all(p.startswith('/Game/') or p.startswith('/Engine/') for p in master['reads'])


def test_every_master_record_is_written_from_the_builder_and_its_own_reads():
    sha = planner.builder_sha(FAMILY)
    for master in FAMILY['masters']:
        text = planner.record_text(FAMILY, master, sha)
        assert f'package = "{master["package"]}"' in text
        assert f'builder = "{master["builder"]}"' in text
        assert f'sha256 = "{sha}"' in text
        assert text.count('[[outputs]]') == 1


# --- the builders, against the recorder ---------------------------------------------------------------------------------

def test_arcade_timber_wires_the_timber_texture_and_the_donor_colour_and_glow():
    tex = '/Game/Japan/Textures/T_Arcade_timber'
    log = trace(builders.arcade_material, MASTERS['/Game/Japan/Materials/M_Arcade']['package'], {tex: 'TIMBER'}, texture=tex, paving=False)
    assert_pure_build(log)
    assert ("'texture'", "'TIMBER'") in calls(log, 'set_editor_property')
    assert ("'dithered_lod_transition'", 'True') in calls(log, 'set_editor_property')
    assert codes(log) == [repr(builders.ARCADE_COLOUR), repr(builders.ARCADE_GLOW)]
    assert connected_properties(log) == ['MP_BASE_COLOR', 'MP_EMISSIVE_COLOR', 'MP_ROUGHNESS', 'MP_SPECULAR']


def test_arcade_paving_overrides_only_the_colour_code_and_keeps_the_rest():
    tex = '/Game/Japan/Textures/T_Arcade_paving'
    log = trace(builders.arcade_material, '/Game/Japan/Materials/M_ArcadePaving', {tex: 'PAVING'}, texture=tex, paving=True)
    assert_pure_build(log)
    assert codes(log) == [repr(builders.ARCADE_COLOUR), repr(builders.ARCADE_PAVING_COLOUR), repr(builders.ARCADE_GLOW)]
    assert connected_properties(log) == ['MP_BASE_COLOR', 'MP_EMISSIVE_COLOR', 'MP_ROUGHNESS', 'MP_SPECULAR']


def test_the_harbor_builds_the_non_water_branch_from_its_two_texture_reads():
    paving, timber = '/Game/Japan/Textures/T_Harbor_paving', '/Game/Japan/Textures/T_Harbor_timber'
    log = trace(builders.harbor_material, '/Game/Japan/Materials/M_Harbor', {paving: 'P', timber: 'T'}, paving=paving, timber=timber)
    assert_pure_build(log)
    textures = [args[1] for args in calls(log, 'set_editor_property') if args[0] == "'texture'"]
    assert textures == ["'P'", "'T'"]
    assert codes(log)[:2] == [repr(builders.HARBOR_COLOUR), repr(builders.HARBOR_NORMAL)]
    assert connected_properties(log) == ['MP_BASE_COLOR', 'MP_NORMAL', 'MP_ROUGHNESS', 'MP_AMBIENT_OCCLUSION', 'MP_SPECULAR', 'MP_EMISSIVE_COLOR']
    assert 'smoothstep(-15.,48.,P.z)' in builders.HARBOR_COLOUR


@pytest.mark.parametrize('pond', [False, True])
def test_plaza_water_and_pond_share_one_builder_and_differ_only_in_their_two_codes(pond):
    package = '/Game/Japan/Materials/M_PondWater' if pond else '/Game/Japan/Materials/M_PlazaWater'
    log = trace(builders.plaza_water, package, {}, pond=pond)
    assert_pure_build(log)
    # The donor writes each default code, then the pond's override after it (plaza_material.py lines 16 and 22).
    expected = [builders.PLAZA_WATER_COLOUR, builders.PLAZA_POND_COLOUR, builders.PLAZA_WATER_NORMAL, builders.PLAZA_POND_NORMAL] \
        if pond else [builders.PLAZA_WATER_COLOUR, builders.PLAZA_WATER_NORMAL]
    assert codes(log) == [repr(text) for text in expected]
    assert connected_properties(log) == ['MP_BASE_COLOR', 'MP_NORMAL', 'MP_ROUGHNESS', 'MP_SPECULAR', 'MP_METALLIC']


def test_the_plaza_paving_reads_the_arcade_paving_texture_and_wires_a_height_normal():
    tex = '/Game/Japan/Textures/T_Arcade_paving'
    log = trace(builders.plaza_paving, '/Game/Japan/Materials/M_PlazaPaving', {tex: 'PAVING'}, texture=tex)
    assert_pure_build(log)
    assert ("'texture'", "'PAVING'") in calls(log, 'set_editor_property')
    assert codes(log) == [repr(builders.PLAZA_PAVING_COLOUR), repr(builders.PLAZA_PAVING_NORMAL)]
    assert connected_properties(log) == ['MP_BASE_COLOR', 'MP_NORMAL', 'MP_ROUGHNESS', 'MP_SPECULAR']


@pytest.mark.parametrize('wake', [False, True])
def test_the_sailboat_cloth_and_wake_differ_by_blend_and_their_wind_and_opacity_pins(wake):
    package = '/Game/Japan/Materials/M_SailboatWake' if wake else '/Game/Japan/Materials/M_SailboatCloth'
    log = trace(builders.sailboat_material, package, {}, wake=wake)
    assert_pure_build(log)
    settings = dict(args for args in calls(log, 'set_editor_property'))
    assert settings["'two_sided'"] == 'True'
    if wake:
        assert settings["'blend_mode'"] == '<BLEND_TRANSLUCENT>'
        assert connected_properties(log)[-2:] == ['MP_OPACITY', 'MP_WORLD_POSITION_OFFSET']
        assert ("'parameter_name'", "'WakeAmount'") in calls(log, 'set_editor_property')
    else:
        assert connected_properties(log)[-1] == 'MP_WORLD_POSITION_OFFSET'
        assert ("'parameter_name'", "'SailFill'") in calls(log, 'set_editor_property')
        assert ("'parameter_name'", "'FlutterDirection'") in calls(log, 'set_editor_property')


def test_the_zeppelin_fabric_is_unlit_and_lit_by_the_sun_parameter():
    log = trace(builders.fabric_material, '/Game/Japan/Materials/M_ZeppelinFabric', {})
    assert_pure_build(log)
    assert ("'shading_model'", '<MSM_UNLIT>') in calls(log, 'set_editor_property')
    assert ("'parameter_name'", "'SunDirection'") in calls(log, 'set_editor_property')
    assert connected_properties(log) == ['MP_EMISSIVE_COLOR']


def test_the_forest_lake_water_has_its_three_custom_pins_and_two_constants():
    log = trace(builders.forest_lake_water, '/Game/Japan/Materials/M_ForestLakeWater', {})
    assert_pure_build(log)
    assert connected_properties(log) == ['MP_BASE_COLOR', 'MP_NORMAL', 'MP_ROUGHNESS', 'MP_SPECULAR', 'MP_METALLIC']
    assert codes(log)[0].startswith(repr(builders.RIPPLE)[:-1])


def test_the_village_resident_is_a_skeletal_two_sided_cloth():
    log = trace(builders.village_resident, '/Game/Japan/Materials/M_VillageResident', {})
    assert_pure_build(log)
    settings = dict(args for args in calls(log, 'set_editor_property'))
    assert settings["'used_with_skeletal_mesh'"] == 'True' and settings["'two_sided'"] == 'True'
    assert ("'parameter_name'", "'ClothTint'") in calls(log, 'set_editor_property')
    assert connected_properties(log) == ['MP_BASE_COLOR', 'MP_EMISSIVE_COLOR', 'MP_ROUGHNESS', 'MP_SPECULAR']


def test_the_bike_has_the_three_custom_inputs_and_its_metal_and_roughness_pins():
    log = trace(builders.bike_material, '/Game/Japan/Materials/M_Bike', {})
    assert_pure_build(log)
    assert connected_properties(log) == ['MP_BASE_COLOR', 'MP_METALLIC', 'MP_ROUGHNESS']


def test_the_cloud_shadow_samples_its_mask_and_emits_its_inverse():
    tex = '/Game/Japan/Textures/T_cloudmask'
    log = trace(builders.cloud_shadow, '/Game/Japan/Materials/M_CloudShadow', {tex: 'MASK'}, texture=tex)
    assert_pure_build(log)
    assert ("'texture'", "'MASK'") in calls(log, 'set_editor_property')
    assert ("'material_domain'", '<MD_LIGHT_FUNCTION>') in calls(log, 'set_editor_property')
    assert connected_properties(log) == ['MP_EMISSIVE_COLOR']


def test_every_master_builds_from_its_own_arguments_without_saving():
    for master in FAMILY['masters']:
        reads = {r: f'read:{r}' for r in master['reads']}
        log = trace(getattr(builders, master['builder']), master['package'], reads, **master['arguments'])
        assert_pure_build(log)
