"""Snapshot launch barriers with temporary paths and no native process launches."""
from types import SimpleNamespace

import pytest

from atelier import artifact_pool, build, build_plan, build_snapshot, cli, paths, playtest, stream
from atelier.safety import process


@pytest.fixture
def snapshot(tmp_path, monkeypatch):
    repo, alternate = tmp_path / 'repo', tmp_path / 'alternate'
    out = alternate / 'standin'
    project = repo / 'games/standin/unreal/Standin.uproject'
    project.parent.mkdir(parents=True)
    project.write_text('{}')
    journal = repo / 'build/standin' / build_snapshot.JOURNAL
    journal.parent.mkdir(parents=True)
    journal.write_text('{}')
    monkeypatch.setattr(paths, 'REPO', repo)
    monkeypatch.setattr(paths, 'build_root', lambda: alternate)
    monkeypatch.setenv('ATELIER_BUILD_ROOT', str(alternate))
    ctx = SimpleNamespace(game='standin', out=out)
    monkeypatch.setattr(build, 'Context', lambda *args, **kwargs: ctx)
    monkeypatch.setattr(cli, 'Context', lambda *args, **kwargs: ctx)
    return SimpleNamespace(repo=repo, out=out, project=project, journal=journal)


@pytest.mark.parametrize('entry', ['build', 'plan', 'private-build', 'play', 'qa', 'playtest', 'stream', 'pool'])
def test_output_override_cannot_hide_default_snapshot_journal(snapshot, entry):
    s = snapshot
    calls = {
        'build': lambda: build.build('standin'),
        'plan': lambda: build.build('standin', dry=True),
        'private-build': lambda: build._build(SimpleNamespace(game='standin', out=s.out), [], force=True,
                                             touch=False, echo=lambda _: None, index=None, steps=[]),
        'play': lambda: cli.play('standin', 'default', None, []),
        'qa': lambda: cli.main(['qa', 'standin', 'fixture']),
        'playtest': lambda: playtest.main('standin'),
        'stream': lambda: stream.start(SimpleNamespace(id='standin')),
        'pool': lambda: artifact_pool.main('publish', 'standin', 'unused'),
    }
    with pytest.raises(SystemExit, match='interrupted'):
        calls[entry]()
    assert s.journal.read_text() == '{}'
    assert not s.out.exists()


@pytest.mark.parametrize('uat', [False, True])
@pytest.mark.parametrize('override', [False, True])
def test_direct_launch_uses_project_default_root_before_spawning(snapshot, monkeypatch, uat, override):
    s = snapshot
    monkeypatch.setattr(process.subprocess, 'Popen', lambda *a, **kw: pytest.fail('partial snapshot launched'))
    argument = ('-project=' if uat else '') + str(s.project)
    env = {'ATELIER_BUILD_ROOT': str(s.out.parent)} if override else {}
    with pytest.raises(SystemExit, match='interrupted'):
        process.spawn(['fixture-launcher', argument], env=env)


def test_clean_alternate_root_stays_usable_and_its_own_journal_is_checked(snapshot, monkeypatch):
    s = snapshot
    s.journal.unlink()
    monkeypatch.setattr(build_plan, 'show', lambda *a, **kw: 37)
    assert build.build('standin', dry=True) == 37
    build_snapshot.require_launch(['fixture-launcher', str(s.project)],
                                  env={'ATELIER_BUILD_ROOT': str(s.out.parent)})
    assert not s.out.exists()
    s.out.mkdir(parents=True)
    (s.out / build_snapshot.JOURNAL).write_text('{}')
    with pytest.raises(SystemExit, match='interrupted'):
        build.build('standin', dry=True)
    with pytest.raises(SystemExit, match='interrupted'):
        build_snapshot.require_launch(['fixture-launcher', str(s.project)],
                                      env={'ATELIER_BUILD_ROOT': str(s.out.parent)})


def test_foreign_project_does_not_consult_controller_journal(snapshot, tmp_path, monkeypatch):
    s = snapshot
    foreign = tmp_path / 'foreign'
    project = foreign / 'games/standin/unreal/Standin.uproject'
    project.parent.mkdir(parents=True)
    project.write_text('{}')
    calls = []
    monkeypatch.setattr(process.subprocess, 'Popen', lambda *a, **kw: calls.append((a, kw)))
    # The controller is incomplete, but neither the foreign default nor selected output is.
    process.spawn(['fixture-launcher', '-project=' + str(project)],
                  env={'ATELIER_BUILD_ROOT': str(s.out.parent)})
    assert len(calls) == 1 and s.journal.exists()
    journal = foreign / 'build/standin' / build_snapshot.JOURNAL
    journal.parent.mkdir(parents=True)
    journal.write_text('{}')
    with pytest.raises(SystemExit, match='interrupted'):
        process.spawn(['fixture-launcher', '-project=' + str(project)],
                      env={'ATELIER_BUILD_ROOT': str(s.out.parent)})
    assert len(calls) == 1


@pytest.mark.parametrize('relative_cwd', [False, True])
def test_relative_output_root_is_checked_against_child_cwd(snapshot, tmp_path, monkeypatch, relative_cwd):
    foreign = tmp_path / 'foreign'
    project = foreign / 'games/standin/unreal/Standin.uproject'
    project.parent.mkdir(parents=True)
    project.write_text('{}')
    journal = foreign / 'alternate/standin' / build_snapshot.JOURNAL
    journal.parent.mkdir(parents=True)
    journal.write_text('{}')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(process.subprocess, 'Popen', lambda *a, **kw: pytest.fail('partial snapshot launched'))
    with pytest.raises(SystemExit, match='interrupted'):
        process.spawn(['fixture-launcher', '-project=games/standin/unreal/Standin.uproject'],
                      cwd='foreign' if relative_cwd else foreign, env={'ATELIER_BUILD_ROOT': 'alternate'})
