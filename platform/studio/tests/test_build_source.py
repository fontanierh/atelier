"""Source execution keys follow the executed adapter, not unrelated build orchestration."""
from dataclasses import replace
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier import artifact_publisher, build, build_audit, build_cache, build_products, build_source, engine, paths


@pytest.fixture(params=['Python', 'Blender'])
def action(tmp_path, monkeypatch, request):
    binary = tmp_path / 'Fixture.app/Contents/MacOS/Blender'
    binary.parent.mkdir(parents=True)
    binary.write_text('fake tool')
    bundled = binary.parent.parent / 'Resources/runtime.py'
    bundled.parent.mkdir()
    bundled.write_text('bundled runtime')
    monkeypatch.setattr(engine, 'blender', lambda: str(binary))
    for name in ('ATELIER_PYTHON', 'PYTHONPATH', 'PYTHONHOME'):
        monkeypatch.delenv(name, raising=False)
    script = tmp_path / 'action.py'
    script.write_text('# generated source fixture')
    command = (build.Python(script) if request.param == 'Python'
               else build.Blender(script, factory_startup=True))
    step = build.Step('fixture', [command], products=[build.Product('result', (tmp_path / 'result',))],
                      toolchain=True)
    return SimpleNamespace(step=step, kind=request.param, binary=binary, runtime=bundled)


def key(step, changed=None):
    def digest(path):
        value = build_products.file_digest(path)
        return value + ':edited' if Path(path).name == changed else value
    return build.fingerprint(step, {}, index=SimpleNamespace(digest=digest))


@pytest.mark.parametrize('orchestration', ['build.py', 'build_cook.py', 'build_timings.py'])
def test_budget_cook_and_progress_edits_do_not_invalidate_source_actions(action, orchestration):
    assert key(action.step) == key(action.step, orchestration)


@pytest.mark.parametrize('support', ['build_source.py', 'build_inputs.py', 'build_products.py', 'build_cache.py',
                                    'build_hashes.py', 'paths.py', 'build_deferred.py', 'process.py', 'exec_gate.py'])
def test_executed_adapter_and_complete_identity_support_remain_inputs(action, support):
    assert key(action.step) != key(action.step, support)


def test_only_blender_ignores_the_parent_lock(action):
    assert (key(action.step) == key(action.step, 'uv.lock')) is (action.kind == 'Blender')


def test_python_installed_packages_remain_part_of_identity(action, monkeypatch):
    monkeypatch.setattr(build_cache.importlib.metadata, 'distributions', lambda: [])
    before = key(action.step)
    monkeypatch.setattr(build_cache.importlib.metadata, 'distributions', lambda: [
        SimpleNamespace(metadata={'Name': 'fixture-package'}, version='2')])
    assert (key(action.step) != before) is (action.kind == 'Python')


def test_blender_runtime_resources_remain_inputs(action):
    before = key(action.step)
    action.runtime.write_text('changed bundled runtime')
    assert (key(action.step) != before) is (action.kind == 'Blender')


@pytest.mark.parametrize('support', ['build_audit.py', 'build_audit_worker.py', 'build_audit_native.py'])
def test_audit_and_bootstrap_edits_invalidate_audited_actions(action, support):
    action.step.audit = True
    action.step.heavy = action.kind == 'Blender'
    assert key(action.step) != key(action.step, support)


def test_command_arguments_and_source_contents_remain_inputs(action):
    before = key(action.step)
    action.step.commands[0] = replace(action.step.commands[0], args=('different',))
    assert key(action.step) != before
    before = key(action.step)
    action.step.commands[0].script.write_text('# changed actual action')
    assert key(action.step) != before
    if action.kind == 'Blender':
        before = key(action.step)
        action.step.commands[0].env = (('PYTHONHASHSEED', '1'),)
        assert key(action.step) != before


def test_public_command_reexports_and_legacy_representations():
    assert build.Python is build_source.Python and build.Blender is build_source.Blender
    assert repr(build.Python(Path('action.py'))) == "Python(script=PosixPath('action.py'), args=())"
    assert repr(build.Blender(Path('action.py'))) == "Blender(script=PosixPath('action.py'), args=(), threads=6)"
    assert Path(build_source.__file__) in artifact_publisher.TOOL_SUPPORT
    # Trusted publication still pins its host certification engine, independently of action keys.
    assert Path(build.__file__) in artifact_publisher.TOOL_SUPPORT


def test_actual_python_launch_uses_adapter_environment_and_arguments(tmp_path, monkeypatch):
    script = tmp_path / 'action.py'
    script.write_text('import json, os, sys\nprint(json.dumps([sys.argv[1:], os.environ["ATELIER_BUILD_ROOT"]]))\n')
    monkeypatch.setattr(paths, 'build_root', lambda: tmp_path / 'generated')
    ctx = SimpleNamespace(game='fixture', env=lambda extra: pytest.fail('source environment must live in the adapter'))
    step = build.Step('fixture', [build.Python(script, ('exact argument',))])
    log = io.StringIO()
    build.run_command(ctx, step, step.commands[0], log)
    assert json.loads(log.getvalue().splitlines()[-1]) == [['exact argument'], str(tmp_path / 'generated')]


def test_actual_blender_adapter_preserves_guard_callbacks_environment_and_markers(tmp_path, monkeypatch):
    ctx = SimpleNamespace(game='fixture', logs=tmp_path, blender='fixture-blender')
    command = build.Blender(Path('action.py'), ('argument',), threads=3, factory_startup=True,
                            env=(('FIXTURE', 'declared'),))
    command.marker, command.progress = 'DONE', 25.
    polls = []
    command.on_poll = polls.append
    observed = []
    def launch(argv, folder, **kwargs):
        observed.append((argv, kwargs))
        folder.mkdir()
        (folder / 'stdout.log').write_text('DONE\n')
        kwargs['on_slot']('big', '')
        kwargs['on_poll'](123)
        return 0
    monkeypatch.setattr(build_source.guarded, 'run', launch)
    step = build.Step('fixture', [command], heavy=True)
    slots = []
    build.run_command(ctx, step, command, io.StringIO(), ('job', None), slots)
    assert observed[0][0] == ['fixture-blender', '--factory-startup', '-b', '--threads', '3',
                              '--python-exit-code', '1', '--python', 'action.py', '--', 'argument']
    assert observed[0][1]['env']['FIXTURE'] == 'declared'
    assert observed[0][1]['progress'] == 25. and polls == [123] and slots == ['big']
