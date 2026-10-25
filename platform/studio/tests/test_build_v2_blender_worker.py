"""The build-v2 Blender job loop over a stand-in Blender (portable; real Blender is the T1b session).

The stand-in accepts only the job command line the loop must use, installs a minimal `bpy` and runs
the job expression, so these tests prove the loop's protocol, command line, environment, clean
process per job and failure handling. Blender's own startup, exporters and sandbox reads are proven
only by the admitted T1b session.
"""
import os
from pathlib import Path
import subprocess
import sys

import pytest

from atelier.build_v2 import blender_worker, protocol, python_worker
from test_build_v2_python_worker import Loop, failure, stage as python_stage

FIXTURES = Path(__file__).resolve().parents[2] / 'build-v2/tests/fixtures'
UNSANDBOXED = FIXTURES / 'unsandboxed_blender_loop.py'
WORKER = Path(blender_worker.__file__)


def stage(*args, **kwargs):
    job = python_stage(*args, **kwargs)
    scratch = Path(job['job_dir']) / blender_worker.RUNTIME_DIRECTORY
    if not os.path.lexists(scratch):
        scratch.mkdir(mode=0o700)
    return job


def fake_blender(root):
    """A stand-in `Blender` binary inside an application bundle, run by this test's interpreter."""
    binary = root / 'Blender.app/Contents/MacOS/Blender'
    binary.parent.mkdir(parents=True)
    binary.write_text(f'#!{sys.executable} -sS\n' + (FIXTURES / 'fake_blender.py').read_text(encoding='utf-8'))
    binary.chmod(0o755)
    return binary


class BlenderLoop(Loop):
    def __init__(self, blender, log=None):
        self.blender = blender
        super().__init__(UNSANDBOXED, '--blender', str(blender), log=log)


@pytest.fixture
def blender(tmp_path):
    return fake_blender(tmp_path / 'platform')


@pytest.fixture
def loop(blender, monkeypatch):
    monkeypatch.setattr(python_worker, 'TEST_WORKER_VERSION', blender_worker.TEST_WORKER_VERSION)
    worker = BlenderLoop(blender)
    yield worker
    if worker.process.poll() is None:
        worker.process.kill()
        worker.process.wait()


def output(job):
    return (Path(job['job_dir']) / 'output/piece.txt').read_bytes()


def test_job_runs_in_a_reset_factory_blender_and_reports_its_outputs(tmp_path, loop, blender):
    script = '''
import bpy, sys
def run(context):
    data = context.input('shape').read_bytes()
    context.output('piece.txt').write_text(repr((data, bpy.app.version_string, bpy.factory_resets,
                                                 bpy.app.binary_path)))
'''
    job = stage(tmp_path / 'job', script=script)
    assert loop.run(job) == {'type': 'completed', 'job_id': 'job-1', 'outputs': {'files': ['piece.txt']}}
    # One reset to an empty factory file before the op, in the Blender binary the loop was given.
    assert output(job) == repr((b'ab', 'fake-blender', [True], str(blender))).encode()
    loop.close()


def test_each_job_gets_a_fresh_blender_so_order_does_not_change_bytes(tmp_path, loop, blender):
    # Every job leaves state behind in bpy, a module and the process; none of it may reach the next job.
    script = '''
import bpy, json, os, sys
def run(context):
    seen = [getattr(bpy, 'left_behind', None), sorted(name for name in sys.modules if name.startswith('ops_'))]
    bpy.left_behind = context.params['name']
    sys.modules['ops_' + context.params['name']] = sys
    context.output('piece.txt').write_text(json.dumps([context.params['name'], seen, os.getpid() > 0]))
'''
    a, b = {'name': 'a', 'scale': 1}, {'name': 'b', 'scale': 1}
    runs = [('alone', a), ('b-first', b), ('b-then-a', a), ('a-first', a), ('a-then-b', b), ('a-b-a', a)]
    produced = {}
    for name, params in runs:
        job = stage(tmp_path / name, script=script, params=params)
        assert loop.run(job)['type'] == 'completed'
        produced[name] = output(job)
    loop.close()
    fresh = BlenderLoop(blender)
    job = stage(tmp_path / 'fresh', script=script, params=a)
    assert fresh.run(job)['type'] == 'completed'
    fresh.close()
    assert produced['alone'] == produced['b-then-a'] == produced['a-b-a'] == output(job)
    assert produced['alone'] == b'["a", [null, []], true]'
    assert produced['b-first'] == produced['a-then-b'] != produced['alone']


