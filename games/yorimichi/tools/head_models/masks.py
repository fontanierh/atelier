"""Workers for rendered-view SAM2 masks; no manual prompts or mesh deformation."""
import argparse
import copy
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

import numpy as np
from PIL import Image
from retopo import digest, fresh, progress, raster_uv, surface_median, verify_export

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

MODEL = 'facebook/sam2.1-hiera-tiny'
REVISION = 'de431c4043854a71d8101e17995dfe596bf101a5'


def setup(args):
    py = args.root/'sam-venv/bin/python'
    commands = [] if py.exists() else [['uv', 'venv', '--python', '3.12', str(py.parents[1])]]
    commands += [['uv', 'pip', 'install', '--python', str(py), '--only-binary', ':all:',
        'torch==2.7.1', 'torchvision==0.22.1', 'transformers==4.57.1', 'numpy==2.2.6',
        'scipy==1.15.3', 'pillow==12.2.0', 'safetensors==0.6.2', 'huggingface-hub==0.36.0'],
        [str(py), '-u', str(Path(__file__).resolve()), 'download', '--root', str(args.root)]]
    for command in commands:
        with progress('SAM2 setup: '+ ' '.join(command)):
            subprocess.run(command, check=True)
    with (args.root/'sam-packages.txt').open('w') as out:
        subprocess.run(['uv', 'pip', 'freeze', '--python', str(py)], stdout=out, check=True)


def download(args):
    os.environ['HF_HUB_DISABLE_XET'] = '1'
    from huggingface_hub import snapshot_download
    folder = args.root/'sam2-tiny'
    snapshot_download(repo_id=MODEL, revision=REVISION, local_dir=str(folder), max_workers=3,
        allow_patterns=['config.json', 'preprocessor_config.json', 'processor_config.json', 'model.safetensors', 'README.md'])
    files = {p.name: dict(bytes=p.stat().st_size, sha256=digest(p)) for p in folder.iterdir() if p.is_file()}
    (args.root/'sam2-source.json').write_text(json.dumps(
        dict(repo=MODEL, revision=REVISION, license='Apache-2.0', files=files), indent=2)+'\n')
    print('Pinned SAM2 checkpoint ready:', files['model.safetensors']['bytes'], 'bytes', flush=True)


def model_parts(path):
    from meshaxiom_pixel_match import load_module
    from meshaxiom_quality import VENDOR
    pm = load_module(VENDOR)
    document, binary = pm._split_glb(path.read_bytes())
    if len(document.get('images', [])) != 1 or document['images'][0] != dict(bufferView=4, mimeType='image/png'):
        raise ValueError('Expected the single embedded texture from head_retopo.py')
    view = document['bufferViews'][4]
    texture = np.array(Image.open(io.BytesIO(binary[view['byteOffset']:view['byteOffset']+view['byteLength']])).convert('RGB'))
    return pm, document, binary, texture


def frame(vertices):
    positions = vertices[:, [0, 2, 1]].copy()
    positions[:, 2] *= -1
    lo, hi = positions.min(0), positions.max(0)
    height = float(hi[1]-lo[1])
    if height <= 0:
        raise ValueError('Head has no height')
    origin = np.array([(lo[0]+hi[0])/2, lo[1], (lo[2]+hi[2])/2])
    return ((positions-origin)/height).astype('float32'), dict(origin=origin.tolist(), height=height)


def camera(yaw, pitch, size=768):
    y, p = np.deg2rad([yaw, pitch])
    target = np.array([0., .5, 0.])
    eye = target+2.2*np.array([np.sin(y)*np.cos(p), np.sin(p), np.cos(y)*np.cos(p)])
    forward = (target-eye)/np.linalg.norm(target-eye)
    right = np.cross(forward, [0., 1., 0.]); right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    return dict(yaw=yaw, pitch=pitch, eye=eye.tolist(), forward=forward.tolist(), right=right.tolist(),
                up=up.tolist(), fov=34., width=size, height=size)


