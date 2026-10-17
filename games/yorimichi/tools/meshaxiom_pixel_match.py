"""Calibrate and project a Sunburst reference with the repo's pinned Pixel Match module.

Use through atelier.safety.guarded. A calibrated reference or an explicitly hashed view
manifest paints visible texels; unseen texels remain neutral. Geometry stays unchanged.
"""
import argparse
from contextlib import contextmanager
from functools import partial
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import threading
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

IDENTITY_FRAME = ((0, 1, 2), (1, 1, 1))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@contextmanager
def stage(name):
    start = time.monotonic()
    done = threading.Event()
    def heartbeat():
        while not done.wait(20):
            print(f'{name}: still computing, {time.monotonic()-start:.0f}s elapsed; no completed-stage progress yet', flush=True)
    thread = threading.Thread(target=heartbeat, daemon=True)
    print(f'{name}: starting', flush=True)
    thread.start()
    try:
        yield
    finally:
        done.set()
    print(f'{name}: complete in {time.monotonic()-start:.1f}s', flush=True)


def load_module(path):
    import sys
    expected = 'a64f11ee0616f3d0457574037979d0d9faf0970814e86c9a69f9ca70c88bc562'
    if digest(path) != expected:
        raise ValueError('Pinned Pixel Match module checksum differs')
    spec = importlib.util.spec_from_file_location('atelier_pixel_match_vendor', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def matte(image):
    """Remove only near-black background connected to the image border; retain dark interior details."""
    rgba = np.array(image.convert('RGBA'))
    if np.any(rgba[..., 3] < 255):
        return rgba
    black = rgba[..., :3].max(axis=2) <= 8
    flood = Image.fromarray(np.pad(black, 1, constant_values=True).astype('uint8')*255).copy()
    ImageDraw.floodfill(flood, (0, 0), 128, thresh=0)
    rgba[..., 3][np.asarray(flood)[1:-1, 1:-1] == 128] = 0
    return rgba


def fitted_view(pm, points, image, yaw, pitch, fov=18):
    yaw, pitch = np.deg2rad([yaw, pitch])
    back = np.array([math.sin(yaw)*math.cos(pitch), math.sin(pitch), math.cos(yaw)*math.cos(pitch)])
    right = np.cross([0., 1., 0.], back)
    right /= np.linalg.norm(right)
    up = np.cross(back, right)
    rotation = np.column_stack([right, up, back])
    target = (points.min(axis=0)+points.max(axis=0))/2
    ys, xs = np.nonzero(image[..., 3] > 127)
    h, w = image.shape[:2]
    focal = (w/2)/math.tan(math.radians(fov)/2)
    local = (points-target) @ rotation
    distance = focal * np.ptp(local[:, 1]) / (ys.max()-ys.min()+1)
    # Fit framing while retaining a fixed FOV and an explicit perspective camera.
    for _ in range(4):
        matrix = np.eye(4)
        matrix[:3, :3] = rotation
        matrix[:3, 3] = target+distance*back
        view = pm.View(image, matrix, math.radians(fov), 'Sunburst head')
        x, y, _ = pm.project(points, view)
        ratio = np.ptp(y)/(ys.max()-ys.min()+1)
        distance *= ratio
        target += right*((x.min()+x.max()-xs.min()-xs.max())/2)*distance/focal
        target -= up*((y.min()+y.max()-ys.min()-ys.max())/2)*distance/focal
    matrix[:3, 3] = target+distance*back
    return pm.View(image, matrix, math.radians(fov), 'Sunburst head')


def silhouette(pm, positions, faces, view):
    x, y, z = pm.project(positions, view)
    face, bary = pm.rasterize(np.stack([x, y], axis=1)[faces], z[faces], view.image.shape[:2])
    return face, bary


def calibrate(args, pm):
    positions, _, faces, _ = pm.read_glb(args.mesh)
    args.output.mkdir(parents=True, exist_ok=True)
    rgba = matte(Image.open(args.image))
    Image.fromarray(rgba).save(args.output/'reference-matted.png')
    small = np.array(Image.fromarray(rgba).resize((96, 96), Image.Resampling.LANCZOS))
    target = small[..., 3] > 127
    candidates = []
    yaws = [args.yaw] if args.yaw is not None else range(-60, 61, 15)
    pitches = [args.pitch] if args.pitch is not None else range(-15, 31, 15)
    for yaw in yaws:
        for pitch in pitches:
            view = fitted_view(pm, positions, small, yaw, pitch)
            face, _ = silhouette(pm, positions, faces, view)
            mask = face >= 0
            iou = float((mask & target).sum()/max((mask | target).sum(), 1))
            candidates.append((iou, float(yaw), float(pitch)))
        print(f'Camera search: {len(candidates)} candidates completed; best silhouette IoU={max(candidates)[0]:.4f}', flush=True)
    candidates.sort(reverse=True)
    _, yaw, pitch = candidates[0]
    if args.yaw is None and args.pitch is None:
        for dy in (-10, -5, 0, 5, 10):
            for dp in (-10, -5, 0, 5, 10):
                view = fitted_view(pm, positions, small, yaw+dy, pitch+dp)
                face, _ = silhouette(pm, positions, faces, view)
                mask = face >= 0
                iou = float((mask & target).sum()/max((mask | target).sum(), 1))
                candidates.append((iou, yaw+dy, pitch+dp))
        candidates.sort(reverse=True)
    iou, yaw, pitch = candidates[0]
    view = fitted_view(pm, positions, rgba, yaw, pitch)
    with stage('Calibration preview'):
        face, bary = silhouette(pm, positions, faces, view)
        visible = face >= 0
        n = pm.vertex_normals(positions, faces)
        texel_n = (bary[visible, :, None]*n[faces[face[visible]]]).sum(axis=1)
        light = np.array([.3, .6, 1.])
        light /= np.linalg.norm(light)
        value = 70+150*np.abs(texel_n @ light)
        clay = np.zeros_like(rgba)
        clay[..., 3] = 255
        clay[visible, :3] = value[:, None]
        Image.fromarray(clay).save(args.output/'calibration-clay.png')
        overlay = (.5*rgba[..., :3]+.5*clay[..., :3]).astype('uint8')
        Image.fromarray(overlay).save(args.output/'calibration-overlay.png')
    record = dict(mesh_sha256=digest(args.mesh), reference_sha256=digest(args.image),
                  matted_sha256=digest(args.output/'reference-matted.png'),
                  camera_angle_x=view.fov_x, transform_matrix=view.cam_to_world.tolist(),
                  frame=IDENTITY_FRAME, yaw_degrees=yaw, pitch_degrees=pitch,
                  silhouette_iou_96px=iou, candidates=candidates[:8],
                  calibration='Silhouette search, perspective 18-degree FOV; inspect facial feature registration separately')
    (args.output/'calibration.json').write_text(json.dumps(record, indent=2)+'\n')
    print(json.dumps(record), flush=True)


def paint(args, pm):
    """@cc [owner:fontanierh,label:correctness] pixel-match-preserves-generated-geometry
    Projection MUST preserve every position, UV and triangle index. Texels unseen by the
    calibrated references MUST keep their neutral base, including a four-texel exclusion
    in empty gutters around protected UV coverage. Provenance MUST identify all inputs.
    """
    calibration = json.loads((args.output/'calibration.json').read_text())
    if calibration['mesh_sha256'] != digest(args.mesh) or calibration['reference_sha256'] != digest(args.image):
        raise ValueError('Calibration inputs no longer match')
    rgba_path = args.output/'reference-matted.png'
    if calibration['matted_sha256'] != digest(rgba_path):
        raise ValueError('Calibration matte no longer matches')
    positions, uvs, faces, base = pm.read_glb(args.mesh)
    view = pm.View(np.array(Image.open(rgba_path).convert('RGBA')),
                   np.array(calibration['transform_matrix']), calibration['camera_angle_x'], 'Sunburst head')
    views = [view]
    view_records = []
    if getattr(args, 'views', None):
        manifest = json.loads(args.views.read_text())
        if manifest['mesh_sha256'] != digest(args.mesh):
            raise ValueError('Multiview manifest mesh no longer matches')
        if not 1 <= len(manifest['views']) <= 12:
            raise ValueError('Use 1–12 calibrated views')
        views = []
        for record in manifest['views']:
            path = args.views.parent/record['image']
            if digest(path) != record['image_sha256']:
                raise ValueError('Multiview reference no longer matches')
            matrix = np.asarray(record['transform_matrix'], dtype=float)
            fov = float(record['camera_angle_x'])
            if (matrix.shape != (4, 4) or not np.isfinite(matrix).all() or not 0 < fov < math.pi
                    or not np.allclose(matrix[3], [0, 0, 0, 1])
                    or not np.allclose(matrix[:3, :3].T @ matrix[:3, :3], np.eye(3), atol=1e-5)
                    or not np.isclose(np.linalg.det(matrix[:3, :3]), 1, atol=1e-5)):
                raise ValueError('Invalid multiview camera')
            views.append(pm.View(matte(Image.open(path)), matrix, fov, record['name']))
            view_records.append(record)
    with stage('Pixel Match projection'):
        blend = getattr(args, 'blend', 'weighted')
        projector = pm.paint_texture if blend == 'weighted' else partial(select_view, pm=pm, mode=blend)
        settings = (pm.Settings(match_colour=False, facing_low=.08, facing_high=.35, edge_px=2)
                    if blend == 'front-first' else pm.Settings(match_colour=False))
        painted, weights = projector(base, positions, uvs, faces, views, frame=IDENTITY_FRAME,
                                     settings=settings)
    with stage('Protection and geometry validation'):
        h, w = base.shape[:2]
        face_of, _ = pm.rasterize((uvs*np.array([w, h]))[faces], np.zeros((len(faces), 3)), (h, w))
        covered = face_of >= 0
        protected = covered & (weights == 0)
        dilated = np.array(Image.fromarray(protected.astype('uint8')*255).filter(ImageFilter.MaxFilter(9))) > 0
        exclusion = protected | (~covered & dilated)
        painted[exclusion] = base[exclusion]
        weights[exclusion] = 0
        if not np.array_equal(painted[protected], base[protected]):
            raise AssertionError('Protected UV texels changed')
        changed = np.any(painted != base, axis=2)
        for name, values in [('confidence', np.rint(weights*255).astype('uint8')),
                             ('protected', protected.astype('uint8')*255),
                             ('changed', changed.astype('uint8')*255)]:
            Image.fromarray(values).save(args.output/f'{name}.png')
        png = pm.encode_png(painted)
        (args.output/'base-colour.png').write_bytes(png)
        model_path = args.output/'head-pixel-match.glb'
        model_path.write_bytes(pm.replace_base_colour(args.mesh.read_bytes(), png))
        check = pm.read_glb(model_path)
        if not all(np.array_equal(a, b) for a, b in zip((positions, uvs, faces), check[:3])):
            raise AssertionError('Projection changed geometry or UVs')
        before_doc, before_bin = pm._split_glb(args.mesh.read_bytes())
        after_doc, after_bin = pm._split_glb(model_path.read_bytes())
        image_view = before_doc['images'][pm.base_colour_image_index(before_doc)]['bufferView']
        for index, (a, b) in enumerate(zip(before_doc['bufferViews'], after_doc['bufferViews'])):
            if index == image_view:
                continue
            start_a, start_b = a.get('byteOffset', 0), b.get('byteOffset', 0)
            if before_bin[start_a:start_a+a['byteLength']] != after_bin[start_b:start_b+b['byteLength']]:
                raise AssertionError('A non-texture buffer changed')
    report = dict(pixel_match_revision='7793fd3622bab7d3fd4526ba02433244d5bf02e2',
                  adapter_sha256=digest(Path(__file__)),
                  module_sha256=digest(args.module), input_mesh_sha256=digest(args.mesh),
                  reference_sha256=digest(args.image), calibration_sha256=digest(args.output/'calibration.json'),
                  output_sha256=digest(model_path), triangle_count=len(faces),
                  exported_vertices=len(positions), atlas_size=list(base.shape[:2]),
                  covered_texels=int(covered.sum()), painted_surface_texels=int(((weights > 0) & covered).sum()),
                  covered_surface_fraction_painted=float(((weights > 0) & covered).sum()/max(covered.sum(), 1)),
                  protected_texels=int(protected.sum()), changed_protected_texels=0,
                  geometry_and_uvs_identical=True, non_texture_buffers_identical=True,
                  view_count=len(views), views=view_records,
                  blend=getattr(args, 'blend', 'weighted'),
                  projection_settings=dict(facing_low=settings.facing_low, facing_high=settings.facing_high,
                                           edge_px=settings.edge_px, depth_tolerance=settings.depth_tolerance,
                                           minimum_source_confidence=.3 if blend == 'front-first' else 0,
                                           normals='triangle' if blend == 'front-first' else 'UV vertex'),
                  confidence_kind='Applied blend weight; front-first uses binary accepted visibility',
                  views_manifest_sha256=digest(args.views) if getattr(args, 'views', None) else None,
                  unseen_surface='Input base colors retained wherever no calibrated view has weight.', match_colour=False)
    (args.output/'pixel-match-report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report), flush=True)


def select_view(texture, positions, uvs, faces, views, *, frame, settings, pm, mode):
    """@cc [owner:fontanierh,label:correctness] coherent-visible-reference-selection
    In front-first mode each covered texel MUST use the first manifest view with visibility
    confidence at least 0.3; later views MUST NOT replace it. Triangle normals MAY affect
    projection confidence only. No stored geometry, UV, index or normal buffer MAY change.
    """
    h, w = texture.shape[:2]
    face_of, bary = pm.rasterize((uvs*np.array([w, h]))[faces], np.zeros((len(faces), 3)), (h, w))
    covered = face_of >= 0
    corners = faces[face_of[covered]]
    view_pos = pm.to_view_space(positions, frame)
    points = (bary[covered, :, None]*view_pos[corners]).sum(axis=1)
    if mode == 'front-first':
        # Projection normals only: avoid cancellation across inconsistently wound UV seams.
        # The stored GLB normals, positions, UVs and connectivity remain byte-identical.
        triangle = view_pos[corners]
        normal = np.cross(triangle[:, 1]-triangle[:, 0], triangle[:, 2]-triangle[:, 0])
    else:
        normals = pm.vertex_normals(view_pos, faces)
        normal = (bary[covered, :, None]*normals[corners]).sum(axis=1)
    normal /= np.maximum(np.linalg.norm(normal, axis=1, keepdims=True), 1e-12)
    best = np.zeros(len(points))
    weight = np.zeros(len(points))
    colour = np.zeros((len(points), 3))
    for index, view in enumerate(views):
        confidence, rgb = pm.view_weights(points, normal, view, view_pos, faces, settings)
        direction = view.position-points
        direction /= np.maximum(np.linalg.norm(direction, axis=1, keepdims=True), 1e-12)
        score = confidence*np.abs((normal*direction).sum(axis=1))**4
        take = ((confidence >= .3) & (weight == 0)) if mode == 'front-first' else score > best
        best[take] = score[take]
        weight[take] = 1. if mode == 'front-first' else confidence[take]
        colour[take] = rgb[take]
        print(f'{mode} projection: {index+1}/{len(views)} views evaluated', flush=True)
    out = texture.astype(float).copy()
    own = out[covered, :3]
    out[covered, :3] = own*(1-weight[:, None])+colour*weight[:, None]
    weights = np.zeros((h, w))
    weights[covered] = weight
    out, weights = pm._grow_into_gutter(out, weights, covered, settings.gutter_px)
    return np.clip(np.rint(out), 0, 255).astype('uint8'), weights


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['calibrate', 'paint'])
    parser.add_argument('--module', type=Path, required=True)
    parser.add_argument('--mesh', type=Path, required=True)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--yaw', type=float)
    parser.add_argument('--pitch', type=float)
    parser.add_argument('--views', type=Path, help='Optional hashed camera/image manifest for multiview painting')
    parser.add_argument('--blend', choices=['weighted', 'best-angle', 'front-first'], default='weighted')
    args = parser.parse_args()
    pm = load_module(args.module)
    (calibrate if args.stage == 'calibrate' else paint)(args, pm)


if __name__ == '__main__':
    main()
