"""Captured code for the original guarded Blender batch, never an executor or issuer.

The scheduler still owns member selection, ACKs, product checks and publication. This
module only binds the used loader bytes to existing task inputs and installs a finite
captured-code scope around the original batch worker.
"""
from dataclasses import dataclass, field
from pathlib import Path

_ORIGIN = object()
_WORKER = (
    'platform/studio/atelier/__init__.py',
    'platform/studio/atelier/build_batch_worker.py',
    'platform/studio/atelier/build_v2/__init__.py',
    'platform/studio/atelier/build_v2/controller_client.py',
    'platform/studio/atelier/build_v2/legacy_action.py',
    'platform/studio/atelier/build_v2/legacy_native_action.py',
    'platform/studio/atelier/build_v2/legacy_qualification.py',
)


@dataclass(frozen=True)
class _NativeRuntime:
    root: Path
    files: tuple[str, ...]
    _origin: object = field(repr=False, compare=False)
    validators: tuple[str, ...] = ()


def captured_native_inputs(step):
    """Only the fixed issuer's private descriptor adds existing canonical inputs."""
    runtime = getattr(step, '_captured_native_runtime', None)
    if runtime is None:
        return ()
    if type(runtime) is not _NativeRuntime or runtime._origin is not _ORIGIN:
        raise ValueError('unqualified captured native runtime descriptor')
    return tuple(runtime.root / name for name in (*runtime.files, *runtime.validators))


def _bind_native_runtime(step, *, checkout, issuer_files, verifier=None):
    """Observe code roles only AFTER raw declaration qualification, never grant work."""
    from atelier.build import required_inputs
    root = Path(checkout)
    names = {path.relative_to(root).as_posix() for path in map(Path, required_inputs(step))
             if path.suffix == '.py'}
    names.update(_WORKER)
    for name in tuple(names):
        parent = (root / name).parent
        while parent != root:
            initializer = parent / '__init__.py'
            if initializer.is_symlink():
                raise ValueError('linked native worker package initializer')
            if initializer.is_file():
                names.add(initializer.relative_to(root).as_posix())
            parent = parent.parent
    if not names <= set(issuer_files):
        raise ValueError('native action code is outside the original captured issuer')
    validators = ()
    if verifier is not None:
        import hashlib
        from .controller_client import _read_at, MAX_SOURCE_FILE_BYTES
        from .legacy_qualification import CallableObservation
        if type(verifier) is not CallableObservation:
            raise ValueError('native validator has no checked source observation')
        name = Path(verifier.filename).relative_to(root).as_posix()
        if name not in issuer_files:
            raise ValueError('native validator source is outside the frozen issuer')
        if hashlib.sha256(_read_at(root, name, MAX_SOURCE_FILE_BYTES)).hexdigest() != verifier.source_digest:
            raise ValueError('native validator source changed before key preparation')
        if name not in names:
            validators = (name,)
    runtime = _NativeRuntime(root, tuple(sorted(names)), _ORIGIN, validators)
    step._captured_native_runtime = runtime
    return runtime


