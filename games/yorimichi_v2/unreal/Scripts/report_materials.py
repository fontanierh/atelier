"""Report material instances as JSON: parent, saved overrides and effective parameter values (read-only `editor.run`).

Run with V2_EDITOR_READ_ONLY=1 through `atelier build yorimichi_v2 editor.run`: no claim is needed, every save is refused
and build.py fails if any file changes. V2_REPORT_PACKAGES names the instances, whitespace separated
("/Game/Japan/Materials/MI_Bark ..."); V2_REPORT_OUT names the JSON file, which must lie outside games/yorimichi_v2.

Each row is keyed by the instance's package path:
  parent     the parent's path name
  overrides  the parameters the instance itself saves: {"scalar": {name: value}, "vector": {name: [r, g, b, a]},
             "texture": {name: texture path, or null}}
  effective  the same three maps for every parameter the parent exposes, with the value the instance renders
  switches   every bHas* static switch the instance or its parent stores: {name: {"override": bool, "value": the
             value the instance stores (inherited when not overridden), "parent": the parent's value, "effective":
             the value the instance renders}}; a value a call could not read is null (never a guess)
  base       every base-property override the instance sets: {name: value}, blend_mode by its BLEND_* name
  error      present only when that instance could not be read; the other rows are still written

The vector rows carry the alpha channel too: an EmissiveFactor is reported as [r, g, b, a], so its alpha is read here.
"""
import json
import os

import unreal as U

MARKER = 'V2 MATERIALS REPORTED'
EAL = U.EditorAssetLibrary
MEL = U.MaterialEditingLibrary
PLACES = 6


def round_value(x):
    return round(float(x), PLACES)


def split_packages(text):
    """Pure: V2_REPORT_PACKAGES is a whitespace-separated list of package paths."""
    return text.split()


GAME = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))


def report_target(target, game=GAME):
    """Pure: the resolved output path, refused inside the game tree (a claim-free read must not write a tracked file or a
    Content package; yorimichi-v2-single-writer). Symlinks are resolved first, so a link that points into the tree is
    refused too."""
    resolved = os.path.realpath(os.path.abspath(target))
    root = os.path.realpath(game)
    if resolved == root or resolved.startswith(root + os.sep):
        raise ValueError(f'V2_REPORT_OUT {target!r} lies inside {root}; write the report outside the game tree')
    return resolved


def check_coverage(report, expected):
    """Pure: the expected packages that have no row, and the rows that carry an error. Nothing else is judged."""
    missing = sorted(p for p in expected if p not in report)
    failed = sorted(p for p, row in report.items() if 'error' in row)
    return missing, failed


def _path(obj):
    return obj.get_path_name() if obj else None


def _name(param):
    return str(param.get_editor_property('parameter_info').get_editor_property('name'))


def _rgba(c):
    return [round_value(c.r), round_value(c.g), round_value(c.b), round_value(c.a)]


def _overrides(inst):
    return dict(
        scalar={_name(p): round_value(p.get_editor_property('parameter_value'))
                for p in inst.get_editor_property('scalar_parameter_values')},
        vector={_name(p): _rgba(p.get_editor_property('parameter_value'))
                for p in inst.get_editor_property('vector_parameter_values')},
        texture={_name(p): _path(p.get_editor_property('parameter_value'))
                 for p in inst.get_editor_property('texture_parameter_values')})


def _effective(inst, parent):
    scalar = {str(n): round_value(MEL.get_material_instance_scalar_parameter_value(inst, n))
              for n in MEL.get_scalar_parameter_names(parent)}
    vector = {str(n): _rgba(MEL.get_material_instance_vector_parameter_value(inst, n))
              for n in MEL.get_vector_parameter_names(parent)}
    texture = {str(n): _path(MEL.get_material_instance_texture_parameter_value(inst, n))
               for n in MEL.get_texture_parameter_names(parent)}
    return dict(scalar=scalar, vector=vector, texture=texture)


SWITCH_PREFIX = 'bHas'


def _flag(value):
    return bool(value) if value is not None else None


def _switch_entries(stored):
    """Pure given the stored entries (each with name, override, value): the bHas* names and their own values."""
    return {name: {'override': bool(override), 'value': _flag(value)}
            for name, override, value in stored if name.startswith(SWITCH_PREFIX)}


