"""Recover stable pre-capture stamp evidence; never inspect or copy live native outputs."""
import hashlib
import json
import os
from pathlib import Path
import stat
import time

from .build_hashes import signature
from .native_candidates import original, task_name
from .native_protocol import CheckpointError, HEX, ReadStore, atomic_json, identity, safe_destination, validate


def recover(game, checkpoint, source, tasks, *, before_ns):
    """@cc [owner:fontanierh,label:correctness] recover-only-original-stable-history
    Recovery MAY read only explicitly selected original task stamp files with producer-owner
    permission. Every stamp's ctime and mtime MUST predate the specified pre-capture boundary;
    descriptor/path metadata MUST stay identical across reading. The boundary MUST predate the
    existing immutable catalogue. Invalid or rewritten evidence MUST be a miss. Recovery MUST
    write only a derived compatibility catalogue outside the producer, never producer metadata,
    output bytes, a receiving stamp or an action certificate. Native source/policy/package
    validation remains mandatory. This small metadata read MUST NOT reserve native capacity.
    """
    task_name(game)
    source = Path(source).absolute()
    store = ReadStore(game)
    saved = original(store, checkpoint)
    if identity(str(source.resolve())) != saved['checkout']:
        raise CheckpointError('Historical stamp source differs from the captured producer')
    manifests = [store.manifests / (checkpoint + '.json'), store.directory / 'candidate-sources' / (checkpoint + '.json')]
    origin = next((p for p in manifests if p.is_file() and not p.is_symlink()), None)
    if (type(before_ns) is not int or before_ns <= 0 or origin is None
            or before_ns >= min(origin.stat().st_mtime_ns, time.time_ns())):
        raise CheckpointError('History boundary must precede the retained catalogue')
    records, observations, misses = {}, {}, {}
    for task in sorted(set(tasks)):
        task_name(task)
        try:
            if task not in saved['steps']:
                raise ValueError('task absent from original recipe')
            path = safe_destination(source, 'build/' + game + '/stamps/' + task + '.json')
            before = path.lstat()
            if (not stat.S_ISREG(before.st_mode) or before.st_size > 16 * 1024**2
                    or max(before.st_ctime_ns, before.st_mtime_ns) >= before_ns):
                raise ValueError('stamp missing, linked, oversized or rewritten after boundary')
            with path.open('rb') as stream:
                if signature(os.fstat(stream.fileno())) != signature(before):
                    raise ValueError('stamp changed before read')
                data = stream.read()
                if signature(os.fstat(stream.fileno())) != signature(before):
                    raise ValueError('stamp changed during read')
            if signature(path.lstat()) != signature(before):
                raise ValueError('stamp changed after read')
            value = json.loads(data)
            if (not isinstance(value, dict) or value.get('touched')
                    or not isinstance(value.get('fingerprint'), str) or not HEX.fullmatch(value['fingerprint'])
                    or not isinstance(value.get('input_state'), dict)
                    or not isinstance(value['input_state'].get('inputs'), dict)
                    or type(value.get('time')) not in (int, float) or not 0 < value['time'] * 1e9 < before_ns):
                raise ValueError('stamp lacks original successful task input evidence')
            records[task] = value
            observations[task] = dict(sha256=hashlib.sha256(data).hexdigest(),
                mtime_ns=before.st_mtime_ns, ctime_ns=before.st_ctime_ns, size=before.st_size)
        except (OSError, ValueError, TypeError, KeyError) as error:
            misses[task] = str(error)
    if not records:
        return dict(checkpoint=checkpoint, recovered=[], missed=misses)
    # Preserve the original catalogue and successful entries exactly. Original evidence that
    # already exists must agree; never replace a different historical record.
    all_saved = {**saved['stamps'], **saved.get('incremental_stamps', {}), **saved.get('historical_stamps', {})}
    if any(task in all_saved and all_saved[task] != value for task, value in records.items()):
        raise CheckpointError('Original retained task evidence conflicts with recovered history')
    history = {**saved.get('historical_stamps', {}), **{k: v for k, v in records.items() if k not in all_saved}}
    derived = dict(saved, historical_stamps=history,
        recovered_history=dict(parent=checkpoint, before_ns=before_ns, observations=observations))
    validate(derived, game)
    key = identity(derived)
    atomic_json(store.directory / 'candidate-sources' / (key + '.json'), derived)
    return dict(checkpoint=key, recovered=sorted(records), missed=misses)
