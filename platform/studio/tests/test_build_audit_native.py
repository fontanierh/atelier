"""Native Python adapter protocol with ordinary Python stand-ins, never native processes."""
from dataclasses import replace
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import py_compile
import subprocess
import sys
import sysconfig
from types import SimpleNamespace

import pytest

from atelier import build, build_audit, build_batches, build_cache, build_plan, build_products, engine
from atelier import build_audit_native


@pytest.fixture(params=['Blender', 'UnrealScript'])
def native_action(tmp_path, monkeypatch, request):
    root = tmp_path.resolve()
    host = root / 'host.py'
    host.write_text('''import os, runpy, sys
bootstrap = next((arg.split('=', 1)[1] for arg in sys.argv if arg.startswith('-script=')), None)
if bootstrap is None:
    bootstrap = sys.argv[sys.argv.index('--python') + 1]
sys.argv = [bootstrap]
namespace = runpy.run_path(bootstrap, run_name='__main__')
''')
    executable = root / 'host'
    executable.write_text(f'#!{sys.executable}\n' + host.read_text())
    executable.chmod(0o755)
    source, script, output = root / 'source.txt', root / 'generate.py', root / 'out/result.txt'
    source.write_text('input')
    ctx = SimpleNamespace(game='fixture', out=output.parent, logs=output.parent / 'logs',
                          stamps=output.parent / 'stamps', blender=str(executable), unreal_cmd=executable,
                          uproject=root / 'project/project.uproject',
                          env=lambda extra=(): dict(os.environ) | dict(extra))
    command = (build.Blender(script, (source, output), factory_startup=True)
               if request.param == 'Blender' else build.UnrealScript(script, 'NATIVE DONE', null_rhi=True))
    step = build.Step('generate', [command], inputs=[source], products=[build.Product('result', (output,))],
                      audit=True, heavy=True)
    steps, calls, messages = [step], [], []
    monkeypatch.setattr(build, 'Context', lambda *args, **kwargs: ctx)
    monkeypatch.setattr(build, 'load_recipe', lambda game: SimpleNamespace(steps=lambda ctx: steps))
    monkeypatch.setattr(build_audit, 'tool_context', lambda *args, **kwargs: {'fake-host': request.param})
    approved = sorted({str(Path(sysconfig.get_path(n)).resolve())
                       for n in ('stdlib', 'platstdlib', 'purelib', 'platlib')})
    monkeypatch.setattr(build_audit, 'installation', lambda command: approved)

    def guard(argv, folder, **kwargs):
        calls.append((argv, kwargs))
        folder.mkdir(exist_ok=True)
        with (folder / 'stdout.log').open('w') as log:
            return subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT, env=kwargs['env'],
                                  pass_fds=kwargs['pass_fds'], stdin=subprocess.DEVNULL).returncode

    monkeypatch.setattr(build.guarded, 'run', guard)

    def code(body):
        script.write_text(f'from pathlib import Path\nimport sys\nsource = Path({str(source)!r})\n'
                          f'output = Path({str(output)!r})\n{body}\nprint("NATIVE DONE", flush=True)\n')

    return SimpleNamespace(root=root, host=host, executable=executable, source=source, script=script,
                           output=output, ctx=ctx, step=step, steps=steps, calls=calls, messages=messages,
                           code=code, run=lambda: build.build('fixture', echo=messages.append),
                           report=lambda: json.loads((ctx.logs / 'generate.audit.json').read_text()),
                           stamp=lambda: json.loads((ctx.stamps / 'generate.json').read_text()))


def test_native_audit_uses_existing_guard_and_owns_argv_and_report(native_action):
    a = native_action
    a.code("output.write_text(source.read_text())\nassert sys.pycache_prefix\nassert sys.dont_write_bytecode")
    assert a.run() == 0, a.messages
    assert a.output.read_text() == 'input' and a.report()['passed']
    argv, options = a.calls[0]
    assert options['pass_fds'] and options['kind'] == 'job' and 'lock' not in options
    assert str(build_audit.NATIVE) in ' '.join(argv)
    assert a.stamp()['audit_receipt']['execution'] == 'audited-native-python-v1'
    if isinstance(a.step.commands[0], build.Blender):
        assert '--factory-startup' in argv
    else:
        assert '-NullRHI' in argv
    assert a.run() == 0 and len(a.calls) == 1


