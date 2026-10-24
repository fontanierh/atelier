"""Fixed captured nested-tool observations; existing guard owns the whole child tree."""
from contextlib import contextmanager
from dataclasses import dataclass, field
import hashlib
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import threading
import io
from . import python_worker

_ORIGIN = object()


@dataclass(frozen=True)
class CapturedNode:
    executable: Path
    image: Path
    sources: tuple[Path, ...]
    libraries: tuple[Path, ...]
    provider: Path
    _origin: object = field(repr=False, compare=False)


def bind_node(sources, provider):
    """Fixed issuer constructor only; this observation grants no launch permission."""
    executable = shutil.which('node')
    if not executable:
        raise ValueError('the original nested mesher requires installed Node')
    executable = Path(executable)
    image = executable.resolve(strict=True)
    if not executable.is_absolute() or not stat.S_ISREG(image.lstat().st_mode):
        raise ValueError('nested tool executable is not a real installed image')
    sources = tuple(map(Path, sources))
    if len(sources) != 4 or len(set(sources)) != 4:
        raise ValueError('nested mesher requires its exact three sources and pin')
    libraries = node_libraries(image)
    return CapturedNode(executable, image, sources, libraries, Path(provider), _ORIGIN)


def node_libraries(image):
    """Read-only installed-image dependency metadata, never a Content/task process.

    The fixed SDK inspector sees only actual executable/library paths. No shell or
    generated source is executed; unresolved/ambiguous/non-Homebrew dependencies refuse.
    System shared-cache libraries retain the existing installed-platform policy.
    """
    queue = [Path(image)]
    found = {}
    while queue:
        binary = queue.pop()
        result = subprocess.run(['/usr/bin/otool', '-L', str(binary)], capture_output=True,
                                text=True, timeout=5, check=True)
        if len(result.stdout) > 65536:
            raise ValueError('installed nested tool dependency metadata exceeds bound')
        for line in result.stdout.splitlines()[1:]:
            name = line.strip().split(' (', 1)[0]
            if name.startswith(('/System/', '/usr/lib/')):
                continue
            if name.startswith('@rpath/'):
                candidates = (binary.parent / name[7:], binary.parent.parent / 'lib' / name[7:])
                targets = {path.resolve(strict=True) for path in candidates if path.exists()}
                if len(targets) != 1:
                    raise ValueError('ambiguous nested tool library resolution')
                role = next(path for path in candidates if path.exists())
            elif name.startswith('@loader_path/'):
                role = binary.parent / name[len('@loader_path/'):]
            else:
                role = Path(name)
            if not role.is_absolute() or not role.is_relative_to('/opt/homebrew'):
                raise ValueError('nested tool library is outside the supported installed context')
            role = Path(os.path.abspath(role))
            real = role.resolve(strict=True)
            if not real.is_relative_to('/opt/homebrew') or not stat.S_ISREG(real.lstat().st_mode):
                raise ValueError('nested tool library is not a real file')
            found[str(role)] = role
            if str(real) not in found:
                found[str(real)] = real
                queue.append(real)
            if len(found) > 64:
                raise ValueError('nested tool dependency closure exceeds bound')
    return tuple(found[name] for name in sorted(found))


def checked_node(tool):
    if type(tool) is not CapturedNode or tool._origin is not _ORIGIN:
        raise ValueError('unqualified nested tool descriptor')
    if tool.executable.resolve(strict=True) != tool.image:
        raise ValueError('nested tool executable role changed')
    return tool


def node_identity(tool, hasher):
    tool = checked_node(tool)
    return {'kind': 'captured-node-mesher/1', 'binary': hasher(tool.image),
            'libraries': [(path.name, hasher(path.resolve(strict=True))) for path in tool.libraries],
            'arguments': ['--max-old-space-size=1024'],
            'sources': [(path.name, hasher(path)) for path in tool.sources]}


def node_spec(tool, hasher):
    tool = checked_node(tool)
    return {'kind': 'captured-node-mesher/1', 'executable': str(tool.executable),
            'image': str(tool.image), 'digest': hasher(tool.image),
            'provider': str(tool.provider),
            'libraries': [{'path': str(path), 'digest': hasher(path.resolve(strict=True))} for path in tool.libraries],
            'sources': [{'path': str(path), 'digest': hasher(path)} for path in tool.sources]}


def _read(path):
    from .controller_client import _read_at
    path = Path(path)
    return _read_at(path.parent, path.name, 256 * 1024 * 1024)


def _verify(spec):
    if (type(spec) is not dict or set(spec) != {'kind', 'executable', 'image', 'digest', 'provider', 'sources', 'libraries'}
            or spec['kind'] != 'captured-node-mesher/1'):
        raise ValueError('unknown captured nested tool')
    role, image = Path(spec['executable']), Path(spec['image'])
    if not role.is_absolute() or role.resolve(strict=True) != image:
        raise ValueError('captured nested tool executable changed')
    if hashlib.sha256(_read(image)).hexdigest() != spec['digest']:
        raise ValueError('captured nested tool image changed')
    if type(spec['sources']) is not list or len(spec['sources']) != 4:
        raise ValueError('captured nested tool source roster changed')
    libraries = spec['libraries']
    if type(libraries) is not list or not 0 < len(libraries) <= 64:
        raise ValueError('captured nested tool runtime roster differs')
    if len({item.get('path') for item in libraries if type(item) is dict}) != len(libraries):
        raise ValueError('duplicate nested tool runtime role')
    for item in libraries:
        if type(item) is not dict or set(item) != {'path', 'digest'}:
            raise ValueError('captured nested tool runtime record differs')
        path = Path(item['path'])
        if (not path.is_absolute() or not path.is_relative_to('/opt/homebrew')
                or not path.resolve(strict=True).is_relative_to('/opt/homebrew')
                or hashlib.sha256(_read(path.resolve(strict=True))).hexdigest() != item['digest']):
            raise ValueError('captured nested tool runtime bytes changed')
    paths = []
    for item in spec['sources']:
        if type(item) is not dict or set(item) != {'path', 'digest'}:
            raise ValueError('captured nested tool source record differs')
        path = Path(item['path'])
        if hashlib.sha256(_read(path)).hexdigest() != item['digest']:
            raise ValueError('captured nested tool source bytes changed')
        paths.append(path)
    if (len(set(paths)) != 4 or tuple(path.name for path in paths) !=
            ('bridge.cjs', 'pieces.cjs', 'terrain.cjs', 'pin.json')
            or any(path.parent != paths[0].parent for path in paths)):
        raise ValueError('captured nested mesher source roles differ')
    return role, image, paths


