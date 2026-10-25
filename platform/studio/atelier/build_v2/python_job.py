"""Bootstrap for one build-v2 Python job, run inside its own sandboxed child process.

The outer job loop (`python_worker.py`) starts `python -P -s -S -B -c <this source>`, configuration on stdin, with the staged
job folder as its working directory, a declared environment only and, on macOS, a deny-default
sandbox. This file is passed as source text: the child never reads the checkout.

**Op interface.** The unit's declared entry script defines one function:

    def run(context):
        data = context.input('shape').read_bytes()
        context.output('piece.glb').write_bytes(convert(data, context.params['scale']))

`context` is a `JobContext`:

- `inputs`: read-only mapping of declared slot name to a job-relative `Path`, or `None` for an
  optional input that is absent. File slots name a file; item slots name a directory holding the
  item's exact members.
- `input(name)`: that path; raises `LookupError` for an absent or undeclared slot.
- `params`: the unit's declared parameters, deeply read-only.
- `output_dir`: `Path('output')`, the only writable place.
- `outputs`: the declared output names, relative to `output_dir`.
- `output(name)`: `output_dir / name` for a declared name (parents created); raises otherwise.
- `seed`: the declared integer parameter `seed`, or 0. The `random` module is seeded with it.

Job IDs, the job folder, the unit label and every source locator are control metadata and are not
in the context. Helper modules are imported from the entry script's directory, and only files in
the unit's declared code closure load. Wall-clock time (including `clock_gettime` of realtime clocks)
reads a fixed instant; `random` always uses the declared seed; Python entropy sources raise
`DeterminismError`. These patches make ordinary scripts reproducible; they do not make the process
deterministic at the OS level, so authors still must not depend on elapsed time, file timestamps,
native-library random generators, threads or addresses.

Only the standard library is used.
"""
import importlib.abc
import importlib.machinery
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import sys
import threading
import traceback
from types import MappingProxyType

FIXED_EPOCH = 946684800  # 2000-01-01T00:00:00Z


class DeterminismError(RuntimeError):
    """A job used a clock or entropy source that build-v2 jobs may not use."""


class UndeclaredModuleError(ImportError):
    """A job tried to load project code outside its declared closure."""


