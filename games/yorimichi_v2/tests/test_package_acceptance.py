"""The V2 package acceptance ledger and automated checks (tools/package/acceptance.py) on a fake package."""
import importlib.util
import json
import plistlib
import subprocess
import sys
from pathlib import Path

import pytest

REAL_RUN = subprocess.run
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'package'))
import acceptance  # noqa: E402
import cook_config  # noqa: E402

BUNDLE = cook_config.bundle_identifier(ROOT)
DATA = b'{"hello": 1}'


def make_app(tmp: Path, *, bundle=BUNDLE, data=DATA, pak=b'pak-1', extra=()):
    app = tmp / 'Yorimichi V2.app'
    (app / 'Contents/MacOS').mkdir(parents=True)
    (app / 'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier': bundle,
                                                             'CFBundleExecutable': 'YorimichiV2'}))
    (app / 'Contents/MacOS/YorimichiV2').write_bytes(b'bin')
    (app / 'Contents/UE/YorimichiV2/Content/Paks').mkdir(parents=True)
    (app / 'Contents/UE/YorimichiV2/Content/Paks/YorimichiV2-Mac.pak').write_bytes(pak)
    (app / 'Contents/UE/YorimichiV2/Content/Data/cairo').mkdir(parents=True)
    (app / 'Contents/UE/YorimichiV2/Content/Data/cairo/character.json').write_bytes(data)
    (app / 'Contents/Frameworks').mkdir(parents=True)
    (app / 'Contents/Frameworks/libx.dylib').write_bytes(b'lib')
    for rel in extra:
        (app / rel).parent.mkdir(parents=True, exist_ok=True)
        (app / rel).write_bytes(b'x')
    return app


def make_game(tmp: Path, data=DATA, name='game'):
    game = tmp / name
    game.mkdir(parents=True)
    (game / 'runtime-data.lock.json').write_text(
        '{"files": {"Data/cairo/character.json": "%s"}}' % acceptance.sha256_bytes(data))
    return game


class Ok:
    def __init__(self, code=0, stdout='', stderr=''):
        self.returncode, self.stdout, self.stderr = code, stdout, stderr


@pytest.fixture(autouse=True)
def fake_game(tmp_path, monkeypatch):
    """The game the ledger reads: its runtime-data lock and Mac identity, both the V2 values the tests pass against."""
    game = make_game(tmp_path, name='fake-game')
    (game / 'unreal/Config/Mac').mkdir(parents=True)
    (game / 'unreal/Config/Mac/MacEngine.ini').write_text(
        f'[/Script/MacTargetPlatform.XcodeProjectSettings]\nBundleIdentifier={BUNDLE}\n')
    monkeypatch.setattr(acceptance, 'GAME', game)
    monkeypatch.setattr(cook_config, 'GAME', game)
    return game


@pytest.fixture
def tools(monkeypatch):
    """codesign and otool stand-ins: a valid signature and dependencies inside the package by default."""
    state = {'codesign': Ok(0, '', ''), 'otool': ''}

    def fake_run(argv, **kwargs):
        if argv[0] == 'codesign':
            return state['codesign']
        if argv[0] == 'otool':
            return Ok(0, state['otool'], '')
        return REAL_RUN(argv, **kwargs)
    monkeypatch.setattr(acceptance.subprocess, 'run', fake_run)
    return state


def test_identity_refuses_the_template_bundle(tmp_path, tools):
    game_app = make_app(tmp_path, bundle='com.YourCompany.YorimichiV2')
    assert [c.name for c in acceptance.check_identity(game_app) if not c.ok] == ['identity.bundle_id']


def test_bundled_dependency_outside_the_package_fails(tmp_path, tools):
    app = make_app(tmp_path)
    tools['otool'] = 'x:\n\t/opt/ue-build/Intermediate/libfoo.dylib (compatibility version 1.0.0)\n\t/usr/lib/libz.dylib (x)\n'
    result = acceptance.check_bundled_deps(app)[0]
    assert not result.ok and 'libfoo' in result.detail
    tools['otool'] = 'x:\n\t@rpath/libx.dylib (x)\n\t/usr/lib/libz.dylib (x)\n'
    assert acceptance.check_bundled_deps(app)[0].ok
    # A universal binary repeats its own path as a header per architecture: that is not a dependency.
    tools['otool'] = ('/opt/pkg/A.app/Contents/UE/Binaries/Mac/libx.dylib (architecture x86_64):\n\t@rpath/libx.dylib (x)\n'
                      '/opt/pkg/A.app/Contents/UE/Binaries/Mac/libx.dylib (architecture arm64):\n\t@rpath/libx.dylib (x)\n')
    assert acceptance.check_bundled_deps(app)[0].ok


def test_a_sandboxed_app_needs_the_coreaudio_lookup(tmp_path, tools):
    app = make_app(tmp_path)
    sandbox = {'com.apple.security.app-sandbox': True}
    tools['codesign'] = Ok(0, plistlib.dumps(sandbox), b'')
    assert not acceptance.check_entitlements(app)[0].ok
    sandbox[acceptance.MACH_LOOKUP] = [acceptance.AUDIO_LOOKUP]
    tools['codesign'] = Ok(0, plistlib.dumps(sandbox), b'')
    assert acceptance.check_entitlements(app)[0].ok


