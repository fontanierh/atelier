"""Observation-only qualification of the fixed Treehouse tree and prop assemblies.

No assembly, inventory, copy, retention or validator callback is executed. Child
exports are independently qualified before any IdentityBinding is constructed.
"""
from dataclasses import MISSING, dataclass, fields
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import tempfile
import types

from atelier.build_v2.legacy_qualification import CallableObservation


PARENTS = ('Tree_Canopy_Maple', 'Tree_Canopy_Crimson', 'Tree_Canopy_Amber', 'Tree_Canopy_Ginkgo')
PROP_PARENTS = tuple('TH_P_' + slug for slug in (
    'backpack', 'barrel', 'basket', 'bell', 'bookshelf', 'crate_desk', 'futon',
    'globe', 'kamado', 'log_table', 'planter', 'stump_kettle', 'telescope'))
PARENTS_BY_REGION = {'treehouse_trees': PARENTS, 'treehouse_props': PROP_PARENTS}


class UnsupportedTreehouseAssembly(ValueError):
    """The declaration is outside the two reviewed fixed-roster assembly roles."""


@dataclass(frozen=True)
class TreehouseAssembly:
    step: str
    region: str
    products: tuple[tuple[str, tuple[Path, ...]], ...]
    code_inputs: tuple[Path, ...]
    produced_inputs: tuple[Path, ...]
    logical: tuple
    children: tuple
    callback: CallableObservation
    inventory: CallableObservation


@dataclass(frozen=True)
class _ItemReference:
    key: str
    root: Path


def _source(checkout, path):
    from atelier.build_v2.controller_client import MAX_SOURCE_FILE_BYTES, _read_at
    try:
        return _read_at(checkout, Path(path).relative_to(checkout).as_posix(), MAX_SOURCE_FILE_BYTES)
    except (OSError, ValueError) as error:
        raise UnsupportedTreehouseAssembly(f'assembly source is absent, linked or invalid: {path}') from error


def _output(path, *, directory):
    from atelier.build_v2.controller_client import _open_root
    current = path
    while True:
        try:
            info = current.lstat()
        except FileNotFoundError:
            if current == current.parent:
                raise UnsupportedTreehouseAssembly(f'assembly output has no real ancestor: {path}') from None
            current = current.parent
            continue
        expected = stat.S_ISDIR if directory or current != path else stat.S_ISREG
        if not expected(info.st_mode):
            raise UnsupportedTreehouseAssembly(f'assembly output is linked or invalid: {current}')
        if stat.S_ISDIR(info.st_mode):
            try:
                descriptor = _open_root(current)
                os.close(descriptor)
            except OSError as error:
                raise UnsupportedTreehouseAssembly(f'assembly output ancestry is linked: {current}') from error
            break
        current = current.parent


def _captured(checkout, path):
    from atelier.build_v2.legacy_qualification import CapturedCode
    return CapturedCode(str(path), _source(checkout, path))


def _item_method(actual, expected, name, item_class):
    if type(actual) is not type(expected):
        raise UnsupportedTreehouseAssembly(f'assembly Item {name} type differs')
    if type(actual) is not types.FunctionType:
        if actual is not expected:
            raise UnsupportedTreehouseAssembly(f'assembly Item {name} inherited method differs')
        return
    if (type(expected) is not types.FunctionType or actual.__defaults__ != expected.__defaults__
            or actual.__kwdefaults__ != expected.__kwdefaults__):
        raise UnsupportedTreehouseAssembly(f'assembly Item {name} defaults differ')
    fields_ = ('co_argcount', 'co_posonlyargcount', 'co_kwonlyargcount', 'co_nlocals',
               'co_stacksize', 'co_flags', 'co_code', 'co_consts', 'co_names',
               'co_varnames', 'co_freevars', 'co_cellvars', 'co_linetable', 'co_exceptiontable')
    if any(getattr(actual.__code__, field) != getattr(expected.__code__, field) for field in fields_):
        raise UnsupportedTreehouseAssembly(f'assembly Item {name} code differs')
    if (actual.__code__.co_freevars != ('__dataclass_builtins_object__',)
            and (actual.__closure__ is None) != (expected.__closure__ is None)):
        raise UnsupportedTreehouseAssembly(f'assembly Item {name} closure shape differs')
    if actual.__closure__ is not None:
        try:
            actual_cells = [cell.cell_contents for cell in actual.__closure__]
            expected_cells = [cell.cell_contents for cell in expected.__closure__]
        except ValueError as error:
            raise UnsupportedTreehouseAssembly(f'assembly Item {name} has an empty closure') from error
        expected_cells = [
            item_class if name == 'cls' and value is _ItemReference else value
            for name, value in zip(actual.__code__.co_freevars, expected_cells)
        ]
        if any(type(actual_value) is not type(expected_value) or actual_value != expected_value
               for actual_value, expected_value in zip(actual_cells, expected_cells)):
            raise UnsupportedTreehouseAssembly(f'assembly Item {name} closure values differ')


