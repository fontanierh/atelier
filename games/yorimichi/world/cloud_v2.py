"""Execute the original cloud build definition for exactly one fresh owned package."""
import ast
import importlib.util
import math
from pathlib import Path
from types import SimpleNamespace

SCRIPTS = 'games/yorimichi/unreal/Scripts/'
ORIGINAL = SCRIPTS + 'crater_cloud_material.py'
SAVE = 'platform/studio/atelier/native_packages.py'
FOLDER = '/Game/CraterPark/Cloud'
NAMES = ('M_CraterCloud', 'M_CraterCloudVeil')


def _keyed(context, relative):
    root = Path(context.job_dir).resolve()
    path = root / relative
    if path.resolve() != path or not path.is_file():
        raise ValueError('Cloud source is not staged keyed code: ' + relative)
    return path


def _select(context, relative, namespace, *, constants=(), functions=()):
    """Select named original definitions/initializers; never execute imports or entrypoints."""
    path = _keyed(context, relative)
    tree = ast.parse(path.read_bytes(), str(path))
    nodes, found = [], []
    for node in tree.body:
        names = []
        if isinstance(node, ast.Assign):
            names = [n.id for target in node.targets for n in ast.walk(target) if isinstance(n, ast.Name)]
            if not names or not set(names) <= set(constants):
                continue
        elif isinstance(node, ast.FunctionDef) and node.name in functions:
            if node.decorator_list:
                raise ValueError('Decorated cloud source definition')
            names = [node.name]
        else:
            continue
        nodes.append(node); found.extend(names)
    expected = set(constants) | set(functions)
    if set(found) != expected or len(found) != len(expected):
        raise ValueError('Original cloud source definitions differ: ' + relative)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace


def original(context, unreal, editor):
    """Rebuild only consumed original namespaces from their keyed staged source."""
    sea = _select(context, SCRIPTS + 'sea_look.py', {},
                  constants=('HORIZON', 'HAZE_CM', 'FAR', 'FAR_COLOUR'), functions=('num', 'f3'))
    atmosphere = _select(context, SCRIPTS + 'atmosphere.py', {'S': SimpleNamespace(**sea)},
                         constants=('HAZE_CM', 'COLOUR', 'START_CM', 'SHARE'))
    namespace = {'math': math, 'unreal': unreal, 'E': editor, 'M': unreal.MaterialEditingLibrary,
                 'AT': unreal.AssetToolsHelpers.get_asset_tools(), 'atmosphere': SimpleNamespace(**atmosphere)}
    return _select(context, ORIGINAL, namespace,
                   constants=('FOLDER', 'F1', 'F2', 'F3', 'TAPS', 'CAMERA', 'NOISE', 'OPACITY', 'COLOUR', 'HAZE'),
                   functions=('build',))


def run(context):
    """@cc [owner:fontanierh,label:correctness] original-cloud-single-package
    Each author MUST call only the selected original build(name, veil), preserving
    its graph and atmosphere/sea constants. Only its exact fresh output MAY be
    loaded/saved, through the job Content root's checked native save. Original
    imports, main and sibling builds MUST NOT execute; there are no native inputs.
    """
    import unreal
    if (set(context.params) != {'args', 'settings'} or context.params['settings'] != []
            or not isinstance(context.params['args'], dict) or set(context.params['args']) != {'asset'}):
        raise ValueError('Unexpected cloud author parameters')
    name = context.params['args']['asset']
    if name not in NAMES:
        raise ValueError('Unknown cloud material')
    package = FOLDER + '/' + name
    if list(context.outputs) != [package] or context.inputs or context.packages:
        raise ValueError('Cloud author owns exactly one output and has no inputs')
    editor = unreal.EditorAssetLibrary
    if editor.does_asset_exist(package):
        raise ValueError('Cloud destination must be fresh')
    spec = importlib.util.spec_from_file_location('cloud_owned_native_save', _keyed(context, SAVE))
    native = importlib.util.module_from_spec(spec); spec.loader.exec_module(native)
    def exists(path):
        if path != package:
            raise ValueError('Cloud accessed an undeclared package')
        return editor.does_asset_exist(path)
    def load(path):
        exists(path)
        return editor.load_asset(path)
    def save(asset, _dirty=False):
        if asset.get_path_name().split('.', 1)[0] != package or not isinstance(asset, unreal.Material):
            raise ValueError('Cloud saved an undeclared material')
        native.save(asset, editor, context.content)
        return True
    owned = SimpleNamespace(does_asset_exist=exists, load_asset=load, save_loaded_asset=save)
    source = original(context, unreal, owned)
    if source['FOLDER'] != FOLDER:
        raise ValueError('Original cloud folder differs')
    built = source['build'](name, name == 'M_CraterCloudVeil')
    if built.get_path_name().split('.', 1)[0] != package or editor.load_asset(package) is None:
        raise ValueError('Cloud material did not load after save')
    return built
