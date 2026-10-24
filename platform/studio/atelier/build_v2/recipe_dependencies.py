"""Pure dependency extraction from composed recipe Steps into immutable data rows.

No keys, cache, scheduler or producer execution: this only reads declarations and runs the
existing static import scanner. Unknown command types, reads or path roots refuse explicitly.
"""
from dataclasses import fields, is_dataclass
import inspect
from pathlib import Path

from atelier import build, build_products


class Unsupported(ValueError):
    """A Step declares something this extractor cannot represent without dropping an effect."""


ROW_KEYS = ('id', 'commands', 'code', 'inputs', 'deferred', 'reads', 'references', 'needs', 'after', 'products',
            'outputs', 'verify', 'replan')


class _Paths:
    def __init__(self, checkout, build_root):
        self.checkout = Path(checkout).resolve()
        self.build_root = Path(build_root).resolve()
        if not self.build_root.is_relative_to(self.checkout):
            raise Unsupported(f'build root {build_root} is outside the checkout')

    def external(self, value):
        """Inputs outside the checkout under a known, portable root, or None."""
        if not isinstance(value, (str, Path)):
            return None
        text = str(Path(value))
        cache = str(Path.home() / '.cache' / 'atelier')
        if text.startswith(cache + '/'):
            return 'atelier-cache', text[len(cache) + 1:]
        marker = 'Blender.app/Contents/Resources/'
        if marker in text:
            return 'blender', text.split(marker, 1)[1]
        return None

    def input(self, value, *, step, optional):
        try:
            return {'path': self.rel(value, step=step, what='input'), 'root': 'checkout', 'optional': optional}
        except Unsupported:
            known = self.external(value)
            if known is None:
                raise
            return {'path': known[1], 'root': known[0], 'optional': optional}

    def rel(self, value, *, step, what):
        if not isinstance(value, (str, Path)):
            raise Unsupported(f'{step}: {what} of type {type(value).__name__}')
        path = Path(value)
        if not path.is_absolute():
            path = self.checkout / path
        # Lexical normalisation only: cold outputs may not exist, and links are refused later by the runtime.
        absolute = Path(*path.parts) if '..' not in path.parts else path.resolve()
        try:
            return absolute.relative_to(self.checkout).as_posix()
        except ValueError:
            resolved = path.resolve()
            if resolved.is_relative_to(self.checkout):
                return resolved.relative_to(self.checkout).as_posix()
            raise Unsupported(f'{step}: {what} {value} is outside the checkout') from None


def _value(value, paths, *, step, what):
    """Command field values as plain data; project paths become checkout-relative."""
    checkout = str(paths.checkout)
    if isinstance(value, Path):
        return {'path': paths.rel(value, step=step, what=what)}
    if isinstance(value, str):
        if value.startswith(checkout + '/') or value == checkout:
            return {'path': paths.rel(value, step=step, what=what)}
        if checkout in value:
            # An embedded checkout path inside a larger argument (--flag=/abs/...): keep it portable.
            return {'text': value.replace(checkout, '<checkout>')}
        return value
    if value is None or type(value) in (bool, int, float):
        return value
    if type(value) in (tuple, list):
        return [_value(item, paths, step=step, what=what) for item in value]
    if isinstance(value, dict):
        return {str(k): _value(v, paths, step=step, what=what) for k, v in value.items()}
    if hasattr(value, 'value') and type(value).__module__.startswith('atelier'):  # enums such as CookMode
        return {'enum': f'{type(value).__name__}.{value.name}'}
    raise Unsupported(f'{step}: unsupported {what} value of type {type(value).__name__}')


def _callable(fn, paths, *, step, what):
    if fn is None:
        return None
    target = inspect.unwrap(fn)
    try:
        source = inspect.getsourcefile(target)
        line = inspect.getsourcelines(target)[1]
    except (TypeError, OSError) as error:
        raise Unsupported(f'{step}: {what} {fn!r} has no source location') from error
    if source is None:
        raise Unsupported(f'{step}: {what} {fn!r} has no source file')
    defaults = getattr(target, '__defaults__', None) or ()
    kwdefaults = getattr(target, '__kwdefaults__', None) or {}
    cells = []
    for cell in getattr(target, '__closure__', None) or ():
        try:
            content = cell.cell_contents
        except ValueError:
            content = None
        cells.append(_closure_value(content, paths, step=step, what=what))
    bound = getattr(fn, '__self__', None)
    return {'source': paths.rel(source, step=step, what=what + ' source'),
            'qualname': target.__qualname__, 'line': line,
            'defaults': [_closure_value(d, paths, step=step, what=what) for d in defaults],
            'kwdefaults': {k: _closure_value(v, paths, step=step, what=what) for k, v in sorted(kwdefaults.items())},
            'closure': cells,
            'bound': None if bound is None else _closure_value(bound, paths, step=step, what=what)}


