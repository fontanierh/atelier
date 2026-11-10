"""Material-master records: a generator-built master names its builder, its reads and its pinned .py generator, and stays
generator-built (authority generated). The inventory (docs/inventory/master-sources.json) is checked against the V2 owner
records. Nothing here runs Unreal and nothing reads the donor checkout."""
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'content'))
import records  # noqa: E402

INVENTORY = ROOT / 'docs/inventory/master-sources.json'
SMALL_MASTERS = ROOT / 'docs/inventory/small-families-masters.txt'
FITS = {'direct', 'needs helper', 'not recoverable'}
GENERATOR_SHA = hashlib.sha256(b'the pinned generator').hexdigest()
DEFAULT_SETTINGS = 'builder = "surface"\nreads = ["/Game/Hippodrome/Textures/T_Grass"]\narguments = { roughness = 0.95 }\n'


def master_toml(*, authority='generated', importer='material-master', version=1, kind='material-master',
                settings=DEFAULT_SETTINGS, deps='["texture/hippodrome/grass"]', sources=None,
                outputs=('/Game/Hippodrome/Materials/M_HD_Grass',)):
    if sources is None:
        sources = f'[[sources]]\npath = "src/import_hippodrome.py"\nsha256 = "{GENERATOR_SHA}"\n'
    deps_line = f'input_dependencies = {deps}\n' if deps is not None else ''
    outs = ''.join(f'[[outputs]]\npackage = "{package}"\n' for package in outputs)
    return (f'schema = 1\nid = "master/hippodrome/grass"\nkind = "{kind}"\nauthority = "{authority}"\n'
            f'owner = "shared/hippodrome/grass"\n{deps_line}{sources}'
            f'[recipe]\nimporter = "{importer}"\nversion = {version}\n[recipe.settings]\n{settings}\n{outs}')


def load_text(tmp_path, text):
    path = tmp_path / 'asset.toml'
    path.write_text(text)
    return records.load_asset(path)


def load_inventory():
    return json.loads(INVENTORY.read_text())


# --- the validator ---------------------------------------------------------------------------------------------------

def test_the_kind_is_known_and_the_published_schema_lists_it():
    assert 'material-master' in records.KINDS
    schema = json.loads((ROOT / 'schemas/asset.schema.json').read_text())
    assert 'material-master' in schema['properties']['kind']['enum']


def test_a_well_formed_master_loads_with_its_generator_pinned(tmp_path):
    asset = load_text(tmp_path, master_toml())
    assert asset.kind == 'material-master' and asset.authority == 'generated'
    assert asset.recipe['settings']['builder'] == 'surface'
    assert [(s.path, s.sha256) for s in asset.sources] == [('src/import_hippodrome.py', GENERATOR_SHA)]
    assert records.material_master_reads(asset) == ['/Game/Hippodrome/Textures/T_Grass']


def test_a_master_with_constants_only_needs_no_reads_and_no_input(tmp_path):
    asset = load_text(tmp_path, master_toml(settings='builder = "surface"\narguments = { roughness = 0.6, two_sided = false }\n',
                                            deps=None))
    assert records.material_master_reads(asset) == []
    assert records.material_input_problems(asset, {}) == []


def test_arguments_may_be_strings_numbers_and_booleans(tmp_path):
    asset = load_text(tmp_path, master_toml(settings='builder = "material"\narguments = { alpha = 1, name = "M_RetailMasked", two_sided = true, scale = 0.5 }\n'))
    assert asset.recipe['settings']['arguments'] == {'alpha': 1, 'name': 'M_RetailMasked', 'two_sided': True, 'scale': 0.5}


