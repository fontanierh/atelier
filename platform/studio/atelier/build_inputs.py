"""Source inventories and static local imports, without importing or executing recipe code."""
import ast
from functools import lru_cache
from pathlib import Path
import stat

from . import build_products, paths
from .build_hashes import signature

SKIP_PARTS = {'__pycache__', '.DS_Store', 'Binaries', 'Intermediate', 'Saved', 'DerivedDataCache'}
SKIP_SUFFIXES = {'.md'}


@lru_cache(maxsize=2048)
def import_names(source, change_token):
    """Memoize parsed imports, never resolution: added/removed local modules must be rediscovered."""
    imports = []
    for node in ast.walk(ast.parse(source.read_text(), filename=str(source))):
        if isinstance(node, ast.Import):
            imports.append((0, tuple(a.name for a in node.names)))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ''
            names = (module, *(f'{module}.{a.name}'.lstrip('.') for a in node.names if a.name != '*'))
            imports.append((node.level, names))
    if signature(source.stat()) != change_token:
        raise ValueError(f'Imported source changed while reading: {source}')
    return imports


def inventory(path, *, hasher, complete=False):
    """Inventory inputs, including every directory member for audited actions.

    Otherwise match legacy directory exclusions. Explicit files are always read; links are refused.
    Generated output inventories deliberately have no exclusions. A source symlink requires an
    explicit declaration of its real target instead, so cache keys cannot hide an external read.
    """
    ignore = None if complete else lambda p: p.name in SKIP_PARTS or p.suffix in SKIP_SUFFIXES
    return build_products._inventory(build_products.Product('input', (Path(path),)), hasher=hasher, ignore=ignore)


def optional_file(path, *, hasher):
    """@cc [owner:fontanierh,label:correctness] explicit-optional-file-identity
    An optional source MUST identify either absence or a regular file's complete contents.
    Links, directories, special files and I/O errors other than ENOENT MUST NOT become absence.
    """
    path = Path(path)
    try:
        info = path.lstat()
    except FileNotFoundError:
        return {'schema': 1, 'kind': 'absent'}
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(f'Optional input must be a regular file: {path}')
    manifest = inventory(path, hasher=hasher, complete=True)
    if set(manifest['files']) != {'0/.'} or manifest['files']['0/.']['kind'] != 'file':
        raise ValueError(f'Optional input changed type during inventory: {path}')
    return {'schema': 1, 'kind': 'file', 'inventory': manifest}


def local_imports(script, roots=()):
    """Return the static local import closure, including package initializers and relative imports.

    Inspect imports inside functions as well. Search the script's ancestors within the checkout,
    the platform package root and any explicitly declared roots. Never import user code here.
    Runtime file loads and computed import names still require explicit recipe declarations.
    """
    script = Path(script).resolve()
    ancestors = [p for p in script.parents if p.is_relative_to(paths.REPO.resolve())]
    search = tuple(dict.fromkeys([*ancestors, Path(__file__).resolve().parent.parent, *map(Path, roots)]))
    seen, todo = set(), [script]

    def resolve(root, parts):
        target = root.joinpath(*parts)
        candidates = [target / '__init__.py'] if not parts else [target.with_suffix('.py'), target / '__init__.py']
        found = next((p for p in candidates if p.is_file()), None)
        if found is None:
            return []
        parents = [root.joinpath(*parts[:i], '__init__.py') for i in range(1, len(parts))]
        return [found, *(p for p in parents if p.is_file())]

    while todo:
        source = todo.pop().resolve()
        if source in seen:
            continue
        seen.add(source)
        for level, names in import_names(source, signature(source.stat())):
            bases = (source.parent, *search)
            if level:
                if level > len(source.parents):
                    raise ValueError(f'Invalid relative import in {source}')
                bases = (source.parents[level - 1],)
            for name in names:
                for base in bases:
                    found = resolve(base, name.split('.') if name else [])
                    if found:
                        todo.extend(found)
                        break
    return sorted(seen)


def validate_imports(step, inputs):
    """A portable action may not hide a statically resolved local helper from its key."""
    declared = [Path(p).resolve() for p in inputs]
    directories = [p for p in declared if p.is_dir()]
    roots = [p if p.is_dir() else p.parent for p in declared]
    missing = set()
    for command in step.commands:
        if not hasattr(command, 'script'):
            continue
        for module in local_imports(command.script, roots):
            covered = any(module.is_relative_to(p) and not SKIP_PARTS.intersection(module.relative_to(p).parts)
                          and module.suffix not in SKIP_SUFFIXES for p in directories)
            if module not in declared and not covered:
                missing.add(module)
    if missing:
        names = ', '.join(str(p.relative_to(paths.REPO)) if p.is_relative_to(paths.REPO) else p.name
                          for p in sorted(missing))
        raise ValueError(f'{step.name}: undeclared local imports: {names}; add them to inputs')
