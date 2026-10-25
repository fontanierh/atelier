"""Independent APFS clones of one SDK group's identical unpacked recipe ROOTs.

A batch can unpack the same large archive into many job views. ``materialize`` stands in for a view's unpack:
the first directory ROOT of an archive digest is byte-unpacked once and becomes a private snapshot, and later
ones are built only from independent clones of it. ``share`` instead replaces the files of a ROOT that was
already unpacked. Either way the copies share storage until written. It is execution context for one group:
never adopted, never persistent CAS.
"""
import ctypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tarfile

if __package__:
    from . import recipe_job
else:  # NativeTool loads frozen helpers as top-level siblings: bind only the adjacent codec file.
    _spec = importlib.util.spec_from_file_location('atelier_root_clones_root_codec', Path(__file__).with_name('recipe_job.py'))
    recipe_job = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(recipe_job)

MANIFEST_LIMIT = 16 * 1024 * 1024


def _clonefile():
    if sys.platform != 'darwin':
        return None
    function = ctypes.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True).clonefile
    function.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    function.restype = ctypes.c_int
    def clone(source, destination):
        if function(os.fsencode(source), os.fsencode(destination), 0) != 0:
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error), str(destination))
    return clone


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns, stat.S_IMODE(info.st_mode))


def _forward(function, *args, check_cancelled=None):
    """Call the codec or inventory with the caller's cancellation check, or exactly as before without one."""
    return function(*args) if check_cancelled is None else function(*args, check_cancelled=check_cancelled)


