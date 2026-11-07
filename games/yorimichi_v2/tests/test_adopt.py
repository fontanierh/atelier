"""Adoption copies donor packages once under their paths, records them editor-owned, and reports gaps."""
import importlib.util
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'content'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import records  # noqa: E402
from claims_fake import FakeClaims  # noqa: E402


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


adopt = load('v2_migrate_adopt', 'tools/migrate/adopt.py')


def write(path, data=b'pkg'):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


@pytest.fixture
def donor(tmp_path, monkeypatch):
    content = tmp_path / 'donor'
    write(content / 'Japan/Assets/House_A.uasset')
    write(content / 'Japan/Assets/House_A.ubulk')
    write(content / 'Japan/Audio/Song.uasset')
    write(content / 'Japan/__ExternalActors__/x.uasset')
    write(content / 'Data/world.json', b'{}')
    refs = {'House_A': ['/Game/Japan/Materials/MI_Wood', '/Script/Engine'], 'Song': []}
    monkeypatch.setattr(adopt, 'references', lambda path: refs[path.stem])
    game = tmp_path / 'game'
    (game / 'unreal/Content').mkdir(parents=True)
    monkeypatch.setenv('ATELIER_AGENT', adopt.authority.BOOTSTRAP_WRITER)
    monkeypatch.delenv('ATELIER_CLAIMS_TASK', raising=False)
    return game, content


def test_adopts_packages_with_companions_and_reports_missing_closure(donor):
    game, content = donor
    report = adopt.adopt(game, content, ['Japan'], ['Japan/Audio'], 'owner-published', echo=lambda *_: None)
    assert report['folders'] == {'Japan': 1}
    assert report['missing_references'] == {'/Game/Japan/Materials/MI_Wood': '/Game/Japan/Assets/House_A'}
    assert (game / 'unreal/Content/Japan/Assets/House_A.ubulk').is_file()
    assert not (game / 'unreal/Content/Japan/Audio/Song.uasset').exists()
    assert not (game / 'unreal/Content/Japan/__ExternalActors__').exists()
    assert report['records'] == {'adopted/japan/assets': 1}
    asset = records.load_asset(game / 'assets/adopted/japan/assets/asset.toml')
    assert asset.kind == 'adopted' and asset.authority == 'editor' and asset.owner == 'shared/japan/assets'
    assert [o.package for o in asset.outputs] == ['/Game/Japan/Assets/House_A']


def test_check_only_writes_nothing_and_a_rerun_changes_nothing(donor):
    game, content = donor
    adopt.adopt(game, content, ['Japan'], [], 'x', check_only=True)
    assert not (game / 'assets').exists() and not (game / 'unreal/Content/Japan').exists()
    adopt.adopt(game, content, ['Japan'], [], 'x', echo=lambda *_: None)
    record = game / 'assets/adopted/japan/assets/asset.toml'
    before = record.stat().st_mtime_ns
    adopt.adopt(game, content, ['Japan'], [], 'x', echo=lambda *_: None)
    assert record.stat().st_mtime_ns == before


def test_refuses_packages_another_record_owns(donor):
    game, content = donor
    (game / 'assets/prop/house').mkdir(parents=True)
    (game / 'assets/prop/house/asset.toml').write_text(
        'schema = 1\nid = "prop/house"\nkind = "static-mesh"\nauthority = "editor"\nowner = "region/w01"\n'
        '[[outputs]]\npackage = "/Game/Japan/Assets/House_A"\n')
    with pytest.raises(adopt.AdoptError, match='already owned by prop/house'):
        adopt.adopt(game, content, ['Japan'], [], 'x')


def test_never_overwrites_a_changed_package(donor):
    game, content = donor
    adopt.adopt(game, content, ['Japan'], [], 'x', echo=lambda *_: None)
    edited = game / 'unreal/Content/Japan/Assets/House_A.uasset'
    edited.write_bytes(b'edited in the editor')
    with pytest.raises(adopt.AdoptError, match='never overwrites'):
        adopt.adopt(game, content, ['Japan'], [], 'x', echo=lambda *_: None)
    assert edited.read_bytes() == b'edited in the editor'


