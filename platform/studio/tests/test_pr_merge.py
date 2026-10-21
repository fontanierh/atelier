"""Merge ordering and failure boundaries, without GitHub writes or native work."""
import json
from pathlib import Path

import pytest

from atelier import build_checkpoints, cli, paths, pr_merge
from atelier.checkpoint_store import CheckpointError
from test_checkpoints import fixture

REAL_RETAIN = build_checkpoints.retain


@pytest.fixture
def merge_environment(monkeypatch, tmp_path):
    events = []
    info = dict(url='https://github.com/owner/project/pull/12', state='OPEN', isDraft=False,
                headRefOid='a' * 40,
                statusCheckRollup=[dict(name='Studio Python / macOS', status='COMPLETED', conclusion='SUCCESS')])
    class GitHub:
        def __init__(self, *_):
            pass
        def run(self, args, **kwargs):
            if args[:2] == ['pr', 'view']:
                return json.dumps(info).encode()
            events.append(('merge', args))
            return b''
    def retain(source, *, echo):
        events.append(('retain', source))
        return {'fixture': 'b' * 64}
    monkeypatch.setattr(pr_merge, 'GitHub', GitHub)
    monkeypatch.setattr(pr_merge, 'remote_repository', lambda *_: ('owner', 'project'))
    monkeypatch.setattr(build_checkpoints, 'retain', retain)
    monkeypatch.setattr(paths, 'REPO', tmp_path)
    return info, events


def test_merge_retains_other_producer_before_merging_exact_ci_head(merge_environment, tmp_path):
    info, events = merge_environment
    producer = tmp_path / 'producer'
    assert pr_merge.merge('12', source=producer, echo=lambda _: None) == 0
    assert events[0] == ('retain', producer)
    assert events[1][0] == 'merge'
    assert events[1][1][-2:] == ['--match-head-commit', info['headRefOid']]
    assert '--delete-branch' not in events[1][1]


@pytest.mark.parametrize('state', ['FAILURE', 'PENDING', 'missing'])
def test_merge_refuses_without_exact_head_ci(merge_environment, state):
    info, events = merge_environment
    if state == 'missing':
        info['statusCheckRollup'] = []
    else:
        info['statusCheckRollup'][0]['conclusion'] = state
    with pytest.raises(CheckpointError, match='must pass'):
        pr_merge.merge('12')
    assert not events


def test_retention_failure_prevents_merge(merge_environment, monkeypatch):
    _, events = merge_environment
    def fail(*_, **kwargs):
        raise CheckpointError('guard failed')
    monkeypatch.setattr(build_checkpoints, 'retain', fail)
    with pytest.raises(CheckpointError, match='guard failed'):
        pr_merge.merge('12')
    assert not events


@pytest.mark.parametrize('change', ['head', 'ci', 'draft', 'closed'])
def test_merge_rechecks_after_slow_retention(merge_environment, monkeypatch, change):
    info, events = merge_environment
    def retain(*_, **kwargs):
        events.append(('retained', 'b' * 64))
        if change == 'head':
            info['headRefOid'] = 'c' * 40
        elif change == 'ci':
            info['statusCheckRollup'][0]['conclusion'] = 'FAILURE'
        elif change == 'draft':
            info['isDraft'] = True
        else:
            info['state'] = 'CLOSED'
        return {'fixture': 'b' * 64}
    monkeypatch.setattr(build_checkpoints, 'retain', retain)
    with pytest.raises(CheckpointError):
        pr_merge.merge('12')
    assert events == [('retained', 'b' * 64)]


def test_already_merged_pr_can_backfill_artifacts(merge_environment):
    info, events = merge_environment
    info['state'] = 'MERGED'
    pr_merge.merge('12', echo=lambda _: None)
    assert [e[0] for e in events] == ['retain']


def test_queued_merge_is_not_reported_as_completed(merge_environment):
    messages = []
    pr_merge.merge('12', echo=messages.append)
    assert any('Merge requested; confirm completion:' in m for m in messages)
    assert not any(m.startswith('Merged ') for m in messages)


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
    def capture(source, game):
        captured.append((source, game))
        return game + '-checkpoint'
    monkeypatch.setattr(build_checkpoints, 'capture_local', capture)
    messages = []
    assert build_checkpoints.retain(tmp_path, echo=messages.append) == {'built': 'built-checkpoint', 'partial': 'partial-checkpoint'}
    assert captured == [(tmp_path, 'built'), (tmp_path, 'partial')]
    assert any('no-build: no existing build stamps' in m for m in messages)
    assert not (tmp_path / 'build/no-build').exists()


def test_mistyped_producer_cannot_silently_merge_without_retention(merge_environment, tmp_path, monkeypatch):
    _, events = merge_environment
    # Use the actual source validation, rather than the fixture's retention stub.
    monkeypatch.setattr(build_checkpoints, 'retain', REAL_RETAIN)
    with pytest.raises(CheckpointError, match='existing Atelier Git checkout'):
        pr_merge.merge('12', source=tmp_path / 'missing-producer')
    assert not events


def test_merge_and_retention_cli_route_to_supported_tooling(monkeypatch):
    calls = []
    monkeypatch.setattr(pr_merge, 'merge', lambda pr, **kwargs: calls.append((pr, kwargs)) or 0)
    assert cli.main(['merge', '12', '--source', 'producer']) == 0
    assert calls == [('12', {'source': 'producer'})]
    args = cli.parse_args(['cache', 'retain', 'fixture', '--source', 'producer'])
    assert args.games == ['fixture'] and args.source == Path('producer')


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
