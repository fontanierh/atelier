"""Convert an Atelier library map cache to project-native source arrays and PNGs.

The optional converter uses pinned format tools. Normal builds read only the
committed library arrays and textures.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct
import sys

import numpy as np
from PIL import Image

UPSTREAM = '60efdef86600d8d8d4feb4b7c608fa0efd0643d7'
BOUNDS = {'minimum': [200., -800.], 'maximum': [500., -500.]}
SOURCE = Path(__file__).resolve().parents[3] / 'assets/megapark'


def sha(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def intersects(bounds):
    return all(bounds['maximum'][axis] >= BOUNDS['minimum'][i]
               and bounds['minimum'][axis] <= BOUNDS['maximum'][i]
               for i, axis in enumerate((0, 2)))


def install_collision_decoder(module):
    """Native GetVertex82AC79D0: unsigned delta, signed saturation, two f32 rounds."""
    original = module._decode_vertices

    def vertices(cluster, count, compression, granularity, end):
        if compression == 0:
            return original(cluster, count, compression, granularity, end)
        if compression == 1:
            base = struct.unpack_from('>3i', cluster, 16)
            if 28 + count * 6 > end:
                raise ValueError('Compressed collision vertices exceed their block')
        elif compression != 2 or 16 + count * 12 > end:
            raise ValueError('Invalid collision vertex format or size')
        result = []
        for i in range(count):
            if compression == 1:
                delta = struct.unpack_from('>3H', cluster, 28 + i * 6)
                integers = [min(2147483647, b + d) for b, d in zip(base, delta)]
            else:
                integers = struct.unpack_from('>3i', cluster, 16 + i * 12)
            point = tuple(float(np.float32(np.float32(n) * np.float32(granularity))) for n in integers)
            if not all(np.isfinite(point)):
                raise ValueError('Non-finite collision point')
            result.append(point)
        return result

    module._decode_vertices = vertices


def export(cache, upstream, output=SOURCE):
    sys.path.insert(0, str(upstream / 'tools/vendor/university/tools/vanilla_map_extraction/tools'))
    import retail_collision_mesh as collision
    install_collision_decoder(collision)
    manifest = json.loads((cache / 'manifest.json').read_text())
    if manifest['district_name'] != 'DIST_University':
        raise ValueError('Super Ultra Mega Park is part of University, not DIST_MegaPark')
    output.mkdir(parents=True, exist_ok=True)
    for folder in ('geometry', 'collision', 'textures'):
        (output / folder).mkdir(exist_ok=True)
    native = {
        'version': 1, 'name': 'Super Ultra Mega Park', 'source_district': 'DIST_University',
        'coordinate_system': 'Original right-handed Y-up metres. Unreal: (100*x,100*z,100*y).',
        'selection_xz': BOUNDS, 'selection_policy': 'Keep complete source meshes intersecting this region; never clip or simplify geometry.',
        'spawn': {'position': [330., 132.006, -710.], 'heading_degrees': 0.},
        'models': [], 'collision': [], 'textures': {}, 'rails': [],
    }
    textures = set()
    for model in manifest['models']:
        if not intersects(model['bounds']):
            continue
        name = model['asset_id'][2:]
        geometry = output / 'geometry' / f'{name}.npz'
        with np.load(cache / model['npz'], allow_pickle=False) as arrays:
            np.savez_compressed(geometry, **{key: arrays[key] for key in arrays.files})
        native['models'].append({**model, 'npz': f'geometry/{name}.npz', 'sha256': sha(geometry), 'rx2': None})
        for part in model['meshes']:
            textures.update(value for value in part.get('retail_texture_ids', {}).values() if value)
            if part.get('texture_id'):
                textures.add(part['texture_id'])
    for entry in manifest['simulation_assets']:
        # Re-read before selecting: older prepared caches used signed deltas,
        # which can corrupt both collision vertices and their cached bounds.
        meshes = collision.decode_rx2_clustered_meshes((cache / entry['rx2']).read_bytes())
        for i, mesh in enumerate(meshes):
            if not intersects({'minimum': mesh.bounds_min, 'maximum': mesh.bounds_max}):
                continue
            name = f"{entry['asset_id'][2:]}_{i}"
            path = output / 'collision' / f'{name}.npz'
            triangles = np.asarray([(t.a, t.b, t.c) for t in mesh.triangles], dtype='<f4')
            np.savez_compressed(path, triangles=triangles,
                surface=np.asarray([t.surface for t in mesh.triangles], dtype='<u2'),
                group=np.asarray([t.group_id or 0 for t in mesh.triangles], dtype='<u2'),
                edge_codes=np.asarray([t.edge_codes if t.edge_codes is not None else (-1,-1,-1) for t in mesh.triangles], dtype='<i2'),
                unit_flags=np.asarray([t.unit_flags for t in mesh.triangles], dtype='u1'),
                one_sided=np.asarray(bool(mesh.mesh_flags & 0x10), dtype='u1'))
            native['collision'].append({'id': name, 'asset_id': entry['asset_id'], 'section_index': i,
                'stream_file': entry['stream_file'], 'npz': f'collision/{name}.npz', 'triangles': len(triangles),
                'bounds': {'minimum': mesh.bounds_min, 'maximum': mesh.bounds_max},
                'mesh_flags': mesh.mesh_flags, 'sha256': sha(path)})
    for rail in manifest['grind_splines']:
        values = np.asarray([struct.unpack('>30f', bytes.fromhex(raw)) for raw in rail['native_segment_payloads']])
        # The cubic's control points bound the entire curve, including interior extrema.
        a, b, c, d = (values[:, offset:offset+3] for offset in (0,4,8,12))
        controls = np.concatenate((d, d+c/3, d+2*c/3+b/3, d+c+b+a))
        if intersects({'minimum': controls.min(axis=0), 'maximum': controls.max(axis=0)}):
            native['rails'].append(rail)
    for tid in sorted(textures):
        if tid not in manifest['textures']:
            raise ValueError('Unresolved original material texture: ' + tid)
        t = manifest['textures'][tid]
        path = output / 'textures' / f'{tid[2:]}.png'
        image = Image.frombytes('RGBA', (t['width'], t['height']), (cache / t['rgba']).read_bytes())
        image.save(path, optimize=True)
        native['textures'][tid] = {'png': f'textures/{path.name}', 'width': t['width'], 'height': t['height'],
            'format': t['format'], 'sha256': sha(path), 'decoded_rgba_sha256': hashlib.sha256(image.tobytes()).hexdigest()}
    native['summary'] = {
        'models': len(native['models']), 'mesh_parts': sum(len(p['meshes']) for p in native['models']),
        'vertices': sum(p['vertex_count'] for p in native['models']),
        'render_triangles': sum(p['triangle_count'] for p in native['models']),
        'collision_meshes': len(native['collision']), 'collision_triangles': sum(p['triangles'] for p in native['collision']),
        'textures': len(textures), 'grind_paths': len(native['rails']),
        'native_cubic_segments': sum(r['segment_count'] for r in native['rails']),
    }
    (output / 'map.json').write_text(json.dumps(native, indent=1) + '\n')
    print(json.dumps(native['summary'], indent=2), flush=True)
    return native


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--upstream', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=SOURCE)
    args = parser.parse_args()
    export(args.cache.resolve(), args.upstream.resolve(), args.output.resolve())
