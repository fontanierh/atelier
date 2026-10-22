"""Partition existing city FBXs without simplifying faces or changing attributes.

Run with guarded Blender; output is isolated under out/city_surface_tiles/TAG.
Each original polygon belongs to one spatial bucket. Polygons are never clipped;
their actual bounds, including any crossing a cell edge, drive Unreal culling.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parent)); import yori  # noqa: E402,F401
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import bpy
import numpy as np
from atelier.mesh_cells import cell_face_groups
from atelier.conventions import to_unreal
from atelier.model_files import regular_files, retain_files
from atelier.atomic_files import atomic_json
from mesh_pieces import capture, subset, create_mesh

ROOT = yori.WORLD
TRIANGLE_LIMIT = 32768


def partition(source, folder, size, expected):
    """@cc [owner:fontanierh,label:correctness] city-pieces-share-complete-corner-copy
    City subdivision MUST use the common complete-corner copier. Captured imported-source
    float32 normals MUST remain bitwise identical in each child; source smoothing, material
    bindings and every UV/colour layer and colour type MUST survive the same face mapping.
    """
    path = yori.OUT / 'hidamari/assets' / (source + '.fbx')
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=str(path), use_anim=False, use_custom_normals=True)
    imported = [ob for ob in bpy.data.objects if ob not in before]
    meshes = [ob for ob in imported if ob.type == 'MESH' and not ob.name.startswith('UCX_')]
    assert len(meshes) == 1, (source, [ob.name for ob in meshes])
    collision = [ob for ob in imported if ob.type == 'MESH' and ob.name.startswith('UCX_')]
    assert len(collision) == expected['collision_boxes'], (source, 'authored collision membership')
    assert len(meshes) + len(collision) == len(imported), (source, 'unsupported source object')
    collision_vertices = [sorted([list(to_unreal(tuple(hull.matrix_world @ vertex.co)))
                                  for vertex in hull.data.vertices]) for hull in collision]
    original = meshes[0]
    mesh = original.data
    # The sources share surface materials: a later import names its copies X.001, which would export as slot X_001.
    for i, slot in enumerate(mesh.materials):
        base = slot and slot.name.rpartition('.')[0]
        if base and slot.name.rpartition('.')[2].isdigit() and base in bpy.data.materials:
            mesh.materials[i] = bpy.data.materials[base]
    source_data = capture(mesh)
    positions = source_data['positions']
    starts, counts = source_data['starts'], source_data['counts']
    vertex_indices = source_data['vertex_indices']
    assert source_data['uvs'] and source_data['colours'], source
    assert sum(counts - 2) == expected['triangles'], (source, 'source FBX differs from production triangle count')
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
    face_owners = np.zeros(len(mesh.polygons), dtype=np.int32)
    for cx, cy, suffix, members in pieces:
        selected = np.asarray(members, dtype=np.int32)
        assert len(selected) and (selected >= 0).all() and (selected < len(mesh.polygons)).all()
        np.add.at(face_owners, selected, 1)
        name = f'{source}_cell_{cx}_{cy}' + ('_Piece' + suffix if suffix else '')
        piece = subset(source_data, members)
        used = piece['used']
        data = create_mesh(name, piece)
        ob = bpy.data.objects.new(name, data)
        bpy.context.collection.objects.link(ob)
        ob.matrix_world = original.matrix_world.copy()
        bpy.ops.object.select_all(action='DESELECT')
        ob.select_set(True)
        # Whole authored UCX belongs to one component. Other pieces still own
        # their exact complex surface; no hidden render parent supplies physics.
        collision_names = []
        if not tiles:
            for index, hull in enumerate(collision):
                collision_names.append(hull.name)
                hull.name = f'UCX_{name}_{index:02d}'
                hull.select_set(True)
        bpy.context.view_layer.objects.active = ob
        destination = folder / (name + '.fbx')
        from atelier.blender.fbx import export_fbx as export_scene_fbx
        try:
            export_scene_fbx(filepath=str(destination), use_selection=True,
                apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL', axis_forward='-Y', axis_up='Z',
                object_types={'MESH'}, mesh_smooth_type='FACE', bake_anim=False, use_custom_props=False)
        finally:
            for hull, old_name in zip(collision, collision_names):
                hull.name = old_name
        tri = piece['triangles']
        assert tri <= TRIANGLE_LIMIT, (name, tri)
        bounds = world_positions[used]
        tiles.append(dict(name=name, polygons=len(selected), triangles=tri,
                          collision_hulls=len(collision) if not tiles else 0,
                          min=bounds.min(axis=0).tolist(), max=bounds.max(axis=0).tolist(),
                          sha256=hashlib.sha256(destination.read_bytes()).hexdigest()))
        total_polygons += len(selected)
        total_triangles += tri
        bpy.data.objects.remove(ob, do_unlink=True)
        bpy.data.meshes.remove(data)
    assert (face_owners == 1).all(), (source, 'every original face must have exactly one owner')
    assert total_polygons == len(mesh.polygons) and total_triangles == expected['triangles']
    result = dict(source_fbx_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                  source_triangles=total_triangles, source_polygons=total_polygons,
                  source_collision_hulls=len(collision),
                  source_collision_vertices=collision_vertices,
                  source_material_slots=[material.name for material in mesh.materials],
                  source_bounds=dict(min=expected['min'],max=expected['max']),
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
    parser.add_argument('--sources', nargs='+', required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
    assert args.tag.replace('_', '').isalnum() and 32 <= args.size <= 256
    root = yori.OUT / 'city_surface_tiles' / args.tag
    expected = json.loads((yori.OUT / 'hidamari/manifest.json').read_text())
    # Roster changes belong to recipe/product admission. This generic selected
    # splitter must not change its key whenever a sibling source is added.
    assert all(re.fullmatch(r'HD_[A-Za-z0-9_]+', source) for source in args.sources), 'Invalid city source name'
    assert len({source.casefold() for source in args.sources}) == len(args.sources), 'Duplicate city source'
    assert all(source in expected for source in args.sources), 'Missing selected city source'
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for source in args.sources:
        folder = root / source
        # This source exclusively owns this generated folder. Check all lexical
        # ancestors and existing members before any write or retirement.
        absolute = folder.absolute()
        if any(path.is_symlink() for path in (absolute, *absolute.parents)):
            raise ValueError('Linked city piece export root')
        if folder.exists():
            regular_files(folder)
        folder.mkdir(parents=True, exist_ok=True)
        row = partition(source, folder, args.size, expected[source])
        report = dict(version=2, complete=True, tag=args.tag, cell_metres=args.size,
                      triangle_limit=TRIANGLE_LIMIT, sources={source: row})
        atomic_json(folder / 'manifest.json', report)
        retain_files(folder, {'manifest.json', *(tile['name']+'.fbx' for tile in row['tiles'])})
        print('CITY SURFACE SOURCE COMPLETE', source, len(row['tiles']), flush=True)
    print('CITY SURFACE TILES COMPLETE', args.tag, flush=True)


if __name__ == '__main__':
    main()
