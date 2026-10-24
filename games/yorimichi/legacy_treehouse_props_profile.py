"""Observation-only qualification of the thirteen existing Treehouse prop planners.

The observations describe original source and output roles for managed integration.
They do not grant execution, batch, cache, repair or output-certification authority.
"""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import stat
import types

from atelier.build_v2.legacy_qualification import CallableObservation


PARENTS = tuple('TH_P_' + slug for slug in (
    'backpack', 'barrel', 'basket', 'bell', 'bookshelf', 'crate_desk', 'futon',
    'globe', 'kamado', 'log_table', 'planter', 'stump_kettle', 'telescope'))


class UnsupportedTreehouseProp(ValueError):
    """The declaration is outside the closed, reviewed Treehouse planner family."""


@dataclass(frozen=True)
class TreehousePropPlanner:
    step: str
    parent: str
    script: Path
    arguments: tuple[str, ...]
    raw_inputs: tuple[Path, ...]
    produced_inputs: tuple[Path, ...]
    code_inputs: tuple[Path, ...]
    products: tuple[tuple[str, tuple[Path, ...]], ...]
    primary_root: Path
    data_root: Path
    verifier: CallableObservation
    batch: tuple[str, tuple[str, ...], float]


def _exact(actual, expected):
    if type(actual) is not type(expected):
        return False
    if type(expected) in (tuple, list):
        return len(actual) == len(expected) and all(_exact(a, b) for a, b in zip(actual, expected))
    return actual == expected


def _directory(path):
    try:
        info = path.lstat()
    except FileNotFoundError as error:
        raise UnsupportedTreehouseProp(f'Treehouse source directory is absent: {path}') from error
    if not stat.S_ISDIR(info.st_mode):
        raise UnsupportedTreehouseProp(f'Treehouse source directory is linked or invalid: {path}')


def _closed_anchors(checkout, output_root, game, world, regions, studio):
    from atelier.build_v2.controller_client import _open_root
    try:
        descriptor = _open_root(checkout)
        os.close(descriptor)
    except OSError as error:
        raise UnsupportedTreehouseProp('Treehouse checkout is not an anchored real directory') from error
    for path in (game, world, regions, regions / 'treehouse', game / 'assets',
                 game / 'assets/treehouse', game / 'assets/treehouse/export-parameters',
                 checkout / 'games', checkout / 'platform', studio, studio / 'atelier',
                 studio / 'atelier/blender'):
        _directory(path)
    for path in (output_root / 'planned_exports/treehouse_props',
                 output_root / 'treehouse-data/props'):
        _output_ancestor(path)


def _output_ancestor(path):
    from atelier.build_v2.controller_client import _open_root
    current = path
    while True:
        try:
            info = current.lstat()
        except FileNotFoundError:
            if current == current.parent:
                raise UnsupportedTreehouseProp('output has no real ancestor') from None
            current = current.parent
            continue
        if not stat.S_ISDIR(info.st_mode):
            raise UnsupportedTreehouseProp(f'output ancestor is linked or invalid: {current}')
        try:
            descriptor = _open_root(current)
            os.close(descriptor)
        except OSError as error:
            raise UnsupportedTreehouseProp('output ancestry is linked or invalid') from error
        return


def _source_bytes(checkout, path):
    from atelier.build_v2.controller_client import MAX_SOURCE_FILE_BYTES, _read_at
    try:
        relative = Path(path).relative_to(checkout).as_posix()
    except ValueError:
        raise UnsupportedTreehouseProp(f'Treehouse source escapes checkout: {path}') from None
    try:
        return _read_at(checkout, relative, MAX_SOURCE_FILE_BYTES)
    except (OSError, ValueError) as error:
        raise UnsupportedTreehouseProp(f'Treehouse source is absent, linked or invalid: {path}') from error


def _raw_model(checkout, path):
    """Check the committed model's regular nofollow role without reading its payload."""
    from atelier.build_v2.controller_client import _open_root
    try:
        path.relative_to(checkout)
        descriptor = _open_root(path.parent)
        try:
            info = os.stat(path.name, dir_fd=descriptor, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode):
                raise ValueError('raw model is not regular')
        finally:
            os.close(descriptor)
    except (OSError, ValueError) as error:
        raise UnsupportedTreehouseProp('raw model is absent, linked or invalid') from error