def _closure_value(value, paths, *, step, what):
    """Closure cells and defaults: plain data, paths and dataclass records; never object identities."""
    import types
    if isinstance(value, types.ModuleType):
        source = getattr(value, '__file__', None)
        if source is None:
            return {'module': value.__name__}
        try:
            return {'module': value.__name__, 'source': paths.rel(source, step=step, what=what + ' module')}
        except Unsupported:
            known = paths.external(source)
            if known is None and Path(source).resolve().is_relative_to(Path(inspect.__file__).resolve().parent):
                return {'module': value.__name__, 'root': 'python-stdlib'}
            if known is None:
                raise
            return {'module': value.__name__, 'root': known[0], 'source': known[1]}
    if callable(value) and not is_dataclass(value) and not isinstance(value, type):
        return {'callable': _callable(value, paths, step=step, what=what + ' closure')}
    if isinstance(value, type):
        return {'type': f'{value.__module__}.{value.__qualname__}'}
    if is_dataclass(value):
        return {'record': type(value).__name__,
                'fields': {f.name: _closure_value(getattr(value, f.name), paths, step=step, what=what)
                           for f in fields(value) if f.compare}}
    if isinstance(value, (set, frozenset)):
        return {'set': sorted((_closure_value(v, paths, step=step, what=what) for v in value), key=repr)}
    return _value(value, paths, step=step, what=what)


def _command(command, step, batch, paths):
    kind = type(command).__name__
    if isinstance(command, build.Call):
        row = {'kind': 'call', 'name': command.name,
               'fn': _callable(command.fn, paths, step=step.name, what='Call')}
    elif isinstance(command, (build.Python, build.Blender, build.UnrealScript, build.UnrealCompile,
                              build.UnrealGame, build.UnrealPackage)):
        row = {'kind': kind.lower() if kind in ('Python', 'Blender') else kind}
        for f in fields(command):
            row[f.name] = _value(getattr(command, f.name), paths, step=step.name, what=f'{kind}.{f.name}')
    else:
        raise Unsupported(f'{step.name}: unsupported command type {kind}')
    if batch is not None:
        row['batch'] = {'group': batch.group, 'runtime_env': list(batch.runtime_env), 'max_seconds': batch.max_seconds}
    return row


def _code(step, scanner, paths, import_roots):
    files = set()
    scripts = []
    for command in step.commands:
        script = getattr(command, 'script', None)
        if script is not None and Path(script).suffix == '.py':
            scripts.append(Path(script))
        if isinstance(command, build.Call):
            source = inspect.getsourcefile(inspect.unwrap(command.fn))
            if source:
                scripts.append(Path(source))
        for extra in getattr(command, 'runs', list)():
            files.add(Path(extra))
    if step.verify is not None:
        source = inspect.getsourcefile(inspect.unwrap(step.verify))
        if source:
            scripts.append(Path(source))
    for script in scripts:
        files.update(scanner.local_imports(script, import_roots))
    if step.batch is not None:
        files.update(Path(build.__file__).with_name(n) for n in ('build_batches.py', 'build_batch_worker.py'))
    if step.audit:
        from atelier.build_audit import SUPPORT
        files.update(map(Path, SUPPORT))
    # Declared Python inputs are code too: a recipe may name helpers the static scanner cannot reach.
    files.update(Path(p) for p in step.inputs if Path(p).suffix == '.py')
    def code_path(f):
        try:
            return paths.rel(f, step=step.name, what='code file')
        except Unsupported:
            known = paths.external(f)
            if known is None or known[0] != 'blender':
                raise
            return f'<{known[0]}>/{known[1]}'  # installed engine: stable platform, not project source
    return sorted({code_path(f) for f in files})


def _products_index(steps, paths):
    index = {}
    for step in steps:
        for product in step.products:
            if product.name in index:
                raise Unsupported(f'product {product.name} has two producers: {index[product.name][0]} and {step.name}')
            index[product.name] = (step.name, [paths.rel(p, step=step.name, what='product path') for p in product.roots()])
    return index


def _owners_index(steps, paths):
    """Every declared generated root (product roots and outputs) with its producing Step."""
    roots = []
    for step in steps:
        for product in step.products:
            roots += [(paths.rel(p, step=step.name, what='product path'), step.name) for p in product.roots()]
        roots += [(paths.rel(o, step=step.name, what='output'), step.name) for o in step.outputs]
    return roots


def _deferred(provider, step, owners, paths):
    """Collector code and settings plus the producers owning its selected roots; no membership scan."""
    from atelier.build_deferred import setting
    try:
        settings = [setting(value) for value in provider.settings]
    except ValueError as error:
        raise Unsupported(f'{step.name}: deferred provider {provider.name} settings: {error}') from None
    def normalised(value):
        if isinstance(value, dict) and set(value) == {'path'}:
            entry = paths.input(value['path'], step=step.name, optional=False)
            return {'path': entry['path']} if entry['root'] == 'checkout' else {'path': entry['path'], 'root': entry['root']}
        if isinstance(value, list):
            return [normalised(item) for item in value]
        return value
    settings = normalised(settings)
    selected = []
    def collect(value):
        if isinstance(value, dict) and set(value) == {'path'}:
            selected.append(value['path'])  # checkout-relative; external roots never match producer roots
        elif isinstance(value, list):
            for item in value:
                collect(item)
    collect(settings)
    owning = sorted({(root, producer) for path in selected for root, producer in owners
                     if path == root or path.startswith(root + '/') or root.startswith(path + '/')})
    return {'name': provider.name,
            'collect': _callable(provider.collect, paths, step=step.name, what=f'deferred {provider.name}'),
            'settings': settings,
            'support': sorted(paths.rel(p, step=step.name, what='deferred support') for p in provider.support),
            'owners': [{'root': root, 'producer': producer} for root, producer in owning]}