def camera_rays(view):
    width, height = view['width'], view['height']
    yy, xx = np.mgrid[:height, :width]
    scale = np.tan(np.deg2rad(view['fov']/2))
    x = (2*(xx+.5)/width-1)*scale*width/height
    y = (1-2*(yy+.5)/height)*scale
    rays = np.empty((height, width, 6), dtype='float32')
    rays[..., :3] = view['eye']
    rays[..., 3:] = (np.asarray(view['forward'])+x[..., None]*view['right']+y[..., None]*view['up'])
    return rays


def project_points(points, view):
    delta = points-np.asarray(view['eye'])
    depth = delta@np.asarray(view['forward'])
    scale = np.tan(np.deg2rad(view['fov']/2))
    x = (delta@np.asarray(view['right']))/np.maximum(depth, 1e-20)/scale*view['height']/view['width']
    y = (delta@np.asarray(view['up']))/np.maximum(depth, 1e-20)/scale
    return np.stack(((x+1)*view['width']/2, (1-y)*view['height']/2), axis=1), depth


def views(args):
    import open3d as o3d
    from vertex_bake import linear, srgb
    fresh(args.output)
    before = digest(args.model)
    with np.load(args.source, allow_pickle=False) as data:
        vertices, faces, uv = data['vertices'], data['faces'], data['uv_corners']
    verify_export(args.model.read_bytes(), vertices, faces)
    _, _, _, texture = model_parts(args.model)
    texture = linear(texture.astype('float32')/255)
    positions, normalization = frame(vertices)
    scene = o3d.t.geometry.RaycastingScene(nthreads=3)
    scene.add_triangles(o3d.core.Tensor.from_numpy(positions), o3d.core.Tensor.from_numpy(faces))
    records = []
    for index, (yaw, pitch) in enumerate([(0, -5), (60, -5), (120, -5), (180, -5),
                                         (240, -5), (300, -5), (60, 55), (240, -40)]):
        view = camera(yaw-90, pitch)
        result = scene.cast_rays(o3d.core.Tensor.from_numpy(camera_rays(view)), nthreads=3)
        depth, ids, bary = result['t_hit'].numpy(), result['primitive_ids'].numpy(), result['primitive_uvs'].numpy()
        occupied = np.isfinite(depth)
        weight = np.stack((1-bary[occupied].sum(1), bary[occupied, 0], bary[occupied, 1]), axis=1)
        coords = (uv[ids[occupied]]*weight[:, :, None]).sum(1)
        xy = coords*np.array([texture.shape[1], texture.shape[0]])-.5
        xy = np.clip(xy, 0, [texture.shape[1]-1, texture.shape[0]-1])
        lo = np.floor(xy).astype(int); hi = np.minimum(lo+1, [texture.shape[1]-1, texture.shape[0]-1])
        fraction = xy-lo
        rgb = (texture[lo[:, 1], lo[:, 0]]*(1-fraction[:, 0, None])*(1-fraction[:, 1, None])
             + texture[lo[:, 1], hi[:, 0]]*fraction[:, 0, None]*(1-fraction[:, 1, None])
             + texture[hi[:, 1], lo[:, 0]]*(1-fraction[:, 0, None])*fraction[:, 1, None]
             + texture[hi[:, 1], hi[:, 0]]*fraction[:, 0, None]*fraction[:, 1, None])
        image = np.full((*occupied.shape, 4), 128, dtype='uint8'); image[..., 3] = occupied*255
        image[occupied, :3] = np.clip(srgb(rgb)*255+.5, 0, 255).astype('uint8')
        name = f'view{index}'
        Image.fromarray(image).save(args.output/(name+'.png'))
        np.savez_compressed(args.output/(name+'-depth.npz'), depth=depth)
        records.append(dict(name=name, camera=view, image_sha256=digest(args.output/(name+'.png')),
                            depth_sha256=digest(args.output/(name+'-depth.npz'))))
        print(f'Segmentation view {index+1}/8 prepared', flush=True)
    if digest(args.model) != before:
        raise ValueError('Segmentation view rendering changed the model')
    (args.output/'views.json').write_text(json.dumps(dict(model_sha256=before, mesh_sha256=digest(args.source),
        normalization=normalization, views=records), indent=2)+'\n')