@pytest.mark.parametrize('body', [
    "try:\n    hidden.read_text()\nexcept PermissionError:\n    pass\noutput.write_text('made')",
    "output.write_text('made')\nraise RuntimeError('failed')",
    "output.write_text('made')\n__import__('os')._exit(0)",
    "output.write_text(output.read_text())",
], ids=['caught-violation', 'failure', 'incomplete', 'stale-output'])
def test_native_failure_never_certifies_even_with_existing_outputs(native_action, body):
    a = native_action
    hidden = a.root / 'hidden.txt'
    hidden.write_text('undeclared')
    a.output.parent.mkdir()
    a.output.write_text('old')
    a.code(f'hidden = Path({str(hidden)!r})\n' + body)
    assert a.run() == 1, a.messages
    assert not a.report()['passed']
    assert not (a.ctx.stamps / 'generate.json').exists()


@pytest.mark.parametrize('postlude', [
    "try:\n    namespace['main']()\nexcept PermissionError:\n    pass\n",
    "try:\n    open(sys._atelier_native_audit_started.spec['script']).read()\nexcept PermissionError:\n    pass\n",
], ids=['second-action', 'post-completion-read'])
def test_native_hook_remains_armed_through_host_teardown(native_action, postlude):
    a = native_action
    # Even an otherwise allowed, previously observed read after COMPLETE invalidates the report.
    a.executable.write_text(a.executable.read_text() + postlude)
    a.code("output.write_text(source.read_text())")
    assert a.run() == 1
    assert not a.report()['passed'] and not a.report()['complete']
    assert not (a.ctx.stamps / 'generate.json').exists()


@pytest.mark.parametrize('problem', ['nonce', 'order', 'duplicate-completion', 'failed-completion'])
def test_fake_native_host_cannot_certify_bad_report(native_action, problem):
    a = native_action
    a.code("output.write_text('made')")
    a.executable.write_text(f'''#!{sys.executable}
import json, os
from pathlib import Path
spec = json.loads(Path(os.environ['ATELIER_AUDIT_SPEC']).read_text())
nonce = spec['nonce']
records = [dict(kind='start', nonce=nonce), dict(kind='complete', nonce=nonce, success=True)]
problem = {problem!r}
if problem == 'nonce':
    records[-1]['nonce'] = 'previous-run'
elif problem == 'order':
    records.reverse()
elif problem == 'duplicate-completion':
    records.append(records[-1])
else:
    records[-1]['success'] = False
Path(spec['outputs'][0]).write_text('made')
for record in records:
    os.write(spec['fd'], (json.dumps(record) + '\\n').encode())
print('NATIVE DONE', flush=True)
''')
    assert a.run() == 1
    assert not a.report()['passed']
    assert not (a.ctx.stamps / 'generate.json').exists()


def test_native_audit_batch_declaration_runs_each_action_in_fresh_host(native_action):
    a = native_action
    a.step.batch = build.Batch('audited')
    a.code("output.write_text(source.read_text())")
    script, output = a.root / 'next.py', a.output.with_name('next.txt')
    script.write_text(a.script.read_text().replace(str(a.output), str(output)))
    next_step = replace(a.step, name='next', commands=[replace(a.step.commands[0], script=script)],
                        products=[build.Product('next', (output,))])
    a.steps.append(next_step)
    assert a.run() == 0, a.messages
    assert len(a.calls) == 2
    assert all('ATELIER_BATCH' not in call[1]['env'] for call in a.calls)
    assert output.read_text() == 'input'
    assert not build_batches.compatible(a.step, next_step)
    assert not build_batches.compatible(replace(a.step, audit=False), next_step)
    with pytest.raises(ValueError, match='fresh native'):
        build_batches.run(a.ctx, [(a.step, 'key', {})], {}, index=None, tool_cache={},
                          echo=lambda text: None, products={})


