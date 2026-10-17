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
import re
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
    for view in cameras['views']:
        if view['name'] not in selected:
            continue
        stem = view.get('reference_stem', view['name'])
        if not re.fullmatch(r'[a-z0-9-]{1,80}', stem):
            raise ValueError('Invalid reference filename stem')
        if (output/f'{stem}.provenance.json').exists():
            raise FileExistsError(f'{stem}: paid receipt already exists; reconcile it, do not retry')
    for view in cameras['views']:
        if view['name'] not in selected:
            continue
        stem = view.get('reference_stem', view['name'])
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
        if view.get('guide_mode') == 'fill-unpainted':
            prompt += '''
Image 2 is a render of the SAME mesh with the front texture already projected into this camera.
Keep its already colored areas EXACTLY: face, pupils, eyebrows, lips, skin and hair colors.
Fill only its blank neutral-gray surface regions. Continue the existing colors smoothly
across the boundary. The projected face is authoritative for feature positions and gaze;
do not redraw it to face the camera. The black background and all shapes remain fixed.'''
        prompt_path = output/f'{stem}.prompt.txt'
        prompt_path.write_text(prompt+'\n')
        print(f'Sunburst high: submitting {stem}; one ledgered call, no automatic retry', flush=True)
        with stage(f'Sunburst {stem}'):
            paint(output/f'{stem}.png', prompt, '1024x1024', images=[args.image, guide],
                  record=output/f'{stem}.provenance.json',
                  metadata=dict(prompt=prompt, guide_sha256=digest(guide),
                                reference_sha256=digest(args.image), camera=view), timeout=300)
    return 0


def coherent_guide(args):
    """Crop an existing guarded diagnostic render into a hashed paint-completion guide.

    This stage only reads completed files, verifies geometry and crops a saved image.
    It does not render, invoke Blender, allocate a model or make a paid call.
    """
    if args.from_model is None or args.from_contact is None:
        raise ValueError('Provide the completed --from-model and --from-contact')
    if not re.fullmatch(r'[a-z0-9-]{1,80}', args.reference_stem):
        raise ValueError('Invalid reference filename stem')
    if (args.output/'references'/f'{args.reference_stem}.provenance.json').exists():
        raise FileExistsError('Guide already has a paid receipt; preserve its inputs')
    proof = json.loads((args.from_model.parent/'pixel-match-report.json').read_text())
    if proof['output_sha256'] != digest(args.from_model):
        raise ValueError('Completed source model no longer matches its report')
    verify_geometry(args.mesh, args.from_model, load_module(VENDOR))
    path = args.output/'guides/cameras.json'
    cameras = json.loads(path.read_text())
    if cameras['reference_sha256'] != digest(args.image):
        raise ValueError('Identity reference changed')
    index = next(i for i, view in enumerate(cameras['views']) if view['name'] == args.guide_view)
    image = Image.open(args.from_contact).convert('RGB')
    if image.size != (1536, 816) or len(cameras['views']) != 8:
        raise ValueError('Expected the eight-camera 384-pixel diagnostic contact sheet')
    x, y = index%4*384, index//4*408
    target = args.output/'guides'/f'{args.reference_stem}-guide.png'
    image.crop((x, y, x+384, y+384)).save(target)
    view = cameras['views'][index]
    view.update(silhouette_guide=view.get('silhouette_guide', view['guide']),
                silhouette_guide_sha256=view.get('silhouette_guide_sha256', view['guide_sha256']))
    view.update(guide=target.name, guide_sha256=digest(target), guide_mode='fill-unpainted',
                reference_stem=args.reference_stem, derived_from_model_sha256=digest(args.from_model),
                derived_from_contact_sha256=digest(args.from_contact), contact_crop_pixels=[x,y,x+384,y+384])
    write(path, cameras)
    print(json.dumps(view), flush=True)
    return 0


