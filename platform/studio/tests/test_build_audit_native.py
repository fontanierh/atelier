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

from atelier import build, build_audit, build_batches, build_cache, build_inputs, build_plan, build_products, engine
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


@pytest.mark.parametrize('kind', ['undeclared', 'declared-stale', 'originless', 'namespace',
                                  'package-path', 'untrusted-bytecode'])
def test_preloaded_non_tool_module_cannot_supply_unobserved_inputs(native_action, kind):
    a = native_action
    hidden = a.root / 'host-startup-secret.py'
    hidden.write_text("VALUE = 'current source'\n")
    if kind == 'declared-stale':
        a.step.inputs.append(hidden)
    preload = f'''import sys, types
from importlib.machinery import ModuleSpec
cached = types.ModuleType('preloaded_project_helper')
cached.VALUE = 'stale value from before bootstrap'
'''
    if kind in ('undeclared', 'declared-stale'):
        preload += f'cached.__file__ = {str(hidden)!r}\n'
        if kind == 'undeclared':
            preload += 'cached.VALUE = open(cached.__file__).read()\n'
    elif kind == 'namespace':
        preload += f'''cached.__spec__ = ModuleSpec(cached.__name__, None, is_package=True)
cached.__spec__.submodule_search_locations = [{str(a.root)!r}]
'''
    elif kind in ('package-path', 'untrusted-bytecode'):
        preload += f'cached.__file__ = {str(Path(sysconfig.get_path("stdlib")) / "os.py")!r}\n'
        if kind == 'package-path':
            preload += f'cached.__path__ = [{str(a.root)!r}]\n'
        else:
            preload += f'cached.__cached__ = {str(a.root / "stale.pyc")!r}\n'
    preload += 'sys.modules[cached.__name__] = cached\n'
    first, rest = a.executable.read_text().split('\n', 1)
    a.executable.write_text(first + '\n' + preload + rest)
    a.code("import importlib\nhelper = importlib.import_module('preloaded_project_helper')\n"
           "output.write_text(helper.VALUE)")
    assert a.run() == 1, a.messages
    assert not a.report()['complete'] and not a.report()['passed']
    assert not (a.ctx.stamps / 'generate.json').exists()
    assert not a.output.exists()


def test_preloaded_host_api_and_fingerprinted_runtime_remain_usable(native_action, monkeypatch):
    a = native_action
    runtime = a.root / 'managed-tool'
    runtime.mkdir()
    source = runtime / 'managed_helper.py'
    source.write_text('first')
    approved = build_audit.installation(a.step.commands[0])
    monkeypatch.setattr(build_audit, 'installation', lambda command: [*approved, runtime])
    monkeypatch.setattr(build_audit, 'tool_context', lambda step, hasher, **kwargs:
                        {'managed': build_inputs.inventory(runtime, hasher=hasher, complete=True)})
    host_module = 'bpy' if isinstance(a.step.commands[0], build.Blender) else 'unreal'
    first, rest = a.executable.read_text().split('\n', 1)
    a.executable.write_text(first + '\n' + f'''import sys, types
managed = types.ModuleType('managed_helper')
managed.__file__ = {str(source)!r}
managed.VALUE = open(managed.__file__).read()
sys.modules[managed.__name__] = managed
native_api = types.ModuleType({host_module!r})
native_api.VALUE = 'host API'
sys.modules[native_api.__name__] = native_api
''' + rest)
    a.code(f"import importlib\nhelper = importlib.import_module('managed_helper')\n"
           f"api = importlib.import_module({host_module!r})\noutput.write_text(helper.VALUE + '/' + api.VALUE)")
    assert a.run() == 0, a.messages
    assert a.output.read_text() == 'first/host API' and a.report()['passed']
    before = a.stamp()['fingerprint']
    source.write_text('second')
    assert a.run() == 0, a.messages
    assert a.output.read_text() == 'second/host API'
    assert a.stamp()['fingerprint'] != before and len(a.calls) == 2


