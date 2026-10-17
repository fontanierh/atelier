"""Project one reference onto a verified native vertex-color head; geometry is immutable."""
from pathlib import Path
from functools import partial
import argparse
import hashlib
import json
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
from PIL import Image
from meshaxiom_pixel_match import digest, fitted_view, load_module, matte, silhouette, stage
from meshaxiom_quality import VENDOR, write


def native_arrays(doc, payload):
    """Accept only the complete, noninterleaved layout emitted by our native bake."""
    if doc.get('scene') != 0 or doc.get('scenes') != [dict(nodes=[0])] or doc.get('nodes') != [dict(mesh=0)]:
        raise ValueError('Expected native identity scene')
    if len(doc['meshes']) != 1 or len(doc['meshes'][0]['primitives']) != 1:
        raise ValueError('Expected complete native primitive')
    primitive = doc['meshes'][0]['primitives'][0]
    if primitive.get('mode', 4) != 4 or primitive['attributes'] != dict(POSITION=0, NORMAL=1, COLOR_0=2) or primitive['indices'] != 3:
        raise ValueError('Expected native bake attribute bindings')
    if len(doc['accessors']) != 4 or len(doc['bufferViews']) != 4 or len(doc['buffers']) != 1:
        raise ValueError('Unexpected native bake buffers')
    arrays = []
    intervals = []
    for index in range(4):
        a = doc['accessors'][index]; v = doc['bufferViews'][index]
        width, kind, component, dtype = (3, 'VEC3', 5126, '<f4') if index < 3 else (1, 'SCALAR', 5125, '<u4')
        if a['bufferView'] != index or a['type'] != kind or a['componentType'] != component or a.get('sparse') or a.get('byteOffset', 0) or a.get('normalized'):
            raise ValueError('Unexpected native bake accessor')
        offset = v.get('byteOffset', 0); length = a['count'] * width * 4
        if v.get('buffer', 0) != 0 or v.get('byteStride') or v['byteLength'] != length or offset < 0 or offset + length > len(payload):
            raise ValueError('Unexpected native bake buffer range')
        intervals.append((offset, offset + length))
        arrays.append(np.frombuffer(payload, dtype=dtype, count=a['count']*width, offset=offset).reshape(-1, width))
    if any(a[1] > b[0] for a, b in zip(sorted(intervals), sorted(intervals)[1:])):
        raise ValueError('Overlapping native buffers')
    positions, normals, colors, indices = arrays
    if not len(positions) or len(normals) != len(positions) or len(colors) != len(positions) or len(indices) % 3 or indices.max() >= len(positions):
        raise ValueError('Invalid complete native geometry')
    if not all(np.isfinite(a).all() for a in arrays[:3]):
        raise ValueError('Nonfinite native attributes')
    return positions, normals, colors, indices.reshape(-1, 3), intervals[2]


def replace_colors(doc, payload, colors, weights, photo_rgb):
    """@cc [owner:fontanierh,label:correctness] vertex-photo-preserves-native-buffers
    Projection MUST change only COLOR_0 bytes. Every zero-weight vertex color and
    all geometry, normal, index, scene and material bindings MUST remain identical.
    """
    from vertex_bake import linear
    _, _, original, _, (start, end) = native_arrays(doc, payload)
    if not np.array_equal(colors, original) or weights.shape != (len(colors),) or photo_rgb.shape != colors.shape:
        raise ValueError('Photo support shape mismatch')
    if not np.isfinite(weights).all() or not np.isfinite(photo_rgb).all() or (weights < 0).any() or (weights > 1).any():
        raise ValueError('Invalid photo support')
    result = colors.copy(); observed = weights > 0
    result[observed] = colors[observed]*(1-weights[observed, None]) + linear(np.clip(photo_rgb[observed]/255, 0, 1))*weights[observed, None]
    output = payload[:start] + result.astype('<f4').tobytes() + payload[end:]
    if output[:start] != payload[:start] or output[end:] != payload[end:] or not np.array_equal(result[~observed], colors[~observed]):
        raise ValueError('Photo projection changed protected bytes')
    return output, int(observed.sum()), hashlib.sha256(result[~observed].tobytes()).hexdigest()


