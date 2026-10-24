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
    # bpy.__init__ imports these exact objects from the embedded _bpy module
    # and registers app/handlers/translations/types in sys.modules. A spelling
    # or origin-less ModuleType is never equivalent to those native bindings.
    core = {'bpy.app': ('app',), 'bpy.app.handlers': ('app', 'handlers'),
            'bpy.app.timers': ('app', 'timers'), 'bpy.app.translations': ('app', 'translations'),
            'bpy.app.icons': ('app', 'icons'), 'bpy.props': ('props',), 'bpy.types': ('types',)}
    if name in core or name == '_bpy':
        bpy = modules.get('bpy')
        binding = modules.get('_bpy')
        if not (bpy and binding and tool(getattr(bpy, '__file__', ''))):
            return False
        if any(getattr(bpy, key, None) is not getattr(binding, key, None)
               or getattr(bpy, key, None) is None for key in ('app', 'props', 'types', 'data', 'context', 'msgbus')):
            return False
        if name == '_bpy':
            return module is binding and type(module) is types.ModuleType
        expected = binding
        for member in core[name]:
            expected = getattr(expected, member, None)
            if expected is None:
                return False
        return module is expected
    if type(module) is not types.ModuleType:
        return False
    namespaces = {'bl_operators.node_editor': 'startup/bl_operators/node_editor',
                  'io_scene_gltf2.blender.com': 'addons_core/io_scene_gltf2/blender/com'}
    if name in namespaces:
        import importlib.machinery
        bpy = modules.get('bpy')
        origin = getattr(bpy, '__file__', None)
        if not origin or not tool(origin):
            return False
        expected = (Path(origin).parents[2] / namespaces[name]).resolve()
        info = getattr(module, '__spec__', None)
        loader = getattr(module, '__loader__', None)
        parent, _, member = name.rpartition('.')
        if (type(loader) is not importlib.machinery.NamespaceLoader or info is None
                or info.loader is not loader or info.name != name or info.origin is not None
                or getattr(module, '__file__', None) is not None or module.__package__ != name
                or getattr(modules.get(parent), member, None) is not module
                or tuple(Path(p).resolve() for p in module.__path__) != (expected,)
                or tuple(Path(p).resolve() for p in info.submodule_search_locations) != (expected,)
                or not tool(str(expected))):
            return False
        standard = {'__name__', '__doc__', '__package__', '__loader__', '__spec__', '__file__', '__path__'}
        # A namespace initializer executes no code; only ordinary imported child
        # module bindings may be present beyond its standard import fields.
        return all(type(value) is types.ModuleType and modules.get(name + '.' + key) is value
                   and value.__name__ == name + '.' + key
                   for key, value in vars(module).items() if key not in standard)
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
            elif name in {'typing.io', 'typing.re'}:
                parent = sys.modules.get('typing')
                parent_origin = getattr(parent, '__file__', None)
                if not (parent_origin and tool(parent_origin) and type(module).__module__ == 'typing'
                        and getattr(parent, name.rsplit('.', 1)[1], None) is module):
                    raise ValueError('native typing namespace differs')
            else:
                raise ValueError('native startup origin is not an exact checked tool provider')
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


def _checked_namedtuple(code, caller, compilation):
    """Only the actual installed namedtuple tuple.__new__ template may synthesize code."""
    import keyword
    from atelier.build_v2.legacy_qualification import _same_code
    import types
    def children(current):
        yield current
        for child in current.co_consts:
            if type(child) is types.CodeType:
                yield from children(child)
    if (caller.f_code.co_qualname != 'namedtuple' or compilation is None
            or not any(_same_code(caller.f_code, target) for target in children(compilation))):
        return False
    values = caller.f_locals
    typename, fields, namespace = values.get('typename'), values.get('field_names'), values.get('namespace')
    def identifier(value):
        return type(value) is str and 0 < len(value) <= 128 and value.isascii() and value.isidentifier() and not keyword.iskeyword(value)
    if (not identifier(typename) or type(fields) is not tuple or not 0 < len(fields) <= 128
            or len(set(fields)) != len(fields) or not all(identifier(value) for value in fields)
            or type(namespace) is not dict or set(namespace) != {'_tuple_new', '__builtins__', '__name__'}
            or namespace['_tuple_new'] is not tuple.__new__ or namespace['__builtins__'] != {}
            or namespace['__name__'] != 'namedtuple_' + typename):
        return False
    arguments = ', '.join(fields) + (',' if len(fields) == 1 else '')
    template = f'lambda _cls, {arguments}: _tuple_new(_cls, ({arguments}))'
    return _same_code(code, compile(template, '<string>', 'eval', dont_inherit=True))


