"""Native bodies for unreal.north's own packages (Scripts/mountain_material.py), one declared package per job.

The original import_hidamari.py run with HIDAMARI_ASSETS=HD_North* calls mountain_material.material(), whose
prelude imports and sets T_VolcanicRock, T_NorthSnowMask, T_NorthCraterMask and T_NorthCraterFloor inline, then
rock_material(parent) and gate_material(). Here those four textures are raw import + finish units (their properties
come from that prelude, by ``split``), and ``args.action`` selects
- ``mountains``: material() with exactly its texture-import statements removed; its metadata gates and graph run
  unchanged, the four names bound to the finished textures, yori.OUT reading only the declared source Items;
- ``rock``: rock_material(M_NorthMountains);
- ``gate``: gate_material().
The HD_North* meshes belong to the city; the original top level, cache and reports never run.
"""
import ast
import json
from pathlib import Path, PurePosixPath
import re
import sys

PACKAGE = re.compile(r'/Game/(?:[A-Za-z0-9_]+/)*[A-Za-z0-9_]+\Z')
SCRIPTS = 'games/yorimichi/unreal/Scripts'
TOOLS = 'games/yorimichi/tools'
ORIGINAL = SCRIPTS + '/mountain_material.py'
TEXTURE_NAMES = ('rock', 'snow_texture', 'crater_texture', 'floor_texture')
FUNCTIONS = ('crater_hlsl', 'floor_hlsl', 'material', 'rock_material', '_seamless', 'gate_material')
PACKAGES = {'mountains': '/Game/Japan/Materials/M_NorthMountains', 'rock': '/Game/Japan/Materials/MI_NorthRockCaps',
            'gate': '/Game/Japan/Materials/M_NorthGate'}
# What material() reads through yori.OUT, by the slot and member each arrives in.
VIEW = {'hidamari/north_snow.json': ('snow', None), 'hidamari/north_crater.json': ('crater', None),
        'craterpark/textures/textures.json': ('restyle', 'textures.json')}


def _names(node):
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _texture_statement(node):
    """One statement of material()'s inline texture import/property prelude."""
    if 'task' in _names(node):
        return True
    if isinstance(node, ast.Assign):
        return any(isinstance(t, ast.Name) and t.id in TEXTURE_NAMES for t in node.targets)
    if isinstance(node, ast.Assert):
        return isinstance(node.test, ast.Name) and node.test.id in TEXTURE_NAMES
    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
        call = node.value
        if isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name):
            if call.func.value.id in TEXTURE_NAMES:
                return True
            if call.func.attr == 'save_loaded_asset' and len(call.args) == 1 and isinstance(call.args[0], ast.Name):
                return call.args[0].id in TEXTURE_NAMES
    return False


def _value(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (bool, int, float, str)):
        return node.value
    text = ast.unparse(node)
    if re.fullmatch(r'unreal\.[A-Za-z_]+\.[A-Z0-9_]+', text):
        return {'unreal_enum': text.removeprefix('unreal.')}
    raise ValueError('mountain_material texture property is not a literal or enum: ' + text)


def split(source):
    """(texture specs, graph statements) of material(): each spec is the prelude's own
    {name, package, filename, properties}; the graph keeps every other statement in order. A texture name that
    the graph would assign, or an import that is not exactly task, load, properties, save, refuses."""
    tree = ast.parse(source)
    found = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'material']
    if len(found) != 1:
        raise ValueError('mountain_material.py no longer defines material()')
    specs, graph, task, current = [], [], {}, None
    for node in found[0].body:
        if not _texture_statement(node):
            if any(isinstance(t, ast.Name) and t.id in TEXTURE_NAMES
                   for n in ast.walk(node) if isinstance(n, (ast.Assign, ast.AugAssign, ast.NamedExpr))
                   for t in ([n.target] if not isinstance(n, ast.Assign) else n.targets)):
                raise ValueError('material() graph assigns a texture name')
            graph.append(node)
            continue
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id == 'task':
                task = {}
                continue
            if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == 'task':
                task[target.attr] = ast.unparse(node.value) if target.attr == 'filename' else _value(node.value)
                continue
            if isinstance(target, ast.Name) and target.id in TEXTURE_NAMES:
                call = node.value
                if (not isinstance(call, ast.Call) or ast.unparse(call.func) != 'e.load_asset' or len(call.args) != 1
                        or task.get('destination_path') is None):
                    raise ValueError('material() texture is not loaded from its import task')
                package = _value(call.args[0])
                if package != task['destination_path'] + '/' + task['destination_name'] or task.get('replace_existing') is not True:
                    raise ValueError('material() texture load differs from its import task')
                current = {'name': task['destination_name'], 'variable': target.id, 'package': package,
                           'filename': task['filename'], 'properties': {}}
                specs.append(current)
                continue
        if isinstance(node, ast.Expr) and 'import_asset_tasks' in ast.unparse(node):
            continue
        if isinstance(node, ast.Assert) and current and node.test.id == current['variable']:
            continue
        call = node.value if isinstance(node, ast.Expr) else None
        if (call is not None and current and isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                and isinstance(call.func.value, ast.Name)):
            if call.func.value.id == current['variable'] and call.func.attr == 'set_editor_property' and len(call.args) == 2:
                current['properties'][_value(call.args[0])] = _value(call.args[1])
                continue
            if call.func.attr == 'save_loaded_asset' and call.args[0].id == current['variable']:
                continue
        raise ValueError('unclassified material() texture statement: ' + ast.unparse(node))
    if sorted(spec['variable'] for spec in specs) != sorted(TEXTURE_NAMES):
        raise ValueError('material() no longer imports exactly its four textures')
    return specs, graph


