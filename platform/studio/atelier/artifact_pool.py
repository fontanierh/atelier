"""Local, immutable portable outputs; explicit ownership, fresh build provenance and full file hashes.

Unreal assets/binaries and dependent steps stay on the strict whole-build reuse path.
"""
import ctypes
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import tempfile

from . import paths
from .build import Context, Python, fingerprint, load_recipe, order
from .reuse import copy_tree
from .safety.render_lock import render_lock


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def roots(ctx, step):
    if not step.pool_roots or step.needs or any(type(c) is not Python for c in step.commands):
        raise ValueError('Pool requires explicitly owned folders and independent Python commands')
    if os.environ.get('ATELIER_PYTHON') or os.environ.get('ATELIER_BUILD_ROOT'):
        raise ValueError('Pool requires the default interpreter and per-checkout build root')
    result = []
    base = ctx.out.resolve()
    for item in step.pool_roots:
        item = Path(item)
        relative = item.resolve().relative_to(base)
        if not relative.parts or relative.parts[0] in ('logs', 'stamps'):
            raise ValueError('Pool roots must be exclusively owned generated subfolders')
        if any(part in ('Content', 'Binaries', 'Intermediate') for part in relative.parts):
            raise ValueError('Mutable Unreal outputs are not portable pool roots')
        result.append(relative)
    if any(a == b or a in b.parents or b in a.parents for i, a in enumerate(result) for b in result[i+1:]):
        raise ValueError('Pool roots overlap')
    for output in step.outputs:
        relative = Path(output).resolve().relative_to(base)
        if not any(relative == root or root in relative.parents for root in result):
            raise ValueError('Every required output must belong to a pool root')
    return result


def key(ctx, step, source_fingerprint):
    owned = roots(ctx, step)
    # Hash local runtime support and dependency lock, not whole game HEAD: unrelated feature edits can hit.
    support = {str(p.relative_to(paths.STUDIO)): digest(p)
               for p in sorted((paths.STUDIO / 'atelier').rglob('*.py'))}
    context = dict(schema=1, game=ctx.game, step=step.name, fingerprint=source_fingerprint,
                   roots=[str(p) for p in owned], system=platform.system(), machine=platform.machine(),
                   python=sys.version, interpreter=digest(sys.executable), support=support,
                   lock=digest(paths.REPO / 'uv.lock'),
                   packages=sorted((d.metadata["Name"], d.version) for d in importlib.metadata.distributions()))
    return hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest()


def inventory(base, owned):
    result = {}
    for root in owned:
        folder = base / root
        if not folder.is_dir() or folder.is_symlink():
            raise ValueError(f'Missing regular pool folder: {root}')
        for item in sorted(folder.rglob('*')):
            if item.is_symlink():
                raise ValueError('Pool outputs must not contain symlinks')
            if item.is_file():
                result[str(item.relative_to(base))] = digest(item)
    if not result:
        raise ValueError('Pool outputs are empty')
    return result


def clone_function():
    if sys.platform != 'darwin':
        return None
    fn = ctypes.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True).clonefile
    fn.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    fn.restype = ctypes.c_int
    return fn


def transfer(action, ctx, step, current, pool):
    owned = roots(ctx, step)
    identity = key(ctx, step, current)
    entry = pool / identity
    stamp_path = ctx.stamps / (step.name + '.json')
    if action == 'publish':
        stamp = json.loads(stamp_path.read_text())
        if stamp.get('fingerprint') != current or stamp.get('pool_key') != identity or stamp.get('touched'):
            raise ValueError('Requires a fresh successful build with matching pool context; legacy/touched stamps refused')
        before = inventory(ctx.out, owned)
        pool.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=pool, prefix='.publish-') as name:
            staging = Path(name) / 'entry';staging.mkdir()
            for root in owned:
                copy_tree(ctx.out / root, staging / 'outputs' / root, paths.REPO, paths.REPO, clone_function())
            if inventory(staging / 'outputs', owned) != before or inventory(ctx.out, owned) != before:
                raise ValueError('Output files changed during publication')
            (staging / 'manifest.json').write_text(json.dumps(dict(key=identity, files=before, stamp=stamp), sort_keys=True)+'\n')
            if entry.exists():
                existing = json.loads((entry / 'manifest.json').read_text())
                if existing['files'] != before or inventory(entry / 'outputs', owned) != before:
                    raise ValueError('Same key produced different bytes; cache entry remains unchanged')
            else:
                staging.rename(entry)
        return identity
    if not entry.exists():
        raise ValueError('Pool miss: no successful output with this source/tool context')
    manifest = json.loads((entry / 'manifest.json').read_text())
    if (manifest.get('key') != identity or manifest['stamp'].get('pool_key') != identity
            or manifest['stamp'].get('fingerprint') != current or manifest['stamp'].get('touched')
            or inventory(entry / 'outputs', owned) != manifest['files']):
        raise ValueError('Pool manifest or output hashes differ; refusing restore')
    # Verify everything before mutation; remove the old stamp before replacing files so interruption cannot certify.
    stamp_path.unlink(missing_ok=True)
    for root in owned:
        destination = ctx.out / root
        if destination.exists():
            shutil.rmtree(destination)
        copy_tree(entry / 'outputs' / root, destination, paths.REPO, paths.REPO, clone_function())
    if inventory(ctx.out, owned) != manifest['files'] or not all(Path(o).is_file() for o in step.outputs):
        raise ValueError('Restored outputs differ; no stamp created')
    ctx.stamps.mkdir(parents=True, exist_ok=True)
    stamp = dict(manifest['stamp'], pooled_from=identity)
    temporary = stamp_path.with_suffix('.tmp')
    temporary.write_text(json.dumps(stamp)+'\n');temporary.replace(stamp_path)
    return identity


def main(action, game, name):
    ctx = Context(game);done = {};target = None
    for step in order(load_recipe(game).steps(ctx), []):
        current = fingerprint(step, done);done[step.name] = current
        if step.name == name:
            target = (step, current)
    if target is None:
        raise ValueError(f'Unknown step: {name}')
    step, current = target
    identity = key(ctx, step, current)
    pool = paths.cache_dir('artifact-pool', 'v1')
    if action == 'status':
        print(f'{name}: {"hit" if (pool / identity).exists() else "miss"} {identity}')
        return 0
    # File replacement is bounded actual work and cannot overlap a builder in this checkout.
    with render_lock(f'artifact pool {action} {name}'):
        before = key(ctx, step, current)
        result = transfer(action, ctx, step, current, pool)
        fresh = {};now = None
        for item in order(load_recipe(game).steps(ctx), []):
            value = fingerprint(item, fresh);fresh[item.name] = value
            if item.name == name:now = key(ctx, item, value)
        if now != before:
            if action == 'restore': (ctx.stamps / (name + '.json')).unlink(missing_ok=True)
            raise ValueError('Source context changed during transfer')
    print(f'{action} {name}: {result}; independent copies, full file hashes verified')
    return 0
