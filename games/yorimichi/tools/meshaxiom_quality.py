"""Reproducible fixed-geometry UV and geometry-guided multiview experiments.

Native preparation owns one aggregate guard. Remote Sunburst calls are separately
ledgered, sequential, and never retried. No mesh repair or deformation is performed.
"""
import argparse
from collections import Counter
from functools import partial
import gzip
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

import numpy as np
from PIL import Image, ImageDraw

from meshaxiom_pixel_match import digest, fitted_view, load_module, matte, silhouette, stage

TOOLS = Path(__file__).resolve().parent
VENDOR = TOOLS/'pixel_match/photo_paint.py'


def write(path, value):
    path.write_text(json.dumps(value, indent=2)+'\n')


def triangle_multiset(triangles):
    result = Counter()
    for triangle in triangles:
        triangle = triangle.astype('float32').copy()
        triangle[triangle == 0] = 0
        result[min(np.roll(triangle, k, axis=0).tobytes() for k in range(3))] += 1
    return result


def verify_geometry(source, model, pm):
    """@cc [owner:fontanierh,label:correctness] quality-keeps-native-triangles
    Every native triangle MUST survive with its winding and float32 coordinates after
    the documented uniform scale, origin and axis conversion. UV seam splits MAY duplicate
    vertices; no triangle, hole, connected component or nonmanifold edge MAY be repaired.
    """
    payload = source.read_bytes()
    native = json.loads(gzip.decompress(payload) if source.suffix == '.gz' else payload)
    vertices = np.asarray(native['vertices'])
    lo, hi = vertices.min(axis=0), vertices.max(axis=0)
    positions = ((vertices-np.array([(lo[0]+hi[0])/2, (lo[1]+hi[1])/2, lo[2]]))
                 * (.35/(hi[2]-lo[2]))).astype('float32')
    positions = positions[:, [0, 2, 1]] * np.array([1, 1, -1], dtype='float32')
    exported, _, faces, _ = pm.read_glb(model)
    if triangle_multiset(positions[np.asarray(native['faces'])]) != triangle_multiset(exported[faces]):
        raise ValueError('Native triangle coordinates or winding changed')
    return dict(native_file=source.name, native_sha256=digest(source), model_sha256=digest(model),
                native_vertices=len(vertices), triangles=len(faces),
                all_triangles_and_winding_preserved=True,
                transform='Uniform height .35m, ground origin, Z-up to Y-up; float32 verification')


def run_child(command):
    from atelier.harness.safety.process import spawn
    start = time.monotonic()
    child = spawn(command)
    while True:
        try:
            code = child.wait(timeout=20)
            break
        except subprocess.TimeoutExpired:
            print(f'Owned UV child: {time.monotonic()-start:.0f}s elapsed; waiting for export', flush=True)
    if code:
        raise RuntimeError(f'Owned UV child exited {code}')


def render(pm, positions, faces, view, texture=None, uvs=None):
    face, bary = silhouette(pm, positions, faces, view)
    seen = face >= 0
    normals = pm.vertex_normals(positions, faces)
    normal = (normals[faces[face[seen]]] * bary[seen, :, None]).sum(axis=1)
    normal /= np.maximum(np.linalg.norm(normal, axis=1, keepdims=True), 1e-12)
    out = np.zeros(view.image.shape, dtype='uint8')
    out[..., 3] = 255
    if texture is None:
        illumination = .45+.55*np.abs(normal @ view.cam_to_world[:3, 2])
        out[seen, :3] = (illumination[:, None]*np.array([205, 205, 205])).astype('uint8')
    else:
        uv = (uvs[faces[face[seen]]] * bary[seen, :, None]).sum(axis=1)
        out[seen, :3] = np.clip(pm.sample_rgb(texture, uv[:, 0]*texture.shape[1],
                                             uv[:, 1]*texture.shape[0]), 0, 255).astype('uint8')
    return out, seen