def _path(asset):
    return asset.get_path_name().split('.', 1)[0]


def _selected(context, slot):
    if not isinstance(slot, str) or context.inputs.get(slot) is None:
        raise ValueError('Missing declared North input: ' + str(slot))
    packages = context.packages.get(slot)
    packages = [packages] if isinstance(packages, str) else packages
    if not isinstance(packages, (list, tuple)) or len(packages) != 1 or not PACKAGE.fullmatch(str(packages[0])):
        raise ValueError('North native input must be exactly one declared package: ' + slot)
    return packages[0]


def _load(unreal, context, slot, cls):
    package = _selected(context, slot)
    asset = unreal.EditorAssetLibrary.load_asset(package)
    if not isinstance(asset, cls) or _path(asset) != package:
        raise ValueError('Declared North input did not load as expected: ' + package)
    return asset


def _data(context, slot, *, directory=False):
    if context.inputs.get(slot) is None or context.packages.get(slot) not in ([], ()):
        raise ValueError('North source must be a declared Data Item: ' + str(slot))
    path = Path(context.inputs[slot])
    if (not path.is_absolute() or path.is_symlink() or path.resolve() != path
            or not path.is_relative_to(Path(context.job_dir).resolve())
            or not (path.is_dir() if directory else path.is_file())):
        raise ValueError('North source must be its exact job-local producer root: ' + slot)
    return path


def _member(root, name):
    path = root.joinpath(*PurePosixPath(name).parts)
    if (PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts or path.is_symlink()
            or path.resolve() != path or not path.is_file()):
        raise ValueError('North source member is absent or aliased: ' + name)
    return path


class _View:
    """yori.OUT for material(): exactly the declared metadata Items and the declared crater floor member."""

    def __init__(self, files, relative=''):
        self._files, self._relative = files, relative

    def __truediv__(self, other):
        return _View(self._files, '/'.join(p for p in (self._relative, str(other)) if p))

    def _file(self):
        if self._relative not in self._files:
            raise ValueError('material() reads an undeclared North source: ' + self._relative)
        return self._files[self._relative]

    def read_text(self, *args, **kwargs):
        return self._file().read_text(*args, **kwargs)

    def read_bytes(self):
        return self._file().read_bytes()

    def __str__(self):
        return 'OUT/' + self._relative


def _staged(context, relative):
    path = Path(context.job_dir) / relative
    if path.is_symlink() or not path.is_file():
        raise ValueError('North code is not staged keyed code: ' + relative)
    return path


