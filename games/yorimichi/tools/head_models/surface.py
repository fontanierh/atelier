"""Exterior depth/color fusion and one-thread Poisson workers for head_retopo.py."""
import argparse
import gc
import json
import os
from pathlib import Path
import time

if __name__ == '__main__':
    for variable in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS'):
        os.environ[variable] = '3'

import numpy as np

from retopo import checked_mesh, digest, fresh, progress


def repair_depth(depth, median, coverage, threshold):
    """@cc [owner:fontanierh,label:correctness] exterior-depth-repair-is-local
    Depth repair MUST leave its input unchanged and affect only well-supported
    pixels with finite median depth. It MUST NOT fill large unsupported openings.
    The native mesh itself MUST remain unchanged; this creates new sample points.
    """
    finite = np.isfinite(depth)
    difference = np.zeros_like(depth)
    both = finite & np.isfinite(median)
    difference[both] = np.abs(depth[both]-median[both])
    repair = coverage & np.isfinite(median) & (~finite | (difference > threshold))
    output = depth.copy()
    output[repair] = median[repair]
    return output, repair


def oriented_samples(rays, depth):
    """Compute visible depth-gradient normals facing each sampling camera."""
    valid = np.isfinite(depth)
    points = rays[..., :3]+np.where(valid, depth, 0)[..., None]*rays[..., 3:]
    dx = np.roll(points, -1, axis=1)-np.roll(points, 1, axis=1)
    dy = np.roll(points, -1, axis=0)-np.roll(points, 1, axis=0)
    normals = np.cross(dx, dy)
    length = np.linalg.norm(normals, axis=2)
    normals /= np.maximum(length[..., None], 1e-15)
    valid &= (np.roll(valid, 1, 0) & np.roll(valid, -1, 0)
              & np.roll(valid, 1, 1) & np.roll(valid, -1, 1) & (length > 1e-10))
    valid[[0, -1], :] = False
    valid[:, [0, -1]] = False
    direction = -rays[..., 3:]
    direction /= np.maximum(np.linalg.norm(direction, axis=2, keepdims=True), 1e-15)
    normals[(normals*direction).sum(2) < 0] *= -1
    valid &= (normals*direction).sum(2) > .3
    return points, normals, valid


def topology(vertices, faces):
    edges = np.sort(np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1)
    _, counts = np.unique(edges, axis=0, return_counts=True)
    return dict(vertices=len(vertices), triangles=len(faces),
                nonmanifold_edges=int((counts > 2).sum()), boundary_edges=int((counts == 1).sum()))


