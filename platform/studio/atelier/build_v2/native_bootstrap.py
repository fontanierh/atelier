"""Guarded execution-only distribution of the current project-owned Unreal worker.

This private bootstrap cache is not the result CAS and grants no Current capability.
The C3 worker independently verifies the loaded DLL's compiled source digest.
"""
from contextlib import chdir
import fcntl
import hashlib
import os
from pathlib import Path
import stat
import uuid

from . import controller_client as control

SOURCE = 'platform/build-v2/unreal/AtelierBuildWorker'
SOURCE_BOUND = 8 * 1024 * 1024
BINARY_BOUND = 256 * 1024 * 1024
HOST_FILES = {
    'AtelierWorkerHost.uproject': b'''{"FileVersion":3,"Modules":[{"Name":"RuntimeDummy","Type":"Runtime","LoadingPhase":"Default"}],"Plugins":[{"Name":"AtelierBuildWorker","Enabled":true}]}\n''',
    'Source/RuntimeDummy/RuntimeDummy.Build.cs': b'''using UnrealBuildTool;
public class RuntimeDummy : ModuleRules {
    public RuntimeDummy(ReadOnlyTargetRules Target) : base(Target) {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.Add("Core");
    }
}
''',
    'Source/RuntimeDummy/RuntimeDummy.cpp': b'''#include "Modules/ModuleManager.h"
IMPLEMENT_PRIMARY_GAME_MODULE(FDefaultGameModuleImpl, RuntimeDummy, "AtelierWorkerHost");
''',
    'Source/AtelierWorkerHostEditor.Target.cs': b'''using UnrealBuildTool;
public class AtelierWorkerHostEditorTarget : TargetRules {
    public AtelierWorkerHostEditorTarget(TargetInfo Target) : base(Target) {
        Type = TargetType.Editor;
        DefaultBuildSettings = BuildSettingsVersion.Latest;
        IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
        ExtraModuleNames.Add("RuntimeDummy");
    }
}
''',
}


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _capture(plugin):
    plugin = Path(plugin)
    descriptor = 'AtelierBuildWorker.uplugin'
    names = [descriptor]
    source = plugin / 'Source'
    if source.is_symlink() or not source.is_dir():
        raise ValueError('native worker Source is missing or linked')
    for directory, children, files in os.walk(source, followlinks=False):
        children.sort()
        for name in children + files:
            path = Path(directory) / name
            if path.is_symlink():
                raise ValueError('native worker source contains a link')
        names += [(Path(directory) / name).relative_to(plugin).as_posix() for name in files
                  if Path(name).suffix in ('.cs', '.cpp', '.h')]
    if len(names) > 512:
        raise ValueError('native worker source closure exceeds bound')
    # StringComparer.Ordinal orders UTF-16 code units, including non-BMP names.
    names.sort(key=lambda name: name.encode('utf-16-be'))
    files = {name: control._read_at(plugin, name, SOURCE_BOUND) for name in names}
    if sum(map(len, files.values())) > 32 * 1024 * 1024:
        raise ValueError('native worker source byte closure exceeds bound')
    required = {'Source/AtelierBuildWorker/AtelierBuildWorker.Build.cs',
                'Source/AtelierBuildWorker/Private/AtelierBuildWorkerLibrary.cpp',
                'Source/AtelierBuildWorker/Private/AtelierBuildWorkerModule.cpp',
                'Source/AtelierBuildWorker/Public/AtelierBuildWorkerLibrary.h'}
    if not required <= set(files):
        raise ValueError('native worker source closure is incomplete')
    manifest = ''.join(name + '\0' + _sha(raw) + '\n' for name, raw in files.items()).encode('utf-8')
    return _sha(manifest), files


def _engine_id(engine):
    value = control._json(control._read_at(engine, 'Engine/Binaries/Mac/UnrealEditor.modules', 4 * 1024 * 1024))
    identity = value.get('BuildId') if isinstance(value, dict) else None
    if not isinstance(identity, str) or not identity or len(identity) > 256 or '\0' in identity:
        raise ValueError('installed engine module BuildId is missing')
    return identity


def _write(root, files):
    for name, raw in files.items():
        control._relative(name)
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(raw); stream.flush(); os.fchmod(stream.fileno(), 0o400); os.fsync(stream.fileno())


def _binaries(plugin, engine_id):
    root = plugin / 'Binaries'
    if root.is_symlink() or not root.is_dir():
        raise ValueError('compiled worker has no independent Binaries directory')
    files = {}
    for directory, children, names in os.walk(root, followlinks=False):
        children.sort()
        for name in children + names:
            path = Path(directory) / name
            if path.is_symlink():
                raise ValueError('compiled worker contains a linked binary member')
        for name in sorted(names):
            path = Path(directory) / name
            relative = path.relative_to(plugin).as_posix()
            files[relative] = _sha(control._read_at(plugin, relative, BINARY_BOUND))
            if len(files) > 1024:
                raise ValueError('compiled worker binary inventory exceeds bound')
    modules_name = 'Binaries/Mac/UnrealEditor.modules'
    if modules_name not in files:
        raise ValueError('compiled worker has no module manifest')
    modules = control._json(control._read_at(plugin, modules_name, 1024 * 1024))
    if (not isinstance(modules, dict) or modules.get('BuildId') != engine_id
            or not isinstance(modules.get('Modules'), dict)
            or set(modules['Modules']) != {'AtelierBuildWorker'}):
        raise ValueError('compiled worker module identity differs from installed engine')
    library = modules['Modules']['AtelierBuildWorker']
    if (not isinstance(library, str) or '/' in library or '\\' in library
            or not library.endswith('.dylib') or 'Binaries/Mac/' + library not in files):
        raise ValueError('compiled worker module library is missing')
    return files