def _code_closure(checkout, script, roots):
    # The existing resolver may stat candidate paths; validate each returned source
    # before its next scanner read/resolve. No imported module body is executed.
    from atelier.build_inputs import ImportScanner
    class CheckedScanner(ImportScanner):
        def _resolve_with_missed(self, root, parts):
            found, missed = super()._resolve_with_missed(root, parts)
            for source in found:
                _source_bytes(checkout, source)
            return found, missed

        def resolve(self, root, parts):
            found = super().resolve(root, parts)
            for source in found:
                _source_bytes(checkout, source)
            return found
    _source_bytes(checkout, script)
    return CheckedScanner().local_imports(script, roots)


def qualify_treehouse_prop(step, *, checkout: Path, output_root: Path) -> TreehousePropPlanner:
    """@cc [owner:fontanierh,label:correctness;safety] closed-treehouse-prop-qualification
    Qualification MUST bind only the thirteen actual full-recipe prop planners, exact original
    command/input/product/batch roles and captured verifier source/globals/defaults/builtins.
    It MUST refuse aliases, unknown controls and linked sources/outputs before source inspection,
    permit absent cold output tails without writes, and return observations rather than executing
    the verifier or granting task, cache, batch, repair or completion authority.
    See test_legacy_treehouse_props_profile.py actual-Graph positive and mutation regressions.
    """
    from atelier import build, build_products
    from atelier.build_v2.legacy_qualification import (
        CapturedCode, IdentityBinding, UnsupportedOrigin, verify_callable,
    )

    checkout, output_root = Path(checkout), Path(output_root)
    if type(step) is not build.Step or not checkout.is_absolute() or not output_root.is_absolute():
        raise UnsupportedTreehouseProp('Treehouse requires a real Step and absolute source/output anchors')
    if (checkout == Path(checkout.anchor) or output_root == Path(output_root.anchor)
            or '..' in checkout.parts or '..' in output_root.parts):
        raise UnsupportedTreehouseProp('Treehouse source/output anchors must not be filesystem roots')
    prefix = 'world.treehouse_props.geometry.'
    if type(step.name) is not str or step.name not in {prefix + parent for parent in PARENTS}:
        raise UnsupportedTreehouseProp(f'not a qualified Treehouse mesh planner: {step.name}')
    parent = step.name.removeprefix(prefix)
    game = checkout / 'games/yorimichi'
    world = game / 'world'
    regions = world / 'regions'
    studio = checkout / 'platform/studio'
    script = regions / 'treehouse/plan_prop.py'
    slug = parent.removeprefix('TH_P_')
    model = game / 'assets/treehouse/props' / slug / f'{slug}.glb'
    parameter = game / 'assets/treehouse/export-parameters' / f'{parent}.json'
    data_root = output_root / 'treehouse-data/props' / parent
    primary_root = output_root / 'planned_exports/treehouse_props' / parent
    arguments = ('--parameters', str(parameter), '--source', str(model),
                 '--data', str(data_root), '--output', str(primary_root))
    _closed_anchors(checkout, output_root, game, world, regions, studio)

    defaults = {
        'deferred_inputs': [], 'after': [], 'outputs': [], 'heavy': True,
        'pool_roots': [], 'explicit': False, 'cutoff': False, 'reads': [], 'references': [],
        'cache': True, 'audit': False, 'optional_inputs': [], 'queries': [],
        'toolchain': True, 'cook_recovery': None, 'checkpoint_previous_needs': None,
        'checkpoint_restore': None, 'checkpoint_outputs': (), 'candidate_scope': None,
        'replan': False, 'controller': None,
    }
    dynamic = {'name', 'commands', 'inputs', 'needs', 'about', 'verify', 'products', 'batch'}
    values = vars(step)
    if (set(values) != set(defaults) | dynamic
            or any(not _exact(values[name], default) for name, default in defaults.items())
            or not _exact(step.needs, [])
            or not _exact(step.about, 'construct only logical mesh ' + parent)):
        raise UnsupportedTreehouseProp(f'{step.name}: unsupported or customized Step controls')
    if type(step.commands) is not list or len(step.commands) != 1:
        raise UnsupportedTreehouseProp(f'{step.name}: expected exactly one original Blender command')
    command = step.commands[0]
    if (type(command) is not build.Blender or set(vars(command)) != {
            'script', 'args', 'threads', 'factory_startup', 'env'}
            or type(command.script) is not type(script) or command.script != script
            or type(command.args) is not tuple
            or not all(type(value) is str for value in command.args) or command.args != arguments
            or command.threads != 3 or type(command.threads) is not int
            or command.factory_startup is not True
            or not _exact(command.env, (('PYTHONHASHSEED', '0'),))):
        raise UnsupportedTreehouseProp(f'{step.name}: original script, arguments or Blender controls differ')
    if (type(step.batch) is not build.Batch
            or set(vars(step.batch)) != {'group', 'runtime_env', 'max_seconds'}
            or not _exact(step.batch.group, 'treehouse_props logical geometry')
            or type(step.batch.runtime_env) is not tuple or step.batch.runtime_env != ()
            or type(step.batch.max_seconds) is not float or step.batch.max_seconds != 240.):
        raise UnsupportedTreehouseProp(f'{step.name}: original Batch fields differ')

    expected_products = ((f'treehouse_props.geometry.{parent}', (primary_root,)),
                         (f'treehouse.prop_data.{parent}', (data_root,)))
    if type(step.products) is not list or len(step.products) != 2:
        raise UnsupportedTreehouseProp(f'{step.name}: expected the two original products')
    products = []
    for product, (name, owned) in zip(step.products, expected_products):
        if (type(product) is not build_products.Product
                or set(vars(product)) != {'name', 'paths', 'collection', 'bounds', 'optional_paths'}
                or not _exact(product.name, name) or not _exact(product.paths, owned)
                or product.collection is not None or product.bounds is not None
                or not _exact(product.optional_paths, ())):
            raise UnsupportedTreehouseProp(f'{step.name}: product name or complete owned roots differ')
        products.append((product.name, product.paths))
    for path in (primary_root, data_root):
        _output_ancestor(path)

    # Only the small parameter JSON is read in its raw role. The potentially large
    # committed GLB and all cold/warm generated contents remain unopened.
    _raw_model(checkout, model)
    parameter_bytes = _source_bytes(checkout, parameter)
    try:
        parameters = json.loads(parameter_bytes)
    except (ValueError, UnicodeError) as error:
        raise UnsupportedTreehouseProp('invalid prop parameter JSON') from error
    if (type(parameters) is not dict or parameters.get('name') != parent
            or parameters.get('slug') != slug):
        raise UnsupportedTreehouseProp('prop parameter parent or slug differs')
    captured = CapturedCode(str(game / 'region_exports.py'), _source_bytes(checkout, game / 'region_exports.py'))
    # Pre-read the original planner and the recipe's declared batch workers before
    # inert AST discovery. Newly discovered imports are checked below by the same
    # anchored reader; no new scanner or source execution is introduced.
    _source_bytes(checkout, script)
    support = tuple(studio / 'atelier' / name for name in
                    ('build_batch_source.py', 'build_batch_worker.py'))
    for source in support:
        _source_bytes(checkout, source)
    if type(step.inputs) is not list:
        raise UnsupportedTreehouseProp('input collection type differs')
    for source in step.inputs:
        if type(source) is not type(script):
            raise UnsupportedTreehouseProp('input path type differs')
        if source.suffix == '.py':
            _source_bytes(checkout, source)
    code = (*_code_closure(checkout, script, (world, regions, studio)), *support)
    # Preserve the recipe's enrichment order; only newly discovered code is appended.
    extra = _code_closure(checkout, script, (world, regions))
    enrichment = tuple(source for source in extra if source not in (*code, parameter, model))
    if len(set(code)) != len(code):
        raise UnsupportedTreehouseProp(f'{step.name}: duplicate original code roles')
    for source in code:
        _source_bytes(checkout, source)
    if (type(step.inputs) is not list or any(type(source) is not type(script) for source in step.inputs)
            or step.inputs != [*code, parameter, model, *enrichment]):
        raise UnsupportedTreehouseProp(f'{step.name}: full-recipe code/raw/produced input order differs')
    if type(step.verify) is not types.FunctionType:
        raise UnsupportedTreehouseProp(f'{step.name}: verifier is not the original source function')
    try:
        verifier = verify_callable(
            step.verify, captured, qualname='steps.<locals>.complete', namespace=step.verify.__globals__,
            defaults=(primary_root, False), keyword_defaults=None, closures={},
            globals_={'WORLD': world}, builtins_={'str': IdentityBinding(str)},
        )
    except UnsupportedOrigin as error:
        raise UnsupportedTreehouseProp(f'{step.name}: verifier source or bindings differ') from error
    return TreehousePropPlanner(step.name, parent, script, arguments, (parameter, model), (),
                                (*code, *enrichment), tuple(products), primary_root, data_root, verifier,
                                (step.batch.group, step.batch.runtime_env, step.batch.max_seconds))
