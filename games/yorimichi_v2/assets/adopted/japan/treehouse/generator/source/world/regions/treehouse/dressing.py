"""Partition only the completed, baked TH_Dressing object; its whole stays in the authoring blend."""
import hashlib
import sys
from pathlib import Path

import bpy
import numpy as np
from atelier.atomic_files import atomic_json
from atelier.blender.fbx import export_fbx
from atelier.mesh_cells import cell_face_groups
from atelier.model_files import regular_files, retain_files
from mesh_pieces import capture, subset, create_mesh

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from treehouse_pieces import CELL_METRES, PARENT, TRIANGLE_LIMIT, UVS, members  # noqa: E402


def export(obj, out):
    """@cc [owner:fontanierh,label:correctness] dressing-preserves-shared-fade-bake
    The original shared Frame/Dressing capsule table MUST be baked before capture.
    Subdivision MUST copy all five UV channels without recomputing fade groups,
    recentering coordinates or changing corners, colour type, materials or normals.
    The whole diagnostic object MUST stay in Treehouse.blend, never production FBX.
    """
    assert obj.name == PARENT and np.array_equal(np.array(obj.matrix_world), np.eye(4))
    folder = Path(out) / 'dressing'
    old = Path(out) / (PARENT + '.fbx')
    if (any(p.is_symlink() for p in (folder.absolute(), *folder.absolute().parents))
            or old.is_symlink() or (old.exists() and not old.is_file())):
        raise ValueError('Invalid dressing generated source destination')
    if folder.exists():
        regular_files(folder)  # Refuse member links/special files before any export writes.
    source = capture(obj.data)
    assert tuple(name for name, _ in source['uvs']) == UVS, 'Missing original shared fade bake'
    faces = [source['vertex_indices'][start:start + count].tolist()
             for start, count in zip(source['starts'], source['counts'])]
    groups = cell_face_groups(source['positions'], faces, CELL_METRES, triangle_limit=TRIANGLE_LIMIT)
    folder.mkdir(parents=True, exist_ok=True)
    owned = np.zeros(len(faces), dtype=np.int32)
    rows = []
    for x, y, suffix, indices in groups:
        np.add.at(owned, list(indices), 1)
        piece = subset(source, indices)
        name = f'{PARENT}_cell_{x}_{y}' + ('_Piece' + suffix if suffix else '')
        data = create_mesh(name, piece)
        child = bpy.data.objects.new(name, data)
        bpy.context.collection.objects.link(child)
        child.matrix_world = obj.matrix_world.copy()
        bpy.ops.object.select_all(action='DESELECT')
        child.select_set(True)
        bpy.context.view_layer.objects.active = child
        path = folder / (name + '.fbx')
        try:
            export_fbx(filepath=str(path), use_selection=True, apply_unit_scale=True,
                       apply_scale_options='FBX_SCALE_ALL', axis_forward='-Y', axis_up='Z',
                       object_types={'MESH'}, mesh_smooth_type='FACE', bake_anim=False, use_custom_props=False)
            rows.append(dict(name=name, triangles=piece['triangles'],
                             used_slots=[slot.name for i, slot in enumerate(piece['slots']) if i in set(piece['materials'])],
                             min=piece['positions'].min(0).tolist(), max=piece['positions'].max(0).tolist(),
                             sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        finally:
            bpy.data.objects.remove(child, do_unlink=True)
            bpy.data.meshes.remove(data)
    assert (owned == 1).all(), 'Every original dressing face requires one owner'
    result = dict(version=1, complete=True, parent=PARENT, triangle_limit=TRIANGLE_LIMIT,
                  cell_metres=CELL_METRES, uv_channels=list(UVS), collision_boxes=0,
                  source_triangles=int(sum(source['counts'] - 2)),
                  min=source['positions'].min(0).tolist(), max=source['positions'].max(0).tolist(),
                  slots=[slot.name for slot in source['slots']], pieces=rows)
    members(result)
    retain_files(folder, [row['name'] + '.fbx' for row in rows])
    atomic_json(Path(out).parent / 'pieces.json', result)
    # Retire only this exact superseded source after complete current exports.
    old.unlink(missing_ok=True)
    return result