def _read_authority(archive, *, check_cancelled=None):
    """(sha256, decoded manifest) of one stable archive, read through a single descriptor.

    The archive is a canonical absolute path without linked ancestors, naming one ordinary single-link file
    whose named and opened identities stay equal before and after reading.
    """
    archive = Path(archive)
    if not archive.is_absolute() or archive.resolve() != archive:
        raise ValueError('recipe root archive is not a canonical unlinked path')
    named = archive.lstat()
    if not stat.S_ISREG(named.st_mode) or named.st_nlink != 1:
        raise ValueError('recipe root archive is not an ordinary single-link file')
    fd = os.open(archive, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if _identity(before) != _identity(named):
            raise ValueError('recipe root archive changed while opening')
        hasher = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            if check_cancelled is not None:
                check_cancelled()
            hasher.update(chunk)
        stream.seek(0)
        with tarfile.open(fileobj=stream, mode='r:') as tar:
            first = tar.next()
            if (first is None or first.name != recipe_job.MANIFEST or not first.isreg()
                    or first.size > MANIFEST_LIMIT):
                raise ValueError('missing bounded root manifest')
            manifest = json.loads(tar.extractfile(first).read())
        after = os.fstat(stream.fileno())
    if not (_identity(before) == _identity(after) == _identity(archive.lstat())) or after.st_nlink != 1:
        raise ValueError('recipe root archive changed while reading')
    if (not isinstance(manifest, dict) or set(manifest) != {'version', 'kind', 'entries'} or manifest['version'] != 1
            or not isinstance(manifest['entries'], list)):
        raise ValueError('invalid root manifest')
    return hasher.hexdigest(), manifest


def _directory_rows(manifest):
    if not manifest['entries'] or manifest['kind'] != 'directory':
        raise ValueError('invalid shareable root manifest')
    rows = []
    for row in manifest['entries']:
        if not isinstance(row, list) or len(row) != 5:
            raise ValueError('invalid root member')
        name, kind, size, mode, digest = row
        if name:
            recipe_job.relative(name)
        if (kind, mode) not in (('directory', 0o755), ('file', 0o644), ('file', 0o755)):
            raise ValueError('root member has an unsupported kind or mode')
        rows.append(tuple(row))
    if rows[0][:2] != ('', 'directory'):
        raise ValueError('shareable root must be a directory')
    return rows


def archive_authority(archive):
    """(sha256, manifest rows) of one stable directory-ROOT archive."""
    key, manifest = _read_authority(archive)
    return key, _directory_rows(manifest)


class CommonRootClones:
    """@cc [owner:fontanierh,label:correctness;safety] verified-common-root-clones
    Reuse MUST key on the actual archive bytes' digest and its complete manifest, never on Item identity.
    The snapshot of a digest MUST come from a directory ROOT that inventories exactly to that manifest: for
    ``materialize``, the original codec's validated unpack; for ``share``, the current ROOT, proven first. It is
    a private immutable snapshot inside this instance's own fresh scope. A later ``materialize`` of the same
    digest MUST build its fresh destination only from independent clones carrying the manifest modes, never
    unpacking or copying bytes, and MUST inventory exactly to the manifest before it is returned. A later
    ``share`` MUST replace only that ROOT's own equivalent regular files with such clones and re-inventory.
    File and absent ROOTs MUST keep the original codec. Destinations overlapping the scope or archive, changed,
    aliased or malformed archives, ROOTs or snapshots, and any clone failure, MUST refuse before writing, without
    a byte-copy fallback, links or changes outside the ROOT's own files.
    """
    def __init__(self, scope, *, inventory=recipe_job.inventory, clone=None):
        scope = Path(scope)
        parent = scope.parent
        if (not scope.is_absolute() or '..' in scope.parts or parent.resolve() != parent
                or not parent.is_dir() or parent.stat().st_uid != os.getuid()):
            raise ValueError('root clone scope needs a canonical owned parent')
        scope.mkdir(mode=0o700)  # Fresh: never adopt an earlier or foreign scope.
        self.scope, self.inventory = scope, inventory
        self._binding = self._observed()
        self.clone = clone if clone is not None else _clonefile()
        self.snapshots = {}  # archive digest -> (rows, {name: identity})

    def _observed(self):
        parent, scope = self.scope.parent.lstat(), self.scope.lstat()
        if not stat.S_ISDIR(parent.st_mode) or not stat.S_ISDIR(scope.st_mode) or scope.st_uid != os.getuid():
            raise ValueError('root clone scope is not an owned directory')
        return (parent.st_dev, parent.st_ino), (scope.st_dev, scope.st_ino)

    def _check_scope(self):
        """The exact fresh scope this instance created, reached without any linked ancestor."""
        try:
            same = self.scope.resolve() == self.scope and self._observed() == self._binding
        except OSError:
            same = False
        if not same:
            raise ValueError('root clone scope was replaced or aliased')

    def _canonical_root(self, root, archive):
        root, archive = Path(root), Path(archive)
        if not root.is_absolute() or root.resolve() != root or root.is_symlink() or not root.is_dir():
            raise ValueError('shared root is not a canonical directory')
        for other in (self.scope, archive.resolve()):
            if root == other or root.is_relative_to(other) or other.is_relative_to(root):
                raise ValueError('shared root aliases the clone scope or its archive')
        return root

    def _verify_snapshot(self, key):
        rows, identities = self.snapshots[key]
        snapshot = self.scope / key / 'root'
        found = {}
        for path in [snapshot, *snapshot.rglob('*')]:
            info = path.lstat()
            name = path.relative_to(snapshot).as_posix() if path != snapshot else ''
            if stat.S_ISDIR(info.st_mode):
                found[name] = None
            elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                found[name] = _identity(info)
            else:
                raise ValueError('common root snapshot contains a link or special file')
        if found != identities:
            raise ValueError('common root snapshot changed')

    def _snapshot(self, key, root, rows, *, check_cancelled=None):
        if self.clone is None:
            raise ValueError('independent clones are unavailable on this volume')
        snapshot = self.scope / key / 'root'
        self._check_scope()
        snapshot.parent.mkdir(mode=0o700)
        try:
            directories = []
            for name, kind, _, mode, _ in rows:
                target = snapshot / name if name else snapshot
                if kind == 'directory':
                    target.mkdir(mode=0o700)
                    directories.append(target)
                else:
                    if check_cancelled is not None:
                        check_cancelled()
                    self.clone(root / name, target)
                    target.chmod(0o555 if mode == 0o755 else 0o444)
            for directory in reversed(directories):
                directory.chmod(0o555)
            identities = {}
            for name, kind, *_ in rows:
                identities[name] = None if kind == 'directory' else _identity((snapshot / name).lstat())
            self.snapshots[key] = (rows, identities)
            if [tuple(row) for row in _forward(self.inventory, snapshot, check_cancelled=check_cancelled)] != rows:
                raise ValueError('common root snapshot differs from its manifest')
        except BaseException:
            self.snapshots.pop(key, None)
            self._remove(snapshot.parent)
            raise

    def share(self, archive, root):
        self._check_scope()
        key, rows = archive_authority(archive)
        root = self._canonical_root(root, archive)
        current = [tuple(row) for row in self.inventory(root)]
        if current != rows:
            raise ValueError('shared root differs from its archive manifest')
        files = [(name, size, mode) for name, kind, size, mode, _ in rows if kind == 'file']
        if key not in self.snapshots:
            self._snapshot(key, root, rows)
            return {'archive': key, 'snapshot': 'created', 'files': len(files), 'bytes': sum(s for _, s, _ in files)}
        if self.snapshots[key][0] != rows:
            raise ValueError('archive digest names another manifest')
        self._check_scope()
        self._verify_snapshot(key)
        observed = {name: _identity((root / name).lstat()) for name, _, _ in files}
        if [tuple(row) for row in self.inventory(root)] != rows:
            raise ValueError('shared root changed while being observed')
        snapshot = self.scope / key / 'root'
        for name, _, mode in files:
            target = root / name
            temporary = target.with_name('.atelier-clone-' + target.name)
            if os.path.lexists(temporary):
                raise ValueError('shared root already holds a clone temporary')
            self.clone(snapshot / name, temporary)
            try:
                temporary.chmod(mode)
                if _identity(target.lstat()) != observed[name]:
                    raise ValueError('shared root file changed before replacement')
                os.replace(temporary, target)
            except BaseException:
                temporary.unlink(missing_ok=True)
                raise
        if [tuple(row) for row in self.inventory(root)] != rows:
            raise ValueError('shared root differs from its manifest after cloning')
        return {'archive': key, 'snapshot': 'reused', 'files': len(files), 'bytes': sum(s for _, s, _ in files)}

    def materialize(self, archive, destination, *, check_cancelled=None):
        """Create a fresh verified ROOT at ``destination`` from ``archive``, for the view's own input.

        File and absent ROOTs keep the original codec. The first directory ROOT of an archive digest is
        byte-unpacked by the original codec, then becomes the snapshot; later ones are independent clones of
        that snapshot with their manifest modes, never unpacked or copied again, and must inventory exactly.
        ``check_cancelled`` (raising to cancel) is called per archive hash chunk and repeated clone member, and
        forwarded to the codec and inventory; without it they are invoked exactly as before.
        """
        self._check_scope()
        destination = Path(destination)
        parent = destination.parent
        if (not destination.is_absolute() or os.path.lexists(destination) or parent.resolve() != parent
                or not parent.is_dir()):
            raise ValueError('materialized root needs a fresh destination under a canonical directory')
        for other in (self.scope, Path(archive)):  # Refused for every kind, before anything is written.
            if destination == other or destination.is_relative_to(other) or other.is_relative_to(destination):
                raise ValueError('materialized root aliases the clone scope or its archive')
        key, manifest = _read_authority(archive, check_cancelled=check_cancelled)
        if manifest['kind'] in ('file', 'absent'):  # Unshared: the original codec, unchanged.
            _forward(recipe_job.unpack_root, archive, destination, check_cancelled=check_cancelled)
            return {'archive': key, 'snapshot': 'none', 'files': 0, 'bytes': 0}
        rows = _directory_rows(manifest)
        files = [(name, size, mode) for name, kind, size, mode, _ in rows if kind == 'file']
        stats = {'archive': key, 'files': len(files), 'bytes': sum(size for _, size, _ in files)}
        if key not in self.snapshots:
            try:
                _forward(recipe_job.unpack_root, archive, destination, check_cancelled=check_cancelled)
                if [tuple(row) for row in _forward(self.inventory, destination, check_cancelled=check_cancelled)] != rows:
                    raise ValueError('unpacked root differs from its archive manifest')
                self._snapshot(key, destination, rows, check_cancelled=check_cancelled)
            except BaseException:
                shutil.rmtree(destination, ignore_errors=True)  # Only the fresh destination this call created.
                raise
            return {**stats, 'snapshot': 'created'}
        if self.snapshots[key][0] != rows:
            raise ValueError('archive digest names another manifest')
        self._verify_snapshot(key)
        if self.clone is None:
            raise ValueError('independent clones are unavailable on this volume')
        snapshot = self.scope / key / 'root'
        destination.mkdir(mode=0o755)
        try:
            for name, kind, _, mode, _ in rows[1:]:
                if kind == 'directory':
                    (destination / name).mkdir(mode=0o755)
                else:
                    if check_cancelled is not None:
                        check_cancelled()
                    self.clone(snapshot / name, destination / name)
                    (destination / name).chmod(mode)
            self._check_scope()
            self._verify_snapshot(key)
            if [tuple(row) for row in _forward(self.inventory, destination, check_cancelled=check_cancelled)] != rows:
                raise ValueError('materialized root differs from its archive manifest')
        except BaseException:
            shutil.rmtree(destination, ignore_errors=True)  # Only the fresh destination this call created.
            raise
        return {**stats, 'snapshot': 'reused'}

    def _remove(self, path):
        """Remove part of this instance's own verified scope; links are unlinked, never followed."""
        path = Path(path)
        self._check_scope()
        if path != self.scope and not path.is_relative_to(self.scope):
            raise ValueError('root clone removal is outside its own scope')
        if not os.path.lexists(path):
            return
        if path.is_symlink() or path.resolve() != path:
            raise ValueError('root clone removal reached a link')
        for folder, directories, _ in os.walk(path):
            os.chmod(folder, 0o700, follow_symlinks=False)
            for directory in directories:
                child = os.path.join(folder, directory)
                if not os.path.islink(child):
                    os.chmod(child, 0o700, follow_symlinks=False)
        self._check_scope()
        shutil.rmtree(path)

    def discard(self):
        """Remove only this instance's own scope; the shared roots' clones stay independent."""
        self._remove(self.scope)
        self.snapshots.clear()
