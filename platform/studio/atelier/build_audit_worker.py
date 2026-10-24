"""PEP 578 observer for one Python build action; launched by build_audit, never imported by recipes.

This catches Python filesystem accesses, not arbitrary native I/O, metadata values or environment
dependencies. It is a recipe diagnostic, not a security boundary against hostile Python code.
"""
# ctypes initializes CPython's own library handle with PyDLL(None). Prepare that
# managed stdlib state before observing an action, as we do for runpy's helpers.
# The action's later ctypes loads and symbol lookups still emit refused events.
import ctypes  # noqa: F401
import functools
import importlib._bootstrap as bootstrap
import importlib._bootstrap_external as external
import json
import os
from pathlib import Path
import runpy
import shutil
import stat
import sys
import threading


class Observer:
    """@cc [owner:fontanierh,label:correctness] sticky-build-access-violations
    Observed undeclared reads and writes outside owned products/private scratch MUST remain failures
    even if the recipe catches their exceptions. This worker MUST empty owned outputs before
    installing its observer and running the action, so previous bytes and metadata cannot become inputs.
    """
    def __init__(self, spec):
        self.spec = spec
        self.inputs = [(Path(p), directory) for p, directory in spec['inputs']]
        self.outputs = [Path(p) for p in spec['outputs']]
        self.runtime = [Path(p) for p in spec['runtime']]
        self.scratch = Path(spec['scratch'])
        self.file_finder = external.FileFinder.find_spec
        self.import_roots = {Path(p or '.').resolve() for p in sys.path}
        self.import_roots.update(p.parent for p, directory in self.inputs if not directory)
        # Namespace search may start above a declared Python module. These roots
        # authorize ONLY the retained actual import resolver's directory probes;
        # module contents, namespace packages and direct IO still pass read().
        self.import_roots.update(parent for p, directory in self.inputs
                                 if not directory and p.suffix == '.py' for parent in p.parents)
        self.fill_cache_code = external.FileFinder._fill_cache.__code__
        self.seen = set()
        self.failed = False
        self.first_refusal = None
        self.sealed = False
        self.local = threading.local()
        self.lock = threading.RLock()
        self.resolve_code = Path.resolve.__code__
        self.realpath_codes = {getattr(getattr(os.path, name, None), '__code__', None)
                               for name in ('realpath', '_joinrealpath', '_realpath')}
        self.realpath_codes.discard(None)
        self.directory_guard_code = None
        helper = Path(__file__).with_name('export_manifest.py')
        if (helper, False) in self.inputs:
            # This named framework helper is already a declared code input. Load
            # it through the active captured loader BEFORE installing the observer,
            # then retain its actual code/global/builtin identities, never a name.
            import builtins
            import types
            from atelier.export_manifest import real_directory
            if (type(real_directory) is types.FunctionType
                    and real_directory.__code__.co_filename == str(helper)
                    and real_directory.__globals__.get('Path') is Path
                    and real_directory.__globals__.get('stat') is stat):
                self.directory_guard_code = real_directory.__code__
                self.directory_guard_globals = {'Path': Path, 'stat': stat}
                self.directory_guard_builtins = {name: getattr(builtins, name) for name in
                                                 ('reversed', 'FileNotFoundError', 'ValueError')}
        self.metadata_codes = {Path.stat.__code__, Path.lstat.__code__}


    # Kernel device nodes are not recipe inputs. CPython reads entropy to name a temporary file
    # and libraries seed themselves from it; macOS reaches the same entropy through getentropy
    # without opening a file, so only Linux reports it here. Discarding an action's output is the
    # one write outside its products that no recipe can depend on.
    READABLE_DEVICES = frozenset({'/dev/urandom', '/dev/random'})
    WRITABLE_DEVICES = frozenset({'/dev/null'})

    def send(self, kind, **values):
        line = json.dumps({'kind': kind, 'nonce': self.spec['nonce'], **values}) + '\n'
        with self.lock:
            data = line.encode()
            while data:
                data = data[os.write(self.spec['fd'], data):]

    def label(self, path):
        for root, label in self.spec['labels']:
            if path.is_relative_to(root):
                return f'<{label}>/{path.relative_to(root).as_posix()}'
        return f'<external>/{path.name}'

    def record(self, operation, path=None, reason=None):
        if self.sealed:
            reason = 'Python access after action completion; host must exit before another action'
        label = self.label(path) if path is not None else None
        item = (operation, label, reason)
        with self.lock:
            if reason:
                self.failed = True
                if self.first_refusal is None:
                    self.first_refusal = f'{operation} {label or ""}: {reason}'.strip()
            if item not in self.seen:
                if len(self.seen) >= 20000:
                    self.failed = True
                    raise RuntimeError('Input audit exceeded 20000 distinct accesses')
                self.seen.add(item)
                self.send('access', operation=operation, path=label, violation=reason)
        if reason:
            raise PermissionError(f'Input audit: {operation} {label or ""}: {reason}')

    def path(self, value, dir_fd=None):
        if isinstance(value, int) or dir_fd not in (None, -1):
            self.record('descriptor access', reason='opaque file descriptors are unsupported')
        if value is None:
            value = '.'
        previous = getattr(self.local, 'busy', False)
        self.local.busy = True
        try:
            return Path(os.fsdecode(value)).resolve()
        finally:
            self.local.busy = previous

    def owns(self, path):
        return path.is_relative_to(self.scratch) or any(path.is_relative_to(p) for p in self.outputs)

    def covered(self, path, *, directory=False):
        # Blender's managed tool identity excludes ambient __pycache__. Native hosts may ignore
        # Python startup environment flags, so these bytes never gain a runtime exemption.
        runtime = any(path.is_relative_to(p) and ('host' not in self.spec
                      or '__pycache__' not in path.relative_to(p).parts) for p in self.runtime)
        return (any(path == p and (not directory or is_dir) or is_dir and path.is_relative_to(p)
                    for p, is_dir in self.inputs)
                or runtime)

    def read(self, path, *, directory=False, metadata=False):
        operation = 'metadata' if metadata else 'list' if directory else 'read'
        if str(path) in self.READABLE_DEVICES:
            return self.record(operation, path)
        if self.covered(path, directory=directory):
            return self.record(operation, path)
        if self.owns(path):
            return self.record(operation, path)
        if metadata and any(path in p.parents for p in self.outputs):
            return self.record(operation, path)
        self.record(operation, path, 'not a declared input/read product or a newly written output')

    def write(self, path, *, mkdir=False):
        allowed = (self.owns(path) or str(path) in self.WRITABLE_DEVICES
                   or mkdir and any(path in p.parents for p in self.outputs))
        self.record('mkdir' if mkdir else 'write', path,
                    None if allowed else 'outside owned products and private scratch')

    def hook(self, event, args):
        if getattr(self.local, 'busy', False):
            return
        self.local.busy = True
        try:
            self.observe(event, args)
        finally:
            self.local.busy = False

    def observe(self, event, args):
        if event == 'import' and args[1] is not None:
            # ExtensionFileLoader does not open a shared library through Python's open event.
            # CPython reports its filename here before loading it, so its bytes still need a key.
            self.read(self.path(args[1]))
        elif event == 'open':
            value, _, flags = args
            path = self.path(value)
            writing = flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            if writing:
                self.write(path)
            if not writing or flags & os.O_RDWR and not flags & os.O_TRUNC:
                self.read(path)
        elif event in ('os.listdir', 'os.scandir'):
            path = self.path(args[0])
            # CPython's import finder lists search directories before opening a module. These are
            # resolver probes, not recipe directory queries; actual module reads are still checked.
            frame = sys._getframe(2)
            importing = (frame.f_code is self.fill_cache_code
                         and frame.f_back is not None and frame.f_back.f_code is self.file_finder.__code__
                         and getattr(self.local, 'resolving', False) and path in self.import_roots)
            if importing:
                self.record('import search', path)
            else:
                self.read(path, directory=True)
        elif event in ('os.remove', 'os.rmdir', 'os.chmod', 'os.utime', 'os.truncate'):
            index = {'os.remove': 1, 'os.rmdir': 1, 'os.chmod': 2, 'os.utime': 3}.get(event)
            path = self.path(args[0], args[index] if index is not None else None)
            self.write(path)
        elif event == 'os.mkdir':
            path = self.path(args[0], args[2])
            self.write(path, mkdir=True)
        elif event == 'os.rename':
            source, target = self.path(args[0], args[2]), self.path(args[1], args[3])
            self.read(source)
            self.write(source)
            self.write(target)
        elif event == 'os.chdir':
            self.read(self.path(args[0]), directory=True)
        elif event in ('os.putenv', 'os.unsetenv', 'os.walk'):
            pass  # Environment values are outside this audit; walk's actual listings are checked.
        elif event.startswith(('os.', 'subprocess.', 'socket.', 'ctypes.', 'mmap.', 'sqlite3.')):
            self.record(event, reason='unsupported mechanism; it can escape Python input observation')

    def checked_metadata(self, function, path, *args, **kwargs):
        if getattr(self.local, 'busy', False):
            return function(path, *args, **kwargs)
        self.local.busy = True
        try:
            checked = self.path(path, kwargs.get('dir_fd'))
            if self.input_resolution_metadata(checked):
                self.record('input resolution metadata', checked)
            elif self.declared_directory_metadata(checked):
                self.record('input directory validation metadata', checked)
            else:
                self.read(checked, metadata=True)
            return function(path, *args, **kwargs)
        finally:
            self.local.busy = False

    def input_resolution_metadata(self, path):
        """@cc [owner:fontanierh,label:correctness;safety] declared-input-resolver-metadata
        Only the retained actual stdlib resolver code chain normalizing one exact
        declared input MAY inspect its ancestor metadata. This MUST NOT grant parent
        directory data/listing/write permission; direct metadata calls, replaced
        resolver code and unknown targets MUST retain the original refusal. See
        test_build_audit.py declared-script and resolver-boundary regressions.
        """
        frame = sys._getframe(2)
        if frame.f_code not in self.realpath_codes:
            return False
        for _ in range(8):
            if frame is None:
                return False
            if frame.f_code not in self.realpath_codes:
                break
            frame = frame.f_back
        if frame is None or frame.f_code is not self.resolve_code:
            return False
        target = frame.f_locals.get('self')
        if type(target) is not type(self.scratch) or not target.is_absolute():
            return False
        return any(target == source and path in source.parents for source, _ in self.inputs)

    def declared_directory_metadata(self, path):
        """@cc [owner:fontanierh,label:correctness;safety] declared-directory-validation-metadata
        Only the retained actual declared framework directory validator through
        original pathlib stat/lstat code MAY inspect ancestor metadata for an EXACT
        declared directory input. Its code/globals/builtins MUST remain bound;
        unknown targets, direct calls, replacement helpers and directory listing,
        contents or writes MUST retain the original checks. This is no input grant.
        """
        if self.directory_guard_code is None:
            return False
        frame = sys._getframe(2)
        for _ in range(4):
            if frame is None or frame.f_code not in self.metadata_codes:
                break
            frame = frame.f_back
        if frame is None or frame.f_code is not self.directory_guard_code:
            return False
        if (any(frame.f_globals.get(name) is not value for name, value in self.directory_guard_globals.items())
                or any(frame.f_globals.get(name, frame.f_builtins.get(name)) is not value
                       for name, value in self.directory_guard_builtins.items())):
            return False
        target = frame.f_locals.get('path')
        if type(target) is not type(self.scratch) or not target.is_absolute():
            return False
        return any(directory and target == source and path in source.parents
                   for source, directory in self.inputs)

    def checked_open(self, function, path, *args, **kwargs):
        # CPython's open event omits dir_fd. Check that argument before letting os.open emit it.
        if kwargs.get('dir_fd') is not None:
            self.record('descriptor access', reason='dir_fd opens are unsupported')
        return function(path, *args, **kwargs)

    def checked_find_spec(self, function, fullname, path=None, target=None):
        # A real import calls PathFinder from _find_spec inside _find_and_load_unlocked. Resolver-only
        # queries must not infer undeclared membership, even after FileFinder has cached a listing.
        caller = sys._getframe(1)
        if (caller.f_code is not bootstrap._find_spec.__code__ or caller.f_back is None
                or caller.f_back.f_code is not bootstrap._find_and_load_unlocked.__code__):
            self.record('module lookup', reason='resolver-only queries are unsupported by this audit')
        # Only this verified lookup may use FileFinder's directory probes. An outer import frame
        # is insufficient: the imported module's body can itself issue a resolver-only query.
        previous = getattr(self.local, 'resolving', False)
        self.local.resolving = True
        try:
            spec = function(fullname, path, target)
        finally:
            self.local.resolving = previous
        if spec is not None and spec.origin is None:
            for folder in spec.submodule_search_locations or ():
                self.read(self.path(folder), directory=True)
        return spec

    def install(self):
        @functools.wraps(self.file_finder)
        def find_spec(finder, *args, **kwargs):
            if (sys._getframe(1).f_code is not external.PathFinder._get_spec.__code__
                    or not getattr(self.local, 'resolving', False)):
                self.record('module lookup', reason='resolver-only queries are unsupported by this audit')
            return self.file_finder(finder, *args, **kwargs)

        sys.addaudithook(self.hook)
        for name in ('stat', 'lstat', 'access'):
            setattr(os, name, functools.partial(self.checked_metadata, getattr(os, name)))
        os.open = functools.partial(self.checked_open, os.open)
        external.PathFinder.find_spec = functools.partial(self.checked_find_spec, external.PathFinder.find_spec)
        external.FileFinder.find_spec = find_spec


