"""Wiring digest of a material master, and the rule that accepts a rebuilt master only when it equals the saved original.

The digest records what a graph is, not how Unreal happens to list it: each expression's class and its own settings
(parameter name, default, texture, sampler, constants), each input connection (source expression and output, destination
expression and input), each material property connection, and the blend mode, shading model and two-sided flag.
Expression indices and object names are not recorded, since a rebuild in another package has other names. The three
lists are compared as multisets, so their order does not matter.

The pure functions (canonical, accept) run without the Unreal editor, and the tests use them. read() needs the editor and
is the only part that touches it. A part that cannot be read makes the whole digest an error, which refuses the master:
a partial digest never matches.
"""
import collections
import json

try:
    import unreal as U
except ImportError:   # outside the editor only the pure functions are usable
    U = None

SETTINGS = ('blend_mode', 'shading_model', 'two_sided')
PROPERTY_PINS = ('MP_BASE_COLOR', 'MP_NORMAL', 'MP_ROUGHNESS', 'MP_METALLIC', 'MP_SPECULAR', 'MP_EMISSIVE_COLOR',
                 'MP_OPACITY', 'MP_OPACITY_MASK', 'MP_AMBIENT_OCCLUSION', 'MP_WORLD_POSITION_OFFSET')
EXPRESSION_PROPERTIES = ('parameter_name', 'default_value', 'r', 'constant', 'const_a', 'const_b', 'texture',
                         'sampler_type', 'code', 'coordinate_index', 'output_type', 'data_index', 'const_default_value')
LISTS = ('expressions', 'connections', 'property_connections')


def _norm(value):
    """A canonical JSON value: floats to six places, lists element by element, anything else as text."""
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, (list, tuple)):
        return [_norm(v) for v in value]
    return str(value)


def canonical(digest):
    """Pure: the digest with its settings normalised and each list sorted, so no order Unreal chose matters."""
    return {'settings': {k: _norm(v) for k, v in sorted(digest['settings'].items())},
            'expressions': sorted(digest['expressions']),
            'connections': sorted(digest['connections']),
            'property_connections': sorted(digest['property_connections'])}


def accept(saved, rebuilt):
    """@cc [owner:fontanierh,label:correctness] master-digest-equals-saved
    A rebuilt master is accepted only when its wiring digest equals the saved original's, with nothing missing on either side.
    A digest that failed to read refuses. Returns the differences: empty exactly when the rebuilt master is accepted."""
    for label, digest in (('saved original', saved), ('rebuilt master', rebuilt)):
        if 'error' in digest:
            return [f'{label} could not be read: {digest["error"]}']
    a, b = canonical(saved), canonical(rebuilt)
    problems = []
    for key in sorted(set(a['settings']) | set(b['settings'])):
        if a['settings'].get(key) != b['settings'].get(key):
            problems.append(f'{key}: saved {a["settings"].get(key)!r}, rebuilt {b["settings"].get(key)!r}')
    for key in LISTS:
        left, right = collections.Counter(a[key]), collections.Counter(b[key])
        for text in sorted((left - right).elements()):
            problems.append(f'{key} only in the saved original: {text}')
        for text in sorted((right - left).elements()):
            problems.append(f'{key} only in the rebuilt master: {text}')
    return problems


def _value(value):
    if hasattr(value, 'get_path_name'):
        return value.get_path_name().split('.')[0]
    if hasattr(value, 'r') and hasattr(value, 'a'):
        return [float(value.r), float(value.g), float(value.b), float(value.a)]
    return value


def _expression_text(expression):
    """The class and its own settings, as canonical JSON. A property the class does not have is absent, on both sides alike."""
    props = {}
    for prop in EXPRESSION_PROPERTIES:
        try:
            value = expression.get_editor_property(prop)
        except Exception:
            continue
        props[prop] = _norm(_value(value))
    return json.dumps({'class': type(expression).__name__, 'props': props}, sort_keys=True)


def _digest(material):
    MEL = U.MaterialEditingLibrary
    settings = {}
    for key in SETTINGS:
        value = material.get_editor_property(key)
        settings[key] = value if isinstance(value, bool) else str(value)
    expressions = list(material.get_editor_property('expressions') or [])
    text = {}
    for expression in expressions:
        text[expression.get_path_name()] = _expression_text(expression)

    def named(expression):
        return text.get(expression.get_path_name()) or _expression_text(expression)

    connections = []
    for expression in expressions:
        for index, wired in enumerate(MEL.get_inputs_for_material_expression(expression)):
            source = wired.expression
            if source is None:
                continue
            outputs = MEL.get_outputs_for_material_expression(source)
            out = str(outputs[wired.output_index].output_name) if wired.output_index < len(outputs) else ''
            pin = str(wired.input_name) or f'#{index}'
            connections.append(f'{named(source)}.{out} -> {named(expression)}.{pin}')
    property_connections = []
    for pin in PROPERTY_PINS:
        prop = getattr(U.MaterialProperty, pin)
        node = MEL.get_material_property_input_node(material, prop)
        if node is None:
            continue
        out = MEL.get_material_property_input_node_output_name(material, prop)
        property_connections.append(f'{pin} <- {named(node)}.{out}')
    return {'settings': settings, 'expressions': [text[k] for k in sorted(text)],
            'connections': connections, 'property_connections': property_connections}


def read(material):
    """The wiring digest of a loaded material master, or {'error': ...} when any part of it cannot be read."""
    try:
        return _digest(material)
    except Exception as error:   # an unreadable part makes the digest unusable; a partial digest never matches
        return {'error': repr(error)}


def compare_reports(saved, rebuilt):
    """Pure: two report_masters.py outputs ({package: row}) compared per package by accept(). A package in only one report,
    or a row without a wiring digest, is a problem. Returns {package: [problems]}; accepted when the list is empty."""
    missing = {'error': 'no wiring digest in the row'}
    out = {}
    for package in sorted(set(saved) | set(rebuilt)):
        if package not in saved or package not in rebuilt:
            side = 'rebuilt' if package not in rebuilt else 'saved'
            out[package] = [f'missing from the {side} report']
            continue
        out[package] = accept(saved[package].get('wiring', missing), rebuilt[package].get('wiring', missing))
    return out


def main(argv=None):
    """Compare two report files: `master_digest.py SAVED_REPORT.json REBUILT_REPORT.json`. Exit 0 only when every package is accepted."""
    import sys
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print('usage: master_digest.py SAVED_REPORT.json REBUILT_REPORT.json', file=sys.stderr)
        return 2
    with open(argv[0]) as f:
        saved = json.load(f)
    with open(argv[1]) as f:
        rebuilt = json.load(f)
    result = compare_reports(saved, rebuilt)
    for package, problems in result.items():
        print(('accepted ' if not problems else 'DIFFERS  ') + package)
        for problem in problems:
            print('    ' + problem)
    return 0 if all(not problems for problems in result.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
