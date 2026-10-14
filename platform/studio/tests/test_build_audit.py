"""Real, small Python children; no native tools, shared cache or render admission."""
import json
import os
from pathlib import Path
import subprocess
import threading
from types import SimpleNamespace

import pytest

from atelier import build, build_audit, build_cache, build_products
from atelier.build import Call, Product, Python, Step


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