def _row(step, index, owners, scanner, paths, import_roots):
    if type(step) is not build.Step:
        raise Unsupported(f'unsupported step type {type(step).__name__}')
    if step.queries:
        raise Unsupported(f'{step.name}: spatial queries ({len(step.queries)}) need graph-resolved bounds')
    # Retired v1 cache/recovery policy (checkpoint_*, cook_recovery, candidate_scope, pool_roots,
    # cache, cutoff) is not a producer effect and is deliberately omitted.
    def resolved(name, kind):
        if name not in index:
            raise Unsupported(f'{step.name}: {kind} {name} has no producer in the composed recipe')
        producer, roots = index[name]
        return {'producer': producer, 'product': name, 'paths': roots}
    reads = [resolved(name, 'read') for name in step.reads]
    inputs = [paths.input(p, step=step.name, optional=False) for p in step.inputs]
    inputs += [paths.input(p, step=step.name, optional=True) for p in step.optional_inputs]
    deferred = [_deferred(provider, step, owners, paths) for provider in step.deferred_inputs]
    products = [{'id': p.name, 'paths': [paths.rel(x, step=step.name, what='product') for x in p.paths],
                 'optional_paths': [paths.rel(x, step=step.name, what='product') for x in p.optional_paths]}
                for p in step.products]
    return {
        'id': step.name,
        'commands': [_command(c, step, step.batch, paths) for c in step.commands],
        'code': _code(step, scanner, paths, import_roots),
        'inputs': inputs,
        'deferred': deferred,
        'reads': reads,
        'references': [resolved(name, 'reference') for name in step.references],
        'needs': list(step.needs),
        'after': list(step.after),
        'products': products,
        'outputs': [paths.rel(o, step=step.name, what='output') for o in step.outputs],
        'verify': _callable(step.verify, paths, step=step.name, what='verify'),
        'replan': bool(step.replan),
    }


def extract(steps, *, checkout, build_root, import_roots=()):
    """@cc [owner:fontanierh,label:correctness] pure-recipe-dependency-rows
    Return one plain-data row per Step with exactly ROW_KEYS. MUST NOT execute producers,
    collectors, verifiers or Calls, hash content, or touch cache state. Every project path is
    checkout-relative. Anything that cannot be represented raises Unsupported, naming the Step.
    """
    steps = list(steps)
    paths = _Paths(checkout, build_root)
    index = _products_index(steps, paths)
    scanner = build._FastImportScanner()
    roots = tuple(Path(r) for r in import_roots)
    owners = _owners_index(steps, paths)
    return [_row(step, index, owners, scanner, paths, roots) for step in steps]


def coverage(steps, *, checkout, build_root, import_roots=()):
    """Per-reason refusal counts over all steps, for the composition report (still pure)."""
    from collections import Counter
    steps = list(steps)
    paths = _Paths(checkout, build_root)
    try:
        index = _products_index(steps, paths)
    except Unsupported as error:
        return {'steps': len(steps), 'extracted': 0, 'refused': len(steps), 'reasons': {str(error): len(steps)}, 'examples': {}}
    scanner = build._FastImportScanner()
    roots = tuple(Path(r) for r in import_roots)
    owners = _owners_index(steps, paths)
    reasons, examples, ok = Counter(), {}, 0
    for step in steps:
        try:
            _row(step, index, owners, scanner, paths, roots)
            ok += 1
        except Exception as error:  # every refusal or defect is counted, never hidden
            text = str(error) if isinstance(error, Unsupported) else f'{step.name}: internal {type(error).__name__}: {error}'
            reason = text.split(': ', 1)[1] if text.startswith(step.name + ': ') else text
            reason = reason.split(' (')[0]
            for marker in (' value of type ', ' is outside the checkout', ' has no producer'):
                if marker in reason:
                    reason = reason[:reason.index(marker) + len(marker)].strip()
            reasons[reason] += 1
            examples.setdefault(reason, text)
    external = Counter()
    for step in steps:
        for item in [*step.inputs, *step.optional_inputs]:
            known = paths.external(item) if isinstance(item, (str, Path)) else None
            if known is not None and not str(Path(item)).startswith(str(paths.checkout)):
                external[f'{known[0]}:{known[1].split("/")[0]}'] += 1
    return {'steps': len(steps), 'extracted': ok, 'refused': len(steps) - ok, 'external_sources': dict(external),
            'reasons': dict(reasons.most_common()), 'examples': examples}
