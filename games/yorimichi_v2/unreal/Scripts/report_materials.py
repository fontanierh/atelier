"""Report material instances as JSON: parent, saved overrides and effective parameter values (read-only `editor.run`).

Run with V2_EDITOR_READ_ONLY=1 through `atelier build yorimichi_v2 editor.run`: no claim is needed, every save is refused
and build.py fails if any file changes. V2_REPORT_PACKAGES names the instances, whitespace separated
("/Game/Japan/Materials/MI_Bark ..."); V2_REPORT_OUT names the JSON file, which must lie outside games/yorimichi_v2.

Each row is keyed by the instance's package path:
  parent     the parent's path name
  overrides  the parameters the instance itself saves: {"scalar": {name: value}, "vector": {name: [r, g, b, a]},
             "texture": {name: texture path, or null}}
  effective  the same three maps for every parameter the parent exposes, with the value the instance renders
  error      present only when that instance could not be read; the other rows are still written
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


def report(path):
    inst = EAL.load_asset(path)
    if not isinstance(inst, U.MaterialInstanceConstant):
        return {'error': f'not a material instance: {path}'}
    parent = inst.get_editor_property('parent')
    if parent is None:
        return {'error': f'{path} has no parent'}
    return dict(parent=_path(parent), overrides=_overrides(inst), effective=_effective(inst, parent))


def main():
    packages = split_packages(os.environ['V2_REPORT_PACKAGES'])
    out = {}
    for path in packages:
        try:   # one unreadable instance is reported, not fatal to the rest
            out[path] = report(path)
        except Exception as exc:
            out[path] = {'error': repr(exc)}
    target = os.environ['V2_REPORT_OUT']
    os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
    with open(target, 'w') as f:
        json.dump(out, f, indent=1, sort_keys=True)
    missing, failed = check_coverage(out, packages)
    U.log(f'{MARKER} {len(out)} rows missing={len(missing)} errors={len(failed)}')


if __name__ == '__main__':
    main()
