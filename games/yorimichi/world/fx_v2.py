"""Native bodies for the /Game/FX materials, one declared package per job.

Scripts/import_combat_fx.py builds everything at import time; these bodies never execute its top level. They take
its definitions by name (``material``, ``node``, ``sprite_material``, ``instance``) and, for M_FX_Trail, its
original top-level trail statements, and run them with module globals rebuilt from the job. ``args.action``:
- ``sprite``: M_FX_Additive or M_FX_Dust by the original sprite_material over its declared default sprite;
- ``trail``: M_FX_Trail by the original statements over the declared T_FX_Trail;
- ``instance``: one MI_FX_* by the original instance over its declared parent and sprite.
"""
import ast
from pathlib import Path

ORIGINAL = 'games/yorimichi/unreal/Scripts/import_combat_fx.py'
DEST = '/Game/FX'
DEFINITIONS = ('material', 'node', 'sprite_material', 'instance')
FIELDS = {'sprite': {'action', 'name', 'inputs', 'blend', 'texture'},
          'trail': {'action', 'name', 'inputs', 'texture'},
          'instance': {'action', 'name', 'inputs', 'parent', 'texture'}}


def _source(context):
    path = Path(context.job_dir) / ORIGINAL
    if path.is_symlink() or not path.is_file():
        raise ValueError('The original combat FX importer is not staged keyed code')
    return path, ast.parse(path.read_text(), str(path))


def _trail(tree):
    """The original top-level statements from `trail = material('M_FX_Trail')` through its save."""
    body = tree.body
    starts = [i for i, node in enumerate(body) if isinstance(node, ast.Assign)
              and [getattr(t, 'id', None) for t in node.targets] == ['trail']]
    if len(starts) != 1:
        raise ValueError('The original importer lacks its trail graph')
    for end in range(starts[0], len(body)):
        node = body[end]
        if (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
                and ast.unparse(node.value) == 'E.save_loaded_asset(trail)'):
            return body[starts[0]:end + 1]
    raise ValueError('The original trail graph is never saved')


def original(context, unreal, *, trail=False):
    path, tree = _source(context)
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in DEFINITIONS]
    if sorted(node.name for node in nodes) != sorted(DEFINITIONS):
        raise ValueError('The original combat FX importer lacks a required definition')
    namespace = {'U': unreal, 'E': unreal.EditorAssetLibrary, 'AT': unreal.AssetToolsHelpers.get_asset_tools(),
                 'M': unreal.MaterialEditingLibrary, 'DEST': DEST}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), namespace)
    if trail:
        namespace['trail_graph'] = compile(ast.Module(body=_trail(tree), type_ignores=[]), str(path), 'exec')
    return namespace


def _inputs(context, unreal, args):
    bound = args['inputs']
    if not isinstance(bound, dict) or set(context.inputs) != set(bound) or set(context.packages) != set(bound):
        raise ValueError('FX inputs differ from the declared finished packages')
    loaded = {}
    for slot, package in bound.items():
        packages = context.packages[slot]
        packages = [packages] if isinstance(packages, str) else list(packages)
        if packages != [package] or not package.startswith('/Game/') or package.startswith('/Game/_Raw/'):
            raise ValueError('FX input must be exactly its declared finished package: ' + slot)
        asset = unreal.EditorAssetLibrary.load_asset(package)
        if asset is None or asset.get_path_name().split('.', 1)[0] != package:
            raise ValueError('Declared FX input did not load: ' + package)
        loaded[package] = asset
    return loaded


def _texture(unreal, loaded, package):
    texture = loaded.get(package)
    if not isinstance(texture, unreal.Texture2D):
        raise ValueError('FX material needs its declared sprite texture: ' + str(package))
    return texture


def run(context):
    """@cc [owner:fontanierh,label:correctness] c3-combat-fx-materials
    Each job MUST author exactly its declared /Game/FX package with the original
    definitions or trail statements, over only its declared finished inputs, and
    read the saved result back. It MUST NOT import sprites, run the original top
    level, make directories outside its package or write the import report.
    """
    import unreal
    params = context.params
    args = params.get('args')
    if (set(params) != {'args', 'settings'} or params['settings'] != [] or not isinstance(args, dict)
            or args.get('action') not in FIELDS or set(args) != FIELDS[args['action']]):
        raise ValueError('Unsupported FX material parameters')
    package = DEST + '/' + args['name']
    if list(context.outputs) != [package] or unreal.EditorAssetLibrary.does_asset_exist(package):
        raise ValueError('FX job owns exactly its fresh declared package: ' + package)
    loaded = _inputs(context, unreal, args)
    texture = _texture(unreal, loaded, args['texture'])
    namespace = original(context, unreal, trail=args['action'] == 'trail')
    if args['action'] == 'sprite':
        if args['name'] not in ('M_FX_Additive', 'M_FX_Dust') or args['blend'] not in ('BLEND_ADDITIVE', 'BLEND_TRANSLUCENT'):
            raise ValueError('Unknown FX sprite material')
        blend = getattr(unreal.BlendMode, args['blend'])
        asset = namespace['sprite_material'](args['name'], blend, texture)
        if asset.get_editor_property('blend_mode') != blend:
            raise ValueError('FX sprite material lost its blend mode')
    elif args['action'] == 'trail':
        if args['name'] != 'M_FX_Trail':
            raise ValueError('Unknown FX trail material')
        namespace['textures'] = {'Trail': texture}
        exec(namespace.pop('trail_graph'), namespace)
        asset = namespace['trail']
    else:
        parent = loaded.get(args['parent'])
        if not isinstance(parent, unreal.Material):
            raise ValueError('FX instance needs its declared parent material')
        asset = namespace['instance'](args['name'], parent, texture)
        if asset.get_editor_property('parent') != parent:
            raise ValueError('FX instance lost its parent')
    if asset is None or asset.get_path_name().split('.', 1)[0] != package:
        raise ValueError('FX material not authored at its declared package: ' + package)
    return asset