def test_excluded_names_fail(tmp_path, tools):
    app = make_app(tmp_path, extra=['Contents/UE/YorimichiV2/Content/Japan/Kart/Car.pak'])
    assert not acceptance.check_excluded(app)[0].ok


def test_runtime_data_must_match_committed_bytes(tmp_path, tools):
    game = make_game(tmp_path)
    assert acceptance.check_runtime_data(make_app(tmp_path / 'a'), game)[0].ok
    bad = make_app(tmp_path / 'b', data=b'changed')
    assert not acceptance.check_runtime_data(bad, game)[0].ok


def test_fingerprint_moves_with_paks_and_data_not_with_extra_files(tmp_path):
    app = make_app(tmp_path)
    before = acceptance.fingerprint(app)
    (app / 'Contents/UE/YorimichiV2/Content/Paks/YorimichiV2-Mac.pak').write_bytes(b'pak-2')
    after_pak = acceptance.fingerprint(app)
    assert after_pak != before
    (app / 'Contents/UE/YorimichiV2/Content/Data/cairo/character.json').write_bytes(b'z')
    assert acceptance.fingerprint(app) != after_pak
    (app / 'Contents/Resources').mkdir(parents=True)
    (app / 'Contents/Resources/readme.txt').write_bytes(b'note')
    assert acceptance.fingerprint(app) == acceptance.fingerprint(app)


def test_ledger_binds_evidence_to_one_package(tmp_path, tools):
    app = make_app(tmp_path)
    evidence = tmp_path / 'ev' / 'evidence.json'
    for item in acceptance.MANUAL:
        acceptance.record(app, evidence, item, 'pass', 'seen', reset=False)
    report = acceptance.verify(app, evidence, multiplayer=False)
    assert report['verdict'] == 'pass', report['failed']
    # a different package: the old evidence refuses to record, and verify sees no evidence for it
    (app / 'Contents/UE/YorimichiV2/Content/Paks/YorimichiV2-Mac.pak').write_bytes(b'pak-new')
    with pytest.raises(SystemExit):
        acceptance.record(app, evidence, 'input', 'pass', 'again', reset=False)
    assert 'manual.first_launch' in acceptance.verify(app, evidence, multiplayer=False)['failed']


def test_failed_item_and_multiplayer_stay_required(tmp_path, tools):
    app = make_app(tmp_path)
    evidence = tmp_path / 'evidence.json'
    for item in acceptance.MANUAL:
        acceptance.record(app, evidence, item, 'pass', 'seen', reset=False)
    acceptance.record(app, evidence, 'sound', 'fail', 'no effects', reset=False)
    assert 'manual.sound' in acceptance.verify(app, evidence, multiplayer=False)['failed']
    assert 'manual.two_machine_multiplayer' in acceptance.verify(app, evidence, multiplayer=True)['failed']


def test_unknown_item_is_refused(tmp_path, tools):
    with pytest.raises(SystemExit):
        acceptance.record(make_app(tmp_path), tmp_path / 'e.json', 'vibes', 'pass', '', reset=False)


def test_check_details_name_the_bundle_not_its_folder(tmp_path):
    """Shareable evidence carries no extraction folder or home path (CONTRACTS yorimichi-v2-portable-records)."""
    app = tmp_path / 'deep' / 'YorimichiV2.app'
    text = (f'{app}/Contents/MacOS/YorimichiV2: code object is not signed; {Path.home()}/x; '
            f"foreign ['/Volumes/Donor/Build/Intermediate/libfoo.dylib']")
    assert acceptance.portable(text, app) == ('YorimichiV2.app/Contents/MacOS/YorimichiV2: code object is not signed; x; '
                                              "foreign ['libfoo.dylib']")


def test_recorded_evidence_carries_no_time(tmp_path, tools):
    """The ledger is shareable evidence too: status and note only, no timestamp (yorimichi-v2-portable-records)."""
    app, evidence = make_app(tmp_path), tmp_path / 'e.json'
    acceptance.record(app, evidence, 'first_launch', 'pass', 'ok', reset=False)
    assert json.loads(evidence.read_text())['items']['first_launch'] == {'status': 'pass', 'note': 'ok'}


def test_manual_notes_are_portable_when_recorded_and_reported(tmp_path, tools):
    """A tester's note naming a local folder keeps only its last part, in the ledger and in the report."""
    app, evidence = make_app(tmp_path), tmp_path / 'e.json'
    acceptance.record(app, evidence, 'save_persistence', 'pass', 'restored from /Volumes/Alice/Saved/SaveGames', reset=False)
    assert json.loads(evidence.read_text())['items']['save_persistence']['note'] == 'restored from SaveGames'
    ledger = json.loads(evidence.read_text())
    ledger['items']['first_launch'] = {'status': 'pass', 'note': 'ran /Volumes/Alice/YorimichiV2.app'}
    evidence.write_text(json.dumps(ledger))
    report = acceptance.verify(app, evidence, multiplayer=False)
    assert '/Volumes/' not in json.dumps(report)
