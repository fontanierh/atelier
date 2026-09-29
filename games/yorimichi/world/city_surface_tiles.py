"""Partition existing city FBXs without simplifying faces or changing attributes.

Run with guarded Blender; output is isolated under out/city_surface_tiles/TAG.
Each original polygon belongs to one spatial bucket. Polygons are never clipped;
their actual bounds, including any crossing a cell edge, drive Unreal culling.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parent)); import yori  # noqa: E402,F401
import argparse
import hashlib
import json
import sys
from pathlib import Path

import bpy
import numpy as np

ROOT = yori.WORLD
SOURCES = ('HD_Terrain', 'HD_Streets', 'HD_Square')


def values(collection, property_name, width, dtype=np.float32):
    data = np.empty(len(collection) * width, dtype=dtype)
    collection.foreach_get(property_name, data)
    return data.reshape(-1, width) if width > 1 else data


def partition(source, folder, size, expected):
    path = yori.OUT / 'hidamari/assets' / (source + '.fbx')
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=str(path), use_anim=False, use_custom_normals=True)
    imported = [ob for ob in bpy.data.objects if ob not in before]
    meshes = [ob for ob in imported if ob.type == 'MESH' and not ob.name.startswith('UCX_')]
    assert len(meshes) == 1, (source, [ob.name for ob in meshes])
    original = meshes[0]
    mesh = original.data
    positions = values(mesh.vertices, 'co', 3)
    starts = values(mesh.polygons, 'loop_start', 1, np.int32)
    counts = values(mesh.polygons, 'loop_total', 1, np.int32)
    vertex_indices = values(mesh.loops, 'vertex_index', 1, np.int32)
    normals = values(mesh.corner_normals, 'vector', 3)
    materials = values(mesh.polygons, 'material_index', 1, np.int32)
    uvs = [(layer.name, values(layer.data, 'uv', 2)) for layer in mesh.uv_layers]
    colours = [(layer.name, layer.domain, values(layer.data, 'color', 4))
               for layer in mesh.color_attributes]
    assert len(normals) == len(mesh.loops) and uvs and colours, source
    assert sum(counts - 2) == expected['triangles'], (source, 'source FBX differs from production triangle count')
    assert np.isfinite(positions).all() and np.isfinite(normals).all()
    # Existing exports are in metres. Validate their world bounds against the
    # production export receipt before assigning metre-sized visibility cells.
    matrix = np.array(original.matrix_world, dtype=np.float64)
    world_positions = positions @ matrix[:3, :3].T + matrix[:3, 3]
    assert np.allclose(world_positions.min(axis=0), expected['min'], atol=.001, rtol=0), source
    assert np.allclose(world_positions.max(axis=0), expected['max'], atol=.001, rtol=0), source
    centers = np.add.reduceat(world_positions[vertex_indices], starts, axis=0) / counts[:, None]
    cell = np.floor(centers[:, :2] / size).astype(np.int32)
    keys, membership = np.unique(cell, axis=0, return_inverse=True)
    tiles = []
    total_polygons = total_triangles = 0
    for number, (cx, cy) in enumerate(keys):
        selected = np.flatnonzero(membership == number)
        loop_map = np.concatenate([np.arange(starts[i], starts[i] + counts[i]) for i in selected])
        used, remapped = np.unique(vertex_indices[loop_map], return_inverse=True)
        lengths = counts[selected]
        ends = np.cumsum(lengths)
        faces = np.split(remapped, ends[:-1])
        name = f'{source}_cell_{int(cx)}_{int(cy)}'
        data = bpy.data.meshes.new(name)
        data.from_pydata(positions[used].tolist(), [], [face.tolist() for face in faces])
        data.update()
        for material in mesh.materials:
            data.materials.append(material)
        data.polygons.foreach_set('material_index', materials[selected])
        data.polygons.foreach_set('use_smooth', np.ones(len(selected), dtype=np.bool_))
        data.normals_split_custom_set(normals[loop_map].tolist())
        for layer_name, uv in uvs:
            layer = data.uv_layers.new(name=layer_name)
            layer.data.foreach_set('uv', uv[loop_map].ravel())
        for layer_name, domain, colour in colours:
            assert domain in ('POINT', 'CORNER'), domain
            layer = data.color_attributes.new(name=layer_name, type='FLOAT_COLOR', domain=domain)
            layer.data.foreach_set('color', colour[used if domain == 'POINT' else loop_map].ravel())
        # Verify the attributes in the actual new mesh, not just the partition math.
        assert np.array_equal(values(data.vertices, 'co', 3), positions[used])
        assert np.allclose(values(data.corner_normals, 'vector', 3), normals[loop_map], atol=2e-5)
        for layer_name, uv in uvs:
            assert np.array_equal(values(data.uv_layers[layer_name].data, 'uv', 2), uv[loop_map])
        for layer_name, domain, colour in colours:
            assert np.allclose(values(data.color_attributes[layer_name].data, 'color', 4),
                               colour[used if domain == 'POINT' else loop_map], atol=1e-7)
        ob = bpy.data.objects.new(name, data)
        bpy.context.collection.objects.link(ob)
        ob.matrix_world = original.matrix_world.copy()
        bpy.ops.object.select_all(action='DESELECT')
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        destination = folder / (name + '.fbx')
        bpy.ops.export_scene.fbx(filepath=str(destination), use_selection=True,
            apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL', axis_forward='-Y', axis_up='Z',
            object_types={'MESH'}, mesh_smooth_type='FACE', bake_anim=False, use_custom_props=False)
        tri = int(sum(lengths - 2))
        bounds = world_positions[used]
        tiles.append(dict(name=name, polygons=len(selected), triangles=tri,
                          min=bounds.min(axis=0).tolist(), max=bounds.max(axis=0).tolist(),
                          sha256=hashlib.sha256(destination.read_bytes()).hexdigest()))
        total_polygons += len(selected)
        total_triangles += tri
        bpy.data.objects.remove(ob, do_unlink=True)
        bpy.data.meshes.remove(data)
    assert total_polygons == len(mesh.polygons) and total_triangles == expected['triangles']
    result = dict(source_fbx_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                  source_triangles=total_triangles, source_polygons=total_polygons,
                  source_matrix=matrix.tolist(), tiles=tiles,
                  attributes_verified=['positions', 'corner_normals', 'all_uvs', 'all_vertex_colours'])
    for ob in imported:
        data = ob.data if ob.type == 'MESH' else None
        bpy.data.objects.remove(ob, do_unlink=True)
        if data and data.users == 0:
            bpy.data.meshes.remove(data)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--size', type=float, default=128)
    parser.add_argument('--sources', nargs='+', choices=SOURCES, default=list(SOURCES))
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
    assert args.tag.replace('_', '').isalnum() and 32 <= args.size <= 256
    folder = yori.OUT / 'city_surface_tiles' / args.tag
    folder.mkdir(parents=True, exist_ok=False)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    expected = json.loads((yori.OUT / 'hidamari/manifest.json').read_text())
    report = dict(tag=args.tag, cell_metres=args.size, sources={})
    for source in args.sources:
        report['sources'][source] = partition(source, folder, args.size, expected[source])
        (folder / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    report['complete'] = True
    (folder / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    print('CITY SURFACE TILES COMPLETE', args.tag,
          sum(len(s['tiles']) for s in report['sources'].values()), flush=True)


if __name__ == '__main__':
    main()