def _native_execution_check(sources, *, checkout, installation):
    """Native-only sticky executable origins; namespace search paths grant no code."""
    import importlib.machinery
    import sys
    import types
    from atelier.build_v2.legacy_qualification import _same_code, UnsupportedOrigin
    from atelier.build_v2.controller_client import _read_at, MAX_SOURCE_FILE_BYTES, MAX_SOURCE_TOTAL_BYTES
    roots = tuple(Path(root).resolve() for root in installation)
    expected = {source.filename: source.compiled() for source in sources}
    installed, total = {}, [0]
    diagnostics = set()
    def diagnose(code):
        # Bounded names/type roles only; never source/constant values or environment.
        try:
            import hashlib, json, marshal
            digest = hashlib.sha256(marshal.dumps(code)).hexdigest()
            if digest in diagnostics or len(diagnostics) >= 16:
                return
            diagnostics.add(digest)
            def label(value):
                return value[:160] if type(value) is str and value.isascii() else '<unknown>'
            frames, frame = [], sys._getframe(2)
            for _ in range(8):
                if frame is None: break
                filename = frame.f_code.co_filename
                role = ('captured/' + Path(filename).relative_to(checkout).as_posix()
                        if Path(filename).is_absolute() and Path(filename).is_relative_to(checkout)
                        else 'tool/' + tool_path(filename)[1].as_posix() if tool_path(filename) else 'outside')
                frames.append({'role': role[:200], 'function': label(frame.f_code.co_name)})
                frame = frame.f_back
            row = {'sha256':digest, 'name':label(code.co_name), 'names':list(map(label, code.co_names[:32])),
                   'constant_types':[type(value).__name__ for value in code.co_consts[:32]], 'callers':frames}
            raw = json.dumps(row, separators=(',', ':'), ensure_ascii=True)
            if len(raw.encode()) <= 4096:
                sys.stderr.write('native_code_refused ' + raw + '\n'); sys.stderr.flush()
        except Exception:
            pass
    def refused():
        check.failed = True
        code = sys._getframe(1).f_locals.get('code')
        if type(code) is types.CodeType:
            diagnose(code)
        raise UnsupportedOrigin('native executable provider is outside its checked code scope')
    def tool_path(filename):
        path = Path(filename)
        if not path.is_absolute():
            return None
        resolved = path.resolve()
        return next(((root, resolved.relative_to(root)) for root in roots
                     if resolved.is_relative_to(root)), None)
    def tool_compilation(filename):
        if filename in installed:
            return installed[filename]
        location = tool_path(filename)
        if location is None or not filename.endswith('.py'):
            return None
        raw = _read_at(location[0], location[1].as_posix(), MAX_SOURCE_FILE_BYTES)
        total[0] += len(raw)
        if total[0] > MAX_SOURCE_TOTAL_BYTES:
            refused()
        code = compile(raw, filename, 'exec', dont_inherit=True, optimize=sys.flags.optimize)
        installed[filename] = code
        return code
    def children(code):
        yield code
        for child in code.co_consts:
            if type(child) is types.CodeType:
                yield from children(child)
    def execution_caller():
        frame = sys._getframe(1)
        for _ in range(8):
            if frame is None:
                return None
            if frame.f_code is check.__code__:
                frame = frame.f_back
                if frame is not None and frame.f_code is getattr(check, 'wrapper_code', None):
                    frame = frame.f_back
                return frame
            frame = frame.f_back
        return None
    def checked_tool_caller(code):
        caller = execution_caller()
        if caller is None:
            return False
        filename = caller.f_code.co_filename
        if Path(filename).name == '__init__.py' and Path(filename).parent.name == 'collections':
            return _checked_namedtuple(code, caller, tool_compilation(filename))
        if Path(filename).name == 'typing.py':
            return checked_cycles_annotation(code, caller, tool_compilation(filename))
        if Path(filename).name == 'dataclasses.py':
            return checked_dataclass(code, caller, tool_compilation(filename))
        return False
    def checked_dataclass(code, caller, compilation):
        # CPython 3.13 builds all methods in one wrapper. Bind the complete
        # wrapper to the actual installed generator AND the static SDK class
        # currently being decorated, rather than granting anonymous exec.
        import ast
        dc = sys.modules.get('dataclasses')
        if (dc is None or compilation is None
                or caller.f_code.co_qualname != '_FuncBuilder.add_fns_to_class'
                or not any(_same_code(caller.f_code, item) for item in children(compilation))):
            return False
        builder, cls = caller.f_locals.get('self'), caller.f_locals.get('cls')
        if (type(builder) is not getattr(dc, '_FuncBuilder', None) or type(cls) is not type
                or set(vars(builder)) != {'names', 'src', 'globals', 'locals',
                                          'overwrite_errors', 'unconditional_adds'}):
            return False
        process = caller.f_back
        if (process is None or process.f_code.co_qualname != '_process_class'
                or not any(_same_code(process.f_code, item) for item in children(compilation))
                or process.f_locals.get('func_builder') is not builder
                or process.f_locals.get('cls') is not cls):
            return False
        frame = process.f_back
        for _ in range(4):
            if frame is None:
                return False
            if frame.f_code.co_filename != caller.f_code.co_filename:
                break
            if not any(_same_code(frame.f_code, item) for item in children(compilation)):
                return False
            frame = frame.f_back
        if frame is None or frame.f_code.co_name != '<module>':
            return False
        module = sys.modules.get(cls.__module__)
        filename = frame.f_code.co_filename
        original = tool_compilation(filename)
        location = tool_path(filename)
        if (module is None or frame.f_globals is not vars(module)
                or builder.globals is not vars(module) or original is None or location is None
                or not _same_code(frame.f_code, original)):
            return False
        raw = _read_at(location[0], location[1].as_posix(), MAX_SOURCE_FILE_BYTES)
        classes = [node for node in ast.parse(raw).body
                   if isinstance(node, ast.ClassDef) and node.name == cls.__name__]
        if (len(classes) != 1 or len(classes[0].decorator_list) != 1
                or not isinstance(classes[0].decorator_list[0], ast.Name)
                or classes[0].decorator_list[0].id != 'dataclass'
                or vars(module).get('dataclass') is not dc.dataclass):
            return False
        fields = [node.target.id for node in classes[0].body
                  if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)]
        if list(vars(cls).get('__annotations__', {})) != fields:
            return False
        if (type(builder.src) is not list or type(builder.names) is not list
                or not 0 < len(builder.src) == len(builder.names) <= 16
                or not all(type(value) is str for value in builder.src + builder.names)
                or any(name not in {'__init__', '__repr__', '__eq__', '__lt__', '__le__',
                                    '__gt__', '__ge__', '__hash__', '__setattr__', '__delattr__'}
                       for name in builder.names)
                or type(builder.locals) is not dict
                or not all(type(name) is str and name.isidentifier() for name in builder.locals)):
            return False
        text = (f'def __create_fn__({",".join(builder.locals)}):\n'
                + '\n'.join(builder.src) + f'\n return ({",".join(builder.names)},)')
        if len(text.encode()) > 65536 or caller.f_locals.get('txt') != text:
            return False
        return _same_code(code, compile(text, '<string>', 'exec', dont_inherit=True))
    def checked_cycles_annotation(code, caller, compilation):
        import ast, builtins
        typing = sys.modules.get('typing')
        ref = caller.f_locals.get('self')
        if (caller.f_code.co_qualname != 'ForwardRef._evaluate' or compilation is None
                or not any(_same_code(caller.f_code, target) for target in children(compilation))
                or typing is None or type(ref) is not typing.ForwardRef
                or ref.__forward_code__ is not code or type(ref.__forward_arg__) is not str
                or len(ref.__forward_arg__) > 16384):
            return False
        frame, base, owner = caller.f_back, None, None
        for _ in range(6):
            if frame is None: break
            if frame.f_code.co_qualname == 'get_type_hints':
                if not any(_same_code(frame.f_code, target) for target in children(compilation)):
                    return False
                base = frame.f_locals.get('base')
                owner = frame.f_locals.get('obj')
                break
            frame = frame.f_back
        bpy, binding = sys.modules.get('bpy'), sys.modules.get('_bpy')
        struct = getattr(getattr(binding, 'types', None), 'bpy_struct', None)
        if (not isinstance(base, type) or not isinstance(owner, type) or not isinstance(struct, type)
                or not issubclass(owner, struct)):
            return False
        module = sys.modules.get(base.__module__)
        filename = getattr(module, '__file__', None)
        bpy_file = getattr(bpy, '__file__', None)
        if not bpy_file or tool_path(bpy_file) is None:
            return False
        script_root = Path(bpy_file).resolve().parents[2]
        def sdk_module(value):
            path = getattr(value, '__file__', None)
            if not path or tool_path(path) is None:
                return False
            resolved = Path(path).resolve()
            if not resolved.is_relative_to(script_root):
                return False
            relative = resolved.relative_to(script_root)
            return relative.parts[0] in {'addons_core', 'startup', 'modules'}
        if (not sdk_module(module) or getattr(module, base.__name__, None) is not base
                or not sdk_module(sys.modules.get(owner.__module__))):
            return False
        namespaces = [caller.f_locals.get('globalns'), caller.f_locals.get('localns')]
        if any(type(namespace) is not dict for namespace in namespaces) or not any(namespace is vars(module) for namespace in namespaces):
            return False
        for namespace in namespaces:
            if namespace is vars(module): continue
            actual = {key:value for key,value in namespace.items() if key != '__builtins__'}
            if (set(actual) != set(vars(base)) or any(actual[key] is not value for key,value in vars(base).items())
                    or namespace.get('__builtins__', vars(builtins)) is not vars(builtins)):
                return False
        location = tool_path(filename)
        raw = _read_at(location[0], location[1].as_posix(), MAX_SOURCE_FILE_BYTES)
        tree = ast.parse(raw, filename)
        wanted = ast.parse(ref.__forward_arg__, mode='eval')
        if sum(1 for _ in ast.walk(wanted)) > 1024:
            return False
        shape = ast.dump(wanted.body, include_attributes=False)
        def annotation(node):
            value = node.annotation
            if isinstance(value, ast.Constant) and type(value.value) is str:
                value = ast.parse(value.value, mode='eval').body
            return ast.dump(value, include_attributes=False)
        if not any(annotation(node) == shape for node in ast.walk(tree) if isinstance(node, ast.AnnAssign)):
            return False
        if not _same_code(code, compile(ref.__forward_arg__, '<string>', 'eval', dont_inherit=True)):
            return False
        target = tool_compilation(filename)
        bpy, binding = sys.modules.get('bpy'), sys.modules.get('_bpy')
        if bpy is None or binding is None or bpy.props is not binding.props:
            return False
        for node in ast.walk(wanted):
            if not isinstance(node, ast.Name): continue
            name = node.id
            value = namespaces[1].get(name, namespaces[0].get(name, vars(builtins).get(name)))
            if getattr(binding.props, name, None) is value and value is not None:
                if type(value) is not types.BuiltinFunctionType:
                    return False
            elif value is getattr(getattr(getattr(binding, 'app', None), 'translations', None), 'contexts', None) and value is not None:
                if getattr(getattr(getattr(bpy, 'app', None), 'translations', None), 'contexts', None) is not value:
                    return False
                attributes = [item.attr for item in ast.walk(wanted) if isinstance(item, ast.Attribute)
                              and isinstance(item.value, ast.Name) and item.value.id == name]
                if not attributes or any(item != 'id_light' for item in attributes) or value.id_light != 'Light':
                    return False
            elif type(value) is types.FunctionType:
                callback_module = sys.modules.get(value.__module__)
                if not sdk_module(callback_module) or value.__globals__ is not vars(callback_module) or value.__closure__:
                    return False
                callback_code = tool_compilation(callback_module.__file__)
                if not any(_same_code(value.__code__, child) for child in children(callback_code)):
                    return False
            elif isinstance(value, type):
                if getattr(module, name, None) is not value or not any(isinstance(c, ast.ClassDef) and c.name == value.__name__ for c in ast.walk(tree)):
                    return False
            elif type(value) is types.ModuleType:
                if value is not bpy:
                    return False
            elif type(value) not in (bool, int, float, str, tuple, list, dict, set, type(None)):
                return False
        return True
    factory_text = (('addon_utils.disable_all()', 'eval', False), ('bl_app_template_utils.reset()', 'eval', False),
                    ('bpy.utils.refresh_script_paths()\naddon_utils.reset_all()', 'exec', False),
                    ('bpy.utils._on_exit()', 'eval', True))
    factory_checked = set()
    def checked_factory_expression(code):
        template = next(((text, c_only) for text, mode, c_only in factory_text
                     if _same_code(code, compile(text, '<string>', mode, dont_inherit=True))), None)
        if template is None or len(roots) != 1:
            return False
        text, c_only = template
        caller_frame = execution_caller()
        if c_only and caller_frame is not None:
            return False
        caller = None if caller_frame is None else caller_frame.f_code
        if caller is not None:
            target = expected.get(caller.co_filename)
            if target is None or not any(_same_code(caller, child) for child in children(target)):
                return False
        if text not in factory_checked:
            import mmap
            binary = roots[0] / 'MacOS/Blender'
            with binary.open('rb') as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as image:
                if image.find(text.encode() + b'\0') < 0:
                    return False
            factory_checked.add(text)
        return True
    def check(event, arguments):
        try:
            if event == 'import' and len(arguments) > 1 and arguments[1]:
                filename = arguments[1]
                if type(filename) is not str or (filename not in expected and tool_path(filename) is None):
                    refused()
            if event != 'exec':
                return
            code = arguments[0]
            filename = code.co_filename
            target = expected.get(filename)
            if target is not None:
                if not _same_code(code, target):
                    refused()
                return
            if filename.startswith('<frozen ') and filename.endswith('>'):
                name = filename[8:-1]
                frozen = importlib.machinery.FrozenImporter.get_code(name)
                if frozen is None or not _same_code(code, frozen):
                    refused()
                return
            if Path(filename).is_absolute():
                target = tool_compilation(filename)
                if target is None or not _same_code(code, target):
                    refused()
            elif filename in {'<string>', '<stdin>'}:
                if not checked_tool_caller(code) and not checked_factory_expression(code):
                    refused()
            else:
                refused()
        except (OSError, ValueError, ImportError, TypeError, AttributeError):
            check.failed = True
            raise
    check.failed = False
    check.mark_failed = lambda: setattr(check, 'failed', True)
    def require_clean():
        if check.failed:
            raise UnsupportedOrigin('native source-origin violation remains sticky')
    check.require_clean = require_clean
    return check


