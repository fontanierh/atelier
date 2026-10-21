"""Source inventories and static local imports, without importing or executing recipe code."""
from pathlib import Path
import stat

from . import build_products, paths
from .source_imports import import_names, ImportScanner, local_imports

SKIP_PARTS = {'__pycache__', '.DS_Store', 'Binaries', 'Intermediate', 'Saved', 'DerivedDataCache'}
SKIP_SUFFIXES = {'.md'}


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
