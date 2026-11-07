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
    asset = records.load_asset(game / 'assets/adopted/japan/asset.toml')
    assert asset.kind == 'adopted' and asset.authority == 'editor'
    assert [o.package for o in asset.outputs] == ['/Game/Japan/Assets/House_A']


def test_check_only_writes_nothing_and_a_rerun_changes_nothing(donor):
    game, content = donor
    adopt.adopt(game, content, ['Japan'], [], 'x', check_only=True)
    assert not (game / 'assets').exists() and not (game / 'unreal/Content/Japan').exists()
    adopt.adopt(game, content, ['Japan'], [], 'x', echo=lambda *_: None)
    record = game / 'assets/adopted/japan/asset.toml'
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
    with pytest.raises(adopt.AdoptError, match='no active scope covering asset/adopted/japan'):
        adopt.adopt(game, content, ['Japan'], [], 'x', claim='T7', echo=lambda *_: None)
    assert not (game / 'unreal/Content/Japan').exists()


def test_runtime_data_copies_regular_files(donor):
    game, content = donor
    assert adopt.copy_data(game, content, echo=lambda *_: None) == 1
    assert adopt.copy_data(game, content, echo=lambda *_: None) == 0
    assert tomllib  # stdlib only