def seeds(mask, count):
    from scipy import ndimage
    distance = ndimage.distance_transform_edt(mask)
    yy, xx = np.mgrid[:mask.shape[0], :mask.shape[1]]
    separation = np.ones(mask.shape, dtype='float32')
    points = []
    for _ in range(count):
        score = np.sqrt(distance)*separation
        y, x = np.unravel_index(score.argmax(), score.shape)
        if score[y, x] <= 0:
            break
        points.append([int(x), int(y)])
        current = np.sqrt((xx-x)**2+(yy-y)**2)
        separation = current if len(points) == 1 else np.minimum(separation, current)
    return points


def priors(rgb, occupied, hair_palette='navy'):
    from scipy import ndimage
    from scipy.spatial import ConvexHull, QhullError
    values = rgb.astype('float32')/255
    chroma = values.max(2)-values.min(2)
    skin = ((values[..., 0] > .45) & (values[..., 0] > values[..., 1]*1.15)
            & (values[..., 0] > values[..., 2]*1.4) & occupied)
    if hair_palette == 'navy':
        hair_prior = (values.max(2) < .4) & (values[..., 2] > values[..., 0]*.95) & occupied
    elif hair_palette == 'grey':
        # Kiyo's hair is neutral silver-grey, not the skater's navy. The skin
        # hull below protects detached brows and eye shapes as features.
        hair_prior = ((chroma < .12) & (values.max(2) > .24) & (values.max(2) < .98) & occupied)
    else:
        raise ValueError('Unsupported hair palette')
    labels, _ = ndimage.label(hair_prior, structure=np.ones((3, 3)))
    counts = np.bincount(labels.ravel()); counts[0] = 0
    hair = labels == counts.argmax() if counts.max() else np.zeros_like(skin)
    # Skin's convex support includes facial features; detached hair components
    # outside it (e.g. a ponytail or low bun) belong to hair rather than brows.
    samples = np.argwhere(skin)
    inside = np.zeros_like(skin)
    if len(samples) >= 3:
        try:
            hull = ConvexHull(samples[::max(1, len(samples)//4000)])
            yy, xx = np.mgrid[:skin.shape[0], :skin.shape[1]]
            inside = np.ones(skin.shape, dtype=bool)
            for a, b, c in hull.equations:
                inside &= a*yy+b*xx+c <= 1
        except QhullError:
            inside = ndimage.binary_fill_holes(skin)
    for label in np.flatnonzero(counts > 20):
        component = labels == label
        if np.count_nonzero(component & inside) < component.sum()*.5:
            hair |= component
    # A brow can touch a bang through a few dark pixels. Protect dark pixels
    # inside the skin hull even when connected to the main hair component.
    # This also leaves some bangs unknown: conservative repainting is intended.
    dark_features = (values.max(2) < .4) & occupied & (~hair | inside)
    neutral = ((values.min(2) > .45) & (chroma < .25) & occupied & ~hair)
    features = ndimage.binary_dilation(dark_features | neutral, iterations=2)
    return skin & ~features, hair & ~features, features & occupied


def infer(args):
    from scipy import ndimage
    os.environ['PYTORCH_ENABLE_MPS_FALLBACK'] = '1'
    import torch
    from transformers import Sam2Model, Sam2Processor
    fresh(args.output)
    torch.set_num_threads(3); torch.set_num_interop_threads(3)
    device = 'mps' if args.device == 'auto' and torch.backends.mps.is_available() else args.device
    if device == 'auto': device = 'cpu'
    if device == 'mps': torch.mps.set_per_process_memory_fraction(.15)
    proof = json.loads((args.root/'sam2-source.json').read_text())
    if proof['repo'] != MODEL or proof['revision'] != REVISION:
        raise ValueError('Unpinned SAM2 source')
    for name, record in proof['files'].items():
        if digest(args.root/'sam2-tiny'/name) != record['sha256']:
            raise ValueError('SAM2 file changed: '+name)
    model, loading = Sam2Model.from_pretrained(args.root/'sam2-tiny', output_loading_info=True)
    if loading['missing_keys'] or loading.get('mismatched_keys'):
        raise ValueError('SAM2 image weights were not fully loaded')
    model = model.to(device).eval()
    processor = Sam2Processor.from_pretrained(args.root/'sam2-tiny')
    manifest = json.loads((args.views/'views.json').read_text())
    records = []
    for view in manifest['views']:
        if not re.fullmatch(r'view[0-9]{1,2}', view['name']):
            raise ValueError('Unexpected view name')
        image_path = args.views/(view['name']+'.png')
        if digest(image_path) != view['image_sha256']:
            raise ValueError('Prepared image changed')
        rgba = np.array(Image.open(image_path).convert('RGBA'))
        occupied = rgba[..., 3] > 250
        rgb = rgba[..., :3].copy(); rgb[~occupied] = 128
        skin, hair, features = priors(rgb, occupied, args.hair_palette)
        skin_points, hair_points, feature_points = seeds(skin, 6), seeds(hair, 6), seeds(features, 6)
        masks, prompts = {}, []
        for name, positive, negative, prior in [('skin', skin_points, hair_points+feature_points, skin),
                                                ('hair', hair_points, skin_points+feature_points, hair)]:
            if not positive:
                masks[name] = np.zeros_like(occupied)
                continue
            points, labels = positive+negative, [1]*len(positive)+[0]*len(negative)
            inputs = processor(images=Image.fromarray(rgb), input_points=[[points]], input_labels=[[labels]], return_tensors='pt').to(device)
            with torch.inference_mode():
                output = model(**inputs, multimask_output=True)
            proposals = processor.post_process_masks(output.pred_masks.cpu(), inputs['original_sizes'].cpu())[0][0].numpy()
            scores = output.iou_scores[0, 0].detach().cpu().numpy()
            candidates = []
            for index, proposal in enumerate(proposals):
                mask = ndimage.binary_fill_holes(ndimage.binary_closing(proposal & occupied, iterations=2)) & occupied & ~features
                agreement = np.count_nonzero(mask & prior)/max(np.count_nonzero(mask | prior), 1)
                missed = sum(not mask[y, x] for x, y in positive)/len(positive)
                violated = sum(mask[y, x] for x, y in negative)/max(len(negative), 1)
                candidates.append((agreement+.2*float(scores[index])-2*missed-2*violated, index, mask))
            score, selected, mask = max(candidates, key=lambda row: row[0])
            masks[name] = mask
            prompts.append(dict(label=name, positive=positive, negative=negative,
                                candidate=selected, model_scores=scores.tolist(), constraint_score=score))
        masks['hair'] &= ~skin
        masks['skin'] &= ~masks['hair'] & ~features
        for name, mask in masks.items():
            Image.fromarray(mask.astype('uint8')*255).save(args.output/(view['name']+'-'+name+'.png'))
        overlay = rgb.copy()
        overlay[masks['skin']] = (.5*overlay[masks['skin']]+[127, 35, 35]).clip(0, 255).astype('uint8')
        overlay[masks['hair']] = (.5*overlay[masks['hair']]+[35, 55, 127]).clip(0, 255).astype('uint8')
        Image.fromarray(overlay).save(args.output/(view['name']+'-overlay.png'))
        records.append(dict(**view, prompts=prompts, masks={name: digest(args.output/(view['name']+'-'+name+'.png')) for name in masks}))
        depth_path = args.views/(view['name']+'-depth.npz')
        if digest(depth_path) != view['depth_sha256']:
            raise ValueError('Prepared depth changed')
        shutil.copyfile(depth_path, args.output/depth_path.name)
        print(f'SAM2 completed {view["name"]}: skin {masks["skin"].sum():,}, hair {masks["hair"].sum():,}', flush=True)
    (args.output/'masks.json').write_text(json.dumps(dict(model_sha256=manifest['model_sha256'],
        mesh_sha256=manifest['mesh_sha256'], normalization=manifest['normalization'],
        source_views_sha256=digest(args.views/'views.json'), source_views=str(args.views.name),
        sam2_revision=REVISION, sam2_weights_sha256=proof['files']['model.safetensors']['sha256'],
        device=device, views=records, limitation='Automatically prompted masks, not semantic ground truth'), indent=2)+'\n')


def replace_image(pm, document, binary, pixels):
    """@cc [owner:fontanierh,label:correctness] masked-paint-changes-image-only
    Repainting MUST retain every non-image binary byte and every scene, material,
    accessor and primitive binding. Only the final PNG and its buffer lengths MAY
    change. Unexpected trailing data or additional images MUST reject.
    """
    if len(document['bufferViews']) != 5 or document['images'] != [dict(bufferView=4, mimeType='image/png')]:
        raise ValueError('Use the known single-texture bake layout')
    view = document['bufferViews'][4]
    start, end = view['byteOffset'], view['byteOffset']+view['byteLength']
    if len(binary)-end not in range(4) or any(binary[end:]):
        raise ValueError('Unexpected data after texture')
    encoded = io.BytesIO()
    Image.fromarray(pixels).save(encoded, format='PNG')
    output_binary = binary[:start]+encoded.getvalue()
    output_document = copy.deepcopy(document)
    output_document['bufferViews'][4]['byteLength'] = len(encoded.getvalue())
    output_document['buffers'][0]['byteLength'] = len(output_binary)
    comparison = copy.deepcopy(output_document)
    comparison['bufferViews'][4]['byteLength'] = view['byteLength']
    comparison['buffers'][0]['byteLength'] = document['buffers'][0]['byteLength']
    if comparison != document or output_binary[:start] != binary[:start]:
        raise ValueError('Repainting changed protected model data')
    return pm._join_glb(output_document, output_binary)


def project(args):
    from scipy import ndimage
    from scipy.spatial import cKDTree
    fresh(args.output)
    started = time.monotonic()
    model_before, mesh_before = digest(args.model), digest(args.source)
    manifest = json.loads((args.views/'masks.json').read_text())
    if manifest['model_sha256'] != model_before or manifest['mesh_sha256'] != mesh_before or manifest['sam2_revision'] != REVISION:
        raise ValueError('Masks were generated for different model/UV data')
    with np.load(args.source, allow_pickle=False) as data:
        vertices, faces, uv = data['vertices'], data['faces'], data['uv_corners']
    baseline = verify_export(args.model.read_bytes(), vertices, faces)
    pm, document, binary, texture = model_parts(args.model)
    if texture.shape[0] != texture.shape[1]:
        raise ValueError('Expected square baked atlas')
    positions, normalization = frame(vertices)
    if normalization != manifest['normalization']:
        raise ValueError('Mask camera normalization differs from the model')
    owner, bary = raster_uv(uv, texture.shape[0])
    occupied = owner >= 0
    yy, xx = np.nonzero(occupied)
    skin_vote, hair_vote, total = [np.zeros(len(yy), dtype='float32') for _ in range(3)]
    normals = np.cross(positions[faces[:, 1]]-positions[faces[:, 0]], positions[faces[:, 2]]-positions[faces[:, 0]])
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-15)
    for record in manifest['views']:
        name = record['name']
        if not re.fullmatch(r'view[0-9]{1,2}', name):
            raise ValueError('Unexpected view name')
        depth_path = args.views/(name+'-depth.npz')
        if digest(depth_path) != record['depth_sha256']:
            raise ValueError('Mask visibility depth changed')
        with np.load(depth_path, allow_pickle=False) as data:
            depth = data['depth']
        masks = {}
        for label in ('skin', 'hair'):
            path = args.views/(name+'-'+label+'.png')
            if digest(path) != record['masks'][label]:
                raise ValueError('Inference mask changed')
            masks[label] = np.array(Image.open(path).convert('L')) > 127
        view = record['camera']
        if depth.shape != (view['height'], view['width']) or any(mask.shape != depth.shape for mask in masks.values()):
            raise ValueError('Mask/depth camera sizes differ')
        for first in range(0, len(yy), 65536):
            y, x = yy[first:first+65536], xx[first:first+65536]
            face = owner[y, x]
            points = (positions[faces[face]]*bary[y, x, :, None]).sum(1)
            screen, z = project_points(points, view)
            inside = ((z > 0) & (screen[:, 0] >= 0) & (screen[:, 0] < view['width'])
                      & (screen[:, 1] >= 0) & (screen[:, 1] < view['height']))
            sample = np.floor(np.clip(screen, [0, 0], [view['width']-1, view['height']-1])).astype(int)
            sx, sy = sample[:, 0], sample[:, 1]
            visible = inside & np.isfinite(depth[sy, sx]) & (np.abs(depth[sy, sx]-z) < .005)
            direction = np.asarray(view['eye'])-points
            direction /= np.maximum(np.linalg.norm(direction, axis=1, keepdims=True), 1e-15)
            weight = ((normals[face]*direction).sum(1)**2*visible).astype('float32')
            stop = first+len(y)
            total[first:stop] += weight
            skin_vote[first:stop] += weight*masks['skin'][sy, sx]
            hair_vote[first:stop] += weight*masks['hair'][sy, sx]
        print('Projected semantic view:', name, flush=True)
    skin_fraction, hair_fraction = skin_vote/np.maximum(total, 1e-15), hair_vote/np.maximum(total, 1e-15)
    skin = np.zeros_like(occupied)
    hair = np.zeros_like(occupied)
    skin[yy, xx] = (total > .05) & (skin_fraction >= .6) & (skin_fraction > hair_fraction+.1)
    hair[yy, xx] = (total > .05) & (hair_fraction >= .6) & (hair_fraction > skin_fraction+.1)
    protected = occupied & ~skin & ~hair
    for name, mask in [('skin', skin), ('hair', hair), ('features-and-unknown', protected), ('occupied', occupied)]:
        Image.fromarray(mask.astype('uint8')*255).save(args.output/(name+'-mask.png'))
    with np.load(args.color_cloud, allow_pickle=False) as data:
        support, colors = data['positions'], data['colors']
    if (support.ndim != 2 or support.shape[1] != 3 or colors.shape != support.shape
            or not all(np.isfinite(a).all() for a in (support, colors))
            or colors.min() < 0 or colors.max() > 1):
        raise ValueError('Invalid repaint color support')
    values = texture.astype('float32')/255
    warm = (colors[:, 0] > colors[:, 1]*1.15) & (colors[:, 0] > colors[:, 2]*1.35) & (colors[:, 0] > .2)
    if args.hair_palette == 'navy':
        hair_colors = (colors.max(1) < .4) & (colors[:, 2] > colors[:, 0]*.95)
        skin_contamination = (values.max(2) < .4) & (values[..., 2] > values[..., 0]*.95)
    elif args.hair_palette == 'grey':
        # Kiyo-specific neutral silver-grey hair. The indigo hat is separate
        # authored geometry and never reaches this bake.
        hair_colors = ((colors.max(1)-colors.min(1) < .12)
                       & (colors.max(1) > .24) & (colors.max(1) < .98))
        skin_contamination = ((values.max(2) < .42) & (values.max(2)-values.min(2) < .12))
    else:
        raise ValueError('Unsupported hair palette')
    skin_target, hair_target = skin.copy(), hair.copy()
    if args.paint_mode == 'repair':
        skin_target &= skin_contamination
        hair_target &= (values[..., 0] > values[..., 1]*1.15) & (values[..., 0] > values[..., 2]*1.35)
    painted = texture.copy()
    for name, target, candidates in [('skin', skin_target, warm), ('hair', hair_target, hair_colors)]:
        y, x = np.nonzero(target)
        if not len(y):
            continue
        if candidates.sum() < 8:
            raise ValueError('Insufficient source material support: '+name)
        tree = cKDTree(support[candidates])
        source_colors = colors[candidates]
        for first in range(0, len(y), 32768):
            cy, cx = y[first:first+32768], x[first:first+32768]
            points = (vertices[faces[owner[cy, cx]]]*bary[cy, cx, :, None]).sum(1)
            replacement, _ = surface_median(tree, source_colors, points, 8)
            painted[cy, cx] = np.clip(replacement*255+.5, 0, 255).astype('uint8')
        print(f'Automatic {name} repaint: {len(y):,} texels', flush=True)
    if not np.array_equal(painted[protected], texture[protected]):
        raise ValueError('Repainting changed protected feature/unknown texels')
    nearest = ndimage.distance_transform_edt(~occupied, return_distances=False, return_indices=True)
    painted[~occupied] = painted[nearest[0][~occupied], nearest[1][~occupied]]
    output = replace_image(pm, document, binary, painted)
    verified = verify_export(output, vertices, faces)
    if verified != baseline:
        raise ValueError('Repaint changed geometry, normal, UV or index streams')
    (args.output/'head.glb').write_bytes(output)
    Image.fromarray(painted).save(args.output/'basecolor.png')
    regions = np.zeros_like(texture)
    regions[occupied] = [230, 180, 60]
    regions[skin] = [255, 150, 150]
    regions[hair] = [80, 120, 255]
    regions[~occupied] = regions[nearest[0][~occupied], nearest[1][~occupied]]
    (args.output/'segments.glb').write_bytes(replace_image(pm, document, binary, regions))
    Image.fromarray(regions).save(args.output/'regions.png')
    if digest(args.model) != model_before or digest(args.source) != mesh_before:
        raise ValueError('Mask projection changed retained input artifacts')
    report = dict(method='Automatic color prompts + eight-view SAM2 + visibility-weighted UV fusion',
        paint_mode=args.paint_mode, input_sha256=model_before, output_sha256=digest(args.output/'head.glb'),
        mesh_sha256=mesh_before, masks_manifest_sha256=digest(args.views/'masks.json'),
        color_cloud_sha256=digest(args.color_cloud), sam2_revision=REVISION,
        sam2_weights_sha256=manifest['sam2_weights_sha256'], **verified,
        skin_texels=int(skin.sum()), hair_texels=int(hair.sum()), protected_texels=int(protected.sum()),
        painted_skin_texels=int(skin_target.sum()), painted_hair_texels=int(hair_target.sum()),
        protected_texture_sha256=__import__('hashlib').sha256(texture[protected].tobytes()).hexdigest(),
        geometry_normals_uv_indices_identical=True, seconds=time.monotonic()-started,
        limitations='Approximate palette-prompted masks; gold regions protect features and unknown surfaces. Inspect before reuse.')
    (args.output/'masks.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage', choices=['setup', 'download', 'views', 'infer', 'project'])
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--source', type=Path)
    p.add_argument('--model', type=Path)
    p.add_argument('--views', type=Path)
    p.add_argument('--color-cloud', type=Path)
    p.add_argument('--output', type=Path)
    p.add_argument('--device', choices=['auto', 'cpu', 'mps'], default='auto')
    p.add_argument('--paint-mode', choices=['repair', 'full'], default='repair')
    p.add_argument('--hair-palette', choices=['navy', 'grey'], default='navy')
    args = p.parse_args()
    return globals()[args.stage](args)


if __name__ == '__main__':
    main()
