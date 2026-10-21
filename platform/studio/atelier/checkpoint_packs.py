"""Bounded concurrent immutable pack storage, independent of checkpoint index releases."""
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from contextlib import contextmanager
import fcntl
import hashlib
import os
from pathlib import Path
import time

from . import build_products, paths, release
from .checkpoint_store import CheckpointError, identity

PART_BYTES = 100 * 1024**2
WORKERS = 6
VAULT_ASSETS = 900
VAULT_BODY = 'Immutable build cache packs; retain while referenced by a checkpoint index.'


@contextmanager
def local_writer(remote):
    """Serialize this machine's private metadata writers without holding the CAS/producer."""
    path = paths.cache_dir('checkpoints', 'writers') / (identity([remote.repository, remote.game]) + '.lock')
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    started = spoken = time.monotonic()
    try:
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if remote.github.stop.wait(1) or time.monotonic() - started >= 600:
                    raise CheckpointError('Private operation cancelled or timed out waiting for this machine writer')
                if time.monotonic() - spoken >= 25:
                    remote.echo(f'private cache: waiting for this machine writer; {time.monotonic() - started:.0f}s elapsed')
                    spoken = time.monotonic()
        yield
    finally:
        os.close(descriptor)


@contextmanager
def writer(remote):
    from .checkpoint_coordination import owned
    with local_writer(remote), owned(remote):
        yield


def upload(remote, item, path, digest, known):
    """Fresh POST responses verify success; ambiguous failures observe before bounded retry."""
    for attempt in range(release.ATTEMPTS):
        existing = known.get(path.name)
        if existing is not None:
            release.matches(existing, path, digest)
            return existing
        failure = None
        try:
            existing = remote.github.upload(item, path)
        except release.TransportError as error:
            failure = error
        if not isinstance(existing, dict):
            existing = release.asset_map(remote.github, item).get(path.name)
        if existing is not None:
            release.matches(existing, path, digest)
            return existing
        if failure is not None and not failure.retryable or attempt + 1 == release.ATTEMPTS:
            raise failure or CheckpointError('Pack upload was not remotely verified')
        remote.github.stop.wait(attempt + 1)
    raise CheckpointError('Pack upload failed')


class Spool:
    """@cc [owner:fontanierh,label:correctness] bounded-private-upload-spool
    Uploads MUST use at most six workers and 100 MiB new parts. Temporary payload bytes MUST be
    bounded by the active window and removed after verified completion. Existing packs MUST
    match remote size/digest; retries MUST NOT overwrite conflicts. Index publication MUST
    follow a fresh verification of every referenced pack, including reused older packs.
    """
    def __init__(self, remote, key, directory):
        self.remote, self.key, self.directory = remote, key, directory
        self.pool = ThreadPoolExecutor(max_workers=WORKERS)
        self.pending, self.vaults = {}, {}
        self.sequence = 0
        self.known = {}
        prefix = remote.game + '-cache-packs-' + key[:24] + '-'
        for page in remote.github.read('releases?per_page=100', pages=True):
            for item in page:
                if item.get('tag_name', '').startswith(prefix) and item.get('body') == VAULT_BODY:
                    self.vaults[item['id']] = item
                    for name, asset in release.asset_map(remote.github, item).items():
                        self.known[name] = (item['id'], asset)
        self.started = time.monotonic()
        self.completed = self.bytes = 0
        self.target = self.assets = None

    def vault(self):
        if self.target is not None and self.count < VAULT_ASSETS:
            return self.target, self.assets
        while True:
            tag = self.remote.game + '-cache-packs-' + self.key[:24] + '-' + str(self.sequence)
            self.sequence += 1
            item = release.find_release(self.remote.github, tag)
            metadata = dict(tag_name=tag, name=tag, body=VAULT_BODY, prerelease=False,
                            target_commitish=self.remote.default_branch)
            if item is None:
                item = self.remote.github.api('releases', method='POST', data={**metadata, 'draft': True})
            release.check_release(item, metadata)
            assets = release.asset_map(self.remote.github, item)
            if len(assets) > VAULT_ASSETS or any(not name.startswith('pack-') for name in assets):
                raise CheckpointError('Pack vault has unexpected assets')
            if len(assets) == VAULT_ASSETS:
                continue
            self.target, self.assets, self.count = item, assets, len(assets)
            self.vaults[item['id']] = item
            return item, assets

    def submit(self, path, digest):
        if path.name in self.known:
            identifier, asset = self.known[path.name]
            release.matches(asset, path, digest)
            path.unlink()
            return identifier
        while len(self.pending) >= WORKERS:
            self.drain()
        item, assets = self.vault()
        self.count += 1
        self.known[path.name] = (item['id'], dict(size=path.stat().st_size, state='uploaded', digest='sha256:' + digest))
        future = self.pool.submit(upload, self.remote, item, path, digest, assets)
        self.pending[future] = (path, item)
        return item['id']

    def drain(self):
        done, _ = wait(self.pending, timeout=10, return_when=FIRST_COMPLETED)
        for future in done:
            path, _ = self.pending.pop(future)
            try:
                result = future.result()
                self.bytes += result['size']; self.completed += 1
                elapsed = max(.001, time.monotonic() - self.started)
                self.remote.echo(f'private packs: {self.completed} verified, {self.bytes / 2**20:.1f} MiB; '
                                 f'{self.bytes / 2**20 / elapsed:.1f} MiB/s observed')
            finally:
                path.unlink(missing_ok=True)
        if not done and self.remote.github.stop.is_set():
            raise CheckpointError('Private upload cancelled')

    def close(self, *, failed=False):
        if failed:
            self.remote.github.stop.set()
        try:
            if not failed:
                while self.pending:
                    self.drain()
        finally:
            self.pool.shutdown(wait=True, cancel_futures=True)
            for path, _ in self.pending.values():
                path.unlink(missing_ok=True)
        if not failed:
            for item in self.vaults.values():
                if item['draft']:
                    self.remote.github.api(f'releases/{item["id"]}', method='PATCH', data={'draft': False})


