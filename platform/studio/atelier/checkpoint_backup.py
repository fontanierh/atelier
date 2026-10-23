"""Durable asynchronous private backups of already retained immutable checkpoints.

Workers never visit the producing checkout. A public release can succeed independently;
failed/interrupted backups remain pinned and resume through the ordinary publisher.
"""
from contextlib import contextmanager
import fcntl
import hashlib
import io
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time
import zipfile

from . import paths, release
from .atomic_files import atomic_json
from .checkpoint_store import Store, CheckpointError, identity, read_json


def save(path, value):
    atomic_json(path, value)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def record_path(store, tag):
    release.leaf(tag)
    return store.directory / 'backups' / (identity(tag) + '.json')


def queue(store, repository, key, tag, revision, *, public_repository):
    """@cc [owner:fontanierh,label:correctness] durable-private-backup-request
    A backup MUST bind an existing immutable local manifest, private destination, release tag
    and full source revision before public publication. Pending/failed records and their blobs
    MUST remain retention roots. Workers MUST NOT read or hold the producing checkout.
    """
    manifest = store.load(key)
    if manifest.get('source_revision', revision) != revision:
        raise CheckpointError('Captured checkpoint source differs from the backup request')
    if not re.fullmatch('[0-9a-f]{40}', revision):
        raise CheckpointError('Backup source revision must be a full Git SHA')
    from .checkpoint_github import Remote
    Remote(repository, store.game)
    Remote(public_repository, store.game)  # Repository syntax only; public destination stays separate.
    expected = dict(schema=1, game=store.game, repository=repository, key=key, tag=tag,
                    revision=revision, public_repository=public_repository)
    target = record_path(store, tag)
    try:
        with locked(target, blocking=False):
            if not target.exists():
                save(target, dict(**expected, state='waiting-public', attempts=0))
    except BlockingIOError:
        pass  # An active worker owns state updates; immutable request fields can still be read.
    if target.exists():
        value = read_json(target)
        if not isinstance(value, dict) or any(value.get(k) != v for k, v in expected.items()):
            raise CheckpointError('Pending private backup differs; preserve the original request')
    else:
        raise CheckpointError('Private backup request is not durably retained')
    return target


