"""Real, small Python children; no native tools, shared cache or render admission."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
from types import SimpleNamespace

import pytest

from atelier import build, build_audit, build_cache, build_products
from atelier.build import Call, Product, Python, Step


@pytest.fixture(autouse=True)
def independent_virtual_checkout(tmp_path, monkeypatch):
    # These tests inject a synthetic recipe/Context. The real source checkout now
    # has managed install metadata; it is not the virtual producer under test.
    from atelier.build_v2 import legacy_entry
    monkeypatch.setattr(legacy_entry, '_checkout', lambda: tmp_path)


@pytest.fixture
def action(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    source = root / 'source.txt'
    source.write_text('input')
    script = root / 'generate.py'
    output = root / 'build/result.txt'
    ctx = SimpleNamespace(game='fixture', out=output.parent, logs=output.parent / 'logs',
                          stamps=output.parent / 'stamps', env=lambda extra=(): dict(os.environ) | dict(extra))
    step = Step('generate', [Python(script, (source, output))], inputs=[source],
                products=[Product('result', (output,))], audit=True, cache=True)
    steps = [step]
    store = build_cache.Store(root / 'store')
    monkeypatch.setattr(build, 'Context', lambda *args, **kwargs: ctx)
    monkeypatch.setattr(build, 'load_recipe', lambda game: SimpleNamespace(steps=lambda ctx: steps))
    monkeypatch.setattr(build_cache, 'Store', lambda: store)
    monkeypatch.setattr(build_cache, 'tool_context', lambda *args, **kwargs: {'test': 'fixed interpreter'})
    messages = []

    def code(body):
        script.write_text('from pathlib import Path\nimport sys\nsource, output = map(Path, sys.argv[1:])\n' + body + '\n')

    return SimpleNamespace(root=root, source=source, script=script, output=output, ctx=ctx,
                           step=step, steps=steps, store=store, code=code, messages=messages,
                           run=lambda **kw: build.build('fixture', echo=messages.append, **kw),
                           report=lambda: json.loads((ctx.logs / 'generate.audit.json').read_text()),
                           stamp=lambda: json.loads((ctx.stamps / 'generate.json').read_text()))


def test_kernel_entropy_and_discard_devices_are_not_recipe_inputs(action):
    """A temporary-file name and a discarded write reach kernel devices; neither is a file the
    recipe read. Reading an undeclared regular file is still refused in the same action."""
    a = action
    a.code('''import os, tempfile
with tempfile.NamedTemporaryFile(mode='w', delete=False) as stream:
    stream.write(source.read_text())
with open('/dev/null', 'w') as discard:
    discard.write('ignored')
os.replace(stream.name, output)
''')
    assert a.run() == 0, a.messages
    report = a.report()
    assert report['passed'] and report['violations'] == []
    # macOS reaches entropy through getentropy, so only Linux records the read.
    for access in report['accesses']:
        if access['path'] in ('<external>/urandom', '<external>/null'):
            assert access['violation'] is None


def test_declared_reads_atomic_write_noop_and_cache_restore(action):
    a = action
    a.code('''import os, tempfile
with tempfile.NamedTemporaryFile(mode='w', delete=False) as stream:
    stream.write(source.read_text())
os.replace(stream.name, output)
assert output.read_text() == 'input'
''')
    assert a.run() == 0, a.messages
    assert a.output.read_text() == 'input'
    report = a.report()
    assert report['complete'] and report['passed'] and report['violations'] == []
    assert any(r['operation'] == 'read' and r['path'].endswith('source.txt') for r in report['accesses'])
    assert 'restored_from' not in a.stamp()
    before = (a.ctx.logs / 'generate.audit.json').read_bytes()
    assert a.run() == 0
    assert (a.ctx.logs / 'generate.audit.json').read_bytes() == before
    a.output.unlink()
    assert a.run() == 0
    assert a.stamp()['restored_from'] == a.stamp()['fingerprint']
    assert a.output.read_text() == 'input'
    assert (a.ctx.logs / 'generate.audit.json').read_bytes() == before


def test_numpy_initialization_and_array_output_are_observed(action):
    a = action
    a.code('''import numpy as np
values = np.arange(6, dtype=np.int64).reshape(2, 3)
with output.open('wb') as stream:
    np.save(stream, values * values)
''')
    assert a.run() == 0, a.messages
    import numpy as np
    np.testing.assert_array_equal(np.load(a.output), [[0, 1, 4], [9, 16, 25]])
    report = a.report()
    assert report['complete'] and report['passed'] and report['violations'] == []
    assert any(r['operation'] == 'read' and 'numpy' in r['path'] for r in report['accesses'])
    assert any(r['operation'] == 'write' and r['path'].endswith('/result.txt') for r in report['accesses'])


@pytest.mark.parametrize('operation,event', [
    ('ctypes.CDLL(None)', 'ctypes.dlopen'),
    ('ctypes.PyDLL(None)', 'ctypes.dlopen'),
    ('ctypes.pythonapi.Py_GetVersion', 'ctypes.dlsym'),
])
def test_action_ctypes_operations_remain_sticky_failures(action, operation, event):
    a = action
    a.code(f'''import ctypes
try:
    {operation}
except PermissionError:
    pass
output.write_text('otherwise successful')
''')
    assert a.run() == 1
    report = a.report()
    assert not report['passed']
    assert any(r['operation'] == event for r in report['violations'])
    assert not (a.ctx.stamps / 'generate.json').exists()
    assert not list((a.store.root / 'actions').glob('*.json'))


@pytest.mark.parametrize('operation', [
    "hidden.read_text()",
    "__import__('io').open(hidden).read()",
    "__import__('os').open(hidden, __import__('os').O_RDONLY)",
    "hidden.exists()",
    "list(hidden.parent.iterdir())",
    "list(hidden.parent.glob('*.txt'))",
    "__import__('glob').glob(str(hidden.parent / '*.txt'))",
    "hidden.write_text('overwrite')",
    "hidden.unlink()",
    "hidden.rename(output)",
], ids=['pathlib', 'io', 'os-open', 'metadata', 'listdir', 'pathlib-glob', 'glob', 'write', 'delete', 'rename'])
def test_undeclared_access_cannot_be_caught_and_certified(action, operation):
    a = action
    hidden = a.root / 'hidden.txt'
    hidden.write_text('secret input')
    a.code(f'''hidden = Path({str(hidden)!r})
try:
    {operation}
except PermissionError:
    pass
output.write_text('otherwise successful')
''')
    assert a.run() == 1
    assert not (a.ctx.stamps / 'generate.json').exists()
    assert a.report()['violations'] and not a.report()['passed']
    assert hidden.read_text() == 'secret input'
    assert not list((a.store.root / 'actions').glob('*.json'))


def test_declared_directory_membership_includes_markdown(action):
    a = action
    folder = a.root / 'data'
    folder.mkdir()
    (folder / 'a.txt').write_text('a')
    a.step.inputs = [folder]
    a.step.commands[0].args = (folder, a.output)
    a.code("output.write_text(','.join(sorted(p.name for p in source.iterdir())))")
    assert a.run() == 0, a.messages
    key = a.stamp()['fingerprint']
    (folder / 'new.md').write_text('membership matters')
    assert a.run() == 0, a.messages
    assert a.stamp()['fingerprint'] != key
    assert a.output.read_text() == 'a.txt,new.md'


def test_dynamic_helper_must_be_declared_and_ignores_ambient_bytecode(action):
    a = action
    helper = a.root / 'helper.py'
    helper.write_text("VALUE = 'from helper'\n")
    # A dynamic import evades the static import closure, but the actual file read is observed.
    a.code("import importlib\noutput.write_text(importlib.import_module('helper').VALUE)")
    assert a.run() == 1
    assert any('helper' in str(r['path']) for r in a.report()['violations'])
    a.step.inputs.append(helper)
    assert a.run() == 0, a.messages
    assert a.output.read_text() == 'from helper'
    assert not (a.root / '__pycache__').exists()
    helper.write_text("VALUE = 'changed helper'\n")
    assert a.run() == 0, a.messages
    assert a.output.read_text() == 'changed helper'


@pytest.mark.parametrize('reference', [False, True], ids=['read', 'reference'])
def test_only_read_edges_grant_product_access(action, reference):
    a = action
    dependency = a.ctx.out / 'dependency.txt'
    a.steps.insert(0, Step('dependency', [Call('write', lambda ctx, log: dependency.write_text('dep'))],
                          products=[Product('dependency', (dependency,))]))
    setattr(a.step, 'references' if reference else 'reads', ['dependency'])
    a.code(f"output.write_text(Path({str(dependency)!r}).read_text())")
    assert a.run() == (1 if reference else 0), a.messages
    assert bool(a.report()['violations']) == reference


@pytest.mark.parametrize('operation', [
    "__import__('os')._exit(0)",
    "raise RuntimeError('action failed')",
    "(output.parent / 'logs/generate.audit.json').write_text('{}')",
    "__import__('subprocess').run([sys.executable, '-c', 'pass'])",
    "__import__('os').open('source.txt', __import__('os').O_RDONLY, dir_fd=1234)",
], ids=['early-exit', 'exception', 'report-write', 'subprocess', 'dir-fd'])
def test_missing_failed_or_escaped_audit_never_certifies(action, operation):
    a = action
    a.code(f"output.write_text('written')\n{operation}")
    assert a.run() == 1
    assert not (a.ctx.stamps / 'generate.json').exists()
    assert not a.report()['passed']
    assert not list((a.store.root / 'actions').glob('*.json'))


@pytest.mark.parametrize('body', ["output.write_text(output.read_text())", "pass"], ids=['stale-read', 'unwritten'])
def test_previous_output_cannot_supply_unkeyed_bytes(action, body):
    a = action
    a.output.parent.mkdir()
    a.output.write_text('old output')
    a.code(body)
    assert a.run() == 1
    assert not (a.ctx.stamps / 'generate.json').exists()


def test_guarded_python_retains_normal_admission_and_report_descriptor(action, monkeypatch):
    a = action
    a.step.heavy = True
    a.code('output.write_text(source.read_text())')
    calls = []
    callback = lambda pid: None
    a.step.commands[0].on_poll = callback

    def guard(argv, folder, **kwargs):
        calls.append(kwargs)
        folder.mkdir()
        with (folder / 'stdout.log').open('w') as log:
            return subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT, env=kwargs['env'],
                                  pass_fds=kwargs['pass_fds'], stdin=subprocess.DEVNULL).returncode

    monkeypatch.setattr(build.guarded, 'run', guard)
    assert a.run() == 0, a.messages
    assert len(calls) == 1 and calls[0]['pass_fds']
    assert calls[0]['kind'] == 'job' and 'lock' not in calls[0]
    assert calls[0]['on_poll'] is callback and a.report()['passed']


def test_audit_configuration_is_rejected_before_any_action(action):
    a = action
    a.step.commands.append(Python(a.script))
    with pytest.raises(ValueError, match='exactly one Python'):
        build_products.Graph(a.steps)
    assert not a.ctx.out.exists()


def test_script_is_an_input_even_when_not_explicitly_listed(action):
    a = action
    a.step.products = [Product('bad', (a.script,))]
    with pytest.raises(ValueError, match='input overlaps'):
        build_products.Graph(a.steps)


@pytest.mark.parametrize('audit', [False, True], ids=['cache-only', 'audited'])
@pytest.mark.parametrize('declaration', ['outputs', 'pool_roots'])
@pytest.mark.parametrize('relation', ['ancestor', 'equal', 'descendant'])
def test_products_cannot_erase_legacy_outputs(action, audit, declaration, relation):
    a = action
    a.step.audit = audit
    shared = a.ctx.out / 'shared'
    shared.mkdir(parents=True)
    existing = shared / 'legacy.txt'
    existing.write_text('legacy bytes')
    product, legacy = {'ancestor': (shared, existing), 'equal': (existing, existing),
                       'descendant': (existing, shared)}[relation]
    a.step.products = [Product('result', (product,))]
    a.steps.insert(0, Step('legacy', [], **{declaration: [legacy]}))
    a.step.after = ['legacy']
    a.code("output.write_text('changed')")
    with pytest.raises(SystemExit, match='overlaps legacy outputs'):
        a.run()
    assert existing.read_text() == 'legacy bytes'
    assert not a.ctx.stamps.exists()


def test_symlink_cannot_redirect_owned_write_to_source(action):
    a = action
    a.output.parent.mkdir()
    a.output.symlink_to(a.source)
    a.code("output.write_text('changed')")
    with pytest.raises(SystemExit, match='input overlaps'):
        a.run()
    assert a.source.read_text() == 'input'


def test_previous_outputs_are_empty_before_metadata_or_append(action):
    a = action
    a.output.parent.mkdir()
    a.output.write_text('old')
    a.code('''size = output.stat().st_size if output.exists() else 0
with output.open('a') as stream:
    stream.write(str(size))
''')
    assert a.run() == 0, a.messages
    assert a.output.read_text() == '0'


def test_previous_hardlinked_output_cannot_damage_source(action):
    a = action
    a.output.parent.mkdir()
    os.link(a.source, a.output)
    a.code("output.write_text('changed')")
    assert a.run() == 0, a.messages
    assert a.output.read_text() == 'changed'
    assert a.source.read_text() == 'input'
    assert a.source.stat().st_ino != a.output.stat().st_ino


@pytest.mark.parametrize('added', [False, True], ids=['startup-path', 'added-path'])
def test_resolver_only_query_cannot_observe_undeclared_module(action, added):
    a = action
    folder = a.root / 'hidden' if added else a.root
    folder.mkdir(exist_ok=True)
    (folder / 'secretmod.py').write_text('VALUE = 1\n')
    a.code(f'''import importlib.util
sys.path.insert(0, {str(folder)!r})
output.write_text(str(importlib.util.find_spec('secretmod') is not None))
''')
    assert a.run() == 1
    assert any(r['operation'] == 'module lookup' for r in a.report()['violations'])


def test_import_finder_filename_cannot_spoof_a_real_import(action):
    a = action
    a.code('''namespace = {}
exec(compile('def _fill_cache(path):\\n    import os\\n    return os.listdir(path)',
             '<frozen importlib._bootstrap_external>', 'exec'), namespace)
output.write_text(str(namespace['_fill_cache'](source.parent)))
''')
    assert a.run() == 1
    assert any(r['operation'] == 'list' for r in a.report()['violations'])


@pytest.mark.parametrize('query', ["finder.find_spec('absent_secret')", 'finder._fill_cache()'],
                         ids=['file-finder', 'fill-cache'])
def test_direct_file_finder_cannot_certify_undeclared_directory_membership(action, query):
    a = action
    a.code(f'''from importlib.machinery import FileFinder, SourceFileLoader
finder = FileFinder(str(source.parent), (SourceFileLoader, ['.py']))
try:
    {query}
except PermissionError:
    pass
output.write_text('otherwise successful')
''')
    assert a.run() == 1
    assert not a.report()['passed'] and a.report()['violations']
    assert not (a.ctx.stamps / 'generate.json').exists()
    assert not list((a.store.root / 'actions').glob('*.json'))


def test_imported_module_cannot_reuse_an_outer_imports_directory_exemption(action):
    a = action
    helper = a.root / 'helper.py'
    helper.write_text('''from importlib.machinery import PathFinder
from pathlib import Path
FOUND = PathFinder._get_spec('absent_secret', [str(Path(__file__).parent)], None)
''')
    a.step.inputs.append(helper)
    a.code("import helper\noutput.write_text(str(helper.FOUND is not None))")
    assert a.run() == 1
    assert any(r['operation'] == 'module lookup' for r in a.report()['violations'])
    assert not (a.ctx.stamps / 'generate.json').exists()


@pytest.mark.parametrize('declared', [False, True])
def test_extension_module_bytes_require_an_input_or_tool_runtime(action, declared):
    from websockets import speedups
    a = action
    library = a.root / Path(speedups.__file__).name
    shutil.copyfile(speedups.__file__, library)
    if declared:
        a.step.inputs.append(library)
    a.code(f'''import importlib.util
spec = importlib.util.spec_from_file_location('speedups', {str(library)!r})
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
output.write_text(repr(module.apply_mask(b'1234', b'abcd')))
''')
    assert a.run() == (0 if declared else 1), a.messages
    assert a.report()['passed'] == declared
    if declared:
        assert a.output.read_text() == "b'PPPP'"
    else:
        assert any(r['path'].endswith(library.name) for r in a.report()['violations'])
        assert not (a.ctx.stamps / 'generate.json').exists()
        assert not list((a.store.root / 'actions').glob('*.json'))


@pytest.mark.parametrize('declared', [False, True])
def test_namespace_package_requires_an_inventoried_directory(action, declared):
    a = action
    package = a.root / 'namespace_package'
    package.mkdir()
    (package / 'data.txt').write_text('member')
    if declared:
        a.step.inputs.append(package)
    a.code("import importlib\nimportlib.import_module('namespace_package')\noutput.write_text('namespace imported')")
    assert a.run() == (0 if declared else 1), a.messages
    assert bool(a.report()['violations']) != declared


@pytest.mark.parametrize('operation', [
    "__import__('sqlite3').connect(source)",
    "__import__('ctypes').CDLL(None)",
    "__import__('os').chown(source, -1, -1)",
    "__import__('os').kill(__import__('os').getpid(), 0)",
], ids=['sqlite', 'ctypes', 'chown', 'signal'])
def test_unhandled_native_operations_are_refused(action, operation):
    a = action
    a.code(f"{operation}\noutput.write_text('otherwise successful')")
    assert a.run() == 1
    assert a.report()['violations'] and not a.report()['passed']
    assert a.source.read_text() == 'input'


@pytest.mark.parametrize('cache', [False, True])
def test_standard_library_and_declared_metadata_keep_normal_semantics(action, cache):
    a = action
    a.step.cache = cache
    a.code('''import os, hashlib
assert source.exists() and source.is_file() and os.access(source, os.R_OK)
assert source.stat().st_size == 5
output.write_text(hashlib.sha256(source.read_bytes()).hexdigest())
''')
    assert a.run() == 0, a.messages
    assert a.report()['passed']


@pytest.mark.parametrize('declared', [False, True])
def test_pillow_file_reads_are_observed(action, declared):
    from PIL import Image
    a = action
    source = a.root / 'source.png'
    Image.new('RGB', (1, 1), (10, 20, 30)).save(source)
    a.step.inputs = [source] if declared else []
    a.step.commands[0].args = (source, a.output)
    a.code('''from PIL import Image
with Image.open(source) as image:
    output.write_text(str(image.getpixel((0, 0))))
''')
    assert a.run() == (0 if declared else 1), a.messages
    if declared:
        assert a.output.read_text() == '(10, 20, 30)'
    else:
        assert any(r['path'].endswith('source.png') for r in a.report()['violations'])


def test_numpy_undeclared_file_read_is_observed(action):
    import numpy as np
    a = action
    source = a.root / 'source.npy'
    np.save(source, np.array([1, 2, 3]))
    a.step.inputs = []
    a.step.commands[0].args = (source, a.output)
    a.code('import numpy as np\noutput.write_text(str(np.load(source).sum()))')
    assert a.run() == 1
    assert any(r['path'] and r['path'].endswith('source.npy') for r in a.report()['violations'])


@pytest.mark.parametrize('problem', ['wrong-nonce', 'truncated', 'extra-after-complete', 'missing-field', 'oversized'])
def test_bad_receipt_is_rejected_and_pipe_is_drained(problem):
    read_fd, write_fd = os.pipe()
    receiver = build_audit.Receiver(read_fd, 'test-nonce')
    records = [{'kind': 'start', 'nonce': 'test-nonce'},
               {'kind': 'complete', 'nonce': 'test-nonce', 'success': True}]
    if problem == 'wrong-nonce':
        records[1]['nonce'] = 'old-nonce'
    elif problem == 'extra-after-complete':
        records.append(records[1])
    elif problem == 'missing-field':
        records.insert(1, {'kind': 'access', 'nonce': 'test-nonce', 'operation': 'read', 'path': 'input'})
    payload = ''.join(json.dumps(r) + '\n' for r in records).encode()
    if problem == 'truncated':
        payload = payload[:-2]
    elif problem == 'oversized':
        payload = b'x' * 100_000 + b'\n' + payload

    def write():
        try:
            remaining = payload
            while remaining:
                remaining = remaining[os.write(write_fd, remaining):]
        except OSError:
            pass  # Cleanup may close the reader after a failed timeout assertion.
        finally:
            os.close(write_fd)

    writer = threading.Thread(target=write, daemon=True)
    receiver.thread.start()
    writer.start()
    try:
        writer.join(timeout=2)
        assert not writer.is_alive(), 'malformed report blocked its child on a full pipe'
        report = receiver.finish(SimpleNamespace(name='fixture'))
        assert not report['passed'] and not report['complete']
    finally:
        receiver.stopped.set()
        os.close(read_fd)
        writer.join(timeout=2)
        receiver.thread.join(timeout=2)


def complete_receipt(write_fd):
    for record in ({'kind': 'start', 'nonce': 'test-nonce'},
                   {'kind': 'complete', 'nonce': 'test-nonce', 'success': True}):
        os.write(write_fd, (json.dumps(record) + '\n').encode())


def test_stop_after_a_poll_that_preceded_the_writer_close_still_reads_eof(monkeypatch):
    read_fd, write_fd = os.pipe()
    receiver = build_audit.Receiver(read_fd, 'test-nonce')
    complete_receipt(write_fd)
    polled, resume = threading.Event(), threading.Event()
    real = build_audit.select.select

    def select(readers, writers, errors, timeout):
        ready = real(readers, writers, errors, 0)
        if ready[0] or polled.is_set():
            return ready
        # This poll finds the pipe empty while the host's writer is still open, and its thread
        # resumes only after the host has closed the writer and stopped, as on a loaded runner.
        polled.set()
        resume.wait(5)
        return [], [], []
    monkeypatch.setattr(build_audit.select, 'select', select)
    stop = receiver.stopped.set
    receiver.stopped.set = lambda: (stop(), resume.set())
    receiver.thread.start()
    try:
        assert polled.wait(5)
        os.close(write_fd)
        report = receiver.finish(SimpleNamespace(name='fixture'))
        assert report['error'] is None and report['complete'] and report['passed'], report
    finally:
        resume.set()
        receiver.thread.join(timeout=2)
        os.close(read_fd)


def test_writer_held_by_another_process_is_reported_without_hanging():
    read_fd, write_fd = os.pipe()
    receiver = build_audit.Receiver(read_fd, 'test-nonce')
    complete_receipt(write_fd)
    held = os.dup(write_fd)  # A leaked descendant still owns the writer after the action.
    receiver.thread.start()
    try:
        os.close(write_fd)
        report = receiver.finish(SimpleNamespace(name='fixture'))
        assert report['error'] == 'audit pipe did not close' and not report['passed']
    finally:
        os.close(held)
        receiver.thread.join(timeout=2)
        os.close(read_fd)


def test_read_product_grants_optional_root_presence_and_bytes_but_not_siblings(action):
    a = action
    mode = a.root / 'mode.txt'
    mode.write_text('absent')
    main, sidecar = a.ctx.out / 'inputs/main.json', a.ctx.out / 'inputs/main.sidecar'
    product = Product('bundle', (main,), optional_paths=(sidecar,))
    def produce(ctx, log):
        main.parent.mkdir(parents=True, exist_ok=True)
        main.write_text('main')
        contents = mode.read_text()
        if contents == 'absent':
            sidecar.unlink(missing_ok=True)
        else:
            sidecar.write_text(contents)
    owner = Step('produce', [Call('produce', produce)], inputs=[mode], products=[product])
    a.steps.insert(0, owner)
    a.step.inputs = []
    a.step.reads = ['bundle']
    a.step.commands[0].args = (main, a.output)
    a.code(f"sidecar = Path({str(sidecar)!r})\noutput.write_text(source.read_text() + '/' + (sidecar.read_text() if sidecar.exists() else 'absent'))")
    keys = []
    for contents in ('absent', 'first', 'changed', 'absent'):
        mode.write_text(contents)
        assert a.run() == 0, a.messages
        assert a.output.read_text() == 'main/' + contents
        keys.append(a.stamp()['fingerprint'])
    assert keys[0] == keys[-1] and len(set(keys)) == 3
    sibling = main.parent / 'unowned.txt'
    sibling.write_text('outside the named product')
    a.script.write_text(a.script.read_text() + f'\nPath({str(sibling)!r}).read_text()\n')
    assert a.run() == 1
    assert a.report()['violations'] and not a.report()['passed']
    assert not (a.ctx.stamps / 'generate.json').exists()
