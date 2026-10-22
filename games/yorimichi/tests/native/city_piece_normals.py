"""Exercise the actual city partitioner on the pier's precision-sensitive corner normals.

Run with guarded Blender and a fresh --output directory. This prepares no world.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

import bpy
import numpy as np

GAME = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(GAME / 'world'), str(GAME / 'world/regions'),
               str(GAME / 'world/regions/skatepark'), str(Path(__file__).parent)]
import city_surface_tiles as city
import features
import geom
from mesh_pieces import capture, create_mesh, values
from piece_normals import faces
from atelier.blender.fbx import export_fbx


def export_object(obj, path):
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    export_fbx(filepath=str(path), use_selection=True, apply_unit_scale=True,
               apply_scale_options='FBX_SCALE_ALL', axis_forward='-Y', axis_up='Z',
               object_types={'MESH'}, mesh_smooth_type='FACE', bake_anim=False,
               use_custom_props=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
    assert not args.output.exists()
    assets = args.output / 'hidamari/assets'
    assets.mkdir(parents=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    material = bpy.data.materials.new('HDS_normal_fixture')
    original = geom.to_object(features.pier(), material)
    source_path = assets / 'HD_Terrain.fbx'
    export_object(original, source_path)
    bpy.data.objects.remove(original, do_unlink=True)
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=str(source_path), use_anim=False, use_custom_normals=True)
    reference, = [obj for obj in bpy.data.objects if obj not in before]
    whole = capture(reference.data)
    matrix = np.asarray(reference.matrix_world, dtype=np.float64)
    world = whole['positions'] @ matrix[:3, :3].T + matrix[:3, 3]
    expected = dict(triangles=int(sum(whole['counts'] - 2)), collision_boxes=0,
                    min=world.min(axis=0).tolist(), max=world.max(axis=0).tolist())
    control = args.output / 'whole-control.fbx'
    export_object(reference, control)
    bpy.data.objects.remove(reference, do_unlink=True)

    observed = dict(pieces=0, corners=0, old_setter_error=0.)

    def checked_mesh(name, piece):
        mesh = create_mesh(name, piece)
        assert values(mesh.corner_normals, 'vector', 3).tobytes() == piece['normals'].tobytes()
        compressed = mesh.copy()
        compressed.attributes.remove(compressed.attributes['custom_normal'])
        compressed.normals_split_custom_set(piece['normals'].tolist())
        observed['old_setter_error'] = max(observed['old_setter_error'], float(np.max(np.abs(
            values(compressed.corner_normals, 'vector', 3) - piece['normals']))))
        bpy.data.meshes.remove(compressed)
        observed['pieces'] += 1
        observed['corners'] += len(piece['normals'])
        return mesh

    # Observe the unchanged production call's actual child data; never replace its partition logic.
    city.create_mesh = checked_mesh
    city.yori.OUT = args.output
    destination = args.output / 'pieces'
    destination.mkdir()
    row = city.partition('HD_Terrain', destination, 32., expected)
    actual = Counter()
    for tile in row['tiles']:
        assert 0 < tile['triangles'] <= city.TRIANGLE_LIMIT
        actual.update(faces(destination / (tile['name'] + '.fbx')))
    assert observed['pieces'] > 1 and observed['pieces'] == len(row['tiles'])
    assert observed['corners'] == len(whole['normals'])
    assert observed['old_setter_error'] > 2e-5, 'Fixture must reproduce former fan-space quantization'
    assert actual == faces(control), 'City pieces changed expanded exported polygon corner normals'
    observed.update(bitwise_corner_storage=True, exported_polygon_corners_equal=True,
                    triangles=row['source_triangles'])
    (args.output / 'result.json').write_text(json.dumps(observed, indent=2) + '\n')
    print('CITY PIECE NORMALS EXACT VERIFIED', flush=True)


if __name__ == '__main__':
    main()
