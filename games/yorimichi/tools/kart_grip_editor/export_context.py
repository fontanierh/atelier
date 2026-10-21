"""Guarded Blender refresh of the kart alone; never regenerate an approved character skin or pose."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

import bpy

GAME = Path(__file__).resolve().parents[2]
ROOT = GAME.parents[1]
KART = GAME / 'assets/vehicles/kart'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--baseline-build', type=Path)
args = parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
sys.path.insert(0, str(KART))
sys.argv = [sys.argv[0], '--', 'cairo', str(ROOT / 'build/yorimichi/kart-polish')]
import preview as p  # noqa: E402


def load_builder(name, source=None):
    spec = importlib.util.spec_from_file_location(name, KART / 'build.py')
    module = importlib.util.module_from_spec(spec)
    if source:
        exec(compile(source.read_text(), str(KART / 'build.py'), 'exec'), module.__dict__)
    else:
        spec.loader.exec_module(module)
    return module


def main():
    current = load_builder('kart_polished')
    report = {}
    if args.baseline_build:
        baseline = load_builder('kart_approved', args.baseline_build)
        for name in ('kart', 'seat', 'wheel', 'steering_wheel'):
            before, after = getattr(baseline, name)(), getattr(current, name)()
            expected, actual = current.geometry_hash(before), current.geometry_hash(after)
            assert expected == actual, f'{name}: polish moved an approved surface'
            report[after.name] = actual
            print('GEOMETRY IDENTICAL', after.name, actual, flush=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    p.SCALE = 1.
    objects = p.import_kart()
    objects = [ob for ob in objects if not ob.name.startswith(('SM_Kart_SteeringWheel', 'PreviewColumn'))]
    p.rig.select(objects, objects[0], reveal=True)
    target = ROOT / 'build/yorimichi/kart-grip-editor/kart.glb'
    temporary = target.with_name('kart.next.glb')
    bpy.ops.export_scene.gltf(filepath=str(temporary), export_format='GLB', use_selection=True,
                              export_yup=False, export_animations=False)
    temporary.replace(target)
    (ROOT / 'build/yorimichi/kart-polish/geometry-proof.json').write_text(json.dumps(report, indent=2)+'\n')
    print('KART CONTEXT REFRESH COMPLETE; character skins and poses untouched', flush=True)


if __name__ == '__main__':
    main()
