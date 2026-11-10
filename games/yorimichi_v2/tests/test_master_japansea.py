"""The japan sea family (M_Sea and M_HarborWater, from adopted/japan/materials/base-materials): the builders traced against a
recording stand-in for unreal, the copied sea look, and the planner's view of the family. Nothing here runs Unreal.

The traces are pinned by a sha256 of the call log. Those pins were produced by running the donor functions (games/yorimichi at
the baseline 7eec0f98dd: import_southwest.sea_material and harbor_material.material(water=True), with the donor's own
sea_look.py and world/coast_water.py) through the same stand-in, which gave identical logs (81 and 159 calls). The donor is
not in this tree, so the pins are the record of that check."""
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

FAMILY = planner.load_families()['japan_sea']
BASE = planner.load_families()['japan_base']
MODULE = SCRIPTS / 'material_masters' / 'japan_sea_masters.py'

spec = importlib.util.spec_from_file_location('v2_japan_sea_masters', MODULE)
builders = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builders)

SEA_TRACE = '0e99c5ffcf5a08a1042a95268ddae34ebc44e53e5cbcf721d58e79878cd9297c'
HARBOR_WATER_TRACE = 'feec71476fa209ea770d5b9e5a8f9ce28a3aaa508060a25e4e49672940f83f8f'
# sha256 of the donor's sea_look.py lines 38-150 (the blob is ffae53cd...), the block copied between the SEA_LOOK markers
SEA_LOOK_BLOCK = '4797b469edbb7f56d9d035e0ebe5547649f0c438a5c495ca144a7282ac39094e'


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


PLUMBING = {'get_asset_tools', 'save_loaded_asset', 'load_asset', 'does_asset_exist', 'create_asset', 'get_asset_tools()'}


def trace(builder, package):
    log = []
    original = builders.unreal
    builders.unreal = Recorder('unreal', log, {'does_asset_exist': False, 'connect_material_expressions': True,
                                               'connect_material_property': True})
    try:
        getattr(builders, builder)(package, {})
    finally:
        builders.unreal = original
    return [entry for entry in log if entry[0] not in PLUMBING]


def digest(log):
    return hashlib.sha256(repr(log).encode()).hexdigest()


def test_the_module_imports_without_the_editor_and_defines_both_builders():
    assert builders.unreal is None
    for master in FAMILY['masters']:
        builder = getattr(builders, master['builder'])
        assert inspect.isfunction(builder) and list(inspect.signature(builder).parameters) == ['package', 'reads']
        assert master['builder'] in FAMILY['donor_lines']


@pytest.mark.parametrize('builder,package,pin', [
    ('sea_material', '/Game/Japan/Materials/M_Sea', SEA_TRACE),
    ('harbor_water', '/Game/Japan/Materials/M_HarborWater', HARBOR_WATER_TRACE),
], ids=['sea', 'harbor-water'])
def test_each_builder_traces_as_its_donor_function(builder, package, pin):
    log = trace(builder, package)
    assert digest(log) == pin
    assert ('save_loaded_asset', ) not in [entry[:1] for entry in log]


def test_the_sea_look_block_is_the_donor_lines_byte_for_byte():
    text = MODULE.read_text()
    start = text.index('\n', text.index('# --- SEA_LOOK')) + 1
    end = text.index('\n\n\n# --- end SEA_LOOK') + 1
    assert hashlib.sha256(text[start:end].encode()).hexdigest() == SEA_LOOK_BLOCK
    assert builders.HARBOR_RECT == (300., -1600., 1800., 600.) and builders.SEA_RECT is builders.HARBOR_RECT


def test_both_masters_write_the_fog_and_normal_settings_the_digest_compares():
    digest_module = importlib.util.spec_from_file_location('v2_master_digest', SCRIPTS / 'master_digest.py')
    module = importlib.util.module_from_spec(digest_module)
    digest_module.loader.exec_module(module)
    for builder, package in (('sea_material', '/Game/Japan/Materials/M_Sea'),
                             ('harbor_water', '/Game/Japan/Materials/M_HarborWater')):
        written = {args[0].strip("'") for name, args in trace(builder, package) if name == 'set_editor_property'
                   and args[0].strip("'") in {'blend_mode', 'compute_fog_per_pixel', 'translucency_lighting_mode',
                                              'tangent_space_normal', 'used_with_instanced_static_meshes'}}
        assert written <= set(module.SETTINGS), builder
        assert {'compute_fog_per_pixel', 'tangent_space_normal', 'blend_mode'} <= written, builder


def test_the_family_shares_the_adopted_record_with_japan_base_and_the_keeps_are_disjoint():
    assert FAMILY['adopted'] == BASE['adopted'] and FAMILY['owner'] == BASE['owner']
    packages = {m['package'] for m in FAMILY['masters']}
    assert not packages & set(FAMILY['keeps'])
    assert not packages & {m['package'] for m in BASE['masters']}
    assert set(FAMILY['keeps']) <= set(BASE['keeps'])
    assert planner.fallback_ids(FAMILY) == ['master/japan/sea/open-sea']


def test_the_planned_records_are_material_masters_pinned_to_the_builder(tmp_path):
    sha = planner.builder_sha(FAMILY)
    for master in FAMILY['masters']:
        path = tmp_path / f'{master["id"].replace("/", "_")}.toml'
        path.write_text(planner.record_text(FAMILY, master, sha))
        asset = records.load_asset(path)
        assert asset.kind == 'material-master' and asset.authority == 'generated'
        assert [(s.path, s.sha256) for s in asset.sources] == [(planner.builder_rel(FAMILY), sha)]
        assert [o.package for o in asset.outputs] == [master['package']]
        assert asset.recipe['settings']['builder'] == master['builder']