def test_job_command_line_keeps_explicit_threads_before_the_job_and_no_user_state(tmp_path, blender):
    worker = blender_worker.BlenderWorker(None, None, sandboxed=True, blender=str(blender))
    command = worker.child_command()
    assert command[0] == str(blender)
    flags = command[1:command.index('--python-expr')]
    assert flags == ['--factory-startup', '-b', '--threads', '3', '--python-exit-code', '1', '--disable-autoexec',
                     '--python-use-system-env']
    assert command[-1].startswith(blender_worker.BOOTSTRAP) and command[-1].endswith(')\n')
    assert worker.version == blender_worker.WORKER_VERSION != python_worker.WORKER_VERSION
    environment = worker.child_environment(str(tmp_path / 'job'))
    missing = str(tmp_path / 'job' / blender_worker.MISSING_USER_FOLDER)
    assert {name: environment[name] for name in blender_worker.USER_FOLDERS} == \
        {name: missing for name in blender_worker.USER_FOLDERS}
    assert environment['PYTHONHASHSEED'] == '0' and 'PATH' not in environment and 'PYTHONPATH' not in environment


def test_job_sees_only_the_declared_environment_and_user_folders_that_do_not_exist(tmp_path, loop):
    probe = '''
import json, os
def run(context):
    folders = {name: os.environ[name] for name in ('HOME', 'BLENDER_USER_CONFIG', 'BLENDER_USER_SCRIPTS')}
    context.output('piece.txt').write_text(json.dumps([sorted(os.environ), sorted(set(folders.values())),
                                                       hash('salted')]))
'''
    first, second = stage(tmp_path / 'one', script=probe), stage(tmp_path / 'two', script=probe)
    assert loop.run(first)['type'] == 'completed'
    assert loop.run(second)['type'] == 'completed'
    names, folders, salted = __import__('json').loads(output(first))
    assert names == sorted(set(python_worker.JOB_ENVIRONMENT) | set(blender_worker.USER_FOLDERS) | {'TMPDIR'})
    assert folders == [str(Path(os.path.realpath(tmp_path / 'one')) / blender_worker.MISSING_USER_FOLDER)]
    assert not (tmp_path / 'one' / blender_worker.MISSING_USER_FOLDER).exists()
    # The declared hash seed reaches the job's Python; the second job's own folder differs, the hash not.
    assert __import__('json').loads(output(second))[2] == salted
    loop.close()


def test_jobs_whose_folder_holds_the_missing_user_folder_are_refused_before_blender_starts(tmp_path, loop):
    # Declared code under the reserved name would give Blender a real, readable user folder.
    marker = tmp_path / 'started'
    script = f'def run(context):\n    open({str(marker)!r}, "w").close()\n'
    code = {f'{blender_worker.MISSING_USER_FOLDER}/startup/helper.py': 'raise SystemExit(3)\n'}
    declared = stage(tmp_path / 'declared', script=script, code=code)
    worker = blender_worker.BlenderWorker(None, None, sandboxed=True, blender=str(loop.blender))
    with pytest.raises(python_worker.JobRefused, match=blender_worker.RUNTIME_DIRECTORY):
        worker.check_job_folder(declared['job_dir'])
    assert blender_worker.RUNTIME_DIRECTORY in failure(loop.run(declared), 'protocol')
    dangling = stage(tmp_path / 'dangling', script=script, job_id='job-2')
    (tmp_path / 'dangling' / blender_worker.RUNTIME_DIRECTORY).rmdir()
    os.symlink(tmp_path / 'nowhere', tmp_path / 'dangling' / blender_worker.RUNTIME_DIRECTORY)
    with pytest.raises(python_worker.JobRefused, match=blender_worker.RUNTIME_DIRECTORY):
        worker.check_job_folder(dangling['job_dir'])
    assert blender_worker.RUNTIME_DIRECTORY in failure(loop.run(dangling), 'protocol')
    assert not marker.exists()
    assert (tmp_path / 'declared' / blender_worker.MISSING_USER_FOLDER / 'startup/helper.py').read_text() == 'raise SystemExit(3)\n'
    assert (tmp_path / 'dangling' / blender_worker.RUNTIME_DIRECTORY).is_symlink()
    assert loop.run(stage(tmp_path / 'next', job_id='job-3'))['type'] == 'completed'
    loop.close()