def worker_argv(command, ctx, *, startup, specification, specification_digest, capture_file,
                capture_digest):
    """@cc [owner:fontanierh,label:correctness;safety] captured-original-native-worker-argv
    Preserve native flags and bind exact private bootstrap arguments in the real argv.
    The original factory/threads/environment and worker role MUST remain unchanged.
    Only the exact batch worker MAY be replaced by the source-bound bootstrap; unknown
    scripts or argument shapes MUST refuse. Private names MUST NOT become task keys.
    """
    import json
    from atelier.build import Blender
    if type(command) is not Blender:
        raise ValueError('unsupported original native worker command type')
    argv = command.argv(ctx)
    # command.script uses its original checkout role, even when this helper was
    # imported from the captured distribution. Resolve the expected role via ctx.
    from atelier import paths
    expected = paths.STUDIO / 'atelier/build_batch_worker.py'
    if command.script != expected or command.args or argv.count('--python') != 1:
        raise ValueError('unsupported original native worker role or arguments')
    index = argv.index('--python')
    if argv[index + 1] != str(expected):
        raise ValueError('native argv script differs from the original worker role')
    values = json.dumps([str(capture_file), capture_digest, str(startup), str(specification),
                         specification_digest], separators=(',', ':'))
    bootstrap = '''import hashlib,os,sys,types,json
p,h,startup,spec,expected=json.loads(VALUES)
if any(n=='atelier' or n.startswith('atelier.') or n=='_atelier_pinned_native_capture' for n in sys.modules):raise RuntimeError('native bootstrap refuses preloaded project helpers')
f=os.open(p,os.O_RDONLY|os.O_NOFOLLOW);raw=os.read(f,8*1024*1024+1);os.close(f)
if hashlib.sha256(raw).hexdigest()!=h:raise RuntimeError('captured native loader changed')
m=types.ModuleType('_atelier_pinned_native_capture');m.__file__=p;sys.modules[m.__name__]=m
exec(compile(raw,p,'exec',dont_inherit=True),m.__dict__)
s=m._json(m._read_at(os.path.dirname(startup),os.path.basename(startup),2*1024*1024,owned=True))
if m.capture_controller(s['distribution']).digest!=s['source_digest']:raise RuntimeError('captured native distribution changed')
sys.dont_write_bytecode=True
sys.path[:0]=[s['distribution']+'/platform/studio']
for name,relative,package in [('atelier','platform/studio/atelier/__init__.py',True),('atelier.build_v2','platform/studio/atelier/build_v2/__init__.py',True),('atelier.build_v2.controller_client','platform/studio/atelier/build_v2/controller_client.py',False),('atelier.build_v2.legacy_qualification','platform/studio/atelier/build_v2/legacy_qualification.py',False),('atelier.build_v2.legacy_native_action','platform/studio/atelier/build_v2/legacy_native_action.py',False)]:
 raw=m._read_at(s['distribution'],relative,8*1024*1024);filename=s['distribution']+'/'+relative
 loaded=types.ModuleType(name);loaded.__file__=filename;loaded.__package__=name if package else name.rpartition('.')[0]
 if package:loaded.__path__=[os.path.dirname(filename)]
 sys.modules[name]=loaded
 if '.' in name:setattr(sys.modules[name.rpartition('.')[0]],name.rpartition('.')[2],loaded)
 exec(compile(raw,filename,'exec',dont_inherit=True),loaded.__dict__)
sys.modules['atelier.build_v2.legacy_native_action'].main(s,spec,expected)
'''.replace('VALUES', repr(values))
    return [*argv[:index], '--python-expr', bootstrap, *argv[index + 2:]]


def _registered_tool_provider(name, module, modules, builtin_names, tool, caller_globals):
    """Exact observed Blender registrations; namespace paths never authorize child code."""
    import types
    if type(module) is not types.ModuleType:
        return False
    if name == '__mp_main__':
        owner = modules.get('multiprocessing')
        if owner is None or not tool(getattr(owner, '__file__', '')):
            return False
        if module is modules.get('__main__') and vars(module) is caller_globals:
            return True
        # Blender replaces PyC_DefaultNameSpace for each expression. CPython's
        # startup multiprocessing alias can retain the prior inert default namespace.
        # It contains no executed script/function; reject any additional binding.
        import builtins
        values = vars(module)
        return (set(values) == {'__name__', '__doc__', '__package__', '__loader__',
                                '__spec__', '__file__', '__builtins__', 'bpy'}
                and values['__name__'] == '__main__' and values['__file__'] == '<blender string>'
                and all(values[key] is None for key in ('__doc__', '__package__', '__loader__', '__spec__'))
                and values['__builtins__'] is vars(builtins) and values['bpy'] is modules.get('bpy'))
    native_children = {
        'bpy.utils.units', 'mathutils.geometry', 'mathutils.interpolate', 'mathutils.noise',
        'mathutils.bvhtree', 'mathutils.kdtree', 'idprop.types',
        'bmesh.types', 'bmesh.ops', 'bmesh.utils', 'bmesh.geometry',
    }
    if name == 'bpy.utils.units':
        binding = modules.get('_bpy')
        return (binding is not None and getattr(binding, '_utils_units', None) is module
                and getattr(module, '__file__', None) is None and getattr(module, '__spec__', None) is None)
    if name == '_freestyle':
        # This dynamically registered embedded C module is absent from CPython's
        # BuiltinImporter table. Require its actual named C entrypoints (these embedded functions may have NULL self) and
        # static native BBox type, never merely its spelling or a Python shim.
        functions = ('getCurrentScene', 'blendRamp', 'evaluateColorRamp', 'evaluateCurveMappingF')
        bbox = getattr(module, 'BBox', None)
        return (getattr(module, '__file__', None) is None and getattr(module, '__spec__', None) is None
                and all(type(getattr(module, key, None)) is types.BuiltinFunctionType
                        and getattr(module, key).__name__ == key
                        and getattr(module, key).__self__ in (None, module) for key in functions)
                and type(bbox) is type and bbox.__name__ == 'BBox'
                and not bbox.__flags__ & (1 << 9)
                and not any(type(value) is types.FunctionType for value in vars(bbox).values()))
    if name in native_children:
        parent_name, _, member = name.rpartition('.')
        parent = modules.get(parent_name)
        if parent is None or getattr(parent, member, None) is not module:
            return False
        origin = getattr(parent, '__file__', None)
        return (getattr(module, '__file__', None) is None and getattr(module, '__spec__', None) is None
                and (bool(origin and tool(origin)) or parent_name in builtin_names))
    if name not in {'bl_ext', 'bl_ext.blender_org', 'bl_ext.user_default', 'bl_ext.system'}:
        return False
    addon = modules.get('addon_utils')
    junction = modules.get('_bpy_internal.extensions.junction_module')
    if not (addon and junction and tool(getattr(addon, '__file__', ''))
            and tool(getattr(junction, '__file__', ''))):
        return False
    handle = getattr(getattr(addon, '_ext_global', None), 'module_handle', None)
    handle_type = getattr(junction, 'JunctionModuleHandle', None)
    if handle_type is None or type(handle) is not handle_type:
        return False
    # The pinned factory creates these inert modules with bracketed identifiers;
    # registry identity (not arbitrary __file__/__path__) proves their exact role.
    if getattr(module, '__file__', None) != '[' + name + ']' or getattr(module, '__spec__', None) is not None:
        return False
    if name == 'bl_ext':
        return getattr(handle, '_module', None) is module
    member = name.rsplit('.', 1)[1]
    registered = dict(handle.submodule_items())
    return (registered.get(member) is module
            and getattr(modules.get('bl_ext'), member, None) is module)


