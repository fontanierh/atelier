"""Automatic local reuse of explicitly portable products, with verified independent copies.

Only generated files under the game's build folder are eligible. Unreal packages, binaries and
mutable engine state require a different relocation protocol and cannot enter this store.
"""
import ctypes
from contextlib import contextmanager
import fcntl
from functools import cache
import importlib.metadata
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import sys
import tempfile

from . import build_products, paths

SCHEMA = 1
DIGEST = re.compile(r'[0-9a-f]{64}')
NATIVE_SUFFIXES = {'.uasset', '.umap', '.uexp', '.ubulk', '.dylib', '.dll', '.so'}


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, prefix='.write-', delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(value, stream, sort_keys=True)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


@cache
def clone_function():
    clone = ctypes.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True).clonefile
    clone.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    clone.restype = ctypes.c_int
    return clone


def copy_file(source, destination):
    """An APFS clone when available, otherwise a byte copy. Never a mutable hard/symbolic link."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform == 'darwin':
        if clone_function()(os.fsencode(source), os.fsencode(destination), 0) == 0:
            destination.chmod(0o644)
            return
    shutil.copyfile(source, destination)
    destination.chmod(0o644)


def roots(ctx, step):
    """Validate declarations before reading cache state or changing a checkout."""
    from .build import Blender, Python
    if not step.products or not step.commands or any(type(c) not in (Python, Blender) for c in step.commands):
        raise ValueError(f'{step.name}: portable caching requires products and Python/Blender commands')
    if step.pool_roots or step.cutoff:
        raise ValueError(f'{step.name}: portable products cannot use legacy pool/cutoff protocols')
    base = ctx.out.resolve()
    result = []
    for product in step.products:
        if product.optional_paths:
            raise ValueError('Optional package sidecars are not eligible for the portable cache')
        for root in product.paths:
            root = Path(root)
            # Resolve only the base: a symlink inside the owned tree must never redirect installation.
            relative = Path(os.path.abspath(root)).relative_to(Path(os.path.abspath(ctx.out)))
            if not relative.parts or relative.parts[0] in ('logs', 'stamps', '.state'):
                raise ValueError('Cached products require an owned generated subpath')
            if any(part in ('Content', 'Binaries', 'Intermediate') or part.startswith('.env') for part in relative.parts):
                raise ValueError('Native state and credential files are not portable products')
            if relative.suffix.lower() in NATIVE_SUFFIXES:
                raise ValueError('Native files are not portable products')
            target = base
            for part in relative.parts:
                target /= part
                if target.is_symlink():
                    raise ValueError(f'Linked cache destination: {root}')
            result.append(relative)
    for output in step.outputs:
        relative = Path(os.path.abspath(output)).relative_to(Path(os.path.abspath(ctx.out)))
        if not any(relative == root or root in relative.parents for root in result):
            raise ValueError(f'{step.name}: required output has no product owner: {output}')
    return result


def tool_context(step, hasher, *, cache=None):
    """Installed tool identity, never a process launch. Tools must stay fixed during an invocation.

    Enumerate packages/app resources once per invocation. Binary changes invalidate that memo;
    a new invocation rediscovers all resources, using the persistent file-hash hints individually.
    """
    from . import build, engine
    kinds = {type(c) for c in step.commands}
    if kinds - {build.Python, build.Blender}:
        raise ValueError('Only Python/Blender source products have a portable tool context')
    context = {'schema': SCHEMA, 'system': platform.system(), 'machine': platform.machine(),
               'lock': hasher(paths.REPO / 'uv.lock'),
               'support': {name: hasher(Path(__file__).with_name(name)) for name in
                           ('build.py', 'build_inputs.py', 'build_products.py', 'build_cache.py', 'build_hashes.py', 'paths.py')}}
    cache = {} if cache is None else cache
    if build.Python in kinds:
        if os.environ.get('ATELIER_PYTHON') or os.environ.get('PYTHONPATH') or os.environ.get('PYTHONHOME'):
            raise ValueError('Portable Python actions require the managed interpreter without path overrides')
        binary = Path(sys.executable).resolve()
        key = ('python', binary, hasher(binary), context['lock'])
        if key not in cache:
            cache[key] = {'version': sys.version, 'binary': key[2],
                          'packages': sorted((d.metadata['Name'], d.version)
                                             for d in importlib.metadata.distributions())}
        context['python'] = cache[key]
    if build.Blender in kinds:
        if any(not c.factory_startup for c in step.commands if isinstance(c, build.Blender)):
            raise ValueError('Cached Blender commands must use factory_startup=True')
        binary = Path(engine.blender()).resolve()
        # The app includes Python, numpy, FBX exporter and dynamic libraries, not just the executable.
        bundle = binary.parent.parent
        if binary.parent.name != 'MacOS' or bundle.name != 'Contents':
            raise ValueError('Portable Blender caching currently requires the complete macOS app bundle')
        key = ('blender', binary, hasher(binary), bundle.stat().st_mtime_ns)
        if key not in cache:
            files = sorted(p for p in bundle.rglob('*') if p.is_file() and '__pycache__' not in p.parts)
            # rglob supplies lexical descendants of this root; no resolution is needed for their keys.
            depth = len(bundle.parts)
            cache[key] = {'/'.join(p.parts[depth:]): hasher(p) for p in files}
        context['blender'] = cache[key]
    return context


def members(manifest, count):
    """Decode inventory paths without trusting any persisted path as an installation destination."""
    if not isinstance(manifest, dict) or manifest.get('schema') != 1 or not isinstance(manifest.get('files'), dict):
        raise ValueError('Invalid product inventory')
    found = set()
    for name, record in sorted(manifest['files'].items()):
        index, separator, relative = name.partition('/')
        if not separator or not index.isdecimal() or str(int(index)) != index or not 0 <= int(index) < count:
            raise ValueError('Invalid product root index')
        item = PurePosixPath(relative)
        if (not relative or item.is_absolute() or '..' in item.parts or '\\' in relative
                or item.as_posix() != relative or not isinstance(record, dict)):
            raise ValueError('Invalid product member path')
        if item.suffix.lower() in NATIVE_SUFFIXES or any(part.startswith('.env') for part in item.parts):
            raise ValueError('Native state and credential files are not portable products')
        if relative == '.':
            found.add(int(index))
        if record.get('kind') == 'file':
            if not DIGEST.fullmatch(str(record.get('sha256', ''))) or type(record.get('size')) is not int or record['size'] < 0:
                raise ValueError('Invalid file identity')
        elif record.get('kind') != 'directory':
            raise ValueError('Invalid product member kind')
        yield int(index), item, record
    if found != set(range(count)):
        raise ValueError('Incomplete product roots')


class Store:
    def __init__(self, root=None):
        self.root = Path(root) if root is not None else paths.cache_dir('products', 'v1', create=False)

    def path(self, *parts):
        path = self.root
        for part in ('', *parts):
            path /= part
            if path.is_symlink():
                raise ValueError('Linked cache path')
        return path

    def action(self, key):
        if not DIGEST.fullmatch(key):
            raise ValueError('Invalid action key')
        return self.path('actions', key + '.json')

    def blob(self, digest):
        if not DIGEST.fullmatch(digest):
            raise ValueError('Invalid blob identity')
        return self.path('blobs', digest[:2], digest[2:])

    @contextmanager
    def lock(self, *, exclusive=False):
        """GC cannot race a publication or a restore. Contention is an immediate cache miss."""
        self.path().mkdir(parents=True, exist_ok=True)
        with self.path('.lock').open('a') as lock:
            kind = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
            fcntl.flock(lock.fileno(), kind | fcntl.LOCK_NB)
            yield

    def publish(self, ctx, step, key, products):
        """Publish only verified bytes. The action index is the final atomic commit."""
        with self.lock():
            return self._publish(ctx, step, key, products)

    def _publish(self, ctx, step, key, products):
        roots(ctx, step)
        if build_products.records(step) != products:
            raise ValueError('Products changed before cache publication')
        entry = {'schema': SCHEMA, 'key': key, 'products': products}
        for product in step.products:
            for index, relative, record in members(products[product.name]['inventory'], len(product.paths)):
                if record['kind'] != 'file':
                    continue
                source = product.paths[index] / relative if relative.parts else product.paths[index]
                target = self.blob(record['sha256'])
                if target.is_file() and not target.is_symlink() and build_products.file_digest(target) == record['sha256']:
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.TemporaryDirectory(dir=target.parent, prefix='.blob-') as folder:
                    temporary = Path(folder) / 'data'
                    copy_file(source, temporary)
                    if build_products.file_digest(temporary) != record['sha256']:
                        raise ValueError('Product changed while publishing')
                    temporary.chmod(0o444)
                    temporary.replace(target)
        if build_products.records(step) != products:
            raise ValueError('Products changed during cache publication')
        action = self.action(key)
        action.parent.mkdir(parents=True, exist_ok=True)
        with action.with_suffix('.lock').open('a') as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            if action.exists():
                previous = json.loads(action.read_text())
                if previous != entry:
                    atomic_json(action.with_suffix('.conflict.json'),
                                {'key': key, 'first': build_products.identity(previous),
                                 'second': build_products.identity(entry)})
                    raise ValueError('Same action key produced different bytes; reuse disabled for this key')
            else:
                atomic_json(action, entry)
            os.utime(action, None)

    def restore(self, ctx, step, key):
        """@cc [owner:fontanierh,label:correctness] verified-product-restoration
        Cached bytes MUST be verified in staging before replacing owned outputs. Replacement MUST
        remove the successful stamp first and keep a recovery journal until the caller certifies
        the action. Restored files MUST be independent copies, with no native packages admitted.
        """
        if not self.action(key).is_file():
            return None
        with self.lock():
            with self.action(key).with_suffix('.lock').open('a') as lock:
                fcntl.flock(lock.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
                return self._restore(ctx, step, key)

    def _restore(self, ctx, step, key):
        roots(ctx, step)
        action = self.action(key)
        if action.with_suffix('.conflict.json').exists():
            return None
        if not action.is_file() or action.is_symlink():
            return None
        entry = json.loads(action.read_text())
        if not isinstance(entry, dict) or entry.get('schema') != SCHEMA or entry.get('key') != key:
            raise ValueError('Invalid cached action')
        records = entry['products']
        if not isinstance(records, dict) or set(records) != {p.name for p in step.products}:
            raise ValueError('Cached product declarations differ')
        parent = staging_root(ctx, step)
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent, prefix='.restore-') as folder:
            staging = Path(folder)
            staged_products = []
            for number, product in enumerate(step.products):
                record = records[product.name]
                manifest = record['inventory']
                if build_products.identity(manifest) != record['digest']:
                    raise ValueError('Invalid product digest')
                staged = tuple(staging / str(number) / str(i) for i in range(len(product.paths)))
                for index, relative, item in members(manifest, len(staged)):
                    target = staged[index] / relative
                    if item['kind'] == 'directory':
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        blob = self.blob(item['sha256'])
                        if not blob.is_file() or blob.is_symlink():
                            raise ValueError('Missing regular cache blob')
                        copy_file(blob, target)
                candidate = build_products.Product(product.name, staged)
                if build_products.inventory(candidate) != manifest:
                    raise ValueError('Cached product bytes differ')
                staged_products.append(candidate)
            # No output is changed until every product has passed full verification.
            stamp = ctx.stamps / (step.name + '.json')
            journal = ctx.stamps / (step.name + '.restore.json')
            stamp.unlink(missing_ok=True)
            atomic_json(journal, {'schema': SCHEMA, 'key': key})
            roots(ctx, step)
            for original, staged in zip(step.products, staged_products, strict=True):
                for destination, source in zip(original.paths, staged.paths, strict=True):
                    if destination.is_dir():
                        shutil.rmtree(destination)
                    else:
                        destination.unlink(missing_ok=True)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    source.replace(destination)
            if build_products.records(step) != records:
                raise ValueError('Installed product inventory differs')
        os.utime(action, None)
        return records


def staging_root(ctx, step):
    target = ctx.out
    for part in ('.state', 'restores', step.name):
        target /= part
        if target.is_symlink():
            raise ValueError('Linked restoration staging path')
    return target


def recover(ctx, step):
    """Remove only this action's abandoned staging. One build writer owns a checkout."""
    staging = staging_root(ctx, step)
    journal = ctx.stamps / (step.name + '.restore.json')
    if journal.exists():
        (ctx.stamps / (step.name + '.json')).unlink(missing_ok=True)
    if staging.exists():
        shutil.rmtree(staging)
