"""Observation-only qualification of the exact Treehouse discovery callback.

Checked source observations do not execute discovery or grant replan, child,
cache, output or completion authority.
"""
from dataclasses import dataclass
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile

from atelier.build_v2.legacy_qualification import CallableObservation


PARENTS = ('Tree_Canopy_Maple', 'Tree_Canopy_Crimson', 'Tree_Canopy_Amber', 'Tree_Canopy_Ginkgo')


class UnsupportedTreehouseDiscovery(ValueError):
    """The declaration is outside the reviewed four-parent discovery role."""


@dataclass(frozen=True)
class TreehouseDiscovery:
    step: str
    region: str
    products: tuple[tuple[str, tuple[Path, ...]], ...]
    code_inputs: tuple[Path, ...]
    produced_inputs: tuple[Path, ...]
    logical: tuple[tuple[str, Path, str, str, str], ...]
    callback: CallableObservation
    inventory: CallableObservation


def _source(checkout, path):
    from atelier.build_v2.controller_client import MAX_SOURCE_FILE_BYTES, _read_at
    try:
        relative = Path(path).relative_to(checkout).as_posix()
        return _read_at(checkout, relative, MAX_SOURCE_FILE_BYTES)
    except (OSError, ValueError) as error:
        raise UnsupportedTreehouseDiscovery(f'discovery source is absent, linked or invalid: {path}') from error


def _output(path, *, directory=False):
    from atelier.build_v2.controller_client import _open_root
    current = path
    while True:
        try:
            info = current.lstat()
        except FileNotFoundError:
            if current == current.parent:
                raise UnsupportedTreehouseDiscovery(f'discovery output has no real ancestor: {path}') from None
            current = current.parent
            continue
        valid = stat.S_ISDIR(info.st_mode) if directory or current != path else stat.S_ISREG(info.st_mode)
        if not valid:
            raise UnsupportedTreehouseDiscovery(f'discovery output is linked or has an invalid role: {current}')
        if stat.S_ISDIR(info.st_mode):
            try:
                descriptor = _open_root(current)
                os.close(descriptor)
            except OSError as error:
                raise UnsupportedTreehouseDiscovery(f'discovery output ancestry is linked: {current}') from error
            break
        current = current.parent


def _captured(checkout, path):
    from atelier.build_v2.legacy_qualification import CapturedCode
    return CapturedCode(str(path), _source(checkout, path))


def _verify(function, captured, **bindings):
    from atelier.build_v2.legacy_qualification import UnsupportedOrigin, verify_callable
    try:
        return verify_callable(function, captured, namespace=function.__globals__, **bindings)
    except UnsupportedOrigin as error:
        raise UnsupportedTreehouseDiscovery('discovery callable source or explicit bindings differ') from error


