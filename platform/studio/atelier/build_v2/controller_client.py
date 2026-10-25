"""Bounded transport and immutable source capture for the normal Rust controller.

These are distribution/control operations, never build-item keys or cache policy.
Planning uses inspect_controller only; it must not call a bootstrap or create state.
"""
from dataclasses import dataclass
from contextlib import chdir, contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import signal
import tempfile
import time
import uuid

MAX_CONTROL_BYTES = 64 * 1024 * 1024
MAX_SOURCE_FILE_BYTES = 8 * 1024 * 1024
MAX_SOURCE_TOTAL_BYTES = 32 * 1024 * 1024
MAX_NAMED_ISSUER_FILES = 512
MAX_BINARY_BYTES = 256 * 1024 * 1024
SOURCE_MANIFEST = 'platform/build-v2/controller-sources.json'


def _stamp(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def _relative(name):
    if (not isinstance(name, str) or not name or '\\' in name or '\x00' in name
            or str(PurePosixPath(name)) != name or PurePosixPath(name).is_absolute()
            or any(part in ('.', '..') for part in name.split('/'))):
        raise ValueError('controller file name must be a normalized relative path')
    return name


def _open_root(root, *, private=False):
    path = Path(os.path.abspath(root))
    descriptor = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        info = os.fstat(descriptor)
        if private and (info.st_uid != os.getuid() or info.st_mode & 0o077):
            raise ValueError('controller control directory must be private and owned')
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _read_at(root, name, bound, *, owned=False):
    """Read one regular file through an anchored nofollow chain, including parents."""
    parts = _relative(name).split('/')
    descriptor = _open_root(root, private=owned)
    try:
        for index, part in enumerate(parts):
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            if index != len(parts) - 1:
                flags |= os.O_DIRECTORY
            child = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return _read_descriptor(descriptor, bound, owned=owned)
    finally:
        os.close(descriptor)


def _read_descriptor(descriptor, bound, *, owned=False):
    before = os.fstat(descriptor)
    if not stat.S_ISREG(before.st_mode) or not 0 <= before.st_size <= bound:
        raise ValueError('controller file is not regular or exceeds its size bound')
    if owned and (before.st_uid != os.getuid() or before.st_mode & 0o077 or before.st_nlink != 1):
        raise ValueError('controller control file must be private, unique and owned')
    chunks, size = [], 0
    while chunk := os.read(descriptor, min(1024**2, bound + 1 - size)):
        chunks.append(chunk)
        size += len(chunk)
        if size > bound:
            raise ValueError('controller file grew beyond its size bound')
    if _stamp(before) != _stamp(os.fstat(descriptor)) or size != before.st_size:
        raise ValueError('controller file changed during capture')
    return b''.join(chunks)


def _json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate control field')
            result[key] = value
        return result
    def nonfinite(value):
        raise ValueError('non-finite control number')
    return json.loads(raw, object_pairs_hook=unique, parse_constant=nonfinite)


@dataclass(frozen=True)
class ControllerSource:
    """Short-lived bootstrap source bytes; never retained by the build explanation ledger."""
    digest: str
    files: tuple

    def materialize(self, destination):
        """Write only this captured closure into a new private source root."""
        root = Path(destination)
        root.mkdir(mode=0o700)
        for name, raw in self.files:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as stream:
                stream.write(raw)
                stream.flush()
                os.fchmod(stream.fileno(), 0o400)
                os.fsync(stream.fileno())


def capture_controller(root):
    """@cc [owner:fontanierh,label:correctness] frozen-controller-distribution
    Controller freshness MUST bind the explicit source manifest and every named regular
    source/config/Cargo file captured without following links. Compilation MUST consume
    materialized captured bytes, never mutable checkout bytes labeled as frozen. Source
    location, Git revision and ambient timestamps MUST NOT enter this distribution digest.
    See test_controller_sources_are_named_frozen_and_location_independent and
    test_controller_source_capture_refuses_links_and_undeclared_build_dependencies.
    """
    raw = _read_at(root, SOURCE_MANIFEST, MAX_CONTROL_BYTES)
    manifest = _json(raw)
    if (not isinstance(manifest, dict) or set(manifest) != {'version', 'files'}
            or type(manifest['version']) is not int or manifest['version'] != 1
            or not isinstance(manifest['files'], list) or not manifest['files']
            or len(manifest['files']) > 256):
        raise ValueError('unsupported controller source manifest')
    names = [_relative(name) for name in manifest['files']]
    if len(set(names)) != len(names) or SOURCE_MANIFEST in names:
        raise ValueError('duplicate controller source name')
    required = {'platform/build-v2/Cargo.toml', 'platform/build-v2/Cargo.lock',
                'platform/build-v2/.cargo/config.toml', 'platform/build-v2/src/lib.rs',
                'platform/build-v2/src/bin/atelier-build-v2.rs'}
    if not required <= set(names):
        raise ValueError('controller source closure is missing required build files')
    files = [(SOURCE_MANIFEST, raw)]
    total = len(raw)
    for name in sorted(names):
        content = _read_at(root, name, MAX_SOURCE_FILE_BYTES)
        total += len(content)
        if total > MAX_SOURCE_TOTAL_BYTES:
            raise ValueError('controller source closure exceeds its size bound')
        files.append((name, content))
    # Cargo path dependencies/build scripts must be deliberately included, never
    # discovered and silently compiled outside the frozen source closure.
    import tomllib
    cargo = tomllib.loads(dict(files)['platform/build-v2/Cargo.toml'].decode())
    if cargo.get('package', {}).get('build') or cargo.get('workspace'):
        raise ValueError('controller build-script/workspace closure needs explicit support')
    def dependencies(table):
        for group in ('dependencies', 'build-dependencies', 'dev-dependencies'):
            if any(isinstance(dep, dict) and ('path' in dep or 'workspace' in dep)
                   for dep in table.get(group, {}).values()):
                raise ValueError('controller path dependency closure needs explicit support')
        for target in table.get('target', {}).values():
            dependencies(target)
    dependencies(cargo)
    config = tomllib.loads(dict(files)['platform/build-v2/.cargo/config.toml'].decode())
    if (set(config) != {'build'} or set(config['build']) - {'jobs', 'target-dir'}
            or type(config['build'].get('jobs')) is not int or not 1 <= config['build']['jobs'] <= 3):
        raise ValueError('controller Cargo configuration needs explicit closure support')
    return _captured_source(files)


def _captured_source(files):
    """The existing distribution framing, also used by an explicit game issuer closure."""
    digest = hashlib.sha256()
    for name, content in sorted(files):
        encoded = name.encode()
        digest.update(len(encoded).to_bytes(8, 'big'))
        digest.update(encoded)
        digest.update(len(content).to_bytes(8, 'big'))
        digest.update(content)
    return ControllerSource(digest.hexdigest(), tuple(files))


def capture_named_sources(root, names):
    """@cc [owner:fontanierh,label:correctness;safety] finite-named-issuer-capture
    A game issuer capture MUST read only its fixed profile's explicit normalized file names
    through the same anchored nofollow/stable bounded reader and digest framing as the
    controller distribution. It MUST NOT discover an ambient directory closure or treat this
    byte capture as a semantic task/cleanup qualification. Its fixed 512-file count MUST NOT
    change the separate controller-distribution 256-file bound or existing byte bounds.
    Installed tool context MUST NOT be
    silently injected into game action identities. See test_build_v2_legacy_capture.py.
    """
    if type(names) not in (tuple, list) or not 0 < len(names) <= MAX_NAMED_ISSUER_FILES:
        raise ValueError('issuer closure needs bounded explicit source names')
    names = [_relative(name) for name in names]
    if len(set(names)) != len(names):
        raise ValueError('duplicate issuer source name')
    files, total = [], 0
    for name in sorted(names):
        raw = _read_at(root, name, MAX_SOURCE_FILE_BYTES)
        total += len(raw)
        if total > MAX_SOURCE_TOTAL_BYTES:
            raise ValueError('issuer source closure exceeds its size bound')
        files.append((name, raw))
    return _captured_source(files)


def write_control(directory, name, record):
    """Exclusive bounded request/report publication inside a caller-owned private directory."""
    _relative(name)
    if '/' in name:
        raise ValueError('control file must be a direct private child')
    raw = json.dumps(record, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()
    if len(raw) > MAX_CONTROL_BYTES:
        raise ValueError('controller control record exceeds its size bound')
    root = _open_root(directory, private=True)
    try:
        descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=root)
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(root)
    finally:
        os.close(root)


def read_control(directory, name):
    return _json(_read_at(directory, name, MAX_CONTROL_BYTES, owned=True))


def inspect_controller(root, directory):
    """Read-only freshness observation. Absence/staleness never triggers compilation."""
    source = capture_controller(root)
    try:
        receipt = read_control(directory, 'controller.json')
        if (not isinstance(receipt, dict) or set(receipt) != {'version', 'source', 'binary'}
                or type(receipt['version']) is not int or receipt['version'] != 1
                or receipt['source'] != source.digest):
            return {'state': 'bootstrap_needed', 'reason': 'source_or_receipt_mismatch'}
        binary = _read_at(directory, 'atelier-build-v2', MAX_BINARY_BYTES)
        if hashlib.sha256(binary).hexdigest() != receipt['binary']:
            return {'state': 'bootstrap_needed', 'reason': 'binary_mismatch'}
        return {'state': 'current', 'source': source.digest, 'binary': receipt['binary']}
    except FileNotFoundError:
        return {'state': 'bootstrap_needed', 'reason': 'missing_controller'}


def _private_root(path):
    """Create missing components under nofollow directory descriptors, never via links."""
    path = Path(os.path.abspath(path))
    descriptor = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            try:
                os.mkdir(part, 0o700, dir_fd=descriptor)
            except FileExistsError:
                pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        info = os.fstat(descriptor)
        if info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError('controller bootstrap directory must be private and owned')
    finally:
        os.close(descriptor)
    return path


@dataclass(frozen=True)
class ControllerExecutable:
    path: Path
    source: str
    binary: str


@contextmanager
def verified_controller(executable):
    """Execute only a private verified binary snapshot, including its embedded source binding."""
    from atelier.harness.board_web import prebuilt
    with prebuilt(executable.path, executable.binary) as binary:
        identity = subprocess.run([str(binary), '--identity'], stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, timeout=10, check=False)
        if identity.returncode or identity.stdout != (executable.source + '\n').encode():
            raise ValueError('controller binary does not bind the frozen source closure')
        yield binary


def ensure_controller(checkout, state, *, echo=print):
    """@cc [owner:fontanierh,label:safety] guarded-controller-bootstrap
    Execution bootstrap MUST compile only materialized frozen controller source through
    ordinary compile admission, locked Cargo and at most three jobs. A current helper
    MUST avoid compilation. Source/binary mismatch or compile/cleanup failure MUST
    refuse without stale fallback. Planning MUST never call this function. It runs
    synchronously before this caller can launch any job; its temporary cwd is restored.
    See test_bootstrap_compiles_frozen_bytes_under_guard_and_reuses_verified_helper and
    test_bootstrap_source_change_or_failure_never_publishes_helper.
    """
    from atelier.harness.safety import guarded
    checkout = Path(checkout)
    captured = capture_controller(checkout)
    state = _private_root(state)
    lock = os.open(state / '.bootstrap.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(lock)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError('invalid controller bootstrap lock')
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('controller bootstrap is already active; no second compile started') from None
        final = state / captured.digest
        observed = inspect_controller(checkout, final)
        if observed['state'] == 'current':
            return ControllerExecutable(final / 'atelier-build-v2', captured.digest, observed['binary'])
        if final.exists() or final.is_symlink():
            raise ValueError('existing controller distribution is incomplete or changed; preserved for diagnosis')
        target = _private_root(state / 'target')
        echo('Preparing build controller: guarded incremental Cargo build (locked, 3 jobs)')
        with tempfile.TemporaryDirectory(prefix='atelier-controller-source-') as temporary:
            frozen = Path(temporary).resolve() / 'source'
            captured.materialize(frozen)
            env = {name: value for name, value in os.environ.items()
                   if not name.startswith('CARGO_') and name not in ('RUSTFLAGS', 'RUSTDOCFLAGS')}
            env.update(ATELIER_CONTROLLER_SOURCE_SHA256=captured.digest, CARGO_INCREMENTAL='1',
                       CARGO_ENCODED_RUSTFLAGS='', RUSTFLAGS='')
            with chdir(frozen / 'platform/build-v2'):
                code = guarded.run(['cargo', 'build', '--locked', '--jobs', '3', '--target-dir', str(target),
                                    '--bin', 'atelier-build-v2'],
                                   state / ('compile-' + uuid.uuid4().hex + '.guard'),
                                   kind='compile', timeout=1800, queue_seconds=1800, progress=25,
                                   aggregate_tree=True, purpose='prepare normal build controller', env=env)
            if code:
                raise RuntimeError('guarded controller compile failed; no helper published')
            if capture_controller(frozen).digest != captured.digest or capture_controller(checkout).digest != captured.digest:
                raise ValueError('controller source changed during bootstrap; no helper published')
            raw = _read_at(target, 'debug/atelier-build-v2', MAX_BINARY_BYTES)
            binary_digest = hashlib.sha256(raw).hexdigest()
            with tempfile.TemporaryDirectory(prefix='.controller-ready-', dir=state) as staged:
                staged = Path(staged)
                executable = staged / 'atelier-build-v2'
                with executable.open('xb') as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fchmod(stream.fileno(), 0o500)
                    os.fsync(stream.fileno())
                write_control(staged, 'controller.json', {'version': 1, 'source': captured.digest,
                                                         'binary': binary_digest})
                proof = ControllerExecutable(executable, captured.digest, binary_digest)
                with verified_controller(proof):
                    pass
                os.rename(staged, final)
                parent = _open_root(state, private=True)
                try:
                    os.fsync(parent)
                finally:
                    os.close(parent)
        return ControllerExecutable(final / 'atelier-build-v2', captured.digest, binary_digest)
    finally:
        os.close(lock)


def _probe_child(process):
    from atelier.harness.capacity_protocol import boot_id, process_start
    if process.poll() is not None:
        raise RuntimeError('controller exited before startup identity observation')
    started = process_start(process.pid)
    boot = boot_id()
    if process.poll() is not None or process_start(process.pid) != started:
        raise RuntimeError('controller changed during startup identity observation')
    return {'pid': process.pid, 'boot': boot, 'started': str(started)}


def _validated_report(raw, source, nonce):
    report = _json(raw)
    if (not isinstance(report, dict) or set(report) != {'version', 'nonce', 'controller_source', 'observation'}
            or type(report['version']) is not int or report['version'] != 1
            or report['nonce'] != nonce or report['controller_source'] != source):
        raise ValueError('controller report identity mismatch')
    observation = report['observation']
    fields = {'version', 'summary', 'io', 'final_requirements_satisfied', 'cancellation_requested',
              'scheduler_error', 'source_finalization', 'root_finalization'}
    if (not isinstance(observation, dict) or set(observation) != fields
            or type(observation['version']) is not int or observation['version'] != 1):
        raise ValueError('invalid controller observation')
    for flag in ('final_requirements_satisfied', 'cancellation_requested', 'scheduler_error'):
        if type(observation[flag]) is not bool:
            raise ValueError('invalid controller observation flag')
    if any(observation[key] not in ('not_opened', 'complete', 'incomplete')
           for key in ('source_finalization', 'root_finalization')):
        raise ValueError('invalid controller finalization observation')
    io = observation['io']
    counts = {'cache_opens', 'cache_lookups', 'staged_jobs', 'input_clones', 'observed_worker_attempts',
              'worker_files_written', 'publications', 'installs', 'receipt_writes'}
    if (not isinstance(io, dict) or set(io) != counts | {'worker_attempts_by_unit'}
            or any(type(io[key]) is not int or io[key] < 0 for key in counts)
            or not isinstance(io['worker_attempts_by_unit'], dict)
            or any(type(value) is not int or value < 0 for value in io['worker_attempts_by_unit'].values())):
        raise ValueError('invalid controller I/O observations')
    summary = observation['summary']
    if summary is not None and (not isinstance(summary, dict)
                               or set(summary) != {'units', 'counts', 'executor_fatal', 'effects_complete'}
                               or type(summary['executor_fatal']) is not bool
                               or type(summary['effects_complete']) is not bool
                               or not isinstance(summary['units'], list) or not isinstance(summary['counts'], dict)):
        raise ValueError('invalid controller scheduler summary')
    if observation['final_requirements_satisfied'] and (
            summary is None or summary['executor_fatal'] or observation['scheduler_error']):
        raise ValueError('controller report contradicts target fulfillment')
    return report


def invoke_controller(checkout, executable, marker, runs, execution, *, echo=print):
    """@cc [owner:fontanierh,label:safety] owned-controller-startup-cancellation
    Invocation MUST execute the verified immutable helper snapshot, pause it until
    the parent probes that exact live PID/start/boot and fsyncs its private bounded
    request/paired spawn receipt, then release only the owned startup pipe. Only the
    parent MUST own that pipe's write end; EOF and TERM MUST request ordinary C5c
    cancellation, never bypass cleanup or fabricate a successful/zero-I/O report.
    Source/provider/identity mismatch MUST fail before Run. Missing/partial reports
    MUST stay incomplete. Portable handshake negatives run on hosted Linux; actual
    worker cancellation/cleanup remains C5c/Q3 and normal I1-min proof pending.
    """
    if capture_controller(checkout).digest != executable.source:
        raise ValueError('controller source changed before invocation')
    execution = dict(execution)
    allowed = {'cache_root', 'interpreter', 'provenance', 'worktree_id', 'memory_gib',
               'job_seconds', 'cleanup_seconds', 'overall_seconds'}
    if set(execution) - {'blender', 'unreal', 'node', 'native_export_project', 'unreal_memory_gib', 'blender_memory_gib', 'unreal_job_seconds', 'ffmpeg', 'ffprobe'} != allowed:
        raise ValueError('invalid controller execution options')
    if 'blender' in execution and (not isinstance(execution['blender'], str) or not Path(execution['blender']).is_absolute()):
        raise ValueError('invalid Blender execution locator')
    for name in ('ffmpeg', 'ffprobe'):
        if name in execution and (not isinstance(execution[name], str) or not Path(execution[name]).is_absolute()):
            raise ValueError('invalid audio execution locator')
    if 'node' in execution and (not isinstance(execution['node'], str) or not Path(execution['node']).is_absolute()):
        raise ValueError('invalid Node execution locator')
    if 'native_export_project' in execution and (not isinstance(execution['native_export_project'], str) or not Path(execution['native_export_project']).is_absolute()):
        raise ValueError('invalid native export project locator')
    for name in ('unreal_memory_gib', 'blender_memory_gib', 'unreal_job_seconds'):
        if name in execution and (type(execution[name]) is not int or execution[name] <= 0):
            raise ValueError('invalid native execution resource')
    if 'unreal' in execution:
        native = execution['unreal']
        if (not isinstance(native, dict) or set(native) - {'engine_root', 'build_id', 'editor_binaries', 'modules', 'engine_plugins', 'plugins', 'config_sources'}
                or not {'engine_root', 'build_id', 'plugins'} <= set(native)
                or not isinstance(native['engine_root'], str) or not Path(native['engine_root']).is_absolute()
                or not isinstance(native['build_id'], str) or not native['build_id']):
            raise ValueError('invalid Unreal execution context')
        if native.get('editor_binaries') is not None and (not isinstance(native['editor_binaries'], str) or not Path(native['editor_binaries']).is_absolute()):
            raise ValueError('invalid native binary execution locator')
        for field in ('engine_plugins', 'plugins'):
            if (not isinstance(native.get(field, {}), dict)
                    or any(not isinstance(name, str) or not isinstance(path, str) or not Path(path).is_absolute()
                           for name, path in native.get(field, {}).items())):
                raise ValueError('invalid native plugin locations')
        if not isinstance(native.get('config_sources', {}), dict):
            raise ValueError('invalid native Config bindings')
        if (not isinstance(native.get('modules', []), list)
                or any(not isinstance(row, dict) or set(row) != {'name', 'kind', 'loading_phase'}
                       or any(not isinstance(v, str) for v in row.values()) for row in native.get('modules', []))):
            raise ValueError('invalid native module records')
    for key in ('memory_gib', 'job_seconds', 'cleanup_seconds', 'overall_seconds'):
        if type(execution[key]) is not int or not 0 < execution[key] < 2**32:
            raise ValueError('invalid controller execution bound')
    if execution['overall_seconds'] < execution['job_seconds'] + execution['cleanup_seconds']:
        raise ValueError('controller overall bound does not cover job and cleanup')
    for key in ('cache_root', 'interpreter'):
        if not isinstance(execution[key], str) or not Path(execution[key]).is_absolute():
            raise ValueError('controller execution locator must be absolute')
    request = marker.request(checkout)
    directory = _private_root(Path(runs) / uuid.uuid4().hex)
    nonce = directory.name
    root = _open_root(directory, private=True)
    descriptors = set()
    process = None
    cancelled = False
    sent = False
    released = False
    previous = {}

    def opened(name, flags):
        fd = os.open(name, flags | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=root)
        descriptors.add(fd)
        return fd

    def close(fd):
        if fd in descriptors:
            os.close(fd)
            descriptors.remove(fd)

    def stop(number, frame):
        nonlocal cancelled
        cancelled = True  # Normal control flow sends TERM and awaits the helper.

    def wait():
        nonlocal cancelled, sent
        began, heartbeat = time.monotonic(), time.monotonic()
        while process.poll() is None:
            if time.monotonic() - began > execution['overall_seconds'] + 30:
                cancelled = True
            if cancelled and not sent:
                try:
                    process.send_signal(signal.SIGTERM)
                except ProcessLookupError:
                    pass
                sent = True
            try:
                process.wait(timeout=.25)
            except subprocess.TimeoutExpired:
                pass
            if time.monotonic() - heartbeat >= 30:
                echo('Waiting for build controller cleanup' if cancelled else 'Waiting for build controller; no new progress observation')
                heartbeat = time.monotonic()
        return process.returncode

    try:
        request_write = opened('request.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        request_read = opened('request.json', os.O_RDONLY)
        report_write = opened('report.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        expected_report = os.fstat(report_write)
        live_read, live_write = os.pipe()
        descriptors.update((live_read, live_write))
        for fd in descriptors:
            os.set_inheritable(fd, False)
        for number in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
            previous[number] = signal.signal(number, stop)
        with verified_controller(executable) as binary:
            image = binary.stat(follow_symlinks=False)
            log = opened('controller.log', os.O_WRONLY | os.O_CREAT | os.O_EXCL)
            process = subprocess.Popen(
                [str(binary), '--request-fd', str(request_read), '--report-fd', str(report_write),
                 '--liveness-fd', str(live_read)], cwd=checkout, stdin=subprocess.DEVNULL,
                stdout=log, stderr=subprocess.STDOUT, close_fds=True,
                pass_fds=(request_read, report_write, live_read))
            for fd in (request_read, report_write, live_read, log):
                close(fd)
            try:
                owner = _probe_child(process)
                if (set(owner) != {'pid', 'boot', 'started'} or type(owner['pid']) is not int
                        or owner['pid'] != process.pid or not isinstance(owner['started'], str)
                        or not owner['started'].isascii() or not owner['started'].isdecimal()
                        or int(owner['started']) <= 0 or str(uuid.UUID(owner['boot'])) != owner['boot']):
                    raise ValueError('invalid controller startup identity provider')
                if _stamp(binary.stat(follow_symlinks=False)) != _stamp(image):
                    raise ValueError('private helper image changed during spawn')
                invocation = {'version': 1, 'nonce': nonce, 'controller_source': executable.source,
                              'request': request, 'execution': {**execution, 'owner': owner}}
                raw = json.dumps(invocation, allow_nan=False, separators=(',', ':')).encode()
                if len(raw) > MAX_CONTROL_BYTES:
                    raise ValueError('controller invocation exceeds its size bound')
                with os.fdopen(request_write, 'wb', closefd=False) as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                close(request_write)
                write_control(directory, 'spawn.json', {
                    'version': 1, 'nonce': nonce, 'controller_source': executable.source,
                    'binary_sha256': executable.binary, 'image_device': image.st_dev,
                    'image_inode': image.st_ino, 'image_size': image.st_size,
                    'child': owner, 'request_sha256': hashlib.sha256(raw).hexdigest()})
                if _probe_child(process) != owner or capture_controller(checkout).digest != executable.source:
                    raise ValueError('controller startup identity/source changed')
                if not cancelled:
                    if os.write(live_write, b'G') != 1:
                        raise RuntimeError('controller startup release was not delivered')
                    released = True
                else:
                    close(live_write)
                code = wait()
            except BaseException:
                cancelled = True
                close(live_write)
                code = wait()
                write_control(directory, 'client.json', {
                    'version': 1, 'state': 'incomplete', 'cancelled': True,
                    'gate_released': released, 'pid': process.pid, 'returncode': code})
                raise
        report = None
        try:
            fd = opened('report.json', os.O_RDONLY)
            actual = os.fstat(fd)
            if (actual.st_dev, actual.st_ino) != (expected_report.st_dev, expected_report.st_ino):
                raise ValueError('controller report identity changed')
            report = _validated_report(_read_descriptor(fd, MAX_CONTROL_BYTES, owned=True), executable.source, nonce)
        except (OSError, ValueError):
            pass  # Retain incomplete bytes and the paired spawn receipt; no guessed counters.
        result = {'state': 'observed' if report is not None and code == 0 else 'incomplete',
                  'cancelled': cancelled, 'returncode': code, 'report': report,
                  'diagnostic_log': str(directory / 'controller.log')}
        write_control(directory, 'client.json', {
            'version': 1, 'state': result['state'], 'cancelled': cancelled,
            'gate_released': released, 'returncode': code,
            'verified_report': report is not None})
        return result
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)
        for fd in list(descriptors):
            close(fd)
        os.close(root)