def _fatal_native_audit(check):
    """An embedded interpreter must not swallow origin refusal during C teardown."""
    import os, sys
    exit_process, write, flush, base, type_ = os._exit, sys.stderr.write, sys.stderr.flush, BaseException, type
    def checked(event, arguments):
        try:
            check(event, arguments)
        except base as error:
            try:
                write('native source-origin refusal: ' + type_(error).__name__ + '\n'); flush()
            except base:
                pass
            # Only this owned worker exits. Its existing independent C7 monitor
            # retains custody/capacity until actual descendant cleanup is positive.
            exit_process(1)
    check.wrapper_code = checked.__code__
    return checked


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
    if set(spec) != {'version', 'source', 'issuer', 'request', 'binary', 'installation', 'code_files', 'atomic_temporary'} or type(spec['version']) is not int or spec['version'] != 1:
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
    import os
    batch = Path(os.environ.get('ATELIER_BATCH', ''))
    temporary = Path(spec['atomic_temporary'])
    if (not batch.is_absolute() or batch.parent != Path(manifest['output']) / '.state/batches'
            or len(batch.name) != 32 or any(c not in '0123456789abcdef' for c in batch.name)
            or temporary != batch / 'atomic-tmp'):
        raise ValueError('native atomic scratch differs from its original owned batch namespace')
    _preloaded(manifest, installation, sys._getframe(1))
    from atelier.build_v2.legacy_qualification import CapturedCode, captured_recipe_imports, captured_spec
    sources = [CapturedCode(str(checkout / name), data) for name, data in all_files if name in files]
    check = _native_execution_check(sources, checkout=checkout, installation=installation)
    sys.addaudithook(_fatal_native_audit(check))
    worker = str(checkout / 'platform/studio/atelier/build_batch_worker.py')
    source = next(item for item in sources if item.filename == worker)
    with captured_recipe_imports(sources, checkout=checkout, platform_roots=installation,
                                 on_refusal=check.mark_failed):
        info = captured_spec('__main__', source)
        module = importlib.util.module_from_spec(info)
        sys.modules['__main__'] = module
        from atelier import atomic_files
        with atomic_files.managed_temporaries(temporary), checked_actions(check):
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
