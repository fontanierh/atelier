"""Inspect frozen A3 Items and independently stage their native package bytes.

The caller owns the Content and runtime roots, sandbox and source declarations.
This helper never writes a staged input or chooses an arbitrary directory member.
"""
import hashlib
import importlib.util
import os
from pathlib import Path, PurePosixPath
import re
import stat

if __package__:
    from . import recipe_job
else:
    _spec = importlib.util.spec_from_file_location('atelier_unreal_root_codec', Path(__file__).with_name('recipe_job.py'))
    recipe_job = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(recipe_job)

SUFFIXES = ('.m.ubulk', '.upayload', '.uasset', '.umap', '.uexp', '.ubulk', '.uptnl')
PRIMARY = ('.uasset', '.umap')
PACKAGE = re.compile(r'/Game/(?:[A-Za-z0-9_]+/)*[A-Za-z0-9_]+\Z')


def _relative(value):
    if (not isinstance(value, str) or not value or '\\' in value or PurePosixPath(value).is_absolute()
            or str(PurePosixPath(value)) != value or any(p in ('', '.', '..') for p in value.split('/'))):
        raise ValueError('noncanonical input member path')
    return value


def _root(value):
    path = Path(value)
    if not path.is_absolute() or path.resolve() != path or not path.is_dir() or path.is_symlink():
        raise ValueError('expected an existing independent absolute directory')
    return path


