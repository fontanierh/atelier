"""Belmonte and Brine Cove scenery objects (tools/migrate/towns.py): every runtime group is saved, not saved with a reason, or
drawn by no one; each saved group is in exactly one object; the models are the adopted records that own the meshes."""
import collections
import importlib.util
import json
import sys
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'content'))
import records  # noqa: E402


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


towns = load('v2_migrate_towns', 'tools/migrate/towns.py')
objects = load('v2_migrate_objects_for_towns', 'tools/migrate/objects.py')
TAGS = sorted(towns.REGIONS)


@pytest.fixture(scope='module')
def owners():
    return towns.package_records(ROOT)


@pytest.fixture(scope='module')
def state(owners):
    """{tag: (head text, runtime data, classification of the groups the existing objects do not save)}."""
    out = {}
    for tag in TAGS:
        text = towns.region_folder(tag, ROOT).joinpath('objects.toml').read_text()
        head = towns.split_head(text)
        data = json.loads(towns.runtime_path(tag, ROOT).read_text())
        result = towns.classify(tag, data, towns.covered_groups(head), owners,
                                {item['id'] for item in tomllib.loads(head).get('objects', [])})
        out[tag] = (text, head, data, result)
    return out


def generated_objects(tag, text):
    """The [[objects]] entries after the marker, as the objects loader reads them."""
    return tomllib.loads(text[text.index(towns.MARKER):]).get('objects', [])


@pytest.mark.parametrize('tag', TAGS)
def test_every_runtime_group_is_accounted_once(state, tag):
    text, head, data, result = state[tag]
    names = [towns.mesh_name(entry) for entry in data['groups']]
    covered = towns.covered_groups(head)
    saved = [name for members in result['units'].values() for name, _, _ in members]
    blocked = [name for reason in towns.REASONS for name, _ in result['blocked'][reason]]
    listed = collections.Counter(saved + blocked)
    assert not [name for name, count in listed.items() if count > 1]
    assert not set(listed) & covered
    unaccounted = sorted({n for n in names if n not in covered and n not in listed})
    assert unaccounted == []


@pytest.mark.parametrize('tag', TAGS)
def test_generated_objects_load_and_match_the_classification(state, tag):
    text, head, data, result = state[tag]
    region = SimpleNamespace(folder=towns.region_folder(tag, ROOT), id=towns.REGIONS[tag])
    # The objects loader validates every entry (keys, ids, duplicate groups); the existing ones are loaded too.
    loaded = objects.load_objects(region)['objects']
    generated = generated_objects(tag, text)
    assert len(generated) == len(result['units'])
    assert {item['id'] for item in loaded} == {item['id'] for item in tomllib.loads(head).get('objects', [])} | \
        {f'object/{tag}/{unit}' for unit in result['units']}
    for item in generated:
        unit = item['id'].rsplit('/', 1)[1]
        members = result['units'][unit]
        expected = [name for name, _, _ in members]
        assert (item['groups'] if 'groups' in item else [item['group']]) == expected


@pytest.mark.parametrize('tag', TAGS)
def test_saved_groups_have_instances_inside_the_district_and_are_not_plants(state, tag):
    _, _, data, result = state[tag]
    by_name = {towns.mesh_name(entry): entry for entry in data['groups']}
    for members in result['units'].values():
        for name, _, kept in members:
            entry = by_name[name]
            assert not entry['plant'], name
            assert kept == towns.in_district(data, entry) > 0, name


@pytest.mark.parametrize('tag', TAGS)
def test_models_are_adopted_records_that_own_the_mesh(state, tag, owners):
    text, _, data, _ = state[tag]
    adopted = {}
    for path in (ROOT / 'assets').rglob('asset.toml'):
        data_toml = tomllib.loads(path.read_text())
        if data_toml.get('kind') == 'adopted':
            adopted[data_toml['id']] = {o['package'] for o in data_toml.get('outputs', [])}
    by_name = {towns.mesh_name(e): e for e in data['groups']}
    for item in generated_objects(tag, text):
        models = [item['model']] if isinstance(item['model'], str) else item['model']
        assert models and all(m in adopted for m in models), item['id']
        for name in ([item['group']] if 'group' in item else item['groups']):
            package = by_name[name]['asset'].rsplit('.', 1)[0]
            assert any(package in adopted[m] for m in models), (item['id'], name)


@pytest.mark.parametrize('tag', TAGS)
def test_object_ids_and_records_are_well_formed(state, tag):
    text, _, _, _ = state[tag]
    ids = [item['id'] for item in tomllib.loads(text).get('objects', [])]
    assert len(ids) == len(set(ids))
    for oid in ids:
        assert records.ID.match(oid) and oid.startswith(f'object/{tag}/'), oid


@pytest.mark.parametrize('tag', TAGS)
def test_rerun_is_idempotent(state, tag, owners):
    text, head, data, _ = state[tag]
    again, _ = towns.render(tag, towns.split_head(text), data, owners)
    assert again == text


def test_existing_objects_are_untouched_and_reasons_are_recorded(state):
    """Belmonte's plants and village houses stay out, each with its reason; Brine Cove's duplicated cover groups too."""
    text, _, _, result = state['belmonte']
    assert {name for name, _ in result['blocked']['plant']} >= {'Bush_Green_B', 'Tree_Tuscan_Oak'}
    assert {name for name, _ in result['blocked']['outside']} == {f'SM_BM_BVV_Village_{n}' for n in range(1, 9)}
    text, _, _, result = state['brinecove']
    dup = {name for name, _ in result['blocked']['duplicate name']}
    assert dup == {f'SM_BC_Plant_Cover{kind}{n}' for kind in ('Fern', 'Grass', 'Leaf') for n in range(3)}
    assert '# duplicate name: SM_BC_Plant_CoverFern0' in text