def prepare(args):
    pm = load_module(VENDOR)
    args.output.mkdir(parents=True, exist_ok=True)
    records = []
    for angle, margin in [(66, .0002), (89, .0002), (89, .00005)]:
        name = f'uv-{angle}-{margin:g}'
        folder = args.output/name
        command = [str(args.blender), '--background', '--threads', '3', '--python',
                   str(TOOLS/'meshaxiom_uv.py'), '--', '--mesh', str(args.mesh),
                   '--output', str(folder), '--angle', str(angle), '--margin', str(margin)]
        run_child(command)
        model = folder/'clay-uv.glb'
        geometry = verify_geometry(args.mesh, model, pm)
        write(folder/'geometry-verification.json', geometry)
        _, uvs, faces, base = pm.read_glb(model)
        h, w = base.shape[:2]
        with stage(f'{name} UV occupancy'):
            face, _ = pm.rasterize((uvs*np.array([w, h]))[faces], np.zeros((len(faces), 3)), (h, w))
        record = dict(name=name, angle=angle, margin=margin,
                      covered_texels=int((face >= 0).sum()), atlas_texels=h*w,
                      occupancy=float((face >= 0).mean()), model_sha256=digest(model))
        records.append(record)
        print(json.dumps(record), flush=True)
    records.sort(key=lambda record: record['occupancy'], reverse=True)
    write(args.output/'uv-comparison.json', records)
    best = args.output/records[0]['name']/'clay-uv.glb'
    guides(args.output/'guides', best, args.image, pm)
    return 0


def guides(output, model, reference, pm):
    output.mkdir(parents=True, exist_ok=True)
    positions, _, faces, _ = pm.read_glb(model)
    image = matte(Image.open(reference))
    cameras = []
    contact = Image.new('RGB', (4*384, 2*408))
    draw = ImageDraw.Draw(contact)
    for index, (yaw, pitch) in enumerate([(0, -5), (60, -5), (120, -5), (180, -5),
                                         (240, -5), (300, -5), (60, 55), (240, -40)]):
        view = fitted_view(pm, positions, image, yaw, pitch)
        pixels, seen = render(pm, positions, faces, view)
        name = f'yaw{yaw}-pitch{pitch}'
        target = output/f'{name}.png'
        Image.fromarray(pixels).save(target)
        Image.fromarray((seen*255).astype('uint8')).save(output/f'{name}-mask.png')
        cameras.append(dict(name=name, guide=target.name, guide_sha256=digest(target),
                            yaw=yaw, pitch=pitch, transform_matrix=view.cam_to_world.tolist(),
                            camera_angle_x=view.fov_x))
        x, y = index%4*384, index//4*408
        contact.paste(Image.fromarray(pixels).convert('RGB').resize((384, 384)), (x, y))
        draw.text((x+8, y+386), name, fill='white')
        print(f'Guide {index+1}/8 rendered: {name}', flush=True)
    contact.save(output/'contact.png')
    write(output/'cameras.json', dict(mesh_sha256=digest(model), reference_sha256=digest(reference), views=cameras))


