"""CPU workers for guarded head reduction, xatlas UVs and learned-color transfer."""
import argparse
from contextlib import contextmanager
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import threading
import time

import numpy as np


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(8*1024*1024), b''):
            result.update(chunk)
    return result.hexdigest()


@contextmanager
def progress(name):
    done = threading.Event()
    started = time.monotonic()
    def heartbeat():
        while not done.wait(20):
            print(f'{name}: active {time.monotonic()-started:.0f}s; waiting for stage completion', flush=True)
    thread = threading.Thread(target=heartbeat, daemon=True)
    print(name, flush=True)
    thread.start()
    try:
        yield
    finally:
        done.set()
        thread.join(timeout=1)


def fresh(path):
    if path.exists() and any(path.iterdir()):
        raise ValueError('Use a fresh output directory; retained trials are never overwritten')
    path.mkdir(parents=True, exist_ok=True)


def setup(args):
    """Install small binary wheels only, without any generation-model weights."""
    py = args.root/'venv/bin/python'
    commands = [['uv', 'venv', '--python', '3.12', str(py.parents[1])]] if not py.exists() else []
    commands.append(['uv', 'pip', 'install', '--python', str(py), '--only-binary', ':all:',
                     'numpy==2.2.6', 'scipy==1.15.3', 'pillow==12.2.0',
                     'fast-simplification==0.2.0', 'xatlas==0.0.11', 'open3d==0.20.0'])
    for command in commands:
        with progress('Post-process runtime: '+ ' '.join(command)):
            subprocess.run(command, check=True)
    if sys.platform == 'darwin':
        brew = shutil.which('brew')
        if not brew:
            raise ValueError('Open3D on macOS requires Homebrew libusb; install Homebrew and rerun setup')
        prefix = subprocess.check_output([brew, '--prefix', 'libusb'], text=True).strip()
        if not (Path(prefix)/'lib/libusb-1.0.0.dylib').is_file():
            with progress('Installing Open3D libusb runtime bottle'):
                subprocess.run([brew, 'install', '--force-bottle', 'libusb'], check=True,
                               env={**os.environ, 'HOMEBREW_NO_AUTO_UPDATE': '1'})
    with (args.root/'packages.txt').open('w') as output:
        subprocess.run(['uv', 'pip', 'freeze', '--python', str(py)], stdout=output, check=True)


def checked_mesh(vertices, faces):
    v = np.asarray(vertices, dtype='<f4')
    f = np.asarray(faces)
    if (v.ndim != 2 or v.shape[1] != 3 or not len(v) or not np.isfinite(v).all()
            or f.ndim != 2 or f.shape[1] != 3 or not len(f)
            or not np.issubdtype(f.dtype, np.integer) or f.min() < 0 or f.max() >= len(v)):
        raise ValueError('Invalid finite triangle mesh')
    return v, f.astype('<u4')


