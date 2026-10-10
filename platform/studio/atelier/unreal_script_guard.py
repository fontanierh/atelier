"""Runs an editor script (ATELIER_SCRIPT) so it can use only the game modules its build step declares.

ATELIER_SCRIPT_MODULES maps each declared module to 'code' or 'interface'; ATELIER_PROJECT_MODULES lists every game
and plugin module. Engine types are free. A script may name a declared module's classes, structs and enums, create
them and set their properties; it may call their functions only when the step depends on the module's code. Naming a
type of another game module, or calling a function of a type whose code the step does not depend on (however the
script came by the type or object), ends the editor with an error, so a script cannot come to depend on game code its
step does not track (atelier.unreal_modules). Runs inside the editor's Python: standard library only.

Unreal's function wrappers are not Python functions (no profiling events) and its types are immutable, so the guard
replaces the functions in those types' own namespaces for the length of the script.
"""
import ctypes, gc, json, os, runpy, sys, types


def module_of(value):
    """'/Script/<Module>' types' module name, or None."""
    for accessor in ('static_class', 'static_struct', 'static_enum'):
        get = getattr(value, accessor, None)
        if get is not None:
            try:
                path = get().get_outer().get_path_name()
            except Exception:
                return None
            return path[len('/Script/'):] if path.startswith('/Script/') else None
    return None


def functions(cls):
    """The functions a type itself defines: public non-data descriptors (properties are data descriptors)."""
    return {name: value for name, value in vars(cls).items() if not name.startswith('_')
            and hasattr(type(value), '__get__') and not hasattr(type(value), '__set__')}


def seal(cls, refuse):
    """Replace the functions `cls` defines with calls to refuse(name); returns what restores them."""
    namespace = gc.get_referents(cls.__dict__)[0]   # the dict behind the read-only mapping
    originals = functions(cls)
    for name in originals:
        namespace[name] = staticmethod(lambda *args, name=name, **kwargs: refuse(name))
    ctypes.pythonapi.PyType_Modified(ctypes.py_object(cls))   # drop cached lookups

    def restore():
        namespace.update(originals)
        ctypes.pythonapi.PyType_Modified(ctypes.py_object(cls))
    return restore


class Guard:
    def __init__(self, unreal, script, declared, project, stop):
        self.unreal, self.script, self.declared, self.project, self.stop = unreal, script, declared, set(project), stop
        self.modules = {}

    def module(self, value):
        key = id(value)
        if key not in self.modules:
            self.modules[key] = module_of(value)
        return self.modules[key]

    def name(self, attribute):
        """unreal.<attribute>, refused when it belongs to an undeclared game module."""
        value = getattr(self.unreal, attribute)
        if isinstance(value, type):
            module = self.module(value)
            if module in self.project and module not in self.declared:
                self.stop(f'{self.script} uses unreal.{attribute} from the game module {module}, which its build step '
                          f'does not declare (UnrealScript modules)')
        return value

    def seal(self):
        """Seal the functions of every game type whose code the step does not depend on; returns what restores them."""
        restores = []
        for attribute in dir(self.unreal):
            value = getattr(self.unreal, attribute, None)
            if not isinstance(value, type):
                continue
            module = self.module(value)
            if module in self.project and self.declared.get(module) != 'code' and functions(value):
                how = 'only by interface' if module in self.declared else 'not at all'
                restores.append(seal(value, lambda function, owner=value.__name__, module=module, how=how: self.stop(
                    f'{self.script} calls {owner}.{function} from the game module {module}, which its build step '
                    f'declares {how}: depend on its code')))
        return lambda: [restore() for restore in restores]


def install(unreal, script, declared, project, stop):
    """Replace the unreal module with a guarded view and seal game functions; returns what restores them."""
    guard = Guard(unreal, script, declared, project, stop)
    view = types.ModuleType('unreal', unreal.__doc__)
    view.__getattr__ = guard.name
    sys.modules['unreal'] = view
    return guard.seal()


def stop(message):
    print(f'ATELIER SCRIPT GUARD: {message}', flush=True)
    sys.stderr.flush()
    os._exit(3)   # an exception could be caught by the script; the step must fail


def main():
    import unreal
    script = os.environ['ATELIER_SCRIPT']
    restore = install(unreal, script, json.loads(os.environ['ATELIER_SCRIPT_MODULES']),
                      json.loads(os.environ['ATELIER_PROJECT_MODULES']), stop)
    sys.argv = [script]
    sys.path.insert(0, os.path.dirname(script))
    try:
        runpy.run_path(script, run_name='__main__')
    finally:
        restore()
        sys.modules['unreal'] = unreal


if __name__ == '__main__':
    main()
