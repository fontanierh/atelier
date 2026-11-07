"""Restricted content (D05 group 2) is never tracked, is pinned by hash, and is fetched only as its exact pinned bytes."""
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

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


fetch = load('v2_restricted_fetch', 'tools/restricted/fetch.py')
check = load('v2_restricted_check', 'tools/content/check.py')
ROLL, STEP = 'Audio/Skate/A_Roll.uasset', 'Japan/Audio/Footsteps/A_Step.uexp'


def write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def game(tmp_path):
    game = tmp_path / 'game'
    game.mkdir()
    shutil.copy(ROOT / 'restricted.toml', game / 'restricted.toml')
    write(game / 'unreal/Content' / ROLL, b'roll v1')
    write(game / 'unreal/Content' / STEP, b'step v1')
    return game


@pytest.fixture
def storage(tmp_path, game):
    """Restricted storage laid out like Content, holding the pinned bytes; the local copies are then removed."""
    fetch.pin(game, echo=lambda *_: None)
    store = tmp_path / 'storage'
    shutil.copytree(game / 'unreal/Content', store)
    shutil.rmtree(game / 'unreal/Content/Audio')
    shutil.rmtree(game / 'unreal/Content/Japan')
    return store


def quiet_fetch(game, source=None):
    return fetch.fetch(game, source, echo=lambda *_: None)


def test_pin_then_fetch_round_trips_with_relative_paths_only(game, storage, monkeypatch):
    lock = json.loads((game / 'restricted.lock.json').read_text())
    assert lock == {'schema': 1, 'files': {ROLL: {'sha256': sha(b'roll v1'), 'size': 7},
                                           STEP: {'sha256': sha(b'step v1'), 'size': 7}}}
    assert str(game) not in (game / 'restricted.lock.json').read_text()
    monkeypatch.setenv('V2_RESTRICTED_SOURCE', str(storage))
    assert quiet_fetch(game) == (2, [])
    assert (game / 'unreal/Content' / ROLL).read_bytes() == b'roll v1'
    assert quiet_fetch(game) == (0, [])                       # already present: nothing copied
    monkeypatch.delenv('V2_RESTRICTED_SOURCE')
    with pytest.raises(records.RecordError, match='V2_RESTRICTED_SOURCE'):
        quiet_fetch(game)


def test_pin_keeps_absent_pins_unless_pruned(game, storage):
    write(game / 'unreal/Content/Audio/Bike/A_Bell.uasset', b'bell')
    assert set(fetch.pin(game, echo=lambda *_: None)) == {ROLL, STEP, 'Audio/Bike/A_Bell.uasset'}
    assert set(fetch.pin(game, prune=True, echo=lambda *_: None)) == {'Audio/Bike/A_Bell.uasset'}


def test_a_source_that_disagrees_with_its_pin_is_refused(game, storage):
    write(storage / ROLL, b'roll v2')                          # same size, other bytes
    write(storage / STEP, b'step v1 longer')
    copied, refused = quiet_fetch(game, storage)
    assert copied == 0 and len(refused) == 2
    assert 'hash differs' in ' '.join(refused) and 'size differs' in ' '.join(refused)
    assert not (game / 'unreal/Content' / ROLL).exists()
    assert not list((game / 'unreal/Content').rglob('*.tmp'))
    assert fetch.main(['--game', str(game), 'fetch', '--source', str(storage)]) == 1


def test_a_differing_local_file_is_never_overwritten(game, storage):
    write(game / 'unreal/Content' / ROLL, b'local edit')
    copied, refused = quiet_fetch(game, storage)
    assert copied == 1 and refused and 'never overwritten' in refused[0]
    assert (game / 'unreal/Content' / ROLL).read_bytes() == b'local edit'


def test_the_lock_holds_only_portable_paths_under_the_roots(game):
    restricted = records.load_restricted(game)
    good = {'sha256': '0' * 64, 'size': 1}
    for bad in ('../Audio/x.uasset', '/' + 'Users/someone/Audio/x.uasset', 'Props/SM_X.uasset', 'Audio/readme.txt'):
        records.write_json(restricted.lock, {'schema': 1, 'files': {bad: good}})
        with pytest.raises(records.RecordError):
            records.load_lock(restricted)


def audio_record(game, files: dict[str, bytes]):
    folder = game / 'assets/adopted/audio'
    folder.mkdir(parents=True)
    outputs = ''.join(f'[[outputs]]\npackage = "/Game/{rel.rsplit(".", 1)[0]}"\n' for rel in files)
    (folder / 'asset.toml').write_text('schema = 1\nid = "adopted/audio"\nkind = "adopted"\nauthority = "editor"\n'
                                       f'owner = "shared/audio"\n{outputs}')
    records.write_json(folder / 'verified.json', {
        'schema': 1, 'kind': 'editor-saved', 'asset': 'adopted/audio', 'engine': '5.8.0-test',
        'files': {f'unreal/Content/{rel}': sha(data) for rel, data in files.items()}})


