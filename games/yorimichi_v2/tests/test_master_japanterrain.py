"""The japan terrain family (M_ForestImpostor, M_ForestGround, M_CoastRock, M_NorthGate and M_NorthMountains, from
adopted/japan/materials/base-materials): the builders traced against a recording stand-in for unreal, the build-output
values they take as arguments, and the planner's view of the family. Nothing here runs Unreal.

The traces are pinned by a sha256 of the call log. The pins were produced by running the donor functions (games/yorimichi
at the baseline 7eec0f98dd: forest_impostor_material.parent, forest_ground.material and rock_material, and
mountain_material.gate_material and material, with the donor's atmosphere.py, ground_grain.py, coast_rock_look.py and
material_assets.py, reading the donor export's north_snow.json, north_crater.json and craterpark textures.json) through
the same stand-in, which gave identical graph calls (84, 65, 67, 43 and 116). The donor's texture imports before its
first graph node are its own plumbing and were left out of its log. The donor is not in this tree, so the pins are the
record of that check."""
import hashlib
import importlib.util
import inspect
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'unreal/Scripts'
sys.path.insert(0, str(ROOT / 'tools' / 'content'))
sys.path.insert(0, str(ROOT / 'tools' / 'migrate'))
import records  # noqa: E402
import master_records as planner  # noqa: E402

FAMILIES = planner.load_families()
FAMILY = FAMILIES['japan_terrain']
MASTERS = {m['builder']: m for m in FAMILY['masters']}
MODULE = SCRIPTS / 'material_masters' / 'japan_terrain_masters.py'

spec = importlib.util.spec_from_file_location('v2_japan_terrain_masters', MODULE)
builders = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builders)

TRACES = {
    'forest_impostor': '12ca4aaddd7d31841f8843d0d1c40556c55b086904e9a19074602c7edcf340c6',
    'forest_ground': '2cb491c6f0d500a4d2aac8b6e3a8b7695ad35c628ad9f8b6474235fa5c34ca89',
    'coast_rock': '4e0591e7ed5715adf5ea669b7c082c8a7dcbd585dcc85bc95b889bcf34625450',
    'north_gate': '5b2c5484c9a6f06634a5b6c6ac20c4b987075c9637a94ccd9ac306456a2909cd',
    'north_mountains': 'db5d59e52d8f1fd297356688d4cf4399f13e22fb81c54487d584367b26959a4d',
}


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
    if isinstance(value, list):
        return '[' + ', '.join(show(v) for v in value) + ']'
    return repr(value)


PLUMBING = {'get_asset_tools', 'save_loaded_asset', 'load_asset', 'does_asset_exist', 'create_asset', 'get_asset_tools()',
            'LOG'}


def trace(builder):
    """The builder's calls from the graph's clear on, with every read loaded through the stand-in, as the donor loaded its
    textures. M_CoastRock is traced over an existing material: the donor's material_assets.create clears only an existing
    one."""
    master = MASTERS[builder]
    log = []
    original = builders.unreal
    rec = Recorder('unreal', log, {'does_asset_exist': builder == 'coast_rock', 'connect_material_expressions': True,
                                   'connect_material_property': True, 'recompile_material': ''})
    builders.unreal = rec
    try:
        reads = {p: rec.EditorAssetLibrary.load_asset(p) for p in master['reads']}
        getattr(builders, builder)(master['package'], reads, **master['arguments'])
    finally:
        builders.unreal = original
    calls = [entry for entry in log if entry[0] not in PLUMBING]
    return calls[next(i for i, e in enumerate(calls) if e[0] == 'delete_all_material_expressions'):]   # from the graph's clear


def test_the_module_imports_without_the_editor_and_every_master_binds_to_its_builder():
    assert builders.unreal is None
    for master in FAMILY['masters']:
        builder = getattr(builders, master['builder'])
        assert inspect.isfunction(builder) and master['builder'] in FAMILY['donor_lines']
        inspect.signature(builder).bind(master['package'], {}, **master['arguments'])


@pytest.mark.parametrize('builder', sorted(TRACES))
def test_each_builder_traces_as_its_donor_function(builder):
    log = trace(builder)
    assert hashlib.sha256(repr(log).encode()).hexdigest() == TRACES[builder]
    assert log[0][0] == 'delete_all_material_expressions'


def test_the_haze_is_the_donor_atmosphere_share_and_colour():
    assert builders.SHARE == 'saturate(1-exp(-max(D-3000.0,0)/900000.0))'
    assert builders.COLOUR == (0.0932, 0.2301, 0.5328)


def test_the_build_output_values_are_the_donor_export_values_and_agree_with_each_other():
    """@cc [owner:fontanierh,label:correctness] terrain-masters-build-values
    The values the donor read from its build output are scalar recipe arguments, as the donor export held them; the
    forest floor and the mountains take the same south join."""
    mountains = MASTERS['north_mountains']['arguments']
    assert MASTERS['forest_ground']['arguments']['south_join_m'] == mountains['south_join_m'] == 3600.0
    assert (mountains['bounds_x0_m'], mountains['bounds_y0_m'], mountains['step_m'], mountains['mask_size']) == (-430.0, 1120.0, 2.5, 1024)
    assert (mountains['floor_metres'], mountains['floor_mean_r'], mountains['floor_mean_g'], mountains['floor_mean_b']) == (16, 100, 98, 100)


def test_the_family_shares_the_adopted_record_and_every_read_is_owned_by_an_input_or_the_engine():
    assert FAMILY['adopted'] == FAMILIES['japan_base']['adopted']
    packages = {m['package'] for m in FAMILY['masters']}
    for other in ('japan_base', 'japan_sea'):
        assert not packages & {m['package'] for m in FAMILIES[other]['masters']}
    assert not packages & set(FAMILY['keeps'])
    for master in FAMILY['masters']:
        owned = set()
        for dep in master['inputs']:
            owned |= {o.package for o in records.load_asset(ROOT / f'assets/{dep}/asset.toml').outputs}
        assert {r for r in master['reads'] if not r.startswith('/Engine/')} <= owned, master['id']


def test_the_planned_records_are_material_masters_pinned_to_the_builder(tmp_path):
    sha = planner.builder_sha(FAMILY)
    for master in FAMILY['masters']:
        path = tmp_path / f'{master["id"].replace("/", "_")}.toml'
        path.write_text(planner.record_text(FAMILY, master, sha))
        asset = records.load_asset(path)
        assert asset.kind == 'material-master' and asset.authority == 'generated'
        assert [(s.path, s.sha256) for s in asset.sources] == [(planner.builder_rel(FAMILY), sha)]
        assert [o.package for o in asset.outputs] == [master['package']]
