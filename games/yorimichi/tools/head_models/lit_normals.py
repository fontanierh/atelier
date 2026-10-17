"""Filter shading normals and split normal seams without changing any geometric triangle."""
from pathlib import Path
import argparse
import copy
import hashlib
import json
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
from meshaxiom_pixel_match import digest, load_module
from meshaxiom_quality import VENDOR, write
from vertex_photo import native_arrays

TENSOR = ((0, 0), (1, 1), (2, 2), (0, 1), (0, 2), (1, 2))


def normal_axes(positions, normals, faces, iterations):
    """@cc [owner:fontanierh,label:correctness] shading-field-never-deforms
    Normal filtering MUST NOT mutate positions, indices or input normals. Tensor
    averaging MUST ignore face-normal sign and use only triangle-connected neighbors;
    it MUST NOT bridge disconnected surfaces merely because they are spatially close.
    """
    if not 0 <= iterations <= 64:
        raise ValueError('Normal iterations must be between zero and 64')
    count = len(positions)
    field = np.zeros((count, 6), dtype='float32')
    for start in range(0, len(faces), 65536):
        f = faces[start:start+65536]; p = positions[f]
        cross = np.cross(p[:, 1]-p[:, 0], p[:, 2]-p[:, 0])
        area = np.linalg.norm(cross, axis=1)
        tensor = np.stack([cross[:, a]*cross[:, b]/np.maximum(area, 1e-30) for a, b in TENSOR], axis=1)
        np.add.at(field, f.reshape(-1), np.repeat(tensor, 3, axis=0))
    trace = field[:, :3].sum(1)
    field /= np.maximum(trace[:, None], 1e-30)
    print(f'Area-weighted unoriented normal tensors: {count:,} vertices', flush=True)
    if iterations:
        # Both directions of each triangle edge; duplicate incidences have equal weight.
        rows = np.tile(faces.reshape(-1), 2)
        neighbors = np.concatenate((faces[:, [1, 2, 0]].reshape(-1), faces[:, [2, 0, 1]].reshape(-1)))
        degree = np.bincount(rows, minlength=count)
        order = np.argsort(rows, kind='stable')
        neighbors = neighbors[order]
        del rows, order
        occupied = degree > 0
        offsets = np.r_[0, np.cumsum(degree)[:-1]][occupied]
        print(f'Connected normal filter: {len(neighbors):,} directed incidences, {iterations} iterations', flush=True)
        for step in range(iterations):
            result = field.copy()
            for channel in range(6):
                summed = np.add.reduceat(field[neighbors, channel], offsets)
                result[occupied, channel] = .5*field[occupied, channel] + .5*summed/degree[occupied]
            field = result
            print(f'Normal tensor diffusion {step+1}/{iterations}', flush=True)
        del neighbors
    axes = np.empty_like(normals)
    for start in range(0, count, 65536):
        t = field[start:start+65536]
        matrix = np.empty((len(t), 3, 3), dtype='float32')
        for channel, (a, b) in enumerate(TENSOR):
            matrix[:, a, b] = matrix[:, b, a] = t[:, channel]
        _, vectors = np.linalg.eigh(matrix)
        axis = vectors[:, :, -1]
        axis[(axis*normals[start:start+len(t)]).sum(1) < 0] *= -1
        axes[start:start+len(t)] = axis
    if not np.isfinite(axes).all():
        raise ValueError('Nonfinite filtered normal field')
    return axes