def _frozen(value):
    if isinstance(value, dict):
        return MappingProxyType({key: _frozen(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_frozen(item) for item in value)
    return value


class JobContext:
    """The op's whole view of its job. See the module docstring."""

    __slots__ = ('_inputs', '_outputs', '_params', '_seed', 'output_dir')

    def __init__(self, inputs, outputs, params, seed):
        self._inputs = MappingProxyType({name: None if path is None else Path(path) for name, path in inputs.items()})
        self._outputs = tuple(outputs)
        self._params = _frozen(params)
        self._seed = seed
        self.output_dir = Path('output')

    @property
    def inputs(self):
        return self._inputs

    @property
    def outputs(self):
        return self._outputs

    @property
    def params(self):
        return self._params

    @property
    def seed(self):
        return self._seed

    def input(self, name):
        path = self._inputs.get(name)
        if path is None:
            raise LookupError(f'input {name!r} is absent or undeclared')
        return path

    def output(self, name):
        if name not in self._outputs:
            raise LookupError(f'output {name!r} is not declared')
        path = self.output_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


def _refuse(name):
    def refused(*args, **kwargs):
        raise DeterminismError(f'{name} is not available to build-v2 jobs')
    return refused


def fix_clock_and_entropy(seed):
    """Fix wall-clock reads to FIXED_EPOCH, seed `random`, and refuse OS entropy APIs."""
    import datetime
    import random
    import time
    import uuid

    original_localtime, original_gmtime = time.localtime, time.gmtime
    original_ctime, original_strftime = time.ctime, time.strftime
    time.time = lambda: float(FIXED_EPOCH)
    time.time_ns = lambda: FIXED_EPOCH * 1_000_000_000
    time.localtime = lambda secs=None: original_localtime(FIXED_EPOCH if secs is None else secs)
    time.gmtime = lambda secs=None: original_gmtime(FIXED_EPOCH if secs is None else secs)
    time.ctime = lambda secs=None: original_ctime(FIXED_EPOCH if secs is None else secs)
    time.strftime = lambda fmt, t=None: original_strftime(fmt, original_localtime(FIXED_EPOCH) if t is None else t)
    # Wall clocks reachable through clock_gettime read the fixed instant too. Elapsed-time clocks
    # (monotonic, perf_counter, process and thread CPU time) still measure real durations.
    wall = {getattr(time, name) for name in ('CLOCK_REALTIME', 'CLOCK_REALTIME_COARSE', 'CLOCK_TAI')
            if hasattr(time, name)}
    # Some interpreter builds (Blender's bundled Python) have no clock_gettime; there is nothing to fix then.
    if hasattr(time, 'clock_gettime'):
        original_clock, original_clock_ns = time.clock_gettime, time.clock_gettime_ns
        time.clock_gettime = lambda clock: float(FIXED_EPOCH) if clock in wall else original_clock(clock)
        time.clock_gettime_ns = lambda clock: (FIXED_EPOCH * 1_000_000_000 if clock in wall
                                               else original_clock_ns(clock))

    class FixedDatetime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls.fromtimestamp(FIXED_EPOCH, tz)

        @classmethod
        def utcnow(cls):
            return cls.fromtimestamp(FIXED_EPOCH, datetime.timezone.utc).replace(tzinfo=None)

        @classmethod
        def today(cls):
            return cls.fromtimestamp(FIXED_EPOCH)

    class FixedDate(datetime.date):
        @classmethod
        def today(cls):
            return cls.fromtimestamp(FIXED_EPOCH)

    datetime.datetime, datetime.date = FixedDatetime, FixedDate

    original_seed = random.Random.seed

    def seed_method(self, a=None, version=2):
        if a is None:
            a = seed  # never fall back to OS entropy
        return original_seed(self, a, version)

    random.Random.seed = seed_method
    # Module-level functions are methods bound at import; rebind seed so random.seed() is fixed too.
    random.seed = random._inst.seed
    random.seed(seed)
    random.SystemRandom = _refuse('random.SystemRandom')
    os.urandom = _refuse('os.urandom')
    if hasattr(os, 'getrandom'):
        os.getrandom = _refuse('os.getrandom')
    uuid.uuid1 = _refuse('uuid.uuid1')
    uuid.uuid4 = _refuse('uuid.uuid4')
    sys.modules.pop('secrets', None)
    sys.meta_path.insert(0, _RefusedModules({'secrets'}))


class _RefusedModules(importlib.abc.MetaPathFinder):
    def __init__(self, names):
        self.names = names

    def find_spec(self, name, path=None, target=None):
        if name in self.names:
            raise DeterminismError(f'module {name!r} is not available to build-v2 jobs')
        return None


def _inside(path, root):
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


class DeclaredCodeFinder(importlib.abc.MetaPathFinder):
    """Allows modules from the platform roots and the declared code closure, nothing else."""

    def __init__(self, job_dir, declared, platform_roots):
        self.job_dir = job_dir
        self.declared = declared
        self.platform_roots = platform_roots

    def allowed(self, origin):
        real = os.path.realpath(origin)
        if _inside(real, self.job_dir):
            return os.path.relpath(real, self.job_dir) in self.declared
        return any(_inside(real, root) for root in self.platform_roots)

    def find_spec(self, name, path=None, target=None):
        spec = importlib.machinery.PathFinder.find_spec(name, path, target)
        if spec is None or spec.origin in (None, 'built-in', 'frozen'):
            return spec
        if not self.allowed(spec.origin):
            raise UndeclaredModuleError(f'module {name!r} is outside the declared code closure')
        return spec


def undeclared_modules(finder):
    """Modules already loaded whose file is neither platform code nor declared project code."""
    found = []
    for name, module in list(sys.modules.items()):
        origin = getattr(module, '__file__', None)
        if origin and not finder.allowed(origin):
            found.append(name)
    return sorted(found)


class PathGuard:
    """Refuses, by path and before any system call, file access outside the declared view.

    The macOS sandbox already kills a job that touches an existing undeclared path, but the kernel
    reports a missing undeclared path as plain ENOENT, so `os.path.exists` would quietly return
    False. This guard closes that gap for Python-level access: any undeclared read, existence check,
    listing or write, present or not, ends the job at once with a `dependency` failure that the job
    cannot catch. Native extension code calling the C library directly bypasses this guard; for it
    only the kernel sandbox applies.
    """

    WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
    MUTATIONS = {'os.mkdir': (0,), 'os.rename': (0, 1), 'os.remove': (0,), 'os.rmdir': (0,),
                 'os.truncate': (0,), 'os.utime': (0,), 'os.chmod': (0,), 'os.chown': (0,),
                 'os.chflags': (0,), 'os.lchflags': (0,), 'os.setxattr': (0,), 'os.removexattr': (0,),
                 'os.mkfifo': (0,), 'os.mknod': (0,)}
    READS = {'os.listdir': (0,), 'os.scandir': (0,), 'os.listxattr': (0,), 'os.getxattr': (0,)}
    # Links could point lexical checks elsewhere; child processes and sockets escape the guard.
    # Directory changes are refused so relative paths always resolve against the job folder.
    REFUSED = ('os.symlink', 'os.link', 'os.chdir', 'socket.', 'subprocess.Popen', 'os.exec',
               'os.posix_spawn', 'os.spawn', 'os.fork', 'os.system', 'os.startfile')

    # os functions taking `dir_fd` or a descriptor in place of a path, with their access kind. Their
    # audit events (if any) omit `dir_fd`, so these wrappers resolve the descriptor's real path.
    DESCRIPTOR_CALLS = {'stat': 'metadata', 'lstat': 'metadata', 'access': 'metadata', 'readlink': 'metadata',
                        'statvfs': 'metadata', 'pathconf': 'metadata', 'open': None, 'listdir': 'read',
                        'scandir': 'read', 'mkdir': 'write', 'rmdir': 'write', 'remove': 'write',
                        'unlink': 'write', 'chmod': 'write', 'chown': 'write', 'utime': 'write',
                        'mkfifo': 'write', 'mknod': 'write', 'rename': 'write', 'replace': 'write'}

    def __init__(self, job_dir, subpaths, literals, report, write_subpaths=None, relative_root=None, mkdir_existing=()):
        self.job_dir = job_dir
        self.relative_root = relative_root or job_dir
        if not _inside(self.relative_root, job_dir):
            raise ValueError("worker cwd is outside the job")
        self.reads = [job_dir] + [os.path.normpath(path) for path in subpaths]
        # Directory literals ('/', '/etc', ...) are kernel startup needs, not readable here: opening
        # one would give a descriptor for probing undeclared names relative to it.
        self.literals = {os.path.normpath(path) for path in literals if not os.path.isdir(path)}
        self.metadata = {ancestor for path in self.reads + sorted(literals) for ancestor in _ancestors(path)}
        self.metadata |= {os.path.normpath(path) for path in literals}
        self.writes = ([os.path.join(job_dir, 'output')] if write_subpaths is None
                       else list(write_subpaths))
        if not self.writes or any(not os.path.isabs(path) or path == job_dir
                                  or not _inside(path, job_dir) for path in self.writes):
            raise ValueError('Worker write roots must be proper job-local directories')
        self.mkdir_existing = frozenset(mkdir_existing)
        if any(not _inside(path, job_dir) or not os.path.isdir(path) or os.path.islink(path) for path in self.mkdir_existing):
            raise ValueError("mkdir context must contain only existing owned directories")
        self.report = report
        self.checked = threading.local()

    def violation(self, access, path):
        print(f'build-v2 job stopped: undeclared {access} of {path}', file=sys.stderr, flush=True)
        self.report({'status': 'failed', 'kind': 'dependency',
                     'message': f'the job attempted an undeclared {access}; only declared inputs, code, '
                                'the installed platform and output/ are visible'})
        os._exit(3)

    def resolve(self, path):
        # Lexical only: the guard itself must not stat or follow anything. Jobs cannot create links.
        return os.path.normpath(os.path.join(self.relative_root, os.fsdecode(path)))

    def allowed(self, access, path):
        if access == 'write':
            return any(_inside(path, root) for root in self.writes)
        if path in self.literals or any(_inside(path, root) for root in self.reads):
            return True
        return access == 'metadata' and path in self.metadata

    def descriptor_path(self, fd):
        """The real path an open descriptor names, or None (pipes, sockets)."""
        try:
            if hasattr(fcntl, 'F_GETPATH'):
                raw = fcntl.fcntl(fd, fcntl.F_GETPATH, bytes(1024))
                return os.fsdecode(raw.split(b'\0', 1)[0])
            return self.original_readlink(f'/proc/self/fd/{fd}')
        except OSError:
            return None

    def check(self, access, path, dir_fd=None):
        if path is None:
            path = '.'
        if isinstance(path, int):
            # A descriptor in place of a path: check what it names. A non-file (pipe) has no path.
            named = self.descriptor_path(path)
            if named is None:
                if access != 'metadata':
                    self.violation(access, f'descriptor {path}')
                return
            if not self.allowed(access, os.path.normpath(named)):
                self.violation(access, named)
            return
        text = os.fsdecode(path)
        if dir_fd is not None and not text.startswith('/'):
            base = self.descriptor_path(dir_fd)
            if base is None:
                self.violation(access, text)
            text = os.path.join(base, text)
        if not self.allowed(access, self.resolve(text)):
            self.violation(access, text)

    def audit(self, event, args):
        if event.startswith(self.REFUSED) or (event == 'ctypes.dlopen' and args[0] is not None):
            self.violation(event, '-')  # loading a named native library is a process-level escape
        if getattr(self.checked, 'skip', False):
            self.checked.skip = False  # this call's wrapper already checked it with its dir_fd
            return
        if args and isinstance(args[0], int):
            return  # an existing descriptor (fdopen); descriptor-taking os calls are checked by wrappers
        if event == 'open':
            path, mode, flags = args
            writes = (isinstance(mode, str) and any(char in mode for char in 'wax+')) or (
                isinstance(flags, int) and flags & self.WRITE_FLAGS)
            self.check('write' if writes else 'read', path)
        elif event == 'os.mkdir' and self.resolve(args[0]) in self.mkdir_existing:
            return  # This already-existing directory cannot be removed or otherwise mutated.
        elif event in self.MUTATIONS:
            for index in self.MUTATIONS[event]:
                self.check('write', args[index])
        elif event in self.READS:
            self.check('read', args[0])

    def wrap(self, name, function, access):
        def guarded(path=_NO_PATH, *args, dir_fd=None, **kwargs):
            if path is _NO_PATH:  # os.listdir() / os.scandir(): the working folder
                self.check(access, '.')
                return function()
            if name == 'mkdir' and dir_fd is None and self.resolve(path) in self.mkdir_existing:
                self.checked.skip = True
                try:
                    return function(path, *args, **kwargs)
                finally:
                    self.checked.skip = False
            kind = access
            if name == 'open':
                flags = args[0] if args else kwargs.get('flags', 0)
                kind = 'write' if flags & self.WRITE_FLAGS else 'read'
            if name in ('rename', 'replace'):
                self.check('write', path, kwargs.get('src_dir_fd'))
                self.check('write', args[0] if args else kwargs['dst'], kwargs.get('dst_dir_fd'))
            else:
                self.check(kind, path, dir_fd)
            if dir_fd is not None:
                kwargs['dir_fd'] = dir_fd
            if dir_fd is not None or kwargs.get('src_dir_fd') is not None or kwargs.get('dst_dir_fd') is not None:
                self.checked.skip = True
            try:
                return function(path, *args, **kwargs)
            finally:
                self.checked.skip = False
        return guarded

    def path_hook(self, entry):
        """First import path hook: the import system probes each new `sys.path` or package path entry
        with the C-level `posix.stat`, which raises no audit event, so an undeclared entry, present or
        missing, is checked here before any finder looks at it. The entries `main` kept (checked by real
        path) and those startup already cached are trusted; every other entry must be declared."""
        if entry not in self.trusted_entries:
            self.check('read', entry)
        raise ImportError('not handled here')

    def install(self):
        self.original_readlink = os.readlink
        sys.addaudithook(self.audit)
        for name, access in self.DESCRIPTOR_CALLS.items():
            if hasattr(os, name):
                setattr(os, name, self.wrap(name, getattr(os, name), access))
        self.trusted_entries = set(sys.path)
        sys.path_hooks.insert(0, self.path_hook)


_NO_PATH = object()


def _ancestors(path):
    found = []
    while True:
        parent = os.path.dirname(path)
        if parent == path:
            return found
        found.append(parent)
        path = parent


def site_libraries(config, platform_roots):
    """The loop's declared installed-library folders, each a real folder inside an approved platform root.

    Nothing else is derived here: under -S the child's own sysconfig no longer names the loop's venv.
    """
    folders = config.get('site_libraries')
    if not isinstance(folders, list) or not all(isinstance(folder, str) for folder in folders):
        raise UndeclaredModuleError('the job configuration names no installed-library folders')
    for folder in folders:
        real = os.path.realpath(folder)
        if not os.path.isabs(folder) or not os.path.isdir(real):
            raise UndeclaredModuleError(f'installed-library folder {folder!r} is not an existing absolute folder')
        if not any(_inside(real, root) for root in platform_roots):
            raise UndeclaredModuleError(f'installed-library folder {folder!r} is outside the platform roots')
    return list(dict.fromkeys(folders))


def main(config, report):
    job_dir = os.path.realpath(os.getcwd())
    platform_roots = [os.path.realpath(root) for root in config['platform_roots']]
    declared = set(config['code'])
    entry_dir = os.path.join(job_dir, os.path.dirname(config['script']))
    # The child starts with -P -s -S, so no .pth file runs and no editable install can put the checkout on
    # the path. The loop's installed-library folders are appended after the standard library, exactly
    # as declared, so they never shadow it; the entry script's directory is the only project import root.
    try:
        libraries = site_libraries(config, platform_roots)
    except UndeclaredModuleError as error:
        return report({'status': 'failed', 'kind': 'dependency', 'message': f'{type(error).__name__}: {error}'})
    standard = [entry for entry in dict.fromkeys(sys.path)
                if entry and any(_inside(os.path.realpath(entry), root) for root in platform_roots)]
    sys.path[:] = [entry_dir] + standard + [folder for folder in libraries if folder not in standard]
    os.environ.pop('__CF_USER_TEXT_ENCODING', None)  # injected by macOS at exec; not declared
    finder = DeclaredCodeFinder(job_dir, declared, platform_roots)
    sys.meta_path.insert(0, finder)
    seed = config['params'].get('seed', 0)
    if isinstance(seed, bool) or not isinstance(seed, int):
        seed = 0
    if config.get('working_directory'):
        # NumPy's pinned installed initializer imports secrets to define its C
        # generators. Initialize that platform module before refusing entropy;
        # producer calls still run after the guard and fixed seed are installed.
        try:
            import numpy as np
            import numpy.random
        except ModuleNotFoundError as error:
            if error.name != 'numpy':
                raise
        else:
            np.random.seed(seed)
            original_rng = np.random.default_rng
            def declared_rng(value=None):
                if value is None:
                    raise DeterminismError('numpy default_rng requires an explicit seed')
                return original_rng(value)
            np.random.default_rng = declared_rng
    fix_clock_and_entropy(seed)
    context = JobContext(config['inputs'], config['outputs'], config['params'], seed)
    working = config.get('working_directory', job_dir)
    if not os.path.isabs(working) or not _inside(working, job_dir):
        raise ValueError('worker cwd is not job owned')
    if working != job_dir:
        context.output_dir = Path(job_dir) / 'output'
        os.chdir(working)
    guard = PathGuard(job_dir, config['read_subpaths'], config['read_literals'], report,
                      config.get('write_subpaths'), working, config.get('mkdir_existing', ()))
    guard.install()
    try:
        spec = importlib.util.spec_from_file_location('atelier_job_entry', os.path.join(job_dir, config['script']))
        module = importlib.util.module_from_spec(spec)
        sys.modules['atelier_job_entry'] = module
        spec.loader.exec_module(module)
        entry = getattr(module, 'run', None)
        if not callable(entry):
            raise TypeError('the entry script defines no run(context) function')
        entry(context)
        if guard.path_hook not in sys.path_hooks or finder not in sys.meta_path:
            # Without them a probe of an undeclared import path could have gone unseen.
            raise UndeclaredModuleError('the job removed the import guards')
        loaded = undeclared_modules(finder)
        if loaded:
            raise UndeclaredModuleError(f'undeclared modules were loaded: {", ".join(loaded)}')
    except (DeterminismError, UndeclaredModuleError, PermissionError) as error:
        traceback.print_exc()
        return report({'status': 'failed', 'kind': 'dependency', 'message': f'{type(error).__name__}: {error}'})
    except BaseException as error:  # noqa: BLE001 - every op failure is reported, never swallowed
        traceback.print_exc()
        return report({'status': 'failed', 'kind': 'job', 'message': f'{type(error).__name__}: {error}'})
    return report({'status': 'ok'})


def _report_to(fd):
    def report(result):
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(result, stream)
    return report


if __name__ == '__main__':
    # The configuration arrives on stdin, not argv, so no valid request can exceed argument limits.
    _config = json.loads(sys.stdin.buffer.read())
    _null = os.open(os.devnull, os.O_RDONLY)
    os.dup2(_null, 0)
    os.close(_null)
    main(_config, _report_to(_config['result_fd']))
