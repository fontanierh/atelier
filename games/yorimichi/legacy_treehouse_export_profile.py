"""Observation-only qualification of the exact Treehouse tree and prop atomic FBX exports.

No validator, verifier, exporter or helper is executed. Returned source observations
do not grant native, cache, publication, future-child or completion authority.
"""
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import types

from atelier.build_v2.legacy_qualification import CallableObservation


PARENTS = ('Tree_Canopy_Maple', 'Tree_Canopy_Crimson', 'Tree_Canopy_Amber', 'Tree_Canopy_Ginkgo')
PROP_PARENTS = tuple('TH_P_' + slug for slug in (
    'backpack', 'barrel', 'basket', 'bell', 'bookshelf', 'crate_desk', 'futon',
    'globe', 'kamado', 'log_table', 'planter', 'stump_kettle', 'telescope'))
PARENTS_BY_REGION = {'treehouse_trees': PARENTS, 'treehouse_props': PROP_PARENTS}


class UnsupportedTreehouseExport(ValueError):
    """The declaration is outside the reviewed one-piece Treehouse export family."""


@dataclass(frozen=True)
class TreehouseExport:
    step: str
    parent: str
    script: Path
    arguments: tuple[str, ...]
    raw_inputs: tuple[Path, ...]
    produced_inputs: tuple[Path, ...]
    code_inputs: tuple[Path, ...]
    products: tuple[tuple[str, tuple[Path, ...]], ...]
    primary_root: Path
    verifier: CallableObservation
    batch: tuple[str, tuple[str, ...], float]


def _exact(actual, expected):
    if type(actual) is not type(expected):
        return False
    if type(expected) in (tuple, list):
        return len(actual) == len(expected) and all(_exact(a, b) for a, b in zip(actual, expected))
    return actual == expected


def _anchors(checkout, *directories):
    from atelier.build_v2.controller_client import _open_root
    for directory in (checkout, *directories):
        try:
            descriptor = _open_root(directory)
            os.close(descriptor)
        except OSError as error:
            raise UnsupportedTreehouseExport('export source anchor is not a real directory') from error


def _code_closure(checkout, script, studio, output_root):
    """Use the existing inert resolver, checking candidates before its source reads."""
    from atelier import build_inputs, paths
    def anchored(root):
        # The scanner includes its installed Studio search root. Bind that fixed
        # role explicitly to this checkout rather than deriving a root from a result.
        if root == paths.STUDIO:
            return studio.parent
        if root == paths.STUDIO / 'atelier':
            return studio
        return root
    def check(source):
        if source.is_relative_to(output_root) or source.suffix != '.py':
            raise UnsupportedTreehouseExport('export generated output cannot be an import source')
        _source(checkout, source)

    class CheckedScanner(build_inputs.ImportScanner):
        def _resolve_with_missed(self, root, parts):
            found, missed = super()._resolve_with_missed(anchored(root), parts)
            for source in found:
                check(source)
            return found, missed

        def resolve(self, root, parts):
            found = super().resolve(anchored(root), parts)
            for source in found:
                check(source)
            return found
    _source(checkout, script)
    sources = CheckedScanner().local_imports(script, (script.parent, studio.parent))
    # The existing scanner can return a verified metadata cache hit without using
    # resolver hooks. Check those returned roles before any later source capture.
    for source in sources:
        check(source)
    return sources


def _source(checkout, path):
    from atelier.build_v2.controller_client import MAX_SOURCE_FILE_BYTES, _read_at
    try:
        relative = Path(path).relative_to(checkout).as_posix()
        return _read_at(checkout, relative, MAX_SOURCE_FILE_BYTES)
    except (OSError, ValueError) as error:
        raise UnsupportedTreehouseExport(f'export source is absent, linked or invalid: {path}') from error