def test_writes_need_a_claim_or_the_bootstrap_writer(donor, monkeypatch):
    game, content = donor
    monkeypatch.setenv('ATELIER_AGENT', 'someone-else')
    with pytest.raises(adopt.AdoptError, match='not the bootstrap writer'):
        adopt.adopt(game, content, ['Japan'], [], 'x', echo=lambda *_: None)
    assert not (game / 'unreal/Content/Japan').exists()
    fake = FakeClaims(scopes=['asset/adopted/japan'], covers=False)
    monkeypatch.setattr(adopt.authority.subprocess, 'run', fake)
    with pytest.raises(adopt.AdoptError, match='does not exactly cover'):
        adopt.adopt(game, content, ['Japan'], [], 'x', claim='T7', echo=lambda *_: None)
    assert fake.checks[0][:9] == ['uv', 'run', 'atelier', 'claims', 'check', '--stage', 'publish', '--task', 'T7']
    assert 'games/yorimichi_v2/unreal/Content/Japan/Assets/House_A.uasset' in fake.checks[0]
    fake.scopes, fake.covers = ['asset/adopted/skatepark'], True
    with pytest.raises(adopt.AdoptError, match='no active scope covering asset/adopted/japan/assets, '
                                               'asset/adopted/japan/audio'):
        adopt.adopt(game, content, ['Japan'], [], 'x', claim='T7', echo=lambda *_: None)
    assert not (game / 'unreal/Content/Japan').exists()


def test_runtime_data_copies_regular_files(donor):
    game, content = donor
    (content / 'Data/megapark').mkdir(parents=True)
    (content / 'Data/megapark/park.json').write_text('{}')   # D05 group 3: rights-blocked, never copied
    assert adopt.copy_data(game, content, echo=lambda *_: None) == 1
    assert adopt.copy_data(game, content, echo=lambda *_: None) == 0
    assert not (game / 'unreal/Content/Data/megapark').exists()
    assert tomllib  # stdlib only
    lock = adopt.records.load_data_lock(game)                 # every copied file is pinned
    assert set(lock) == set(adopt.records.data_files(game)) and len(lock) == 1


def test_runtime_data_writes_and_pins_need_a_claim_or_the_bootstrap_writer(donor, monkeypatch):
    game, content = donor
    adopt.copy_data(game, content, echo=lambda *_: None)
    data = next((game / 'unreal/Content/Data').rglob('*.json'))
    data.write_text('{"edited": true}')
    monkeypatch.setenv('ATELIER_AGENT', 'someone-else')
    with pytest.raises(adopt.AdoptError, match='not the bootstrap writer'):
        adopt.pin_data(game, echo=lambda *_: None)
    monkeypatch.setenv('ATELIER_AGENT', adopt.authority.BOOTSTRAP_WRITER)
    assert adopt.pin_data(game, echo=lambda *_: None) == 1
    assert adopt.records.load_data_lock(game)[data.relative_to(game / 'unreal/Content').as_posix()] == \
        adopt.records.sha256_file(data)
    assert adopt.pin_data(game, echo=lambda *_: None) == 0   # unchanged: nothing to pin


# Ownership units: one record per unit, prefix-free, capped; package paths never change.

TREE = ([f'/Game/Japan/Hidamari/Textures/T_{i:03d}' for i in range(450)]
        + [f'/Game/Japan/Hidamari/Meshes/SM_{i}' for i in range(5)]
        + ['/Game/Japan/Hidamari/M_Direct', '/Game/Japan/Treehouse/Deck/SM_Plank', '/Game/Japan/M_Root'])


