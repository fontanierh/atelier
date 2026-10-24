"""Observation-only qualification of the four existing Treehouse mesh planners.

The observations describe original source and output roles for managed integration.
They do not grant execution, batch, cache, repair or output-certification authority.
"""
from dataclasses import dataclass
import os
from pathlib import Path
import stat
import types

from atelier.build_v2.legacy_qualification import CallableObservation


PARENTS = ('Tree_Canopy_Maple', 'Tree_Canopy_Crimson', 'Tree_Canopy_Amber', 'Tree_Canopy_Ginkgo')


class UnsupportedTreehouse(ValueError):
    """The declaration is outside the closed, reviewed Treehouse planner family."""


@dataclass(frozen=True)
class TreehousePlanner:
    step: str
    parent: str
    script: Path
    arguments: tuple[str, ...]
    raw_inputs: tuple[Path, ...]
    produced_inputs: tuple[Path, ...]
    code_inputs: tuple[Path, ...]
    products: tuple[tuple[str, tuple[Path, ...]], ...]
    primary_root: Path
    record: Path
    verifier: CallableObservation
    batch: tuple[str, tuple[str, ...], float]


def _directory(path):
    try:
        info = path.lstat()
    except FileNotFoundError as error:
        raise UnsupportedTreehouse(f'Treehouse source directory is absent: {path}') from error
    if not stat.S_ISDIR(info.st_mode):
        raise UnsupportedTreehouse(f'Treehouse source directory is linked or invalid: {path}')


def _closed_anchors(checkout, output_root, game, world, regions, studio):
    from atelier.build_v2.controller_client import _open_root
    try:
        descriptor = _open_root(checkout)
        os.close(descriptor)
    except OSError as error:
        raise UnsupportedTreehouse('Treehouse checkout is not an anchored real directory') from error
    for path in (game, world, regions, regions / 'treehouse', game / 'assets',
                 game / 'assets/treehouse', game / 'assets/treehouse/export-parameters',
                 checkout / 'games', checkout / 'platform', studio, studio / 'atelier',
                 studio / 'atelier/blender'):
        _directory(path)
    for path, directory in ((output_root / 'planned_exports/treehouse_trees', True),
                            (output_root / 'treehouse-data/canopy/records', False),
                            (output_root / 'textures', False)):
        current = path
        while True:
            try:
                info = current.lstat()
            except FileNotFoundError:
                if current == current.parent:
                    raise UnsupportedTreehouse(f'Treehouse output has no real ancestor: {path}') from None
                current = current.parent
                continue
            if not stat.S_ISDIR(info.st_mode):
                raise UnsupportedTreehouse(f'Treehouse output ancestor is linked or invalid: {current}')
            try:
                descriptor = _open_root(current)
                os.close(descriptor)
            except OSError as error:
                raise UnsupportedTreehouse(f'Treehouse output ancestor is linked: {current}') from error
            break


def _source_bytes(checkout, path):
    from atelier.build_v2.controller_client import MAX_SOURCE_FILE_BYTES, _read_at
    try:
        relative = Path(path).relative_to(checkout).as_posix()
    except ValueError:
        raise UnsupportedTreehouse(f'Treehouse source escapes checkout: {path}') from None
    try:
        return _read_at(checkout, relative, MAX_SOURCE_FILE_BYTES)
    except (OSError, ValueError) as error:
        raise UnsupportedTreehouse(f'Treehouse source is absent, linked or invalid: {path}') from error


def _check_output(path, *, directory):
    from atelier.build_v2.controller_client import _open_root
    try:
        info = path.lstat()
    except FileNotFoundError:
        return  # Cold outputs and produced inputs need not exist during declaration qualification.
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected(info.st_mode):
        raise UnsupportedTreehouse(f'Treehouse output has a linked or invalid role: {path}')
    try:
        descriptor = _open_root(path if directory else path.parent)
        os.close(descriptor)
    except OSError as error:
        raise UnsupportedTreehouse(f'Treehouse output ancestry is linked: {path}') from error