def _state(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _open_absolute(path, directory=False):
    path = Path(path)
    if not path.is_absolute() or str(path) != os.path.abspath(path):
        raise ValueError('expected a canonical absolute source path')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        parts = path.parts[1:]
        for index, name in enumerate(parts):
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            if directory or index < len(parts) - 1:
                flags |= os.O_DIRECTORY
            child = os.open(name, flags, dir_fd=fd)
            os.close(fd); fd = child
        result, fd = fd, None
        return result
    finally:
        if fd is not None:
            os.close(fd)


def _inventory(root):
    """Complete nofollow bytes and directory census, stable through each visit."""
    root = Path(root)
    files, directories = {}, []
    def visit(fd, path, name):
        before = os.fstat(fd)
        if stat.S_ISDIR(before.st_mode):
            directories.append(name)
            names = sorted(os.listdir(fd))
            for child in names:
                _relative(child)
                child_fd = os.open(child, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
                try:
                    visit(child_fd, path / child, name + '/' + child if name else child)
                    if _state(os.fstat(child_fd)) != _state(os.stat(child, dir_fd=fd, follow_symlinks=False)):
                        raise ValueError('input member changed while reading')
                finally:
                    os.close(child_fd)
            if sorted(os.listdir(fd)) != names:
                raise ValueError('input directory membership changed')
        elif stat.S_ISREG(before.st_mode):
            digest = hashlib.sha256()
            for chunk in iter(lambda: os.read(fd, 1024 * 1024), b''):
                digest.update(chunk)
            files[name] = digest.hexdigest()
        else:
            raise ValueError('input contains a link or special member')
        if _state(os.fstat(fd)) != _state(before):
            raise ValueError('input changed while reading')
    fd = _open_absolute(root)
    try:
        visit(fd, root, '')
        if _state(os.fstat(fd)) != _state(root.lstat()):
            raise ValueError('input root changed while reading')
    finally:
        os.close(fd)
    return files, directories


def _open_member(root, member):
    """Open every path component relative to its held nofollow directory."""
    if not member:
        return _open_absolute(root)
    fd = _open_absolute(root, directory=True)
    try:
        parts = _relative(member).split('/')
        for index, name in enumerate(parts):
            child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | (os.O_DIRECTORY if index < len(parts) - 1 else 0), dir_fd=fd)
            os.close(fd); fd = child
        result, fd = fd, None
        return result
    finally:
        if fd is not None:
            os.close(fd)


def select_member(root, members, member):
    """@cc [owner:fontanierh,label:correctness] exact-unreal-source-member
    An explicit member MAY be selected only after its complete source inventory
    matches every declared member SHA. Missing, extra, linked and changed files
    MUST refuse; a directory MUST never be replaced with its first file.
    """
    root = _root(root)
    expected = {}
    for row in members:
        if not isinstance(row, dict) or set(row) != {'path', 'sha256'}:
            raise ValueError('invalid complete source inventory row')
        name, digest = _relative(row['path']), row['sha256']
        if name in expected or not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
            raise ValueError('invalid or duplicate source member digest')
        expected[name] = digest
    actual, directories = _inventory(root)
    expected_directories = {''} | {str(parent) for member in expected for parent in PurePosixPath(member).parents if str(parent) != '.'}
    if actual != expected or set(directories) != expected_directories:
        raise ValueError('complete source inventory differs')
    member = _relative(member)
    if member not in expected:
        raise ValueError('selected source member is undeclared')
    return root / member


def stage_inputs(job_dir, items, content_dir, *, runtime_dir, output_packages=(), root_bindings=None):
    """@cc [owner:fontanierh,label:correctness;safety] frozen-unreal-item-staging
    Every present Item MUST be inventoried without following links. Native Content
    copies MUST preserve exact source bytes and complete sidecars, never mutate
    staged inputs or replace existing Content, and MUST refuse input/output overlap
    before copying. Archives MUST use the existing checked recipe root codec in
    the caller's owned runtime directory. Raw source directories remain directories.
    Returned reads are declarations for actual bytes, never cache certification.
    """
    job_dir, content, runtime = _root(job_dir), _root(content_dir), _root(runtime_dir)
    root_bindings = {} if root_bindings is None else root_bindings
    if (not isinstance(root_bindings, dict)
            or set(root_bindings) - {item['name'] for item in items}):
        raise ValueError('ROOT binding names an undeclared input slot')
    for binding in root_bindings.values():
        if not isinstance(binding, dict) or set(binding) != {'archive_member', 'name'}:
            raise ValueError('invalid explicit ROOT binding')
        _relative(binding['archive_member'])
        if not binding['archive_member'].endswith('.tree.tar'):
            raise ValueError('ROOT binding must select an exact archive member')
        if '/' in _relative(binding['name']):
            raise ValueError('ROOT binding name must be one producer root basename')
    if (not runtime.is_relative_to(job_dir) or runtime == job_dir
            or content == job_dir or content.is_relative_to(runtime) or runtime.is_relative_to(content)):
        raise ValueError('runtime and Content must be distinct owned roots')
    outputs = set()
    for package in output_packages:
        if not isinstance(package, str) or not PACKAGE.fullmatch(package):
            raise ValueError('invalid output package name')
        outputs.add(package.casefold())
    inputs, packages, reads, plan, inspections = {}, {}, set(), {}, []
    package_owners, primary = {}, {}
    for index, item in enumerate(items):
        name = item['name']
        if not isinstance(name, str) or not name or name in inputs:
            raise ValueError('duplicate or invalid input slot')
        path = _relative(item['path']); source = job_dir / path
        if any(parent.is_symlink() for parent in (source, *source.parents)):
            raise ValueError('input locator traverses a link')
        if any(source == owned or source.is_relative_to(owned) or owned.is_relative_to(source)
               for owned in (runtime, content)):
            raise ValueError('input overlaps owned runtime or Content')
        state = item['identity']['state']
        if state not in ('absent', 'digest'):
            raise ValueError('unknown staged input identity state')
        present = state != 'absent'
        if present != os.path.lexists(source):
            raise ValueError('staged input presence differs')
        inputs[name], packages[name] = None, []
        if not present:
            continue
        original, original_directories = _inventory(source)
        reads.update(source / member if member else source for member in original)
        binding = root_bindings.get(name)
        archive = None
        destination = runtime / ('item-' + str(index))
        if binding is not None:
            if not original_directories or binding['archive_member'] not in original:
                raise ValueError('explicit ROOT archive member is absent or not an Item file')
            archive = source / binding['archive_member']
            if os.path.lexists(destination):
                raise ValueError('ROOT binding runtime parent is already occupied')
            destination /= binding['name']
        elif source.name.endswith('.tree.tar'):
            if set(original) != {''}:
                raise ValueError('root archive input must be a regular file')
            archive = source
        if archive is not None:
            decoded = recipe_job.unpack_root(archive, destination)
            if _inventory(source) != (original, original_directories):
                raise ValueError('archive input changed during decode')
            if decoded['kind'] == 'absent':
                continue
            source = destination
        files, directories = _inventory(source)
        inspections.append((source, files, directories))
        reads.update(source / member if member else source for member in files)
        inputs[name] = str(source)
        native = {}
        for member, digest in files.items():
            logical = (path[len('in/'):] if path.startswith('in/content/Game/') else '') if not member else member
            if not logical.startswith('content/Game/'):
                continue
            relative = logical[len('content/Game/'):]
            suffix = next((suffix for suffix in SUFFIXES if relative.endswith(suffix)), None)
            if suffix is None:
                raise ValueError('unknown native Content member')
            base = relative[:-len(suffix)]; package = '/Game/' + base
            if not PACKAGE.fullmatch(package):
                raise ValueError('invalid native package path')
            if package.casefold() in outputs:
                raise ValueError('package is both an input and an output')
            target = content / relative
            key = relative.casefold()
            if key in plan or os.path.lexists(target):
                raise ValueError('duplicate or occupied native Content member')
            owner = package_owners.setdefault(package.casefold(), package)
            if owner != package:
                raise ValueError('case-aliased native package')
            plan[key] = (source, member, target, digest)
            native.setdefault(package, []).append(suffix)
            if suffix in PRIMARY:
                if package.casefold() in primary:
                    raise ValueError('multiple native package primary files')
                primary[package.casefold()] = package
                if not directories:
                    inputs[name] = package
            elif not directories:
                inputs[name] = str(target)
        packages[name] = sorted(native)
    for _, (source, member, target, digest) in plan.items():
        relative = target.relative_to(content).as_posix()
        suffix = next(s for s in SUFFIXES if relative.endswith(s))
        if ('/Game/' + relative[:-len(suffix)]).casefold() not in primary:
            raise ValueError('native sidecar has no primary package')
    staged = {}
    for source, member, target, expected in plan.values():
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.parent.resolve() != target.parent:
            raise ValueError('Content destination traverses a link')
        incoming = _open_member(source, member)
        try:
            before = os.fstat(incoming)
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o444)
            with os.fdopen(fd, 'wb') as outgoing:
                digest = hashlib.sha256()
                for chunk in iter(lambda: os.read(incoming, 1024 * 1024), b''):
                    digest.update(chunk); outgoing.write(chunk)
            if digest.hexdigest() != expected or _state(before) != _state(os.fstat(incoming)):
                raise ValueError('native source changed during independent copy')
        finally:
            os.close(incoming)
        staged[target] = expected; reads.add(target)
    for source, files, directories in inspections:
        if _inventory(source) != (files, directories):
            raise ValueError('input changed during staging')
    return {'inputs': inputs, 'packages': packages, 'declared_reads': sorted(reads), 'staged_files': staged}