def test_factory_user_directory_is_fresh_private_scratch_and_not_product_output(tmp_path, loop):
    script = '''
import os
from pathlib import Path
def run(context):
    home = Path(os.environ['HOME'])
    home.mkdir(parents=True)
    (home / 'unexpected-preference').write_text('must remain in actual inventory')
    context.output('piece.txt').write_text('complete')
'''
    job = stage(tmp_path / 'factory', script=script)
    result = loop.run(job)
    assert result['type'] == 'completed'
    assert result['outputs']['files'] == ['piece.txt']
    assert (tmp_path / 'factory' / blender_worker.MISSING_USER_FOLDER / 'unexpected-preference').read_text() == 'must remain in actual inventory'
    assert Path(os.environ.get('HOME', '')).resolve() != (tmp_path / 'factory' / blender_worker.MISSING_USER_FOLDER)
    loop.close()


def test_failure_publishes_nothing_and_the_next_job_behaves(tmp_path, loop):
    broken = 'def run(context):\n    context.output("piece.txt").write_text("partial")\n    raise ValueError("boom")\n'
    job = stage(tmp_path / 'broken', script=broken)
    assert 'boom' in failure(loop.run(job), 'job')
    # The loop reports a failure only; the controller removes the job folder, publishing nothing.
    good = stage(tmp_path / 'good', job_id='job-2')
    assert loop.run(good) == {'type': 'completed', 'job_id': 'job-2', 'outputs': {'files': ['piece.txt']}}
    assert output(good) == b'abab0'
    loop.close()


def test_blender_ending_without_a_result_fails_the_job(tmp_path, loop):
    abrupt = 'import os\ndef run(context):\n    os._exit(1)\n'
    assert 'no result' in failure(loop.run(stage(tmp_path / 'abrupt', script=abrupt)), 'job')
    assert loop.run(stage(tmp_path / 'next', job_id='job-2'))['type'] == 'completed'
    loop.close()


def test_loop_reports_every_actual_output_and_refuses_links(tmp_path, loop):
    # The complete actual set: the controller refuses an undeclared or missing member and publishes nothing.
    extra = ('def run(context):\n    (context.output_dir / "stray.bin").write_text("b")\n'
             '    context.output("piece.txt").write_text("a")\n')
    assert loop.run(stage(tmp_path / 'extra', script=extra))['outputs'] == {'files': ['piece.txt', 'stray.bin']}
    missing = stage(tmp_path / 'missing', script='def run(context):\n    pass\n')
    assert loop.run(missing)['outputs'] == {'files': []}
    link = 'import os\ndef run(context):\n    os.symlink("/etc/hosts", context.output("piece.txt"))\n'
    assert 'os.symlink' in failure(loop.run(stage(tmp_path / 'link', script=link)), 'dependency')
    fifo = 'import os\ndef run(context):\n    os.mkfifo(context.output("piece.txt"))\n'
    assert 'regular file' in failure(loop.run(stage(tmp_path / 'fifo', script=fifo)), 'job')
    loop.close()


def test_cancel_stops_the_blender_and_the_loop_serves_the_next(tmp_path, loop):
    slow = 'import threading\ndef run(context):\n    threading.Event().wait(60)\n'
    loop.send({'type': 'run', 'job': stage(tmp_path / 'slow', script=slow)})
    assert loop.read() == {'type': 'started', 'job_id': 'job-1'}
    loop.send({'type': 'cancel', 'job_id': 'job-1'})
    failure(loop.read(), 'cancelled')
    assert list((tmp_path / 'slow/output').iterdir()) == []
    assert loop.run(stage(tmp_path / 'next', job_id='job-2'))['type'] == 'completed'
    loop.close()


def test_missing_blender_gets_a_terminal_failure_and_a_clean_shutdown(tmp_path, monkeypatch):
    monkeypatch.setattr(python_worker, 'TEST_WORKER_VERSION', blender_worker.TEST_WORKER_VERSION)
    loop = BlenderLoop(tmp_path / 'no/Blender.app/Contents/MacOS/Blender')
    assert 'cannot start the job process' in failure(loop.run(stage(tmp_path / 'job')), 'dependency')
    assert list((tmp_path / 'job/output').iterdir()) == []
    loop.close()