def _preloaded(manifest, installation, caller):
    """Check the fixed bootstrap plus native tool context before any project imports."""
    import importlib.machinery
    import os
    import sys
    import types
    from atelier.build_v2.legacy_qualification import _same_code
    roots = tuple(Path(path).resolve() for path in installation)
    def tool(value):
        path = Path(value).resolve()
        return any(path.is_relative_to(root) for root in roots)
    # The actual --python-expr bytes are part of the persisted guard launch argv.
    if sys.argv.count('--python-expr') != 1:
        raise ValueError('native bootstrap has no unique source-bound expression')
    expression = sys.argv[sys.argv.index('--python-expr') + 1]
    if not _same_code(caller.f_code, compile(expression, caller.f_code.co_filename, 'exec', dont_inherit=True)):
        raise ValueError('native bootstrap caller differs from its actual launch expression')
    distribution = Path(manifest['distribution'])
    known = {
        '_atelier_pinned_native_capture': distribution / 'platform/studio/atelier/build_v2/controller_client.py',
        'atelier': distribution / 'platform/studio/atelier/__init__.py',
        'atelier.build_v2': distribution / 'platform/studio/atelier/build_v2/__init__.py',
        'atelier.build_v2.controller_client': distribution / 'platform/studio/atelier/build_v2/controller_client.py',
        'atelier.build_v2.legacy_native_action': distribution / 'platform/studio/atelier/build_v2/legacy_native_action.py',
        'atelier.build_v2.legacy_qualification': distribution / 'platform/studio/atelier/build_v2/legacy_qualification.py',
    }
    # Do not purge/hide ambient modules: every observed module is classified before
    # the captured importer can replace a project module or its globals.
    unclassified, unclassified_count = [], 0
    def safe_label(value):
        if type(value) is str and len(value) <= 160 and all(c.isascii() and (c.isalnum() or c in '._-') for c in value):
            return value
        return '<unclassified>'
    def file_role(value):
        if value is None:
            return 'none'
        if type(value) is not str:
            return 'non-string'
        if value in ('built-in', 'frozen'):
            return value
        try:
            path = Path(value).resolve()
            for root in roots:
                if path.is_relative_to(root):
                    return 'tool/' + path.relative_to(root).as_posix()[:160]
            if path.is_relative_to(distribution):
                return 'captured/' + path.relative_to(distribution).as_posix()[:160]
        except (OSError, ValueError):
            return 'unresolved'
        return 'outside-checked-roots'
    for name, module in tuple(sys.modules.items()):
        try:
            if module is None:
                continue
            if _registered_tool_provider(name, module, sys.modules, sys.builtin_module_names, tool, caller.f_globals):
                continue
            if name == '__main__' and vars(module) is caller.f_globals:
                continue  # Exact live expression compared above, not a forged __file__.
            origin = getattr(module, '__file__', None)
            info = getattr(module, '__spec__', None)
            if name in known:
                if origin != str(known[name]):
                    raise ValueError('native bootstrap helper has a different loaded origin')
                continue  # Fresh immutable distribution was verified before these imports.
            if origin:
                if not tool(origin):
                    raise ValueError('native startup preloaded code outside its checked installation')
                actual = getattr(info, 'origin', None)
                if actual not in (None, 'built-in', 'frozen') and not tool(actual):
                    raise ValueError('native module spec differs from its tool origin')
                cached = getattr(module, '__cached__', None)
                if cached and not tool(cached):
                    raise ValueError('native startup cached code outside its installation')
            elif (getattr(info, 'loader', None) is importlib.machinery.BuiltinImporter
                  and name in sys.builtin_module_names and info.origin == 'built-in'):
                pass
            elif (getattr(info, 'loader', None) is importlib.machinery.FrozenImporter
                  and info.origin == 'frozen' and importlib.machinery.FrozenImporter.find_spec(name) is not None):
                pass
            elif name in {'_bpy', 'bpy', 'bpy.app', 'bpy.app.handlers', 'bpy.app.timers',
                          'bpy.app.translations', 'bpy.app.icons', 'bpy.props', 'bpy.types'}:
                if getattr(info, 'origin', None) not in (None, 'built-in'):
                    raise ValueError('native Blender binding has an unknown origin')
            elif name in {'typing.io', 'typing.re'}:
                parent = sys.modules.get('typing')
                parent_origin = getattr(parent, '__file__', None)
                if not (parent_origin and tool(parent_origin) and type(module).__module__ == 'typing'
                        and getattr(parent, name.rsplit('.', 1)[1], None) is module):
                    raise ValueError('native typing namespace differs')
            else:
                locations = getattr(info, 'submodule_search_locations', None)
                if not locations or not all(tool(path) for path in locations):
                    raise ValueError('native startup origin is not a checked tool module')
            for locations in (getattr(module, '__path__', None), getattr(info, 'submodule_search_locations', None)):
                if locations is not None and not all(tool(path) for path in locations):
                    raise ValueError('native startup package search escapes its installation')
        except (ValueError, TypeError, AttributeError, OSError) as error:
            unclassified_count += 1
            if len(unclassified) < 32:
                try:
                    info = getattr(module, '__spec__', None)
                    loader = getattr(info, 'loader', None)
                    unclassified.append({'name': safe_label(name),
                        'type': safe_label(type(module).__module__ + '.' + type(module).__qualname__),
                        'file_role': file_role(getattr(module, '__file__', None)),
                        'spec_origin': file_role(getattr(info, 'origin', None)),
                        'loader_type': safe_label(type(loader).__module__ + '.' + type(loader).__qualname__),
                        'failure': safe_label(type(error).__name__)})
                    if name in {'_freestyle', '__mp_main__'}:
                        row = unclassified[-1]
                        if name == '_freestyle':
                            row['c_functions'] = [{'name': key,
                                'type': safe_label(type(getattr(module, key, None)).__name__),
                                'actual_name': safe_label(getattr(getattr(module, key, None), '__name__', None)),
                                'self_module': getattr(getattr(module, key, None), '__self__', None) is module,
                                'self_none': getattr(getattr(module, key, None), '__self__', None) is None}
                                for key in ('getCurrentScene', 'blendRamp', 'evaluateColorRamp', 'evaluateCurveMappingF')]
                            bbox = getattr(module, 'BBox', None)
                            row['bbox'] = {'name': safe_label(getattr(bbox, '__name__', None)),
                                           'module': safe_label(getattr(bbox, '__module__', None)),
                                           'flags': getattr(bbox, '__flags__', None)}
                        row['main_alias'] = module is sys.modules.get('__main__')
                        row['caller_globals'] = vars(module) is caller.f_globals
                        filename = getattr(module, '__file__', None)
                        if type(filename) is str and filename in {'<blender string>', '<string>'}:
                            row['synthetic_file'] = filename
                        row['attributes'] = [{'name': safe_label(key),
                            'type': safe_label(type(value).__module__ + '.' + type(value).__qualname__),
                            'code_role': file_role(getattr(getattr(value, '__code__', None), 'co_filename', None))}
                            for key, value in list(vars(module).items())[:32]]
                except Exception:
                    unclassified.append({'name': safe_label(name), 'metadata': 'unavailable'})
    if unclassified_count:
        # Diagnostic only. Classify every entry, retain a bounded safe table, and
        # keep the original fail-before-worker outcome if diagnostics themselves fail.
        try:
            import json
            record = {'count': unclassified_count, 'modules': unclassified,
                      'truncated': unclassified_count > len(unclassified)}
            raw = json.dumps(record, separators=(',', ':'), ensure_ascii=True)
            while len(raw.encode()) > 8192 and record['modules']:
                record['modules'].pop()
                record['truncated'] = True
                raw = json.dumps(record, separators=(',', ':'), ensure_ascii=True)
            sys.stderr.write('native_preload_unclassified ' + raw + '\n')
            sys.stderr.flush()
        except Exception:
            pass
        raise ValueError('native startup contains unclassified preloaded providers')


