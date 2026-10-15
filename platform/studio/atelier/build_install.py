"""Offline package transaction foundation; no Unreal hydration backend is enabled.

The sole backend is a closed, explicitly typed JSON package fixture and its rebuilt registry.
The public internal entry point owns one legacy-only common guarded worker lifecycle with live
monitor and held-mutex proof; broker configurations and all cutover states refuse. It cannot adopt
unowned Content, accept a readiness callback, or enable native package restoration.
"""
from dataclasses import dataclass
from contextlib import contextmanager, ExitStack
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import uuid

from . import build_snapshot, paths

BACKEND = 'typed-json-packages-v1'
MAX_JSON = 4 * 1024**2
MAX_FILES = 10000
MAX_FILE = 8 * 1024**3
MAX_TOTAL = 64 * 1024**3
SUFFIXES = ('.m.ubulk', '.uasset', '.umap', '.uexp', '.ubulk', '.uptnl')
CURRENT = '.package-install-current.json'
RECEIPT = '.package-install-complete.json'
STAGES = '.package-install-stage'


class InstallError(RuntimeError):
    pass


def _fields(value, names):
    if type(value) is not dict or set(value) != set(names):
        raise InstallError('Unsupported package transaction fields')
    return value


def _decode(data):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise InstallError('Duplicate package transaction field')
            value[key] = item
        return value
    if len(data) > MAX_JSON:
        raise InstallError('Package transaction exceeds its bounded frame')
    try:
        return json.loads(data, object_pairs_hook=unique)
    except (ValueError, UnicodeError):
        raise InstallError('Invalid package transaction JSON') from None


def _encode(value):
    data = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode() + b'\n'
    if len(data) > MAX_JSON:
        raise InstallError('Package transaction exceeds its bounded frame')
    return data


def _digest(value):
    return hashlib.sha256(_encode(value)).hexdigest()


def _relative(value):
    if (type(value) is not str or not value or len(value) > 1024 or '\\' in value
            or any(ord(c) < 32 for c in value)):
        raise InstallError('Invalid relative Content leaf')
    path = PurePosixPath(value)
    if path.is_absolute() or str(path) != value or any(part in ('.', '..') for part in path.parts):
        raise InstallError('Content leaves must be canonical relative paths')
    return value


def _package(value):
    if (type(value) is not str or not re.fullmatch(r'/[A-Za-z][A-Za-z0-9_]*/[A-Za-z0-9_/]+', value)
            or any(not part for part in value.split('/')[1:])):
        raise InstallError('Invalid logical package name')
    return value


def _leaf_package(value):
    value = _relative(value)
    suffix = next((suffix for suffix in SUFFIXES if value.endswith(suffix)), None)
    if suffix is None:
        raise InstallError('Unsupported generated package leaf')
    return _package('/Game/' + value[:-len(suffix)])


def snapshot(value):
    _fields(value, ('schema', 'backend', 'packages', 'external_references'))
    if type(value['schema']) is not int or value['schema'] != 1 or value['backend'] != BACKEND:
        raise InstallError('Native package installation has no validated backend')
    if type(value['packages']) is not list or len(value['packages']) > MAX_FILES:
        raise InstallError('Invalid bounded generated package list')
    if type(value['external_references']) is not list:
        raise InstallError('Explicit external references are required')
    external = [_package(name) for name in value['external_references']]
    if len({name.casefold() for name in external}) != len(external):
        raise InstallError('Duplicate external reference')
    names, aliases, leaves, total = {}, set(), {}, 0
    for package in value['packages']:
        _fields(package, ('name', 'owner', 'references', 'files'))
        name = _package(package['name'])
        if not name.startswith('/Game/') or name.casefold() in aliases:
            raise InstallError('Duplicate or case-aliased generated package')
        aliases.add(name.casefold())
        if type(package['owner']) is not str or not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', package['owner']):
            raise InstallError('A stable package owner is required')
        if type(package['references']) is not list or len(package['references']) > MAX_FILES:
            raise InstallError('Invalid package references')
        refs = [_package(ref) for ref in package['references']]
        if len(set(refs)) != len(refs):
            raise InstallError('Duplicate package reference')
        if type(package['files']) is not list or not package['files']:
            raise InstallError('A complete package leaf inventory is required')
        primary = 0
        for leaf in package['files']:
            _fields(leaf, ('path', 'size', 'sha256'))
            path = _relative(leaf['path'])
            if _leaf_package(path) != name or path.casefold() in leaves:
                raise InstallError('Duplicate ownership or package leaf alias')
            if type(leaf['size']) is not int or not 0 <= leaf['size'] <= MAX_FILE:
                raise InstallError('Package leaf size exceeds its bound')
            if type(leaf['sha256']) is not str or not re.fullmatch('[0-9a-f]{64}', leaf['sha256']):
                raise InstallError('An exact package leaf SHA256 is required')
            leaves[path.casefold()] = leaf
            total += leaf['size']
            primary += path.endswith(('.uasset', '.umap'))
        if primary != 1:
            raise InstallError('Each package needs exactly one primary leaf')
        names[name] = package
    if len(leaves) > MAX_FILES or total > MAX_TOTAL or set(aliases) & {name.casefold() for name in external}:
        raise InstallError('Invalid complete generated snapshot scope')
    for package in names.values():
        if any(ref not in names and ref not in external for ref in package['references']):
            raise InstallError('Package reference is neither generated nor explicitly external')
    return value


