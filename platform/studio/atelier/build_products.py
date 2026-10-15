"""Named build outputs and their complete inventories. No processes, locks or shared state.

Products are opt-in. Legacy steps keep their existing fingerprints; a product consumer reads the
bytes of its named product instead of depending on everything its producer happened to generate.
"""
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import stat


@dataclass(frozen=True)
class Product:
    """One independently consumed output, possibly a package and its sidecars or a directory tree."""

    name: str
    paths: tuple[Path, ...]
    collection: str | None = field(default=None, repr=False)
    bounds: tuple[float, ...] | None = field(default=None, repr=False)

    def __post_init__(self):
        if self.collection is None and self.bounds is None:
            return
        from .build_spatial import box
        if not isinstance(self.collection, str) or not self.collection:
            raise ValueError(f'{self.name}: spatial products require a collection and bounds')
        object.__setattr__(self, 'bounds', box(self.bounds))


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def identity(value) -> str:
    """Hash a versioned JSON value with deterministic ordering and unambiguous boundaries."""
    encoded = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def inventory(product: Product, *, hasher=None) -> dict:
    """@cc [owner:fontanierh,label:correctness] complete-output-inventory
    Every declared root and its members MUST be inventoried. Missing, linked, special or changing
    files MUST fail verification; checking only a representative output cannot certify a product.

    Root indexes make the record independent of checkout location. Paths and their ordering are
    part of the recipe, while relative member names belong to this output identity.
    """
    return _inventory(product, hasher=hasher)