def test_native_audit_does_not_enable_cache_or_unguarded_commands(native_action):
    a = native_action
    for bad in (replace(a.step, cache=True), replace(a.step, heavy=False)):
        with pytest.raises(ValueError, match='heavy=True and cache=False'):
            build_products.Graph([bad])
    if isinstance(a.step.commands[0], build.UnrealScript):
        with pytest.raises(ValueError, match='portable caching'):
            build_cache.roots(a.ctx, a.step)


def test_host_with_runtime_outside_hashed_installation_cannot_complete(native_action, monkeypatch):
    a = native_action
    a.code("output.write_text('made')")
    monkeypatch.setattr(build_audit, 'installation', lambda command: [a.root / 'unrelated'])
    assert a.run() == 1
    assert not a.report()['complete'] and not a.report()['passed']
    assert not (a.ctx.stamps / 'generate.json').exists()


def test_native_action_cannot_return_with_live_python_threads(native_action):
    a = native_action
    a.code("import threading\nthreading.Thread(target=threading.Event().wait, daemon=True).start()\n"
           "output.write_text('made')")
    assert a.run() == 1
    assert any(v['operation'] == 'threads' for v in a.report()['violations'])
    assert not (a.ctx.stamps / 'generate.json').exists()


def test_unreal_adapter_preserves_descriptor_and_trusted_module_checks(native_action, monkeypatch):
    a = native_action
    if not isinstance(a.step.commands[0], build.UnrealScript):
        pytest.skip('Unreal descriptor protocol')
    from atelier import unreal_modules
    checks = a.root / 'module-checks.txt'
    descriptor_events = []

    @contextmanager
    def descriptor(project, modules):
        assert modules == ('Declared',)
        temporary = a.root / 'isolated.uproject'
        temporary.write_text('{}')
        descriptor_events.append('open')
        try:
            yield temporary, ['excluded.dylib']
        finally:
            temporary.unlink()
            descriptor_events.append('closed')

    monkeypatch.setattr(unreal_modules, 'descriptor', descriptor)
    a.step.commands[0].modules = ('Declared',)
    a.step.needs = ['unreal.module.Declared']
    a.steps.insert(0, build.Step('unreal.module.Declared', []))
    # Substitute only the library-inspection helper in this Python stand-in. No dyld call occurs.
    a.executable.write_text(f'''#!{sys.executable}
import os, runpy, sys
from pathlib import Path
from types import SimpleNamespace
bootstrap = next(arg.split('=', 1)[1] for arg in sys.argv if arg.startswith('-script='))
assert '-script={build_audit.NATIVE}' in sys.argv
assert Path(sys.argv[1]).exists()
namespace = runpy.run_path(bootstrap, run_name='fake_framework')
original = namespace['load']
def check(script, left_out, stop):
    assert left_out == ['excluded.dylib']
    with open({str(checks)!r}, 'a') as stream:
        stream.write('checked\\n')
def load(name, path):
    if path.name == 'unreal_script_guard.py':
        return SimpleNamespace(check=check, stop=lambda message: sys.exit(3))
    return original(name, path)
namespace['main'].__globals__['load'] = load
namespace['main']()
''')
    a.code("output.write_text(source.read_text())")
    assert a.run() == 0, a.messages
    assert checks.read_text() == 'checked\nchecked\n'
    assert descriptor_events == ['open', 'closed']
    assert a.report()['passed']
    a.code(f'''try:
    Path({str(checks)!r}).read_text()
except PermissionError:
    pass
output.write_text('made')''')
    assert a.run() == 1
    assert a.report()['violations'] and not a.report()['passed']
    assert descriptor_events == ['open', 'closed', 'open', 'closed']


