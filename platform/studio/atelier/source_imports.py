"""Static repository import resolution shared by controllers and native interpreters."""
import ast
from functools import lru_cache
from pathlib import Path
from . import paths
from .build_hashes import signature

@lru_cache(maxsize=2048)
def import_names(source, change_token):
    """Memoize parsed imports, never resolution: added/removed local modules must be rediscovered."""
    imports = []
    todo = [ast.parse(source.read_text(), filename=str(source))]
    while todo:
        node = todo.pop()
        # Imports are statements. Walk every statement suite, including exception handlers and
        # match cases, without visiting hundreds of thousands of numeric terrain literals.
        for field in ('body', 'orelse', 'finalbody', 'handlers', 'cases'):
            value = getattr(node, field, ())
            if isinstance(value, list):
                todo.extend(value)
        if isinstance(node, ast.Import):
            imports.append((0, tuple(a.name for a in node.names)))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ''
            names = (module, *(f'{module}.{a.name}'.lstrip('.') for a in node.names if a.name != '*'))
            imports.append((node.level, names))
    if signature(source.stat()) != change_token:
        raise ValueError(f'Imported source changed while reading: {source}')
    return imports


class ImportScanner:
    """Resolve imports while assembling one recipe. Discard the scanner before the next plan.

    Only this short-lived scope caches resolution, so helpers shared by many actions do not
    repeat filesystem probes. A fresh scanner discovers added/removed modules on the next plan.
    """
    def __init__(self):
        self.resolved = {}

    def resolve(self, root, parts):
        key = (root, tuple(parts))
        if key in self.resolved:
            return self.resolved[key]
        # atelier's source namespace spans Studio and Harness. Resolve it statically,
        # including old public aliases, without importing code from a recipe.
        namespace_parents = []
        if root == paths.STUDIO / 'atelier':
            root, parts = paths.STUDIO, ['atelier', *parts]
        if root == paths.STUDIO and parts and parts[0] == 'atelier':
            namespace_parents = [paths.STUDIO / 'atelier' / '__init__.py']
            if len(parts) > 1 and parts[1] == 'harness':
                root, parts = paths.HARNESS, parts[1:]
            elif len(parts) > 1 and (parts[1] in {'board', 'capacity', 'safety'}
                                    or parts[1].startswith(('board_', 'capacity_'))):
                root, parts = paths.HARNESS, ['harness', *parts[1:]]
        target = root.joinpath(*parts)
        candidates = [target / '__init__.py'] if not parts else [target.with_suffix('.py'), target / '__init__.py']
        found = next((p for p in candidates if p.is_file()), None)
        parents = [root.joinpath(*parts[:i], '__init__.py') for i in range(1, len(parts))]
        result = [found, *(p for p in [*parents, *namespace_parents] if p.is_file())] if found else []
        self.resolved[key] = result
        return result

    def local_imports(self, script, roots=()):
        script = Path(script).resolve()
        repo = paths.REPO.resolve()
        ancestors = [p for p in script.parents if p.is_relative_to(repo)]
        search = tuple(dict.fromkeys([*ancestors, Path(__file__).resolve().parent.parent, *map(Path, roots)]))
        seen, todo = set(), [script]
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
                        found = self.resolve(base, name.split('.') if name else [])
                        if found:
                            todo.extend(found)
                            break
        return sorted(seen)


def local_imports(script, roots=()):
    """Static local imports, including nested statements, package initializers and relative levels.

    Resolve afresh on every call; never import user code. Runtime file loads and computed names
    still require explicit recipe inputs. Recipe factories may share one short-lived scanner.
    """
    return ImportScanner().local_imports(script, roots)