def test_preload_gate_rechecks_modules_loaded_by_framework_initialization(native_action):
    a = native_action
    hidden = a.root / 'framework-startup-helper.py'
    hidden.write_text('unobserved')
    a.executable.write_text(f'''#!{sys.executable}
import runpy, sys, types
bootstrap = next((arg.split('=', 1)[1] for arg in sys.argv if arg.startswith('-script=')), None)
if bootstrap is None:
    bootstrap = sys.argv[sys.argv.index('--python') + 1]
namespace = runpy.run_path(bootstrap, run_name='fake_framework')
sys.modules['__main__'].__file__ = bootstrap
original = namespace['load']
def load(name, path):
    worker = original(name, path)
    if name == 'atelier_native_audit_worker':
        module = types.ModuleType('preloaded_late_helper')
        module.__file__ = {str(hidden)!r}
        module.VALUE = open(module.__file__).read()
        sys.modules[module.__name__] = module
    return worker
namespace['main'].__globals__['load'] = load
namespace['main']()
''')
    a.code("import importlib\nhelper = importlib.import_module('preloaded_late_helper')\n"
           "output.write_text(helper.VALUE)")
    assert a.run() == 1, a.messages
    assert not a.report()['complete'] and not a.report()['passed']
    assert not (a.ctx.stamps / 'generate.json').exists()
    assert not a.output.exists()


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
sys.modules['__main__'].__file__ = bootstrap
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
    version.write_text(json.dumps({'MajorVersion': 5, 'MinorVersion': 8, 'PatchVersion': 2}))
    plugin = root / 'Engine/Plugins/Experimental/PythonScriptPlugin'
    wrapper = plugin / 'Content/Python/unreal_core.py'
    wrapper.parent.mkdir(parents=True)
    wrapper.write_text('from _unreal_core import *\n')
    bytecode = wrapper.parent / '__pycache__/unreal_core.pyc'
    bytecode.parent.mkdir()
    bytecode.write_bytes(b'bytecode')
    binaries = plugin / 'Binaries/Mac'
    binaries.mkdir(parents=True)
    native = [binaries / name for name in ('libUnrealEditor-PythonScriptPlugin.dylib',
              'libUnrealEditor-PythonScriptPluginPreload.dylib', 'UnrealEditor.modules')]
    for file in native:
        file.write_bytes(b'native')
    monkeypatch.setattr(engine, 'unreal_root', lambda: root)
    monkeypatch.setattr(engine, 'unreal_cmd', lambda: binary)
    step = build.Step('native', [build.UnrealScript(tmp_path / 'script.py', 'DONE')], audit=True)
    hasher = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
    first = build_audit.tool_context(step, hasher, cache={})
    assert first['host'] == 'UnrealScript'
    assert build_audit.installation(step.commands[0]) == [runtime, wrapper.parent]
    for file in (library, wrapper, bytecode, *native):
        before = build_audit.tool_context(step, hasher, cache={})
        file.write_bytes(file.read_bytes() + b'changed')
        assert build_audit.tool_context(step, hasher, cache={}) != before, file.name
    native[0].unlink()
    with pytest.raises(FileNotFoundError):
        build_audit.tool_context(step, hasher, cache={})


@pytest.mark.parametrize('major,minor', [(5, 7), (5, 9), (6, 0)])
def test_unreal_source_verified_tool_adapter_refuses_other_engine_versions(tmp_path, monkeypatch, major, minor):
    version = tmp_path / 'Engine/Build/Build.version'
    version.parent.mkdir(parents=True)
    version.write_text(json.dumps({'MajorVersion': major, 'MinorVersion': minor}))
    monkeypatch.setattr(engine, 'unreal_root', lambda: tmp_path)
    with pytest.raises(ValueError, match='verified only for UE 5.8'):
        build_audit.installation(build.UnrealScript(tmp_path / 'script.py', 'DONE'))