def test_partition_is_deterministic_capped_and_prefix_free():
    units = adopt.partition(TREE, 'Japan', cap=200)
    assert sorted(units) == ['adopted/japan/hidamari/loose_files', 'adopted/japan/hidamari/meshes',
                             'adopted/japan/hidamari/textures/loose_files_01',
                             'adopted/japan/hidamari/textures/loose_files_02',
                             'adopted/japan/hidamari/textures/loose_files_03', 'adopted/japan/loose_files',
                             'adopted/japan/treehouse']
    assert units == adopt.partition(list(reversed(TREE)) + TREE[:3], 'Japan', cap=200)
    members = [p for _, _, packages in units.values() for p in packages]
    assert sorted(members) == sorted(TREE) and max(len(u[2]) for u in units.values()) == 200
    assert units['adopted/japan/treehouse'][:2] == ('shared/japan/treehouse', '/Game/Japan/Treehouse')
    for a in units:
        assert records.ID.match(a) and records.ID.match(units[a][0])
        assert not any(b != a and b.startswith(a + '/') for b in units), a   # no unit's scope covers another's
    # A subfolder adopted on its own gets the units a whole-folder adoption gives it.
    alone = adopt.partition([p for p in TREE if '/Treehouse/' in p], 'Japan/Treehouse', cap=200)
    assert alone == {'adopted/japan/treehouse': units['adopted/japan/treehouse']}


def test_partition_refuses_folders_whose_names_collide():
    with pytest.raises(adopt.AdoptError, match='share the record name my-props'):
        adopt.partition(['/Game/Japan/My Props/A', '/Game/Japan/My_Props/B'], 'Japan')


def test_a_group_rule_splits_a_mixed_folder_by_what_its_packages_are(tmp_path):
    """A folder of unrelated props becomes one record per feature; unmatched packages get their own; over cap, parts."""
    rules = tmp_path / 'groups.toml'
    rules.write_text('[[group]]\nfolder = "/Game/Japan/Assets"\nkey = \'^(BK|Tree_[A-Za-z]+)_\'\n'
                     'names = { BK = "bike" }\n')
    groups = adopt.load_groups(rules)
    mixed = (['/Game/Japan/Assets/BK_Frame', '/Game/Japan/Assets/BK_Pedal', '/Game/Japan/Assets/Tree_Maple_A',
              '/Game/Japan/Assets/Tree_Maple_B', '/Game/Japan/Assets/HD_P_postbox', '/Game/Japan/Assets/Sub/SM_X']
             + [f'/Game/Japan/Assets/Tree_Pine_{i:02d}' for i in range(5)])
    units = adopt.partition(mixed, 'Japan/Assets', cap=3, groups=groups)
    assert {u: sorted(p.rsplit('/', 1)[1] for p in v[2]) for u, v in units.items()} == {
        'adopted/japan/assets/bike': ['BK_Frame', 'BK_Pedal'],
        'adopted/japan/assets/tree-maple': ['Tree_Maple_A', 'Tree_Maple_B'],
        'adopted/japan/assets/tree-pine_01': ['Tree_Pine_00', 'Tree_Pine_01', 'Tree_Pine_02'],
        'adopted/japan/assets/tree-pine_02': ['Tree_Pine_03', 'Tree_Pine_04'],
        'adopted/japan/assets/hd-p-postbox': ['HD_P_postbox'],
        'adopted/japan/assets/sub': ['SM_X']}
    assert units['adopted/japan/assets/bike'][0] == 'shared/japan/assets/bike'
    for a in units:
        assert not any(b != a and b.startswith(a + '/') for b in units), a
    assert adopt.partition(list(reversed(mixed)), 'Japan/Assets', cap=3, groups=groups) == units
    # Without the rule the same folder is one record, as before.
    assert sorted(adopt.partition(mixed, 'Japan/Assets', cap=200)) == ['adopted/japan/assets']