def reduce(args):
    import fast_simplification
    fresh(args.output)
    path = args.checkpoint/'mesh_raw.npz'
    before = digest(path)
    with np.load(path, allow_pickle=False) as source:
        vertices, faces = checked_mesh(source['vertices'], source['faces'])
    started = time.monotonic()
    with progress(f'QEM working copy: {len(faces):,} input triangles; target 200,000'):
        v, f = fast_simplification.simplify(vertices, faces, target_count=min(200000, len(faces)), agg=7)
    v, f = checked_mesh(v, f)
    np.savez_compressed(args.output/'mesh.npz', vertices=v, faces=f)
    if digest(path) != before:
        raise ValueError('Native checkpoint changed')
    report = dict(method='QEM working copy; achieved count is measured, not assumed',
                  source_sha256=before, source_vertices=len(vertices), source_triangles=len(faces),
                  vertices=len(v), triangles=len(f), seconds=time.monotonic()-started)
    (args.output/'reduction.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report), flush=True)


def raster_uv(uv_corners, size):
    """@cc [owner:fontanierh,label:correctness] head-uv-interior-ownership
    Rasterization MUST use strict triangle interiors and reject any texel covered
    by two interiors. UVs MUST be finite and inside the unit square. Shared edges
    MUST NOT count as overlaps. Barycentric weights MUST sum to one.
    """
    owner, weights, conflicts = _raster_uv(uv_corners, size)
    if conflicts:
        raise ValueError('Overlapping UV triangle interiors')
    return owner, weights


def _raster_uv(uv_corners, size):
    uv = np.asarray(uv_corners, dtype='float64')
    if (uv.ndim != 3 or uv.shape[1:] != (3, 2) or not np.isfinite(uv).all()
            or uv.min() < 0 or uv.max() > 1 or not 1 <= size <= 4096):
        raise ValueError('Invalid UV atlas')
    owner = np.full((size, size), -1, dtype='int32')
    weights = np.zeros((size, size, 3), dtype='float32')
    conflicts = set()
    for index, triangle in enumerate(uv*size):
        lo = np.maximum(np.floor(triangle.min(0)).astype(int), 0)
        hi = np.minimum(np.ceil(triangle.max(0)).astype(int), size-1)
        if np.any(lo > hi):
            continue
        x, y = np.meshgrid(np.arange(lo[0], hi[0]+1)+.5, np.arange(lo[1], hi[1]+1)+.5)
        delta = np.stack((x-triangle[0, 0], y-triangle[0, 1]), axis=-1)
        a, b = triangle[1]-triangle[0], triangle[2]-triangle[0]
        determinant = a[0]*b[1]-a[1]*b[0]
        if abs(determinant) < 1e-12:
            continue
        u = (delta[..., 0]*b[1]-delta[..., 1]*b[0])/determinant
        v = (a[0]*delta[..., 1]-a[1]*delta[..., 0])/determinant
        hit = (u > 1e-6) & (v > 1e-6) & (u+v < 1-1e-6)
        yy, xx = np.nonzero(hit)
        yy += lo[1]; xx += lo[0]
        covered = owner[yy, xx]
        overlaps = covered >= 0
        if overlaps.any():
            conflicts.update(covered[overlaps].tolist())
            conflicts.add(index)
        owner[yy, xx] = index
        weights[yy, xx] = np.stack((1-u[hit]-v[hit], u[hit], v[hit]), axis=1)
    if not (owner >= 0).any():
        raise ValueError('UV atlas covers no texels')
    return owner, weights, conflicts


def unwrap(vertices, faces, size):
    """@cc [owner:fontanierh,label:correctness] head-uv-repair-is-layout-only
    UV repair MUST NOT change any ordered geometric triangle. Overlapping charts
    MUST be split and repacked automatically, then pass strict interior ownership.
    Multiple atlas pages MUST reject rather than share normalized UV coordinates.
    """
    import xatlas
    atlas = xatlas.Atlas()
    atlas.add_mesh(vertices, faces)
    chart = xatlas.ChartOptions()
    chart.max_iterations = 1
    chart.fix_winding = True
    pack = xatlas.PackOptions()
    pack.resolution = 0
    pack.padding = 8
    with progress('Generating one-page xatlas UV charts'):
        atlas.generate(chart_options=chart, pack_options=pack)
    mapping, indices, coords = atlas[0]
    if atlas.atlas_count != 1 or not np.array_equal(vertices[mapping[indices]], vertices[faces]):
        raise ValueError('UV generation changed triangles or created multiple pages')
    uv = coords[indices]
    with progress('Checking UV chart interiors'):
        owner, bary, conflicts = _raster_uv(uv, size)
    repaired = 0
    if conflicts:
        _, assignments = atlas.get_mesh_vertex_assignment(0)
        labels = assignments[indices[:, 0]].astype('uint32')
        bad_charts = np.unique(labels[list(conflicts)])
        split = np.isin(labels, bad_charts)
        repaired = int(split.sum())
        print(f'UV repair: splitting {len(bad_charts)} folded charts / {repaired} triangles', flush=True)
        # Parameterize each affected triangle isometrically, then repack those
        # triangles and all intact charts as separate 2D islands.
        points = vertices[faces[split]].astype('float64')
        a, b = points[:, 1]-points[:, 0], points[:, 2]-points[:, 0]
        length = np.linalg.norm(a, axis=1)
        along = (a*b).sum(1)/np.maximum(length, 1e-30)
        height = np.sqrt(np.maximum((b*b).sum(1)-along*along, 0))
        world_area = np.linalg.norm(np.cross(vertices[faces[:, 1]]-vertices[faces[:, 0]],
                                             vertices[faces[:, 2]]-vertices[faces[:, 0]]), axis=1)
        edge_a, edge_b = uv[:, 1]-uv[:, 0], uv[:, 2]-uv[:, 0]
        uv_area = np.abs(edge_a[:, 0]*edge_b[:, 1]-edge_a[:, 1]*edge_b[:, 0])
        valid = (world_area > 1e-15) & (uv_area > 1e-15)
        scale = np.sqrt(np.median(uv_area[valid]/world_area[valid]))
        flat = np.zeros((repaired, 3, 2), dtype='float32')
        flat[:, 1, 0] = length*scale
        flat[:, 2, 0] = along*scale
        flat[:, 2, 1] = height*scale
        uv[split] = flat
        labels[split] = np.arange(repaired, dtype='uint32')+int(labels.max())+1
        packed = xatlas.Atlas()
        corners = np.arange(faces.size, dtype='uint32').reshape(-1, 3)
        packed.add_uv_mesh(uv.reshape(-1, 2), corners, face_materials=labels[:, None])
        # Thousands of repaired triangle islands need the requested page size.
        # Automatic packing can choose a smaller page and overlap them at 4096.
        # Eight texels also over-pads these tiny islands; four is the measured
        # collision-free layout for the Kiyo 100K surface.
        pack.resolution = size
        pack.padding = 4
        with progress('Repacking intact charts and repaired triangle islands'):
            packed.generate(pack_options=pack)
        mapping, indices, coords = packed[0]
        if packed.atlas_count != 1 or not np.array_equal(mapping[indices], corners):
            raise ValueError('Repacking changed triangle corner order or page count')
        uv = coords[indices]
        owner, bary = raster_uv(uv, size)
        atlas = packed
    print(f'UV pass: {atlas.chart_count} charts, zero overlapping interiors', flush=True)
    return uv, owner, bary, atlas.chart_count, repaired


def surface_median(tree, colors, positions, neighbors):
    """@cc [owner:fontanierh,label:correctness] surface-color-median-no-input-edits
    Transfer MUST use native surface neighbors, never absent support as black.
    Median filtering MUST change colors only and leave source positions and colors
    unchanged. Temporary neighbor arrays MUST be bounded to 32,768 queries.
    """
    if neighbors not in (1, 8, 16, 32) or neighbors > len(colors):
        raise ValueError('Unsupported native surface neighborhood')
    result = np.empty((len(positions), 3), dtype='float32')
    distances = np.empty(len(positions), dtype='float32')
    for first in range(0, len(positions), 32768):
        distance, indices = tree.query(positions[first:first+32768], k=neighbors, workers=3)
        if neighbors == 1:
            result[first:first+len(indices)] = colors[indices]
            distances[first:first+len(indices)] = distance
        else:
            result[first:first+len(indices)] = np.median(colors[indices], axis=1)
            distances[first:first+len(indices)] = distance[:, 0]
    return result, distances


def material_regions(rgb, occupied):
    """Return approximate palette regions, explicitly not anatomical ground truth."""
    skin = ((rgb[..., 0] > rgb[..., 2]*1.35) & (rgb[..., 0] > rgb[..., 1]*1.15)
            & (rgb[..., 0] > .2) & occupied)
    dark = (rgb.max(axis=-1) < .4) & (rgb[..., 2] > rgb[..., 0]*.95) & occupied
    return skin, dark, occupied & ~skin & ~dark


def recolor_native(document, binary, values):
    """@cc [owner:fontanierh,label:correctness] dense-despeckle-keeps-all-other-bytes
    Dense cleanup MUST replace only the native COLOR_0 interval. All positions,
    normals, indices, scene, material and accessor bindings MUST remain identical.
    Nonfinite, out-of-range or incorrectly shaped replacement colors MUST reject.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from vertex_photo import native_arrays
    _, _, original, _, (start, end) = native_arrays(document, binary)
    values = np.asarray(values, dtype='<f4')
    if (values.shape != original.shape or not np.isfinite(values).all()
            or values.min() < 0 or values.max() > 1):
        raise ValueError('Invalid replacement native colors')
    result = binary[:start]+values.tobytes()+binary[end:]
    if result[:start] != binary[:start] or result[end:] != binary[end:]:
        raise ValueError('Dense color cleanup modified protected bytes')
    return result


def dense(args):
    from scipy.spatial import cKDTree
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from vertex_bake import vertex_colors, linear
    from vertex_photo import native_arrays
    from meshaxiom_pixel_match import load_module
    from meshaxiom_quality import VENDOR
    fresh(args.output)
    started = time.monotonic()
    before = digest(args.source)
    pm = load_module(VENDOR)
    document, binary = pm._split_glb(args.source.read_bytes())
    positions, _, original, faces, (start, end) = native_arrays(document, binary)
    with np.load(args.checkpoint/'mesh_raw.npz', allow_pickle=False) as source:
        native = source['vertices']
    with np.load(args.checkpoint/'decoder_output.npz', allow_pickle=False) as source:
        coords = source['coords'][:, 1:4]
    grid = json.loads((args.checkpoint/'mesh_raw.json').read_text())['mesh_grid_size']
    with np.load(args.checkpoint/'texture.npz', allow_pickle=False) as source:
        colors = vertex_colors(coords, source['tex_coords_spatial'], source['tex_np'], grid)
    if len(native) != len(colors) or len(positions) < len(native):
        raise ValueError('Native shape/color support differs')
    expected = native[:, [0, 2, 1]].copy()
    expected[:, 2] *= -1
    if not np.array_equal(positions[:len(native)], expected):
        raise ValueError('Dense export does not match the native checkpoint frame')
    del expected, coords
    with progress('Building native surface lookup for immutable dense head'):
        tree = cKDTree(native)
    values = np.empty_like(original)
    with progress('Dense surface-color cleanup; positions and shading normals retained'):
        for first in range(0, len(positions), 32768):
            points = positions[first:first+32768][:, [0, 2, 1]].copy()
            points[:, 1] *= -1
            rgb, distances = surface_median(tree, colors, points, args.neighbors)
            if distances.max() > 1e-7:
                raise ValueError('Dense vertex is absent from the source checkpoint')
            values[first:first+len(rgb)] = linear(rgb)
            if first % 1048576 == 0:
                print(f'Dense cleanup: {first:,}/{len(positions):,} vertices', flush=True)
    protected = hashlib.sha256()
    protected.update(memoryview(binary)[:start])
    protected.update(memoryview(binary)[end:])
    output = recolor_native(document, binary, values)
    target = args.output/'head.glb'
    target.write_bytes(pm._join_glb(document, output))
    del output
    checked, payload = pm._split_glb(target.read_bytes())
    proof = hashlib.sha256()
    proof.update(memoryview(payload)[:start])
    proof.update(memoryview(payload)[end:])
    if checked != document or proof.digest() != protected.digest() or digest(args.source) != before:
        raise ValueError('Dense cleanup changed metadata or protected source bytes')
    report = dict(method='Native surface-neighbor componentwise color median; no geometry changes',
        neighbors=args.neighbors, input_sha256=before, output_sha256=digest(target),
        native_checkpoint_sha256=digest(args.checkpoint/'mesh_raw.npz'),
        texture_checkpoint_sha256=digest(args.checkpoint/'texture.npz'),
        vertices=len(positions), triangles=len(faces),
        changed_color_vertices=int(np.any(values != original, axis=1).sum()),
        protected_geometry_normals_indices_sha256=proof.hexdigest(),
        geometry_normals_indices_materials_identical=True,
        seconds=time.monotonic()-started,
        limitation='Color filtering can soften detail; original geometric pits and UV absence remain')
    (args.output/'dense.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report), flush=True)


def textured_glb(vertices, faces, uv_corners, pixels):
    """@cc [owner:fontanierh,label:correctness] retopo-bake-keeps-every-triangle
    Export MUST retain all ordered reduced triangle positions and winding exactly,
    up to the documented fixed Z-up to Y-up rotation. Only coincident vertices
    required by UV or winding-aligned shading-normal seams MAY be added; they MUST
    NOT move, omit, reorder or reverse geometric triangles.
    Colors MUST use a texture without COLOR_0 multiplication.
    Lighting MUST remain conventional PBR, with no unlit extension or normal map.
    """
    from PIL import Image
    vertices, faces = checked_mesh(vertices, faces)
    normals = np.zeros_like(vertices)
    cross = np.cross(vertices[faces[:, 1]]-vertices[faces[:, 0]],
                     vertices[faces[:, 2]]-vertices[faces[:, 0]])
    for corner in range(3):
        np.add.at(normals, faces[:, corner], cross)
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-20)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from lit_normals import normal_axes
    axes = normal_axes(vertices, normals, faces, 4)
    corner_normals = axes[faces].copy()
    corner_normals[(corner_normals*cross[:, None, :]).sum(2) < 0] *= -1
    positions = vertices[faces].reshape(-1, 3)[:, [0, 2, 1]].copy()
    positions[:, 2] *= -1
    shading = corner_normals.reshape(-1, 3)[:, [0, 2, 1]].copy()
    shading[:, 2] *= -1
    uvs = np.asarray(uv_corners, dtype='<f4').reshape(-1, 2)
    if uvs.shape != (len(positions), 2) or not np.isfinite(uvs).all():
        raise ValueError('UV corner count differs from geometry')
    # Share identical attribute tuples within islands; retain true UV/normal
    # seams. This reduces GPU vertices without changing any triangle corner.
    attributes = np.ascontiguousarray(np.concatenate((positions, shading, uvs), axis=1), dtype='<f4')
    _, first, indices = np.unique(attributes.view('V32').reshape(-1), return_index=True, return_inverse=True)
    compact = attributes[first]
    if compact[indices, :3].tobytes() != positions.astype('<f4').tobytes():
        raise ValueError('Attribute compaction changed triangle positions')
    positions = compact[:, :3]
    arrays = [positions.astype('<f4'), compact[:, 3:6].astype('<f4'), compact[:, 6:8].astype('<f4'),
              indices.astype('<u4')]
    views, binary = [], bytearray()
    for array in arrays:
        binary += b'\0'*(-len(binary) % 4)
        views.append(dict(buffer=0, byteOffset=len(binary), byteLength=array.nbytes))
        binary += array.tobytes()
    encoded = io.BytesIO()
    # glTF UV (0,0) denotes the image's top-left, as does this CPU raster.
    Image.fromarray(pixels).save(encoded, format='PNG')
    binary += b'\0'*(-len(binary) % 4)
    views.append(dict(buffer=0, byteOffset=len(binary), byteLength=len(encoded.getvalue())))
    binary += encoded.getvalue()
    accessors = [dict(bufferView=i, componentType=5126, count=len(positions),
                      type='VEC2' if i == 2 else 'VEC3') for i in range(3)]
    accessors[0].update(min=positions.min(0).tolist(), max=positions.max(0).tolist())
    accessors.append(dict(bufferView=3, componentType=5125, count=faces.size, type='SCALAR'))
    document = dict(asset=dict(version='2.0', generator='Atelier automatic head UV bake'),
        scene=0, scenes=[dict(nodes=[0])], nodes=[dict(mesh=0)],
        meshes=[dict(primitives=[dict(attributes=dict(POSITION=0, NORMAL=1, TEXCOORD_0=2),
                                     indices=3, material=0, mode=4)])],
        materials=[dict(doubleSided=True, pbrMetallicRoughness=dict(
            baseColorTexture=dict(index=0), metallicFactor=0, roughnessFactor=.85))],
        buffers=[dict(byteLength=len(binary))], bufferViews=views, accessors=accessors,
        images=[dict(bufferView=4, mimeType='image/png')], textures=[dict(source=0, sampler=0)],
        samplers=[dict(magFilter=9729, minFilter=9987, wrapS=33071, wrapT=33071)])
    header = json.dumps(document, separators=(',', ':')).encode()
    header += b' '*(-len(header) % 4)
    binary += b'\0'*(-len(binary) % 4)
    return (struct.pack('<III', 0x46546c67, 2, 28+len(header)+len(binary))
            + struct.pack('<I4s', len(header), b'JSON') + header
            + struct.pack('<I4s', len(binary), b'BIN\0') + binary)


def verify_export(blob, vertices, faces):
    """Independently decode the saved index/position streams and prove all corners."""
    if struct.unpack_from('<III', blob) != (0x46546c67, 2, len(blob)):
        raise ValueError('Invalid exported GLB header')
    json_size, kind = struct.unpack_from('<I4s', blob, 12)
    if kind != b'JSON':
        raise ValueError('Missing exported JSON chunk')
    document = json.loads(blob[20:20+json_size])
    binary_size, kind = struct.unpack_from('<I4s', blob, 20+json_size)
    if kind != b'BIN\0' or 28+json_size+binary_size != len(blob):
        raise ValueError('Invalid exported binary chunk')
    binary = memoryview(blob)[28+json_size:]
    if (document.get('scene') != 0 or document.get('scenes') != [dict(nodes=[0])]
            or document.get('nodes') != [dict(mesh=0)] or len(document.get('meshes', [])) != 1
            or len(document['meshes'][0]['primitives']) != 1
            or len(document.get('accessors', [])) != 4
            or len(document.get('bufferViews', [])) != 5
            or len(document.get('buffers', [])) != 1
            or set(document['buffers'][0]) != {'byteLength'}):
        raise ValueError('Expected a single identity-scene textured bake')
    primitive = document['meshes'][0]['primitives'][0]
    if (primitive['attributes'] != dict(POSITION=0, NORMAL=1, TEXCOORD_0=2)
            or primitive['indices'] != 3 or primitive.get('mode') != 4):
        raise ValueError('Unexpected export bindings')
    end = 0
    for index, (view, accessor) in enumerate(zip(document['bufferViews'][:4], document['accessors'])):
        components = 2 if index == 2 else (1 if index == 3 else 3)
        expected_accessor = dict(bufferView=index, componentType=5125 if index == 3 else 5126,
                                 count=accessor['count'], type='SCALAR' if index == 3 else ('VEC2' if index == 2 else 'VEC3'))
        actual = {k: v for k, v in accessor.items() if k not in ('min', 'max')}
        if (actual != expected_accessor or accessor['count'] <= 0
                or set(view) != {'buffer', 'byteOffset', 'byteLength'} or view['buffer'] != 0
                or view['byteOffset'] < end or view['byteOffset'] % 4
                or view['byteLength'] != accessor['count']*components*4):
            raise ValueError('Unexpected export attribute layout')
        end = view['byteOffset']+view['byteLength']
        if end > len(binary):
            raise ValueError('Export stream extends beyond its buffer')
    position_view, index_view = document['bufferViews'][0], document['bufferViews'][3]
    positions = np.frombuffer(binary, dtype='<f4', count=document['accessors'][0]['count']*3,
                              offset=position_view['byteOffset']).reshape(-1, 3)
    indices = np.frombuffer(binary, dtype='<u4', count=document['accessors'][3]['count'],
                            offset=index_view['byteOffset'])
    expected = vertices[faces].reshape(-1, 3)[:, [0, 2, 1]].copy()
    expected[:, 2] *= -1
    if indices.size != faces.size or indices.max() >= len(positions) or positions[indices].tobytes() != expected.astype('<f4').tobytes():
        raise ValueError('Saved GLB changed geometric triangle corners or winding')
    protected = hashlib.sha256()
    for view in document['bufferViews'][:4]:
        protected.update(binary[view['byteOffset']:view['byteOffset']+view['byteLength']])
    return dict(export_vertices=len(positions), geometry_normals_uv_indices_sha256=protected.hexdigest())


def bake(args):
    from scipy.spatial import cKDTree
    from scipy import ndimage
    from PIL import Image
    from vertex_bake import vertex_colors
    fresh(args.output)
    started = time.monotonic()
    before = digest(args.source)
    with np.load(args.source, allow_pickle=False) as source:
        if source['vertices'].dtype != np.dtype('float32'):
            raise ValueError('UV baking requires a float32 reduced reference; convert during geometry authoring')
        vertices, faces = checked_mesh(source['vertices'], source['faces'])
        uv = source['uv_corners'].copy() if 'uv_corners' in source.files else None
    reused = uv is not None
    if reused:
        owner, bary = raster_uv(uv, args.texture_size)
        charts, repaired = None, 0
    else:
        uv, owner, bary, charts, repaired = unwrap(vertices, faces, args.texture_size)
    occupied = owner >= 0
    if args.color_cloud:
        with np.load(args.color_cloud, allow_pickle=False) as cloud:
            native_positions, colors = cloud['positions'], cloud['colors']
        if (native_positions.ndim != 2 or native_positions.shape[1] != 3
                or colors.shape != native_positions.shape or len(colors) < args.neighbors
                or not np.isfinite(native_positions).all() or not np.isfinite(colors).all()
                or colors.min() < 0 or colors.max() > 1):
            raise ValueError('Invalid exterior surface color support')
    else:
        with np.load(args.checkpoint/'mesh_raw.npz', allow_pickle=False) as native:
            native_positions = native['vertices']
        with np.load(args.checkpoint/'decoder_output.npz', allow_pickle=False) as decoder:
            shape_coords = decoder['coords'][:, 1:4]
        grid = json.loads((args.checkpoint/'mesh_raw.json').read_text())['mesh_grid_size']
        with np.load(args.checkpoint/'texture.npz', allow_pickle=False) as texture:
            colors = vertex_colors(shape_coords, texture['tex_coords_spatial'], texture['tex_np'], grid)
    with progress('Building native surface color lookup'):
        tree = cKDTree(native_positions)
    yy, xx = np.nonzero(occupied)
    painted = np.zeros((*occupied.shape, 3), dtype='float32')
    distance_stats = []
    with progress('Transferring learned colors onto UV texels'):
        for first in range(0, len(yy), 32768):
            y, x = yy[first:first+32768], xx[first:first+32768]
            positions = (vertices[faces[owner[y, x]]]*bary[y, x, :, None]).sum(1)
            values, distances = surface_median(tree, colors, positions, args.neighbors)
            painted[y, x] = values
            distance_stats.append(distances)
    nearest = ndimage.distance_transform_edt(~occupied, return_distances=False, return_indices=True)
    pixels = np.clip(painted[nearest[0], nearest[1]]*255+.5, 0, 255).astype('uint8')
    Image.fromarray(pixels).save(args.output/'basecolor.png')
    skin, dark, other = material_regions(painted, occupied)
    for name, mask in [('skin', skin), ('dark-hair-and-features', dark), ('other', other), ('occupied', occupied)]:
        Image.fromarray((mask*255).astype('uint8')).save(args.output/(name+'-mask.png'))
    model = args.output/'head.glb'
    model.write_bytes(textured_glb(vertices, faces, uv, pixels))
    verified = verify_export(model.read_bytes(), vertices, faces)
    np.savez_compressed(args.output/'mesh-uv.npz', vertices=vertices, faces=faces, uv_corners=uv)
    source_json = json.dumps(dict(vertices=vertices.tolist(), faces=faces.tolist()), separators=(',', ':')).encode()
    (args.output/'mesh.source.json.gz').write_bytes(gzip.compress(source_json, mtime=0))
    if digest(args.source) != before:
        raise ValueError('Color bake changed the reduced reference')
    report = dict(source_sha256=before, native_checkpoint_sha256=digest(args.checkpoint/'mesh_raw.npz'),
        texture_checkpoint_sha256=digest(args.checkpoint/'texture.npz'), model_sha256=digest(model),
        color_cloud_sha256=digest(args.color_cloud) if args.color_cloud else None, **verified,
        method='xatlas + native surface-neighbor componentwise color median',
        neighbors=args.neighbors, texture_size=args.texture_size, charts=charts,
        repaired_uv_triangles=repaired, uv_reused=reused, normal_tensor_iterations=4,
        triangles=len(faces), vertices=len(vertices), occupied_texels=int(occupied.sum()),
        uv_interior_overlap_texels=0, exact_reduced_triangles=True,
        color_support_distance_percentiles=np.percentile(np.concatenate(distance_stats), [50, 95, 99, 100]).tolist(),
        masks='Approximate color-based material regions; dark mask also includes brows/eyes. No semantic ground-truth claim.',
        material='Conventional lit PBR; uniform roughness .85, metallic 0; no normal map',
        seconds=time.monotonic()-started)
    (args.output/'bake.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage', choices=['setup', 'reduce', 'bake', 'dense'])
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--source', type=Path)
    p.add_argument('--checkpoint', type=Path)
    p.add_argument('--color-cloud', type=Path)
    p.add_argument('--output', type=Path)
    p.add_argument('--texture-size', type=int, default=2048)
    p.add_argument('--neighbors', type=int, default=16)
    args = p.parse_args()
    return globals()[args.stage](args)


if __name__ == '__main__':
    main()
