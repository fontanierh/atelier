"""The parameters of a material parameter collection, and the rule that accepts a generated collection only when it is
exactly its generator's parameters with every saved parameter's id kept.

A material reads a collection parameter by the collection and the parameter's id (a GUID), not its name alone, so a
collection rebuilt with fresh ids would leave every material that reads it pointing at nothing until it is compiled again.
The generator (see_through.py collection(create=True)) therefore never recreates a collection: it appends the parameters
the saved one lacks and keeps the others with their ids. These checks hold the importer to that.

The pure functions (problems_before, accept) run without the Unreal editor, and the tests use them. read() needs the
editor and is the only part that touches it.
"""
import re

try:
    import unreal as U
except ImportError:   # outside the editor only the pure functions are usable
    U = None

ZERO_ID = '00000000000000000000000000000000'
ID_TEXT = re.compile(r'(?:^|[(,])Id=([0-9A-Fa-f]{32})(?=[,)])')


def _color(value):
    return [float(value.r), float(value.g), float(value.b), float(value.a)]


def id_of_text(text):
    """The Id of a parameter from its exported struct text, e.g. '(...,ParameterName="Focus",Id=21734E42...)'. Python
    cannot read the protected Id property, but the struct's own text export writes it."""
    found = ID_TEXT.findall(text)
    if len(found) != 1:
        raise RuntimeError(f'no single Id in {text[:120]!r}')
    return found[0].upper()


def _id(parameter):
    return id_of_text(parameter.export_text())


def read(collection):
    """{'vectors': [{name, default, id}], 'scalars': [{name, default, id}]}, in the collection's own order."""
    out = {}
    for prop, key, value in (('vector_parameters', 'vectors', _color), ('scalar_parameters', 'scalars', float)):
        out[key] = [{'name': str(p.get_editor_property('parameter_name')),
                     'default': value(p.get_editor_property('default_value')), 'id': _id(p)}
                    for p in collection.get_editor_property(prop)]
    return out


def expected_of(vectors, scalars=()):
    """The generator's parameters as {'vectors': {name: [r, g, b, a]}, 'scalars': {name: value}}."""
    return {'vectors': {name: [float(v) for v in value] for name, value in vectors},
            'scalars': {name: float(value) for name, value in scalars}}


def _rows_problems(expected, rows, kind, *, complete):
    problems = []
    names = [row['name'] for row in rows]
    for name in sorted({n for n in names if names.count(n) > 1}):
        problems.append(f'{kind} parameter {name} is listed {names.count(name)} times')
    for row in rows:
        if row['name'] not in expected:
            problems.append(f'{kind} parameter {row["name"]} is not one of the generator\'s')
        elif row['default'] != expected[row['name']]:
            problems.append(f'{kind} parameter {row["name"]} defaults to {row["default"]}, '
                            f'the generator gives {expected[row["name"]]}')
    if complete:
        for name in expected:
            if name not in names:
                problems.append(f'{kind} parameter {name} is missing')
    return problems


def problems_before(expected, saved):
    """@cc [owner:fontanierh,label:correctness] parameter-collection-only-appends
    What refuses a collection before the generator touches it: a parameter the generator does not make, a default it
    would not give, or a repeated name. The generator only appends missing parameters, so it can never repair these and
    the importer refuses before any write. A collection that does not exist yet (saved None) has no problems."""
    if saved is None:
        return []
    return (_rows_problems(expected['vectors'], saved['vectors'], 'vector', complete=False)
            + _rows_problems(expected['scalars'], saved['scalars'], 'scalar', complete=False))


def accept(expected, saved, built):
    """@cc [owner:fontanierh,label:correctness] parameter-collection-ids-kept
    Accept a written collection only when its parameters are exactly the generator's, with the generator's defaults,
    each id non-zero and distinct, and every parameter of the saved original (if there was one) still under its own id:
    a material that reads the original keeps reading the same parameter. [] when accepted."""
    problems = (_rows_problems(expected['vectors'], built['vectors'], 'vector', complete=True)
                + _rows_problems(expected['scalars'], built['scalars'], 'scalar', complete=True))
    rows = built['vectors'] + built['scalars']
    ids = [row['id'] for row in rows]
    for row in rows:
        if row['id'] in ('', ZERO_ID):
            problems.append(f'parameter {row["name"]} has no id')
        elif ids.count(row['id']) > 1:
            problems.append(f'parameter {row["name"]} shares its id {row["id"]}')
    if saved is not None:
        now = {(kind, row['name']): row['id'] for kind in ('vectors', 'scalars') for row in built[kind]}
        for kind in ('vectors', 'scalars'):
            for row in saved[kind]:
                if now.get((kind, row['name'])) != row['id']:
                    problems.append(f'parameter {row["name"]} changed id {row["id"]} -> {now.get((kind, row["name"]))}')
    return problems