def test_group_rules_are_checked_and_colliding_group_names_refused(tmp_path):
    rules = tmp_path / 'groups.toml'
    rules.write_text('[[group]]\nfolder = "/Game/A"\nkey = "^BK_"\n')
    with pytest.raises(adopt.AdoptError, match='capture group'):
        adopt.load_groups(rules)
    rules.write_text('[[group]]\nfolder = "/Game/A"\nkey = "^(BK)_"\nnames = { BK = "sub" }\n')
    with pytest.raises(adopt.AdoptError, match='share the record name sub'):
        adopt.partition(['/Game/A/BK_1', '/Game/A/Sub/X'], 'A', groups=adopt.load_groups(rules))
    assert adopt.load_groups(tmp_path / 'missing.toml') == {}


def coarse_tree(game, packages, asset_id='adopted/japan', verified=True):
    """An adoption from before ownership units: one record per top-level folder, validated."""
    files = {}
    for package in packages:
        rel = f'unreal/Content/{package[len("/Game/"):]}.uasset'
        write(game / rel, package.encode())
        files[rel] = records.sha256_file(game / rel)
    companion = f'unreal/Content/{packages[0][len("/Game/"):]}.ubulk'
    write(game / companion, b'bulk')
    files[companion] = records.sha256_file(game / companion)
    folder = game / 'assets' / asset_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'asset.toml').write_text(
        f'schema = 1\nid = "{asset_id}"\nkind = "adopted"\nauthority = "editor"\nowner = "shared/japan"\n'
        f'provenance = "{adopt.PROVENANCE}"\nlicense = "owner-published"\n'
        + ''.join(f'[[outputs]]\npackage = "{p}"\n' for p in packages))
    if verified:
        records.write_json(folder / 'verified.json', {'schema': 1, 'kind': 'editor-saved', 'asset': asset_id,
                                                      'engine': 'UE 5.8 test', 'dependencies': {}, 'files': files})
    return files


def membership(game):
    assets, _ = records.discover(game)
    listed = [o.package for a in assets for o in a.outputs]
    verified = {}
    for a in assets:
        if a.verified.is_file():
            for rel, digest in records.load_verified(a.verified)['files'].items():
                assert rel not in verified, f'{rel} verified twice'
                verified[rel] = digest
    return assets, listed, verified


def test_repartition_keeps_membership_exactly_passes_the_check_and_is_idempotent(donor):
    game, _ = donor
    files = coarse_tree(game, TREE)
    report = adopt.repartition(game, cap=200, echo=lambda *_: None)
    assert report['delete'] == ['assets/adopted/japan/asset.toml', 'assets/adopted/japan/verified.json']
    assets, listed, verified = membership(game)
    assert len(assets) == 7 and len(listed) == len(set(listed)) and sorted(listed) == sorted(TREE)
    assert verified == files                     # every verified file carried, into exactly one unit
    assert all(len(a.outputs) <= 200 and a.owner == 'shared/' + a.id[len('adopted/'):] for a in assets)
    assert not (game / 'assets/adopted/japan/asset.toml').exists()
    check = load('v2_adopt_content_check', 'tools/content/check.py')
    problems, _ = check.check(game, full=True, write_index=False)
    assert problems == []                        # single writer: every package exactly one owning record
    stamps = {p: p.stat().st_mtime_ns for p in (game / 'assets').rglob('*') if p.is_file()}
    again = adopt.repartition(game, cap=200, echo=lambda *_: None)
    assert again['write'] == [] and again['delete'] == [] and again['records'] == report['records']
    assert stamps == {p: p.stat().st_mtime_ns for p in (game / 'assets').rglob('*') if p.is_file()}