def _identity(info, *, directory=False):
    valid = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode) and info.st_nlink == 1
    if not valid or info.st_uid != os.getuid():
        raise InstallError('Package paths must be owned regular files/directories without links')
    return dict(device=info.st_dev, inode=info.st_ino, mode=stat.S_IMODE(info.st_mode),
                size=info.st_size, mtime_ns=info.st_mtime_ns, ctime_ns=info.st_ctime_ns)


def _directory(path):
    for part in (path, *path.parents):
        if part.is_symlink() and str(part) not in ('/tmp', '/var', '/etc'):
            raise InstallError('Package paths cannot follow symbolic links')
    return _identity(path.lstat(), directory=True)


def _file(path, *, limit=MAX_FILE, dir_fd=None):
    if dir_fd is None:
        _directory(path.parent)
    fd = os.open(path if dir_fd is None else path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                 dir_fd=dir_fd)
    with os.fdopen(fd, 'rb') as stream:
        before = _identity(os.fstat(stream.fileno()))
        if before['size'] > limit:
            raise InstallError('Package file exceeds its bound')
        digest = hashlib.sha256()
        read, spoken = 0, time.monotonic()
        while chunk := stream.read(min(1024**2, before['size'] + 1 - read)):
            read += len(chunk)
            if read > before['size']:
                raise InstallError('Package file grew beyond its observed size')
            digest.update(chunk)
            if time.monotonic() - spoken >= 30:
                print(f'package verification {read // 1024**2} MiB observed', flush=True)
                spoken = time.monotonic()
        final = path.lstat() if dir_fd is None else os.stat(path.name, dir_fd=dir_fd, follow_symlinks=False)
        if _identity(os.fstat(stream.fileno())) != before or _identity(final) != before:
            raise InstallError('Package file changed while reading')
    return dict(pin=before, size=before['size'], sha256=digest.hexdigest())


def _read(path, *, private=False):
    _directory(path.parent)
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        before = _identity(os.fstat(stream.fileno()))
        if before['size'] > MAX_JSON or private and before['mode'] & 0o077:
            raise InstallError('Package metadata exceeds its bound')
        data = stream.read(MAX_JSON + 1)
        if _identity(os.fstat(stream.fileno())) != before or _identity(path.lstat()) != before:
            raise InstallError('Package metadata changed while reading')
    return _decode(data)


def _mkdir(path, mode=0o700):
    if os.path.lexists(path):
        return _directory(path)
    _mkdir(path.parent, mode)
    parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.mkdir(path.name, mode, dir_fd=parent)
        os.fsync(parent)
    finally:
        os.close(parent)
    return _directory(path)