def register_reference(args):
    """@cc [owner:fontanierh,label:correctness] bounded-reference-framing-correction
    Registration MUST only change uniform 2D scale and translation, preserving the raw paid
    output. It MUST reject scale outside 0.85–1.15, shifts beyond 12% of image width, and
    full-resolution silhouette IoU below 0.95. Input/output hashes and transform MUST be recorded.
    """
    cameras = json.loads((args.output/'guides/cameras.json').read_text())
    view = next(view for view in cameras['views'] if view['name'] == args.guide_view)
    stem = view.get('reference_stem', view['name'])
    if not re.fullmatch(r'[a-z0-9-]{1,80}', stem):
        raise ValueError('Invalid reference filename stem')
    source = args.output/'references'/f'{stem}.png'
    receipt = json.loads(source.with_suffix('.provenance.json').read_text())
    if (receipt.get('status') != 'done' or receipt.get('output_sha256') != digest(source)
            or receipt.get('camera') != view or receipt.get('reference_sha256') != digest(args.image)):
        raise ValueError('Paid source identity changed')
    guide = args.output/'guides'/view.get('silhouette_guide', view['guide'])
    if digest(guide) != view.get('silhouette_guide_sha256', view['guide_sha256']):
        raise ValueError('Silhouette guide changed')
    image = Image.fromarray(matte(Image.open(source)))
    target = np.asarray(Image.open(guide).convert('RGB')).max(axis=2) > 8
    mask = np.asarray(image)[..., 3] > 127
    if image.size[0] != image.size[1] or mask.shape != target.shape:
        raise ValueError('Use square, equally sized source and silhouette images')
    boxes = []
    for values in (mask, target):
        ys, xs = np.nonzero(values)
        if len(xs) == 0:
            raise ValueError('Empty registration silhouette')
        boxes.append((xs.min(), ys.min(), xs.max(), ys.max()))
    sb, tb = boxes
    source_center = np.array([(sb[0]+sb[2])/2, (sb[1]+sb[3])/2])
    target_center = np.array([(tb[0]+tb[2])/2, (tb[1]+tb[3])/2])
    scale_y = (tb[3]-tb[1])/max(sb[3]-sb[1], 1)
    small = Image.fromarray((mask*255).astype('uint8')).resize((128,128), Image.Resampling.NEAREST)
    target_small = np.asarray(Image.fromarray((target*255).astype('uint8')).resize((128,128), Image.Resampling.NEAREST)) > 127
    ratio = image.width/128
    best = (-1., None, None)
    for scale in np.linspace(scale_y*.94, scale_y*1.06, 13):
        for dx in range(-24,25,8):
            for dy in range(-24,25,8):
                shift = target_center-scale*source_center+np.array([dx,dy])*image.width/1024
                inverse = (1/scale,0,-shift[0]/scale/ratio,0,1/scale,-shift[1]/scale/ratio)
                moved = np.asarray(small.transform((128,128), Image.Transform.AFFINE,
                                                   inverse, Image.Resampling.NEAREST)) > 127
                iou = float((moved & target_small).sum()/max((moved | target_small).sum(), 1))
                if iou > best[0]:
                    best = (iou, float(scale), shift)
    _, scale, shift = best
    if not .85 <= scale <= 1.15 or np.any(np.abs(shift) > image.width*.12):
        raise ValueError('Reference needs more than a small framing correction; reject its pose')
    inverse = (1/scale,0,-shift[0]/scale,0,1/scale,-shift[1]/scale)
    registered = image.transform(image.size, Image.Transform.AFFINE, inverse, Image.Resampling.BICUBIC)
    aligned = np.asarray(registered)[...,3] > 127
    after = float((aligned & target).sum()/max((aligned | target).sum(), 1))
    if after < .95:
        raise ValueError(f'Framing correction still fails silhouette check: {after:.4f} < .95')
    output = source.with_name(f'{stem}-registered.png')
    registered.save(output)
    record = dict(status='complete', raw_sha256=digest(source), silhouette_sha256=digest(guide),
                  tool_sha256=digest(Path(__file__)), output=output.name, output_sha256=digest(output),
                  uniform_scale=scale, translation_pixels=shift.tolist(),
                  silhouette_iou_before=float((mask & target).sum()/max((mask | target).sum(), 1)),
                  silhouette_iou_after=after, method='Uniform 2D scale and translation; no shape warp or mesh changes')
    write(source.with_suffix('.registration.json'), record)
    print(json.dumps(record), flush=True)
    return 0


def camera_set(folder, reference):
    records = json.loads((folder/'uv-comparison.json').read_text())
    model = folder/records[0]['name']/'clay-uv.glb'
    cameras = json.loads((folder/'guides/cameras.json').read_text())
    if cameras['mesh_sha256'] != digest(model) or cameras['reference_sha256'] != digest(reference):
        raise ValueError('Guide inputs no longer match')
    return model, cameras


