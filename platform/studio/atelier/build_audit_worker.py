"""PEP 578 observer for one Python build action; launched by build_audit, never imported by recipes.

This catches Python filesystem accesses, not arbitrary native I/O, metadata values or environment
dependencies. It is a recipe diagnostic, not a security boundary against hostile Python code.
"""
import functools
import importlib._bootstrap as bootstrap
import importlib._bootstrap_external as external
import json
import os
from pathlib import Path
import runpy
import sys
import threading


class Observer:
    """@cc [owner:fontanierh,label:correctness] sticky-build-access-violations
    Observed undeclared reads and writes outside owned products/private scratch MUST remain failures
    even if the recipe catches their exceptions. The launcher MUST empty owned outputs before this
    worker runs, so previous output bytes and metadata cannot become inputs.
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
        self.seen = set()
        self.failed = False
        self.local = threading.local()
        self.lock = threading.RLock()

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
        label = self.label(path) if path is not None else None
        item = (operation, label, reason)
        with self.lock:
            if reason:
                self.failed = True
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
        return (any(path == p and (not directory or is_dir) or is_dir and path.is_relative_to(p)
                    for p, is_dir in self.inputs)
                or any(path.is_relative_to(p) for p in self.runtime))

    def read(self, path, *, directory=False, metadata=False):
        operation = 'metadata' if metadata else 'list' if directory else 'read'
        if self.covered(path, directory=directory):
            return self.record(operation, path)
        if self.owns(path):
            return self.record(operation, path)
        if metadata and any(path in p.parents for p in self.outputs):
            return self.record(operation, path)
        self.record(operation, path, 'not a declared input/read product or a newly written output')

    def write(self, path, *, mkdir=False):
        allowed = self.owns(path) or mkdir and any(path in p.parents for p in self.outputs)
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
            importing = (frame.f_code is external.FileFinder._fill_cache.__code__
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
            self.read(self.path(path, kwargs.get('dir_fd')), metadata=True)
            return function(path, *args, **kwargs)
        finally:
            self.local.busy = False

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


def main(config):
    spec = json.loads(Path(config).read_text())
    observer = Observer(spec)
    script = spec['script']
    sys.argv = [script, *spec['args']]
    sys.path[0] = str(Path(script).parent)
    sys.dont_write_bytecode = True
    # Import runpy's helper before installing the observer; its subsequent target/module reads
    # still pass through the hook. The prefix was also set before interpreter startup.
    import pkgutil  # noqa: F401
    observer.send('start')
    observer.install()
    succeeded = False
    try:
        runpy.run_path(script, run_name='__main__')
        succeeded = True
    except SystemExit as error:
        succeeded = error.code in (None, 0)
        if not succeeded:
            raise
    finally:
        if any(t is not threading.current_thread() and t.is_alive() for t in threading.enumerate()):
            observer.failed = True
            observer.send('access', operation='threads', path=None, violation='action returned with live Python threads')
        observer.send('complete', success=succeeded and not observer.failed)
    if observer.failed:
        raise SystemExit('Input audit failed; see the action audit report')


if __name__ == '__main__':
    main(sys.argv[1])
