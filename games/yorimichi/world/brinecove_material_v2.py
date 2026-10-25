"""One original Brinecove shader package per job, with no old receiver execution."""
import ast
import math
from pathlib import Path
import re
import sys

ROOT = '/Game/Brinecove'
PARENTS = {'opaque': 'M_Brinecove', 'emissive': 'M_Brinecove', 'masked': 'M_BrinecoveMasked',
           'translucent': 'M_BrinecoveSpray', 'terrain': 'M_BrinecoveTerrain'}


def factories(unreal):
    """Compile original named parent graph functions, never original imports/main."""
    scripts = Path(__file__).resolve().parents[1] / 'unreal/Scripts'
    sys.path.insert(0, str(scripts))
    import atmosphere
    source = scripts / 'import_brinecove.py'
    tree = ast.parse(source.read_bytes())
    namespace = {'unreal': unreal, 'ROOT': ROOT, 'E': unreal.EditorAssetLibrary,
        'MEL': unreal.MaterialEditingLibrary, 'AT': unreal.AssetToolsHelpers.get_asset_tools(),
        'atmosphere': atmosphere}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            key = node.targets[0].id
            if key in ('PARENTS', 'MOTION', 'TERRAIN_WEIGHTS'):
                namespace[key] = ast.literal_eval(node.value)
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in ('parent', 'terrain_parent')]
    if len(functions) != 2 or any(node.decorator_list for node in functions) or not {'PARENTS', 'MOTION', 'TERRAIN_WEIGHTS'} <= set(namespace):
        raise ValueError('Missing original Brinecove parent shader source')
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), 'exec'), namespace)
    return namespace


def descriptor(value):
    """Closed original instance fields, preserving optional original motion defaults."""
    if not isinstance(value, dict) or set(value) - {'name', 'colour', 'texture', 'kind', 'pan', 'motion', 'roughness', 'metal', 'layers', 'normals', 'rock_only'}:
        raise ValueError('Unexpected Brinecove material descriptor')
    if (not isinstance(value.get('name'), str) or not re.fullmatch('MI_BC_[A-Za-z0-9_-]+', value['name'])
            or value.get('kind') not in PARENTS or not isinstance(value.get('colour'), (list, tuple))
            or len(value['colour']) != 3 or any(type(n) not in (int, float) or not math.isfinite(n) for n in value['colour'])):
        raise ValueError('Invalid original Brinecove material identity/colour/kind')
    if value['kind'] == 'terrain':
        if (type(value.get('rock_only')) is not bool or not isinstance(value.get('layers'), dict)
                or set(value['layers']) != {'Sand', 'Meadow', 'Forest', 'Rock'}
                or not isinstance(value.get('normals'), dict) or set(value['normals']) != {'SandN', 'MeadowN', 'ForestN', 'RockN'}
                or any(not isinstance(name, str) or not name for table in ('layers', 'normals') for name in value[table].values())):
            raise ValueError('Brinecove terrain requires all original albedo/normal-cavity layers')
    else:
        if (type(value.get('metal')) is not bool or any(type(value.get(key)) not in (int, float)
                or not math.isfinite(value[key]) for key in ('pan', 'roughness'))
                or not isinstance(value.get('motion', {}), dict)
                or any(key not in ('Drift', 'Wash', 'Layer', 'Opacity') or type(n) not in (int, float) or not math.isfinite(n)
                       for key, n in value.get('motion', {}).items())):
            raise ValueError('Invalid original Brinecove surface parameters')
    return value