def _stored_switches(static_set):
    """(name, override, value) of each switch in a static parameter set, read through the editor's properties."""
    rows = []
    for p in static_set.get_editor_property('static_switch_parameters'):
        override = p.get_editor_property('override') if _has(p, 'override') else p.get_editor_property('b_override')
        rows.append((_name(p), override, p.get_editor_property('value')))
    return rows


def _has(obj, name):
    try:
        obj.get_editor_property(name)
        return True
    except Exception:
        return False


def _effective_switch(inst, name):
    try:
        got = MEL.get_material_instance_static_switch_parameter_value(inst, name)
        return _flag(got[0] if isinstance(got, tuple) else got)
    except Exception:
        return None


def _stored(material):
    """The switches a material's stored static parameter set holds, or {} where UE 5.8's Python does not expose
    `static_parameters` on the class (MaterialInstanceConstant does not)."""
    try:
        return _switch_entries(_stored_switches(material.get_editor_property('static_parameters')))
    except Exception:
        return {}


def _switch_names(material):
    try:
        return {str(n) for n in MEL.get_static_switch_parameter_names(material)}
    except Exception:
        return set()


def _parent_switch(parent, name):
    """The parent's value: an instance parent reads like the instance, a base material reads its default."""
    if isinstance(parent, U.MaterialInstance):
        return _effective_switch(parent, name)
    try:
        return _flag(MEL.get_material_default_static_switch_parameter_value(parent, name))
    except Exception:
        return None


def _switches(inst, parent):
    """Every bHas* switch of the instance and of its parent, with the instance's own override and value, the parent's
    value and the effective value. Each read is independent: a failed one is null, the rest are still reported.
    Where the stored set is not readable, `override` is null and `value` is the effective value; an effective value
    that differs from the parent's is then the evidence of an override."""
    own = _stored(inst)
    inherited = _stored(parent)
    names = {n for n in _switch_names(inst) | _switch_names(parent) | set(own) | set(inherited)
             if n.startswith(SWITCH_PREFIX)}
    out = {}
    for name in sorted(names):
        effective = _effective_switch(inst, name)
        base = inherited.get(name, {}).get('value')
        if base is None:
            base = _parent_switch(parent, name)
        mine = own.get(name, {'override': None if not own else False, 'value': None if own else effective})
        out[name] = dict(override=mine['override'], value=mine['value'], parent=base, effective=effective)
    return out


def _base(inst):
    """{name: value} of each base-property override the instance sets (blend mode by name); the same read import_asset.py
    makes after a write. A flag whose value this Python cannot read reports null, never a guess."""
    overrides = inst.get_editor_property('base_property_overrides')
    out = {}
    for flag in sorted(n for n in dir(overrides) if n.startswith('override_')):
        if not overrides.get_editor_property(flag):
            continue
        name = flag[len('override_'):]
        try:
            value = overrides.get_editor_property(name)
        except Exception:
            out[name] = None
            continue
        if isinstance(value, float):
            value = round_value(value)
        elif not isinstance(value, bool) and getattr(value, 'name', None) is not None:
            value = str(value.name)
        out[name] = value
    return out


def report(path):
    inst = EAL.load_asset(path)
    if not isinstance(inst, U.MaterialInstanceConstant):
        return {'error': f'not a material instance: {path}'}
    parent = inst.get_editor_property('parent')
    if parent is None:
        return {'error': f'{path} has no parent'}
    return dict(parent=_path(parent), overrides=_overrides(inst), effective=_effective(inst, parent),
                switches=_switches(inst, parent), base=_base(inst))


def main():
    target = report_target(os.environ['V2_REPORT_OUT'])   # refused before anything is read or opened
    packages = split_packages(os.environ['V2_REPORT_PACKAGES'])
    out = {}
    for path in packages:
        try:   # one unreadable instance is reported, not fatal to the rest
            out[path] = report(path)
        except Exception as exc:
            out[path] = {'error': repr(exc)}
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, 'w') as f:
        json.dump(out, f, indent=1, sort_keys=True)
    missing, failed = check_coverage(out, packages)
    U.log(f'{MARKER} {len(out)} rows missing={len(missing)} errors={len(failed)}')


if __name__ == '__main__':
    main()
