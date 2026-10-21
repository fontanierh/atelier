"""File preparation precedes editor exec under one normal guarded root; no editor runs here."""
from dataclasses import replace
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from atelier import build, build_batches, unreal_preflight as prepare


@pytest.fixture
def hook(tmp_path, monkeypatch):
    script = tmp_path / 'prepare.py'
    script.write_text("from pathlib import Path\nimport os\nPath(os.environ['DEST']).joinpath(os.environ.get('OWNER','single')).write_text(str(os.getpid()))\n")
    monkeypatch.setenv(prepare.KEY, str(script))
    monkeypatch.setenv('DEST', str(tmp_path))
    return script


def plan(hook, owners=('one', 'two')):
    path = hook.parent / 'plan.json'
    path.write_text(json.dumps(dict(kind='UnrealScript', actions=[
        dict(name=owner, env={prepare.KEY: str(hook), 'OWNER': owner}) for owner in owners])))
    return path


def test_wrap_is_read_only_before_guard_admission(hook):
    argv = ['editor with spaces', '-script=original.py', '-NullRHI']
    wrapped = prepare.wrap(argv, hook)
    assert wrapped[wrapped.index('--') + 1:] == argv
    assert not (hook.parent / 'single').exists()


def test_actual_exec_preserves_pid_and_original_argv(hook):
    child = hook.parent / 'editor_standin.py'
    child.write_text("from pathlib import Path\nimport os,sys\nPath(os.environ['DEST']).joinpath('after').write_text(str(os.getpid())+'|'+repr(sys.argv[1:]))\n")
    original = [sys.executable, str(child), 'argument with spaces', '--literal']
    process = subprocess.Popen(prepare.wrap(original, hook), env=dict(os.environ))
    assert process.wait(timeout=10) == 0
    assert (hook.parent / 'single').read_text() == str(process.pid)
    assert (hook.parent / 'after').read_text() == str(process.pid) + "|['argument with spaces', '--literal']"


def test_every_selected_owner_is_prepared_before_exec_with_original_environment_restored(hook):
    path = plan(hook)
    raw = path.read_bytes()
    before_env, before_path, before_args = dict(os.environ), list(sys.path), list(sys.argv)
    prepare.prepare(hook, path, hashlib.sha256(raw).hexdigest())
    assert (hook.parent / 'one').exists() and (hook.parent / 'two').exists()
    assert not (hook.parent / 'single').exists()
    assert dict(os.environ) == before_env and sys.path == before_path and sys.argv == before_args


def test_changed_plan_while_queued_refuses_before_any_file_preparation(hook):
    path = plan(hook)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    value = json.loads(path.read_text());value['actions'][0]['env']['OWNER'] = 'unexpected'
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='during admission wait'):
        prepare.prepare(hook, path, digest)
    assert not (hook.parent / 'unexpected').exists() and not (hook.parent / 'two').exists()


@pytest.mark.parametrize('bad', ['other-hook', 'wrong-kind', 'empty'])
def test_all_batch_metadata_is_checked_before_the_first_preparation(hook, bad):
    path = plan(hook)
    value = json.loads(path.read_text())
    if bad == 'other-hook':
        value['actions'][1]['env'][prepare.KEY] = 'different.py'
    elif bad == 'wrong-kind':
        value['kind'] = 'Blender'
    else:
        value['actions'] = []
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='must share'):
        prepare.prepare(hook, path, hashlib.sha256(path.read_bytes()).hexdigest())
    assert not (hook.parent / 'one').exists()


def test_hook_failure_prevents_exec_and_restores_environment(hook, monkeypatch):
    hook.write_text("import os\nos.environ['LEAK']='bad'\nraise RuntimeError('preparation refused')\n")
    argv = [str(Path(prepare.__file__)), '--script', str(hook), '--', 'never-exec']
    monkeypatch.setattr(sys, 'argv', argv)
    monkeypatch.setattr(prepare.os, 'execvpe', lambda *args: pytest.fail('Failed preflight must never exec'))
    before = dict(os.environ)
    with pytest.raises(RuntimeError, match='preparation refused'):
        prepare.main()
    assert dict(os.environ) == before


def test_importing_unreal_in_a_hook_refuses_before_exec(hook, monkeypatch):
    monkeypatch.delitem(sys.modules, 'unreal', raising=False)
    hook.write_text("import sys\nsys.modules['unreal']=object()\n")
    try:
        with pytest.raises(RuntimeError, match='must not import Unreal'):
            prepare.prepare(hook)
    finally:
        sys.modules.pop('unreal', None)


def test_symlink_or_hardlinked_plan_refuses(hook):
    path = plan(hook)
    link = hook.parent / 'link.json'
    link.symlink_to(path)
    with pytest.raises(OSError):
        prepare.read_plan(link)
    link.unlink()
    os.link(path, link)
    with pytest.raises(ValueError, match='owned bounded regular'):
        prepare.read_plan(path)


def test_preparation_cannot_enter_an_unguarded_build_path(hook):
    command = build.UnrealScript(Path('import.py'), 'DONE', env=((prepare.KEY, str(hook)),))
    with pytest.raises(ValueError, match='guarded heavy lifecycle'):
        build.run_argv(SimpleNamespace(), build.Step('import', [command]), command, ['editor'], (),
                       io.StringIO(), None, None)
    assert not (hook.parent / 'single').exists()


def test_explicit_startup_override_preserves_batch_compatibility_and_declares_code(hook):
    command = build.UnrealScript(Path('import.py'), 'DONE', env=((prepare.KEY, str(hook)),))
    first = build.Step('one', [command], batch=build.Batch('native'))
    same = replace(first, name='two')
    other = replace(first, commands=[replace(command, env=())])
    assert build_batches.compatible(first, same)
    assert not build_batches.compatible(first, other)
    assert Path(prepare.__file__) in command.runs() and hook in command.runs()
    assert Path(prepare.__file__) not in build.UnrealScript(Path('import.py'), 'DONE').runs()


def test_normal_build_keeps_one_guard_and_requires_aggregate_before_preflight(hook, monkeypatch):
    command = build.UnrealScript(Path('import.py'), 'DONE', env=((prepare.KEY, str(hook)),))
    ctx = SimpleNamespace(logs=hook.parent / 'logs', out=hook.parent / 'build', env=lambda extra: dict(extra), game='fixture')
    step = build.Step('import', [command], heavy=True)
    calls = []
    def guard(argv, folder, **kwargs):
        calls.append(kwargs)
        assert kwargs['aggregate_tree'] is True
        folder.mkdir(parents=True)
        (folder / 'stdout.log').write_text('DONE\n')
        return 0
    monkeypatch.setattr(build.guarded, 'run', guard)
    build.run_argv(ctx, step, command, ['wrapped-editor'], command.env, io.StringIO(), ('job', None), None)
    assert len(calls) == 1 and calls[0]['kind'] == 'job'
