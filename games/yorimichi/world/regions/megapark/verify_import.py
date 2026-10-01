"""Compare every built Unreal triangle against the committed map, despite reordering.

Run with project Python after the Unreal import. Requires NumPy, no Unreal or
retail decoder. Geometry dumps come from actual built LOD vertex/index buffers.
"""
from collections import defaultdict
from itertools import product
from pathlib import Path
import json
import sys
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import yori
from megapark import plants, sign

SOURCE = yori.ASSETS/'megapark'
OUT = yori.OUT/'megapark'
TOLERANCE = .0005  # original metres; 0.05 cm in Unreal


def expected_triangles(entry, source):
    if entry.get('source_asset_id'):
        model = next(m for m in source['models'] if m['asset_id'] == entry['source_asset_id'])
        parts = []
        with np.load(SOURCE/model['npz'], allow_pickle=False) as arrays:
            for p in model['meshes']:
                if plants.is_foliage(p):
                    continue   # replaced by island trees (build.py)
                if sign.is_letters(model, p):
                    parts.append(letters())   # SHARKS -> 寄り道 (build.py)
                    continue
                i = p['index']
                parts.append(arrays[f'vertices_{i}'][arrays[f'faces_{i}']])
        triangles = np.concatenate(parts).astype('f8')
        valid = np.linalg.norm(np.cross(triangles[:,1]-triangles[:,0], triangles[:,2]-triangles[:,0]), axis=1) > 1e-12
        assert int((~valid).sum()) == entry['degenerate_faces_removed']
        return triangles[valid]
    model = next(m for m in source['collision'] if m['id'] == entry['source_id'])
    with np.load(SOURCE/model['npz'], allow_pickle=False) as arrays:
        triangles = arrays['triangles']
    if model['id'] == sign.SECTION:
        triangles = np.concatenate([triangles[~sign.letters_mask(triangles)], letters().astype(triangles.dtype)])
    return triangles


def letters():
    with np.load(OUT/'letters.npz', allow_pickle=False) as arrays:
        return arrays['triangles']


def compare(entry, original):
    actual = np.fromfile(OUT/'imported-geometry'/f"{entry['name']}.bin", dtype='<f8').reshape(-1,3,3)
    actual = actual[:,:,[0,2,1]]/100.
    assert len(actual) == len(original), entry['name']
    points, source_indices = np.unique(original.reshape(-1,3), axis=0, return_inverse=True)
    imported, actual_indices = np.unique(actual.reshape(-1,3), axis=0, return_inverse=True)
    buckets = defaultdict(list)
    for i, key in enumerate(np.floor(points/TOLERANCE).astype('i8')):
        buckets[tuple(key)].append(i)
    shifts = list(product((-1,0,1), repeat=3))
    mapping = np.empty(len(imported), dtype='i8'); maximum = 0.
    for i, p in enumerate(imported):
        key = np.floor(p/TOLERANCE).astype('i8')
        candidates = []
        for shift in shifts:
            candidates.extend(buckets.get(tuple(key+shift), ()))
        assert candidates, (entry['name'], 'New vertex', p)
        differences = points[candidates].astype('f8')-p
        distances = np.einsum('ij,ij->i', differences, differences)
        nearest = int(np.argmin(distances)); error = float(np.sqrt(distances[nearest]))
        assert error < TOLERANCE, (entry['name'], 'Moved vertex', p, error)
        mapping[i] = candidates[nearest]; maximum = max(maximum, error)
    # Compare triangle multisets, not only vertices or bounding boxes. FBX may
    # reorder sections and duplicate/weld UV seams; those do not change geometry.
    def ordered(indices):
        triangles = np.sort(indices.reshape(-1,3), axis=1)
        return triangles[np.lexsort(triangles.T[::-1])]
    assert np.array_equal(ordered(source_indices), ordered(mapping[actual_indices])), (entry['name'], 'Changed triangle connectivity')
    return {'name': entry['name'], 'triangles': len(actual), 'maximum_vertex_error_cm': maximum*100.}


def main():
    source = json.loads((SOURCE/'map.json').read_text())
    build = json.loads((OUT/'build.json').read_text())
    checked = []
    for entry in build['render']+build['collision']:
        checked.append(compare(entry, expected_triangles(entry, source)))
        print('Verified', checked[-1], flush=True)
    result = {'status': 'passed', 'triangles': sum(m['triangles'] for m in checked),
              'maximum_vertex_error_cm': max(m['maximum_vertex_error_cm'] for m in checked), 'meshes': checked}
    (OUT/'geometry-verification.json').write_text(json.dumps(result, indent=2)+'\n')
    print('MEGAPARK GEOMETRY VERIFIED', result['triangles'], result['maximum_vertex_error_cm'], flush=True)


if __name__ == '__main__': main()
