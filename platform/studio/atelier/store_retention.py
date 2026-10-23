"""Bounded local checkpoint store: least recently used entries go first.

Pinned, backed-up, recent and workspace-referenced manifests stay. Blobs are deleted only when
no remaining manifest or task entry references them, and only under the store lock that
publication also holds, so an entry is never written against a deleted blob.
"""
import json
import os
from pathlib import Path
import time

from .native_protocol import CheckpointError, HEX, read_json

DEFAULT_BUDGET_GIB = 200
INTERVAL_SECONDS = 6 * 3600
KEEP_RECENT = 4
WORKSPACE_DAYS = 14


def touch(store, key):
    """Record a reuse hit for LRU ordering; never changes a manifest or entry."""
    try:
        marker = store.directory / 'used' / key
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
    except OSError:
        pass


def budget_bytes(store):
    settings = store.directory.parent.parent / 'settings.json'
    try:
        value = read_json(settings).get('local_budget_gib', DEFAULT_BUDGET_GIB) if settings.is_file() else DEFAULT_BUDGET_GIB
    except (OSError, ValueError, CheckpointError):
        value = DEFAULT_BUDGET_GIB
    return int(value * 2**30) if type(value) in (int, float) and value > 0 else DEFAULT_BUDGET_GIB * 2**30


def _used(store, path):
    marker = store.directory / 'used' / path.stem
    times = [path.stat().st_mtime]
    if marker.exists():
        times.append(marker.stat().st_mtime)
    return max(times)


def _blobs(value):
    files = dict(value.get('files', {}))
    for action in value.get('actions', {}).values():
        files.update(action.get('files', {}))
    return {e['sha256'] for e in files.values() if e.get('kind') == 'file' and HEX.fullmatch(e.get('sha256', ''))}


def collect(store, *, budget=None, now=None, min_age=3600, echo=print):
    """@cc [owner:fontanierh,label:safety] local-store-retention
    Collection MUST hold the store lock, MUST keep pinned, backed-up, recent and in-use
    manifests, and MUST delete a blob only when no remaining manifest or task entry references it.
    Blobs younger than min_age MUST stay, so a concurrent unlocked writer cannot lose bytes.
    """
    now = time.time() if now is None else now
    budget = budget_bytes(store) if budget is None else budget
    with store.locked():
        sizes = {}
        for entry in os.scandir(store.blobs) if store.blobs.is_dir() else ():
            if HEX.fullmatch(entry.name):
                info = entry.stat(follow_symlinks=False)
                sizes[entry.name] = (info.st_size, info.st_mtime)
        total = sum(size for size, _ in sizes.values())
        if total <= budget:
            return dict(total=total, budget=budget, removed_entries=0, removed_blobs=0, freed=0)
        protected = set()
        for record in store.directory.glob('pins/*.json'):
            protected |= set(read_json(record).get('checkpoints', []))
        for record in store.directory.glob('backups/*.json'):
            protected.add(read_json(record).get('key'))
        for pointer in store.directory.glob('workspaces/*.json'):
            if now - pointer.stat().st_mtime < WORKSPACE_DAYS * 86400:
                protected.add(read_json(pointer).get('key'))
        manifests = sorted(store.manifests.glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True)
        protected |= {p.stem for p in manifests[:KEEP_RECENT]}
        entries = []
        for path in [*manifests, *sorted((store.directory / 'actions').glob('*.json'))]:
            try:
                value = json.loads(path.read_bytes())
            except (OSError, ValueError):
                continue
            entries.append((_used(store, path), path, _blobs(value), path.parent.name == 'manifests' and path.stem in protected))
        live = {}
        for _, path, blobs, _ in entries:
            for digest in blobs:
                live[digest] = live.get(digest, 0) + 1
        removed, freed = 0, 0
        def unreferenced(blobs):
            return sum(sizes[d][0] for d in blobs if live.get(d) == 1 and d in sizes)
        for used, path, blobs, keep in sorted(entries, key=lambda e: e[0]):
            if total - freed <= budget:
                break
            if keep or now - used < min_age:
                continue
            gain = unreferenced(blobs)
            path.unlink(missing_ok=True)
            path.with_suffix('.conflict').unlink(missing_ok=True)
            (store.directory / 'index' / path.name).unlink(missing_ok=True)
            removed += 1
            for digest in blobs:
                live[digest] -= 1
            freed += gain
        deleted = 0
        for digest, (size, mtime) in sizes.items():
            if live.get(digest, 0) <= 0 and now - mtime >= min_age:
                store.blob(digest).unlink(missing_ok=True)
                deleted += 1
        echo(f'checkpoint store retention: {removed} entries and {deleted} blobs removed, '
             f'{freed / 2**30:.1f} GiB freed of {total / 2**30:.1f} GiB (budget {budget / 2**30:.0f} GiB)')
        return dict(total=total, budget=budget, removed_entries=removed, removed_blobs=deleted, freed=freed)


def maybe_collect(store, *, echo=print):
    """At most once per interval per store; never fails the caller."""
    marker = store.directory / 'retention.json'
    try:
        if marker.is_file() and time.time() - marker.stat().st_mtime < INTERVAL_SECONDS:
            return None
        marker.write_text(json.dumps(dict(started=time.time())) + '\n')
        return collect(store, echo=echo)
    except (OSError, ValueError, KeyError, TypeError, CheckpointError) as error:
        echo(f'checkpoint store retention skipped ({error})')
        return None
