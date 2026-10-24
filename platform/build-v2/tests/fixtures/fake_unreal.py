"""A stand-in `UnrealEditor-Cmd` for T0: no engine, the same command line and worker surface.

Tests install this file, after a `#!<python> -sS` line, as `<engine>/Engine/Binaries/Mac/UnrealEditor-Cmd`.
It accepts only the command line `unreal.rs` builds, loads the declared project modules from the
scratch project's `Binaries/Mac` (a library whose bytes are `stale` makes it try to rebuild that
module, which fails on the read-only clone, as the real editor would), then installs a minimal
`unreal` module and runs the `-script` as `__main__`, as the `pythonscript` commandlet does.

The fake `unreal` module models only what the worker uses: a package table (loaded, dirty, pinned),
saved-package recording, the asset registry's view of `/Game`, console variables with their set-by
source (a forced CVar the stand-in does not register is ignored, as the editor ignores an unknown one),
ini values from `-ini:`, saves whose writes may finish only at a flush (the plugin hashes a save's files
after flushing), each saved file's import table, failed ensures, `find_object`, and the effective cache graph built from `-DDC=` (the
engine's pak plus inline file-system nodes; without `-DDC=` it reports the installed default
graph, Zen plus a shared folder, as the editor's fallback would). As in the editor, `SystemLibrary.collect_garbage` only
schedules a collection (a commandlet script never reaches the next tick); only the plugin's
`collect_garbage_now` collects. Its test-only `AtelierFake` class lets fixture ops create, save, load,
pin and dirty packages, set or register a CVar, fail an ensure, write a stray file and make an
editor call raise. Real Unreal behaviour is proven only by the admitted T2 sessions.
"""
import hashlib
import json
import os
from pathlib import Path
import runpy
import sys
import types

FLAGS = ['-unattended', '-nop4', '-nosplash', '-stdout', '-AllowStdOutLogVerbosity', '-NullRHI', '-nocrashreports']
ENGINE = Path(__file__).resolve().parents[3]
DEFAULT_ENGINE_PLUGINS = {'ContentBrowserData': ENGINE / 'Engine/Plugins/Editor/ContentBrowserData'}


def fail(message):
    print(f'fake-unreal: {message}', file=sys.stderr, flush=True)
    raise SystemExit(1)


argv = sys.argv[1:]
flags_end = 3 + len(FLAGS)
if len(argv) < flags_end + 1 or argv[1] != '-run=pythonscript' or not argv[2].startswith('-script='):
    fail(f'unexpected command line {argv}')
if argv[3:flags_end] != FLAGS or not argv[flags_end].startswith('-UserDir='):
    fail(f'unexpected flags {argv[3:flags_end + 1]}')
settings, ddc = [], {'flags': [], 'graph': None}
# Test-only: what this stand-in reports instead of a setting's applied value (None: not set), as
# a real editor may print a console variable its own way or ignore an ini key.
readback = {}
for token in argv[flags_end + 1:]:
    if token == '--request-fd':
        break
    if token in ('-nowrite', '-NoZenAutoLaunch'):
        ddc['flags'].append(token)
    elif token.startswith('-DDC='):
        ddc['graph'] = token[len('-DDC='):]
    elif token.startswith(('-ini:', '-ForceDPCVars=')):
        settings.append(token)
    elif token.startswith('-FakeReadback='):
        target, separator, value = token[len('-FakeReadback='):].partition('|')
        readback[target] = value if separator else None
    else:
        fail(f'undeclared argument {token}')


def cache_nodes(graph):
    """The stores an inline `-DDC=(...)` graph builds: named engine nodes and `Name=(Type=...,...)` entries."""
    if graph is None:
        return [{'kind': 'Pak File', 'path': str(ENGINE / 'Engine/DerivedDataCache/Compressed.ddp')},
                {'kind': 'Zen', 'path': ''}, {'kind': 'File System', 'path': str(ENGINE.parent / 'shared-ddc')}]
    entries, depth, current = [], 0, ''
    for char in graph.strip()[1:-1]:
        depth += {'(': 1, ')': -1}.get(char, 0)
        if char == ',' and depth == 0:
            entries.append(current)
            current = ''
        else:
            current += char
    entries.append(current)
    nodes = []
    for entry in entries:
        if entry == 'InstalledEnginePak':
            nodes.append({'kind': 'Pak File', 'path': str(ENGINE / 'Engine/DerivedDataCache/Compressed.ddp')})
            continue
        params = dict(item.split('=', 1) for item in entry.split('=(', 1)[1].rstrip(')').split(','))
        kind = {'FileSystem': 'File System', 'Zen': 'Zen', 'ReadPak': 'Pak File'}[params['Type']]
        nodes.append({'kind': kind, 'path': params.get('Path', params.get('Filename', ''))})
    return nodes
uproject, script = Path(argv[0]), argv[2][len('-script='):]
project = uproject.parent
descriptor = json.loads(uproject.read_text())
# As installed: the BuildId modules must match is in the engine's module manifest.
build_id = json.loads((ENGINE / 'Engine/Binaries/Mac/UnrealEditor.modules').read_text())['BuildId']