def pack(remote, store, needed, known, directory, key, *, legacy=None):
    """Write complete ranges in deterministic blob order, retaining verified legacy draft packs."""
    from .checkpoint_github import PACK_BYTES
    blobs = {digest: known[digest] for digest in needed if digest in known}
    remaining = [(digest, size) for digest, size in sorted(needed.items()) if digest not in blobs]
    old_assets = release.asset_map(remote.github, legacy) if legacy else {}
    # Replay the old deterministic packing only while a legacy pack inventory exists. This
    # preserves already uploaded 128 MiB packs rather than uploading their bytes again.
    legacy_mode = bool(old_assets)
    spool = Spool(remote, key, directory)
    pending_parts, stream, hasher, number = [], None, None, 0
    def open_pack():
        nonlocal stream, hasher, number
        number += 1
        stream = (directory / ('pending-' + str(number))).open('wb')
        hasher = hashlib.sha256()
    def finish():
        nonlocal pending_parts, legacy_mode
        if not pending_parts:
            return
        stream.close()
        digest = hasher.hexdigest()
        path = Path(stream.name)
        final = path.with_name('pack-' + digest + '.bin')
        # Identical packs can appear more than once while an earlier copy is uploading.
        # Wait before sharing its content-addressed temporary name.
        if final.exists():
            while final.exists():
                spool.drain()
        path.rename(final)
        existing = old_assets.get(final.name) if legacy_mode else None
        if existing is not None:
            release.matches(existing, final, digest)
            identifier = legacy['id']; final.unlink()
            remote.echo('private packs: retained verified legacy pack')
        else:
            if legacy_mode:
                # First missing legacy-sized pack is split into new bounded parts below.
                legacy_mode = False
                with final.open('rb') as source:
                    offset = 0
                    while offset < final.stat().st_size or offset == 0:
                        raw = source.read(min(PART_BYTES, PACK_BYTES))
                        sub_digest = hashlib.sha256(raw).hexdigest()
                        part = directory / ('pack-' + sub_digest + '.bin')
                        while part.exists() and part != final:
                            spool.drain()
                        if part == final:
                            identifier = spool.submit(final, digest)
                        else:
                            part.write_bytes(raw)
                            identifier = spool.submit(part, sub_digest)
                        for blob, start, size in pending_parts:
                            left, right = max(start, offset), min(start + size, offset + len(raw))
                            if right > left or size == 0 and start == offset:
                                blobs[blob].append(dict(release=identifier, pack=sub_digest,
                                                        offset=left - offset, size=right - left))
                        offset += len(raw)
                        if not raw or part == final:
                            break
                if final.exists() and final not in [p for p, _ in spool.pending.values()]:
                    final.unlink()
                pending_parts = []
                return
            identifier = spool.submit(final, digest)
        for blob, offset, size in pending_parts:
            blobs[blob].append(dict(release=identifier, pack=digest, offset=offset, size=size))
        pending_parts = []
    open_pack()
    try:
        for digest, size in remaining:
            blobs[digest] = []
            source = store.blob(digest)
            if source.is_symlink() or source.stat().st_size != size or build_products.file_digest(source) != digest:
                raise CheckpointError('Local checkpoint blob changed before upload')
            with source.open('rb') as input_:
                left = size
                while left or not blobs[digest] and not any(p[0] == digest for p in pending_parts):
                    limit = PACK_BYTES if legacy_mode else min(PART_BYTES, PACK_BYTES)
                    room = limit - stream.tell()
                    if not room:
                        finish(); open_pack()
                        limit = PACK_BYTES if legacy_mode else min(PART_BYTES, PACK_BYTES)
                        room = limit
                    offset, length = stream.tell(), min(left, room)
                    remaining_bytes = length
                    while remaining_bytes:
                        block = input_.read(min(remaining_bytes, 1024**2))
                        if not block:
                            raise CheckpointError('Local checkpoint blob was truncated')
                        stream.write(block); hasher.update(block); remaining_bytes -= len(block)
                    pending_parts.append((digest, offset, length)); left -= length
                    if not left:
                        break
            if stream.tell() == (PACK_BYTES if legacy_mode else min(PART_BYTES, PACK_BYTES)):
                finish(); open_pack()
        finish()
        spool.close()
    except BaseException:
        spool.close(failed=True)
        raise
    finally:
        stream.close()
    return blobs