def references(args):
    from atelier.ai.images import paint
    cameras = json.loads((args.output/'guides/cameras.json').read_text())
    if cameras['reference_sha256'] != digest(args.image):
        raise ValueError('Reference identity changed')
    output = args.output/'references'
    output.mkdir(exist_ok=True)
    selected = set(args.views.split(','))
    if selected - {view['name'] for view in cameras['views']}:
        raise ValueError('Unknown requested camera')
    for name in selected:
        if (output/f'{name}.provenance.json').exists():
            raise FileExistsError(f'{name}: paid receipt already exists; reconcile it, do not retry')
    for view in cameras['views']:
        if view['name'] not in selected:
            continue
        guide = args.output/'guides'/view['guide']
        if digest(guide) != view['guide_sha256']:
            raise ValueError('Geometry guide identity changed')
        prompt = f'''Use case: identity-preserve. Asset type: calibrated albedo reference for a fixed 3D game head.
Image 1 supplies the character identity and colors. Image 2 is the exact geometry/camera target to color.
Paint ONLY the head shown in image 2. Preserve its silhouette, nose, eyes, mouth, ears, hair tufts,
ponytail, neck shape, projection, framing, and black background pixel positions exactly.
The target camera has yaw {view['yaw']} degrees and pitch {view['pitch']} degrees around the SAME head.
Use the warm brown skin, dark indigo hair, brown eyes, eyebrows and friendly expression of image 1.
Follow image 2 for WHICH parts are visible: do not turn the head toward image 1; do not add a face on the back.
For back views, faithfully color the back of the indigo hair and ponytail and the brown neck.
Material colors should be clean, detailed stylized game albedo, diffuse and evenly lit. Avoid baked highlights,
cast shadows, outlines, accessories, text, watermarks, new hair tufts, or geometry changes.
Return one 1024x1024 image at exactly the target framing, pure black outside the target head.'''
        prompt_path = output/f'{view["name"]}.prompt.txt'
        prompt_path.write_text(prompt+'\n')
        print(f'Sunburst high: submitting {view["name"]}; one ledgered call, no automatic retry', flush=True)
        with stage(f'Sunburst {view["name"]}'):
            paint(output/f'{view["name"]}.png', prompt, '1024x1024', images=[args.image, guide],
                  record=output/f'{view["name"]}.provenance.json',
                  metadata=dict(prompt=prompt, guide_sha256=digest(guide),
                                reference_sha256=digest(args.image), camera=view), timeout=300)
    return 0


