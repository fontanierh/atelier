"""Closed nested Node context for a declared recipe frontend; the worker owns admission.

The installed SDK is execution context, not an automatic key ingredient. Project
JavaScript and input bytes must already belong to the frozen private recipe view.
This helper never constructs a second sandbox, memory guard or source capture.
"""
from contextlib import contextmanager
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import threading


def _file(path):
    path = Path(path)
    if not path.is_absolute() or path != Path(os.path.abspath(path)):
        raise ValueError('Node paths must be normalized and absolute')
    if not path.is_file() or path.is_symlink() or path.resolve() != path:
        raise ValueError('Node source/context path is not an independent regular file')
    return path


def _links(filename):
    found, pending, seen = set(), str(filename), set()
    while pending not in seen:
        seen.add(pending)
        current = Path('/')
        parts = Path(pending).parts[1:]
        for index, part in enumerate(parts):
            current /= part
            if current.is_symlink():
                found.add(str(current))
                pending = os.path.normpath(str(current.parent / os.readlink(current) / Path(*parts[index + 1:])))
                break
        else:
            return found
    raise ValueError('cyclic installed Node library link')


def discover_node():
    """Inspect only installed image dependency metadata, before entering the job."""
    role = shutil.which('node')
    if not role or not Path(role).is_absolute():
        raise ValueError('the recipe frontend requires installed Node')
    image = Path(role).resolve(strict=True)
    if not image.is_relative_to('/opt/homebrew') or not image.is_file():
        raise ValueError('unsupported installed Node image')
    queue, files = [image], {str(image), role}
    while queue:
        binary = queue.pop()
        result = subprocess.run(['/usr/bin/otool', '-L', str(binary)], capture_output=True,
                                text=True, timeout=5, check=True)
        if len(result.stdout) > 65536:
            raise ValueError('Node library metadata exceeds bound')
        for line in result.stdout.splitlines()[1:]:
            name = line.strip().split(' (', 1)[0]
            if name.startswith(('/System/', '/usr/lib/')):
                continue
            if name.startswith('@rpath/'):
                candidates = [binary.parent / name[7:], binary.parent.parent / 'lib' / name[7:]]
                targets = {p.resolve() for p in candidates if p.is_file()}
                if len(targets) != 1:
                    raise ValueError('ambiguous Node library resolution')
                target = next(p for p in candidates if p.is_file())
            elif name.startswith('@loader_path/'):
                target = binary.parent / name[len('@loader_path/'):]
            else:
                target = Path(name)
            target = Path(os.path.abspath(target))
            real = target.resolve(strict=True)
            if not target.is_relative_to('/opt/homebrew') or not real.is_relative_to('/opt/homebrew') or not real.is_file():
                raise ValueError('Node library escapes installed platform')
            if str(real) not in files:
                queue.append(real)
            files.update((str(target), str(real)))
            if len(files) > 128:
                raise ValueError('Node library closure exceeds bound')
    # Include link components as literals; no recursive Homebrew read grant.
    for filename in tuple(files):
        files.update(_links(filename))
    return {'version': 1, 'executable': role, 'image': str(image), 'read_literals': sorted(files)}


def permissions(sdk):
    """Extra platform permissions for the EXISTING worker sandbox only."""
    if (set(sdk) != {'version', 'executable', 'image', 'read_literals'} or sdk['version'] != 1
            or not Path(sdk['executable']).is_absolute()
            or not Path(sdk['image']).is_relative_to('/opt/homebrew')
            or Path(sdk['image']).name != 'node'
            or not Path(sdk['image']).is_file()
            or Path(sdk['executable']).resolve(strict=True) != Path(sdk['image'])
            or not {sdk['executable'], sdk['image']}.issubset(sdk['read_literals'])):
        raise ValueError('invalid installed Node context')
    for name in sdk['read_literals']:
        if not Path(name).is_absolute() or not Path(name).is_relative_to('/opt/homebrew'):
            raise ValueError('invalid installed Node read literal')
    # CPython's close_fds subprocess path forks before its exact allowed exec.
    # PathGuard still refuses raw fork/spawn, and the Node loader forbids children.
    return {'executables': [sdk['image']], 'read_literals': list(sdk['read_literals']),
            'read_subpaths': [str(Path(sdk['image']).parent.parent)],
            'extra_rules': ['(allow process-fork)', '(allow file-read* (literal "/dev/fd"))',
                            '(allow file-read-metadata (subpath '
                            + json.dumps(str(Path(sdk['image']).parent.parent)) + '))']}


