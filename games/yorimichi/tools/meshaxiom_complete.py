"""Bounded surface-color extrapolation after projection, with immutable observed texels.

This is a separate material-completion experiment. Extrapolated colors are not new
observations. No geometry, UV, normal or connectivity changes are permitted.
"""
import argparse
from functools import partial
import hashlib
import itertools
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageDraw

from meshaxiom_pixel_match import digest, load_module, stage
from meshaxiom_quality import render, verify_geometry, write, VENDOR


def extrapolate(points, colours, observed, voxel=.35/128, radius=.35/64):
    """Fill only unobserved samples from nearby occupied cell means, in bounded tiles."""
    if not observed.any():
        raise ValueError('Completion needs observed surface colours')
    origin = points.min(axis=0)
    cells = np.floor((points-origin)/voxel).astype('int32')
    shape = tuple(cells.max(axis=0)+1)
    size = int(np.prod(shape))
    if size > 4_000_000:
        raise ValueError('Surface grid exceeds bounded completion workspace')
    ids = np.ravel_multi_index(cells.T, shape)
    known_ids = ids[observed]
    count = np.bincount(known_ids, minlength=size)
    denominator = np.maximum(count, 1)
    centroids = np.column_stack([np.bincount(known_ids, weights=points[observed, i], minlength=size)
                                 / denominator for i in range(3)])
    means = np.column_stack([np.bincount(known_ids, weights=colours[observed, i], minlength=size)
                             / denominator for i in range(3)])
    result = colours.copy()
    filled = np.zeros(len(points), dtype=bool)
    unknown = np.flatnonzero(~observed)
    for start in range(0, len(unknown), 65536):
        indices = unknown[start:start+65536]
        best = np.full(len(indices), radius*radius)
        chosen = np.full(len(indices), -1, dtype='int64')
        for offset in itertools.product(range(-2, 3), repeat=3):
            query = cells[indices]+offset
            valid = ((query >= 0) & (query < shape)).all(axis=1)
            rows = np.flatnonzero(valid)
            bins = np.ravel_multi_index(query[valid].T, shape)
            occupied = count[bins] > 0
            rows, bins = rows[occupied], bins[occupied]
            distance = ((points[indices[rows]]-centroids[bins])**2).sum(axis=1)
            take = distance < best[rows]
            chosen[rows[take]], best[rows[take]] = bins[take], distance[take]
        accepted = chosen >= 0
        result[indices[accepted]] = np.rint(means[chosen[accepted]]).clip(0, 255).astype('uint8')
        filled[indices[accepted]] = True
        print(f'Surface completion: {min(start+65536,len(unknown))}/{len(unknown)} unseen texels checked', flush=True)
    return result, filled