def qualify_treehouse_planner(step, *, checkout: Path, output_root: Path) -> TreehousePlanner:
    """@cc [owner:fontanierh,label:correctness;safety] closed-treehouse-planner-qualification
    Qualification MUST bind only the four actual full-recipe mesh planners, exact original
    command/input/product/batch roles and captured verifier source/globals/defaults/builtins.
    It MUST refuse aliases, unknown controls and linked sources/outputs before source inspection,
    permit absent cold output tails without writes, and return observations rather than executing
    the verifier or granting task, cache, batch, repair or completion authority.
    See test_legacy_treehouse_profile.py actual-Graph positive and mutation regressions.
    """
    from atelier import build, build_batch_source, build_inputs, build_products, paths
    from atelier.build_v2.legacy_qualification import (
        CapturedCode, IdentityBinding, UnsupportedOrigin, verify_callable,
    )

    checkout, output_root = Path(checkout), Path(output_root)
    if type(step) is not build.Step or not checkout.is_absolute() or not output_root.is_absolute():
        raise UnsupportedTreehouse('Treehouse requires a real Step and absolute source/output anchors')
    if checkout == Path(checkout.anchor) or output_root == Path(output_root.anchor):
        raise UnsupportedTreehouse('Treehouse source/output anchors must not be filesystem roots')
    prefix = 'world.treehouse_trees.geometry.'
    if step.name not in {prefix + parent for parent in PARENTS}:
        raise UnsupportedTreehouse(f'not a qualified Treehouse mesh planner: {step.name}')
    parent = step.name.removeprefix(prefix)
    game = checkout / 'games/yorimichi'
    world = game / 'world'
    regions = world / 'regions'
    studio = checkout / 'platform/studio'
    script = regions / 'treehouse/plan_tree.py'
    parameter = game / 'assets/treehouse/export-parameters' / f'{parent}.json'
    record = output_root / 'treehouse-data/canopy/records' / f'{parent}.json'
    primary_root = output_root / 'planned_exports/treehouse_trees' / parent
    produced = (output_root / 'textures/T_bark.jpg', output_root / 'textures/T_leaf_maple.png')
    arguments = ('--parameters', str(parameter), '--record', str(record), '--output', str(primary_root))
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
    if (set(values) - dynamic != set(defaults)
            or any(values[name] != default for name, default in defaults.items())
            or step.needs != ['world.textures'] or getattr(step, '_query_bindings', None) not in (None, ())):
        raise UnsupportedTreehouse(f'{step.name}: unsupported or customized Step controls')
    if len(step.commands) != 1:
        raise UnsupportedTreehouse(f'{step.name}: expected exactly one original Blender command')
    command = step.commands[0]
    if (type(command) is not build.Blender or set(vars(command)) != {
            'script', 'args', 'threads', 'factory_startup', 'env'}
            or type(command.script) is not type(script) or command.script != script
            or type(command.args) is not tuple
            or not all(type(value) is str for value in command.args) or command.args != arguments
            or command.threads != 3 or type(command.threads) is not int
            or command.factory_startup is not True
            or command.env != (('PYTHONHASHSEED', '0'),)):
        raise UnsupportedTreehouse(f'{step.name}: original script, arguments or Blender controls differ')
    if (type(step.batch) is not build.Batch
            or set(vars(step.batch)) != {'group', 'runtime_env', 'max_seconds'}
            or step.batch.group != 'treehouse_trees logical geometry'
            or type(step.batch.runtime_env) is not tuple or step.batch.runtime_env != ()
            or type(step.batch.max_seconds) is not float or step.batch.max_seconds != 240.):
        raise UnsupportedTreehouse(f'{step.name}: original Batch fields differ')

    expected_products = ((f'treehouse_trees.geometry.{parent}', (primary_root,)),
                         (f'treehouse.canopy_record.{parent}', (record,)))
    if type(step.products) is not list or len(step.products) != 2:
        raise UnsupportedTreehouse(f'{step.name}: expected the two original products')
    products = []
    for product, (name, owned) in zip(step.products, expected_products):
        if (type(product) is not build_products.Product
                or set(vars(product)) != {'name', 'paths', 'collection', 'bounds', 'optional_paths'}
                or product.name != name or type(product.paths) is not tuple or product.paths != owned
                or product.collection is not None or product.bounds is not None or product.optional_paths):
            raise UnsupportedTreehouse(f'{step.name}: product name or complete owned roots differ')
        products.append((product.name, product.paths))
    if primary_root == record or primary_root in record.parents or record in primary_root.parents:
        raise UnsupportedTreehouse(f'{step.name}: planner products overlap')
    _check_output(primary_root, directory=True)
    for path in (record, *produced):
        _check_output(path, directory=False)

    # All source reads use the existing bounded anchored nofollow reader. Generated
    # produced inputs are deliberately not read or required to exist at this stage.
    _source_bytes(checkout, parameter)
    captured = CapturedCode(str(game / 'region_exports.py'), _source_bytes(checkout, game / 'region_exports.py'))
    # Pre-read the original planner and the recipe's declared batch workers before
    # inert AST discovery. Newly discovered imports are checked below by the same
    # anchored reader; no new scanner or source execution is introduced.
    _source_bytes(checkout, script)
    support = tuple(build_batch_source.support().values())
    for source in support:
        _source_bytes(checkout, source)
    code = (*build_inputs.local_imports(script, (world, regions, studio)), *support)
    if len(set(code)) != len(code):
        raise UnsupportedTreehouse(f'{step.name}: duplicate original code roles')
    for source in code:
        _source_bytes(checkout, source)
    if (type(step.inputs) is not list or any(type(source) is not type(script) for source in step.inputs)
            or step.inputs != [*code, parameter, *produced]):
        raise UnsupportedTreehouse(f'{step.name}: full-recipe code/raw/produced input order differs')
    if type(step.verify) is not types.FunctionType:
        raise UnsupportedTreehouse(f'{step.name}: verifier is not the original source function')
    try:
        verifier = verify_callable(
            step.verify, captured, qualname='steps.<locals>.complete', namespace=step.verify.__globals__,
            defaults=(primary_root, False), keyword_defaults=None, closures={},
            globals_={'WORLD': world}, builtins_={'str': IdentityBinding(str)},
        )
    except UnsupportedOrigin as error:
        raise UnsupportedTreehouse(f'{step.name}: verifier source or bindings differ') from error
    return TreehousePlanner(step.name, parent, script, arguments, (parameter,), produced,
                            tuple(code), tuple(products), primary_root, record, verifier,
                            (step.batch.group, step.batch.runtime_env, step.batch.max_seconds))
