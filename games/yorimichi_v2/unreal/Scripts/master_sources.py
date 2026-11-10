"""Load one material master's declared Python sources for one import, without sharing its helper modules with a peer.

The import caller has checked each source against its record pin. The first source is the entry builder; any others
are helpers in dependency order. Relative imports can see only those declared helpers, never unlisted sibling files.
"""
from contextlib import contextmanager
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
import uuid


@contextmanager
def builder(sources, name):
    """@cc [owner:fontanierh,label:correctness] material-master-private-sources
    Load the first declared source as the builder and the others as its relative helper modules. Each call owns a fresh
    namespace with no filesystem search path. Undeclared relative imports fail; success and failure remove only this
    call's modules, so a warm editor cannot reuse another record's same-named helper. Execute the declared source bytes
    directly rather than a timestamp-based bytecode cache. The caller must verify all source pins before calling this.
    """
    paths = [Path(path).resolve() for path in sources]
    if not paths or len({path.stem for path in paths}) != len(paths):
        raise RuntimeError('a material master needs an entry source and distinct helper module names')
    if any(path.suffix != '.py' or not path.stem.isidentifier() or path.stem == '__init__' for path in paths):
        raise RuntimeError('material-master source names must be Python module names ending in .py')
    namespace = f'_v2_master_{uuid.uuid4().hex}'
    package = ModuleType(namespace)
    package.__package__ = namespace
    package.__path__ = []
    sys.modules[namespace] = package
    try:
        # Helpers load before the entry point; there is no sys.path change or general dependency resolver.
        for path in paths[1:] + paths[:1]:
            module_name = f'{namespace}.{path.stem}'
            spec = importlib.util.spec_from_file_location(module_name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            setattr(package, path.stem, module)
            exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
        function = getattr(module, name, None)  # the entry builder was loaded last
        if not callable(function) or name.startswith('_'):
            raise RuntimeError(f'{paths[0]} has no builder {name}')
        yield function
    finally:
        for key in list(sys.modules):
            if key == namespace or key.startswith(namespace + '.'):
                del sys.modules[key]