def _sync(directory):
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _save(path, value):
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(_encode(value))
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
        _sync(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _same_directory(path, pin):
    current = _directory(path)
    if any(current[key] != pin[key] for key in ('device', 'inode', 'mode')):
        raise InstallError('A package destination directory was replaced or changed')


def _record(value):
    _fields(value, ('pin', 'size', 'sha256'))
    _fields(value['pin'], ('device', 'inode', 'mode', 'size', 'mtime_ns', 'ctime_ns'))
    if (any(type(item) is not int for item in value['pin'].values())
            or type(value['size']) is not int or not 0 <= value['size'] <= MAX_FILE
            or value['pin']['size'] != value['size'] or type(value['sha256']) is not str
            or not re.fullmatch('[0-9a-f]{64}', value['sha256'])):
        raise InstallError('Invalid pinned package record')
    return value


def _exists(path, dir_fd=None):
    try:
        os.stat(path if dir_fd is None else path.name, dir_fd=dir_fd, follow_symlinks=False)
        return True
    except FileNotFoundError:
        return False


def _matches(path, expected, *, renamed=False, dir_fd=None):
    if not _exists(path, dir_fd):
        return False
    current = _file(path, dir_fd=dir_fd)
    keys = ('device', 'inode', 'mode', 'size', 'mtime_ns') if renamed else tuple(expected['pin'])
    return (all(current['pin'][key] == expected['pin'][key] for key in keys)
            and current['size'] == expected['size'] and current['sha256'] == expected['sha256'])


def _leaves(value):
    return {leaf['path']: leaf for package in value['packages'] for leaf in package['files']}


def _primary(path, name):
    value = _read(path)
    _fields(value, ('schema', 'backend', 'package', 'references'))
    if type(value['schema']) is not int or value['schema'] != 1 or value['backend'] != BACKEND or value['package'] != name:
        raise InstallError('Native/binary package bytes are unsupported by the closed offline registry backend')
    if type(value['references']) is not list:
        raise InstallError('Invalid typed package references')
    return [_package(ref) for ref in value['references']]


@dataclass
class Scope:
    repo: Path
    game: str

    def __post_init__(self):
        if not re.fullmatch('[A-Za-z0-9_][A-Za-z0-9_-]*', self.game):
            raise InstallError('Invalid game scope')
        self.repo = Path(self.repo).absolute()
        _directory(self.repo)
        self.project = self.repo / 'games' / self.game / 'unreal'
        _directory(self.project)
        self.project_pin = _directory(self.project)
        self.content = self.project / 'Content'
        self.out = self.repo / 'build' / self.game
        _mkdir(self.out)
        _directory(self.out)
        self.journal = self.out / build_snapshot.PACKAGE_JOURNAL
        self.current = self.out / CURRENT
        self.receipt = self.out / RECEIPT
        self.stages = self.out / STAGES
        _mkdir(self.stages)
        _directory(self.stages)
        if self.stages.stat().st_mode & 0o077 or self.out.stat().st_mode & 0o022:
            raise InstallError('Package metadata/stage directories must exclude foreign writers/readers')
        if self.stages.stat().st_dev != self.project.stat().st_dev:
            raise InstallError('Package transactions require one filesystem for atomic installation')

    def eligible(self):
        projects = list(self.project.glob('*.uproject'))
        value = _read(projects[0]) if len(projects) == 1 else None
        if (type(value) is not dict or set(value) != {'schema', 'backend'}
                or type(value['schema']) is not int or value != {'schema': 1, 'backend': BACKEND}):
            raise InstallError('This project has no validated package registry backend; native hydration is disabled')

    def tracked(self):
        result = subprocess.run(['git', '-C', str(self.repo), 'ls-files', '-z', '--',
                                 f'games/{self.game}/unreal/Content'], capture_output=True, timeout=5)
        if result.returncode or len(result.stdout) > MAX_JSON:
            raise InstallError('Cannot establish Git-tracked package ownership')
        prefix = f'games/{self.game}/unreal/Content/'
        return {name.decode().removeprefix(prefix).casefold() for name in result.stdout.split(b'\0') if name}

    def bind_ownership(self, names):
        result = subprocess.run(['git', '-C', str(self.repo), 'rev-parse', '--path-format=absolute',
                                 '--git-path', 'index'], capture_output=True, timeout=5)
        if result.returncode or len(result.stdout) > 4096:
            raise InstallError('Cannot establish the current Git index identity')
        self.index_path = Path(result.stdout.decode().strip())
        if not self.index_path.is_absolute():
            raise InstallError('Git index path must be absolute')
        self.index_pin = _identity(self.index_path.lstat()) if os.path.lexists(self.index_path) else None
        if {name.casefold() for name in names} & self.tracked():
            raise InstallError('Git-tracked Content cannot be installed or retired')
        self.check_index()

    def check_binding(self):
        if hasattr(self, 'worker_proof'):
            self.worker_proof.check()

    def check_index(self):
        self.check_binding()
        if hasattr(self, 'index_path'):
            current = _identity(self.index_path.lstat()) if os.path.lexists(self.index_path) else None
            if current != self.index_pin:
                raise InstallError('Git ownership changed during package installation')

    def check(self, directories):
        self.check_index()
        _same_directory(self.project, self.project_pin)
        for name, pin in directories.items():
            _same_directory(self.content / name if name else self.content, pin)


@contextmanager
def _destination_parent(scope, relative, directories):
    """Walk held directory descriptors; a swapped parent symlink cannot redirect a mutation."""
    scope.check_index()
    with ExitStack() as stack:
        def opened(name, parent=None, pin=None):
            fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            stack.callback(os.close, fd)
            actual = _identity(os.fstat(fd), directory=True)
            if any(actual[key] != pin[key] for key in ('device', 'inode', 'mode')):
                raise InstallError('Package destination parent identity changed')
            return fd
        parent = opened(scope.project, pin=scope.project_pin)
        if not relative:
            yield parent, 'Content'
            return
        parent = opened('Content', parent, directories[''])
        parts = PurePosixPath(relative).parts
        for index, component in enumerate(parts[:-1]):
            parent = opened(component, parent, directories['/'.join(parts[:index + 1])])
        yield parent, parts[-1]


def _move_prepared(scope, source, relative, directories, after, before=None, *, directory=False):
    source_parent = os.open(source.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = _identity(os.stat(source.name, dir_fd=source_parent, follow_symlinks=False), directory=directory)
        expected = after if directory else after['pin']
        keys = ('device', 'inode', 'mode') if directory else tuple(expected)
        if any(info[key] != expected[key] for key in keys):
            raise InstallError('Prepared package inode changed before rename')
        with _destination_parent(scope, relative, directories) as (parent, name):
            target = Path(name)
            if before is None:
                if _exists(target, parent):
                    raise InstallError('A prepared package would replace an unowned destination')
            elif not _matches(target, before, dir_fd=parent):
                raise InstallError('Owned package destination changed before replacement')
            scope.check_index()
            os.replace(source.name, name, src_dir_fd=source_parent, dst_dir_fd=parent)
            os.fsync(parent)
            os.fsync(source_parent)
    finally:
        os.close(source_parent)


def _retire_owned(scope, relative, directories, before):
    with _destination_parent(scope, relative, directories) as (parent, name):
        if not _matches(Path(name), before, dir_fd=parent):
            raise InstallError('Owned retirement inode changed before unlink')
        scope.check_index()
        os.unlink(name, dir_fd=parent)
        os.fsync(parent)


def _copy(source, target, expected, *, readonly=False):
    before = _file(source)
    if any(before[key] != expected[key] for key in ('size', 'sha256')):
        raise InstallError('Package source bytes do not match the complete snapshot')
    source_fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    target_fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(source_fd, 'rb') as incoming, os.fdopen(target_fd, 'wb') as outgoing:
            copied, spoken = 0, time.monotonic()
            while chunk := incoming.read(min(1024**2, expected['size'] + 1 - copied)):
                copied += len(chunk)
                if copied > expected['size']:
                    raise InstallError('Package source grew beyond its declared size')
                outgoing.write(chunk)
                if time.monotonic() - spoken >= 30:
                    print(f'package staging {copied // 1024**2} MiB copied', flush=True)
                    spoken = time.monotonic()
            outgoing.flush()
            if readonly:
                os.fchmod(outgoing.fileno(), 0o400)
            os.fsync(outgoing.fileno())
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    after = _file(target)
    if any(after[key] != expected[key] for key in ('size', 'sha256')) or _file(source) != before:
        raise InstallError('Package source changed during independent staging')
    return after


def _tree(root):
    """A bounded exact leaf set, including unrelated files but never following links."""
    _directory(root)
    files, directories = {}, {'': _directory(root)}
    todo = [root]
    while todo:
        directory = todo.pop()
        for path in sorted(directory.iterdir()):
            relative = path.relative_to(root).as_posix()
            if len(files) + len(directories) >= MAX_FILES * 2:
                raise InstallError('Package tree exceeds its bounded inventory')
            if path.is_symlink():
                raise InstallError('Package trees cannot contain symbolic links')
            if path.is_dir():
                directories[relative] = _directory(path)
                todo.append(path)
            else:
                files[relative] = _identity(path.lstat())
    aliases = [name.casefold() for name in (*files, *directories)]
    if len(set(aliases)) != len(aliases):
        raise InstallError('Package tree contains a case alias')
    return files, directories


def _previous(scope):
    if not os.path.lexists(scope.current):
        return dict(schema=1, backend=BACKEND, packages=[], external_references=[]), {}, None
    value = _read(scope.current, private=True)
    _fields(value, ('schema', 'repo', 'game', 'snapshot', 'files', 'transaction'))
    if type(value['schema']) is not int or value['schema'] != 1 or value['repo'] != str(scope.repo) or value['game'] != scope.game:
        raise InstallError('Current ownership manifest belongs to another checkout')
    previous = snapshot(value['snapshot'])
    if type(value['files']) is not dict or set(value['files']) != set(_leaves(previous)):
        raise InstallError('Current ownership manifest is incomplete')
    for name, leaf in _leaves(previous).items():
        actual = _record(value['files'][name])
        if any(actual[key] != leaf[key] for key in ('size', 'sha256')):
            raise InstallError('Current ownership identity differs from its snapshot')
    if type(value['transaction']) is not str or not re.fullmatch('[0-9a-f]{32}', value['transaction']):
        raise InstallError('Current ownership manifest has no valid transaction')
    return previous, value['files'], value


def _prepare(scope, plan, source, *, nonce=None):
    """@cc [owner:fontanierh,label:correctness] owned-package-installation-plan
    Prior ownership MUST come only from this installer's durable current manifest. Unowned or
    tracked leaves MUST NOT be replaced or retired. Every source byte and prepared inode MUST
    be independently staged and fsynced before the durable journal permits destination mutation.
    """
    scope.eligible()
    if os.path.lexists(scope.journal):
        raise InstallError('Package installation already has a recovery journal')
    previous, old_files, base_document = _previous(scope)
    base = _file(scope.current) if base_document is not None else None
    if base is not None and base['sha256'] != _digest(base_document):
        raise InstallError('Current ownership manifest changed before staging')
    new = _leaves(plan)
    old = _leaves(previous)
    prior_names = {item['name'].casefold(): item['name'] for item in previous['packages']}
    new_names = {item['name'].casefold(): item['name'] for item in plan['packages']}
    if any(prior_names[key] != new_names[key] for key in prior_names.keys() & new_names.keys()):
        raise InstallError('Generated package names cannot change only their case')
    retired_names = prior_names.keys() - new_names.keys()
    for package in plan['packages']:
        if {ref.casefold() for ref in package['references']} & retired_names:
            raise InstallError('A reference to a retired generated package requires an owned redirector or fixup')
        prior = next((item for item in previous['packages'] if item['name'] == package['name']), None)
        if prior and prior['owner'] != package['owner']:
            raise InstallError('Package ownership transfer requires a separate reviewed protocol')
    scope.bind_ownership(set(old) | set(new))
    present, directories = _tree(scope.content) if os.path.lexists(scope.content) else ({}, {})
    authored = {}
    for name in present:
        if name.endswith(('.uasset', '.umap')):
            refs = _primary(scope.content / name, _leaf_package(name))
            if name not in old:
                authored[name] = _file(scope.content / name)
                if {ref.casefold() for ref in refs} & retired_names:
                    raise InstallError('An authored package still references a retired generated package')
    actual_aliases = {name.casefold(): name for name in present}
    for name, expected in old_files.items():
        if not _matches(scope.content / name, expected):
            raise InstallError('Previously owned Content was changed outside its transaction')
    for name in new:
        alias = actual_aliases.get(name.casefold())
        if alias is not None and (alias != name or name not in old):
            raise InstallError('The installation cannot adopt a preexisting unowned Content leaf')
    source = Path(source).absolute()
    source_pin = _directory(source)
    if source == scope.content or source.is_relative_to(scope.content) or scope.content.is_relative_to(source):
        raise InstallError('Package sources and destination cannot overlap')
    source_files, _ = _tree(source)
    if set(source_files) != set(new):
        raise InstallError('Source leaves differ from the complete package inventory')
    total = sum(item['size'] for item in new.values())
    if shutil.disk_usage(scope.out).free < total * 2 + 64 * 1024**2:
        raise InstallError('Insufficient staging headroom for the complete package snapshot')
    nonce = uuid.uuid4().hex if nonce is None else nonce
    if type(nonce) is not str or not re.fullmatch('[0-9a-f]{32}', nonce):
        raise InstallError('Invalid package transaction identity')
    stage = scope.stages / nonce
    _mkdir(stage)
    payload, candidates, dir_candidates = stage / 'payload', stage / 'candidates', stage / 'directories'
    for root in (payload, candidates, dir_candidates):
        _mkdir(root)
    staged, operations = {}, []
    for index, (name, leaf) in enumerate(sorted(new.items())):
        target = payload / str(index)
        staged[name] = dict(path=str(target.relative_to(stage)), **_copy(source / name, target, leaf, readonly=True))
        if name.endswith(('.uasset', '.umap')):
            package = next(package for package in plan['packages'] if package['name'] == _leaf_package(name))
            if _primary(target, package['name']) != package['references']:
                raise InstallError('Staged package references differ from the complete snapshot')
        if name in old and old[name] == leaf:
            continue
        candidate = candidates / str(index)
        prepared = _copy(target, candidate, leaf)
        operations.append(dict(path=name, before=old_files.get(name), after=prepared,
                               candidate=str(candidate.relative_to(stage)), installed=None))
        print(f'package staging {index + 1}/{len(new)} leaves', flush=True)
    for name in sorted(set(old) - set(new)):
        operations.append(dict(path=name, before=old_files[name], after=None, candidate=None, installed=None))
    needed = {''}
    for name in new:
        needed.update(str(parent) if str(parent) != '.' else '' for parent in PurePosixPath(name).parents)
    create = []
    for index, name in enumerate(sorted(needed - directories.keys(), key=lambda name: (name.count('/'), name))):
        candidate = dir_candidates / str(index)
        pin = _mkdir(candidate)
        create.append(dict(path=name, candidate=str(candidate.relative_to(stage)), pin=pin))
    for root in (payload, candidates, dir_candidates, stage, scope.stages):
        _sync(root)
    if _directory(source) != source_pin:
        raise InstallError('Package source root changed during staging')
    if base is not None and not _matches(scope.current, base) or base is None and os.path.lexists(scope.current):
        raise InstallError('Current ownership manifest changed during staging')
    value = dict(schema=1, backend=BACKEND, nonce=nonce, repo=str(scope.repo), game=scope.game,
                 project_pin=scope.project_pin, stage_pin=_directory(stage), snapshot=plan,
                 snapshot_sha256=_digest(plan), previous=previous, old_files=old_files, staged=staged,
                 base=base, base_transaction=None if base_document is None else base_document['transaction'],
                 authored=authored, directories=directories, create=create, operations=operations, phase='installing')
    scope.check_binding()
    _save(scope.journal, value)
    return value


def _journal(scope):
    value = _read(scope.journal, private=True)
    _fields(value, ('schema', 'backend', 'nonce', 'repo', 'game', 'project_pin', 'stage_pin', 'snapshot',
                    'snapshot_sha256', 'previous', 'old_files', 'staged', 'directories', 'create',
                    'base', 'base_transaction', 'authored', 'operations', 'phase'))
    if (type(value['schema']) is not int or value['schema'] != 1 or value['backend'] != BACKEND
            or value['repo'] != str(scope.repo) or value['game'] != scope.game
            or type(value['nonce']) is not str or not re.fullmatch('[0-9a-f]{32}', value['nonce'])
            or value['phase'] not in ('installing', 'registry-pending', 'complete')):
        raise InstallError('Package recovery journal has a foreign scope or phase')
    plan = snapshot(value['snapshot'])
    previous = snapshot(value['previous'])
    if _digest(plan) != value['snapshot_sha256']:
        raise InstallError('Package recovery snapshot identity changed')
    stage = scope.stages / value['nonce']
    _same_directory(stage, value['stage_pin'])
    _same_directory(scope.project, value['project_pin'])
    expected = _leaves(plan)
    old = _leaves(previous)
    if type(value['old_files']) is not dict or set(value['old_files']) != set(old):
        raise InstallError('Recovery prior ownership inventory is incomplete')
    for name, leaf in old.items():
        record = _record(value['old_files'][name])
        if any(record[key] != leaf[key] for key in ('size', 'sha256')):
            raise InstallError('Recovery prior ownership differs from its snapshot')
    if value['base'] is None:
        if old or value['base_transaction'] is not None:
            raise InstallError('Initial recovery cannot assert previous ownership')
    else:
        _record(value['base'])
        prior_document = dict(schema=1, repo=str(scope.repo), game=scope.game, snapshot=previous,
                              files=value['old_files'], transaction=value['base_transaction'])
        if _digest(prior_document) != value['base']['sha256']:
            raise InstallError('Recovery prior ownership is not bound to its durable current manifest')
    original_current = (not os.path.lexists(scope.current) if value['base'] is None
                        else _matches(scope.current, value['base']))
    if not original_current:
        completed = _read(scope.current, private=True)
        _fields(completed, ('schema', 'repo', 'game', 'snapshot', 'files', 'transaction'))
        if (type(completed['schema']) is not int or completed['schema'] != 1):
            raise InstallError('Invalid recovery completion ownership schema')
        if (value['phase'] == 'installing' or completed.get('transaction') != value['nonce']
                or completed.get('snapshot') != plan or completed.get('repo') != str(scope.repo)
                or completed.get('game') != scope.game or set(completed.get('files', {})) != set(expected)):
            raise InstallError('Recovery current ownership manifest was changed outside its completion phase')
        for name, record in completed['files'].items():
            _record(record)
            if (any(record[key] != expected[name][key] for key in ('size', 'sha256'))
                    or not _matches(scope.content / name, record)):
                raise InstallError('Recovery completion manifest no longer matches installed bytes')
    if set(value['staged']) != set(expected) or len(value['operations']) > MAX_FILES * 2:
        raise InstallError('Package recovery inventory is incomplete')
    for name, item in value['staged'].items():
        _relative(name)
        _relative(item['path'])
        record = {key: item[key] for key in ('pin', 'size', 'sha256')}
        _record(record)
        if not _matches(stage / item['path'], record):
            raise InstallError('Immutable recovery staging bytes or inode changed')
        if any(item[key] != expected[name][key] for key in ('size', 'sha256')):
            raise InstallError('Recovery staging differs from its complete snapshot')
    operations = set()
    for operation in value['operations']:
        _fields(operation, ('path', 'before', 'after', 'candidate', 'installed'))
        name = _relative(operation['path'])
        if name in operations or name not in set(expected) | set(_leaves(value['previous'])):
            raise InstallError('Package recovery operation exceeds declared ownership')
        operations.add(name)
        if operation['before'] != value['old_files'].get(name):
            raise InstallError('Recovery operation asserts ownership absent from the previous manifest')
        if operation['after'] is not None:
            _relative(operation['candidate'])
            if name not in expected or any(operation['after'][key] != expected[name][key] for key in ('size', 'sha256')):
                raise InstallError('Prepared replacement differs from the snapshot')
        elif name in expected or operation['before'] != value['old_files'].get(name):
            raise InstallError('Retirement is not owned by the previous inventory')
    for name in value['directories']:
        if name:
            _relative(name)
    for item in value['create']:
        _fields(item, ('path', 'candidate', 'pin'))
        if item['path']:
            _relative(item['path'])
        _relative(item['candidate'])
    scope.bind_ownership(set(old) | set(expected))
    for name, item in value['authored'].items():
        if not _matches(scope.content / _relative(name), item):
            raise InstallError('An authored registry input changed during the transaction')
    return value


def _apply(scope, value):
    """@cc [owner:fontanierh,label:correctness] recover-forward-owned-packages
    All Content mutations MUST follow a fsynced complete journal. Recovery MUST accept only the
    recorded before inode/bytes or the prepared replacement inode/bytes; unexplained changes MUST
    refuse. Retirement MUST unlink only exact prior-owned leaves, never a Content subtree.
    """
    stage = scope.stages / value['nonce']
    directories = value['directories']
    for item in value['create']:
        destination = scope.content / item['path'] if item['path'] else scope.content
        if os.path.lexists(destination):
            _same_directory(destination, item['pin'])
        else:
            parent = destination.parent
            if destination != scope.content:
                parent_name = str(PurePosixPath(item['path']).parent)
                parent_name = '' if parent_name == '.' else parent_name
                _same_directory(parent, directories[parent_name])
            else:
                _same_directory(parent, scope.project_pin)
            candidate = stage / item['candidate']
            _same_directory(candidate, item['pin'])
            _move_prepared(scope, candidate, item['path'], directories, item['pin'], directory=True)
        directories[item['path']] = _directory(destination)
        _save(scope.journal, value)
    scope.check(directories)
    for index, operation in enumerate(value['operations']):
        scope.check(directories)
        path = scope.content / operation['path']
        if operation['installed'] is not None:
            if operation['after'] is None:
                if os.path.lexists(path):
                    raise InstallError('Retired Content reappeared during recovery')
            elif not _matches(path, operation['installed']):
                raise InstallError('Installed Content changed during recovery')
            continue
        if operation['after'] is None:
            if os.path.lexists(path):
                if not _matches(path, operation['before']):
                    raise InstallError('Retirement target differs from its prior owned inode/bytes')
                _retire_owned(scope, operation['path'], directories, operation['before'])
            operation['installed'] = {'absent': True}
        else:
            candidate = stage / operation['candidate']
            if _matches(path, operation['after'], renamed=True):
                if os.path.lexists(candidate):
                    raise InstallError('Prepared inode exists at two conflicting paths')
            else:
                if operation['before'] is None:
                    if os.path.lexists(path):
                        raise InstallError('New package leaf would replace an unowned file')
                elif not _matches(path, operation['before']):
                    raise InstallError('Replacement target changed outside its transaction')
                if not _matches(candidate, operation['after']):
                    raise InstallError('Prepared replacement inode/bytes changed')
                _move_prepared(scope, candidate, operation['path'], directories,
                               operation['after'], operation['before'])
            operation['installed'] = _file(path)
        _save(scope.journal, value)
        print(f'package installation {index + 1}/{len(value["operations"])} leaves', flush=True)
    installed = {}
    expected = _leaves(value['snapshot'])
    for name, leaf in expected.items():
        installed[name] = _file(scope.content / name)
        if any(installed[name][key] != leaf[key] for key in ('size', 'sha256')):
            raise InstallError('Installed package inventory differs from the snapshot')
        if name in value['old_files'] and name not in {op['path'] for op in value['operations']}:
            if installed[name] != value['old_files'][name]:
                raise InstallError('An unchanged owned leaf was replaced during installation')
    for name in set(_leaves(value['previous'])) - set(expected):
        if os.path.lexists(scope.content / name):
            raise InstallError('A retired owned package leaf remains installed')
    scope.check(directories)
    value['phase'] = 'registry-pending'
    _save(scope.journal, value)
    return installed


def registry_catalog(scope, request):
    """A real index rebuild/query of the closed typed fixture format, never an Unreal claim."""
    scope.eligible()
    _same_directory(scope.content, request['content_pin'])
    leaves, _ = _tree(scope.content)
    catalog = {}
    for name in sorted(leaves):
        if name.endswith(('.uasset', '.umap')):
            logical = _leaf_package(name)
            if logical in catalog:
                raise InstallError('The registry found duplicate primary package ownership')
            catalog[logical] = dict(references=_primary(scope.content / name, logical), files={})
    for name in leaves:
        if not name.endswith(SUFFIXES):
            continue
        logical = _leaf_package(name)
        if logical not in catalog:
            raise InstallError('The registry found an orphan package sidecar')
        actual = _file(scope.content / name)
        catalog[logical]['files'][name] = {key: actual[key] for key in ('size', 'sha256')}
    for package in catalog.values():
        if any(ref not in catalog for ref in package['references']):
            raise InstallError('The rebuilt typed registry has an unresolved package reference')
    index = scope.out / '.package-install-registry.json'
    if os.path.lexists(index):
        prior_index = _read(index, private=True)
        _fields(prior_index, ('schema', 'backend', 'nonce', 'content_pin', 'packages'))
        if type(prior_index['schema']) is not int or prior_index['schema'] != 1 or prior_index['backend'] != BACKEND:
            raise InstallError('Registry index is not owned by the supported backend')
        index.unlink()
        _sync(scope.out)
    value = dict(schema=1, backend=BACKEND, nonce=request['nonce'],
                 content_pin=request['content_pin'], packages=catalog)
    _save(index, value)
    rebuilt = _read(index, private=True)
    _same_directory(scope.content, request['content_pin'])
    return dict(schema=1, backend=BACKEND, nonce=request['nonce'], repo=str(scope.repo), game=scope.game,
                content_pin=request['content_pin'], packages=rebuilt['packages'],
                observed_monotonic=time.monotonic())


def _query_registry(scope, value):
    from . import capacity_protocol as wire
    from .safety.process import spawn
    content_pin = _directory(scope.content)
    request = dict(schema=1, backend=BACKEND, nonce=value['nonce'], repo=str(scope.repo), game=scope.game,
                   content_pin=content_pin, parent=[os.getpid(), wire.process_start(os.getpid())])
    process = spawn([sys.executable, '-m', 'atelier.build_install_worker', 'registry'],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        child = [process.pid, wire.process_start(process.pid)]
        request['child'] = child
        output, _ = process.communicate(_encode(request), timeout=15)
        if process.returncode:
            raise InstallError('The supported registry process refused its bound observation')
        result = _decode(output)
        if result.get('child') != child or result.get('parent') != request['parent']:
            raise InstallError('The registry response belongs to another process')
        return _validate_registry(scope, value, result, content_pin)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=2)


def _validate_registry(scope, value, result, content_pin):
    """@cc [owner:fontanierh,label:correctness] bound-positive-package-registry
    Completion MUST require a concrete supported registry observation bound to the transaction,
    checkout, Content inode and actual package inventory. Every new package MUST be observed and
    every retired generated package absent. A callback boolean, copy or stale index MUST NOT suffice.
    """
    _fields(result, ('schema', 'backend', 'nonce', 'repo', 'game', 'content_pin', 'packages',
                     'observed_monotonic', 'parent', 'child'))
    observed = result['observed_monotonic']
    if (type(result['schema']) is not int or result['schema'] != 1 or result['backend'] != BACKEND
            or result['nonce'] != value['nonce'] or result['repo'] != str(scope.repo)
            or result['game'] != scope.game or result['content_pin'] != content_pin
            or type(observed) not in (int, float) or not math.isfinite(observed)
            or not 0 <= time.monotonic() - observed <= 15 or type(result['packages']) is not dict):
        raise InstallError('Registry readiness observation is stale or belongs to another transaction')
    _same_directory(scope.content, content_pin)
    expected = {package['name']: package for package in value['snapshot']['packages']}
    actual_names = [_package(name) for name in result['packages']]
    if len({name.casefold() for name in actual_names}) != len(actual_names):
        raise InstallError('Registry package names contain case aliases')
    retired = {package['name'].casefold() for package in value['previous']['packages']} - {name.casefold() for name in expected}
    if retired & {name.casefold() for name in actual_names} or not expected.keys() <= result['packages'].keys():
        raise InstallError('Registry package presence/retirement differs from the snapshot')
    for name, package in expected.items():
        found = result['packages'][name]
        if (type(found) is not dict or found.get('references') != package['references']
                or found.get('files') != {leaf['path']: {key: leaf[key] for key in ('size', 'sha256')}
                                         for leaf in package['files']}):
            raise InstallError('Registry package inventory or references differ from the installed snapshot')
    return result


def _execute(scope, plan=None, source=None, *, resume=False, nonce=None):
    """Internal worker protocol. The public caller supplies the owned guarded lifecycle."""
    scope.eligible()
    selected = Path(os.environ.get('ATELIER_BUILD_ROOT') or scope.repo / 'build') / scope.game
    for root in {scope.out, selected}:
        for marker in (build_snapshot.JOURNAL, build_snapshot.PORTABLE_JOURNAL):
            if os.path.lexists(root / marker):
                raise InstallError('Another snapshot transaction blocks package installation')
        if root != scope.out and os.path.lexists(root / build_snapshot.PACKAGE_JOURNAL):
            raise InstallError('Another package transaction blocks package installation')
    value = _journal(scope) if resume else _prepare(scope, snapshot(plan), source, nonce=nonce)
    installed = _apply(scope, value)
    print('package registry: rebuilding and querying the supported index', flush=True)
    observation = _query_registry(scope, value)
    _validate_registry(scope, value, observation, _directory(scope.content))
    for name, expected in installed.items():
        if not _matches(scope.content / name, expected):
            raise InstallError('Installed Content changed after registry observation')
    for name, expected in value['authored'].items():
        if not _matches(scope.content / name, expected):
            raise InstallError('Authored registry inputs changed after observation')
    scope.check(value['directories'])
    current = dict(schema=1, repo=str(scope.repo), game=scope.game, snapshot=value['snapshot'],
                   files=installed, transaction=value['nonce'])
    _save(scope.current, current)
    _save(scope.receipt, dict(schema=1, nonce=value['nonce'], snapshot_sha256=value['snapshot_sha256'],
                              registry=observation, current_sha256=_digest(current)))
    value['phase'] = 'complete'
    _save(scope.journal, value)
    scope.journal.unlink()
    _sync(scope.out)
    return current


def _guarded(game, plan=None, source=None, *, resume=False, timeout=300):
    """The only installation entry owns one normal checkout mutation/admission lifecycle."""
    from . import capacity_protocol as wire
    from .safety import guarded
    from .safety.worker_binding import WorkerBinding, require_legacy
    require_legacy()
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 1 <= timeout <= 3600:
        raise InstallError('Package worker requires a finite bounded deadline')
    scope = Scope(paths.REPO, game)
    scope.eligible()
    value = _journal(scope) if resume else None
    if not resume:
        plan = snapshot(plan)
        source = Path(source).absolute()
        source_pin = _directory(source)
    else:
        plan = value['snapshot']
        source_pin = None
    nonce = uuid.uuid4().hex
    spec = dict(schema=1, operation='recover' if resume else 'install', nonce=nonce,
                parent=[os.getpid(), wire.process_start(os.getpid())], repo=str(scope.repo), game=game,
                snapshot=plan, snapshot_sha256=_digest(plan), source=None if resume else str(source),
                source_pin=source_pin, transaction=nonce if value is None else value['nonce'])
    fd, name = tempfile.mkstemp(prefix='.package-worker-', dir=scope.out)
    descriptor = None
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(_encode(spec))
            stream.flush()
            os.fchmod(stream.fileno(), 0o400)
            os.fsync(stream.fileno())
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW)
        os.unlink(name)
        _sync(scope.out)
        binding = WorkerBinding(spec['nonce'], _digest(spec), scope.repo)
        command = [sys.executable, '-m', 'atelier.build_install_worker', 'install', str(descriptor), str(binding.descriptor)]
        folder = scope.out / 'package-install.guard'
        with binding:
            code = guarded.run(command, folder, purpose='package installation', aggregate_tree=True,
                               limit_gib=1., timeout=timeout, pass_fds=(descriptor, binding.descriptor),
                               performance=True, worker_binding=binding)
        if code:
            raise InstallError('Guarded package worker failed; preserve its journal and stage for recovery')
        if os.path.lexists(scope.journal):
            raise InstallError('Package worker exited without completing registry readiness')
        current, receipt = _read(scope.current, private=True), _read(scope.receipt, private=True)
        if (current.get('transaction') != spec['transaction'] or current.get('snapshot') != plan
                or receipt.get('nonce') != spec['transaction'] or receipt.get('snapshot_sha256') != _digest(plan)
                or receipt.get('current_sha256') != _digest(current)):
            raise InstallError('Package worker completion is stale or belongs to another invocation')
        return current
    finally:
        if descriptor is not None:
            os.close(descriptor)
        Path(name).unlink(missing_ok=True)


def install(game, snapshot_path, source_root, *, timeout=300):
    """Install an eligible snapshot through one legacy guarded worker; native/broker modes refuse."""
    from .safety.worker_binding import require_legacy
    require_legacy()
    return _guarded(game, _read(Path(snapshot_path)), source_root, timeout=timeout)


def recover(game, *, timeout=300):
    """Roll the exact durable transaction forward under fresh normal admission."""
    return _guarded(game, resume=True, timeout=timeout)