def complete(args):
    """@cc [owner:fontanierh,label:correctness] completion-preserves-observations-and-mesh
    Completion MUST preserve every observed texel and every non-image GLB buffer.
    Only unobserved occupied texels within the recorded bounded surface-cell search MAY
    receive extrapolated colours. Reports MUST distinguish observations from extrapolation,
    retain exact input identities and verify the native triangles including winding.
    """
    model = args.source/'head-pixel-match.glb'
    proof = json.loads((args.source/'pixel-match-report.json').read_text())
    mask_path = args.source/'confidence.png'
    views_path = args.source/'views.json'
    if (proof['output_sha256'] != digest(model) or proof['blend'] != 'front-first'
            or proof['views_manifest_sha256'] != digest(views_path)):
        raise ValueError('Completion source differs from its front-first projection receipt')
    pm = load_module(VENDOR)
    pm.rasterize = partial(pm.rasterize, chunk=256)
    positions, uvs, faces, texture = pm.read_glb(model)
    mask = np.asarray(Image.open(mask_path).convert('L'))
    if mask.shape != texture.shape[:2] or not np.isin(mask, [0, 255]).all():
        raise ValueError('Completion needs the binary front-first observation mask')
    with stage('Completion UV rasterization'):
        h, w = texture.shape[:2]
        face, bary = pm.rasterize((uvs*np.array([w, h]))[faces], np.zeros((len(faces), 3)), (h, w))
    covered = face >= 0
    observed = mask[covered] > 0
    if int(observed.sum()) != proof['painted_surface_texels']:
        raise ValueError('Observation mask count differs from projection receipt')
    points = (positions[faces[face[covered]]] * bary[covered, :, None]).sum(axis=1)
    before = texture[covered, :3].copy()
    observed_rgba = texture[covered][observed].copy()
    with stage('Bounded surface-colour completion'):
        colours, filled = extrapolate(points, before, observed)
    if not np.array_equal(colours[observed], before[observed]):
        raise AssertionError('An observed texel changed')
    texture[covered, :3] = colours
    args.output.mkdir(parents=True, exist_ok=True)
    output = args.output/'head-completed.glb'
    output.write_bytes(pm.replace_base_colour(model.read_bytes(), pm.encode_png(texture)))
    check = pm.read_glb(output)
    if not np.array_equal(check[3][covered][observed], observed_rgba):
        raise AssertionError('Serialized completion changed an observed texel')
    before_doc, before_bin = pm._split_glb(model.read_bytes())
    after_doc, after_bin = pm._split_glb(output.read_bytes())
    image_view = before_doc['images'][pm.base_colour_image_index(before_doc)]['bufferView']
    if len(before_doc['bufferViews']) != len(after_doc['bufferViews']):
        raise AssertionError('Completion changed the buffer inventory')
    for i, (a, b) in enumerate(zip(before_doc['bufferViews'], after_doc['bufferViews'])):
        if i != image_view:
            ai, bi = a.get('byteOffset', 0), b.get('byteOffset', 0)
            if before_bin[ai:ai+a['byteLength']] != after_bin[bi:bi+b['byteLength']]:
                raise AssertionError('Completion changed a non-image buffer')
    write(args.output/'geometry-verification.json', verify_geometry(args.mesh, output, pm))
    fill_mask = np.zeros((h, w), dtype='uint8')
    fill_mask[covered] = filled*255
    Image.fromarray(fill_mask).save(args.output/'extrapolated.png')
    report = dict(input_sha256=digest(model), output_sha256=digest(output),
                  projection_receipt_sha256=digest(args.source/'pixel-match-report.json'),
                  observation_mask_sha256=digest(mask_path), tool_sha256=digest(Path(__file__)),
                  observed_texels=int(observed.sum()), extrapolated_texels=int(filled.sum()),
                  occupied_texels=int(covered.sum()), observed_texels_unchanged=True,
                  observed_rgb_sha256=hashlib.sha256(before[observed].tobytes()).hexdigest(),
                  non_image_buffers_identical=True, voxel_metres=.35/128,
                  search_radius_metres=.35/64, neighbouring_cells_per_axis=5,
                  method='Nearest occupied surface-cell mean within radius; not a new observation',
                  remaining_unseen='Original neutral texels retained beyond the bounded search')
    camera_path = args.source.parent/'guides/cameras.json'
    cameras = json.loads(camera_path.read_text())
    if (cameras['mesh_sha256'] != proof['input_mesh_sha256']
            or cameras['reference_sha256'] != proof['reference_sha256'] or len(cameras['views']) != 8):
        raise ValueError('Completion diagnostic cameras differ from the source UV mesh')
    report['diagnostic_camera_manifest_sha256'] = digest(camera_path)
    write(args.output/'completion-report.json', report)
    contact = Image.new('RGB', (1536, 816))
    draw = ImageDraw.Draw(contact)
    for index, camera in enumerate(cameras['views']):
        view = pm.View(np.zeros((1024,1024,4), dtype='uint8'), np.array(camera['transform_matrix']),
                       camera['camera_angle_x'], camera['name'])
        pixels, _ = render(pm, positions, faces, view, texture, uvs)
        contact.paste(Image.fromarray(pixels).convert('RGB').resize((384,384)),
                      (index%4*384, index//4*408))
        draw.text((index%4*384+8, index//4*408+386), camera['name'], fill='white')
        print(f'Completion diagnostic {index+1}/{len(cameras["views"])} rendered', flush=True)
    contact.save(args.output/'contact.png')
    print(json.dumps(report), flush=True)
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True, help='Completed 2K front-first bake folder')
    p.add_argument('--mesh', type=Path, required=True, help='Immutable native source JSON or JSON.gz')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--memory-gib', type=int, choices=range(4,11), default=4)
    p.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = p.parse_args(argv)
    if args.worker:
        return complete(args)
    if args.report.exists():
        p.error('Use a new guard report directory')
    from atelier.harness.safety.guarded import run
    return run([sys.executable, '-u', str(Path(__file__).resolve()), '--worker', *argv],
               args.report, timeout=900, purpose='Fixed-mesh surface colour completion',
               limit_gib=args.memory_gib, aggregate_tree=True, progress=20)


if __name__ == '__main__':
    raise SystemExit(main())