@pytest.mark.parametrize('kwargs, reason', [
    (dict(importer='material-instance'), 'importer "material-master"'),
    (dict(version=2), 'version 1'),
    (dict(authority='editor'), 'generator-built'),
    (dict(authority='split'), 'generator-built'),
    (dict(settings='reads = []\n'), 'builder'),
    (dict(settings='builder = "Surface"\n'), 'lower-case'),
    (dict(settings='builder = "surface"\nextra = 1\n'), 'unknown key'),
    (dict(settings='builder = "surface"\nreads = ["Grass"]\n'), 'distinct /Game or /Engine packages'),
    (dict(settings='builder = "surface"\nreads = ["/Game/Hippodrome/Textures/T_Grass", "/Game/Hippodrome/Textures/T_Grass"]\n'), 'distinct /Game or /Engine packages'),
    (dict(settings='builder = "surface"\narguments = { roughness = [0.9] }\n'), 'plain scalar'),
    (dict(settings='builder = "surface"\narguments = { "bad name" = 1 }\n'), 'plain scalar'),
    (dict(settings='builder = "surface"\narguments = "roughness"\n'), 'table of name = value'),
    (dict(outputs=('/Game/Hippodrome/Materials/Grass',)), 'named M_'),
    (dict(sources=''), 'names its generator'),
    (dict(sources='[[sources]]\npath = "src/T_Grass.png"\nsha256 = "' + GENERATOR_SHA + '"\n'), 'names its generator'),
])
def test_a_malformed_master_is_refused(tmp_path, kwargs, reason):
    with pytest.raises(records.RecordError, match=reason):
        load_text(tmp_path, master_toml(**kwargs))


def test_a_master_with_no_settings_table_is_refused(tmp_path):
    text = master_toml().split('[recipe.settings]')[0] + '[[outputs]]\npackage = "/Game/Hippodrome/Materials/M_HD_Grass"\n'
    with pytest.raises(records.RecordError, match='recipe.settings'):
        load_text(tmp_path, text)


# --- the read-set check ----------------------------------------------------------------------------------------------

def test_a_read_owned_by_an_input_dependency_passes(tmp_path):
    asset = load_text(tmp_path, master_toml())
    assert records.material_input_problems(asset, {'texture/hippodrome/grass': {'/Game/Hippodrome/Textures/T_Grass'}}) == []


def test_a_read_not_owned_by_any_input_is_reported_for_a_master(tmp_path):
    asset = load_text(tmp_path, master_toml(deps='["texture/hippodrome/dirt"]'))
    problems = records.material_input_problems(asset, {'texture/hippodrome/dirt': {'/Game/Hippodrome/Textures/T_Dirt'}})
    assert problems == ['/Game/Hippodrome/Textures/T_Grass is read by master/hippodrome/grass but no input dependency owns it']


# --- the inventory ---------------------------------------------------------------------------------------------------

def test_the_inventory_covers_the_held_small_family_masters():
    covered = {master['package'] for master in load_inventory()['masters']}
    held = [line.strip() for line in SMALL_MASTERS.read_text().splitlines() if line.strip()]
    assert [package for package in held if package not in covered] == []
    assert len(held) == 19


def test_every_master_has_a_fit_a_record_and_the_package_as_its_output():
    for master in load_inventory()['masters']:
        assert master['fit'] in FITS, master['package']
        asset = records.load_asset(ROOT / 'assets' / master['record'] / 'asset.toml')
        assert master['package'] in {output.package for output in asset.outputs}, master['package']


def test_every_texture_input_is_an_output_of_the_owner_record_it_names():
    for master in load_inventory()['masters']:
        for entry in master['inputs']:
            if entry['kind'] != 'texture':
                continue
            owner = records.load_asset(ROOT / 'assets' / entry['owner'] / 'asset.toml')
            assert entry['name'] in {output.package for output in owner.outputs}, (master['package'], entry['name'])


def test_every_reads_entry_is_a_texture_input_of_its_master():
    for master in load_inventory()['masters']:
        textures = {entry['name'] for entry in master['inputs'] if entry['kind'] == 'texture'}
        assert set(master.get('reads', [])) <= textures, master['package']


def test_the_inventory_pins_are_sha256_and_line_ranges_and_carry_no_home_paths():
    data = load_inventory()
    for helper in data['helper_files']:
        assert len(helper['sha256']) == 64 and set(helper['sha256']) <= set('0123456789abcdef'), helper['path']
    for master in data['masters']:
        low, high = master['generator']['lines']
        assert 1 <= low <= high, master['package']
        assert len(master['generator']['sha256']) == 64, master['package']
    text = INVENTORY.read_text()
    assert '/Users/' not in text and '/home/' not in text and 'hostname' not in text.lower()


def test_the_needs_helper_masters_name_the_helper_they_need():
    for master in load_inventory()['masters']:
        if master['fit'] == 'needs helper':
            assert any(h['path'].endswith('atmosphere.py') for h in master['helpers']), master['package']
