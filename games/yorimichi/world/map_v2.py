"""Build only the original Slice world from this job's finished native inputs."""
import ast
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import tarfile

PACKAGE = '/Game/Japan/Maps/Slice'


def _relative(value):
    if (not isinstance(value, str) or not value or '\\' in value or '\x00' in value
            or PurePosixPath(value).is_absolute()
            or any(part in ('', '.', '..') for part in value.split('/'))):
        raise ValueError('invalid staged map data path')
    return value


def world_data(context, selection):
    """Read only the explicitly selected frozen JSON, including the file ROOT codec."""
    if set(selection) - {'file', 'member'} or 'file' not in selection:
        raise ValueError('map requires an explicit world JSON selector')
    source = Path(context.inputs['world'])
    relative = _relative(selection['file'])
    if source.is_dir():
        source /= relative
    elif source.name != PurePosixPath(relative).name:
        raise ValueError('world input differs from the declared staged file')
    member = selection.get('member', '')
    if member:
        _relative(member)
    if source.is_symlink() or not source.is_file():
        raise ValueError('missing regular staged world data')
    if source.name.endswith('.tree.tar'):
        with tarfile.open(source, 'r:') as archive:
            header = archive.next()
            if (header is None or header.name != 'atelier-root.json' or not header.isreg()
                    or not 0 < header.size <= 16 * 1024 * 1024):
                raise ValueError('missing bounded world ROOT manifest')
            manifest = json.loads(archive.extractfile(header).read())
            if (set(manifest) != {'version', 'kind', 'entries'} or manifest['version'] != 1
                    or manifest['kind'] not in ('file', 'directory') or not isinstance(manifest['entries'], list)):
                raise ValueError('invalid world ROOT manifest')
            selected = [row for row in manifest['entries'] if isinstance(row, list) and len(row) == 5 and row[0] == member]
            if len(selected) != 1:
                raise ValueError('world ROOT member is missing or ambiguous')
            row = selected[0]
            name = 'root' + ('/' + member if member else '')
            matches = [entry for entry in archive if entry.name == name]
            if (len(matches) != 1 or not matches[0].isreg() or row[1] != 'file'
                    or type(row[2]) is not int or not 0 < row[2] <= 8 * 1024 * 1024
                    or matches[0].size != row[2]):
                raise ValueError('world ROOT member differs from its manifest')
            data = archive.extractfile(matches[0]).read()
            if hashlib.sha256(data).hexdigest() != row[4]:
                raise ValueError('world ROOT payload differs from its manifest')
    else:
        if member or source.stat().st_size > 8 * 1024 * 1024:
            raise ValueError('world JSON selector differs or exceeds its bound')
        data = source.read_bytes()
    world = json.loads(data)
    start = world.get('player_start') if isinstance(world, dict) else None
    if (not isinstance(start, list) or len(start) != 4
            or any(type(value) not in (int, float) or not math.isfinite(value) for value in start)):
        raise ValueError('world player_start must contain four finite coordinates')
    return world


def _original_builder(unreal):
    """Compile only the actual keyed definitions, never setup_project's module body."""
    scripts = Path(__file__).resolve().parents[1] / 'unreal/Scripts'
    namespace = {'unreal': unreal, 'LOG': unreal.log}
    for filename, names in [('material_assets.py', {'opt'}),
                            ('setup_project.py', {'soft_colour_grade', 'build_level'})]:
        path = scripts / filename
        tree = ast.parse(path.read_text(), filename=str(path))
        definitions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
        if len(definitions) != len(names) or {node.name for node in definitions} != names:
            raise ValueError('original map helper definitions are missing or ambiguous')
        exec(compile(ast.Module(body=definitions, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace['build_level']


def run(context):
    """@cc [owner:fontanierh,label:correctness] original-slice-map-only
    The body MUST load only declared finished native inputs and selected frozen
    world data, then call the original keyed build_level with its original helpers.
    It MUST NOT execute setup_project module globals, main, purge, receiving or
    cache paths. Exactly Slice MUST be saved; failure MUST refuse. After save the
    editor MUST switch to a fresh unsaved blank world to release map roots for C3
    reset, and failure to create that blank MUST also refuse completion.
    """
    import unreal
    if set(context.params) != {'args', 'settings'} or context.params['settings'] != []:
        raise ValueError('unsupported map parameters')
    args = context.params['args']
    if (set(args) != {'package', 'world', 'native', 'terrain'} or args['package'] != PACKAGE
            or list(context.outputs) != [PACKAGE]):
        raise ValueError('map author must own exactly Slice')
    native = args['native']
    if 'painterly' not in native or not args['terrain']:
        raise ValueError('map requires painterly and terrain inputs')
    rows = {}
    for parent, value in args['terrain'].items():
        if parent == 'Sea' or not parent or any(c in parent for c in '/\\:\x00'):
            raise ValueError('foreign map terrain parent')
        if isinstance(value, dict):
            if set(value) != {'derived_items'} or set(value['derived_items']) != {'root', 'members'}:
                raise ValueError('map terrain expansion must be resolved before keying')
            value = value['derived_items']['members']
        if not isinstance(value, (list, tuple)) or not value:
            raise ValueError('empty map terrain membership')
        names = set()
        rows[parent] = []
        for row in value:
            if (not {'piece', 'slot'} <= set(row) or set(row) - {'piece', 'slot', 'root'}
                    or not isinstance(row['piece'], str) or not row['piece']
                    or any(c in row['piece'] for c in '/\\:\x00') or row['piece'].casefold() in names):
                raise ValueError('invalid or duplicate map piece')
            names.add(row['piece'].casefold())
            rows[parent].append((row['piece'], row['slot']))
    mesh_slots = [slot for pieces in rows.values() for _, slot in pieces]
    if len(set(mesh_slots)) != len(mesh_slots) or set(mesh_slots) & {'world', 'painterly'}:
        raise ValueError('map terrain slots overlap')
    slots = {'world', *native, *mesh_slots}
    if set(context.inputs) != slots or set(context.packages) != slots or context.packages['world'] != []:
        raise ValueError('map inputs differ from declared native/data membership')
    world = world_data(context, args['world'])
    loaded = {}
    for slot in sorted(slots - {'world'}):
        values = context.packages[slot]
        paths = [values] if isinstance(values, str) else list(values)
        if (len(paths) != 1 or not paths[0].startswith('/Game/') or paths[0] == PACKAGE
                or paths[0].startswith(('/Game/AtelierRaw/', '/Game/_Raw/')) or (slot in native and native[slot] != paths[0])):
            raise ValueError('map requires one exact finished package per input')
        asset = unreal.EditorAssetLibrary.load_asset(paths[0])
        if asset is None or (slot in mesh_slots and not isinstance(asset, unreal.StaticMesh)):
            raise ValueError('missing or wrong-class map native input: ' + paths[0])
        loaded[slot] = asset
    terrain = {parent: [(piece, loaded[slot]) for piece, slot in pieces] for parent, pieces in rows.items()}
    _original_builder(unreal)(terrain, world, {'_painterly': loaded['painterly']})
    if unreal.EditorLoadingAndSavingUtils.new_blank_map(False) is None:
        raise RuntimeError('Failed to release Slice editor world for reset')