def _builtins(**values):
    from atelier.build_v2.legacy_qualification import IdentityBinding
    return {name: IdentityBinding(value) for name, value in values.items()}


def _verify(function, captured, *, qualname, **bindings):
    from atelier.build_v2.legacy_qualification import UnsupportedOrigin, verify_callable
    if type(function) is not types.FunctionType:
        raise UnsupportedTreehouseAssembly(f'{qualname}: expected original source function')
    try:
        return verify_callable(function, captured, qualname=qualname, namespace=function.__globals__, **bindings)
    except UnsupportedOrigin as error:
        raise UnsupportedTreehouseAssembly(f'{qualname}: source or explicit bindings differ') from error


def qualify_treehouse_assembly(step, *, checkout: Path, output_root: Path) -> TreehouseAssembly:
    """@cc [owner:fontanierh,label:correctness;safety] closed-treehouse-assembly-observation
    Qualification MUST bind only the actual four-tree and thirteen-prop assemblies,
    independently qualifying each original raw export before IdentityBinding and checking
    complete source/helper/closure/constant roles. Bounded nofollow fixed sources and cold/warm preservation are
    mandatory; no callback/helper execution, future child, runtime/cache/frame/Finish
    authority or generated-output adoption is returned. See actual-Graph/poisoning tests.
    """
    from atelier import atomic_files, build, build_products, export_assembly, export_manifest, export_tasks, file_copy, model_files
    from atelier.build_v2.controller_client import _open_root
    from atelier.build_v2.legacy_qualification import IdentityBinding

    checkout, output_root = Path(checkout), Path(output_root)
    variants = {f'world.{region}.assembled': (region, parents)
                for region, parents in PARENTS_BY_REGION.items()}
    if (type(step) is not build.Step or type(step.name) is not str or step.name not in variants
            or not checkout.is_absolute() or not output_root.is_absolute()
            or checkout == Path(checkout.anchor) or output_root == Path(output_root.anchor)):
        raise UnsupportedTreehouseAssembly('not the exact Treehouse assembly and absolute anchors')
    try:
        descriptor = _open_root(checkout)
        os.close(descriptor)
    except OSError as error:
        raise UnsupportedTreehouseAssembly('assembly checkout is not a real anchored directory') from error
    game = checkout / 'games/yorimichi'
    studio = checkout / 'platform/studio/atelier'
    region_source = game / 'region_exports.py'
    region, parents = variants[step.name]
    destination = output_root / 'atomic_regions' / region
    logical = tuple((parent, output_root / 'planned_exports' / region / parent,
                     f'world.{region}.geometry.{parent}', f'{region}.geometry.{parent}', 'mesh_ir')
                    for parent in parents)
    children = tuple((parent, parent, f'world.{region}.export.{parent}',
                      f'world.{region}.export.{parent}', output_root / 'exports' / f'world.{region}.export' / parent)
                     for parent in parents)
    produced = (*(row[4] for row in children), *(row[1] for row in logical))
    if (len(set(produced)) != 2 * len(parents)
            or any(root == destination or root in destination.parents or destination in root.parents
                   for root in produced)):
        raise UnsupportedTreehouseAssembly('assembly produced/destination roles overlap')
    for root in produced:
        _output(root, directory=True)
    _output(destination, directory=True)

    defaults = {
        'deferred_inputs': [], 'after': [], 'outputs': [], 'heavy': False, 'pool_roots': [],
        'explicit': False, 'verify': None, 'cutoff': False, 'references': [], 'cache': False,
        'audit': False, 'optional_inputs': [], 'queries': [], 'toolchain': False, 'batch': None,
        'cook_recovery': None, 'checkpoint_previous_needs': None, 'checkpoint_restore': None,
        'checkpoint_outputs': (), 'candidate_scope': None, 'replan': False, 'controller': None,
    }
    dynamic = {'name', 'commands', 'inputs', 'needs', 'about', 'products', 'reads'}
    expected_reads = [row[3] for row in children] + [row[3] for row in logical]
    if (set(vars(step)) - dynamic != set(defaults)
            or any(type(vars(step)[name]) is not type(value) or vars(step)[name] != value
                   for name, value in defaults.items())
            or getattr(step, '_query_bindings', None) not in (None, ())
            or step.needs != [f'world.{region}.geometry'] or step.reads != expected_reads):
        raise UnsupportedTreehouseAssembly('assembly controls, needs or ordered reads differ')
    if type(step.commands) is not list or len(step.commands) != 1 or type(step.commands[0]) is not build.Call:
        raise UnsupportedTreehouseAssembly('assembly requires one original Call')
    call = step.commands[0]
    if call.name != f'assemble {region}' or type(call.name) is not str or set(vars(call)) != {'name', 'fn'}:
        raise UnsupportedTreehouseAssembly('assembly Call identity differs')
    expected_inputs = [region_source, *(studio / name for name in
        ('export_assembly.py', 'atomic_files.py', 'file_copy.py', 'export_manifest.py', 'model_files.py'))]
    if (type(step.inputs) is not list or len(step.inputs) != len(expected_inputs) or any(
            type(actual) is not type(expected) or actual != expected
            for actual, expected in zip(step.inputs, expected_inputs))):
        raise UnsupportedTreehouseAssembly('assembly original source input order differs')
    if type(step.products) is not list or len(step.products) != 1:
        raise UnsupportedTreehouseAssembly('assembly requires one original Product')
    product = step.products[0]
    if (type(product) is not build_products.Product
            or set(vars(product)) != {'name', 'paths', 'collection', 'bounds', 'optional_paths'}
            or product.name != f'{region}.atomic' or product.paths != (destination,)
            or product.collection is not None or product.bounds is not None or product.optional_paths):
        raise UnsupportedTreehouseAssembly('assembly product or destination ownership differs')
    code_inputs = tuple(expected_inputs)
    for source in (*code_inputs, game / 'legacy_treehouse_export_profile.py', studio / 'export_tasks.py'):
        _source(checkout, source)
    region_code = _captured(checkout, region_source)
    assembly_code = _captured(checkout, studio / 'export_assembly.py')
    manifest_code = _captured(checkout, studio / 'export_manifest.py')
    model_code = _captured(checkout, studio / 'model_files.py')
    copy_code = _captured(checkout, studio / 'file_copy.py')
    atomic_code = _captured(checkout, studio / 'atomic_files.py')

    if type(call.fn) is not types.FunctionType:
        raise UnsupportedTreehouseAssembly('assembly callback is not a source function')
    cells = {name: cell.cell_contents for name, cell in
             zip(call.fn.__code__.co_freevars, call.fn.__closure__ or ())}
    if (set(cells) != {'logical', 'children', 'destination', 'region'}
            or cells['destination'] != destination or cells['region'] != region):
        raise UnsupportedTreehouseAssembly('assembly closure names or destination differ')
    if (cells['logical'] != list(logical) or type(cells['children']) is not list
            or len(cells['children']) != len(parents)):
        raise UnsupportedTreehouseAssembly('assembly logical/children closure differs')
    from legacy_treehouse_export_profile import UnsupportedTreehouseExport, qualify_treehouse_export
    for (child, child_key), row in zip(cells['children'], children):
        parent, key, child_name, product_name, root = row
        if (child_key != key or type(child) is not build.Step or child.name != child_name
                or len(child.products) != 1 or child.products[0].name != product_name):
            raise UnsupportedTreehouseAssembly('assembly child identity or order differs')
        try:
            qualified = qualify_treehouse_export(child, checkout=checkout, output_root=output_root)
        except UnsupportedTreehouseExport as error:
            raise UnsupportedTreehouseAssembly(f'assembly child is not independently qualified: {child_name}') from error
        if qualified.primary_root != root or qualified.parent != parent or qualified.products != ((product_name, (root,)),):
            raise UnsupportedTreehouseAssembly('assembly child observation does not match closure identity')

    # Base-source helper bindings are intentionally exact; Inventory owns any later
    # managed-temp atomic_json rebind rather than this profile accepting another shape.
    if (type(export_assembly.Item) is not type or export_assembly.Item is _ItemReference
            or export_assembly.Item.__module__ != export_assembly.__name__
            or export_assembly.Item.__qualname__ != 'Item'
            or export_assembly.Item.__bases__ != (object,)
            or export_assembly.Item.__dict__.keys() != _ItemReference.__dict__.keys()
            or export_assembly.Item.__dataclass_fields__.keys() != {'key', 'root'}
            or export_assembly.Item.__dataclass_params__.frozen is not True
            or any(field.default is not MISSING or field.default_factory is not MISSING
                   for field in fields(export_assembly.Item))):
        raise UnsupportedTreehouseAssembly('assembly Item declaration differs')
    for name in ('__init__', '__new__', '__getattribute__', '__setattr__', '__delattr__'):
        _item_method(getattr(export_assembly.Item, name), getattr(_ItemReference, name), name,
                     export_assembly.Item)
    manifest = export_manifest.__dict__
    if (type(manifest.get('PRIMARY')) is not set or manifest['PRIMARY'] != {'.fbx', '.glb'}
            or type(manifest.get('TRIANGLE_LIMIT')) is not int or manifest['TRIANGLE_LIMIT'] != 32768
            or type(manifest.get('NAME')) is not re.Pattern
            or manifest['NAME'].pattern != '[A-Za-z][A-Za-z0-9_-]*' or manifest['NAME'].flags != re.ASCII):
        raise UnsupportedTreehouseAssembly('assembly fixed manifest constants differ')
    _verify(export_manifest.name, manifest_code, qualname='name',
        globals_={'NAME': IdentityBinding(manifest['NAME'])},
        builtins_=_builtins(isinstance=isinstance, str=str, ValueError=ValueError))
    _verify(export_manifest.real_directory, manifest_code, qualname='real_directory',
        keyword_defaults={'create': False}, globals_={'Path': IdentityBinding(Path), 'stat': IdentityBinding(stat)},
        builtins_=_builtins(reversed=reversed, FileNotFoundError=FileNotFoundError, ValueError=ValueError))
    _verify(model_files.member, model_code, qualname='member',
        globals_={'PurePosixPath': IdentityBinding(PurePosixPath)},
        builtins_=_builtins(isinstance=isinstance, str=str, any=any, ValueError=ValueError))
    _verify(export_manifest.sha, manifest_code, qualname='sha',
        globals_={'hashlib': IdentityBinding(hashlib), 'Path': IdentityBinding(Path)}, builtins_=_builtins(iter=iter))
    _verify(model_files.regular_files, model_code, qualname='regular_files',
        globals_={'Path': IdentityBinding(Path), 'stat': IdentityBinding(stat)},
        builtins_=_builtins(ValueError=ValueError, set=set, sorted=sorted))
    _verify(model_files.retain_files, model_code, qualname='retain_files',
        globals_={'Path': IdentityBinding(Path), 'member': IdentityBinding(model_files.member),
                  'regular_files': IdentityBinding(model_files.regular_files)},
        builtins_=_builtins(ValueError=ValueError, any=any, sorted=sorted))
    _verify(export_manifest.validate, manifest_code, qualname='validate', keyword_defaults={'limit': 32768},
        globals_={'real_directory': IdentityBinding(export_manifest.real_directory),
                  'name': IdentityBinding(export_manifest.name),
                  'regular_files': IdentityBinding(model_files.regular_files), 'json': IdentityBinding(json),
                  'member': IdentityBinding(model_files.member), 'Path': IdentityBinding(Path),
                  'PRIMARY': IdentityBinding(manifest['PRIMARY']), 'math': IdentityBinding(math),
                  'sha': IdentityBinding(export_manifest.sha)},
        builtins_=_builtins(ValueError=ValueError, type=type, int=int, isinstance=isinstance,
                            list=list, len=len, any=any, float=float, zip=zip))
    clone = file_copy.clone_function
    import _functools
    if type(clone) is not _functools._lru_cache_wrapper:
        raise UnsupportedTreehouseAssembly('assembly clone_function is not the real cache wrapper')
    try:
        cache_info = _functools._lru_cache_wrapper.__dict__['cache_info'](clone)
    except (AttributeError, TypeError) as error:
        raise UnsupportedTreehouseAssembly('assembly cache wrapper state is uninspectable') from error
    import gc
    referents = gc.get_referents(clone)
    dictionaries = [value for value in referents if value is clone.__dict__]
    internal = [value for value in referents if type(value) is types.FunctionType]
    from functools import lru_cache
    reference_parameters = lru_cache(maxsize=None, typed=False)(
        lambda: None).__dict__['cache_parameters']
    parameters = clone.__dict__.get('cache_parameters')
    if (type(parameters) is not types.FunctionType
            or parameters.__code__ != reference_parameters.__code__
            or parameters.__defaults__ != reference_parameters.__defaults__
            or parameters.__kwdefaults__ != reference_parameters.__kwdefaults__
            or [cell.cell_contents for cell in parameters.__closure__ or ()] != [None, False]
            or cache_info.maxsize is not None or len(dictionaries) != 1
            or len(internal) != 1 or internal[0] is not clone.__dict__.get('__wrapped__')):
        raise UnsupportedTreehouseAssembly('assembly cache wrapper state is ambiguous or spoofed')
    _verify(clone.__wrapped__, copy_code, qualname='clone_function',
        globals_={'ctypes': IdentityBinding(ctypes)})
    _verify(file_copy.copy_file, copy_code, qualname='copy_file',
        globals_={'clone_function': IdentityBinding(file_copy.clone_function), 'os': IdentityBinding(os),
                  'shutil': IdentityBinding(shutil), 'sys': IdentityBinding(sys),
                  '_MANAGED_TEMPORARY': IdentityBinding(atomic_files._MANAGED_TEMPORARY)})
    _verify(export_assembly.destination_members, assembly_code, qualname='destination_members',
        globals_={'json': IdentityBinding(json), 'name': IdentityBinding(export_manifest.name),
                  'regular_files': IdentityBinding(model_files.regular_files)},
        builtins_=_builtins(KeyError=KeyError, TypeError=TypeError, ValueError=ValueError,
                            any=any, dict=dict, isinstance=isinstance, list=list, set=set, str=str))
    _verify(export_assembly.copy_verified, assembly_code, qualname='copy_verified',
        globals_={'copy_file': IdentityBinding(file_copy.copy_file),
                  'real_directory': IdentityBinding(export_manifest.real_directory),
                  'sha': IdentityBinding(export_manifest.sha)}, builtins_=_builtins(ValueError=ValueError))
    _verify(export_assembly.assemble, assembly_code, qualname='assemble',
        globals_={'Path': IdentityBinding(Path), 'atomic_json': IdentityBinding(atomic_files.atomic_json),
                  'copy_file': IdentityBinding(file_copy.copy_file),
                  'managed_temporary_parent': IdentityBinding(atomic_files.managed_temporary_parent),
                  'destination_members': IdentityBinding(export_assembly.destination_members),
                  'name': IdentityBinding(export_manifest.name),
                  'real_directory': IdentityBinding(export_manifest.real_directory),
                  'retain_files': IdentityBinding(model_files.retain_files),
                  'sha': IdentityBinding(export_manifest.sha), 'tempfile': IdentityBinding(tempfile),
                  'validate': IdentityBinding(export_manifest.validate)},
        builtins_=_builtins(ValueError=ValueError, dict=dict, len=len, tuple=tuple))
    _verify(atomic_files.managed_temporary_parent, atomic_code, qualname='managed_temporary_parent',
        globals_={'_MANAGED_TEMPORARY': IdentityBinding(atomic_files._MANAGED_TEMPORARY),
                  'os': IdentityBinding(os), 'stat': IdentityBinding(stat)},
        builtins_=_builtins(ValueError=ValueError))
    _verify(atomic_files.atomic_json, atomic_code, qualname='atomic_json',
        globals_={'tempfile': IdentityBinding(tempfile), 'Path': IdentityBinding(Path),
                  'json': IdentityBinding(json), 'os': IdentityBinding(os),
                  'stat': IdentityBinding(stat),
                  '_MANAGED_TEMPORARY': IdentityBinding(atomic_files._MANAGED_TEMPORARY)},
        builtins_=_builtins(ValueError=ValueError))
    inventory = call.fn.__globals__.get('inventory')
    inventory_observation = _verify(inventory, region_code, qualname='inventory',
        keyword_defaults={'encoding': 'mesh_ir'}, closures={},
        globals_={'Path': IdentityBinding(Path), 'os': IdentityBinding(os), 'json': IdentityBinding(json),
                  'export_tasks': IdentityBinding(export_tasks), 'member': IdentityBinding(model_files.member)},
        builtins_=_builtins(ValueError=ValueError, set=set, type=type, int=int, tuple=tuple))
    expected_cells = dict(cells)
    expected_cells['children'] = [(IdentityBinding(child), child_key) for child, child_key in cells['children']]
    callback = _verify(call.fn, region_code, qualname='steps.<locals>.assemble',
        defaults=None, keyword_defaults=None, closures=expected_cells,
        globals_={'inventory': IdentityBinding(inventory), 'json': IdentityBinding(json),
                  'export_assembly': IdentityBinding(export_assembly),
                  'atomic_json': IdentityBinding(atomic_files.atomic_json)},
        builtins_=_builtins(ValueError=ValueError, dict=dict, len=len))
    return TreehouseAssembly(step.name, region, ((product.name, product.paths),), code_inputs,
                             produced, logical, children, callback, inventory_observation)
