"""Fixed captured nested-tool observations; existing guard owns the whole child tree."""
from contextlib import contextmanager
from dataclasses import dataclass, field
import hashlib
import os
import re
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import threading
import io
import json
from . import python_worker

_ORIGIN = object()


@dataclass(frozen=True)
class CapturedNode:
    executable: Path
    image: Path
    sources: tuple[Path, ...]
    libraries: tuple[Path, ...]
    links: tuple[tuple[str, str], ...]
    configurations: tuple[Path, ...]
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
    links = library_links((executable, image, *libraries))
    return CapturedNode(executable, image, sources, libraries, links,
                        openssl_configurations(libraries), Path(provider), _ORIGIN)


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


def openssl_configurations(libraries):
    """One compiled default configuration is a closed, keyed installed-tool input.

    Includes, environment overrides and external provider-module declarations are
    unsupported; no directory, certificate or follow-on configuration grant exists.
    """
    if any(name in os.environ for name in ('OPENSSL_CONF', 'OPENSSL_CONF_INCLUDE', 'OPENSSL_MODULES')):
        raise ValueError('unsupported OpenSSL environment override')
    crypto = {Path(path).resolve(strict=True) for path in libraries
              if Path(path).name == 'libcrypto.3.dylib'}
    if not crypto:
        return ()  # A selected runtime without libcrypto has no such input.
    if len(crypto) != 1:
        raise ValueError('ambiguous selected OpenSSL library')
    matches = re.findall(rb'OPENSSLDIR: "([^"\x00\r\n]+)"', _read(next(iter(crypto))))
    if len(matches) != 1:
        raise ValueError('selected OpenSSL default directory is not exact')
    directory = Path(matches[0].decode('utf-8'))
    if not directory.is_absolute() or '..' in directory.parts:
        raise ValueError('selected OpenSSL directory is not absolute')
    config = directory / 'openssl.cnf'
    from .controller_client import _read_at
    data = _read_at(config.parent, config.name, 1024 * 1024)
    active = [line.split('#', 1)[0].strip() for line in data.decode('utf-8').splitlines()]
    if any(line.startswith('.include') or re.search(r'^(?:module|dynamic_path|engines)\s*=', line)
           or '$ENV::' in line for line in active):
        raise ValueError('unsupported OpenSSL include or external provider configuration')
    return (config,)


def library_links(paths):
    """Every already-selected image's actual intermediate links, metadata only."""
    links = sorted({link for path in paths for link in python_worker._links(str(path))})
    if len(links) > 256:
        raise ValueError('installed image link closure exceeds bound')
    return tuple((link, os.readlink(link)) for link in links)


def checked_node(tool):
    if type(tool) is not CapturedNode or tool._origin is not _ORIGIN:
        raise ValueError('unqualified nested tool descriptor')
    if tool.executable.resolve(strict=True) != tool.image:
        raise ValueError('nested tool executable role changed')
    if library_links((tool.executable, tool.image, *tool.libraries)) != tool.links:
        raise ValueError('nested tool library link roles changed')
    if openssl_configurations(tool.libraries) != tool.configurations:
        raise ValueError('selected OpenSSL configuration role changed')
    return tool


def installation_inventory(root, hasher=None):
    """Complete installed-tool identity through the existing inventory/JSON encoder.

    Link text is recorded without following any target outside the installation.
    No source/output witness capability is minted from this inventory.
    """
    from atelier.build_products import Product, _inventory
    from .controller_client import _open_root, _stamp
    root = Path(root)
    descriptor = _open_root(root)
    try:
        before = os.fstat(descriptor)
        links, observed = {}, []
        def link(path):
            info = path.lstat()
            if not stat.S_ISLNK(info.st_mode):
                return False
            target = os.readlink(path)
            links[path.relative_to(root).as_posix()] = target
            observed.append((path, _stamp(info), target))
            return True
        manifest = _inventory(Product('installed-tool', (root,)), hasher=hasher, ignore=link)
        for path, stamp, target in observed:
            if _stamp(path.lstat()) != stamp or os.readlink(path) != target:
                raise ValueError('installed tool link changed during inventory')
        current = root.lstat()
        if (current.st_dev, current.st_ino) != (before.st_dev, before.st_ino):
            raise ValueError('installed tool root changed during inventory')
        return {'schema': 1, 'inventory': manifest, 'links': links}
    finally:
        os.close(descriptor)


