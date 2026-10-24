"""The build-v2 Python job loop runs real tiny jobs over inherited pipes (portable, no isolation claim)."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from atelier.build_v2 import protocol, python_worker

WORKER = Path(python_worker.__file__)
# The only unsandboxed route: a test-only entry that announces a test worker version.
UNSANDBOXED = Path(__file__).resolve().parents[2] / 'build-v2/tests/fixtures/unsandboxed_job_loop.py'

ECHO = '''
def run(context):
    data = context.input('shape').read_bytes()
    scale = context.params['scale']
    context.output('piece.txt').write_bytes(data * scale + str(context.seed).encode())
'''


def stage(root, script=ECHO, inputs=None, code=None, **job):
    """A hand-staged job folder; the Rust staging layer builds the same shape from a PreparedUnit."""
    root.mkdir(parents=True)
    (root / 'output').mkdir()
    files = {'ops/run.py': script, **(code or {})}
    for path, text in files.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(text, encoding='utf-8')
        (root / path).chmod(0o444)
    staged = []
    for name, (path, data) in (inputs if inputs is not None else {'shape': ('in/shape.bin', b'ab')}).items():
        if data is not None:
            (root / path).parent.mkdir(parents=True, exist_ok=True)
            (root / path).write_bytes(data)
            (root / path).chmod(0o444)
        staged.append({'name': name, 'path': path, 'identity': {'state': 'absent'} if data is None
                       else {'state': 'digest', 'digest': '0' * 64}})
    request = {'job_id': 'job-1', 'unit': 'u', 'op': {'kind': 'py', 'version': '1'}, 'job_dir': str(root),
               'script': 'ops/run.py', 'code': sorted(files), 'inputs': staged, 'params': {'scale': 2},
               'outputs': [{'path': 'piece.txt', 'required': True}]}
    request.update(job)
    return request


class Loop:
    """A direct owned worker child over two inherited pipes, as the launcher starts it."""

    def __init__(self, entry=UNSANDBOXED, *flags, log=None):
        request_read, self.request_write = os.pipe()
        self.response_read, response_write = os.pipe()
        self.process = subprocess.Popen(
            [sys.executable, '-I', str(entry), '--request-fd', str(request_read), '--response-fd',
             str(response_write), *flags], pass_fds=(request_read, response_write), stdin=subprocess.DEVNULL,
            stdout=log, stderr=log)
        # A pipe's two ends share one inode: the job must hold neither protocol pipe.
        self.protocol_pipes = {(os.fstat(fd).st_dev, os.fstat(fd).st_ino) for fd in (request_read, response_write)}
        os.close(request_read)
        os.close(response_write)
        self.requests = os.fdopen(self.request_write, 'wb', buffering=0)
        self.responses = os.fdopen(self.response_read, 'rb', buffering=0)
        version = python_worker.WORKER_VERSION if entry == WORKER else python_worker.TEST_WORKER_VERSION
        assert self.read() == {'type': 'hello', 'worker_version': version}

    def send(self, message):
        protocol.write_frame(self.requests, protocol.REQUEST, message)

    def read(self):
        return protocol.read_frame(self.responses, protocol.RESPONSE)

    def run(self, job):
        self.send({'type': 'run', 'job': job})
        assert self.read() == {'type': 'started', 'job_id': job['job_id']}
        return self.read()

    def close(self):
        self.send({'type': 'shutdown'})
        assert self.read() == {'type': 'stopped'}
        assert self.read() is None
        self.requests.close()
        self.responses.close()
        assert self.process.wait(timeout=10) == 0


@pytest.fixture
def loop():
    worker = Loop()
    yield worker
    if worker.process.poll() is None:
        worker.process.kill()
        worker.process.wait()


def failure(response, kind):
    assert response['type'] == 'failed', response
    assert response['failure']['kind'] == kind, response
    return response['failure']['message']


def test_job_runs_and_reports_its_declared_outputs(tmp_path, loop):
    job = stage(tmp_path / 'job')
    assert loop.run(job) == {'type': 'completed', 'job_id': 'job-1', 'outputs': {'files': ['piece.txt']}}
    assert (tmp_path / 'job/output/piece.txt').read_bytes() == b'abab0'
    loop.close()


def test_same_bytes_under_other_job_ids_and_folders(tmp_path, loop):
    script = '''
import os, random, time
def run(context):
    context.output('piece.txt').write_text(repr((hash('salted'), random.random(), time.time(),
                                                 sorted(vars(context.__class__)), context.inputs)))
'''
    first = stage(tmp_path / 'a/job', script=script)
    second = stage(tmp_path / 'elsewhere/deeper/folder', script=script, job_id='other-id')
    assert loop.run(first)['type'] == 'completed'
    assert loop.run(second)['type'] == 'completed'
    produced = [(Path(job['job_dir']) / 'output/piece.txt').read_bytes() for job in (first, second)]
    assert produced[0] == produced[1]
    assert b'job-1' not in produced[0] and b'other-id' not in produced[1]


def test_changing_only_seed_or_params_changes_output(tmp_path, loop):
    script = '''
import random
def run(context):
    context.output('piece.txt').write_text(f'{random.random()} {context.params["scale"]}')
'''
    outputs = []
    for index, params in enumerate(({'scale': 1, 'seed': 1}, {'scale': 1, 'seed': 1}, {'scale': 1, 'seed': 2},
                                    {'scale': 3, 'seed': 1})):
        job = stage(tmp_path / f'job{index}', script=script, params=params)
        assert loop.run(job)['type'] == 'completed'
        outputs.append((tmp_path / f'job{index}/output/piece.txt').read_text())
    assert outputs[0] == outputs[1]
    assert len(set(outputs[1:])) == 3


def test_optional_absent_input_is_none_and_creates_no_file(tmp_path, loop):
    script = '''
def run(context):
    try:
        context.input('extra')
        found = 'present'
    except LookupError:
        found = 'absent'
    context.output('piece.txt').write_text(f'{context.inputs["extra"]} {found}')
'''
    job = stage(tmp_path / 'job', script=script, inputs={'shape': ('shape.bin', b'x'), 'extra': ('extra.bin', None)})
    assert loop.run(job)['type'] == 'completed'
    assert (tmp_path / 'job/output/piece.txt').read_text() == 'None absent'
    assert not (tmp_path / 'job/extra.bin').exists()


def test_staged_presence_must_match_the_declared_identity(tmp_path, loop):
    job = stage(tmp_path / 'job', inputs={'shape': ('shape.bin', None)})
    (tmp_path / 'job/shape.bin').write_bytes(b'stray')
    assert 'staged presence' in failure(loop.run(job), 'protocol')


def test_wall_clock_is_fixed_and_entropy_is_refused(tmp_path, loop):
    clock = '''
import datetime, time
def run(context):
    context.output('piece.txt').write_text(f'{time.time()} {datetime.datetime.now(datetime.timezone.utc).isoformat()}')
'''
    job = stage(tmp_path / 'clock', script=clock)
    assert loop.run(job)['type'] == 'completed'
    assert (tmp_path / 'clock/output/piece.txt').read_text() == '946684800.0 2000-01-01T00:00:00+00:00'
    for index, call in enumerate(('os.urandom(4)', 'uuid.uuid4()', '__import__("secrets")', 'random.SystemRandom()')):
        script = f'import os, random, uuid\ndef run(context):\n    {call}\n'
        assert loop.run(stage(tmp_path / f'entropy{index}', script=script))['failure']['kind'] == 'dependency'


def test_only_declared_code_loads_and_the_checkout_is_not_importable(tmp_path, loop):
    helper = 'def value():\n    return "helper"\n'
    uses_helper = 'import helper\ndef run(context):\n    context.output("piece.txt").write_text(helper.value())\n'
    declared = stage(tmp_path / 'declared', script=uses_helper, code={'ops/helper.py': helper})
    assert loop.run(declared)['type'] == 'completed'
    undeclared = stage(tmp_path / 'undeclared', script=uses_helper)
    (tmp_path / 'undeclared/ops/helper.py').write_text(helper)  # present on disk, not declared
    assert 'declared code closure' in failure(loop.run(undeclared), 'dependency')
    probe = '''
import sys
def run(context):
    try:
        import atelier
        found = 'importable'
    except ImportError:
        found = 'missing'
    context.output('piece.txt').write_text(found + ' ' + str(any('platform/studio' in p for p in sys.path)))
'''
    assert loop.run(stage(tmp_path / 'probe', script=probe))['type'] == 'completed'
    assert (tmp_path / 'probe/output/piece.txt').read_text() == 'missing False'


def test_job_sees_no_protocol_descriptor_and_only_the_declared_environment(tmp_path, loop):
    probe = '''
import json, os, stat
def run(context):
    pipes = []
    for fd in range(3, 256):
        try:
            info = os.fstat(fd)
        except OSError:
            continue
        if stat.S_ISFIFO(info.st_mode):
            pipes.append([info.st_dev, info.st_ino])
    context.output('piece.txt').write_text(json.dumps([pipes, sorted(os.environ)]))
'''
    assert loop.run(stage(tmp_path / 'job', script=probe))['type'] == 'completed'
    pipes, environment = json.loads((tmp_path / 'job/output/piece.txt').read_text())
    assert pipes  # the job's own result pipe
    assert not {tuple(pipe) for pipe in pipes} & loop.protocol_pipes
    assert environment == sorted(python_worker.JOB_ENVIRONMENT)


def test_loop_reports_every_actual_output_and_refuses_links_and_special_files(tmp_path, loop):
    # Membership is the controller's: undeclared files (a group member, say) are reported, not hidden.
    extra = ('def run(context):\n    (context.output_dir / "pieces/a").mkdir(parents=True)\n'
             '    (context.output_dir / "pieces/a/m.glb").write_text("x")\n'
             '    context.output("piece.txt").write_text("x")\n')
    assert loop.run(stage(tmp_path / 'extra', script=extra)) == {
        'type': 'completed', 'job_id': 'job-1', 'outputs': {'files': ['piece.txt', 'pieces/a/m.glb']}}
    missing = 'def run(context):\n    pass\n'
    assert loop.run(stage(tmp_path / 'missing', script=missing)) == {
        'type': 'completed', 'job_id': 'job-1', 'outputs': {'files': []}}
    link = 'import os\ndef run(context):\n    os.symlink("/etc/hosts", context.output("piece.txt"))\n'
    assert 'os.symlink' in failure(loop.run(stage(tmp_path / 'link', script=link)), 'dependency')
    fifo = 'import os\ndef run(context):\n    os.mkfifo(context.output("piece.txt"))\n'
    assert 'regular file' in failure(loop.run(stage(tmp_path / 'fifo', script=fifo)), 'job')
    raises = 'def run(context):\n    raise ValueError("bad mesh")\n'
    assert 'bad mesh' in failure(loop.run(stage(tmp_path / 'raises', script=raises)), 'job')


def test_cancel_stops_the_job_and_the_loop_serves_the_next(tmp_path, loop):
    slow = 'import threading\ndef run(context):\n    threading.Event().wait(60)\n'
    job = stage(tmp_path / 'slow', script=slow)
    loop.send({'type': 'run', 'job': job})
    assert loop.read() == {'type': 'started', 'job_id': 'job-1'}
    loop.send({'type': 'cancel', 'job_id': 'job-1'})
    failure(loop.read(), 'cancelled')
    assert list((tmp_path / 'slow/output').iterdir()) == []
    loop.send({'type': 'cancel', 'job_id': 'job-1'})  # late: no reply
    assert loop.run(stage(tmp_path / 'next', job_id='job-2'))['type'] == 'completed'
    loop.close()


def test_production_entry_has_no_unsandboxed_mode(tmp_path):
    for flags in (['--no-sandbox-portable-test'], ['--sandboxed=false'], ['--unsandboxed']):
        run = subprocess.run([sys.executable, '-I', str(WORKER), '--request-fd', '0', '--response-fd', '1', *flags],
                             stdin=subprocess.DEVNULL, capture_output=True, timeout=20)
        assert run.returncode == 2 and b'unrecognized arguments' in run.stderr
    assert python_worker.TEST_WORKER_VERSION != python_worker.WORKER_VERSION
    # The production entry always builds a sandboxed worker that announces the production version.
    built = []
    original = python_worker.Worker

    class Recording(original):
        def serve(self):
            built.append((self.sandboxed, self.version))

    python_worker.Worker = Recording
    try:
        request_read, request_write = os.pipe()
        response_read, response_write = os.pipe()
        python_worker.main(['--request-fd', str(request_read), '--response-fd', str(response_write)])
    finally:
        python_worker.Worker = original
        for fd in (request_read, request_write, response_read, response_write):
            try:
                os.close(fd)
            except OSError:
                pass
    assert built == [(True, python_worker.WORKER_VERSION)]


def test_sandboxed_worker_fails_jobs_when_no_sandbox_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(python_worker, 'SANDBOX_EXEC', str(tmp_path / 'missing-sandbox'))
    request_read, request_write = os.pipe()
    response_read, response_write = os.pipe()
    with os.fdopen(request_write, 'wb') as requests:
        protocol.write_frame(requests, protocol.REQUEST, {'type': 'run', 'job': stage(tmp_path / 'job')})
        protocol.write_frame(requests, protocol.REQUEST, {'type': 'shutdown'})
    with os.fdopen(request_read, 'rb') as requests, os.fdopen(response_write, 'wb') as responses:
        python_worker.Worker(requests, responses, sandboxed=True).serve()
    with os.fdopen(response_read, 'rb') as responses:
        replies = [protocol.read_frame(responses, protocol.RESPONSE) for _ in range(4)]
    assert replies[1] == {'type': 'started', 'job_id': 'job-1'}
    assert 'no supported job sandbox' in failure(replies[2], 'dependency')
    assert replies[3] == {'type': 'stopped'}
    assert list((tmp_path / 'job/output').iterdir()) == []


def test_undeclared_path_checks_fail_even_when_missing_or_caught(tmp_path, loop):
    missing = str(tmp_path / 'never-created')
    for index, body in enumerate((f'os.path.exists({missing!r})', f'Path({missing!r}).is_file()',
                                  f'os.listdir({missing!r})', 'os.listdir("..")',
                                  f'open({missing!r}, "w")', 'subprocess.run(["true"])')):
        script = ('import os, subprocess\nfrom pathlib import Path\ndef run(context):\n'
                  f'    try:\n        {body}\n    except BaseException:\n        pass\n'
                  '    context.output("piece.txt").write_text("ran")\n')
        job = stage(tmp_path / f'job{index}', script=script)
        assert 'undeclared' in failure(loop.run(job), 'dependency')
        assert list((tmp_path / f'job{index}/output').iterdir()) == []
    assert not os.path.exists(missing)


def test_ctypes_imports_but_named_native_libraries_and_sockets_are_refused(tmp_path, loop):
    imports = 'import ctypes\ndef run(context):\n    context.output("piece.txt").write_text("ok")\n'
    assert loop.run(stage(tmp_path / 'imports', script=imports))['type'] == 'completed'
    for index, body in enumerate(('ctypes.CDLL("libc.dylib")', 'socket.socketpair()',
                                  'socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(b"x", ("127.0.0.1", 9))')):
        script = f'import ctypes, socket\ndef run(context):\n    {body}\n'
        assert 'undeclared' in failure(loop.run(stage(tmp_path / f'job{index}', script=script)), 'dependency')


def test_descriptor_relative_access_is_checked_against_the_real_directory(tmp_path, loop):
    # Paid review: os.stat(name, dir_fd=fd) on a descriptor for '/' probed undeclared absence.
    for index, body in enumerate(('fd = os.open("/", os.O_RDONLY)',
                                  'fd = os.open("ops", os.O_RDONLY); os.stat("../../never-created", dir_fd=fd)',
                                  'fd = os.open("ops", os.O_RDONLY); os.open("../../x", os.O_RDONLY, dir_fd=fd)',
                                  'fd = os.open("output", os.O_RDONLY); os.mkdir("../../made", dir_fd=fd)',
                                  'fd = os.open("in", os.O_RDONLY); os.open("new", os.O_CREAT | os.O_WRONLY, dir_fd=fd)')):
        script = (f'import os\ndef run(context):\n    try:\n        {body}\n    except BaseException:\n        pass\n'
                  '    context.output("piece.txt").write_text("ran")\n')
        assert 'undeclared' in failure(loop.run(stage(tmp_path / f'job{index}', script=script)), 'dependency')
    assert not (tmp_path / 'made').exists()
    # Descriptor-relative access inside the declared view still works, including shutil.rmtree.
    inside = '''
import os, shutil
def run(context):
    fd = os.open('in', os.O_RDONLY)
    seen = [os.path.exists('shape.bin') or 'x', sorted(os.listdir(fd)), os.stat('shape.bin', dir_fd=fd).st_size]
    try:
        os.stat('absent.bin', dir_fd=fd)
    except FileNotFoundError:
        seen.append('absent')
    os.makedirs('output/tmp/a')
    open('output/tmp/a/f', 'w').write('x')
    shutil.rmtree('output/tmp')
    context.output('piece.txt').write_text(repr(seen))
'''
    assert loop.run(stage(tmp_path / 'inside', script=inside))['type'] == 'completed'
    assert (tmp_path / 'inside/output/piece.txt').read_text() == "['x', ['shape.bin'], 2, 'absent']"


def test_imports_from_undeclared_path_entries_fail_whether_present_or_missing(tmp_path, loop):
    # The import system probes path entries with posix.stat, which raises no audit event; a missing
    # entry used to fail as a plain ModuleNotFoundError (`job`) instead of an undeclared access.
    present = tmp_path / 'elsewhere'
    present.mkdir()
    (present / 'stray_module.py').write_text('VALUE = 1\n')
    for index, entry in enumerate((tmp_path / 'never-created', present)):
        for name in ('stray_module', 'not_declared_module'):
            script = f'import sys\ndef run(context):\n    sys.path.append({str(entry)!r})\n    __import__({name!r})\n'
            job = stage(tmp_path / f'job-{index}-{name}', script=script)
            assert 'undeclared read' in failure(loop.run(job), 'dependency')
    # Clearing the importer cache is no bypass: the hook checks every entry again.
    cleared = (f'import sys\ndef run(context):\n    sys.path_importer_cache.clear()\n'
               f'    sys.path.append({str(tmp_path / "never-created")!r})\n    __import__("not_declared_module")\n')
    assert 'undeclared read' in failure(loop.run(stage(tmp_path / 'cleared', script=cleared)), 'dependency')
    # Removing the hook or the finder is no bypass either: another check stops the probe, or the removal
    # itself is detected when the op returns.
    removals = ("sys.path_hooks[:] = [hook for hook in sys.path_hooks if getattr(hook, '__name__', '') != 'path_hook']",
                "sys.meta_path[:] = [item for item in sys.meta_path if type(item).__name__ != 'DeclaredCodeFinder']")
    for index, removal in enumerate(removals):
        script = (f'import sys\ndef run(context):\n    {removal}\n'
                  f'    sys.path.append({str(tmp_path / "never-created")!r})\n'
                  '    try:\n        __import__("not_declared_module")\n    except ImportError:\n        pass\n'
                  '    context.output("piece.txt").write_text("hidden")\n')
        message = failure(loop.run(stage(tmp_path / f'removed-{index}', script=script)), 'dependency')
        assert 'removed the import guards' in message or 'undeclared read' in message
    removed = ("import sys\ndef run(context):\n"
               "    sys.path_hooks[:] = [hook for hook in sys.path_hooks if getattr(hook, '__name__', '') != 'path_hook']\n"
               "    context.output('piece.txt').write_text('hidden')\n")
    assert 'removed the import guards' in failure(loop.run(stage(tmp_path / 'removed', script=removed)), 'dependency')
    # Declared code and platform modules still import after the hook is installed.
    fine = 'import json, helper\ndef run(context):\n    context.output("piece.txt").write_text(helper.VALUE)\n'
    job = stage(tmp_path / 'fine', script=fine, code={'ops/helper.py': 'VALUE = "ok"\n'})
    assert loop.run(job)['type'] == 'completed'


def test_realtime_clocks_and_module_level_reseeding_are_fixed(tmp_path, loop):
    # Paid review: time.clock_gettime(CLOCK_REALTIME) and random.seed() escaped the fixes.
    script = '''
import random, time
def run(context):
    first = random.random()
    random.seed()
    reseeded = random.random()
    random.seed(7)
    explicit = random.random()
    clocks = [time.clock_gettime(time.CLOCK_REALTIME), time.clock_gettime_ns(time.CLOCK_REALTIME)]
    time.monotonic()  # elapsed-time clocks still run; they must not shape output
    context.output('piece.txt').write_text(repr([reseeded == explicit, random.Random().random() == explicit,
                                                 clocks, first]))
'''
    # The bootstrap skips the clock_gettime fix only where an interpreter has none (Blender's bundled
    # Python). Every supported host Python has it, so for Python jobs the fix must apply, as asserted below.
    import time
    assert hasattr(time, 'clock_gettime') and hasattr(time, 'CLOCK_REALTIME')
    texts = []
    for index in range(2):
        job = stage(tmp_path / f'job{index}', script=script, params={'scale': 1, 'seed': 7})
        assert loop.run(job)['type'] == 'completed'
        texts.append((tmp_path / f'job{index}/output/piece.txt').read_text())
    assert texts[0] == texts[1]
    assert texts[0].startswith('[True, True, [946684800.0, 946684800000000000], ')


def test_large_valid_requests_run_and_launch_failures_still_get_a_terminal_reply(tmp_path, loop, monkeypatch):
    # Paid review: a one-MiB parameter overflowed argv (E2BIG) and the loop sent no terminal reply.
    script = 'def run(context):\n    context.output("piece.txt").write_text(str(len(context.params["blob"])))\n'
    job = stage(tmp_path / 'large', script=script, params={'scale': 1, 'blob': 'x' * (4 << 20)})
    assert loop.run(job)['type'] == 'completed'
    assert (tmp_path / 'large/output/piece.txt').read_text() == str(4 << 20)

    def refuse(*args, **kwargs):
        raise OSError(7, 'Argument list too long')

    monkeypatch.setattr(python_worker.subprocess, 'Popen', refuse)
    request_read, request_write = os.pipe()
    response_read, response_write = os.pipe()
    with os.fdopen(request_write, 'wb') as requests:
        protocol.write_frame(requests, protocol.REQUEST, {'type': 'run', 'job': stage(tmp_path / 'refused')})
        protocol.write_frame(requests, protocol.REQUEST, {'type': 'shutdown'})
    with os.fdopen(request_read, 'rb') as requests, os.fdopen(response_write, 'wb') as responses:
        python_worker.Worker(requests, responses, sandboxed=False).serve()
    with os.fdopen(response_read, 'rb') as responses:
        replies = [protocol.read_frame(responses, protocol.RESPONSE) for _ in range(4)]
    assert replies[1] == {'type': 'started', 'job_id': 'job-1'}
    assert 'cannot start the job process' in failure(replies[2], 'dependency')
    assert replies[3] == {'type': 'stopped'}


def test_directory_changes_are_refused_so_relative_checks_stay_anchored(tmp_path, loop):
    # Paid review: after os.chdir('/'), relative existence checks were resolved against the job folder.
    for index, body in enumerate(('os.chdir("/"); os.path.exists("never-created")',
                                  'os.chdir("ops"); os.path.exists("never-created")',
                                  'fd = os.open("ops", os.O_RDONLY); os.fchdir(fd)')):
        script = (f'import os\ndef run(context):\n    try:\n        {body}\n    except BaseException:\n        pass\n'
                  '    context.output("piece.txt").write_text("ran")\n')
        assert 'os.chdir' in failure(loop.run(stage(tmp_path / f'job{index}', script=script)), 'dependency')


@pytest.mark.parametrize('neighbor', [
    '/private/etc/ssl/cert.pem',
    '/private/etc/ssl/certs/example.pem',
    '/private/etc/hosts',
])
def test_openssl_platform_config_literal_never_grants_neighbor_data_reads(monkeypatch, neighbor):
    """Inspect the actual generated profile; this portable test does not execute Seatbelt."""
    import re
    from pathlib import PurePosixPath

    monkeypatch.setattr(python_worker, 'interpreter_roots', lambda: ['/installed/python'])
    monkeypatch.setattr(python_worker, 'interpreter_executables', lambda: ['/installed/python/bin/python'])
    monkeypatch.setattr(python_worker, '_links', lambda path: [])
    profile = python_worker.sandbox_profile('/staged-job')
    read_rule = next(line for line in profile.splitlines() if line.startswith('(allow file-read* '))
    # Parse only generated filter operands, not a second sandbox-policy implementation.
    operands = re.findall(r'\((literal|subpath) ("(?:[^"\\]|\\.)*")\)', read_rule)
    literals = [json.loads(value) for kind, value in operands if kind == 'literal']
    subpaths = [json.loads(value) for kind, value in operands if kind == 'subpath']
    assert literals.count('/private/etc/ssl/openssl.cnf') == 1
    assert '/etc/ssl/openssl.cnf' not in literals  # No unneeded alias grant.
    assert neighbor not in literals
    assert not any(PurePosixPath(neighbor).is_relative_to(path) for path in subpaths)
    assert '/private/etc' not in subpaths and '/private/etc/ssl' not in subpaths
    assert '(deny default)' in profile
    assert '(deny file-read* network* (with send-signal SIGKILL))' in profile
    assert '(allow network' not in profile and '(allow mach-lookup' not in profile
    assert 'OPENSSL_CONF' not in python_worker.JOB_ENVIRONMENT
    assert next(line for line in profile.splitlines() if line.startswith('(allow process-exec ')) == (
        '(allow process-exec (literal "/installed/python/bin/python"))')
    assert next(line for line in profile.splitlines() if line.startswith('(allow file-write* ')) == (
        '(allow file-write* (subpath "/staged-job/output") (literal "/dev/null"))')