def test_repartition_refuses_double_ownership_and_lost_packages_writing_nothing(donor, monkeypatch):
    game, _ = donor
    coarse_tree(game, TREE[:3])
    coarse_tree(game, TREE[2:4], asset_id='adopted/japan-extra', verified=False)
    before = sorted((game / 'assets').rglob('*'))
    with pytest.raises(adopt.AdoptError, match=f'{TREE[2]} is owned by both adopted/japan'):
        adopt.repartition(game, echo=lambda *_: None)
    assert sorted((game / 'assets').rglob('*')) == before
    (game / 'assets/adopted/japan-extra/asset.toml').unlink()
    (game / 'assets/adopted/japan-extra').rmdir()
    real = adopt.partition
    monkeypatch.setattr(adopt, 'partition', lambda *a, **k: {u: (o, w, p[1:]) for u, (o, w, p) in real(*a, **k).items()})
    with pytest.raises(adopt.AdoptError, match='would lose 1 and double-own 0'):
        adopt.repartition(game, echo=lambda *_: None)
    assert (game / 'assets/adopted/japan/asset.toml').is_file()


def test_repartition_writes_only_as_adoption_may(donor, monkeypatch):
    game, _ = donor
    coarse_tree(game, TREE)
    monkeypatch.setenv('ATELIER_AGENT', 'someone-else')
    with pytest.raises(adopt.AdoptError, match='not the bootstrap writer'):
        adopt.repartition(game, echo=lambda *_: None)
    assert [a.id for a in records.discover(game)[0]] == ['adopted/japan']
    fake = FakeClaims(scopes=['asset/adopted/japan/hidamari'])
    monkeypatch.setattr(adopt.authority.subprocess, 'run', fake)
    with pytest.raises(adopt.AdoptError, match='no active scope covering'):
        adopt.repartition(game, claim='T9', echo=lambda *_: None)
    fake.scopes = ['asset/adopted/japan']        # the coarse record's scope covers all of its units
    adopt.repartition(game, claim='T9', echo=lambda *_: None)
    paths = fake.checks[0][fake.checks[0].index('--paths') + 1:]
    assert 'games/yorimichi_v2/assets/adopted/japan/asset.toml' in paths
    assert 'games/yorimichi_v2/assets/adopted/japan/hidamari/meshes/verified.json' in paths


def test_a_claim_on_one_unit_does_not_cover_a_sibling_units_package(donor):
    game, _ = donor
    coarse_tree(game, TREE)
    adopt.repartition(game, echo=lambda *_: None)
    authority = adopt.authority
    rel = 'games/yorimichi_v2/unreal/Content/Japan/Hidamari/{}.uasset'.format
    for held in (['asset/adopted/japan/hidamari/meshes'], ['shared/japan/hidamari/meshes']):
        mine, _ = authority.owning_scopes(game, [rel('Meshes/SM_0')])
        assert all(authority.covered(s, held) for s in mine)
        for sibling in ('M_Direct', 'Textures/T_000'):
            theirs, unowned = authority.owning_scopes(game, [rel(sibling)])
            assert theirs and not unowned and not any(authority.covered(s, held) for s in theirs), sibling


def test_adoption_writes_the_repartitioned_units_and_asks_for_repartition_over_coarse_records(donor, monkeypatch):
    game, content = donor
    monkeypatch.setattr(adopt, 'references', lambda path: [])
    for package in TREE:
        write(content / f'{package[len("/Game/"):]}.uasset', package.encode())
    coarse_tree(game, TREE)
    write(content / 'Japan/Hidamari/Textures/T_000.ubulk', b'bulk')     # the coarse tree's companion
    for stray in ('Assets/House_A.uasset', 'Assets/House_A.ubulk', 'Audio/Song.uasset'):
        (content / 'Japan' / stray).unlink()
    with pytest.raises(adopt.AdoptError, match='already owned by adopted/japan .run adopt.py --repartition first'):
        adopt.adopt(game, content, ['Japan'], [], 'owner-published', echo=lambda *_: None)
    adopt.repartition(game, echo=lambda *_: None)
    stamps = {p: p.stat().st_mtime_ns for p in (game / 'assets').rglob('asset.toml')}
    report = adopt.adopt(game, content, ['Japan'], [], 'owner-published', echo=lambda *_: None)
    assert set(report['records']) == {a.id for a in records.discover(game)[0]}
    assert stamps == {p: p.stat().st_mtime_ns for p in (game / 'assets').rglob('asset.toml')}