def test_production_entry_has_no_unsandboxed_mode_and_uses_the_admitted_blender(monkeypatch):
    for flags in (['--unsandboxed'], ['--blender', '/elsewhere/Blender'], ['--sandboxed=false']):
        run = subprocess.run([sys.executable, '-I', str(WORKER), '--', '--request-fd', '0', '--response-fd', '1',
                              *flags], stdin=subprocess.DEVNULL, capture_output=True, timeout=20)
        assert run.returncode == 2 and b'unrecognized arguments' in run.stderr
    served = []
    monkeypatch.setattr(blender_worker, 'serve', lambda *args, **kwargs: served.append((args, kwargs)))
    monkeypatch.setitem(sys.modules, 'bpy', type(sys)('bpy'))
    sys.modules['bpy'].app = type('app', (), {'binary_path': '/Applications/Blender.app/Contents/MacOS/Blender'})
    monkeypatch.setattr(sys, 'argv', ['Blender', '-b', '-P', str(WORKER), '--', '--request-fd', '5',
                                      '--response-fd', '6'])
    blender_worker.main()
    assert served == [((5, 6), {'sandboxed': True, 'blender': '/Applications/Blender.app/Contents/MacOS/Blender'})]
    assert blender_worker.TEST_WORKER_VERSION != blender_worker.WORKER_VERSION


def test_sandbox_profile_allows_the_bundle_and_only_the_blender_binary(tmp_path, blender):
    worker = blender_worker.BlenderWorker(None, None, sandboxed=True, blender=str(blender))
    assert blender_worker.application_bundle(str(blender)) == str(tmp_path / 'platform/Blender.app')
    assert blender_worker.application_bundle(sys.executable) != '/'
    job_dir = str(tmp_path / 'job')
    profile = python_worker.sandbox_profile(job_dir, worker.platform)
    lines = profile.splitlines()
    assert lines[:3] == ['(version 1)', '(deny default)', '(deny file-read* network* (with send-signal SIGKILL))']
    executables = next(line for line in lines if line.startswith('(allow process-exec'))
    assert executables == f'(allow process-exec (literal "{blender}"))'
    reads = next(line for line in lines if line.startswith('(allow file-read* '))
    assert f'(subpath "{tmp_path / "platform/Blender.app"}")' in reads and f'(subpath "{job_dir}")' in reads
    home = os.path.expanduser('~')
    assert f'"{home}"' not in reads and f'"{home}/Library' not in profile
    writes = next(line for line in lines if line.startswith('(allow file-write*'))
    assert writes == (f'(allow file-write* (subpath "{job_dir}/output") '
                      f'(subpath "{job_dir}/{blender_worker.RUNTIME_DIRECTORY}") (literal "/dev/null"))')
    default_profile = python_worker.sandbox_profile(job_dir)
    assert f'(subpath "{job_dir}/{blender_worker.RUNTIME_DIRECTORY}")' not in default_profile
    assert str(tmp_path / 'platform/Blender.app') in worker.platform.import_roots()
    # The reviewed Blender allowances follow the kill rule, so the bind refusal replaces the kill for binds only.
    assert lines[-len(blender_worker.BLENDER_RULES):] == list(blender_worker.BLENDER_RULES)
    assert lines[-1] == '(deny network-bind)'
    assert '(literal "/usr/share/icu")' not in reads and '(subpath "/usr/share/icu")' in reads
    # /dev/urandom is readable to Blender's startup in the kernel profile only, never to the Python guard.
    config = python_worker.job_config(stage(tmp_path / 'job'), str(tmp_path / 'job'), 9, worker.platform)
    assert '/dev/urandom' not in config['read_literals'] and '/dev/urandom' not in config['read_subpaths']
    assert '/Applications/Xcode.app' not in config['read_literals']