def surface(args):
    import open3d as o3d
    from scipy import ndimage
    from PIL import Image
    from vertex_bake import vertex_colors, linear, srgb
    fresh(args.output)
    started = time.monotonic()
    source = args.checkpoint/'mesh_raw.npz'
    before = digest(source)
    with np.load(source, allow_pickle=False) as raw:
        vertices, faces = checked_mesh(raw['vertices'], raw['faces'])
    with np.load(args.checkpoint/'decoder_output.npz', allow_pickle=False) as data:
        coords = data['coords'][:, 1:4]
    grid = json.loads((args.checkpoint/'mesh_raw.json').read_text())['mesh_grid_size']
    with np.load(args.checkpoint/'texture.npz', allow_pickle=False) as data:
        rgb = linear(vertex_colors(coords, data['tex_coords_spatial'], data['tex_np'], grid))
    del coords
    with progress('Building native exterior raycasting BVH'):
        scene = o3d.t.geometry.RaycastingScene(nthreads=3)
        scene.add_triangles(o3d.core.Tensor.from_numpy(vertices), o3d.core.Tensor.from_numpy(faces))
    points, normals, colors, views = [], [], [], []
    center = (vertices.min(0)+vertices.max(0))/2
    size = 768
    angles = [(yaw, pitch) for pitch in (-25, 25) for yaw in range(0, 360, 30)] + [(0, 80), (180, -75)]
    for index, (yaw, pitch) in enumerate(angles):
        y, p = np.deg2rad([yaw, pitch])
        eye = center+2.2*np.array([np.cos(y)*np.cos(p), np.sin(y)*np.cos(p), np.sin(p)])
        rays = o3d.t.geometry.RaycastingScene.create_rays_pinhole(fov_deg=35.,
            center=center.tolist(), eye=eye.tolist(), up=[0., 0., 1.], width_px=size, height_px=size)
        result = scene.cast_rays(rays, nthreads=3)
        rays_np, depth = rays.numpy(), result['t_hit'].numpy()
        seen = np.isfinite(depth)
        median = ndimage.median_filter(depth, size=3, mode='constant', cval=np.inf)
        coverage = ndimage.uniform_filter(seen.astype('float32'), size=3) > .7
        depth, repaired = repair_depth(depth, median, coverage, .0025)
        ids, bary = result['primitive_ids'].numpy(), result['primitive_uvs'].numpy()
        image = np.zeros((size, size, 3), dtype='float32')
        weights = np.stack((1-bary[seen].sum(1), bary[seen, 0], bary[seen, 1]), axis=1)
        image[seen] = (rgb[faces[ids[seen]]]*weights[:, :, None]).sum(1)
        image = srgb(np.clip(image, 0, 1)).astype('float32')
        filtered = ndimage.median_filter(image, size=(3, 3, 1))
        image[coverage] = filtered[coverage]
        cloud, normal, valid = oriented_samples(rays_np, depth)
        points.append(cloud[valid].astype('float32'))
        normals.append(normal[valid].astype('float32'))
        # Average color observations in linear light when voxel-fusing views.
        colors.append(linear(np.clip(image[valid], 0, 1)))
        Image.fromarray(np.clip(image*255+.5, 0, 255).astype('uint8')).save(args.output/f'view{index}.png')
        views.append(dict(yaw=yaw, pitch=pitch, eye=eye.tolist(), center=center.tolist(), up=[0, 0, 1],
                          fov=35, width=size, height=size, points=int(valid.sum()),
                          repaired_depth_pixels=int(repaired.sum())))
        print(f'Exterior view {index+1}/{len(angles)}: {valid.sum():,} samples; {repaired.sum():,} repaired depths', flush=True)
    del scene, rgb
    gc.collect()
    with progress('Fusing visible oriented surface and color support'):
        cloud = o3d.geometry.PointCloud()
        cloud.points = o3d.utility.Vector3dVector(np.concatenate(points))
        cloud.normals = o3d.utility.Vector3dVector(np.concatenate(normals))
        cloud.colors = o3d.utility.Vector3dVector(np.concatenate(colors))
        cloud = cloud.voxel_down_sample(.0025)
        cloud.normalize_normals()
        np.savez_compressed(args.output/'cloud.npz', positions=np.asarray(cloud.points).astype('float32'),
            normals=np.asarray(cloud.normals).astype('float32'),
            colors=srgb(np.clip(np.asarray(cloud.colors), 0, 1)).astype('float32'))
    if digest(source) != before:
        raise ValueError('Exterior sampling changed native geometry')
    report = dict(method='26 exterior depth/color views; deterministic local filtering and oriented fusion',
        native_mesh_sha256=before, native_texture_sha256=digest(args.checkpoint/'texture.npz'),
        worker_sha256=digest(Path(__file__)), cloud_sha256=digest(args.output/'cloud.npz'),
        original_triangles=len(faces), original_vertices=len(vertices), points=len(cloud.points),
        voxel_size=.0025, median_width=3, depth_outlier_threshold=.0025, color_space='sRGB in cloud; linear-light voxel averaging',
        source_frame='Unscaled native TRELLIS Z-up unit cube', views=views, seconds=time.monotonic()-started)
    (args.output/'surface.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'views'}), flush=True)


def reconstruct(args):
    """@cc [owner:fontanierh,label:correctness] exterior-poisson-solver-and-source
    Reconstruction MUST use a separate copy and one Poisson solver thread, avoiding
    the observed ARM threading failure. Input samples MUST have finite positions,
    colors and unit normals. Reported counts MUST describe cleaned float32 exports.
    """
    import open3d as o3d
    fresh(args.output)
    started = time.monotonic()
    before = digest(args.source)
    with np.load(args.source, allow_pickle=False) as data:
        positions, normals, colors = data['positions'], data['normals'], data['colors']
    if (positions.ndim != 2 or positions.shape[1] != 3 or len(positions) < 100
            or normals.shape != positions.shape or colors.shape != positions.shape
            or not all(np.isfinite(a).all() for a in (positions, normals, colors))
            or not np.allclose(np.linalg.norm(normals, axis=1), 1, atol=1e-4)):
        raise ValueError('Invalid oriented exterior cloud')
    if len(positions) > 400000:
        selected = np.sort(np.random.default_rng(42).choice(len(positions), 400000, replace=False))
        positions, normals = positions[selected], normals[selected]
    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(positions)
    cloud.normals = o3d.utility.Vector3dVector(normals)
    with progress(f'Exterior Poisson depth {args.depth}, one solver thread, {len(positions):,} points'):
        mesh, _ = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
            cloud, depth=args.depth, scale=1.1, linear_fit=False, n_threads=1)
    with np.load(args.checkpoint/'mesh_raw.npz', allow_pickle=False) as source:
        native = source['vertices']
    mesh = mesh.crop(o3d.geometry.AxisAlignedBoundingBox(native.min(0).astype(float), native.max(0).astype(float)))
    mesh.remove_duplicated_vertices()
    mesh.remove_duplicated_triangles()
    mesh.remove_degenerate_triangles()
    mesh.remove_unreferenced_vertices()
    labels, _, areas = mesh.cluster_connected_triangles()
    labels, areas = np.asarray(labels), np.asarray(areas)
    mesh.remove_triangles_by_mask(areas[np.asarray(labels)] < areas.max()*.005)
    mesh.remove_unreferenced_vertices()
    results = []
    for budget in args.triangles:
        with progress(f'Adaptive triangle reduction to {budget:,}'):
            reduced = mesh.simplify_quadric_decimation(budget)
            reduced.remove_degenerate_triangles()
            reduced.remove_duplicated_triangles()
            reduced.remove_unreferenced_vertices()
        v, f = checked_mesh(np.asarray(reduced.vertices), np.asarray(reduced.triangles))
        # Remove only newly degenerate float32 triangles at this geometry stage,
        # before the later UV/repaint stages promise immutable triangles.
        cross = np.cross(v[f[:, 1]]-v[f[:, 0]], v[f[:, 2]]-v[f[:, 0]])
        valid = np.linalg.norm(cross, axis=1) > 1e-14
        removed = int((~valid).sum())
        f = f[valid]
        qa = topology(v, f)
        if qa['nonmanifold_edges']:
            raise ValueError(f'Reduced candidate has nonmanifold edges: {qa}')
        target = args.output/f'mesh-{budget}.npz'
        np.savez_compressed(target, vertices=v, faces=f)
        results.append(dict(target_triangles=budget, **qa, sha256=digest(target),
                            removed_degenerate_float32_triangles=removed))
        print('Reduced candidate:', json.dumps(results[-1]), flush=True)
    if digest(args.source) != before:
        raise ValueError('Reconstruction changed retained exterior samples')
    report = dict(method='Exterior oriented screened Poisson + adaptive QEM; no manual edits',
        source_sha256=before, worker_sha256=digest(Path(__file__)), depth=args.depth,
        solver_threads=1, point_support=len(positions), sample_seed=42,
        small_component_area_fraction=.005, results=results, seconds=time.monotonic()-started,
        limitation='A derived surface, with possible feature loss; no facial deformation-loop guarantee')
    (args.output/'reconstruct.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage', choices=['surface', 'reconstruct'])
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--checkpoint', type=Path, required=True)
    p.add_argument('--source', type=Path)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--depth', type=int, default=9)
    p.add_argument('--triangles', type=int, nargs='+', default=[40000, 100000])
    args = p.parse_args()
    return globals()[args.stage](args)


if __name__ == '__main__':
    main()
