"""Report material masters as JSON: blend mode, shading, two-sided, domain, parameters by kind, expressions and textures
(read-only `editor.run`, V2_EDITOR_READ_ONLY=1). The masters are the parents of the instances report_materials.py reads.

V2_REPORT_PACKAGES names the masters, whitespace separated ("/Game/Hippodrome/Materials/M_HD_Dirt ..."); V2_REPORT_OUT names
the JSON file, which must lie outside games/yorimichi_v2. Nothing is saved; build.py fails if any file changes.

Each row is keyed by the master's package path:
  blend_mode, shading_model, two_sided, domain   the master's own settings; a value the call could not read is null
  parameters   {"scalar": {name: default}, "vector": {name: [r, g, b, a]}, "texture": {name: texture path or null},
               "static_switch": {name: default}}: read from the parameter expressions, so a name appears only if the
               graph exposes it
  expressions  the number of expressions in the graph
  textures     the texture paths the graph samples or parameterises, sorted
  error        present only when that master could not be read; the other rows are still written

The parameter kinds come from the expression classes (MaterialExpressionScalarParameter and so on), not from
MaterialEditingLibrary name lists, so nothing is guessed: a missing property is written as null.
"""
import json
import os

import unreal as U

MARKER = 'V2 MASTERS REPORTED'
EAL = U.EditorAssetLibrary
GAME = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))

KINDS = {   # expression class name -> (parameter kind, the property holding its default)
    'MaterialExpressionScalarParameter': ('scalar', 'default_value'),
    'MaterialExpressionVectorParameter': ('vector', 'default_value'),
    'MaterialExpressionTextureSampleParameter2D': ('texture', 'texture'),
    'MaterialExpressionTextureObjectParameter': ('texture', 'texture'),
    'MaterialExpressionStaticSwitchParameter': ('static_switch', 'default_value'),
}
TEXTURE_CLASSES = ('MaterialExpressionTextureSample', 'MaterialExpressionTextureSampleParameter2D',
                   'MaterialExpressionTextureObjectParameter')


def split_packages(text):
    return [p for p in text.split() if p]


def report_target(target, game=GAME):
    """The output path, resolved, refused when it lies inside the game tree (as report_materials.py refuses it)."""
    resolved = os.path.realpath(os.path.abspath(target))
    root = os.path.realpath(game)
    if resolved == root or resolved.startswith(root + os.sep):
        raise ValueError(f'V2_REPORT_OUT {target!r} lies inside {root}; write the report outside the game tree')
    return resolved


def color(value):
    """A LinearColor-like value as [r, g, b, a], or None."""
    if value is None:
        return None
    try:
        return [float(value.r), float(value.g), float(value.b), float(value.a)]
    except AttributeError:
        try:
            return [float(v) for v in value]
        except TypeError:
            return None


def name_of(value):
    """A parameter name, or None."""
    return None if value is None else str(value)


def texture_path(texture):
    """The /Game path of a texture object, or None when unset."""
    if texture is None:
        return None
    try:
        return texture.get_path_name().split('.')[0]
    except AttributeError:
        return str(texture)


def describe(expressions):
    """Pure: from (class name, {property: value}) pairs, the parameters by kind, the expression count and the textures.
    A property a call could not read is None; a name is recorded once, with its first default."""
    parameters = {'scalar': {}, 'vector': {}, 'texture': {}, 'static_switch': {}}
    textures = set()
    for class_name, props in expressions:
        if class_name in KINDS:
            kind, prop = KINDS[class_name]
            name = name_of(props.get('parameter_name'))
            if name is None:
                continue
            value = props.get(prop)
            if kind == 'vector':
                value = color(value)
            elif kind == 'texture':
                value = texture_path(value)
            elif kind in ('scalar', 'static_switch'):
                value = None if value is None else (bool(value) if kind == 'static_switch' else float(value))
            parameters[kind].setdefault(name, value)
        if class_name in TEXTURE_CLASSES:
            path = texture_path(props.get('texture'))
            if path:
                textures.add(path)
    for kind in parameters:
        if kind == 'texture':
            textures.update(v for v in parameters[kind].values() if v)
    return {'parameters': parameters, 'textures': sorted(textures)}


def read_expressions(material):
    """(class name, {property: value}) for every expression of the master's graph."""
    out = []
    for expression in material.get_editor_property('expressions') or []:
        props = {}
        for prop in ('parameter_name', 'default_value', 'texture'):
            try:
                props[prop] = expression.get_editor_property(prop)
            except Exception:   # the class has no such property: recorded as absent, not guessed
                props[prop] = None
        out.append((type(expression).__name__, props))
    return out


def settings(material):
    """The master's own settings. Each is read by name; an unreadable one is None."""
    row = {}
    for key, prop in (('blend_mode', 'blend_mode'), ('shading_model', 'shading_model'), ('two_sided', 'two_sided'),
                      ('domain', 'material_domain')):
        try:
            value = material.get_editor_property(prop)
            row[key] = value if isinstance(value, bool) else str(value)
        except Exception:
            row[key] = None
    return row


def report(path):
    material = EAL.load_asset(path)
    if material is None:
        raise RuntimeError(f'{path}: no asset at this path')
    if material.get_class().get_name() != 'Material':
        raise RuntimeError(f'{path}: not a material master ({material.get_class().get_name()})')
    expressions = read_expressions(material)
    described = describe(expressions)
    row = settings(material)
    row.update(described)
    row['expressions'] = len(expressions)
    return row


def main():
    target = report_target(os.environ['V2_REPORT_OUT'])   # refused before anything is read or opened
    out = {}
    packages = split_packages(os.environ['V2_REPORT_PACKAGES'])
    for path in packages:
        try:
            out[path] = report(path)
        except Exception as exc:
            out[path] = {'error': repr(exc)}
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, 'w') as f:
        json.dump(out, f, indent=1, sort_keys=True)
    failed = sorted(p for p, row in out.items() if 'error' in row)
    U.log(f'{MARKER} {len(out)} rows errors={len(failed)}')


if __name__ == '__main__':
    main()