def test_native_products_can_live_in_owned_content_but_not_linked_or_reserved_paths(native_action):
    a = native_action
    a.code("output.write_text('made')")
    if isinstance(a.step.commands[0], build.UnrealScript):
        content = a.ctx.uproject.parent / 'Content/owned/package.uasset'
        native = replace(a.step, products=[build.Product('native', (content,))])
        build_audit.roots(a.ctx, native)
        a.steps[:] = [native]
        assert build_plan.inspect(a.ctx, [native])
        assert not a.ctx.out.exists()
    for path in (a.ctx.out, a.ctx.logs / 'result', a.root / 'source-other'):
        with pytest.raises(ValueError, match='generated subpath'):
            build_audit.roots(a.ctx, replace(a.step, products=[build.Product('bad', (path,))]))
    a.output.parent.mkdir()
    a.output.symlink_to(a.source)
    with pytest.raises(ValueError, match='Linked'):
        build_audit.roots(a.ctx, a.step)


def test_bootstrap_runtime_exemptions_never_follow_arbitrary_sys_path(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(tmp_path))
    roots = build_audit_native.runtime_roots([sys.base_prefix, sys.prefix])
    assert str(tmp_path) not in roots
    monkeypatch.setattr(sysconfig, 'get_path', lambda name: str(tmp_path))
    with pytest.raises(RuntimeError, match='fingerprinted installation'):
        build_audit_native.runtime_roots([sys.base_prefix, sys.prefix])


def test_bootstrap_helpers_execute_fingerprinted_source_without_ambient_bytecode(tmp_path):
    source = tmp_path / 'helper.py'
    source.write_text("VALUE = 'old'\n")
    before = source.stat()
    py_compile.compile(str(source), doraise=True)
    source.write_text("VALUE = 'new'\n")
    os.utime(source, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert build_audit_native.load('helper', source).VALUE == 'new'


def test_native_runtime_does_not_exempt_unfingerprinted_ambient_bytecode(tmp_path):
    from atelier.build_audit_worker import Observer
    runtime = tmp_path / 'runtime'
    bytecode = runtime / '__pycache__/helper.pyc'
    spec = {'host': 'Blender', 'inputs': [], 'outputs': [], 'runtime': [runtime],
            'scratch': tmp_path / 'scratch'}
    observer = Observer(spec)
    assert observer.covered(runtime / 'helper.py')
    assert not observer.covered(bytecode)
    observer.inputs.append((bytecode, False))
    assert observer.covered(bytecode)


def test_unreal_audit_tool_identity_hashes_recognized_runtime_without_native_cache(tmp_path, monkeypatch):
    root = tmp_path / 'engine'
    runtime = root / 'Engine/Binaries/ThirdParty/Python3/Mac'
    library = runtime / 'lib/python3.11/runtime.py'
    library.parent.mkdir(parents=True)
    library.write_text('first')
    binary, version = root / 'editor', root / 'Engine/Build/Build.version'
    version.parent.mkdir()
    binary.write_text('editor')
    version.write_text('{}')
    monkeypatch.setattr(engine, 'unreal_root', lambda: root)
    monkeypatch.setattr(engine, 'unreal_cmd', lambda: binary)
    step = build.Step('native', [build.UnrealScript(tmp_path / 'script.py', 'DONE')], audit=True)
    hasher = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
    first = build_audit.tool_context(step, hasher, cache={})
    library.write_text('second')
    assert build_audit.tool_context(step, hasher, cache={}) != first
    assert first['host'] == 'UnrealScript'


def test_complete_report_without_pipe_closure_is_not_a_completed_read():
    read_fd, write_fd = os.pipe()
    receiver = build_audit.Receiver(read_fd, 'fresh')
    payload = ({'kind': 'start', 'nonce': 'fresh'},
               {'kind': 'complete', 'nonce': 'fresh', 'success': True})
    os.write(write_fd, ''.join(json.dumps(r) + '\n' for r in payload).encode())
    receiver.thread.start()
    try:
        report = receiver.finish(SimpleNamespace(name='fixture'))
        assert not report['complete'] and not report['passed']
        assert report['error'] == 'audit pipe did not close'
    finally:
        os.close(write_fd)
        os.close(read_fd)
