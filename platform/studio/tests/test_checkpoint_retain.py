"""Local checkpoint retention and capture boundaries, without GitHub writes or native work."""
import json
from pathlib import Path

import pytest

from atelier import build_checkpoints, cli, paths
from atelier.checkpoint_store import CheckpointError
from test_checkpoints import fixture


@pytest.mark.parametrize('deadline', [600, 900])
def test_read_only_capture_uses_original_fingerprints_and_current_capture_code(tmp_path, monkeypatch, deadline):
    import hashlib
    import subprocess
    from atelier import build, checkpoint_candidates
    from atelier.harness.safety import guarded
    source = tmp_path / 'producer'; package = source / 'platform/studio/atelier'
    package.mkdir(parents=True)
    # This stand-in deliberately retains an old fingerprint function and obsolete mutating
    # checkpoint modules. No engine or native process is involved.
    code = Path(build.__file__).read_text()
    code += '''
def fingerprint(step, done, **kwargs):
    return 'a' * 64
class Context:
    def __init__(self, game, *, create=True, **kwargs):
        assert not create
        self.game = game
        self.out = paths.REPO / 'build' / game
        self.stamps = self.out / 'stamps'
        self.logs = self.out / 'logs'
        self.uproject = self.unreal_root = self.blender = None
'''
    (package / 'build.py').write_text(code)
    for name in ('checkpoint_store', 'build_checkpoints', 'checkpoint_worker'):
        (package / (name + '.py')).write_text("raise AssertionError('Old mutating capture code must not execute')\n")
    game = source / 'games/fixture'; game.mkdir(parents=True)
    (game / 'game.toml').write_text('')
    (game / 'helper.py').write_text('VALUE = 1\n')
    (game / 'build.py').write_text("from atelier.build import Step\ndef steps(ctx):\n    return [Step('mesh', [], outputs=[ctx.out / 'mesh.bin'])]\n")
    generated = source / 'build/fixture'; (generated / 'stamps').mkdir(parents=True)
    (generated / 'mesh.bin').write_bytes(b'generated')
    (generated / 'stamps/mesh.json').write_text(json.dumps(dict(fingerprint='a' * 64)))
    (source / '.gitignore').write_text('build/\n__pycache__/\n')
    for args in (['init', '-q'], ['add', '.'], ['-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'source']):
        # A background Git maintenance child can remove its own lock during the
        # full-tree read-only assertion. Keep fixture creation synchronous.
        subprocess.run(['git', '-c', 'maintenance.auto=false', '-c', 'gc.auto=0', '-C', str(source), *args],
                       check=True, capture_output=True)
    def observation():
        return {p.relative_to(source).as_posix(): (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
                for p in source.rglob('*') if p.is_file()}
    before = observation()
    monkeypatch.setenv('ATELIER_CACHE', str(tmp_path / 'cache'))
    monkeypatch.setattr(paths, 'build_root', lambda: tmp_path / 'controller/build')
    def guard(argv, folder, **kwargs):
        assert kwargs['aggregate_tree'] and kwargs['timeout'] == deadline and '-B' in argv and '-u' in argv
        completed = subprocess.run(argv, text=True, capture_output=True, timeout=20)
        assert completed.returncode == 0, completed.stdout + completed.stderr
        return 0
    monkeypatch.setattr(guarded, 'run', guard)
    key = build_checkpoints.capture_local(source, 'fixture', read_only=True, deadline_seconds=deadline)
    saved = checkpoint_candidates.original(checkpoint_candidates.Store('fixture'), key)
    assert saved['candidate_only'] and saved['stamps'] == {}
    assert saved['incremental_stamps']['mesh']['fingerprint'] == 'a' * 64
    assert len(saved['source_revision']) == 40
    assert observation() == before
    assert not list(source.rglob('__pycache__'))


def test_retain_auto_selects_only_games_with_existing_stamps(tmp_path, monkeypatch):
    monkeypatch.delenv('ATELIER_BUILD_ROOT', raising=False)
    (tmp_path / '.git').touch()
    studio = tmp_path / 'platform/studio/atelier'
    studio.mkdir(parents=True); (studio / 'build.py').write_text('')
    for name in ('built', 'partial', 'no-build'):
        game = tmp_path / 'games' / name
        game.mkdir(parents=True); (game / 'game.toml').write_text('')
    for name in ('built', 'partial'):
        stamps = tmp_path / 'build' / name / 'stamps'
        stamps.mkdir(parents=True); (stamps / 'completed.json').write_text('{}')
    captured = []
    def capture(source, output, game):
        assert output == source / 'build' / game
        captured.append((source, game))
        return game + '-checkpoint'
    from atelier import checkpoint_manifest
    monkeypatch.setattr(checkpoint_manifest, 'retain', capture)
    monkeypatch.setattr(build_checkpoints, 'capture_local', lambda *a, **kw: pytest.fail('retention must never launch capture'))
    messages = []
    assert build_checkpoints.retain(tmp_path, echo=messages.append) == {'built': 'built-checkpoint', 'partial': 'partial-checkpoint'}
    assert captured == [(tmp_path, 'built'), (tmp_path, 'partial')]
    assert any('no-build: no existing build stamps' in m for m in messages)
    assert not (tmp_path / 'build/no-build').exists()


@pytest.mark.parametrize('exit_code', [0, 2])
def test_local_capture_uses_guard_and_publishes_to_normal_restore_store(fixture, monkeypatch, exit_code):
    from atelier import checkpoint_store as cp
    from atelier.build_cache import atomic_json
    from atelier.harness.safety import guarded
    ctx, steps = fixture.checkout('producer')
    source = paths.REPO
    game = source / 'games/fixture'; game.mkdir(parents=True)
    (game / 'game.toml').write_text('')
    fixture.produce(ctx, steps)
    before = steps[0].outputs[0].read_bytes()
    monkeypatch.setattr(build_checkpoints, 'Store', lambda _: fixture.store)
    def guard(argv, folder, **options):
        assert options['aggregate_tree'] and options['timeout'] == 3600
        assert 'atelier.checkpoint_worker' in argv[2] and 'capture' in argv
        if exit_code:
            return exit_code
        key = cp.capture(ctx, steps, fixture.store, echo=lambda _: None)
        atomic_json(folder / 'result.json', dict(key=key))
        return 0
    monkeypatch.setattr(guarded, 'run', guard)
    if exit_code:
        with pytest.raises(CheckpointError, match='capture failed'):
            build_checkpoints.capture_local(source, 'fixture')
    else:
        key = build_checkpoints.capture_local(source, 'fixture')
        receiver, current = fixture.checkout('latest-main', changed=True)
        stamps = cp.restore(receiver, current, fixture.store, key, echo=lambda _: None)
        assert set(stamps) == {'tree', 'house'}
    assert before == steps[0].outputs[0].read_bytes()


@pytest.mark.parametrize('deadline', [True, 59, 901, 60.5])
def test_candidate_deadline_refuses_outside_bounded_handoff(tmp_path, deadline):
    with pytest.raises(CheckpointError, match='deadline'):
        build_checkpoints.capture_local(tmp_path, 'fixture', read_only=True, deadline_seconds=deadline)


def test_retention_cli_routes_to_supported_tooling():
    args = cli.parse_args(['cache', 'retain', 'fixture', '--source', 'producer'])
    assert args.games == ['fixture'] and args.source == Path('producer')
    with pytest.raises(SystemExit):
        cli.parse_args(['merge', '12'])
