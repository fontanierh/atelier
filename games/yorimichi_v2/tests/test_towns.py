"""Belmonte and Brine Cove scenery objects (tools/migrate/towns.py): every runtime group is saved, or not saved with a reason,
and each saved group or cell piece is in exactly one object; the models are the adopted records that own the meshes; the
keys and plant pieces follow the runtime's own filters (V2MigrationTowns.cpp, ABelmonteRegion::PlantTransforms)."""
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


def need(path: Path) -> Path:
    """The town data are LFS files; a checkout without them (CI) skips these tests instead of failing."""
    if not path.is_file() or records.is_lfs_pointer(path):
        pytest.skip(f'{path.name} is not hydrated in this checkout')
    return path


@pytest.fixture(scope='module')
def owners():
    return towns.package_records(ROOT)


@pytest.fixture(scope='module')
def units():
    return towns.saved_units(ROOT)


@pytest.fixture(scope='module')
def clearance():
    need(towns.CLEARANCE)
    return towns.clearance_segments()


@pytest.fixture(scope='module')
def state(owners, units, clearance):
    """{tag: (text, head, runtime data, classification of the groups the region's existing objects do not save)}."""
    out = {}
    for tag in TAGS:
        runtime = need(towns.runtime_path(tag, ROOT))
        text = towns.region_folder(tag, ROOT).joinpath('objects.toml').read_text()
        head = towns.split_head(text)
        data = json.loads(runtime.read_text())
        taken = {item['id'] for item in tomllib.loads(head).get('objects', [])}
        result = towns.classify(tag, data, towns.covered_groups(head), owners, taken, clearance, units[tag])
        out[tag] = (text, head, data, result)
    return out


def generated_objects(text):
    """The [[objects]] entries after the marker, as the objects loader reads them."""
    return tomllib.loads(text[text.index(towns.MARKER):]).get('objects', [])


def all_groups(text):
    """Every group key the region's objects name, existing and generated."""
    return [g for item in tomllib.loads(text).get('objects', []) for g in item.get('groups', []) + [item.get('group', '')]
            if g]


def test_keys_are_plain_names_unless_shared():
    data = {'groups': [
        {'asset': '/Game/A/SM_One.SM_One'}, {'asset': '/Game/A/SM_Two.SM_Two'}, {'asset': '/Game/B/SM_Two.SM_Two'},
    ]}
    assert towns.group_keys(data) == ['SM_One', 'SM_Two#1', 'SM_Two#2']


def test_piece_keys_round_trip():
    assert towns.piece_key('Tree_Tuscan_Oak', -3, 5) == 'Tree_Tuscan_Oak@-3_5'
    assert towns.split_piece('Tree_Tuscan_Oak@-3_5') == ('Tree_Tuscan_Oak', (-3, 5))
    assert towns.split_piece('SM_BM_BT_Terrain_0_0') is None


def test_check_group_keys_refuses_unknown_keys():
    data = {'groups': [{'asset': '/Game/A/SM_One.SM_One', 'transforms': []}]}
    towns.check_group_keys('t', ['SM_One', 'SM_One@1_2'], data)
    with pytest.raises(towns.TownError):
        towns.check_group_keys('t', ['SM_Two'], data)
    with pytest.raises(towns.TownError):
        towns.check_group_keys('t', ['SM_One#0'], data)


@pytest.mark.parametrize('tag', TAGS)
def test_every_runtime_group_is_accounted_once(state, tag):
    text, head, data, result = state[tag]
    keys = towns.group_keys(data)
    covered = towns.covered_groups(head)
    generated = all_groups(text[text.index(towns.MARKER):])
    assert len(generated) == len(set(generated))
    assert not set(generated) & covered
    blocked = [key for reason in towns.REASONS for key, _ in result['blocked'][reason]]
    assert not set(blocked) & set(generated)
    for key in keys:
        if key in covered:
            continue
        pieces = {g for g in generated if towns.split_piece(g) and towns.split_piece(g)[0] == key}
        assert key in generated or key in blocked or pieces, key


@pytest.mark.parametrize('tag', TAGS)
def test_generated_objects_load_and_match_the_classification(state, tag):
    text, head, data, result = state[tag]
    region = SimpleNamespace(folder=towns.region_folder(tag, ROOT), id=towns.REGIONS[tag])
    # The objects loader validates every entry (keys, ids, duplicate groups); the existing ones are loaded too.
    loaded = objects.load_objects(region)['objects']
    assert {item['id'] for item in loaded} == {item['id'] for item in tomllib.loads(head).get('objects', [])} | \
        {f'object/{tag}/{unit}' for unit in result['units']}
    for item in generated_objects(text):
        unit = item['id'].rsplit('/', 1)[1]
        expected = [key for key, _, _ in result['units'][unit]]
        assert (item['groups'] if 'groups' in item else [item['group']]) == expected