def main(manifest, specification, expected):
    """Run only the original named batch worker inside its finite captured code scope."""
    import hashlib
    import importlib.util
    import json
    import sys
    from atelier.build_v2.controller_client import _read_at, _json, _captured_source, MAX_NAMED_ISSUER_FILES
    checkout = Path(manifest['checkout'])
    raw = _read_at(Path(specification).parent, Path(specification).name, 2 * 1024 * 1024, owned=True)
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('native worker context changed after launch intent')
    spec = _json(raw)
    if set(spec) != {'version', 'source', 'issuer', 'request', 'binary', 'installation', 'code_files'} or type(spec['version']) is not int or spec['version'] != 1:
        raise ValueError('unsupported captured native worker context')
    if (spec['source'] != manifest['source_digest'] or spec['issuer'] != manifest['issuer_digest']
            or spec['request'] != manifest['scheduler_request']['digest']):
        raise ValueError('native context differs from the original owned invocation')
    files = spec['code_files']
    if (type(files) is not list or not 0 < len(files) <= MAX_NAMED_ISSUER_FILES
            or any(type(name) is not str for name in files) or len(set(files)) != len(files)
            or not set(files) <= set(manifest['issuer_files']) or not set(_WORKER) <= set(files)):
        raise ValueError('native worker code roster is not the selected captured closure')
    all_files = [(name, _read_at(manifest['issuer_root'], name, 8 * 1024 * 1024))
                 for name in manifest['issuer_files']]
    if _captured_source(all_files).digest != manifest['issuer_digest']:
        raise ValueError('native issuer bytes changed')
    installation = spec['installation']
    if (type(installation) is not list or len(installation) != 1
            or type(installation[0]) is not str or not Path(installation[0]).is_absolute()):
        raise ValueError('native installation context is not the fixed Blender bundle')
    import bpy
    binary = Path(bpy.app.binary_path).resolve()
    bundle = binary.parent.parent
    if (binary != Path(spec['binary']).resolve() or binary.parent.name != 'MacOS'
            or bundle.name != 'Contents' or [str(bundle)] != installation):
        raise ValueError('running native image differs from its checked original Blender role')
    _preloaded(manifest, installation, sys._getframe(1))
    from atelier.build_v2.legacy_qualification import CapturedCode, captured_recipe_imports, captured_spec
    from atelier.build_v2.legacy_action import captured_execution_check
    sources = [CapturedCode(str(checkout / name), data) for name, data in all_files if name in files]
    check = captured_execution_check(sources, checkout=checkout, platform_roots=installation)
    sys.addaudithook(check)
    worker = str(checkout / 'platform/studio/atelier/build_batch_worker.py')
    source = next(item for item in sources if item.filename == worker)
    with captured_recipe_imports(sources, checkout=checkout, platform_roots=installation,
                                 on_refusal=check.mark_failed):
        info = captured_spec('__main__', source)
        module = importlib.util.module_from_spec(info)
        sys.modules['__main__'] = module
        with checked_actions(check):
            info.loader.exec_module(module)
            check.require_clean()



def checked_actions(check):
    """Keep the existing worker's receipt AFTER each action's sticky source fence."""
    from contextlib import contextmanager
    @contextmanager
    def observed():
        import runpy
        original = runpy.run_path
        def checked(*args, **kwargs):
            check.require_clean()
            try:
                return original(*args, **kwargs)
            finally:
                check.require_clean()
        runpy.run_path = checked
        try:
            yield
        finally:
            runpy.run_path = original
            check.require_clean()
    return observed()
