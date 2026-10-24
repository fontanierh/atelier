"""Observation-only qualification of the original Treehouse canopy recolour step.

The returned declaration never executes Blender, image code or a verifier and
does not grant cache, native-runtime, output-certification or completion authority.
"""
import ast
from dataclasses import dataclass
import os
from pathlib import Path
import stat


COLOURS = ('crimson', 'amber')


class UnsupportedTreehouseRecolour(ValueError):
    """The declaration is outside the reviewed original canopy recolour role."""


@dataclass(frozen=True)
class TreehouseRecolour:
    step: str
    script: Path
    arguments: tuple[str, ...]
    raw_inputs: tuple[Path, ...]
    produced_inputs: tuple[Path, ...]
    code_inputs: tuple[Path, ...]
    products: tuple[tuple[str, tuple[Path, ...]], ...]


def _source(checkout, path):
    from atelier.build_v2.controller_client import MAX_SOURCE_FILE_BYTES, _read_at
    try:
        return _read_at(checkout, Path(path).relative_to(checkout).as_posix(), MAX_SOURCE_FILE_BYTES)
    except (OSError, ValueError) as error:
        raise UnsupportedTreehouseRecolour(
            f'recolour source is absent, linked or invalid: {path}') from error


def _directory(path):
    try:
        info = path.lstat()
    except FileNotFoundError as error:
        raise UnsupportedTreehouseRecolour(f'recolour source directory is absent: {path}') from error
    if not stat.S_ISDIR(info.st_mode):
        raise UnsupportedTreehouseRecolour(f'recolour source directory is linked: {path}')


def _output(path, *, directory=False):
    from atelier.build_v2.controller_client import _open_root
    current = path
    while True:
        try:
            info = current.lstat()
        except FileNotFoundError:
            if current == current.parent:
                raise UnsupportedTreehouseRecolour(f'recolour output has no real ancestor: {path}') from None
            current = current.parent
            continue
        expected = stat.S_ISDIR if directory or current != path else stat.S_ISREG
        if not expected(info.st_mode):
            raise UnsupportedTreehouseRecolour(f'recolour output is linked or invalid: {current}')
        if stat.S_ISDIR(info.st_mode):
            try:
                descriptor = _open_root(current)
                os.close(descriptor)
            except OSError as error:
                raise UnsupportedTreehouseRecolour(f'recolour output ancestry is linked: {current}') from error
            break
        current = current.parent


def _recolour_source(checkout, source, script, trees):
    """Inspect only the two relevant AST roles; never import or execute them."""
    try:
        tree = ast.parse(source, filename=str(script))
        main = next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == 'main')
        branch = next(node for node in main.body if isinstance(node, ast.If)
                      and isinstance(node.test, ast.Attribute)
                      and isinstance(node.test.value, ast.Name) and node.test.value.id == 'args'
                      and node.test.attr == 'recolour')
        if (not any(isinstance(node, ast.Import) and any(alias.name == 'bpy' for alias in node.names)
                    for node in ast.walk(branch))
                or not any(isinstance(node, ast.ImportFrom) and node.module == 'treehouse'
                           and any(alias.name == 'trees' for alias in node.names)
                           for node in ast.walk(branch))
                or not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                           and isinstance(node.func.value, ast.Name) and node.func.value.id == 'trees'
                           and node.func.attr == 'recolour' and not node.args and not node.keywords
                           for node in ast.walk(branch))):
            raise UnsupportedTreehouseRecolour('canopy_data --recolour dispatch differs')
        tree_source = _source(checkout, trees)
        tree_ast = ast.parse(tree_source, filename=str(trees))
        assignment = next(node for node in tree_ast.body if isinstance(node, ast.Assign)
                          and any(isinstance(target, ast.Name) and target.id == 'RECOLOUR'
                                  for target in node.targets))
        if tuple(ast.literal_eval(assignment.value)) != COLOURS:
            raise UnsupportedTreehouseRecolour('fixed canopy recolour keys differ')
        function = next(node for node in tree_ast.body
                        if isinstance(node, ast.FunctionDef) and node.name == 'recolour')
        written = []
        for node in ast.walk(function):
            if (isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'path'
                                                     for target in node.targets)
                    and isinstance(node.value, ast.BinOp) and isinstance(node.value.op, ast.Div)):
                written.append(node.value)
        if len(written) != 1:
            raise UnsupportedTreehouseRecolour('recolour output construction differs')
    except (OSError, SyntaxError, ValueError, TypeError, StopIteration) as error:
        raise UnsupportedTreehouseRecolour('recolour source roles are missing or invalid') from error