def _reuse(state, expected):
    try:
        raw = control._read_at(state, 'ready.json', 4 * 1024 * 1024, owned=True)
    except FileNotFoundError:
        return None
    receipt = control._json(raw)
    if (not isinstance(receipt, dict) or set(receipt) != {*expected, 'generation', 'binaries'}
            or any(receipt.get(key) != value for key, value in expected.items())):
        raise ValueError('native worker bootstrap receipt changed; preserved for diagnosis')
    generation = receipt['generation']
    if not isinstance(generation, str) or not generation.startswith('attempt-') or '/' in generation or '\\' in generation:
        raise ValueError('invalid native bootstrap generation')
    plugin = state / generation / 'Host/Plugins/AtelierBuildWorker'
    source, _ = _capture(plugin)
    if source != expected['source_digest'] or _binaries(plugin, expected['engine_build_id']) != receipt['binaries']:
        raise ValueError('native worker cached source/binaries changed; no stale reuse')
    return plugin


def ensure_native_worker(checkout, cache_root, engine_root, *, echo=print):
    """@cc [owner:fontanierh,label:correctness;safety] guarded-native-worker-bootstrap
    Compile only independently materialized current plugin source under ordinary
    guarded compile admission, nice10 and at most three workers, before any native
    controller job. Source, installed BuildId and bootstrap implementation identify
    only this PRIVATE distribution cache, never automatic SDK item ingredients.
    Publish an immutable complete binary receipt only after guarded success, cleanup
    and source revalidation. Changed, missing or failed artifacts MUST NOT yield a
    stale worker; source checkouts and prior generations MUST remain untouched.
    No native runtime validation or CAS Current capability is minted here.
    """
    from atelier.harness.safety import guarded
    checkout, engine = Path(checkout).absolute(), Path(engine_root).absolute()
    source_digest, source_files = _capture(checkout / SOURCE)
    engine_id = _engine_id(engine)
    bootstrap = _sha(control._read_at(Path(__file__).parent, Path(__file__).name, SOURCE_BOUND))
    expected = {'version': 1, 'source_digest': source_digest, 'bootstrap_sha256': bootstrap,
                'engine_build_id': engine_id, 'scope': 'native_worker_bootstrap'}
    locator = _sha((source_digest + '\0' + bootstrap + '\0' + engine_id).encode('utf-8'))
    cache = control._private_root(cache_root)
    state = control._private_root(cache / locator)
    lock = os.open(state / '.bootstrap.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(lock)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_nlink != 1:
            raise ValueError('invalid private native bootstrap lock')
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('native worker bootstrap is already active; no second compile started') from None
        current = _reuse(state, expected)
        if current is not None:
            return current
        generation = state / ('attempt-' + uuid.uuid4().hex)
        generation.mkdir(mode=0o700)
        host = generation / 'Host'; host.mkdir(mode=0o700)
        plugin = host / 'Plugins/AtelierBuildWorker'; plugin.mkdir(parents=True, mode=0o700)
        _write(host, HOST_FILES); _write(plugin, source_files)
        build = engine / 'Engine/Build/BatchFiles/Mac/Build.sh'
        control._read_at(engine, 'Engine/Build/BatchFiles/Mac/Build.sh', SOURCE_BOUND)
        command = ['/usr/bin/nice', '-n', '10', str(build), 'AtelierWorkerHostEditor', 'Mac', 'Development',
                   '-Project=' + str(host / 'AtelierWorkerHost.uproject'), '-NoUBTMakefiles', '-NoHotReload',
                   '-architecture=arm64', '-MaxParallelActions=3', '-NoUBA']
        echo('Preparing Unreal worker: guarded current-source Editor build (nice 10, 3 workers)')
        with chdir(host):
            code = guarded.run(command, generation / 'compile.guard', kind='compile', timeout=1800,
                               queue_seconds=1800, progress=25, aggregate_tree=True,
                               purpose='prepare current project-owned Unreal worker')
        if code:
            raise RuntimeError('guarded native worker compile failed; no worker published')
        if (_capture(checkout / SOURCE)[0] != source_digest or _capture(plugin)[0] != source_digest
                or _engine_id(engine) != engine_id):
            raise ValueError('native worker source/engine changed during compile; no worker published')
        binaries = _binaries(plugin, engine_id)
        for relative in binaries:
            (plugin / relative).chmod(0o500 if relative.endswith('.dylib') else 0o400)
        control.write_control(state, 'ready.json', dict(expected, generation=generation.name, binaries=binaries))
        (state / 'ready.json').chmod(0o400)
        return plugin
    finally:
        os.close(lock)