def worker(args):
    started = time.monotonic(); args.output.mkdir(parents=True, exist_ok=True)
    target = args.output/'head.glb'
    if target.exists(): raise ValueError('Completed photo trial exists')
    pm = load_module(VENDOR); pm.rasterize = partial(pm.rasterize, chunk=256)
    before = digest(args.model); doc, payload = pm._split_glb(args.model.read_bytes())
    positions, normals, colors, faces, _ = native_arrays(doc, payload)
    rgba = matte(Image.open(args.image)); small = np.array(Image.fromarray(rgba).resize((96, 96), Image.Resampling.LANCZOS))
    mask = small[..., 3] > 127; candidates = []
    # Camera registration only: no source pixels, model positions or normals are fitted.
    for yaw in (-45, -30, -15):
        for pitch in (-10, -5, 0):
            with stage(f'Photo camera yaw{yaw}/pitch{pitch}'):
                view = fitted_view(pm, positions, small, yaw, pitch)
                face, _ = silhouette(pm, positions, faces, view); visible = face >= 0
                score = float((visible & mask).sum()/max((visible | mask).sum(), 1))
                candidates.append((score, yaw, pitch))
        print(f'Photo camera search: {len(candidates)}/9 complete, best IoU={max(candidates)[0]:.4f}', flush=True)
    score, yaw, pitch = max(candidates)
    view = fitted_view(pm, positions, rgba, yaw, pitch)
    with stage('Depth-tested original-photo projection at native vertices'):
        weights, photo = pm.view_weights(positions, normals, view, positions, faces, pm.Settings(match_colour=False))
        output, painted, protected = replace_colors(doc, payload, colors, weights, photo)
        target.write_bytes(pm._join_glb(doc, output))
        checked, binary = pm._split_glb(target.read_bytes())
        _, _, _, _, (start, end) = native_arrays(checked, binary)
        if checked != doc or binary[:start] != payload[:start] or binary[end:] != payload[end:] or digest(args.model) != before:
            raise ValueError('Photo export changed native model data')
    write(args.output/'photo-report.json', dict(method='Depth/facing/matte-weighted original photo over native learned vertex colors',
        worker_sha256=digest(Path(__file__)), input_sha256=before, output_sha256=digest(target), reference_sha256=digest(args.image),
        triangles=len(faces), vertices=len(positions), painted_vertices=painted, painted_vertex_fraction=painted/len(positions),
        protected_vertex_color_sha256=protected, geometry_normals_indices_materials_identical=True,
        camera=dict(yaw=yaw, pitch=pitch, silhouette_iou_96px=score, transform_matrix=view.cam_to_world.tolist(), camera_angle_x=view.fov_x),
        limitations='Silhouette registration does not establish eye/mouth correspondence. Inspect eight views. Vertex fraction is not surface area.',
        seconds=round(time.monotonic()-started, 3)))
    del payload, binary, output
    from vertex_bake import render_existing
    args.model = target; args.yaw_offset = -90
    render_existing(args)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model', type=Path, required=True); p.add_argument('--image', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True); p.add_argument('--report', type=Path, required=True)
    p.add_argument('--memory-gib', type=int, choices=range(4, 11), default=8)
    p.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = p.parse_args(argv)
    if args.worker: return worker(args)
    if args.report.exists(): p.error('Use a fresh guard report')
    from atelier.harness.safety.guarded import run
    forwarded = sys.argv[1:] if argv is None else list(argv)
    return run([sys.executable, '-u', str(Path(__file__).resolve()), *forwarded, '--worker'], args.report,
        timeout=900, purpose='Native TRELLIS original-photo vertex projection and eight views',
        limit_gib=args.memory_gib, aggregate_tree=True, progress=20)


if __name__ == '__main__': sys.exit(main())