def original(context, unreal, *, textures=None, view=None):
    """mountain_material.py's named functions and CRATER_PAINT bound to its own editor globals, material()
    without its texture prelude; craterpark_textures is its committed WORLD_ALIGNED table. No top level."""
    source = _staged(context, ORIGINAL).read_bytes()
    tree = ast.parse(source)
    nodes = [n for n in tree.body if (isinstance(n, ast.FunctionDef) and n.name in FUNCTIONS)
             or (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'CRATER_PAINT' for t in n.targets))]
    if {getattr(n, 'name', 'CRATER_PAINT') for n in nodes} != {*FUNCTIONS, 'CRATER_PAINT'} or len(nodes) != len(FUNCTIONS) + 1:
        raise ValueError('mountain_material.py no longer defines its native functions')
    _, graph = split(source)
    for node in nodes:
        if isinstance(node, ast.FunctionDef) and node.name == 'material':
            node.body = graph
    table = [n for n in ast.parse(_staged(context, TOOLS + '/craterpark_textures.py').read_bytes()).body
             if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'WORLD_ALIGNED' for t in n.targets)]
    if len(table) != 1:
        raise ValueError('craterpark_textures.py no longer defines WORLD_ALIGNED')
    scripts = str(Path(context.job_dir) / SCRIPTS)
    sys.path.insert(0, scripts)
    try:
        import atmosphere
        import ground_grain
    finally:
        sys.path.remove(scripts)
    import hashlib
    from types import SimpleNamespace
    scope = {'unreal': unreal, 'atmosphere': atmosphere, 'ground_grain': ground_grain, 'hashlib': hashlib, 'json': json,
             'yori': SimpleNamespace(OUT=view), 'craterpark_textures': SimpleNamespace(
                 WORLD_ALIGNED=ast.literal_eval(table[0].value)), **(textures or {})}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), 'mountain_material.py', 'exec'), scope)
    return scope


def _start(context, unreal, action):
    package = PACKAGES[action]
    if list(context.outputs) != [package]:
        raise ValueError('North job owns exactly its declared package: ' + package)
    if unreal.EditorAssetLibrary.does_asset_exist(package):
        raise ValueError('North destination must be fresh: ' + package)
    return package


def mountains(context, unreal, args):
    package = _start(context, unreal, 'mountains')
    specs, _ = split(_staged(context, ORIGINAL).read_bytes())
    textures = {}
    for spec in specs:
        texture = _load(unreal, context, args['textures'][spec['name']], unreal.Texture)
        if _path(texture) != spec['package']:
            raise ValueError('finished North texture differs from its import task: ' + spec['name'])
        textures[spec['variable']] = texture
    for slot in args['natives'].values():
        _selected(context, slot)
    restyle = _data(context, args['restyle'], directory=True)
    files = {relative: (_member(restyle, member) if member else _data(context, args[slot]))
             for relative, (slot, member) in VIEW.items()}
    painted = json.loads(files['craterpark/textures/textures.json'].read_bytes())['world_aligned']['crater_floor']
    if painted.get('png') != args['floor']:
        raise ValueError('textures.json names a crater floor other than the declared member')
    files['craterpark/textures/' + args['floor']] = _member(restyle, args['floor'])
    material = original(context, unreal, textures=textures, view=_View(files))['material']()
    if not isinstance(material, unreal.Material) or _path(material) != package:
        raise ValueError('M_NorthMountains not authored at its package')
    return material


def rock(context, unreal, args):
    package = _start(context, unreal, 'rock')
    parent = _load(unreal, context, args['parent'], unreal.Material)
    if _path(parent) != PACKAGES['mountains']:
        raise ValueError('MI_NorthRockCaps parent differs')
    for slot in args['closure']:
        _selected(context, slot)
    instance = original(context, unreal)['rock_material'](parent)
    if _path(instance) != package:
        raise ValueError('MI_NorthRockCaps not authored at its package')
    return instance


def gate(context, unreal, args):
    package = _start(context, unreal, 'gate')
    if _selected(context, args['ground']) != '/Game/Japan/Textures/T_ground':
        raise ValueError('M_NorthGate ground differs')
    material = original(context, unreal)['gate_material']()
    if not isinstance(material, unreal.Material) or _path(material) != package:
        raise ValueError('M_NorthGate not authored at its package')
    return material


ACTIONS = {'mountains': mountains, 'rock': rock, 'gate': gate}


def run(context):
    """@cc [owner:fontanierh,label:correctness] c3-north-bodies
    Each job MUST author exactly its declared North package with
    mountain_material.py's own functions: material() less only its inline
    texture-import prelude, reading finished texture packages and declared
    source Items, never ambient build paths; rock_material and gate_material
    unchanged. It MUST NOT run the original top level, cache or reports.
    """
    import unreal
    params = context.params
    args = params.get('args')
    if not isinstance(args, dict) or args.get('action') not in ACTIONS or set(params) - {'args', 'settings', 'input_roots'}:
        raise ValueError('Unsupported North action')
    return ACTIONS[args['action']](context, unreal, args)
