"""Actual city source topology/query parity before any mesh export exists."""
import argparse
import json
import os
from pathlib import Path
import sys

import bpy
import numpy as np
from mathutils import Matrix

GAME = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(GAME / 'world'))
import yori  # noqa: E402,F401
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.build_inputs import local_imports  # noqa: E402
from atelier.build_cache import copy_file  # noqa: E402
from atelier.export_manifest import real_directory, sha  # noqa: E402
from mesh_pieces import capture, create_mesh  # noqa: E402
import region_query  # noqa: E402
import source_geometry  # noqa: E402
from hidamari.plan_asset import main as plan  # noqa: E402
from hidamari import source_context  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--donor', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    root = real_directory(args.output)
    if os.path.lexists(root): raise ValueError('Source/query proof requires fresh evidence')
    region = GAME / 'world/regions/hidamari'
    context = GAME / 'assets/hidamari/export-parameters/HD_Harbor.json'
    sources = {Path(__file__), *source_context.inputs(context, 'HD_Harbor')}
    donor = real_directory(args.donor)
    inputs = ('world.json', 'heightmap.npy', 'farhills.npy', 'megapark/trail.json',
              'craterpark/v2/geometry.npz', 'terrain/FarHills/final.npz')
    for relative in inputs:
        path = donor / relative
        real_directory(path.parent)
        if path.is_symlink() or not path.is_file(): raise ValueError('Query proof requires regular declared inputs')
        sources.add(path)
    for script in (region / 'plan_asset.py', region / 'logical/HD_Harbor.py'):
        sources.update(local_imports(script, (GAME / 'world', GAME / 'world/regions')))
    def identities():
        return {str(path): sha(path) for path in sorted(sources)}
    before = identities()
    for relative in inputs:
        target = root / 'data' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        copy_file(donor / relative, target)
        assert sha(target) == before[str(donor / relative)]
    yori.OUT = root / 'data'
    plan(['--asset', 'HD_Harbor', '--context', str(context), '--output', str(root / 'planned'),
          '--query-output', str(root / 'query.npz'), '--source-output', str(root / 'source')])
    original = bpy.data.objects['HD_Harbor']
    expected = capture(original.data)
    whole = source_geometry.read(root / 'source', owner='HD_Harbor')
    assert whole['triangles'] == 190920
    assert whole['matrix'] == [list(row) for row in original.matrix_world]
    assert whole['slots'] == [material.name for material in expected['slots']]
    whole['slots'] = expected['slots']
    mesh = create_mesh('SourceReadback', whole)
    rebuilt = bpy.data.objects.new('SourceReadback', mesh)
    rebuilt.matrix_world = Matrix(whole['matrix'])
    current = capture(mesh)
    for key in ('positions', 'starts', 'counts', 'vertex_indices', 'normals', 'materials', 'smooth'):
        assert current[key].tobytes() == expected[key].tobytes(), key
    assert current['selection'] == expected['selection']
    for key in ('uvs', 'colours'):
        for a, b in zip(expected[key], current[key]):
            assert a[:-1] == b[:-1] and a[-1].tobytes() == b[-1].tobytes(), (key, a[0])
    queries = region_query.load(root / 'query.npz', owner='HD_Harbor', stage='raw')
    direct = region_query.triangles([region_query.capture(original)])
    actual = region_query.triangles(queries, roles=('render',))
    assert actual.tobytes() == direct.tobytes()
    reconstructed = region_query.triangles([region_query.capture(rebuilt)])
    assert reconstructed.tobytes() == direct.tobytes()
    assert len(queries) == 1 + len(whole['collisions'])
    assert identities() == before
    atomic_json(root / 'result.json', dict(complete=True, triangles=len(direct),
        exact_topology_corner_channels=True, exact_actual_triangulation=True, inputs=before,
        packets=len(json.loads((root / 'source/plan.json').read_text())['pieces']),
        scope='actual raw Harbor source/query data; final ferry cut and native receiving remain pending'))
    print('CITY SOURCE QUERY CANARY COMPLETE', flush=True)


if __name__ == '__main__': main()