def projection_fit(folder, camera, generated):
    """Check a frozen photo against the new mesh's independently calibrated guide."""
    guide = folder/'guides'/camera['guide']
    if digest(guide) != camera['guide_sha256']:
        raise ValueError('Target projection guide changed')
    target = np.asarray(Image.open(guide).convert('RGB')).max(axis=2) > 8
    mask = generated[..., 3] > 127
    if target.shape != mask.shape:
        raise ValueError('Target projection guide and reference dimensions differ')
    iou = float((target & mask).sum()/max((target | mask).sum(), 1))
    if iou < .95:
        raise ValueError(f'{camera["name"]}: target silhouette IoU {iou:.4f} below .95; reject transfer')
    return dict(target_guide_sha256=digest(guide), target_silhouette_iou=iou)


def paint_variants(args):
    """@cc [owner:fontanierh,label:correctness] texture-transfer-identifies-both-meshes
    Reusing photographs on a new native mesh MUST retain their original generation mesh,
    guide and paid camera identity. The new projection mesh/camera MUST be identified
    separately, and both source and target silhouette checks MUST meet the unchanged .95
    threshold. Transfer MUST NOT change geometry, alter receipts or imply multiview geometry conditioning.
    """
    from meshaxiom_pixel_match import paint
    pm = load_module(VENDOR)
    # Keep the exact pinned rasterizer, with smaller triangle batches to bound fragment arrays at 4K.
    pm.rasterize = partial(pm.rasterize, chunk=256)
    model, cameras = camera_set(args.output, args.image)
    reference_root = getattr(args, 'reference_set', None) or args.output
    generation_model, generation_cameras = camera_set(reference_root, args.image)
    generation_views = {view['name']: view for view in generation_cameras['views']}
    anchor = next(view for view in cameras['views'] if view['yaw'] == 60 and view['pitch'] == -5)
    selected = set(args.views.split(','))
    views = [] if anchor['name'] in selected else [dict(
        name='original', image=str(args.image), image_sha256=digest(args.image),
        transform_matrix=anchor['transform_matrix'], camera_angle_x=anchor['camera_angle_x'])]
    checks = []
    for target_view in cameras['views']:
        if target_view['name'] not in selected:
            continue
        view = generation_views[target_view['name']]
        if (view['yaw'], view['pitch']) != (target_view['yaw'], target_view['pitch']):
            raise ValueError('Generation and projection camera labels differ')
        stem = view.get('reference_stem', view['name'])
        if not re.fullmatch(r'[a-z0-9-]{1,80}', stem):
            raise ValueError('Invalid reference filename stem')
        path = reference_root/'references'/f'{stem}.png'
        receipt = json.loads(path.with_suffix('.provenance.json').read_text())
        if receipt.get('status') != 'done' or receipt.get('output_sha256') != digest(path):
            raise ValueError('Generated reference differs from its paid receipt')
        if (receipt.get('guide_sha256') != view['guide_sha256']
                or receipt.get('reference_sha256') != digest(args.image) or receipt.get('camera') != view):
            raise ValueError('Generated reference recipe differs from the guide manifest')
        guide = reference_root/'guides'/view['guide']
        if digest(guide) != view['guide_sha256']:
            raise ValueError('Geometry guide changed before projection')
        silhouette_guide = reference_root/'guides'/view.get('silhouette_guide', view['guide'])
        if digest(silhouette_guide) != view.get('silhouette_guide_sha256', view['guide_sha256']):
            raise ValueError('Silhouette guide changed')
        raw_sha256 = digest(path)
        registration_path = path.with_suffix('.registration.json')
        registration = None
        if registration_path.exists():
            registration = json.loads(registration_path.read_text())
            derived = path.with_name(f'{stem}-registered.png')
            if (registration.get('status') != 'complete' or registration.get('raw_sha256') != raw_sha256
                    or registration.get('silhouette_sha256') != digest(silhouette_guide)
                    or registration.get('output') != derived.name
                    or registration.get('output_sha256') != digest(derived)):
                raise ValueError('Registered reference inputs or output changed')
            path = derived
        generated = matte(Image.open(path))
        target = np.asarray(Image.open(silhouette_guide).convert('RGB')).max(axis=2) > 8
        mask = generated[..., 3] > 127
        iou = float((target & mask).sum()/max((target | mask).sum(), 1))
        if iou < .95:
            raise ValueError(f'{view["name"]}: guide silhouette IoU {iou:.4f} below .95; reject view')
        transfer = projection_fit(args.output, target_view, generated) if reference_root != args.output else {}
        checks.append(dict(name=view['name'], silhouette_iou=iou, image_sha256=digest(path),
                           guide_sha256=view['guide_sha256'], guide_mode=view.get('guide_mode', 'clay'),
                           reference_stem=stem, registration=registration, **transfer))
        views.append(dict(name=view['name'], image=str(path), image_sha256=digest(path),
                          raw_image_sha256=raw_sha256,
                          registration_sha256=digest(registration_path) if registration else None,
                          reference_generation=dict(mesh_sha256=digest(generation_model),
                              guide_sha256=view['guide_sha256'], camera=view,
                              receipt_sha256=digest((reference_root/'references'/f'{stem}.provenance.json'))),
                          projection_mesh_sha256=digest(model),
                          transform_matrix=target_view['transform_matrix'],
                          camera_angle_x=target_view['camera_angle_x'], **transfer))
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
              camera_angle_x=anchor['camera_angle_x'],
              calibration='Target mesh silhouette camera; generation cameras retained separately; no mesh fitting'))
        manifest = folder/'views.json'
        used_views = [view for view in views if view['name'] == anchor['name']] if variant == 'guided-single' else views
        if variant in ('front-first', '4k'):
            priorities = [anchor['name'], 'yaw120-pitch-5', 'yaw0-pitch-5', 'yaw180-pitch-5',
                          'yaw240-pitch-5', 'yaw300-pitch-5', 'yaw60-pitch55', 'yaw240-pitch-40']
            used_views = sorted(used_views, key=lambda view: priorities.index(view['name'])
                                if view['name'] in priorities else len(priorities))
        if not used_views:
            raise ValueError('Guided-single variant requires the generated front camera')
        write(manifest, dict(mesh_sha256=digest(source), views=[
            {**view, 'projection_mesh_sha256': digest(source),
             'image': os.path.relpath(view['image'], folder)} for view in used_views]))
        recipe = SimpleNamespace(mesh=source, image=args.image, output=folder, module=VENDOR,
                                 views=None if variant == 'single' else manifest,
                                 blend=('weighted' if variant in ('single', 'guided-single', 'weighted')
                                        else 'best-angle' if variant == 'best-angle' else 'front-first'))
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
    parser.add_argument('stage', choices=['prepare', 'references', 'paint', 'guide', 'register'])
    parser.add_argument('--mesh', type=Path, required=True)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--blender', type=Path, default=Path('/Applications/Blender.app/Contents/MacOS/Blender'))
    parser.add_argument('--views', default='yaw0-pitch-5,yaw60-pitch-5,yaw120-pitch-5,yaw180-pitch-5,yaw240-pitch-5,yaw300-pitch-5,yaw60-pitch55,yaw240-pitch-40')
    parser.add_argument('--variants', default='single,guided-single,weighted,best-angle,front-first,4k')
    parser.add_argument('--report', type=Path)
    parser.add_argument('--from-model', type=Path)
    parser.add_argument('--from-contact', type=Path)
    parser.add_argument('--reference-set', type=Path,
                        help='Reuse verified photos from an earlier mesh; independently check new guide overlap')
    parser.add_argument('--guide-view', default='yaw120-pitch-5')
    parser.add_argument('--reference-stem', default='yaw120-coherent')
    parser.add_argument('--memory-gib', type=int, choices=range(4, 11), default=10,
                        help='Aggregate CPU preparation/painting ceiling, 4–10 GiB')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.stage == 'references':
        return references(args)
    if args.stage == 'guide':
        return coherent_guide(args)
    if args.stage == 'register':
        return register_reference(args)
    if set(args.variants.split(',')) - {'single', 'guided-single', 'weighted', 'best-angle', 'front-first', '4k'}:
        parser.error('Unknown texture variant')
    if args.worker:
        return (prepare if args.stage == 'prepare' else paint_variants)(args)
    if args.report is None or args.report.exists():
        parser.error('Use a new --report directory for native preparation')
    from atelier.harness.safety.guarded import run
    return run([sys.executable, '-u', str(Path(__file__).resolve()), '--worker', *argv],
               args.report, timeout=900, purpose=f'Fixed-geometry head quality: {args.stage}',
               limit_gib=args.memory_gib, aggregate_tree=True, progress=20)


if __name__ == '__main__':
    raise SystemExit(main())