def node_identity(tool, hasher):
    tool = checked_node(tool)
    return {'kind': 'captured-node-mesher/1', 'binary': hasher(tool.image),
            'libraries': [(path.name, hasher(path.resolve(strict=True))) for path in tool.libraries],
            'links': list(tool.links),
            'configurations': [(str(path), hasher(path)) for path in tool.configurations],
            'installation': installation_inventory(tool.image.parent.parent, hasher),
            'arguments': ['--max-old-space-size=1024'], 'cwd': 'owned-snapshot-root',
            'execution_role': 'canonical-installed-image',
            'sources': [(path.name, hasher(path)) for path in tool.sources]}


def node_spec(tool, hasher):
    tool = checked_node(tool)
    from atelier.build_products import identity
    root = tool.image.parent.parent
    info = root.lstat()
    return {'kind': 'captured-node-mesher/1', 'executable': str(tool.executable),
            'image': str(tool.image), 'digest': hasher(tool.image),
            'provider': str(tool.provider),
            'installation_root': str(root),
            'installation_anchor': {'device': info.st_dev, 'inode': info.st_ino},
            'installation_digest': identity(installation_inventory(root, hasher)),
            'links': [{'path': path, 'target': target} for path, target in tool.links],
            'configurations': [{'path': str(path), 'digest': hasher(path)} for path in tool.configurations],
            'libraries': [{'path': str(path), 'digest': hasher(path.resolve(strict=True))} for path in tool.libraries],
            'sources': [{'path': str(path), 'digest': hasher(path)} for path in tool.sources]}


def _read(path):
    from .controller_client import _read_at
    path = Path(path)
    return _read_at(path.parent, path.name, 256 * 1024 * 1024)


def _verify(spec):
    if (type(spec) is not dict or set(spec) != {'kind', 'executable', 'image', 'digest', 'provider', 'sources', 'libraries', 'links',
                'installation_root', 'installation_anchor', 'installation_digest', 'configurations'}
            or spec['kind'] != 'captured-node-mesher/1'):
        raise ValueError('unknown captured nested tool')
    role, image = Path(spec['executable']), Path(spec['image'])
    if not role.is_absolute() or role.resolve(strict=True) != image:
        raise ValueError('captured nested tool executable changed')
    if hashlib.sha256(_read(image)).hexdigest() != spec['digest']:
        raise ValueError('captured nested tool image changed')
    if type(spec['sources']) is not list or len(spec['sources']) != 4:
        raise ValueError('captured nested tool source roster changed')
    from atelier.build_products import identity
    root = Path(spec['installation_root'])
    info = root.lstat()
    if (root != image.parent.parent or image.parent.name != 'bin'
            or spec['installation_anchor'] != {'device': info.st_dev, 'inode': info.st_ino}
            or identity(installation_inventory(root)) != spec['installation_digest']):
        raise ValueError('captured installed tool identity or root changed')
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
    configurations = [{'path': str(path), 'digest': hashlib.sha256(_read(path)).hexdigest()}
                      for path in openssl_configurations(item['path'] for item in libraries)]
    if spec['configurations'] != configurations:
        raise ValueError('captured OpenSSL configuration bytes or role changed')
    expected_links = [{'path': path, 'target': target} for path, target in
                      library_links((role, image, *(item['path'] for item in libraries)))]
    if spec['links'] != expected_links:
        raise ValueError('captured installed image link chain changed')
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


