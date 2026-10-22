"""Static repository import resolution shared by controllers and native interpreters."""
import ast
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
import threading
from . import paths
from .build_hashes import signature

_SCOPE = threading.local()
_DEFAULT_REPO = paths.REPO.resolve()
_REPO_CLOSURE_CACHE = {}


@contextmanager
def scan_scope():
    """Share one short-lived ImportScanner across a single recipe assembly or plan pass."""
    previous = getattr(_SCOPE, 'scanner', None)
    if previous is None or previous._repo_raw != paths.REPO:
        _SCOPE.scanner = ImportScanner(_fresh=True)
    try:
        yield _SCOPE.scanner
    finally:
        _SCOPE.scanner = previous


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
    def __new__(cls, *, _fresh=False):
        if not _fresh:
            active = getattr(_SCOPE, 'scanner', None)
            if active is not None and active._repo_raw == paths.REPO:
                return active
        instance = super().__new__(cls)
        instance._initialized = False
        return instance

    def __init__(self, *, _fresh=False):
        if getattr(self, '_initialized', False) and self._repo_raw == paths.REPO:
            return
        self._initialized = True
        self._repo_raw = paths.REPO
        self.resolved = {}
        self._realpaths = {}
        self._tokens = {}
        self._direct = {}
        self._closures = {}
        self._call_cache = {}
        self._repo = paths.REPO.resolve()
        self._studio = Path(__file__).resolve().parent.parent

    def _realpath(self, path):
        path = Path(path)
        try:
            return self._realpaths[path]
        except KeyError:
            resolved = path.resolve()
            self._realpaths[path] = resolved
            self._realpaths[resolved] = resolved
            return resolved

    def _token(self, source):
        try:
            return self._tokens[source]
        except KeyError:
            token = signature(source.stat())
            self._tokens[source] = token
            return token

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
        if self._repo_raw != paths.REPO:
            self._initialized = False
            self.__init__(_fresh=True)
        raw_key = (script, tuple(roots))
        if raw_key in self._call_cache:
            return list(self._call_cache[raw_key])
        script = self._realpath(script)
        repo = self._repo
        ancestors = []
        for parent in script.parents:
            ancestors.append(parent)
            if parent == repo:
                break
        else:
            ancestors = [p for p in script.parents if p.is_relative_to(repo)]
        resolved_roots = tuple(self._realpath(r) for r in roots)
        search = tuple(dict.fromkeys([*ancestors, self._studio, *resolved_roots]))
        closure_key = (script, search)
        if closure_key in self._closures:
            self._call_cache[raw_key] = self._closures[closure_key]
            return list(self._closures[closure_key])
        in_default_repo = (
            repo == _DEFAULT_REPO
            and (ancestors and ancestors[-1] == _DEFAULT_REPO)
            and all(r.is_relative_to(_DEFAULT_REPO) for r in resolved_roots)
        )
        if in_default_repo and closure_key in _REPO_CLOSURE_CACHE:
            cached_result, cached_tokens = _REPO_CLOSURE_CACHE[closure_key]
            try:
                if all(self._token(f) == tok for f, tok in cached_tokens):
                    self._closures[closure_key] = cached_result
                    self._call_cache[raw_key] = cached_result
                    return list(cached_result)
            except OSError:
                pass
        seen, todo = set(), [script]
        while todo:
            source = self._realpath(todo.pop())
            if source in seen:
                continue
            seen.add(source)
            direct_key = (source, search)
            if direct_key in self._direct:
                todo.extend(self._direct[direct_key])
                continue
            found_all = []
            for level, names in import_names(source, self._token(source)):
                bases = (source.parent, *search)
                if level:
                    if level > len(source.parents):
                        raise ValueError(f'Invalid relative import in {source}')
                    bases = (source.parents[level - 1],)
                for name in names:
                    parts = name.split('.') if name else []
                    for base in bases:
                        found = self.resolve(base, parts)
                        if found:
                            found_all.extend(found)
                            break
            self._direct[direct_key] = tuple(found_all)
            todo.extend(found_all)
        result = tuple(sorted(seen))
        self._closures[closure_key] = result
        self._call_cache[raw_key] = result
        if in_default_repo:
            _REPO_CLOSURE_CACHE[closure_key] = (result, tuple((f, self._token(f)) for f in result))
        return list(result)


def local_imports(script, roots=()):
    """Static local imports, including nested statements, package initializers and relative levels.

    Resolve afresh on every call; never import user code. Runtime file loads and computed names
    still require explicit recipe inputs. Recipe factories may share one short-lived scanner.
    """
    return ImportScanner().local_imports(script, roots)
