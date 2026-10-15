"""Recipe-declared spatial dependencies. Boxes use one caller-defined coordinate frame and unit."""
from dataclasses import dataclass, replace
import math


def box(value):
    """Canonical finite (min_x, min_y, min_z, max_x, max_y, max_z), including flat boxes."""
    if not isinstance(value, (tuple, list)) or len(value) != 6 or not all(
            type(n) in (int, float) and math.isfinite(n) for n in value):
        raise ValueError('Spatial bounds require six finite numbers')
    result = tuple(float(n) for n in value)
    if any(result[i] > result[i + 3] for i in range(3)):
        raise ValueError('Spatial bounds minimum exceeds maximum')
    return result


@dataclass(frozen=True)
class BBoxQuery:
    """A named, inclusive intersection against one collection of conservative product bounds."""

    name: str
    collection: str
    bounds: tuple[float, ...]

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name or not isinstance(self.collection, str) or not self.collection:
            raise ValueError('Spatial queries require a name and collection')
        object.__setattr__(self, 'bounds', box(self.bounds))


@dataclass(frozen=True)
class Match:
    name: str
    owner: str
    paths: tuple
    bounds: tuple


@dataclass(frozen=True)
class Binding:
    query: BBoxQuery
    matches: tuple[Match, ...]


def bind(steps, owners, *, catalogue=None):
    """@cc [owner:fontanierh,label:correctness] complete-spatial-membership
    Each query MUST resolve against all current declarations before scheduling. Its key MUST
    include the selector and complete sorted match set, including an empty set. Unmatched products
    MUST NOT become read dependencies. Touching boxes count as intersections.

    Work on copies: planning the same recipe twice must not accumulate inferred read edges.
    A checkpoint may bind just its consumer, against a separately validated complete catalogue.
    """
    collections = {}
    for step in steps if catalogue is None else catalogue:
        for product in step.products:
            if product.collection is not None:
                collections.setdefault(product.collection, []).append(
                    Match(product.name, owners[product.name], tuple(product.paths), product.bounds))
    bound = []
    for step in steps:
        if not step.queries:
            bound.append(step)
            continue
        if not step.audit:
            raise ValueError(f'{step.name}: spatial queries require an audited Python action')
        if any(not isinstance(q, BBoxQuery) for q in step.queries):
            raise ValueError(f'{step.name}: invalid spatial query')
        if len({q.name for q in step.queries}) != len(step.queries):
            raise ValueError(f'{step.name}: duplicate spatial query name')
        bindings = []
        for query in sorted(step.queries, key=lambda q: q.name):
            matches = tuple(sorted((p for p in collections.get(query.collection, ()) if all(
                query.bounds[i] <= p.bounds[i + 3] and p.bounds[i] <= query.bounds[i + 3]
                for i in range(3))), key=lambda p: p.name))
            bindings.append(Binding(query, matches))
        effective = replace(step, reads=list(dict.fromkeys([
            *step.reads, *(p.name for binding in bindings for p in binding.matches)])))
        effective._query_bindings = tuple(bindings)
        bound.append(effective)
    return bound


def manifest(step):
    """Only frozen query results, never the global catalogue. Paths are normalized when keyed."""
    if step.queries and step._query_bindings is None:
        raise ValueError(f'{step.name}: spatial queries must be resolved by the build graph')
    return {'schema': 1, 'intersection': 'inclusive', 'queries': {
        binding.query.name: {'collection': binding.query.collection, 'bounds': binding.query.bounds,
                             'matches': [{'name': p.name, 'owner': p.owner, 'bounds': p.bounds,
                                          'paths': [str(path) for path in p.paths]} for p in binding.matches]}
        for binding in step._query_bindings or ()}}


def verify_current(ctx, step, done, *, hasher=None):
    """Abort on catalogue drift; the current execution plan cannot safely add new producers."""
    from . import build, build_products
    catalogue = build_products.Catalogue(build.load_recipe(ctx.game).steps(ctx))
    current = catalogue.by_name.get(step.name)
    if current is not None:
        current = bind([current], catalogue.owners, catalogue=catalogue.steps)[0]
        catalogue.validate_dependencies(current)
    if (current is None or current.reads != step.reads or current.needs != step.needs
            or current.after != step.after or manifest(current) != manifest(step)):
        raise ValueError(f'{step.name}: spatial inputs changed; rerun the build to replan')
    # A producer's receipt is not proof that its output stayed unchanged while a consumer ran.
    checked = set()
    for binding in step._query_bindings:
        for match in binding.matches:
            if match.name in checked:
                continue
            checked.add(match.name)
            product = build_products.Product(match.name, match.paths)
            digest = build_products.identity(build_products.inventory(product, hasher=hasher))
            if done.get(f'product:{match.name}') != digest:
                raise ValueError(f'{step.name}: spatial product changed: {match.name}')
    return current
