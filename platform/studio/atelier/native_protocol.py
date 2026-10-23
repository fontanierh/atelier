"""Standard-library native reuse wire format. No build controller or execution imports."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import unicodedata
from types import SimpleNamespace

from . import engine, paths
from .file_identity import digest_file
from .atomic_files import atomic_json

SCHEMA = 1
MAX_MANIFEST = 64 * 1024**2
MAX_FILES = 500000
MAX_BYTES = 512 * 1024**3
HEX = re.compile(r'[0-9a-f]{64}')
IGNORED = {'logs', 'stamps', '.state', '.DS_Store', '__pycache__', '.git', '.env',
           'release-publish', 'checkpoint-publish'}

class CheckpointError(RuntimeError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def identity(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def read_json(path):
    if path.is_symlink() or path.stat().st_size > MAX_MANIFEST:
        raise CheckpointError('Checkpoint metadata is linked or exceeds its size limit')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise CheckpointError('Duplicate checkpoint metadata key')
            result[key] = value
        return result
    return json.loads(path.read_bytes(), object_pairs_hook=unique)


def relative(value):
    if (not isinstance(value, str) or not value or '\\' in value
            or any(ord(c) < 32 for c in value)):
        raise CheckpointError('Invalid checkpoint member path')
    path = PurePosixPath(value)
    if path.is_absolute() or str(path) != value or any(p in ('.', '..') for p in path.parts):
        raise CheckpointError('Checkpoint members must be canonical relative paths')
    return path


def context(ctx):
    """Engine identity is independent of game HEAD; native ABI identity is mandatory."""
    import platform
    engine = getattr(ctx, 'unreal_root', None)
    files = {}
    if engine is not None:
        for name in ('Engine/Build/Build.version', 'Engine/Binaries/Mac/UnrealEditor.modules'):
            path = engine / name
            if not path.is_file():
                raise CheckpointError('Checkpoint requires the installed engine version and module identity')
            files[name] = digest_file(path)
    toolchain = {}
    if engine is not None and platform.system() == 'Darwin':
        import subprocess
        developer = Path(subprocess.check_output(['xcode-select', '-p'], timeout=10, text=True).strip())
        for name, path in {
            'xcode': developer.parent / 'Info.plist',
            'toolchain': developer / 'Toolchains/XcodeDefault.xctoolchain/ToolchainInfo.plist',
            'sdk': developer / 'Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk/SDKSettings.json',
        }.items():
            if not path.is_file():
                raise CheckpointError('Checkpoint requires the selected Xcode/toolchain/SDK identity')
            toolchain[name] = digest_file(path)
    return dict(system=platform.system(), machine=platform.machine(), engine=files, toolchain=toolchain,
                engine_location=identity(str(engine.resolve())) if engine else None)


def excluded(path):
    return any(p in IGNORED or p.startswith('.env.') or p.endswith('.guard')
               or p.startswith(('.restore-', '.checkpoint-', '.reuse-', '.portable-snapshot-'))
               for p in path.parts)


def safe_destination(root, member):
    relative(member)
    path = root.joinpath(*PurePosixPath(member).parts)
    for parent in path.parents:
        if parent.is_symlink():
            raise CheckpointError('Checkpoint destination has a linked ancestor')
        if parent == root:
            break
    # Resolve every ancestor, including parents of an absent root.
    if root.resolve() != root.absolute():
        raise CheckpointError('Checkpoint destination root has a linked ancestor')
    return path


def validate(manifest, game):
    """@cc [owner:fontanierh,label:security] bounded-checkpoint-paths
    A checkpoint MUST contain only canonical, bounded, uniquely owned member paths and valid
    content digests. Case/Unicode aliases, linked parents, special files and credential paths MUST
    be refused. Downloaded root labels MUST NOT grant authority to write arbitrary paths.
    """
    if (type(manifest) is not dict or manifest.get('schema') != SCHEMA or manifest.get('game') != game
            or type(manifest.get('files')) is not dict or len(manifest['files']) > MAX_FILES
            or type(manifest.get('stamps')) is not dict or type(manifest.get('context')) is not dict
            or not HEX.fullmatch(manifest.get('checkout', ''))):
        raise CheckpointError('Invalid checkpoint manifest')
    aliases, total = set(), 0
    for name, entry in manifest['files'].items():
        path = relative(name)
        alias = unicodedata.normalize('NFC', name).casefold()
        if alias in aliases or excluded(PurePosixPath(*path.parts[1:])) or len(path.parts) < 2:
            raise CheckpointError('Aliased or excluded checkpoint member')
        aliases.add(alias)
        if type(entry) is not dict or entry.get('kind') not in ('file', 'link', 'directory'):
            raise CheckpointError('Invalid checkpoint file kind')
        if type(entry.get('mode')) is not int or not 0 <= entry['mode'] <= 0o777:
            raise CheckpointError('Invalid checkpoint file permissions')
        if type(entry.get('mtime_ns')) is not int or entry['mtime_ns'] < 0:
            raise CheckpointError('Invalid checkpoint timestamp')
        if entry['kind'] == 'file':
            if (type(entry.get('size')) is not int or not 0 <= entry['size'] <= MAX_BYTES
                    or not isinstance(entry.get('sha256'), str) or not HEX.fullmatch(entry['sha256'])):
                raise CheckpointError('Invalid checkpoint file identity')
            total += entry['size']
        elif entry['kind'] == 'link':
            target = entry.get('target')
            if not isinstance(target, str) or not target.startswith(('member:', 'engine:')):
                raise CheckpointError('Invalid checkpoint link target')
            relative(target.partition(':')[2])
    leaves = {unicodedata.normalize('NFC', n).casefold() for n, e in manifest['files'].items() if e['kind'] != 'directory'}
    for name in aliases:
        if any(str(p) in leaves for p in PurePosixPath(name).parents if str(p) != '.'):
            raise CheckpointError('Checkpoint file is another member\'s parent')
    if total > MAX_BYTES or len(canonical(manifest)) > MAX_MANIFEST:
        raise CheckpointError('Checkpoint exceeds its size limit')
    incremental = manifest.get('incremental_stamps', {})
    if type(incremental) is not dict or set(incremental) & set(manifest['stamps']):
        raise CheckpointError('Invalid incremental checkpoint state')
    history = manifest.get('historical_stamps', {})
    if type(history) is not dict or set(history) & (set(manifest['stamps']) | set(incremental)):
        raise CheckpointError('Invalid historical candidate evidence')
    for name, stamp in {**manifest['stamps'], **incremental, **history}.items():
        if (not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*', name) or type(stamp) is not dict
                or not HEX.fullmatch(stamp.get('fingerprint', '')) or stamp.get('touched')):
            raise CheckpointError('Checkpoint contains an invalid or touched certificate')




def entry_path(store, action_key):
    if not isinstance(action_key, str) or not HEX.fullmatch(action_key):
        raise CheckpointError('Invalid task cache identity')
    return store.directory / 'actions' / (action_key + '.json')


def validate_action(value, store, action_key):
    if (type(value) is not dict or value.get('schema') != 1 or value.get('game') != store.game
            or value.get('key') != action_key or type(value.get('roots')) is not list
            or type(value.get('files')) is not dict or type(value.get('stamp')) is not dict
            or not HEX.fullmatch(value.get('fingerprint', '')) or value['stamp'].get('touched')
            or value['stamp'].get('fingerprint') != value['fingerprint']
            or value['stamp'].get('checkpoint_key') != action_key
            or value['stamp'].get('checkpoint_inventory') != inventory_identity(value['roots'], value['files'])):
        raise CheckpointError('Invalid task cache manifest')
    for root in value['roots']:
        if type(root) is not dict or root.get('kind') not in ('file', 'directory', 'absent'):
            raise CheckpointError('Invalid task output root')
        relative(root['path'])
    validate(dict(schema=1, game=store.game, files=value['files'], context={}, checkout='0' * 64,
                        stamps={value['task']: value['stamp']}), store.game)
    for name in value['files']:
        if not any(name == r['path'] or name.startswith(r['path'] + '/') for r in value['roots']):
            raise CheckpointError('Task cache member escapes its declared roots')
    return value


def inventory_identity(declarations, files):
    return identity(dict(roots=declarations,
                         files={name: {k: v for k, v in e.items() if k != 'mtime_ns'} for name, e in files.items()}))


def native_context(game):
    """@cc [owner:fontanierh,label:architecture] native-protocol-excludes-controller
    Native reuse MUST depend only on the standard-library runtime protocol and path/source
    helpers. Creating this context MUST NOT import the build controller, initialize generated
    state or launch a tool. Controller/release changes MUST NOT become native geometry inputs.
    """
    if not isinstance(game, str) or not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*', game) or '..' in game:
        raise ValueError('Invalid native game owner')
    return SimpleNamespace(game=game, out=paths.build_root() / game,
                           uproject=paths.uproject(game), unreal_root=engine.unreal_root())


class ReadStore:
    """Read immutable metadata without creating or chmodding the shared store."""
    def __init__(self, game, directory=None):
        self.game = game
        self.directory = Path(directory) if directory else paths.cache_dir('checkpoints', 'v1', game, create=False)
        self.blobs = self.directory / 'blobs'
        self.manifests = self.directory / 'manifests'

    def load(self, key):
        if not isinstance(key, str) or not HEX.fullmatch(key):
            raise CheckpointError('Invalid checkpoint identity')
        value = read_json(self.manifests / (key + '.json'))
        validate(value, self.game)
        if identity(value) != key:
            raise CheckpointError('Checkpoint manifest digest differs')
        return value


RUNTIME_FILES = ('__init__.py', 'atomic_files.py', 'engine.py', 'file_identity.py', 'mesh_reuse.py',
                 'native_candidates.py', 'native_protocol.py', 'paths.py',
                 'source_imports.py', 'unreal_mesh_reuse.py')


def runtime_files():
    """Complete static source closure of the shared native adapter, enforced by regression."""
    return tuple(Path(__file__).resolve().parent / name for name in RUNTIME_FILES)