def normal_seams(document, payload, axes):
    """@cc [owner:fontanierh,label:correctness] lit-normals-preserve-geometric-triangles
    Export MUST preserve every original ordered triangle's position and vertex-color
    bytes, including winding, duplicates and degenerates. Only shading normals and
    coincident normal-seam vertex copies may change. Scene and material bindings MUST
    remain identical; no face may be removed, reordered, reversed or repaired.
    """
    positions, _, colors, faces, _ = native_arrays(document, payload)
    if document.get('extensionsUsed') or len(document.get('materials', [])) != 1:
        raise ValueError('Use the original conventionally lit native bake')
    if axes.shape != positions.shape or not np.isfinite(axes).all() or not np.allclose(np.linalg.norm(axes, axis=1), 1, atol=1e-5):
        raise ValueError('Invalid unit normal field')
    negative = np.zeros(len(positions), dtype=bool)
    signs = np.zeros(len(faces), dtype='uint8')
    for start in range(0, len(faces), 65536):
        f = faces[start:start+65536]; p = positions[f]
        cross = np.cross(p[:, 1]-p[:, 0], p[:, 2]-p[:, 0])
        for corner in range(3):
            flip = (axes[f[:, corner]]*cross).sum(1) < 0
            signs[start:start+len(f)] |= flip.astype('uint8') << corner
            negative[f[flip, corner]] = True
    copies = np.flatnonzero(negative)
    if len(positions)+len(copies) >= 2**32:
        raise ValueError('Normal seams exceed uint32 indices')
    lookup = np.zeros(len(positions), dtype='uint32')
    lookup[copies] = np.arange(len(copies), dtype='uint32')+len(positions)
    indices = faces.copy()
    for corner in range(3):
        selected = (signs & (1 << corner)) != 0
        indices[selected, corner] = lookup[faces[selected, corner]]
    arrays = [np.concatenate((positions, positions[copies])),
              np.concatenate((axes, -axes[copies])),
              np.concatenate((colors, colors[copies])), indices]
    result = copy.deepcopy(document); binary = bytearray()
    for index, array in enumerate(arrays):
        binary += b'\0'*(-len(binary) % 4)
        result['bufferViews'][index].update(byteOffset=len(binary), byteLength=array.nbytes)
        result['accessors'][index]['count'] = array.size if index == 3 else len(array)
        binary += array.tobytes()
    result['buffers'][0]['byteLength'] = len(binary)
    # Mapping seam copies back to their source vertex proves index order and winding.
    source_index = np.concatenate((np.arange(len(positions), dtype='uint32'), copies.astype('uint32')))
    for start in range(0, len(faces), 65536):
        f = faces[start:start+65536]; exported = indices[start:start+len(f)]
        if not np.array_equal(source_index[exported], f):
            raise ValueError('Normal seams changed native triangle order')
        if arrays[0][exported].tobytes() != positions[f].tobytes() or arrays[2][exported].tobytes() != colors[f].tobytes():
            raise ValueError('Normal seams changed native triangle positions or colors')
    for key in ('scene', 'scenes', 'nodes', 'meshes', 'materials'):
        if result[key] != document[key]:
            raise ValueError('Normal export changed scene/material bindings')
    return result, bytes(binary), dict(native_vertices=len(positions), exported_vertices=len(arrays[0]),
        normal_seam_copies=len(copies), triangles=len(faces),
        ordered_triangle_positions_colors_winding_exact=True, scene_material_bindings_identical=True)


def worker(args):
    started = time.monotonic(); args.output.mkdir(parents=True, exist_ok=True)
    if (args.output/'head.glb').exists():
        raise ValueError('Completed lit-normal trial exists')
    pm = load_module(VENDOR); before = digest(args.model)
    document, payload = pm._split_glb(args.model.read_bytes())
    positions, normals, _, faces, _ = native_arrays(document, payload)
    print(f'Loaded {len(faces):,} native triangles; positions remain fixed', flush=True)
    axes = normal_axes(positions, normals, faces, args.iterations)
    output, binary, proof = normal_seams(document, payload, axes)
    target = args.output/'head.glb'; target.write_bytes(pm._join_glb(output, binary))
    checked, checked_binary = pm._split_glb(target.read_bytes())
    if checked != output or checked_binary != binary or digest(args.model) != before:
        raise ValueError('Lit-normal export changed source or verified output')
    proof.update(method='Area-weighted unoriented normal tensors, connected diffusion, winding-aligned normal seams',
        worker_sha256=digest(Path(__file__)), input_sha256=before, output_sha256=digest(target),
        iterations=args.iterations, relaxation=.5, normal_field_sha256=hashlib.sha256(axes.tobytes()).hexdigest(),
        seconds=round(time.monotonic()-started, 3),
        limitations='Only shading is filtered. Raw geometry, holes, self-intersections and learned color speckles remain.')
    write(args.output/'normal-report.json', proof)
    print(json.dumps(proof), flush=True)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('model', 'output', 'report'):
        p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--iterations', type=int, choices=range(0, 65), default=16)
    p.add_argument('--memory-gib', type=int, choices=range(4, 11), default=8)
    p.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = p.parse_args(argv)
    if args.worker:
        return worker(args)
    if args.report.exists():
        p.error('Use a fresh guard report')
    from atelier.harness.safety.guarded import run
    forwarded = sys.argv[1:] if argv is None else list(argv)
    return run([sys.executable, '-u', str(Path(__file__).resolve()), *forwarded, '--worker'], args.report,
        timeout=1200, purpose='TRELLIS lit shading normals, exact native geometric triangles',
        limit_gib=args.memory_gib, aggregate_tree=True, progress=20)


if __name__ == '__main__':
    sys.exit(main())
