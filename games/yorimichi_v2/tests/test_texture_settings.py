"""The optional texture recipe settings (max_texture_size, lod_group, ...): the record validator and the importer's list
agree, existing texture records load and keep their input fingerprints, and malformed or unknown values are refused."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'content'))
sys.path.insert(0, str(ROOT / 'unreal' / 'Scripts'))
import import_settings  # noqa: E402
import records  # noqa: E402


def texture_records():
    out = []
    for path in records.record_paths(ROOT):
        asset = records.load_asset(path)
        if asset.kind == 'texture':
            out.append((path, asset))
    return out


def test_the_group_lists_agree():
    assert set(records.TEXTURE_GROUPS) == set(import_settings.TEXTURE_GROUPS)


def test_every_existing_texture_record_still_loads():
    assert texture_records(), 'no texture records found'


def test_existing_texture_fingerprints_are_unchanged():
    """A texture record whose verified.json carries an input fingerprint (and no input dependency) must still produce it.
    Stating the new settings in a record changes its fingerprint; leaving them out does not."""
    checked = 0
    for path, asset in texture_records():
        if asset.input_dependencies:
            continue
        verified = path.parent / 'verified.json'
        if not verified.is_file():
            continue
        recorded = json.loads(verified.read_text()).get('input_fingerprint')
        if recorded is None:
            continue
        assert records.input_fingerprint(asset, {}) == recorded, asset.id
        checked += 1
    assert checked, 'no verified texture fingerprints to compare'


def write_record(tmp_path, settings_block):
    text = ('schema = 1\nid = "texture/fixture/one"\nkind = "texture"\nauthority = "generated"\n'
            'owner = "shared/fixture/one"\n\n[[sources]]\npath = "src/T_one.png"\n'
            'sha256 = "' + '0' * 64 + '"\n\n[recipe]\nimporter = "texture"\nversion = 1\n\n'
            '[recipe.settings]\n' + settings_block + '\n[[outputs]]\npackage = "/Game/Fixture/T_one"\n')
    path = tmp_path / 'assets' / 'texture' / 'fixture' / 'one' / 'asset.toml'
    path.parent.mkdir(parents=True)
    path.write_text(text)
    return path


def test_stated_settings_change_the_fingerprint(tmp_path):
    bare = records.load_asset(write_record(tmp_path / 'a', ''))
    stated = records.load_asset(write_record(tmp_path / 'b', 'max_texture_size = 1024\nlod_group = "TEXTUREGROUP_WORLD"\n'))
    assert records.input_fingerprint(bare, {}) != records.input_fingerprint(stated, {})


@pytest.mark.parametrize('settings_block', [
    'lod_group = "World"',
    'lod_group = "TEXTUREGROUP_Bogus"',
    'max_texture_size = 1000',
    'max_texture_size = 0',
    'max_texture_size = true',
    'srgb = "yes"',
    'compression = "NORMAL"',
    'address = "clamp"',
    'filter = "trilinear"',
])
def test_malformed_or_unknown_settings_are_refused(tmp_path, settings_block):
    with pytest.raises(records.RecordError):
        records.load_asset(write_record(tmp_path, settings_block + '\n'))


def test_the_well_formed_settings_load(tmp_path):
    asset = records.load_asset(write_record(
        tmp_path, 'srgb = true\ncompression = "TC_NORMALMAP"\nmax_texture_size = 1024\n'
                  'lod_group = "TEXTUREGROUP_WORLD"\naddress = "wrap"\n'))
    assert asset.recipe['settings']['max_texture_size'] == 1024