def run(context):
    """@cc [owner:fontanierh,label:correctness] individual-brinecove-material-body
    Each invocation MUST author/save only one fresh declared original package.
    Parent shader graphs MUST use original named AST functions and atmosphere code,
    never old top-level/main or receiver/cache state. Instance colour, motion,
    texture, roughness, metal, glow and complete terrain layers MUST match the
    declared original semantic descriptor. Every native texture/parent MUST be an
    explicit loaded input; missing roles, nonfinite data and failed saves refuse.
    """
    import unreal
    if set(context.params) != {'args', 'settings'} or context.params['settings'] != []:
        raise ValueError('Unexpected Brinecove material settings')
    args = context.params['args']
    if set(args) - {'asset', 'package', 'factory', 'inputs', 'blend', 'descriptor'} or not {'asset', 'package', 'factory', 'inputs'} <= set(args):
        raise ValueError('Unexpected Brinecove material arguments')
    name, package, factory = args['asset'], args['package'], args['factory']
    if package != ROOT + '/Materials/' + name or list(context.outputs) != [package]:
        raise ValueError('Brinecove material must own exactly its original one package')
    declared = args['inputs']
    if not isinstance(declared, dict) or set(context.inputs) != set(declared) or set(context.packages) != set(declared):
        raise ValueError('Brinecove material inputs differ from explicit native dependencies')
    loaded = {}
    E, MEL, AT = unreal.EditorAssetLibrary, unreal.MaterialEditingLibrary, unreal.AssetToolsHelpers.get_asset_tools()
    for slot, path in declared.items():
        if not isinstance(path, str) or not path.startswith('/Game/') or path == package or context.packages[slot] not in (path, [path]):
            raise ValueError('Brinecove native dependency differs')
        asset = E.load_asset(path)
        if asset is None or asset.get_path_name().split('.')[0] != path:
            raise ValueError('Missing actual Brinecove native dependency')
        loaded[path] = asset
    if E.does_asset_exist(package):
        raise ValueError('Brinecove material destination must be fresh')
    if factory in ('parent', 'terrain_parent'):
        blend = args.get('blend')
        if blend not in ('opaque', 'masked', 'translucent', 'terrain') or name != PARENTS[blend] or bool(blend == 'terrain') != bool(factory == 'terrain_parent'):
            raise ValueError('Brinecove parent identity/blend differs')
        original = factories(unreal)
        result = original['terrain_parent']() if factory == 'terrain_parent' else original['parent'](name, blend)
    elif factory == 'instance':
        entry = descriptor(args.get('descriptor'))
        if entry['name'] != name:
            raise ValueError('Brinecove instance differs from original descriptor')
        parent = loaded[ROOT + '/Materials/' + PARENTS[entry['kind']]]
        result = AT.create_asset(name, ROOT + '/Materials', unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
        if result is None:
            raise ValueError('Brinecove instance creation failed')
        MEL.clear_all_material_instance_parameters(result)
        MEL.set_material_instance_parent(result, parent)
        MEL.set_material_instance_vector_parameter_value(result, 'Colour', unreal.LinearColor(*entry['colour'], 1.))
        def image(filename):
            if not isinstance(filename, str) or Path(filename).name != filename or not filename.startswith('T_BC_'):
                raise ValueError('Invalid original Brinecove texture role')
            return loaded[ROOT + '/Textures/' + Path(filename).stem]
        if entry['kind'] == 'terrain':
            MEL.set_material_instance_scalar_parameter_value(result, 'RockOnly', 1. if entry['rock_only'] else 0.)
            for key, filename in [*entry['layers'].items(), *entry['normals'].items()]:
                MEL.set_material_instance_texture_parameter_value(result, key, image(filename))
        else:
            for key, value in entry.get('motion', {}).items():
                MEL.set_material_instance_scalar_parameter_value(result, key, float(value))
            scalars = {'UseTex': float(bool(entry.get('texture'))), 'Pan': float(entry['pan']), 'Roughness': float(entry['roughness']),
                       'Metallic': .6 if entry['metal'] else 0., 'Glow': 1.6 if entry['kind'] == 'emissive' else .045}
            for key, value in scalars.items():
                MEL.set_material_instance_scalar_parameter_value(result, key, value)
            if entry.get('texture'):
                MEL.set_material_instance_texture_parameter_value(result, 'Tex', image(entry['texture']))
        MEL.update_material_instance(result)
    else:
        raise ValueError('Unsupported original Brinecove material factory')
    if result is None or result.get_path_name().split('.')[0] != package or not E.save_loaded_asset(result, False):
        raise ValueError('Brinecove material identity/save failed')
    return result
