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
import tempfile
import uuid

MAX_CONTROL_BYTES = 2 * 1024 * 1024
MAX_SOURCE_FILE_BYTES = 8 * 1024 * 1024
MAX_SOURCE_TOTAL_BYTES = 32 * 1024 * 1024
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
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or not 0 <= before.st_size <= bound:
            raise ValueError('controller file is not regular or exceeds its size bound')
        if owned and (before.st_uid != os.getuid() or before.st_mode & 0o077):
            raise ValueError('controller control file must be private and owned')
        chunks, size = [], 0
        while chunk := os.read(descriptor, min(1024**2, bound + 1 - size)):
            chunks.append(chunk)
            size += len(chunk)
            if size > bound:
                raise ValueError('controller file grew beyond its size bound')
        if _stamp(before) != _stamp(os.fstat(descriptor)) or size != before.st_size:
            raise ValueError('controller file changed during capture')
        return b''.join(chunks)
    finally:
        os.close(descriptor)


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
    digest = hashlib.sha256()
    for name, content in sorted(files):
        encoded = name.encode()
        digest.update(len(encoded).to_bytes(8, 'big'))
        digest.update(encoded)
        digest.update(len(content).to_bytes(8, 'big'))
        digest.update(content)
    return ControllerSource(digest.hexdigest(), tuple(files))


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