def _inventory(product, *, hasher=None, ignore=None):
    """Shared traversal. Only source inventories may exclude generated/cache files."""
    entries, observed = {}, []

    def visit(path, root, index):
        before = path.lstat()
        name = f'{index}/{path.relative_to(root).as_posix()}'
        if stat.S_ISLNK(before.st_mode):
            raise ValueError(f'{product.name}: linked output {path}')
        if stat.S_ISDIR(before.st_mode):
            # Observe the directory before listing it, so additions during traversal are detected.
            observed.append((path, before))
            entries[name] = {'kind': 'directory'}
            for child in sorted(path.iterdir()):
                if ignore is None or not ignore(child):
                    visit(child, root, index)
        elif stat.S_ISREG(before.st_mode):
            entries[name] = {'kind': 'file', 'size': before.st_size, 'sha256': (hasher or file_digest)(path)}
            observed.append((path, before))
        else:
            raise ValueError(f'{product.name}: non-regular output {path}')

    for index, root in enumerate(product.paths):
        root = Path(root)
        if root.is_symlink():
            raise ValueError(f'{product.name}: linked output {root}')
        # System paths such as /tmp and /var may be aliases. Resolve ancestors once, while still
        # rejecting the product root itself and any member that is a link.
        root = root.parent.resolve() / root.name
        visit(root, root, index)
    # Catch membership changes while traversing a tree and changes to earlier files while a later
    # file was being hashed. No second content read is needed.
    for path, before in observed:
        after = path.lstat()
        if (before.st_ino, before.st_mode, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_ino, after.st_mode, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError(f'{product.name}: output changed during inventory {path}')
    return {'schema': 1, 'files': entries}


def records(step, *, hasher=None) -> dict:
    """A complete, independently verifiable record for each product a step owns."""
    result = {}
    for product in step.products:
        manifest = inventory(product, hasher=hasher)
        result[product.name] = {'digest': identity(manifest), 'inventory': manifest}
    return result


def valid_records(step, previous: dict, *, hasher=None) -> bool:
    try:
        return records(step, hasher=hasher) == previous
    except (OSError, ValueError):
        return False


def feed_results(done: dict, products: dict) -> None:
    if not isinstance(products, dict):
        return
    for name, record in products.items():
        digest = record.get('digest') if isinstance(record, dict) else None
        if isinstance(digest, str) and re.fullmatch(r'[0-9a-f]{64}', digest):
            done[f'product:{name}'] = digest


class Graph:
    """Validate declarations once, then select a stable topological execution order.

    Read/order edges constrain execution. Reference edges only expand the selected snapshot;
    mutually referencing records are allowed when neither embeds data derived from the other.
    """

    def __init__(self, steps):
        from . import build_audit
        from .build import declared_inputs, required_inputs
        self.steps = list(steps)
        self.by_name = {}
        self.owners = {}
        owned_paths = []
        for step in self.steps:
            build_audit.validate(step)
            if step.optional_inputs:
                if not step.products:
                    raise ValueError(f'{step.name}: optional inputs require named products')
                required = {str(Path(p).resolve()).casefold() for p in required_inputs(step)}
                optional = [str(Path(p).resolve()).casefold() for p in step.optional_inputs]
                if len(set(optional)) != len(optional) or required.intersection(optional):
                    raise ValueError(f'{step.name}: duplicate or required optional input')
            if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*', step.name):
                raise ValueError(f'Invalid step name: {step.name!r}')
            if step.name in self.by_name:
                raise ValueError(f'Duplicate step: {step.name}')
            self.by_name[step.name] = step
            sources = [tuple(p.casefold() for p in Path(source).resolve().parts)
                       for source in declared_inputs(step)] if step.products else []
            for product in step.products:
                if not product.name or product.name in self.owners:
                    raise ValueError(f'Duplicate or empty product name: {product.name!r}')
                if not product.paths:
                    raise ValueError(f'{product.name}: a product must declare output paths')
                self.owners[product.name] = step.name
                for path in product.paths:
                    output = Path(os.path.abspath(path)).resolve()
                    parts = tuple(p.casefold() for p in output.parts)
                    for source in sources:
                        if source[:len(parts)] == parts or parts[:len(source)] == source:
                            raise ValueError(f'{step.name}: input overlaps its own product {product.name}')
                    owned_paths.append((output, product.name))
        # Sorting path components puts every ancestor immediately before its first descendant.
        # Case-folded comparisons also reject aliases on case-insensitive worktree filesystems.
        previous = None
        for path, owner in sorted((tuple(p.casefold() for p in path.parts), owner)
                                  for path, owner in owned_paths):
            if previous is not None:
                other, other_owner = previous
                if path[:len(other)] == other:
                    raise ValueError(f'Overlapping product ownership: {owner} and {other_owner}')
            previous = path, owner
        # Legacy declarations still reserve their paths. Product restoration and audited rebuilds
        # replace whole roots, so those roots cannot contain (or sit inside) another step's outputs.
        legacy_paths = [(step.name, tuple(p.casefold() for p in Path(path).resolve().parts))
                        for step in self.steps for path in (*step.outputs, *step.pool_roots)]
        for path, product in owned_paths:
            parts = tuple(p.casefold() for p in path.parts)
            for step_name, other in legacy_paths:
                if self.owners[product] != step_name and (parts[:len(other)] == other or other[:len(parts)] == parts):
                    raise ValueError(f'Product {product} overlaps legacy outputs of {step_name}')
        # Resolve against the complete catalogue before topological sorting or target selection.
        from .build_spatial import bind
        self.steps = bind(self.steps, self.owners)
        self.by_name = {s.name: s for s in self.steps}
        for step in self.steps:
            for dependency in (*step.needs, *step.after):
                if dependency not in self.by_name:
                    raise ValueError(f'{step.name}: unknown step dependency {dependency}')
            for name in (*step.reads, *step.references):
                if name not in self.owners:
                    raise ValueError(f'{step.name}: unknown product {name}')
        self._topological = self._sort()

    def prerequisites(self, step):
        return list(dict.fromkeys([*step.needs, *step.after, *(self.owners[n] for n in step.reads)]))

    def _sort(self):
        ordered, visited, active, visiting = [], set(), [], set()

        def visit(name):
            if name in visiting:
                cycle = ' -> '.join([*active[active.index(name):], name])
                raise ValueError(f'Build dependency cycle: {cycle}')
            if name in visited:
                return
            active.append(name)
            visiting.add(name)
            for dependency in self.prerequisites(self.by_name[name]):
                visit(dependency)
            active.pop()
            visiting.remove(name)
            visited.add(name)
            ordered.append(self.by_name[name])

        for step in self.steps:
            visit(step.name)
        return ordered

    def select(self, wanted=()):
        chosen = set()

        def add(name):
            if name in chosen:
                return
            chosen.add(name)
            step = self.by_name[name]
            for dependency in self.prerequisites(step):
                add(dependency)
            for reference in step.references:
                add(self.owners[reference])

        if wanted:
            for name in wanted:
                matches = [s for s in self.steps if s.name == name or
                           (s.name.startswith(name + '.') and not s.explicit)]
                if not matches:
                    raise ValueError(f'Unknown step: {name}; `atelier build <game> --list` shows them')
                for step in matches:
                    add(step.name)
        else:
            for step in self.steps:
                if not step.explicit:
                    add(step.name)
        return [step for step in self._topological if step.name in chosen]
