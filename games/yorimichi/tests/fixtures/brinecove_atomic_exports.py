"""Compare actual coastal Harbor finishing and serialized exports against the original owner."""
import argparse
import json
import os
from pathlib import Path
import sys

import bpy

GAME = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(GAME / 'world'))
import yori  # noqa: E402,F401
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.build_inputs import local_imports  # noqa: E402
from atelier.export_manifest import real_directory, sha  # noqa: E402
from random_stream import positioned  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'native'))
from glb_corners import read as corners  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    root, reference = real_directory(args.output), real_directory(args.reference)
    if os.path.lexists(root): raise ValueError('Coastal export proof requires fresh evidence')
    region = GAME / 'world/regions/brinecove'
    params = GAME / 'assets/brinecove/export-parameters/Harbor.json'
    rim_path, reference_result = reference / 'rim.json', reference / 'result.json'
    inputs = {rim_path, reference_result, params, Path(__file__), Path(corners.__code__.co_filename)}
    for script in ('build.py', 'plan_component.py'):
        inputs.update(local_imports(region / script, (GAME / 'world', GAME / 'world/regions')))
    inputs.update(local_imports(region / 'procedural/harbor.py', (GAME / 'world', GAME / 'world/regions')))
    inputs.update(local_imports(GAME / 'world/export_region_piece.py', (GAME / 'world', GAME / 'world/regions')))
    inputs.update(GAME / 'assets/brinecove/models' / name for name in (
        'pirate-queen-statue.glb', 'galleon-figurehead.glb', 'ships-wheel.glb',
        'galleon-hull.glb', 'galleon-hull.provenance.json'))
    def identities():
        result = {}
        for path in sorted(inputs):
            real_directory(path.parent)
            if path.is_symlink() or not path.is_file(): raise ValueError('Coastal proof input is not regular')
            result[str(path)] = sha(path)
        return result
    before = identities()
    reference_value = json.loads(reference_result.read_text())
    assert reference_value['complete'] and reference_value['exact_builder_fields']
    root.mkdir(parents=True)
    from brinecove import build as original, modules, rocks
    from brinecove.plan_component import main as current, read_context
    from brinecove.rim_schema import read
    from atelier.model_export import mesh_object, export
    from export_region_piece import main as atomic_export
    from region_mesh_parts import validate
    rim, _ = read(json.loads(rim_path.read_text()))
    context = read_context(params, 'Harbor')
    original.modules.RNG.setstate(positioned(context['seed'], context['prefix_words']).getstate())
    modules.FLAT_PAVING.clear()
    settled = original.settle(rim)
    def final_ground(x, y):
        value = settled(x, y)[1]
        return original.L.ground(x, y) if value is None else value
    rocks.FINAL = final_ground
    builder = modules.harbor()
    import hashlib
    raw = hashlib.sha256(json.dumps(vars(builder), sort_keys=True, allow_nan=False,
                                    separators=(',', ':')).encode()).hexdigest()
    assert raw == reference_value['assets']['Harbor']['sha256'], 'Original Harbor source differs from retained raw proof'
    parts, outside, drowned, degenerate = original.split(builder, 'Harbor', settled)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    materials = original.blender_materials()
    expected, roles = {}, {}
    for (_, _, soft, _), part in sorted(parts.items()):
        obj = mesh_object(part, materials)
        target = root / 'controls' / (part.name + '.glb')
        target.parent.mkdir(parents=True, exist_ok=True)
        assert sum(len(f) - 2 for f in part.faces) <= 32768
        export(obj, target)
        expected[part.name] = corners(target)
        water = getattr(part, 'parent_water', all(s.startswith(
            ('water', 'mist', 'spray', 'foam', 'waterfall')) for s in part.mats))
        roles[part.name] = dict(component='Harbor', collision=not soft, shadow=not water, cull_cm=120000)
        bpy.data.objects.remove(obj, do_unlink=True)
        print('COASTAL BASELINE EXPORT', part.name, flush=True)
    current(['--asset', 'Harbor', '--builder', 'harbor', '--context', str(params),
             '--rim', str(rim_path), '--paving-output', str(root / 'paving.json'), '--output', str(root / 'plan')])
    value = validate(root / 'plan')
    assert {row['name'] for row in value['pieces']} == set(expected)
    assert value['metadata'] == roles
    assert value['diagnostics'] == dict(outside=outside, drowned=drowned, degenerate=degenerate,
                                       raw_triangles=sum(len(f) - 2 for f in builder.faces))
    for row in value['pieces']:
        output = root / 'exports' / row['name']
        argv = ['--input', str(root / 'plan' / row['payload']), '--output', str(output), '--format', '.glb']
        atomic_export(argv)
        target = output / (row['name'] + '.glb')
        assert corners(target) == expected[row['name']], (row['name'], 'serialized triangle/corner/material channels changed')
        print('COASTAL ATOMIC EXPORT MATCH', row['name'], flush=True)
    assert identities() == before, 'Source or retained proof changed during coastal export validation'
    atomic_json(root / 'result.json', dict(complete=True, raw_reference_equal=True,
        serialized_glb_corner_equality=True, complete_runtime_policy_equal=True,
        pieces=len(expected), triangles=value['source_triangles'], source_identities=before,
        scope='actual Harbor source finishing and serialized geometry only; Unreal receiving remains pending'))
    print('COASTAL ATOMIC EXPORT CANARY COMPLETE', flush=True)


if __name__ == '__main__': main()