class NodeExecution:
    """@cc [owner:fontanierh,label:safety;correctness] recipe-closed-node
    Only the fixed declared JavaScript entry MAY launch, with generated snapshot
    and output roles confined to owned scratch. Arbitrary processes, environment,
    shell/loader switches and inherited descriptors MUST refuse. The existing
    PathGuard MUST invoke allow_subprocess solely for subprocess.Popen; all other
    refused events remain refused. The existing kernel sandbox MUST include the
    exact installed permissions and preserve deny-default network/exec policy.
    No successful launch certifies result membership or complete source keys.
    """
    def __init__(self, sdk, *, view, scratch, entry, sources):
        permissions(sdk)
        self.sdk = sdk
        self.view, self.scratch = Path(view), Path(scratch)
        for root in (self.view, self.scratch):
            if not root.is_absolute() or root.resolve() != root or not root.is_dir():
                raise ValueError('Node requires existing owned absolute roots')
        if self.scratch == self.view or self.scratch.is_relative_to(self.view):
            raise ValueError('Node scratch must be separate from the frozen view')
        self.sources = tuple(_file(p) for p in sources)
        self.entry = _file(entry)
        if (self.entry not in self.sources or self.entry.suffix != '.cjs'
                or len(set(self.sources)) != len(self.sources)
                or any(not p.is_relative_to(self.view) for p in self.sources)):
            raise ValueError('Node entry and helpers must be exact declared private sources')
        self.environment = {'LC_ALL': 'C', 'TZ': 'UTC', 'OPENSSL_CONF': '/dev/null',
                            'HOME': str(self.scratch), 'TMPDIR': str(self.scratch),
                            'PATH': str(Path(sdk['image']).parent)}
        self._grant = None

    def validate(self, argv, args, kwargs):
        if (args or type(argv) is not list or len(argv) != 6 or any(type(x) is not str for x in argv)
                or argv[:3] != [self.sdk['executable'], '--max-old-space-size=1024', str(self.entry)]
                or set(kwargs) != {'stdout', 'stderr', 'timeout', 'check'}
                or type(kwargs['stdout']) is not io.TextIOWrapper
                or kwargs['stderr'] != subprocess.STDOUT or kwargs['check'] is not False
                or type(kwargs['timeout']) not in (int, float) or not 0 < kwargs['timeout'] <= 600):
            raise ValueError('unsupported Node subprocess request')
        park, data, output = map(Path, argv[3:])
        cwd = park.parent.parent
        if (not cwd.is_absolute() or cwd.resolve() != cwd or not cwd.is_relative_to(self.scratch)
                or park != cwd / 'snap/park.json' or data != cwd / 'snap/data' or output != cwd / 'mesh'
                or _file(park) != park or not data.is_dir() or data.resolve() != data
                or not output.is_dir() or output.resolve() != output):
            raise ValueError('Node snapshot/output roles escape owned scratch')
        info = os.fstat(kwargs['stdout'].fileno())
        log = _file(output / 'node.log').stat()
        if not stat.S_ISREG(info.st_mode) or (info.st_dev, info.st_ino) != (log.st_dev, log.st_ino):
            raise ValueError('Node stdout must be its exact owned log')
        # Node's native permission loader prevents JS from spawning even another
        # Node process; the enclosing worker sandbox still owns OS enforcement.
        command = [self.sdk['image'], '--permission', '--disable-proto=throw',
                   '--allow-fs-read=' + str(self.view), '--allow-fs-read=' + str(cwd / 'snap'),
                   '--allow-fs-read=' + str(output), '--allow-fs-write=' + str(output), *argv[1:]]
        return command, str(cwd)

    def allow_subprocess(self, audit_args):
        """Consume exactly one matching Popen audit event on the launching thread."""
        if self._grant is None:
            return False
        executable, argv, cwd, env = audit_args
        command, directory, thread = self._grant
        if (executable != command[0] or argv != command or cwd != directory
                or env != self.environment or threading.get_ident() != thread):
            return False
        self._grant = None
        return True

    @contextmanager
    def install(self):
        """Adapt the existing frontend call; caller retains the audit hook."""
        original_run, original_which = subprocess.run, shutil.which
        def which(name, *args, **kwargs):
            if name != 'node' or args or kwargs:
                raise ValueError('unsupported executable lookup')
            return self.sdk['executable']
        def run(argv, *args, **kwargs):
            command, cwd = self.validate(argv, args, kwargs)
            self._grant = (command, cwd, threading.get_ident())
            try:
                return original_run(command, cwd=cwd, env=dict(self.environment), close_fds=True, **kwargs)
            finally:
                self._grant = None
        subprocess.run, shutil.which = run, which
        try:
            yield self
        finally:
            subprocess.run, shutil.which = original_run, original_which
