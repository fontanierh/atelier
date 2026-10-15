"""One-shot Blender/editor Python bootstrap. Standard library only; never launches a host.

The parent supplies a private inherited report pipe and approved, hashed installation roots.
An audit covers Python-level action work, not the host's native I/O or native callbacks.
"""
import json
from importlib.machinery import BuiltinImporter, FrozenImporter
import os
from pathlib import Path
import sys
import sysconfig
from types import ModuleType


def load(name, path):
    # Embedded hosts may ignore PYTHONPYCACHEPREFIX at startup. Never execute ambient support
    # bytecode before execute() has configured the observer's private bytecode location.
    path = Path(path)
    module = ModuleType(name)
    module.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    return module


def runtime_roots(approved, *, host=None):
    """Only recognized Python library directories inside the hashed host installation."""
    approved = [Path(p).resolve() for p in approved]
    roots = {Path(sysconfig.get_path(name)).resolve()
             for name in ('stdlib', 'platstdlib', 'purelib', 'platlib')}
    if not roots or any(not any(p.is_relative_to(base) for base in approved) for p in roots):
        raise RuntimeError('Native Python runtime is outside its fingerprinted installation')
    if host == 'UnrealScript':
        # Source-verified UE 5.8 wrapper directory, completely inventoried by the parent. Do
        # not grant other engine/plugin/project paths just because a host added them to sys.path.
        suffix = ('Engine', 'Plugins', 'Experimental', 'PythonScriptPlugin', 'Content', 'Python')
        roots.update(p for p in approved if p.parts[-len(suffix):] == suffix)
    return sorted(map(str, roots))


HOST_MODULES = {
    'Blender': {'_bpy', 'bpy', 'bpy.app', 'bpy.app.handlers', 'bpy.app.timers',
                'bpy.app.translations', 'bpy.app.icons', 'bpy.props', 'bpy.types'},
    # UE 5.8 PythonScriptPlugin.cpp imports these four bindings at startup. PyCore/PySlate/
    # PyEngine/PyEditor.cpp create exactly these originless modules with PyImport_AddModule.
    # Both native plugin binaries and their module descriptor are part of the tool identity.
    'UnrealScript': {'unreal', '_unreal_core', '_unreal_slate', '_unreal_engine', '_unreal_editor'},
}


def check_preloaded(spec):
    """@cc [owner:fontanierh,label:correctness] native-preload-provenance
    Preloaded non-tool Python modules MUST be refused even when their source is a declared input:
    a declaration cannot prove their already consumed bytes or cached values. Tool module origins,
    module-spec origins and namespace locations MUST belong to a completely fingerprinted
    installation. Cached bytecode MUST belong to that installation or the fresh private bytecode
    directory. Originless modules require genuine builtin/frozen loader provenance or an explicit
    native-host/runtime API; arbitrary search paths grant no trust.
    """
    installation = [Path(p).resolve() for p in spec['installation']]
    bytecode = Path(spec['scratch']).resolve() / 'bytecode'
    bootstrap = Path(__file__).resolve()

    def tool_path(value):
        path = Path(value).resolve()
        return any(path.is_relative_to(root) for root in installation)

    for name, module in list(sys.modules.items()):
        origin = getattr(module, '__file__', None)
        info = getattr(module, '__spec__', None)
        bootstrap_main = name == '__main__' and origin and Path(origin).resolve() == bootstrap
        actual = getattr(info, 'origin', None)
        if (actual not in (None, 'built-in', 'frozen') and not tool_path(actual)
                and not (bootstrap_main and Path(actual).resolve() == bootstrap)):
            raise RuntimeError('Native audit refuses an inconsistent preloaded module origin')
        cached = getattr(module, '__cached__', None)
        if cached and not (tool_path(cached) or Path(cached).resolve().is_relative_to(bytecode)):
            raise RuntimeError('Native audit refuses preloaded bytecode outside its tool or fresh scratch')
        for locations in (getattr(module, '__path__', None), getattr(info, 'submodule_search_locations', None)):
            if locations is not None and not all(tool_path(p) for p in locations):
                raise RuntimeError('Native audit refuses preloaded package paths outside its tool')
        if bootstrap_main:
            continue  # runpy replaces __main__ with the action's own freshly executed module.
        if (name == '__main__' and spec['host'] == 'UnrealScript' and origin is None and info is None
                and isinstance(module, ModuleType) and module.__name__ == '__main__'):
            # UE 5.8 creates this empty module with PyImport_AddModule, then executes files in
            # a copied globals dict. runpy replaces it before the recipe can import __main__.
            continue
        if origin:
            if not tool_path(origin):
                raise RuntimeError('Native audit refuses a preloaded non-tool Python module')
            continue
        if (getattr(info, 'loader', None) is BuiltinImporter and name in sys.builtin_module_names
                and info.origin == 'built-in'):
            continue
        if (getattr(info, 'loader', None) is FrozenImporter and info.origin == 'frozen'
                and FrozenImporter.find_spec(name) is not None):
            continue
        locations = getattr(info, 'submodule_search_locations', None)
        if locations is not None and locations and all(tool_path(p) for p in locations):
            continue
        if (name in HOST_MODULES[spec['host']] and module is not None
                and getattr(info, 'origin', None) in (None, 'built-in')):
            continue
        # CPython 3.11/3.12 exports these two class namespaces through sys.modules. They have
        # no module spec; verify their exact binding and defining tool module, not a prefix.
        if name in ('typing.io', 'typing.re'):
            parent = sys.modules.get('typing')
            parent_origin = getattr(parent, '__file__', None)
            if (parent_origin and tool_path(parent_origin) and type(module).__module__ == 'typing'
                    and getattr(parent, name.rsplit('.', 1)[1], None) is module):
                continue
        raise RuntimeError('Native audit refuses an unverifiable preloaded Python module')


def main():
    """@cc [owner:fontanierh,label:correctness] fresh-native-audit-process
    A native host MUST observe at most one audited action. Its irreversible hook MUST remain armed
    after completion, and the parent MUST reject trailing records before certifying the action.
    Arbitrary sys.path entries MUST NOT receive a tool-runtime exemption.
    """
    previous = getattr(sys, '_atelier_native_audit_started', False)
    if previous:
        if hasattr(previous, 'record'):
            previous.record('native lifecycle', reason='native host attempted a second audited action')
        raise RuntimeError('Native input audits require a fresh process for every action')
    sys._atelier_native_audit_started = True
    spec = json.loads(Path(os.environ['ATELIER_AUDIT_SPEC']).read_text())
    if spec['host'] not in ('Blender', 'UnrealScript'):
        raise ValueError('Unsupported native audit host')
    spec['runtime'] = runtime_roots(spec['installation'], host=spec['host'])
    spec['labels'].extend((p, 'runtime') for p in spec['runtime'])
    check_preloaded(spec)
    worker = load('atelier_native_audit_worker', Path(__file__).with_name('build_audit_worker.py'))
    after = None
    if spec['host'] == 'UnrealScript' and spec['module_guard']:
        guard = load('atelier_native_module_guard', Path(__file__).with_name('unreal_script_guard.py'))
        left_out = json.loads(os.environ['ATELIER_LEFT_OUT'])
        # Preserve descriptor isolation and the existing before/after native library checks.
        after = lambda: guard.check(spec['script'], left_out, guard.stop)
        after()
    worker.execute(spec, blender=spec['host'] == 'Blender', before=lambda: check_preloaded(spec), after=after)


if __name__ == '__main__':
    main()