def test_an_absent_restricted_package_fails_unless_explicitly_allowed(tmp_path, game, storage):
    audio_record(game, {ROLL: b'roll v1', STEP: b'step v1'})
    problems, stats = check.check(game, full=True)
    assert [p.code for p in problems] == ['RESTRICTED_ABSENT'] and 'fetch required' in problems[0].detail
    assert check.main(['--game', str(game)]) == 1
    problems, stats = check.check(game, full=True, allow_restricted_absent=True)
    assert problems == []
    assert stats['restricted_absent'] == 2 and [n['code'] for n in stats['notices']] == ['RESTRICTED_ABSENT']
    assert check.main(['--game', str(game), '--allow-restricted-absent']) == 0
    quiet_fetch(game, storage)
    problems, stats = check.check(game, full=True)
    assert problems == [] and stats['restricted_absent'] == 0 and stats['notices'] == []


def test_present_restricted_files_must_match_their_pins(game, storage):
    quiet_fetch(game, storage)
    audio_record(game, {ROLL: b'roll v1'})
    write(game / 'unreal/Content' / ROLL, b'roll v2')
    write(game / 'unreal/Content/Audio/Bike/A_Bell.uasset', b'bell')
    found = {(p.code, p.subject) for p in check.check(game, full=True)[0]}
    assert ('RESTRICTED_CHANGED', ROLL) in found and ('OUTPUT_CHANGED', 'adopted/audio') in found
    assert ('RESTRICTED_UNPINNED', 'Audio/Bike/A_Bell.uasset') in found


def test_a_recorded_restricted_package_without_a_pin_fails(game):
    audio_record(game, {'Audio/Combat/A_Hit.uasset': b'hit'})
    fetch.pin(game, echo=lambda *_: None)
    found = [(p.code, p.subject) for p in check.check(game, full=True)[0]]
    assert ('RESTRICTED_UNPINNED', 'adopted/audio') in found


def test_a_tracked_restricted_path_is_an_error(game):
    fetch.pin(game, echo=lambda *_: None)
    git = lambda *args: subprocess.run(['git', *args], cwd=game, check=True, capture_output=True)  # noqa: E731
    git('init', '-q')
    git('add', '-f', f'unreal/Content/{ROLL}')
    found = [(p.code, p.subject) for p in check.check(game, full=True)[0]]
    assert ('RESTRICTED_TRACKED', f'unreal/Content/{ROLL}') in found


def test_adoption_treats_only_pinned_restricted_references_as_satisfied(tmp_path, game, monkeypatch):
    adopt = load('v2_restricted_adopt', 'tools/migrate/adopt.py')
    fetch.pin(game, echo=lambda *_: None)
    shutil.rmtree(game / 'unreal/Content/Audio')
    donor = tmp_path / 'donor'
    write(donor / 'Skate/BP_Board.uasset', b'board')
    write(donor / 'Japan/Audio/DA_Footsteps.uasset', b'data')     # the donor has it; not adopted in this run
    refs = ['/Game/Audio/Skate/A_Roll', '/Game/Japan/Audio/DA_Footsteps', '/Game/Audio/Combat/A_Gone']
    monkeypatch.setattr(adopt, 'references', lambda path: refs)
    report = adopt.adopt(game, donor, ['Skate'], [], 'owner-published', check_only=True)
    assert report['missing_references'] == {'/Game/Japan/Audio/DA_Footsteps': '/Game/Skate/BP_Board',   # neither adopted nor pinned
                                            '/Game/Audio/Combat/A_Gone': '/Game/Skate/BP_Board'}


def test_this_game_ignores_and_never_tracks_its_restricted_roots():
    if shutil.which('git') is None or subprocess.run(['git', 'rev-parse'], cwd=ROOT, capture_output=True).returncode:
        pytest.skip('not a Git checkout')
    restricted = records.load_restricted(ROOT)
    assert restricted.roots and records.load_lock(restricted) is not None
    for folder in restricted.folders:
        probe = f'unreal/Content/{folder}/Probe/A_Probe.uasset'
        assert subprocess.run(['git', 'check-ignore', '-q', probe], cwd=ROOT).returncode == 0, probe
    assert subprocess.run(['git', 'check-ignore', '-q', 'unreal/Content/Japan/Props/SM_Probe.uasset'],
                          cwd=ROOT).returncode == 1
    assert records.restricted_tracked(ROOT, restricted) == []