@pytest.mark.parametrize('tag', TAGS)
def test_saved_groups_follow_the_runtime_filters(state, tag, clearance):
    """Each saved group or cell piece holds exactly the instances the runtime draws there: a plant's outside the gondola
    clearance, any other group's inside the district; a piece only its 128 m cell's."""
    _, _, data, result = state[tag]
    by_key = dict(zip(towns.group_keys(data), data['groups']))
    cached = {}
    for members in result['units'].values():
        for key, _, count in members:
            piece = towns.split_piece(key)
            base, cell = piece if piece else (key, None)
            entry = by_key[base]
            if base not in cached:
                cached[base] = towns.kept_cells(data, entry, clearance)
            cells = cached[base]
            assert count == (cells[cell] if cell else sum(cells.values())) > 0, key
            if cell is None:
                assert sum(cells.values()) <= towns.PIECE_LIMIT, key


@pytest.mark.parametrize('tag', TAGS)
def test_pieces_are_cut_only_for_groups_over_the_limit(state, tag, clearance):
    _, _, data, result = state[tag]
    by_key = dict(zip(towns.group_keys(data), data['groups']))
    totals = {}
    for members in result['units'].values():
        for key, _, _ in members:
            piece = towns.split_piece(key)
            if piece:
                if piece[0] not in totals:
                    totals[piece[0]] = sum(towns.kept_cells(data, by_key[piece[0]], clearance).values())
                assert totals[piece[0]] > towns.PIECE_LIMIT, key


@pytest.mark.parametrize('tag', TAGS)
def test_models_are_records_that_own_the_mesh(state, tag):
    """An adopted record, or the record a recovery made in its place, owns each generated object's meshes."""
    text, _, data, _ = state[tag]
    adopted = {}
    for path in (ROOT / 'assets').rglob('asset.toml'):
        record = tomllib.loads(path.read_text())
        if record.get('kind') != 'placement':
            adopted[record['id']] = {o['package'] for o in record.get('outputs', [])}
    by_key = dict(zip(towns.group_keys(data), data['groups']))
    for item in generated_objects(text):
        models = [item['model']] if isinstance(item['model'], str) else item['model']
        assert models and all(m in adopted for m in models), item['id']
        for group in ([item['group']] if 'group' in item else item['groups']):
            base = towns.split_piece(group)[0] if towns.split_piece(group) else group
            package = by_key[base]['asset'].rsplit('.', 1)[0]
            assert any(package in adopted[m] for m in models), (item['id'], group)


@pytest.mark.parametrize('tag', TAGS)
def test_object_ids_and_records_are_well_formed(state, tag):
    text, _, _, _ = state[tag]
    ids = [item['id'] for item in tomllib.loads(text).get('objects', [])]
    assert len(ids) == len(set(ids))
    for oid in ids:
        assert records.ID.match(oid) and oid.startswith(f'object/{tag}/'), oid


@pytest.mark.parametrize('tag', TAGS)
def test_rerun_is_idempotent(state, tag, owners, units, clearance):
    text, head, data, _ = state[tag]
    again, _ = towns.render(tag, towns.split_head(text), data, owners, units[tag])
    assert again == text


def test_unchanged_rerun_writes_nothing(state, capsys):
    """A no-op run leaves every committed objects.toml untouched, timestamps included (yorimichi-v2-targeted-authoring)."""
    paths = [towns.region_folder(tag, ROOT) / 'objects.toml' for tag in TAGS]
    before = [p.stat().st_mtime_ns for p in paths]
    assert towns.main([]) == 0
    assert [p.stat().st_mtime_ns for p in paths] == before


def test_reasons_are_the_runtime_ones(state):
    """Belmonte's village houses stay out (outside the district, never drawn). Every other group is saved: the plants by
    the gondola clearance, the Brine Cove cover groups whole, the sharers of a mesh name by key."""
    _, _, _, bm = state['belmonte']
    assert {key for key, _ in bm['blocked']['outside']} == {f'SM_BM_BVV_Village_{n}' for n in range(1, 9)}
    assert bm['blocked']['no record'] == []
    _, _, _, bc = state['brinecove']
    # Brine Cove batch 1's two Soft remainders are saved as their own objects, so no group lacks a record.
    assert bc['blocked']['outside'] == [] and bc['blocked']['no record'] == []


def test_shared_mesh_names_are_saved_by_key(state):
    text, _, data, _ = state['brinecove']
    shared = {k for k in towns.group_keys(data) if '#' in k}
    # 18 cover-plant groups, plus four hero-hull cells per ship that the ship objects own above the marker.
    assert len(shared) == 30
    saved = {g.split('@', 1)[0] for g in all_groups(text) if '#' in g}
    assert saved == shared


@pytest.mark.parametrize('tag', TAGS)
def test_saved_definitions_name_the_current_group_keys(state, tag):
    """Retiring runtime groups shifts the later `#index` keys (towns.group_keys); objects.saved.json must be relabelled with
    objects.toml, or objects.py refuses the next save of those objects as changed (yorimichi-v2-targeted-authoring)."""
    text = state[tag][0]
    path = towns.region_folder(tag, ROOT) / objects.SAVED
    if not path.is_file():
        pytest.skip(f'{tag} has no {objects.SAVED}')
    saved = json.loads(path.read_text())['objects']
    now = {item['id']: item.get('groups', [item.get('group')]) for item in tomllib.loads(text).get('objects', [])}
    assert {k: v['groups'] for k, v in saved.items() if k in now and v['groups'] != now[k]} == {}