def _output(path, *, directory):
    from atelier.build_v2.controller_client import _open_root
    current = path
    while True:
        try:
            info = current.lstat()
        except FileNotFoundError:
            if current == current.parent:
                raise UnsupportedTreehouseExport(f'export output has no real ancestor: {path}') from None
            current = current.parent
            continue
        except OSError as error:
            raise UnsupportedTreehouseExport('export output ancestry is invalid') from error
        expected = stat.S_ISDIR if directory or current != path else stat.S_ISREG
        if not expected(info.st_mode):
            raise UnsupportedTreehouseExport(f'export output is linked or has an invalid role: {current}')
        if stat.S_ISDIR(info.st_mode):
            try:
                descriptor = _open_root(current)
                os.close(descriptor)
            except OSError as error:
                raise UnsupportedTreehouseExport(f'export output ancestry is linked: {current}') from error
            break
        current = current.parent


def _captured(checkout, path):
    from atelier.build_v2.legacy_qualification import CapturedCode
    return CapturedCode(str(path), _source(checkout, path))


def _verify(function, captured, *, qualname, **bindings):
    from atelier.build_v2.legacy_qualification import UnsupportedOrigin, verify_callable
    if type(function) is not types.FunctionType:
        raise UnsupportedTreehouseExport(f'{qualname}: expected an original source function')
    try:
        return verify_callable(function, captured, qualname=qualname,
                               namespace=function.__globals__, **bindings)
    except UnsupportedOrigin as error:
        raise UnsupportedTreehouseExport(f'{qualname}: source or explicit bindings differ') from error


def _builtins(**values):
    from atelier.build_v2.legacy_qualification import IdentityBinding
    return {name: IdentityBinding(value) for name, value in values.items()}