@pytest.mark.parametrize('native_action', ['UnrealScript'], indirect=True)
def test_unreal_tool_wrapper_tree_and_exact_native_bindings_work_in_fake_host(native_action, monkeypatch):
    a = native_action
    wrappers = a.root / 'engine/Engine/Plugins/Experimental/PythonScriptPlugin/Content/Python'
    wrappers.mkdir(parents=True)
    core = wrappers / 'unreal_core.py'
    core.write_text("from _unreal_core import *\nVALUE = 'first'\n")
    helper = wrappers / 'tool_helper.py'
    helper.write_text("VALUE = 'action-time wrapper read'\n")
    approved = build_audit.installation(a.step.commands[0])
    monkeypatch.setattr(build_audit, 'installation', lambda command: [*approved, wrappers])
    # The stand-in executes with this test's managed interpreter. The production tool-context
    # test above independently exercises the actual UE layout, binary and wrapper identities.
    monkeypatch.setattr(build_audit, 'tool_context', lambda step, hasher, **kwargs:
                        {'wrappers': build_inputs.inventory(wrappers, hasher=hasher, complete=True)})
    first, rest = a.executable.read_text().split('\n', 1)
    # UE RunFile executes in copied globals, while its real __main__ module has no __file__.
    rest = rest.replace("namespace = runpy.run_path(bootstrap, run_name='__main__')", '''
del sys.modules['__main__'].__file__
sys.modules['__main__'].STARTUP_VALUE = 'must not leak into the action main module'
namespace = {'__name__': '__main__', '__file__': bootstrap}
exec(compile(open(bootstrap, 'rb').read(), bootstrap, 'exec'), namespace)
''')
    a.executable.write_text(first + '\n' + f'''import sys, types
for suffix in ('core', 'slate', 'engine', 'editor'):
    binding = types.ModuleType('_unreal_' + suffix)
    binding.VALUE = suffix
    sys.modules[binding.__name__] = binding
sys.path.insert(0, {str(wrappers)!r})
import unreal_core
unreal = types.ModuleType('unreal')
unreal.VALUE = unreal_core.VALUE
sys.modules['unreal'] = unreal
''' + rest)
    a.code("import unreal, unreal_core, _unreal_core, _unreal_slate, _unreal_engine, _unreal_editor\n"
           "import __main__\nassert __main__.__file__ == __file__\nassert not hasattr(__main__, 'STARTUP_VALUE')\n"
           "import importlib\nhelper = importlib.import_module('tool_helper')\n"
           "output.write_text(unreal.VALUE + '/' + helper.VALUE)\n")
    assert a.run() == 0, a.messages
    assert a.output.read_text() == 'first/action-time wrapper read' and a.report()['passed']
    assert any(r['path'].endswith('tool_helper.py') for r in a.report()['accesses'])
    before = a.stamp()['fingerprint']
    core.write_text("from _unreal_core import *\nVALUE = 'second'\n")
    assert a.run() == 0, a.messages
    assert a.output.read_text() == 'second/action-time wrapper read'
    assert a.stamp()['fingerprint'] != before and len(a.calls) == 2


@pytest.mark.parametrize('native_action', ['UnrealScript'], indirect=True)
@pytest.mark.parametrize('kind', ['unknown-dynamic', 'project-wrapper', 'known-binding-project-origin',
                                  'known-binding-project-spec'])
def test_unreal_adapter_does_not_grant_project_or_dynamic_binding_exemptions(native_action, kind):
    a = native_action
    project = a.root / 'engine/Engine/Plugins/UnknownProject/Content/Python/unreal_project.py'
    project.parent.mkdir(parents=True)
    project.write_text('unobserved project input')
    name = '_unreal_core' if kind.startswith('known-binding') else '_unreal_unknown_project'
    origin = '' if kind == 'unknown-dynamic' else f'module.__file__ = {str(project)!r}\n'
    if kind == 'known-binding-project-spec':
        origin = f"module.__spec__ = ModuleSpec(module.__name__, None, origin={str(project)!r})\n"
    first, rest = a.executable.read_text().split('\n', 1)
    a.executable.write_text(first + '\n' + f'''import sys, types
from importlib.machinery import ModuleSpec
module = types.ModuleType({name!r})
module.VALUE = 'project state'
{origin}sys.modules[module.__name__] = module
''' + rest)
    a.code(f"import importlib\nhelper = importlib.import_module({name!r})\noutput.write_text(helper.VALUE)")
    assert a.run() == 1
    assert not a.report()['complete'] and not a.report()['passed']
    assert not (a.ctx.stamps / 'generate.json').exists()


def test_blender_audit_identity_includes_preloaded_ambient_tool_bytecode(tmp_path, monkeypatch):
    bundle = tmp_path / 'Host.app/Contents'
    binary = bundle / 'MacOS/host'
    binary.parent.mkdir(parents=True)
    binary.write_text('host')
    bytecode = bundle / 'Resources/python/__pycache__/runtime.pyc'
    bytecode.parent.mkdir(parents=True)
    bytecode.write_bytes(b'first')
    monkeypatch.setattr(engine, 'blender', lambda: str(binary))
    step = build.Step('native', [build.Blender(tmp_path / 'script.py', factory_startup=True)], audit=True)
    hasher = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
    cache = {}
    first = build_audit.tool_context(step, hasher, cache=cache)
    bytecode.write_bytes(b'second')
    assert build_audit.tool_context(step, hasher, cache=cache) != first


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