libraries = []
for module in descriptor['Modules']:
    library = project / 'Binaries/Mac' / f'libUnrealEditor-{module["Name"]}.dylib'
    if not library.is_file():
        fail(f'module {module["Name"]} is missing')
    if library.read_bytes() == b'stale':
        try:
            library.write_bytes(b'rebuilt')
        except OSError as error:
            fail(f'could not rebuild module {module["Name"]}: {error}')
    libraries.append(str(library))
plugins = dict(DEFAULT_ENGINE_PLUGINS)
for plugin in descriptor['Plugins']:
    if not plugin['Enabled']:
        continue
    folder = project / 'Plugins' / plugin['Name']
    plugins[plugin['Name']] = folder if folder.is_dir() else ENGINE / 'Engine/Plugins' / plugin['Name']
    libraries.extend(str(path) for path in sorted(folder.glob('Binaries/Mac/*.dylib')))
libraries.append(str(ENGINE / 'Engine/Binaries/Mac/libUnrealEditor-Core.dylib'))

CONTENT = project / 'Content'
packages = {}  # name -> {'loaded', 'dirty', 'pinned', 'imports'}
# name -> [value, set by], as the plugin's settings_snapshot reports them.
cvars = {'r.Existing': ['0', 'Constructor'], 'r.GenerateMeshDistanceFields': ['1', 'Constructor']}
config = {}  # (file, section, key) -> value
for token in settings:
    if token.startswith('-ForceDPCVars='):
        for pair in token[len('-ForceDPCVars='):].split(','):
            name, _, value = pair.partition('=')
            if name in cvars:
                cvars[name] = [value, 'Commandline']
    else:
        file, section, rest = token[len('-ini:'):].split(':', 2)
        key, _, value = rest.partition('=')
        config[(file, section.strip('[]'), key)] = value
for target, value in readback.items():
    if ':[' in target:
        file, rest = target.split(':[', 1)
        section, key = rest.split(']:', 1)
        store, slot = config, (file, section, key)
    else:
        store, slot = cvars, target
        value = None if value is None else [value, 'Commandline']
    if value is None:
        store.pop(slot, None)
    else:
        store[slot] = value
pending = {}  # path -> bytes a deferred save writes only when its writes are flushed
registry = set()
recording = None
broken = set()  # editor calls a fixture op made raise
scheduled = {'gc': False}  # SystemLibrary.collect_garbage only schedules; a commandlet script never ticks
ensures = [0]


def stamp(path):
    """Which file is at `path`, as the plugin's stat stamp: None when there is no regular file."""
    try:
        info = path.stat()
    except FileNotFoundError:
        return None
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


def file_of(name):
    if not name.startswith('/Game/'):
        raise ValueError(f'{name} is not under /Game')
    return CONTENT / (name[len('/Game/'):] + '.uasset')


def name_of(path):
    relative = Path(path).resolve().relative_to(CONTENT.resolve())
    return '/Game/' + str(relative.with_suffix(''))


class Package:
    def __init__(self, name):
        self.name = name

    def get_name(self):
        return self.name


unreal = types.ModuleType('unreal')


class SystemLibrary:
    @staticmethod
    def get_command_line():
        return ' '.join(argv)

    @staticmethod
    def collect_garbage():
        scheduled['gc'] = True  # as in the editor: nothing is collected before the next engine tick


class Paths:
    @staticmethod
    def project_dir():
        return str(project) + '/'

    @staticmethod
    def engine_dir():
        return str(ENGINE / 'Engine') + '/'

    @staticmethod
    def convert_relative_path_to_full(path):
        return path


class EditorLoadingAndSavingUtils:
    @staticmethod
    def unload_packages(objects):
        if 'unload' in broken:
            raise RuntimeError('unload_packages failed')
        any_unloaded = False
        for value in objects:
            entry = packages.get(value.get_name())
            if entry and entry.get('import_hold'):
                entry['import_hold'] = False  # as after an import: the first unload frees nothing
                continue
            if entry and not entry['pinned']:
                entry['loaded'] = False
                any_unloaded = True
        return any_unloaded


def find_object(outer, name):
    entry = packages.get(name)
    return Package(name) if entry and (entry['loaded'] or entry['pinned']) else None


class Registry:
    def scan_files_synchronous(self, files, force):
        registry.update(str(Path(path).resolve()) for path in files if Path(path).is_file())

    def get_assets_by_path(self, path, recursive):
        return sorted(registry)


class AssetRegistryHelpers:
    @staticmethod
    def get_asset_registry():
        return Registry()


