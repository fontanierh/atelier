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
from atelier.mesh_cells import cell_face_groups
from mesh_pieces import capture, subset, create_mesh

ROOT = yori.WORLD
SOURCES = ('HD_Terrain', 'HD_Streets', 'HD_Square')
TRIANGLE_LIMIT = 32768


def partition(source, folder, size, expected):
    path = yori.OUT / 'hidamari/assets' / (source + '.fbx')
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=str(path), use_anim=False, use_custom_normals=True)
    imported = [ob for ob in bpy.data.objects if ob not in before]
    meshes = [ob for ob in imported if ob.type == 'MESH' and not ob.name.startswith('UCX_')]
    assert len(meshes) == 1, (source, [ob.name for ob in meshes])
    original = meshes[0]
    mesh = original.data
    # The sources share surface materials: a later import names its copies X.001, which would export as slot X_001.
    for i, slot in enumerate(mesh.materials):
        base = slot and slot.name.rpartition('.')[0]
        if base and slot.name.rpartition('.')[2].isdigit() and base in bpy.data.materials:
            mesh.materials[i] = bpy.data.materials[base]
    whole = capture(mesh)
    positions, starts, counts, vertex_indices = (whole[key] for key in ('positions', 'starts', 'counts', 'vertex_indices'))
    # Preserve the existing tile export policy: custom whole-source corner normals on smooth faces.
    whole['smooth'] = np.ones(len(mesh.polygons), dtype=np.bool_)
    assert whole['uvs'] and whole['colours'], source
    assert sum(counts - 2) == expected['triangles'], (source, 'source FBX differs from production triangle count')
    assert np.isfinite(positions).all() and np.isfinite(whole['normals']).all()
    # Existing exports are in metres. Validate their world bounds against the
    # production export receipt before assigning metre-sized visibility cells.
    matrix = np.array(original.matrix_world, dtype=np.float64)
    world_positions = positions @ matrix[:3, :3].T + matrix[:3, 3]
    assert np.allclose(world_positions.min(axis=0), expected['min'], atol=.001, rtol=0), source
    assert np.allclose(world_positions.max(axis=0), expected['max'], atol=.001, rtol=0), source
    centers = np.add.reduceat(world_positions[vertex_indices], starts, axis=0) / counts[:, None]
    source_faces = [vertex_indices[start:start + count].tolist() for start, count in zip(starts, counts)]
    pieces = cell_face_groups(world_positions, source_faces, size, triangle_limit=TRIANGLE_LIMIT,
                             locations=centers[:, :2].tolist())
    tiles = []
    total_polygons = total_triangles = 0
    for cx, cy, suffix, members in pieces:
        piece = subset(whole, members)
        name = f'{source}_cell_{cx}_{cy}' + ('_Piece' + suffix if suffix else '')
        # The previous tile writer always emitted FLOAT_COLOR, even for byte-colour input.
        piece['colours'] = [(name, domain, 'FLOAT_COLOR', colour) for name, domain, _, colour in piece['colours']]
        data = create_mesh(name, piece)
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
        tri = piece['triangles']
        assert tri <= TRIANGLE_LIMIT, (name, tri)
        bounds = world_positions[piece['used']]
        tiles.append(dict(name=name, polygons=len(members), triangles=tri,
                          min=bounds.min(axis=0).tolist(), max=bounds.max(axis=0).tolist(),
                          sha256=hashlib.sha256(destination.read_bytes()).hexdigest()))
        total_polygons += len(members)
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
    if folder.exists():   # a rebuild replaces this tag's previous output
        __import__('shutil').rmtree(folder)
    folder.mkdir(parents=True, exist_ok=False)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    expected = json.loads((yori.OUT / 'hidamari/manifest.json').read_text())
    report = dict(tag=args.tag, cell_metres=args.size, triangle_limit=TRIANGLE_LIMIT, sources={})
    for source in args.sources:
        report['sources'][source] = partition(source, folder, args.size, expected[source])
        (folder / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    report['complete'] = True
    (folder / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    print('CITY SURFACE TILES COMPLETE', args.tag,
          sum(len(s['tiles']) for s in report['sources'].values()), flush=True)


if __name__ == '__main__':
    main()