def qualify_treehouse_export(step, *, checkout: Path, output_root: Path) -> TreehouseExport:
    """@cc [owner:fontanierh,label:correctness;safety] closed-treehouse-export-observation
    Qualification MUST bind only the actual four tree and thirteen prop one-piece FBX exporters,
    original repeated input roles and independently source-checked verifier/helper/constant closure. Fixed
    sources MUST use bounded anchored nofollow reads; cold outputs MUST remain absent and
    warm bytes untouched. No callback/helper execution, generic future piece, cache/native/
    cleanup/publication/completion authority or output adoption is returned.
    See focused actual-Graph, call-trace and helper-poisoning tests.
    """
    from atelier import build, build_products, export_tasks
    from atelier.build_v2.legacy_qualification import IdentityBinding

    checkout, output_root = Path(checkout), Path(output_root)
    if (type(step) is not build.Step or type(step.name) is not str
            or not checkout.is_absolute() or not output_root.is_absolute()
            or checkout == Path(checkout.anchor) or output_root == Path(output_root.anchor)
            or '..' in checkout.parts or '..' in output_root.parts):
        raise UnsupportedTreehouseExport('not an exact Treehouse export and absolute anchors')
    variants = {f'world.{region}.export.{parent}': (region, parent)
                for region, parents in PARENTS_BY_REGION.items() for parent in parents}
    if step.name not in variants:
        raise UnsupportedTreehouseExport('not an exact Treehouse tree or prop export')
    region, parent = variants[step.name]
    prefix = f'world.{region}.export'
    game = checkout / 'games/yorimichi'
    world = game / 'world'
    studio = checkout / 'platform/studio/atelier'
    _anchors(checkout, game, world, studio, studio / 'blender')
    script = world / 'export_region_piece.py'
    payload = output_root / 'planned_exports' / region / parent / f'{parent}.npz'
    primary_root = output_root / 'exports' / prefix / parent
    arguments = ('--input', str(payload), '--output', str(primary_root), '--format', '.fbx')
    if payload == primary_root or payload in primary_root.parents or primary_root in payload.parents:
        raise UnsupportedTreehouseExport('export produced input and output overlap')
    _output(payload, directory=False)
    _output(primary_root, directory=True)

    defaults = {
        'deferred_inputs': [], 'needs': [], 'outputs': [], 'heavy': True, 'pool_roots': [],
        'explicit': False, 'cutoff': False, 'reads': [], 'references': [], 'cache': True,
        'audit': False, 'optional_inputs': [], 'queries': [], 'toolchain': True,
        'cook_recovery': None, 'checkpoint_previous_needs': None, 'checkpoint_restore': None,
        'checkpoint_outputs': (), 'candidate_scope': None, 'replan': False, 'controller': None,
    }
    dynamic = {'name', 'commands', 'inputs', 'after', 'about', 'verify', 'products', 'batch'}
    if (set(vars(step)) != set(defaults) | dynamic
            or any(not _exact(vars(step)[name], value) for name, value in defaults.items())
            or not _exact(step.after, [f'world.{region}.geometry'])
            or not _exact(step.about, 'independent bounded export ' + parent)):
        raise UnsupportedTreehouseExport('export Step controls, flags or after role differs')
    if type(step.commands) is not list or len(step.commands) != 1:
        raise UnsupportedTreehouseExport('export requires one original Blender command')
    command = step.commands[0]
    if (type(command) is not build.Blender or set(vars(command)) != {
            'script', 'args', 'threads', 'factory_startup', 'env'}
            or type(command.script) is not type(script) or command.script != script
            or type(command.args) is not tuple or command.args != arguments
            or not all(type(value) is str for value in command.args)
            or type(command.threads) is not int or command.threads != 3
            or command.factory_startup is not True or not _exact(command.env, (('PYTHONHASHSEED', '0'),))):
        raise UnsupportedTreehouseExport('export script, arguments or Blender controls differ')
    if (type(step.batch) is not build.Batch
            or set(vars(step.batch)) != {'group', 'runtime_env', 'max_seconds'}
            or not _exact(step.batch.group, prefix + ' atomic exports')
            or type(step.batch.runtime_env) is not tuple or step.batch.runtime_env != ()
            or type(step.batch.max_seconds) is not float or step.batch.max_seconds != 240.):
        raise UnsupportedTreehouseExport('export original Batch fields differ')
    if type(step.products) is not list or len(step.products) != 1:
        raise UnsupportedTreehouseExport('export requires one complete Product')
    product = step.products[0]
    if (type(product) is not build_products.Product
            or set(vars(product)) != {'name', 'paths', 'collection', 'bounds', 'optional_paths'}
            or not _exact(product.name, step.name) or not _exact(product.paths, (primary_root,))
            or product.collection is not None or product.bounds is not None
            or not _exact(product.optional_paths, ())):
        raise UnsupportedTreehouseExport('export product name or owned root differs')

    # Generated payloads never enter the source reader, even if a malformed
    # declaration moves them into a code slot or appends an extra source after them.
    if type(step.inputs) is not list or not step.inputs:
        raise UnsupportedTreehouseExport('export original input collection differs')
    for source in step.inputs[:-1]:
        if type(source) is not type(script) or not source.is_relative_to(checkout):
            raise UnsupportedTreehouseExport('export code source role differs')
        if source.is_relative_to(output_root) or source.suffix != '.py':
            raise UnsupportedTreehouseExport('export generated payload cannot be a code source')
        _source(checkout, source)
    _source(checkout, studio / 'export_tasks.py')
    code = [*_code_closure(checkout, script, studio, output_root),
            studio / 'build_batch_source.py', studio / 'build_batch_worker.py',
            world / 'mesh_pieces.py']
    expected_inputs = [*code, payload]
    if (type(step.inputs) is not list or len(step.inputs) != len(expected_inputs) or any(
            type(actual) is not type(expected) or actual != expected
            for actual, expected in zip(step.inputs, expected_inputs))):
        raise UnsupportedTreehouseExport('export original code/repeat/payload input order differs')
    # export_tasks.py is appended once as the checked verifier provider; original repeats
    # in code_inputs remain in their factory positions and are never normalized.
    code_inputs = (*code, studio / 'export_tasks.py')
    for source in code_inputs:
        _source(checkout, source)
    tasks_code = _captured(checkout, studio / 'export_tasks.py')
    manifest_code = _captured(checkout, studio / 'export_manifest.py')
    model_code = _captured(checkout, studio / 'model_files.py')

    present_function = export_tasks.present
    validate_function = present_function.__globals__.get('validate') if type(present_function) is types.FunctionType else None
    manifest = validate_function.__globals__ if type(validate_function) is types.FunctionType else {}
    if (type(manifest.get('PRIMARY')) is not set or manifest['PRIMARY'] != {'.fbx', '.glb'}
            or type(manifest.get('TRIANGLE_LIMIT')) is not int or manifest['TRIANGLE_LIMIT'] != 32768
            or type(manifest.get('NAME')) is not re.Pattern
            or manifest['NAME'].pattern != '[A-Za-z][A-Za-z0-9_-]*'
            or manifest['NAME'].flags != re.ASCII):
        raise UnsupportedTreehouseExport('export manifest fixed PRIMARY/limit/NAME differs')
    checked = {}
    checked['name'] = _verify(manifest.get('name'), manifest_code, qualname='name',
        globals_={'NAME': IdentityBinding(manifest['NAME'])},
        builtins_=_builtins(isinstance=isinstance, str=str, ValueError=ValueError))
    checked['real_directory'] = _verify(manifest.get('real_directory'), manifest_code,
        qualname='real_directory', keyword_defaults={'create': False},
        globals_={'Path': IdentityBinding(Path), 'stat': IdentityBinding(stat)},
        builtins_=_builtins(reversed=reversed, FileNotFoundError=FileNotFoundError, ValueError=ValueError))
    checked['member'] = _verify(manifest.get('member'), model_code, qualname='member',
        globals_={'PurePosixPath': IdentityBinding(PurePosixPath)},
        builtins_=_builtins(isinstance=isinstance, str=str, any=any, ValueError=ValueError))
    checked['sha'] = _verify(manifest.get('sha'), manifest_code, qualname='sha',
        globals_={'hashlib': IdentityBinding(hashlib), 'Path': IdentityBinding(Path)},
        builtins_=_builtins(iter=iter))
    checked['regular_files'] = _verify(manifest.get('regular_files'), model_code, qualname='regular_files',
        globals_={'Path': IdentityBinding(Path), 'stat': IdentityBinding(stat)},
        builtins_=_builtins(ValueError=ValueError, set=set, sorted=sorted))
    validate = manifest.get('validate')
    _verify(validate, manifest_code, qualname='validate', keyword_defaults={'limit': 32768},
        globals_={'real_directory': IdentityBinding(manifest['real_directory']),
                  'name': IdentityBinding(manifest['name']),
                  'regular_files': IdentityBinding(manifest['regular_files']),
                  'json': IdentityBinding(json), 'member': IdentityBinding(manifest['member']),
                  'Path': IdentityBinding(Path), 'PRIMARY': IdentityBinding(manifest['PRIMARY']),
                  'math': IdentityBinding(math), 'sha': IdentityBinding(manifest['sha'])},
        builtins_=_builtins(ValueError=ValueError, type=type, int=int, isinstance=isinstance,
                            list=list, len=len, any=any, float=float, zip=zip))
    present = step.verify.__globals__.get('present') if type(step.verify) is types.FunctionType else None
    _verify(present, tasks_code, qualname='present', keyword_defaults=None, closures={},
        globals_={'validate': IdentityBinding(validate)},
        builtins_=_builtins(OSError=OSError, ValueError=ValueError, KeyError=KeyError, TypeError=TypeError))
    verifier = _verify(step.verify, tasks_code, qualname='steps.<locals>.<lambda>',
        defaults=(primary_root, parent), keyword_defaults=None, closures={},
        globals_={'present': IdentityBinding(present)})
    return TreehouseExport(step.name, parent, script, arguments, (), (payload,), tuple(code_inputs),
                           ((product.name, product.paths),), primary_root, verifier,
                           (step.batch.group, step.batch.runtime_env, step.batch.max_seconds))