def test_sandboxed_loop_fails_jobs_without_a_sandbox_tool(tmp_path, blender, monkeypatch):
    monkeypatch.setattr(python_worker, 'SANDBOX_EXEC', str(tmp_path / 'missing-sandbox'))
    request_read, request_write = os.pipe()
    response_read, response_write = os.pipe()
    with os.fdopen(request_write, 'wb') as requests:
        protocol.write_frame(requests, protocol.REQUEST, {'type': 'run', 'job': stage(tmp_path / 'job')})
        protocol.write_frame(requests, protocol.REQUEST, {'type': 'shutdown'})
    with os.fdopen(request_read, 'rb') as requests, os.fdopen(response_write, 'wb') as responses:
        blender_worker.BlenderWorker(requests, responses, sandboxed=True, blender=str(blender)).serve()
    with os.fdopen(response_read, 'rb') as responses:
        replies = [protocol.read_frame(responses, protocol.RESPONSE) for _ in range(4)]
    assert replies[0] == {'type': 'hello', 'worker_version': blender_worker.WORKER_VERSION}
    assert 'no supported job sandbox' in failure(replies[2], 'dependency')
    assert replies[3] == {'type': 'stopped'}


def test_uuid4_is_seeded_in_blender_jobs_and_other_entropy_stays_refused(tmp_path, loop):
    # Blender's bundled glTF exporter keys its node tree with uuid4, so it must work, from the seed.
    script = '''
import random, uuid
def run(context):
    context.output('piece.txt').write_text(f'{uuid.uuid4()} {uuid.uuid4()} {random.random()}')
'''
    texts = []
    for index, seed in enumerate((1, 1, 2)):
        job = stage(tmp_path / f'job{index}', script=script, params={'scale': 1, 'seed': seed})
        assert loop.run(job)['type'] == 'completed'
        texts.append(output(job).decode())
    assert texts[0] == texts[1] != texts[2]
    first, second, number = texts[0].split()
    assert first != second and first[14] == '4'
    # The op's own random stream is the Python job's: uuid4 draws from a separate generator.
    import random
    assert float(number) == random.Random(1).random()
    for index, call in enumerate(('os.urandom(4)', 'uuid.uuid1()', '__import__("secrets")', 'random.SystemRandom()')):
        script = f'import os, random, uuid\ndef run(context):\n    {call}\n'
        assert loop.run(stage(tmp_path / f'entropy{index}', script=script))['failure']['kind'] == 'dependency'
    loop.close()


def test_background_render_registration_has_exact_native_service_and_bundle_bounds(tmp_path, blender):
    platform = blender_worker.BlenderPlatform(str(blender))
    profile = python_worker.sandbox_profile(str(tmp_path / 'job'), platform)
    rules = [line for line in profile.splitlines() if line.startswith('(allow mach-lookup')]
    assert rules == ['(allow mach-lookup ' + ' '.join('(global-name "' + service + '")'
                       for service in blender_worker.BLENDER_RENDER_SERVICES) + ')']
    assert set(blender_worker.BLENDER_RENDER_SERVICES) == {
        'com.apple.windowserver.active', 'com.apple.coreservices.launchservicesd',
        'com.apple.lsd.mapdb', 'com.apple.lsd.modifydb'}
    extension = [line for line in profile.splitlines() if line.startswith('(allow file-issue-extension')]
    assert extension == ['(allow file-issue-extension (require-all '
        '(extension-class "com.apple.app-sandbox.read") (literal "' + platform.bundle + '")))']
    ordinary = python_worker.sandbox_profile(str(tmp_path / 'job'))
    assert '(allow mach-lookup' not in ordinary and '(allow file-issue-extension' not in ordinary
    assert 'com.apple.pasteboard' not in profile and 'com.apple.tccd' not in profile
    setup = [line for line in profile.splitlines() if '/private/var/db/.AppleSetupDone' in line]
    assert len(setup) == 1 and setup[0].startswith('(allow file-read-metadata ')
    assert '(literal "/private/var/db/.AppleSetupDone")' in setup[0]
    assert '(subpath "/private/var/db")' not in profile
    eligibility = '/private/var/db/eligibilityd/eligibility.plist'
    assert '(allow file-read-data (literal "' + eligibility + '"))' in profile
    roots, literals = platform.reads()
    assert eligibility not in literals and not any(eligibility.startswith(root + '/') for root in roots)
    assert '(allow process*)' not in profile and '(allow network*)' not in profile
    assert profile.splitlines()[-1] == '(deny network-bind)'
    outside_bundle = blender_worker.BlenderPlatform(str(tmp_path / 'plain/Blender'))
    assert not any(line.startswith('(allow file-issue-extension') for line in outside_bundle.extra_rules())
