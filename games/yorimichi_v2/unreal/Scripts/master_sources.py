"""Load one material master's declared Python sources for one import, without sharing its helper modules with a peer.

The import caller has checked each source against its record pin. The first source is the entry builder; any others
are helpers in dependency order. Relative imports can see only those declared helpers, never unlisted sibling files.
"""
from contextlib import contextmanager
import hashlib
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
import uuid


def checked_sources(game, asset, plan):
    """@cc [owner:fontanierh,label:correctness] material-master-plan-sources
    At each write boundary the prepared master plan MUST match its canonical record's recipe, ordered source paths and
    packages. Read and verify every source against its recorded pin before any source executes. Return those exact byte
    snapshots for the loader, so a file changed after this check cannot substitute different executable bytes.
    """
    if asset is None or asset.kind != 'material-master' or asset.authority != 'generated':
        raise RuntimeError('the import plan has no generated material-master record')
    game = Path(game).resolve()
    folder = asset.folder.resolve()
    paths = [(folder / source.path).resolve() for source in asset.sources]
    if not folder.is_relative_to(game / 'assets') or any(not path.is_relative_to(folder) for path in paths):
        raise RuntimeError(f'{asset.id}: master sources must stay inside their record folder')
    expected = {
        'asset': asset.id, 'kind': asset.kind, 'importer': asset.recipe['importer'], 'version': asset.recipe['version'],
        'settings': asset.recipe.get('settings', {}),
        'sources': [str(path) for path in paths],
        'portable_sources': ['games/yorimichi_v2/' + path.relative_to(game).as_posix() for path in paths],
        'packages': [output.package for output in asset.outputs if output.writer == 'generated'],
    }
    for key, value in expected.items():
        if plan.get(key) != value:
            raise RuntimeError(f'{asset.id}: import plan {key} does not match its record')
    contents = [path.read_bytes() for path in paths]
    for source, content in zip(asset.sources, contents):
        if hashlib.sha256(content).hexdigest() != source.sha256:
            raise RuntimeError(f'{asset.id}: builder source {source.path} differs from its pinned sha256')
    return contents


@contextmanager
def builder(sources, name, *, source_bytes=None):
    """@cc [owner:fontanierh,label:correctness] material-master-private-sources
    Load the first declared source as the builder and the others as its relative helper modules. Each call owns a fresh
    namespace with no filesystem search path. Undeclared relative imports fail; success and failure remove only this
    call's modules, so a warm editor cannot reuse another record's same-named helper. Execute the declared source bytes
    directly rather than a timestamp-based bytecode cache. Production callers supply the verified snapshots returned by
    checked_sources; a caller without snapshots must verify all source pins before calling this.
    """
    paths = [Path(path).resolve() for path in sources]
    if not paths or len({path.stem for path in paths}) != len(paths):
        raise RuntimeError('a material master needs an entry source and distinct helper module names')
    if any(path.suffix != '.py' or not path.stem.isidentifier() or path.stem == '__init__' for path in paths):
        raise RuntimeError('material-master source names must be Python module names ending in .py')
    contents = [path.read_bytes() for path in paths] if source_bytes is None else list(source_bytes)
    if len(contents) != len(paths):
        raise RuntimeError('a material master needs one source snapshot per declared path')
    modules = list(zip(paths, contents))
    namespace = f'_v2_master_{uuid.uuid4().hex}'
    package = ModuleType(namespace)
    package.__package__ = namespace
    package.__path__ = []
    sys.modules[namespace] = package
    try:
        # Helpers load before the entry point; there is no sys.path change or general dependency resolver.
        for path, content in modules[1:] + modules[:1]:
            module_name = f'{namespace}.{path.stem}'
            spec = importlib.util.spec_from_file_location(module_name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            setattr(package, path.stem, module)
            exec(compile(content, str(path), 'exec'), module.__dict__)
        function = getattr(module, name, None)  # the entry builder was loaded last
        if not callable(function) or name.startswith('_'):
            raise RuntimeError(f'{paths[0]} has no builder {name}')
        yield function
    finally:
        for key in list(sys.modules):
            if key == namespace or key.startswith(namespace + '.'):
                del sys.modules[key]
