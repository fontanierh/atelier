"""Actual Harbor query data equals the previous GLB-based query geometry."""
import argparse
from collections import Counter
import importlib.util
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
from atelier.model_files import regular_files  # noqa: E402
import region_query  # noqa: E402


def triangle_rows(triangles):
    result = Counter()
    for triangle in triangles:
        row = tuple(tuple(float(v) for v in point) for point in triangle)
        result[min(row[index:] + row[:index] for index in range(3))] += 1
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('baseline', 'rim', 'output'): parser.add_argument('--' + key, type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    root, baseline = real_directory(args.output), real_directory(args.baseline)
    if os.path.lexists(root): raise ValueError('Coastal query proof requires fresh evidence')
    previous = json.loads((baseline / 'result.json').read_text())
    assert previous['complete'] and previous['serialized_glb_corner_equality'] and previous['complete_runtime_policy_equal']
    controls = baseline / 'controls'
    names = regular_files(controls)
    assert len(names) == previous['pieces'] and all(Path(relative).suffix == '.glb' for relative in names)
    script = GAME / 'assets/vehicles/ferry/terminals/world_probe.py'
    region = GAME / 'world/regions/brinecove'
    params = GAME / 'assets/brinecove/export-parameters/Harbor.json'
    inputs = {Path(__file__), params, args.rim, baseline / 'result.json', *(controls / relative for relative in names)}
    for source in (script, script.with_name('site.py'), script.parent.parent / 'build.py',
                   region / 'plan_component.py', region / 'procedural/harbor.py'):
        inputs.update(local_imports(source, (GAME / 'world', GAME / 'world/regions')))
    def identities():
        result = {}
        for path in sorted(inputs):
            real_directory(path.parent)
            if path.is_symlink() or not path.is_file(): raise ValueError('Coastal query proof input must be regular')
            result[str(path)] = sha(path)
        return result
    before = identities()
    spec = importlib.util.spec_from_file_location('previous_ferry_mesh_query', script)
    old = importlib.util.module_from_spec(spec); spec.loader.exec_module(old)
    expected = Counter()
    for relative in sorted(names):
        old.clear_scene()
        expected.update(triangle_rows(old.triangles(old.import_file(controls / relative))))
    assert sum(expected.values()) == previous['triangles'] == 37352
    from brinecove.plan_component import main as plan
    plan(['--asset', 'Harbor', '--builder', 'harbor', '--context', str(params), '--rim', str(args.rim),
          '--paving-output', str(root / 'paving.json'), '--output', str(root / 'planned'),
          '--query-output', str(root / 'query.npz')])
    current = region_query.load(root / 'query.npz', owner='SM_BC_Harbor', stage='final')
    actual = triangle_rows(region_query.triangles(current))
    assert actual == expected, 'Explicit source query differs from the actual former GLB query geometry'
    assert identities() == before
    atomic_json(root / 'result.json', dict(complete=True, triangles=sum(actual.values()), pieces=previous['pieces'],
        exact_query_triangle_cycles=True, inputs=before,
        scope='actual coastal Harbor query geometry only; full ferry sweeps/native receiving/traversal remain pending'))
    print('COASTAL SOURCE QUERY CANARY COMPLETE', flush=True)


if __name__ == '__main__': main()
