"""One independently authored island material, over explicit frozen dependencies."""
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import sys
import tarfile


def _relative(name):
    if (not isinstance(name, str) or not name or '\\' in name or PurePosixPath(name).is_absolute()
            or str(PurePosixPath(name)) != name or any(part in ('.', '..') for part in name.split('/'))):
        raise ValueError('noncanonical island metadata member')
    return name


def snow_join(context, selection):
    """Read the actual selected frozen JSON, including the existing file ROOT codec."""
    source = Path(context.inputs['north_snow'])
    if source.is_dir():
        source /= _relative(selection['file'])
    if source.name.endswith('.tree.tar'):
        with tarfile.open(source, 'r:') as archive:
            members = archive.getmembers()
            if (not members or members[0].name != 'atelier-root.json' or not members[0].isreg()
                    or members[0].size > 16 * 1024 * 1024):
                raise ValueError('missing bounded north_snow ROOT manifest')
            manifest = json.loads(archive.extractfile(members[0]).read())
            member = selection.get('member', '')
            if member:
                _relative(member)
            if (set(manifest) != {'version', 'kind', 'entries'} or manifest['version'] != 1
                    or manifest['kind'] not in ('file', 'directory') or not isinstance(manifest['entries'], list)
                    or len(members) != len(manifest['entries']) + 1):
                raise ValueError('incomplete north_snow ROOT')
            selected = [(entry, row) for entry, row in zip(members[1:], manifest['entries'])
                        if isinstance(row, list) and len(row) == 5 and row[0] == member]
            if len(selected) != 1:
                raise ValueError('north_snow ROOT member is absent or ambiguous')
            entry, row = selected[0]
            name = 'root' + ('/' + member if member else '')
            if (entry.name != name or not entry.isreg() or row[1] != 'file' or entry.size != row[2]
                    or not 0 < entry.size <= 1024 * 1024):
                raise ValueError('north_snow ROOT member differs')
            data = archive.extractfile(entry).read()
            if hashlib.sha256(data).hexdigest() != row[4]:
                raise ValueError('north_snow ROOT payload differs from its manifest')
    else:
        if not source.is_file() or source.stat().st_size > 1024 * 1024:
            raise ValueError('missing bounded north_snow JSON')
        data = source.read_bytes()
    value = json.loads(data)['south_join_m']
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('north_snow south_join_m must be finite')
    return value


def _helpers():
    scripts = Path(__file__).resolve().parents[1] / 'unreal/Scripts'
    sys.path.insert(0, str(scripts))
    import forest_ground
    import import_southwest
    import material_assets
    return forest_ground, import_southwest, material_assets


def run(context):
    """@cc [owner:fontanierh,label:correctness] one-island-material-write
    Each job MUST save only its declared material/instance. The forest join MUST
    come from its declared JSON and rock colour from a separately finished texture.
    Production MUST call narrow original factories with explicit inputs and MUST
    NOT fall back to ambient generated data, texture import, old receiving/cache
    actions or parent recreation. Native compilation/save failure MUST refuse.
    """
    import unreal
    if set(context.params) != {'args', 'settings'} or context.params['settings'] != []:
        raise ValueError('unsupported island material parameters')
    args = context.params['args']
    name, package, factory = args['asset'], args['package'], args['factory']
    if package != '/Game/Japan/Materials/' + name or list(context.outputs) != [package]:
        raise ValueError('island author must own exactly one material package')
    fields = {'forest': {'north_snow'}, 'coast': {'parent'}, 'instance': {'parent'}, 'rock': set(), 'sand': set(), 'sea': set()}
    if factory not in fields or set(args) - {'asset', 'package', 'factory', 'inputs'} - fields[factory]:
        raise ValueError('unsupported island material factory arguments')
    declared = args['inputs']
    slots = set(declared) | ({'north_snow'} if factory == 'forest' else set())
    if set(context.inputs) != slots or set(context.packages) != slots:
        raise ValueError('island material slots differ from declared dependencies')
    for slot, path in declared.items():
        if context.packages[slot] not in (path, [path]) or not path.startswith('/Game/') or path == package:
            raise ValueError('island material native dependency differs')
    if factory == 'forest' and context.packages['north_snow'] != []:
        raise ValueError('north_snow must be declared data, not a native package')
    join = snow_join(context, args['north_snow']) if factory == 'forest' else None
    loaded = {}
    for slot, path in declared.items():
        asset = unreal.EditorAssetLibrary.load_asset(path)
        if asset is None:
            raise ValueError('missing declared island material input: ' + path)
        loaded[slot] = asset
    forest, southwest, assets = _helpers()
    if factory == 'forest' and name == 'M_ForestGround':
        result = forest.material(south_join_m=join)
    elif factory == 'rock' and name == 'M_CoastRock':
        result = forest.rock_material(texture=loaded['T_CoastRock'])
    elif factory == 'coast' and name == 'MI_Coast':
        result = forest.coast_instance(parent=loaded[args['parent']])
    elif factory == 'instance' and name in ('MI_FarForest', 'MI_CoastRock'):
        result = assets.instance(name, loaded[args['parent']])
    elif factory == 'sand' and name == 'MI_Sand':
        result = southwest.sand_material()
    elif factory == 'sea' and name == 'M_Sea':
        result = southwest.sea_material()
    else:
        raise ValueError('unsupported island material factory')
    if result is None or result.get_path_name().split('.')[0] != package:
        raise ValueError('island material factory returned another package')
    if name.startswith('M_'):
        assets.save_material(result)
    elif not unreal.EditorAssetLibrary.save_loaded_asset(result, False):
        raise ValueError('could not save island material instance')