def _profile(directory, output, role, image, sources, libraries, links=(), configurations=()):
    if any(not Path(path).is_absolute() or '..' in Path(path).parts
           for path in (directory, output, role, image, *sources, *libraries, *links, *configurations)):
        raise ValueError('nested sandbox requires exact absolute owned and installed paths')
    class NodePlatform(python_worker.Platform):
        def executables(self):
            return sorted(set([str(role), str(image), *python_worker._links(str(role))]))

        def reads(self):
            return [*python_worker.PLATFORM_READ_SUBPATHS, str(image.parent.parent)], [
                *python_worker.PLATFORM_READ_LITERALS, *map(str, sources),
                *libraries, *map(str, configurations), str(role), str(image)]

        def extra_rules(self):
            rules = [f'(allow file-write* (subpath {python_worker._quote(str(output))}))']
            rules.append(f'(allow file-read-metadata (subpath {python_worker._quote(str(image.parent.parent))}))')
            if links:
                rules.append('(allow file-read-metadata ' + ' '.join(
                    f'(regex (string-append "^" (regex-quote {python_worker._quote(path)}) "$"))' for path in links) + ')')
            return rules
    profile = python_worker.sandbox_profile(str(directory), NodePlatform())
    profile = profile.replace('(version 1)', '(version 1)\n(debug deny)', 1)
    denial = '(deny file-read* network* (with send-signal SIGKILL))'
    if profile.splitlines().count(denial) != 1:
        raise ValueError('installed sandbox template deny clause changed')
    profile = profile.replace(denial, '(deny file-read* network* (with send-signal SIGKILL) '
                              '(with telemetry) (with message "atelier checked nested node"))')
    # The shared Python profile has a default output subtree. This tool uses the
    # existing exact mesh destination instead; do not retain an unused write grant.
    unused = f'(allow file-write* (subpath {python_worker._quote(str(directory / "output"))}) (literal "/dev/null"))'
    if profile.splitlines().count(unused) != 1:
        raise ValueError('installed sandbox template write clause changed')
    return '\n'.join(line for line in profile.splitlines() if line != unused)


@contextmanager
def node_execution(spec, *, scratch, sources, observer):
    """@cc [owner:fontanierh,label:safety;correctness] captured-nested-node-execution
    Only the checked captured provider MAY invoke the original fixed Node mesher command.
    Installed images, complete canonical Node installation and the one compiled-default
    OpenSSL configuration MUST be keyed and revalidated before launch. Includes, external
    provider modules and OpenSSL environment overrides MUST refuse. A deny-default sandbox
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
    original_which = shutil.which
    original_hook = observer._nested_process
    granted = None

    def observe(arguments):
        if granted is not None:
            executable, argv, cwd, env = arguments
            if (executable == granted['command'][0] and argv == granted['command']
                    and cwd == granted['cwd'] and env is None and threading.get_ident() == granted['thread']
                    and not granted['used']):
                granted['used'] = True
                return True
        return False

    def which(command, *args, **kwargs):
        caller = sys._getframe(1)
        if (command != 'node' or args or kwargs or not _same_code(caller.f_code, expected[0])
                or caller.f_globals.get('__file__') != provider):
            observer.record('tool lookup', reason='unqualified installed tool lookup')
            raise ValueError('unqualified installed tool lookup')
        observer.record('checked tool lookup')
        return str(role)

    def diagnostic(event, returncode=None):
        try:
            suffix = '' if returncode is None else f' returncode={returncode}'
            print(f'checked_nested_node v1 event={event} owner_pid={os.getpid()}{suffix}',
                  file=sys.stderr, flush=True)
        except BaseException:
            pass

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
                               [p['path'] for p in spec['libraries']], [p['path'] for p in spec.get('links', [])],
                               [p['path'] for p in spec.get('configurations', [])])
        finally:
            observer.local.busy = previous_busy
        try:
            (scratch / 'nested-node-sandbox.sb').write_text(profile)
            print('checked_nested_node v1 profile_sha256=' + hashlib.sha256(profile.encode()).hexdigest(),
                  file=sys.stderr, flush=True)
        except BaseException:
            pass  # Diagnostic retention never changes the original tool result.
        command = ['/usr/bin/sandbox-exec', '-p', profile, str(image), *argv[1:]]
        try:
            (scratch / 'nested-node-launch.json').write_text(json.dumps({
                'version': 1, 'owner_pid': os.getpid(), 'program': str(image),
                'arguments': argv[1:], 'cwd': str(directory),
                'wrapper': '/usr/bin/sandbox-exec',
                'profile_sha256': hashlib.sha256(profile.encode()).hexdigest()}, sort_keys=True))
        except BaseException:
            pass
        granted = {'command': command, 'cwd': str(directory), 'thread': threading.get_ident(), 'used': False}
        try:
            diagnostic('launch')
            result = original(command, cwd=str(directory), **kwargs)
            diagnostic('returned', result.returncode)
            return result
        finally:
            granted = None

    observer._nested_process = observe
    subprocess.run = run
    shutil.which = which
    try:
        yield
    finally:
        subprocess.run = original
        shutil.which = original_which
        observer._nested_process = original_hook