def clear_outputs(outputs):
    """@cc [owner:fontanierh,label:safety] admitted-audit-output-cleanup
    Only the executing child MAY clear an audited action's owned outputs. Heavy actions MUST reach
    this worker through ordinary guarded admission. Cleanup MUST refuse root/ancestor symbolic links
    after the admission wait and MUST unlink old leaves without modifying other hard-link names.
    Removal MUST use a held parent descriptor without following ancestor or child links.
    Cleanup failure MUST prevent a complete audit report and certification.
    """
    roots = [Path(p) for p in outputs]

    def checked(root):
        if not root.is_absolute() or any(p.is_symlink() for p in (root, *root.parents)):
            raise RuntimeError('Linked or relative audit cleanup destination')

    for root in roots:
        checked(root)
    for root in roots:
        checked(root)
        parent = None
        try:
            try:
                parent = os.open(root.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                for component in root.parts[1:-1]:
                    child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                    os.close(parent)
                    parent = child
                mode = os.stat(root.name, dir_fd=parent, follow_symlinks=False).st_mode
            except FileNotFoundError:
                continue  # A missing owned root or parent is already empty.
            if stat.S_ISLNK(mode):
                raise RuntimeError('Linked audit cleanup destination')
            if stat.S_ISDIR(mode):
                if not shutil.rmtree.avoids_symlink_attacks:
                    raise RuntimeError('Audit cleanup requires descriptor-safe directory removal')
                shutil.rmtree(root.name, dir_fd=parent)
            else:
                os.unlink(root.name, dir_fd=parent)
        finally:
            if parent is not None:
                os.close(parent)
        checked(root)


def execute(spec, *, blender=False, before=None, after=None, execution_scope=None):
    """Execute once; the observer remains armed until this fresh process exits.

    ``before``/``after`` are framework-only checks, never recipe callbacks. Native adapters use
    them to validate preload provenance after managed imports and retain module-isolation checks.
    """
    clear_outputs(spec['outputs'])
    observer = Observer(spec)
    if 'host' in spec:
        sys._atelier_native_audit_started = observer
    script = spec['script']
    sys.argv = [script, *(['--'] if blender else []), *spec['args']]
    if 'host' in spec:
        sys.path.insert(0, str(Path(script).parent))
    else:
        sys.path[0] = str(Path(script).parent)
    sys.dont_write_bytecode = True
    sys.pycache_prefix = str(Path(spec['scratch']) / 'bytecode')
    # Import runpy's helper before installing the observer; its subsequent target/module reads
    # still pass through the hook. The prefix was also set before interpreter startup.
    import pkgutil  # noqa: F401
    if before is not None:
        before()
    observer.send('start')
    observer.install()
    succeeded = False
    try:
        from contextlib import nullcontext
        with (execution_scope(observer) if execution_scope is not None else nullcontext()):
            runpy.run_path(script, run_name='__main__')
        succeeded = True
    except SystemExit as error:
        succeeded = error.code in (None, 0)
        if not succeeded:
            raise
    finally:
        # The native module guard inspects dyld through ctypes. It is trusted framework work,
        # not recipe I/O; its exception still prevents a successful completion report.
        if after is not None:
            observer.local.busy = True
            try:
                after()
            except BaseException:
                succeeded = False
                raise
            finally:
                observer.local.busy = False
        if any(t is not threading.current_thread() and t.is_alive() for t in threading.enumerate()):
            observer.failed = True
            observer.send('access', operation='threads', path=None, violation='action returned with live Python threads')
        observer.send('complete', success=succeeded and not observer.failed)
        observer.sealed = True
    if observer.failed:
        # Name the refusal here too: this line is what the step log shows, and a hook error raised
        # while reporting another one can stay swallowed by CPython.
        raise SystemExit('Input audit failed: ' + (observer.first_refusal or 'no complete report'))


if __name__ == '__main__':
    execute(json.loads(Path(sys.argv[1]).read_text()))