@contextmanager
def locked(target, *, blocking=True):
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(target.with_suffix('.lock'), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        yield
    finally:
        os.close(descriptor)


def start(target, *, echo=print):
    """Only call after observed public success. Spawn failure never changes that success."""
    try:
        with locked(target, blocking=False):
            record = read_json(target)
            if record.get('state') == 'complete':
                return
            record['state'] = 'pending'
            save(target, record)
        log = target.with_suffix('.log')
        runtime = snapshot_runtime(target.parent)
        bootstrap = ('import hashlib,pathlib,runpy,sys; p=pathlib.Path(sys.argv.pop(1)); '
                     'assert hashlib.sha256(p.read_bytes()).hexdigest()==p.stem.removeprefix("runtime-"); '
                     'sys.path.insert(0,str(p)); runpy.run_module("atelier.checkpoint_backup",run_name="__main__")')
        with log.open('ab') as stream:
            subprocess.Popen([sys.executable, '-I', '-S', '-u', '-c', bootstrap, str(runtime), str(target)],
                             stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT,
                             start_new_session=True, close_fds=True, cwd=target.parent)
        echo('Private checkpoint backup queued; public release is ready. Inspect `atelier cache status` for backup state.')
    except BlockingIOError:
        echo('Private checkpoint backup is already active; public release is ready.')
    except (OSError, ValueError, RuntimeError):
        echo('Public release is ready; private backup remains pending. Rerun the same publish command to resume.')


def snapshot_runtime(directory):
    """Freeze the standard-library upload runtime so checkout changes cannot break a detached worker."""
    modules = ('__init__', 'checkpoint_backup', 'checkpoint_github', 'checkpoint_store', 'checkpoint_actions',
               'checkpoint_packs', 'checkpoint_archive', 'checkpoint_coordination', 'checkpoint_pins', 'checkpoint_gc', 'native_protocol', 'atomic_files', 'build_cache',
               'build_products', 'build_hashes', 'file_identity', 'file_copy',
               'engine', 'paths', 'release', 'release_claim', 'playtest', 'manifest')
    source = Path(__file__).parent
    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name in modules:
            archive.writestr(zipfile.ZipInfo('atelier/' + name + '.py'), (source / (name + '.py')).read_bytes())
    raw = data.getvalue()
    target = directory / ('runtime-' + hashlib.sha256(raw).hexdigest() + '.zip')
    if not target.exists():
        temporary = target.with_suffix('.' + os.urandom(8).hex() + '.tmp')
        try:
            descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(raw); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
    if target.is_symlink() or hashlib.sha256(target.read_bytes()).hexdigest() != hashlib.sha256(raw).hexdigest():
        raise CheckpointError('Detached upload runtime changed')
    return target


def pending():
    root = paths.cache_dir('checkpoints', 'v1', create=False)
    result = []
    for target in sorted(root.glob('*/backups/*.json')):
        try:
            value = read_json(target)
            result.append(dict(game=value['game'], tag=value['tag'], checkpoint=value['key'],
                               state=value['state'], attempts=value.get('attempts', 0)))
        except (OSError, ValueError, KeyError, TypeError):
            result.append(dict(state='invalid-preserved', record=target.name))
    return result


def run(target):
    """A bounded detached process; a persistent request survives crashes and transport failures."""
    target = Path(target).resolve()
    try:
        with locked(target, blocking=False):
            record = read_json(target)
            store = Store(record['game'], target.parent.parent)
            if record_path(store, record['tag']) != target or record.get('schema') != 1:
                raise CheckpointError('Invalid private backup request location')
            if record.get('state') == 'complete':
                return 0
            if record.get('state') not in ('pending', 'uploading', 'failed'):
                raise CheckpointError('Public release has not completed for this backup')
            record.update(state='uploading', attempts=record.get('attempts', 0) + 1)
            save(target, record)
            from .checkpoint_github import Remote
            remote = Remote(record['repository'], record['game'])
            deadline = threading.Timer(3 * 3600, remote.github.stop.set)
            deadline.daemon = True; deadline.start()
            stopped = threading.Event()
            started = time.monotonic()
            def heartbeat():
                while not stopped.wait(25):
                    print(f'private backup active: {time.monotonic() - started:.0f}s elapsed; '
                          'waiting for verified upload completion; progress is recorded below', flush=True)
            monitor = threading.Thread(target=heartbeat, daemon=True); monitor.start()
            try:
                # The key is immutable and pins CAS bytes. No source checkout access/revalidation.
                remote.publish(store, record['key'], record['tag'], revision=record['revision'],
                               revalidate=lambda: store.load(record['key']))
                record.update(state='complete', completed=time.time())
                save(target, record)
                return 0
            except (KeyboardInterrupt, OSError, ValueError, RuntimeError, release.PublishError):
                remote.github.stop.set()
                record.update(state='failed', failed=time.time())
                save(target, record)
                print('Private backup failed; retained manifest, blobs and remote packs remain resumable.', flush=True)
                return 1
            finally:
                stopped.set(); deadline.cancel()
    except BlockingIOError:
        return 0


def resume(game, key, tag, revision, public_repository, *, echo=print):
    """Recover an interrupted backup without recapture or producer access."""
    from .checkpoint_github import Remote
    settings = paths.cache_dir('checkpoints', create=False) / 'settings.json'
    repository = read_json(settings).get('repository')
    remote = Remote(repository, game)
    metadata = remote.require_private()
    found = release.find_release(remote.github, remote.prefix + release.leaf(tag))
    expected = dict(tag_name=remote.prefix + tag, name=remote.prefix + tag,
        body=f'Build checkpoint {key}\nSource {revision}\nRetain this release: later checkpoints may reference its packs.',
        prerelease=False, target_commitish=metadata['default_branch'])
    store = Store(game)
    if found is None:
        # A worker can fail before its first private release exists. Only an already
        # durable, exactly bound local request authorizes this no-draft recovery path.
        target = record_path(store, tag)
        value = read_json(target) if target.exists() else None
        bindings = dict(schema=1, game=game, repository=repository, key=key, tag=tag,
                        revision=revision, public_repository=public_repository)
        if type(value) is not dict or any(value.get(k) != v for k, v in bindings.items()):
            raise CheckpointError('No matching retained backup request or private release')
    else:
        release.check_release(found, expected)
    public = release.GitHub(public_repository, threading.Event())
    published = release.find_release(public, tag)
    if published is None or published.get('draft') is not False:
        raise CheckpointError('Verified public release is not published yet')
    release.check_tag(public, tag, revision, required=True)
    assets = release.asset_map(public, published)
    if not {'SHA256SUMS', 'manifest.json', 'verification.json'} <= assets.keys():
        raise CheckpointError('Published release lacks readiness/verification assets')
    target = queue(store, repository, key, tag, revision, public_repository=public_repository)
    start(target, echo=echo)
    return dict(queued=True, checkpoint=key)


if __name__ == '__main__':
    def cancel(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, cancel)
    raise SystemExit(run(sys.argv[1]))