def qualify_treehouse_discovery(step, *, checkout: Path, output_root: Path) -> TreehouseDiscovery:
    """@cc [owner:fontanierh,label:correctness;safety] closed-treehouse-discovery-observation
    Qualification MUST bind only the actual four-parent discovery Step, its exact logical
    closure/products/inputs and independently source-checked helper callables/constants.
    Fixed sources MUST use bounded anchored nofollow reads before compilation; cold output
    tails MUST remain absent and warm bytes untouched. Inert import discovery is not claimed
    as pre-execution coverage. No callback/helper execution, replan/child/cache/completion
    authority or output adoption is returned. See focused actual-Graph and poisoning tests.
    """
    from atelier import atomic_files, build, build_products, export_assembly, export_tasks, model_files
    from atelier.build_v2.controller_client import _open_root
    from atelier.build_v2.legacy_qualification import IdentityBinding

    checkout, output_root = Path(checkout), Path(output_root)
    if (type(step) is not build.Step or step.name != 'world.treehouse_trees.geometry'
            or not checkout.is_absolute() or not output_root.is_absolute()
            or checkout == Path(checkout.anchor) or output_root == Path(output_root.anchor)):
        raise UnsupportedTreehouseDiscovery('not the exact Treehouse discovery Step and absolute anchors')
    try:
        descriptor = _open_root(checkout)
        os.close(descriptor)
    except OSError as error:
        raise UnsupportedTreehouseDiscovery('discovery checkout is not a real anchored directory') from error
    game = checkout / 'games/yorimichi'
    studio = checkout / 'platform/studio/atelier'
    region_source = game / 'region_exports.py'
    discovery = output_root / 'planned_exports/treehouse_trees/discovery.json'
    region = 'treehouse_trees'
    logical = tuple((parent, output_root / 'planned_exports/treehouse_trees' / parent,
                     f'world.treehouse_trees.geometry.{parent}', f'treehouse_trees.geometry.{parent}', 'mesh_ir')
                    for parent in PARENTS)
    produced = tuple(row[1] for row in logical)
    if len(set(produced)) != 4 or any(root == discovery or root in discovery.parents or discovery in root.parents
                                     for root in produced):
        raise UnsupportedTreehouseDiscovery('discovery produced roots overlap')
    for root in produced:
        _output(root, directory=True)
    _output(discovery)

    defaults = {
        'deferred_inputs': [], 'needs': [], 'after': [], 'outputs': [], 'heavy': False,
        'pool_roots': [], 'explicit': False, 'verify': None, 'cutoff': False,
        'references': [], 'cache': False, 'audit': False, 'optional_inputs': [], 'queries': [],
        'toolchain': False, 'batch': None, 'cook_recovery': None, 'checkpoint_previous_needs': None,
        'checkpoint_restore': None, 'checkpoint_outputs': (), 'candidate_scope': None,
        'replan': True, 'controller': None,
    }
    dynamic = {'name', 'commands', 'inputs', 'about', 'products', 'reads'}
    if (set(vars(step)) - dynamic != set(defaults)
            or any(vars(step)[name] != value for name, value in defaults.items())
            or getattr(step, '_query_bindings', None) not in (None, ())
            or step.reads != [row[3] for row in logical]):
        raise UnsupportedTreehouseDiscovery('discovery Step controls, flags or reads differ')
    if len(step.commands) != 1 or type(step.commands[0]) is not build.Call:
        raise UnsupportedTreehouseDiscovery('discovery requires exactly one original Call')
    call = step.commands[0]
    if type(call.name) is not str or call.name != 'discover treehouse_trees' or set(vars(call)) != {'name', 'fn'}:
        raise UnsupportedTreehouseDiscovery('discovery Call identity differs')
    runtime = export_assembly.runtime_inputs()
    runtime_root = Path(runtime[0]).parent
    expected_inputs = [region_source, *(studio / path.relative_to(runtime_root) for path in runtime)]
    if type(step.inputs) is not list or len(step.inputs) != len(expected_inputs) or any(
            type(actual) is not type(expected) or actual != expected
            for actual, expected in zip(step.inputs, expected_inputs)):
        raise UnsupportedTreehouseDiscovery('discovery original code-input membership/order differs')
    if len(step.products) != 1:
        raise UnsupportedTreehouseDiscovery('discovery requires one original product')
    product = step.products[0]
    if (type(product) is not build_products.Product
            or set(vars(product)) != {'name', 'paths', 'collection', 'bounds', 'optional_paths'}
            or product.name != 'treehouse_trees.geometry_inventory' or product.paths != (discovery,)
            or product.collection is not None or product.bounds is not None or product.optional_paths):
        raise UnsupportedTreehouseDiscovery('discovery product or owned root differs')

    # Original inputs plus export_tasks.py, the only additional checked provider used by
    # inventory, in first-use order with no duplicate path roles.
    code_inputs = tuple(dict.fromkeys([*expected_inputs, studio / 'export_tasks.py']))
    for source in code_inputs:
        _source(checkout, source)
    region_code = _captured(checkout, region_source)
    manifest_code = _captured(checkout, studio / 'export_manifest.py')
    model_code = _captured(checkout, studio / 'model_files.py')
    atomic_code = _captured(checkout, studio / 'atomic_files.py')

    namespace = call.fn.__globals__
    inventory = namespace.get('inventory')
    atomic_json = namespace.get('atomic_json')
    if inventory is None or atomic_json is None:
        raise UnsupportedTreehouseDiscovery('discovery globals lack original helpers')
    export_module = inventory.__globals__.get('export_tasks')
    export_manifest = export_tasks.name.__globals__
    if (export_module is not export_tasks or export_tasks.name is not export_manifest.get('name')
            or export_tasks.real_directory is not export_manifest.get('real_directory')
            or type(export_tasks.TRIANGLE_LIMIT) is not int or export_tasks.TRIANGLE_LIMIT != 32768):
        raise UnsupportedTreehouseDiscovery('inventory helper provider or fixed triangle limit differs')
    if (type(export_manifest.get('NAME')) is not re.Pattern
            or export_manifest['NAME'].pattern != '[A-Za-z][A-Za-z0-9_-]*'
            or export_manifest['NAME'].flags != re.ASCII):
        raise UnsupportedTreehouseDiscovery('inventory helper NAME regex differs')
    _verify(export_tasks.name, manifest_code, qualname='name',
            globals_={'NAME': IdentityBinding(export_manifest['NAME'])},
            builtins_={name: IdentityBinding(value) for name, value in
                       {'isinstance': isinstance, 'str': str, 'ValueError': ValueError}.items()})
    _verify(export_tasks.real_directory, manifest_code, qualname='real_directory',
            keyword_defaults={'create': False},
            globals_={'Path': IdentityBinding(Path), 'stat': IdentityBinding(stat)},
            builtins_={name: IdentityBinding(value) for name, value in {
                'reversed': reversed, 'FileNotFoundError': FileNotFoundError, 'ValueError': ValueError}.items()})
    member = inventory.__globals__.get('member')
    if member is not model_files.member:
        raise UnsupportedTreehouseDiscovery('inventory member helper differs')
    _verify(member, model_code, qualname='member', globals_={'PurePosixPath': IdentityBinding(PurePosixPath)},
            builtins_={name: IdentityBinding(value) for name, value in {
                'isinstance': isinstance, 'str': str, 'any': any, 'ValueError': ValueError}.items()})
    if atomic_json is not atomic_files.atomic_json:
        raise UnsupportedTreehouseDiscovery('discovery atomic_json helper differs')
    _verify(atomic_json, atomic_code, qualname='atomic_json',
            globals_={'tempfile': IdentityBinding(tempfile), 'Path': IdentityBinding(Path),
                      'json': IdentityBinding(json), 'os': IdentityBinding(os),
                      'stat': IdentityBinding(stat),
                      '_MANAGED_TEMPORARY': IdentityBinding(atomic_files._MANAGED_TEMPORARY)},
            builtins_={'ValueError': IdentityBinding(ValueError)})
    inventory_observation = _verify(
        inventory, region_code, qualname='inventory', keyword_defaults={'encoding': 'mesh_ir'}, closures={},
        globals_={'Path': IdentityBinding(Path), 'os': IdentityBinding(os), 'json': IdentityBinding(json),
                  'export_tasks': IdentityBinding(export_tasks), 'member': IdentityBinding(member)},
        builtins_={name: IdentityBinding(value) for name, value in {
            'ValueError': ValueError, 'set': set, 'type': type, 'int': int, 'tuple': tuple}.items()})
    callback = _verify(
        call.fn, region_code, qualname='steps.<locals>.discover', defaults=None, keyword_defaults=None,
        closures={'logical': list(logical), 'region': region, 'discovery': discovery},
        globals_={'inventory': IdentityBinding(inventory), 'atomic_json': IdentityBinding(atomic_json)},
        builtins_={name: IdentityBinding(value) for name, value in {
            'ValueError': ValueError, 'dict': dict, 'sum': sum, 'map': map, 'len': len}.items()})
    return TreehouseDiscovery(step.name, region, ((product.name, product.paths),), code_inputs,
                              produced, logical, callback, inventory_observation)