def paint_variants(args):
    from meshaxiom_pixel_match import paint
    pm = load_module(VENDOR)
    # Keep the exact pinned rasterizer, with smaller triangle batches to bound fragment arrays at 4K.
    pm.rasterize = partial(pm.rasterize, chunk=256)
    records = json.loads((args.output/'uv-comparison.json').read_text())
    model = args.output/records[0]['name']/'clay-uv.glb'
    cameras = json.loads((args.output/'guides/cameras.json').read_text())
    if cameras['mesh_sha256'] != digest(model) or cameras['reference_sha256'] != digest(args.image):
        raise ValueError('Guide inputs no longer match')
    anchor = next(view for view in cameras['views'] if view['yaw'] == 60 and view['pitch'] == -5)
    selected = set(args.views.split(','))
    views = [] if anchor['name'] in selected else [dict(
        name='original', image=str(args.image), image_sha256=digest(args.image),
        transform_matrix=anchor['transform_matrix'], camera_angle_x=anchor['camera_angle_x'])]
    checks = []
    for view in cameras['views']:
        if view['name'] not in selected:
            continue
        path = args.output/'references'/f'{view["name"]}.png'
        receipt = json.loads(path.with_suffix('.provenance.json').read_text())
        if receipt.get('status') != 'done' or receipt.get('output_sha256') != digest(path):
            raise ValueError('Generated reference differs from its paid receipt')
        if (receipt.get('guide_sha256') != view['guide_sha256']
                or receipt.get('reference_sha256') != digest(args.image) or receipt.get('camera') != view):
            raise ValueError('Generated reference recipe differs from the guide manifest')
        generated = matte(Image.open(path))
        guide = args.output/'guides'/view['guide']
        if digest(guide) != view['guide_sha256']:
            raise ValueError('Geometry guide changed before projection')
        target = np.asarray(Image.open(guide).convert('RGB')).max(axis=2) > 8
        mask = generated[..., 3] > 127
        iou = float((target & mask).sum()/max((target | mask).sum(), 1))
        if iou < .95:
            raise ValueError(f'{view["name"]}: guide silhouette IoU {iou:.4f} below .95; reject view')
        checks.append(dict(name=view['name'], silhouette_iou=iou, image_sha256=digest(path)))
        views.append(dict(name=view['name'], image=str(path), image_sha256=digest(path),
                          transform_matrix=view['transform_matrix'], camera_angle_x=view['camera_angle_x']))
    if len(checks) != len(selected):
        raise ValueError('Missing requested cameras')
    write(args.output/'reference-validation.json', checks)
    summary = []
    for variant in args.variants.split(','):
        folder = args.output/variant
        folder.mkdir(exist_ok=True)
        source = model
        if variant == '4k':
            positions, uvs, faces, base = pm.read_glb(model)
            base = np.asarray(Image.fromarray(base).resize((4096, 4096), Image.Resampling.NEAREST))
            source = folder/'clay-uv.glb'
            source.write_bytes(pm.replace_base_colour(model.read_bytes(), pm.encode_png(base)))
        rgba = matte(Image.open(args.image))
        Image.fromarray(rgba).save(folder/'reference-matted.png')
        write(folder/'calibration.json', dict(mesh_sha256=digest(source), reference_sha256=digest(args.image),
              matted_sha256=digest(folder/'reference-matted.png'), transform_matrix=anchor['transform_matrix'],
              camera_angle_x=anchor['camera_angle_x'], calibration='Fixed original camera, no shape fitting'))
        manifest = folder/'views.json'
        used_views = [view for view in views if view['name'] == anchor['name']] if variant == 'guided-single' else views
        if not used_views:
            raise ValueError('Guided-single variant requires the generated front camera')
        write(manifest, dict(mesh_sha256=digest(source), views=[
            {**view, 'image': os.path.relpath(view['image'], folder)} for view in used_views]))
        recipe = SimpleNamespace(mesh=source, image=args.image, output=folder, module=VENDOR,
                                 views=None if variant == 'single' else manifest,
                                 blend='weighted' if variant in ('single', 'guided-single', 'weighted') else 'best-angle')
        started = time.monotonic()
        paint(recipe, pm)
        paint_seconds = time.monotonic()-started
        model_path = folder/'head-pixel-match.glb'
        write(folder/'geometry-verification.json', verify_geometry(args.mesh, model_path, pm))
        positions, uvs, faces, texture = pm.read_glb(model_path)
        contact = Image.new('RGB', (4*384, 2*408))
        draw = ImageDraw.Draw(contact)
        for index, camera in enumerate(cameras['views']):
            view = pm.View(np.zeros((1024, 1024, 4), dtype='uint8'), np.array(camera['transform_matrix']),
                           camera['camera_angle_x'], camera['name'])
            pixels, _ = render(pm, positions, faces, view, texture, uvs)
            Image.fromarray(pixels).save(folder/f'{camera["name"]}.png')
            x, y = index%4*384, index//4*408
            contact.paste(Image.fromarray(pixels).convert('RGB').resize((384, 384)), (x, y))
            draw.text((x+8, y+386), camera['name'], fill='white')
        contact.save(folder/'contact.png')
        report = json.loads((folder/'pixel-match-report.json').read_text())
        summary.append(dict(variant=variant, model_sha256=digest(model_path),
                            painted_fraction=report['covered_surface_fraction_painted'],
                            covered_texels=report['covered_texels'], views=report['view_count'],
                            projection_validation_seconds=round(paint_seconds, 3)))
        write(args.output/'texture-comparison.json', summary)
        print(f'Variant {variant} complete: {json.dumps(summary[-1])}', flush=True)
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['prepare', 'references', 'paint'])
    parser.add_argument('--mesh', type=Path, required=True)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--blender', type=Path, default=Path('/Applications/Blender.app/Contents/MacOS/Blender'))
    parser.add_argument('--views', default='yaw0-pitch-5,yaw60-pitch-5,yaw120-pitch-5,yaw180-pitch-5,yaw240-pitch-5,yaw300-pitch-5,yaw60-pitch55')
    parser.add_argument('--variants', default='single,guided-single,weighted,best-angle,4k')
    parser.add_argument('--report', type=Path)
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.stage == 'references':
        return references(args)
    if set(args.variants.split(',')) - {'single', 'guided-single', 'weighted', 'best-angle', '4k'}:
        parser.error('Unknown texture variant')
    if args.worker:
        return (prepare if args.stage == 'prepare' else paint_variants)(args)
    if args.report is None or args.report.exists():
        parser.error('Use a new --report directory for native preparation')
    from atelier.harness.safety.guarded import run
    return run([sys.executable, '-u', str(Path(__file__).resolve()), '--worker', *argv],
               args.report, timeout=900, purpose=f'Fixed-geometry head quality: {args.stage}',
               aggregate_tree=True, progress=20)


if __name__ == '__main__':
    raise SystemExit(main())