def _profile(directory, output, role, image, sources, libraries):
    class NodePlatform(python_worker.Platform):
        def executables(self):
            return sorted(set([str(role), str(image), *python_worker._links(str(role))]))

        def reads(self):
            return list(python_worker.PLATFORM_READ_SUBPATHS), [
                *python_worker.PLATFORM_READ_LITERALS, *map(str, sources),
                *libraries, str(role), str(image)]

        def extra_rules(self):
            return [f'(allow file-write* (subpath {python_worker._quote(str(output))}))']
    return python_worker.sandbox_profile(str(directory), NodePlatform())


@contextmanager
def node_execution(spec, *, scratch, sources, observer):
    """@cc [owner:fontanierh,label:safety;correctness] captured-nested-node-execution
    Only the checked captured provider MAY invoke the original fixed Node mesher command.
    Installed image and source bytes MUST revalidate before launch; a deny-default sandbox
    MUST restrict native reads/writes/exec/network while the original outer guard retains
    descendant custody. Unknown calls MUST remain sticky audit failures. No second admission,
    audit disable, shell, ambient executable substitution or output certification is granted.
    See test_build_v2_legacy_tool_action.py.
    """
    from .legacy_qualification import _same_code
    # These are closed framework identity reads, not producer execution. The
    # existing observer separately receives every native command and the sandbox
    # checks its actual filesystem access. Never call a producer while inspecting.
    previous_busy = getattr(observer.local, 'busy', False)
    observer.local.busy = True
    try:
        role, image, tool_sources = _verify(spec)
    finally:
        observer.local.busy = previous_busy
    provider = str(Path(spec['provider']))
    source = next((item for item in sources if item.filename == provider), None)
    if source is None:
        raise ValueError('nested tool provider is outside the selected captured code')
    expected = [code for code in source.compiled().co_consts
                if type(code) is type(source.compiled()) and code.co_name == 'compile_snapshot']
    if len(expected) != 1:
        raise ValueError('nested tool provider has no unique captured compiler')
    scratch = Path(scratch)
    original = subprocess.run
    original_hook = observer.observe
    granted = None

    def observe(event, arguments):
        if event == 'subprocess.Popen' and granted is not None:
            executable, argv, cwd, env = arguments
            if (executable == granted['command'][0] and argv == granted['command']
                    and cwd is None and env is None and threading.get_ident() == granted['thread']
                    and not granted['used']):
                granted['used'] = True
                observer.record('checked nested tool')
                return
        return original_hook(event, arguments)

    def run(argv, *args, **kwargs):
        nonlocal granted
        caller = sys._getframe(1)
        if (args or set(kwargs) != {'stdout', 'stderr', 'timeout', 'check'}
                or not _same_code(caller.f_code, expected[0])
                or caller.f_globals.get('__file__') != provider
                or type(kwargs.get('stdout')) is not io.TextIOWrapper
                or type(argv) is not list or len(argv) != 6 or any(type(v) is not str for v in argv)
                or argv[:3] != [str(role), '--max-old-space-size=1024', str(tool_sources[0])]
                or kwargs['stderr'] != subprocess.STDOUT or kwargs['check'] is not False
                or kwargs['timeout'] != 600):
            observer.record('subprocess', reason='unqualified nested tool invocation')
            raise ValueError('unqualified nested tool invocation')
        park, data, output = map(Path, argv[3:])
        directory = park.parent.parent
        if (park.name != 'park.json' or park.parent.name != 'snap'
                or data != park.parent / 'data' or output != directory / 'mesh'
                or not directory.is_relative_to(scratch / 'tmp')):
            observer.record('subprocess', reason='nested tool scratch roles differ')
            raise ValueError('nested tool scratch roles differ')
        from .controller_client import _open_root
        previous_busy = getattr(observer.local, 'busy', False)
        observer.local.busy = True
        try:
            descriptor = _open_root(directory)
            os.close(descriptor)
            info = os.fstat(kwargs['stdout'].fileno())
            expected_log = output / 'node.log'
            if (not stat.S_ISREG(info.st_mode) or not expected_log.is_file()
                    or (expected_log.stat().st_dev, expected_log.stat().st_ino) != (info.st_dev, info.st_ino)):
                raise ValueError('nested tool stdout is not its owned log')
            _verify(spec)
            profile = _profile(directory, output, role, image, tool_sources,
                               [p['path'] for p in spec['libraries']])
        finally:
            observer.local.busy = previous_busy
        command = ['/usr/bin/sandbox-exec', '-p', profile, *argv]
        granted = {'command': command, 'thread': threading.get_ident(), 'used': False}
        try:
            return original(command, **kwargs)
        finally:
            granted = None

    observer.observe = observe
    subprocess.run = run
    try:
        yield
    finally:
        subprocess.run = original
        observer.observe = original_hook
