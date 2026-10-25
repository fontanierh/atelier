"""Original narrow Treehouse factories, without executing the importer's top-level code."""
import ast
import hashlib
import json
import math
from pathlib import Path
import sys
import tarfile

MAT = '/Game/Japan/Treehouse/Materials/'


def _pairs(rows):
    result = {}
    for key, value in rows:
        if key in result:
            raise ValueError('Duplicate Treehouse source JSON field')
        result[key] = value
    return result


def read_data(context, selection):
    """Read exactly one declared bounded JSON member of an actual frozen Data Item."""
    from atelier.build_v2.recipe_job import relative
    slot, filename, member = selection['slot'], relative(selection['file']), relative(selection['member'])
    root = Path(context.inputs[slot])
    if not root.is_absolute() or not root.is_relative_to(Path(context.job_dir)) or root.resolve() != root:
        raise ValueError('Treehouse metadata must be staged job-local content')
    path = root / filename if root.is_dir() else root
    if path.is_symlink() or not path.is_file() or path.resolve() != path or path.stat().st_nlink != 1:
        raise ValueError('Treehouse metadata source is missing or linked')
    if path.name.endswith('.tree.tar'):
        with tarfile.open(path, 'r:') as archive:
            members = archive.getmembers()
            if (not members or len(members) > 65536 or members[0].name != 'atelier-root.json'
                    or not members[0].isreg() or members[0].size > 16 * 1024 * 1024
                    or len({m.name for m in members}) != len(members)):
                raise ValueError('Invalid complete Treehouse Data ROOT')
            manifest = json.loads(archive.extractfile(members[0]).read(), object_pairs_hook=_pairs)
            if (set(manifest) != {'version', 'kind', 'entries'} or manifest['version'] != 1
                    or manifest['kind'] != 'directory' or not isinstance(manifest['entries'], list)
                    or len(manifest['entries']) + 1 != len(members)):
                raise ValueError('Incomplete Treehouse Data ROOT')
            rows = [(entry, row) for entry, row in zip(members[1:], manifest['entries'])
                    if isinstance(row, list) and len(row) == 5 and row[0] == member]
            if len(rows) != 1:
                raise ValueError('Treehouse metadata member is absent or ambiguous')
            entry, row = rows[0]
            if (entry.name != 'root/' + member or not entry.isreg() or row[1] != 'file'
                    or entry.size != row[2] or not 0 < entry.size <= 4 * 1024 * 1024):
                raise ValueError('Treehouse metadata member differs from ROOT')
            raw = archive.extractfile(entry).read()
            if hashlib.sha256(raw).hexdigest() != row[4]:
                raise ValueError('Treehouse metadata bytes differ from ROOT')
    else:
        selected = path.parent / member if root.is_file() else root / member
        if selected != path or not 0 < path.stat().st_size <= 4 * 1024 * 1024:
            raise ValueError('Treehouse direct metadata selection differs')
        raw = path.read_bytes()
    result = json.loads(raw, object_pairs_hook=_pairs,
                        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite Treehouse metadata')))
    if not isinstance(result, dict):
        raise ValueError('Treehouse metadata must be an object')
    return result


def _literal(node):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'dict' and not node.args:
        if any(keyword.arg is None for keyword in node.keywords):
            raise ValueError('Unbounded Treehouse constant')
        return {keyword.arg: _literal(keyword.value) for keyword in node.keywords}
    if isinstance(node, ast.Dict):
        return {_literal(key): _literal(value) for key, value in zip(node.keys, node.values)}
    return ast.literal_eval(node)


def factories(unreal):
    """Compile only three original factory definitions and their literal constants."""
    scripts = Path(__file__).resolve().parents[1] / 'unreal/Scripts'
    sys.path.insert(0, str(scripts))
    import see_through
    source = scripts / 'import_treehouse.py'
    parsed = ast.parse(source.read_bytes(), filename=str(source))
    names = {'parent', 'instance', 'light_parent'}
    definitions = [node for node in parsed.body if isinstance(node, ast.FunctionDef) and node.name in names]
    if len(definitions) != len(names) or any(node.decorator_list for node in definitions):
        raise ValueError('Original Treehouse narrow factories are missing or decorated')
    constants = {}
    for node in parsed.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in ('GLOW', 'SUN_TINT', 'LIGHT'):
                constants[name] = _literal(node.value)
    if set(constants) != {'GLOW', 'SUN_TINT', 'LIGHT'}:
        raise ValueError('Original Treehouse shader constants missing')
    namespace = {'unreal': unreal, 'E': unreal.EditorAssetLibrary, 'MEL': unreal.MaterialEditingLibrary,
                 'AT': unreal.AssetToolsHelpers.get_asset_tools(), 'MAT': MAT.rstrip('/'),
                 'see_through': see_through, **constants}
    exec(compile(ast.Module(body=definitions, type_ignores=[]), str(source), 'exec'), namespace)
    return namespace


def run(context):
    """@cc [owner:fontanierh,label:correctness] treehouse-original-material-factories
    Each job MUST author only its one original package with the actual parent,
    texture and collection inputs. Original shader/cloth/room/fade/gain/glow and
    light constants MUST survive. Only selected named function AST definitions MAY
    execute; original imports/top-level/main MUST NOT run. Gain/glow MUST be finite
    values from the declared finished metadata; missing native/data roles refuse.
    """
    import unreal
    if set(context.params) != {'args', 'settings'} or context.params['settings'] != []:
        raise ValueError('Unexpected Treehouse material parameters')
    args = context.params['args']
    if set(args) - {'asset', 'package', 'factory', 'inputs', 'key', 'data'} or not {'asset', 'package', 'factory', 'inputs'} <= set(args):
        raise ValueError('Unexpected Treehouse material arguments')
    name, package, factory = args['asset'], args['package'], args['factory']
    expected = '/Game/Japan/Materials/' + name if factory == 'foliage' else MAT + name
    if package != expected or list(context.outputs) != [package]:
        raise ValueError('Treehouse material owns exactly its original one package')
    inputs = args['inputs']
    data = args.get('data')
    if not isinstance(inputs, dict) or set(context.inputs) != set(inputs) | ({data['slot']} if data else set()):
        raise ValueError('Treehouse material slots differ from declared inputs')
    loaded = {}
    for slot, native in inputs.items():
        if context.packages.get(slot) not in (native, [native]) or native == package or not native.startswith('/Game/'):
            raise ValueError('Treehouse native input differs')
        asset = unreal.EditorAssetLibrary.load_asset(native)
        if asset is None or asset.get_path_name().split('.')[0] != native:
            raise ValueError('Treehouse declared dependency did not load')
        loaded[native] = asset
    if data and context.packages.get(data['slot']) not in ([], ()):
        raise ValueError('Treehouse palette metadata must be Data, not native packages')
    original = factories(unreal)
    E, MEL, AT = unreal.EditorAssetLibrary, unreal.MaterialEditingLibrary, unreal.AssetToolsHelpers.get_asset_tools()
    if E.does_asset_exist(package):
        raise ValueError('Treehouse material destination must be fresh')
    if factory == 'parent' and name == 'M_TreeHouse':
        result = original['parent'](loaded['/Game/Japan/Treehouse/Textures/T_TH_wood_plank'])
    elif factory == 'light_parent' and name == 'M_TH_Light':
        # Same original parent graph; instances have their own separate owner jobs.
        original['LIGHT'] = {}
        original['light_parent']()
        result = E.load_asset(package)
    elif factory in ('palette', 'trunk', 'prop'):
        key = args['key']
        rows = read_data(context, data)
        row = rows.get(key)
        if not isinstance(row, dict) or type(row.get('gain')) not in (int, float) or not math.isfinite(row['gain']) or row['gain'] <= 0:
            raise ValueError('Missing actual finite Treehouse texture gain')
        if factory == 'palette':
            if name != 'MI_TH_' + key:
                raise ValueError('Treehouse palette instance identity differs')
            texture = '/Game/Japan/Treehouse/Textures/T_TH_' + key
            glow = original['GLOW'].get(key, 0.)
        elif factory == 'trunk':
            if key != 'bark' or name != 'MI_TH_trunk':
                raise ValueError('Treehouse trunk identity differs')
            texture, glow = '/Game/Japan/Treehouse/Textures/T_TH_bark', 0.
        else:
            if not key.startswith('TH_P_') or name != 'MI_' + key:
                raise ValueError('Treehouse prop instance identity differs')
            texture, glow = '/Game/Japan/Treehouse/Textures/T_' + key, row.get('glow', 0.)
        if type(glow) not in (int, float) or not math.isfinite(glow):
            raise ValueError('Invalid original Treehouse glow')
        result = original['instance'](name, loaded[MAT + 'M_TreeHouse'], loaded[texture], row['gain'], glow)
        if factory == 'trunk':
            MEL.set_material_instance_scalar_parameter_value(result, 'RoomCut', 0.)
            MEL.update_material_instance(result)
    elif factory in ('pane', 'foliage'):
        if factory == 'pane' and name == 'MI_TH_pane':
            parent = loaded[MAT + 'M_TH_Light']; texture = None
        elif factory == 'foliage' and name in ('MI_LeafCrimson', 'MI_LeafAmber'):
            parent = loaded['/Game/Japan/Materials/M_Foliage']
            texture = loaded['/Game/Japan/Textures/T_leaf_' + name.removeprefix('MI_Leaf').lower()]
        else:
            raise ValueError('Unexpected Treehouse leaf/light instance')
        result = AT.create_asset(name, package.rsplit('/', 1)[0], unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
        MEL.set_material_instance_parent(result, parent)
        if texture is not None:
            MEL.set_material_instance_texture_parameter_value(result, 'Tex', texture)
        else:
            for key, value in original['LIGHT']['pane'].items():
                MEL.set_material_instance_scalar_parameter_value(result, key, float(value))
        MEL.update_material_instance(result)
    else:
        raise ValueError('Unsupported Treehouse narrow factory')
    if result is None or result.get_path_name().split('.')[0] != package or not E.save_loaded_asset(result, False):
        raise ValueError('Treehouse material identity/save failed')
    return result