def qualify_treehouse_recolour(step, *, checkout: Path, output_root: Path) -> TreehouseRecolour:
    """@cc [owner:fontanierh,label:correctness;safety] closed-treehouse-recolour-observation
    Qualification MUST bind only the actual full-recipe single-Blender canopy recolour,
    exact source/argv/input/product/two-required-PNG roles and original controls. Fixed
    sources MUST use bounded anchored nofollow reads before inert import discovery;
    cold tails MUST remain absent and warm generated bytes unread/unchanged. It MUST NOT
    execute scripts/helpers, add a Batch/verifier, or grant native/cache/Finish authority.
    """
    from atelier import build, build_inputs, build_products
    from atelier.build_v2.controller_client import _open_root

    checkout, output_root = Path(checkout), Path(output_root)
    if (type(step) is not build.Step or step.name != 'world.treehouse_trees.recolour'
            or not checkout.is_absolute() or not output_root.is_absolute()
            or checkout == Path(checkout.anchor) or output_root == Path(output_root.anchor)):
        raise UnsupportedTreehouseRecolour('not the exact Treehouse recolour Step and absolute anchors')
    try:
        descriptor = _open_root(checkout)
        os.close(descriptor)
    except OSError as error:
        raise UnsupportedTreehouseRecolour('recolour checkout is not a real anchored directory') from error
    game = checkout / 'games/yorimichi'
    world = game / 'world'
    regions = world / 'regions'
    studio = checkout / 'platform/studio/atelier'
    for path in (world, regions, regions / 'treehouse', studio):
        _directory(path)
    script = regions / 'treehouse/canopy_data.py'
    trees = regions / 'treehouse/trees.py'
    destination = output_root / 'treehouse-data/canopy/recoloured'
    required = tuple(destination / f'T_leaf_{colour}.png' for colour in COLOURS)
    produced = (output_root / 'textures/T_leaf_maple.png',)
    arguments = ('--recolour', str(destination))
    if (len(set(required)) != 2 or destination in produced or produced[0] == destination
            or any(path in produced[0].parents for path in (destination, *required))):
        raise UnsupportedTreehouseRecolour('recolour input/output roles overlap')
    _output(destination, directory=True)
    for path in (*required, *produced):
        _output(path)

    defaults = {
        'deferred_inputs': [], 'after': [], 'heavy': True, 'pool_roots': [], 'explicit': False,
        'verify': None, 'cutoff': False, 'reads': [], 'references': [], 'cache': True,
        'audit': False, 'optional_inputs': [], 'queries': [], 'toolchain': False, 'batch': None,
        'cook_recovery': None, 'checkpoint_previous_needs': None, 'checkpoint_restore': None,
        'checkpoint_outputs': (), 'candidate_scope': None, 'replan': False, 'controller': None,
    }
    dynamic = {'name', 'commands', 'inputs', 'needs', 'about', 'products', 'outputs'}
    if (set(vars(step)) - dynamic != set(defaults)
            or any(vars(step)[name] != value for name, value in defaults.items())
            or getattr(step, '_query_bindings', None) not in (None, ())
            or step.needs != ['world.textures']):
        raise UnsupportedTreehouseRecolour('recolour controls, needs or flags differ')
    if len(step.commands) != 1:
        raise UnsupportedTreehouseRecolour('recolour requires exactly one original Blender command')
    command = step.commands[0]
    if (type(command) is not build.Blender
            or set(vars(command)) != {'script', 'args', 'threads', 'factory_startup', 'env'}
            or type(command.script) is not type(script) or command.script != script
            or type(command.args) is not tuple or command.args != arguments
            or not all(type(value) is str for value in command.args)
            or type(command.threads) is not int or command.threads != 3
            or command.factory_startup is not True or command.env != ()):
        raise UnsupportedTreehouseRecolour('recolour script, argv or original Blender controls differ')
    if (type(step.outputs) is not list or len(step.outputs) != 2
            or any(type(actual) is not type(expected) or actual != expected
                   for actual, expected in zip(step.outputs, required))):
        raise UnsupportedTreehouseRecolour('recolour requires both exact ordered PNG outputs')
    if len(step.products) != 1:
        raise UnsupportedTreehouseRecolour('recolour requires one original Product')
    product = step.products[0]
    if (type(product) is not build_products.Product
            or set(vars(product)) != {'name', 'paths', 'collection', 'bounds', 'optional_paths'}
            or product.name != 'treehouse.canopy_recolours' or product.paths != (destination,)
            or product.collection is not None or product.bounds is not None or product.optional_paths):
        raise UnsupportedTreehouseRecolour('recolour product or destination ownership differs')

    # Pre-read fixed declared source roles before the existing inert import scanner.
    _recolour_source(checkout, _source(checkout, script), script, trees)
    for source in step.inputs:
        try:
            _source(checkout, source)
        except UnsupportedTreehouseRecolour:
            if Path(source) != produced[0]:
                raise
    local = build_inputs.local_imports(script, (world, regions))
    code = []
    for path in local:
        try:
            mapped = studio / path.relative_to(studio)
        except ValueError:
            try:
                mapped = world / path.relative_to(world)
            except ValueError as error:
                raise UnsupportedTreehouseRecolour(f'recolour source has a foreign root: {path}') from error
        code.append(mapped)
    if trees not in code or len(set(code)) != len(code):
        raise UnsupportedTreehouseRecolour('recolour code closure omits trees or duplicates a role')
    expected = [*code, *produced]
    if (type(step.inputs) is not list or len(step.inputs) != len(expected) or any(
            type(actual) is not type(expected_value) or actual != expected_value
            for actual, expected_value in zip(step.inputs, expected))):
        raise UnsupportedTreehouseRecolour('recolour enriched code/produced input order differs')
    for source in code:
        _source(checkout, source)
    return TreehouseRecolour(step.name, script, arguments, (), produced, tuple(code),
                             ((product.name, product.paths),))