class AtelierBuildWorkerLibrary:
    @staticmethod
    def native_context():
        return json.dumps({'build_id': build_id, 'modules': [m['Name'] for m in descriptor['Modules']],
                           'plugins': {name: str(folder) for name, folder in plugins.items()},
                           'libraries': libraries, 'rhi': 'null'})

    @staticmethod
    def ddc_graph():
        return json.dumps({'graph': ddc['graph'] or 'InstalledDerivedDataBackendGraph',
                           'nodes': cache_nodes(ddc['graph'])})

    @staticmethod
    def begin_read_recording():
        return True

    @staticmethod
    def end_read_recording():
        return json.dumps({'version': 1, 'best_effort': True, 'files': []})

    @staticmethod
    def begin_save_recording():
        global recording
        recording = []
        broken.clear()  # a fixture op breaks editor calls for its own job (and that job's reset) only

    @staticmethod
    def end_save_recording():
        global recording
        saved, recording = recording or [], None
        return json.dumps(saved)

    @staticmethod
    def finish_background_work():
        flush(force=True)

    @staticmethod
    def dirty_package_names():
        return [name for name, entry in packages.items() if entry['dirty']]

    @staticmethod
    def loaded_package_names(prefix):
        return [name for name, entry in packages.items()
                if name.startswith(prefix) and (entry['loaded'] or entry['pinned'])]

    @staticmethod
    def package_imports(filename):
        if 'imports' in broken:
            return ''  # an unreadable import table
        return json.dumps(packages.get(name_of(filename), {}).get('imports', []))

    @staticmethod
    def config_value(file, section, key):
        found = (file, section, key) in config
        return json.dumps({'found': found, 'value': config.get((file, section, key), '')})

    @staticmethod
    def settings_snapshot():
        return json.dumps(cvars)

    @staticmethod
    def collect_garbage_now():
        for name in [n for n, p in packages.items() if not p['loaded'] and not p['pinned']]:
            del packages[name]

    @staticmethod
    def begin_ensure_count():
        ensures[0] = 0

    @staticmethod
    def ensure_count():
        return ensures[0]

    @staticmethod
    def forget_files(paths):
        for path in paths:
            registry.discard(str(Path(path).resolve()))


class AtelierFake:
    """Test-only editor actions for fixture ops."""

    @staticmethod
    def create_package(name, payload, imports=()):
        packages[name] = {'loaded': True, 'dirty': True, 'pinned': False, 'payload': payload,
                          'imports': [list(item) for item in imports]}

    @staticmethod
    def import_package(name, payload):
        """Create and save `name` as an Interchange import does: it survives its first unload."""
        AtelierFake.create_package(name, payload)
        packages[name]['import_hold'] = True
        AtelierFake.save_package(name)

    @staticmethod
    def save_package(name, deferred=False, bulk=None, into=None):
        """Save `name`; a deferred save writes its bytes only when its writes are flushed.

        `bulk` also writes a `.ubulk` companion, moved into place from a temporary file as Unreal does.
        `into` saves to another package's file, as a save with an explicit filename can.
        """
        entry = packages[name]
        path = file_of(into or name)
        path.parent.mkdir(parents=True, exist_ok=True)
        companions = [path.with_suffix(suffix) for suffix in ('.uexp', '.ubulk', '.uptnl')]
        before = {other: stamp(other) for other in companions}  # as the plugin's pre-save handler
        if deferred:
            path.write_bytes(b'not yet written')
            pending[path] = entry['payload']
        else:
            path.write_bytes(entry['payload'])
        if bulk is not None:
            temporary = path.with_name(path.name + '.tmp')
            temporary.write_bytes(bulk)
            os.replace(temporary, path.with_suffix('.ubulk'))
        entry['dirty'] = False
        registry.add(str(path.resolve()))
        if recording is not None:
            flush()  # as the plugin does before hashing a save's files
            # Only what this save wrote: its target and each companion it created or replaced.
            wrote = [path] + [other for other in companions if stamp(other) not in (None, before[other])]
            files = {str(other): hashlib.sha1(other.read_bytes()).hexdigest() for other in wrote if other.is_file()}
            recording.append({'package': name, 'filename': str(path), 'files': files})

    @staticmethod
    def load_package(name):
        path = file_of(name)
        packages[name] = {'loaded': True, 'dirty': False, 'pinned': False, 'payload': path.read_bytes(),
                          'imports': []}
        return packages[name]['payload']

    @staticmethod
    def dirty(name):
        packages[name]['dirty'] = True

    @staticmethod
    def keep_alive(name):
        packages[name]['pinned'] = True

    @staticmethod
    def set_cvar(name, value):
        cvars[name] = [value, 'Console']

    @staticmethod
    def register_cvar(name, value):
        cvars.setdefault(name, [value, 'Constructor'])  # a module loaded on demand, at its default

    @staticmethod
    def ensure():
        ensures[0] += 1

    @staticmethod
    def break_call(name):
        broken.add(name)

    @staticmethod
    def write_file(relative, data):
        path = CONTENT / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def flush(force=False):
    """Finish pending package writes (`UPackage::WaitForAsyncFileWrites`); a broken flush leaves them to the end."""
    if 'flush' in broken and not force:
        return
    for path, payload in list(pending.items()):
        path.write_bytes(payload)
        del pending[path]


for value in (SystemLibrary, Paths, EditorLoadingAndSavingUtils, AssetRegistryHelpers, AtelierBuildWorkerLibrary,
              AtelierFake):
    setattr(unreal, value.__name__, value)
unreal.find_object = find_object
sys.modules['unreal'] = unreal
sys.argv = [script]
runpy.run_path(script, run_name='__main__')
