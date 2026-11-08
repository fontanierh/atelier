"""Convert the current scene extraction to Yorimichi's committed model library.

This is an acquisition tool, run once in guarded Blender. Normal builds use only
the committed GLBs and manifest. Source collision hulls are exported separately;
plants and embedded foliage never enter the render library.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'world'))
import yori  # noqa: E402,F401
from belmonte.source import native_colours  # noqa: E402


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bounds(objects):
    points = np.array([tuple(obj.matrix_world @ vertex.co) for obj in objects for vertex in obj.data.vertices])
    return [points.min(axis=0).tolist(), points.max(axis=0).tolist()]


def remove_plants(obj):
    """Keep connected foliage bounds as planting hints, then remove those faces."""
    mesh = obj.data
    green = {i for i, material in enumerate(mesh.materials) if 'foliage' in material.name.lower()}
    faces = [face for face in mesh.polygons if face.material_index in green]
    if not faces:
        return [], 0
    parents = {}

    def find(index):
        parents.setdefault(index, index)
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    for face in faces:
        root = find(face.vertices[0])
        for vertex in face.vertices[1:]:
            parents[find(vertex)] = root
    groups = {}
    for index in parents:
        groups.setdefault(find(index), []).append(obj.matrix_world @ mesh.vertices[index].co)
    hints = []
    for points in groups.values():
        points = np.array([tuple(point) for point in points])
        lo, hi = points.min(0), points.max(0)
        hints.append({'base_m': [(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]],
                      'size_m': (hi - lo).tolist()})
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.delete(bm, geom=[face for face in bm.faces if face.material_index in green], context='FACES')
    bm.to_mesh(mesh)
    bm.free()
    return hints, len(faces)


def save(objects, path):
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.export_scene.gltf(filepath=str(path), export_format='GLB', use_selection=True,
                              export_materials='EXPORT', export_animations=False,
                              export_vertex_color='ACTIVE', export_all_vertex_colors=False,
                              export_cameras=False, export_lights=False, export_yup=True)
    assert path.is_file() and path.stat().st_size > 0, path
    native_colours(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--only', help='One named mesh for a conversion diagnostic; writes no scene manifest')
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    scene = json.loads((args.source / 'scene.json').read_text())
    assert not scene['dry_run']
    model_dir = args.output / 'meshes'
    model_dir.mkdir(parents=True, exist_ok=True)
    models = {}
    for index, entry in enumerate(scene['meshes']):
        if args.only and entry['name'] != args.only:
            continue
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        for material in list(bpy.data.materials):
            if material.users == 0:
                bpy.data.materials.remove(material)
        source = args.source / entry['fbx']
        assert digest(source) == entry['sha256'], source
        bpy.ops.import_scene.fbx(filepath=str(source), use_custom_normals=True)
        objects = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']
        hulls = [obj for obj in objects if obj.name.startswith(('UCX_', 'UBX_', 'USP_', 'UCP_'))]
        render = [obj for obj in objects if obj not in hulls]
        assert len(render) == 1, (entry['name'], [obj.name for obj in render])
        expected = np.array(entry['bounds_cm'])[:, [0, 1, 2]] / 100
        expected[:, 1] *= -1
        expected[:, 1] = expected[::-1, 1]
        actual = np.array(bounds(render))
        assert np.max(np.abs(expected - actual)) < .02, (entry['name'], expected, actual)
        bpy.ops.object.select_all(action='DESELECT')
        for item in objects:
            item.select_set(True)
        bpy.context.view_layer.objects.active = render[0]
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        obj = render[0]
        original_triangles = sum(len(face.vertices) - 2 for face in obj.data.polygons)
        hints, removed = remove_plants(obj)
        name = 'SM_BM_' + entry['name'].removeprefix('SM_')
        obj.name = name
        # Slot names retain source indices even if unused slots are omitted by glTF.
        for slot, material in enumerate(obj.data.materials):
            material.name = f'BM_{slot:03d}_{entry["slots"][slot]}'
            material.use_nodes = True
            material.node_tree.nodes.clear()
            principled = material.node_tree.nodes.new('ShaderNodeBsdfPrincipled')
            principled.inputs['Base Color'].default_value = (1, 1, 1, 1)
            principled.inputs['Roughness'].default_value = .9
            output = material.node_tree.nodes.new('ShaderNodeOutputMaterial')
            material.node_tree.links.new(principled.outputs['BSDF'], output.inputs['Surface'])
        path = model_dir / (name + '.glb')
        save(render, path)
        info = {'name': name, 'path': path.relative_to(args.output).as_posix(), 'sha256': digest(path),
                'source_asset': entry['source_asset'], 'bounds_m': bounds(render),
                'source_triangles': original_triangles,
                'triangles': sum(len(face.vertices) - 2 for face in obj.data.polygons),
                'slots': entry['slots'], 'embedded_plants': hints, 'removed_foliage_faces': removed}
        hulls = [hull for hull in hulls if hull.data.polygons]
        if hulls:
            collision = model_dir / (name + '_Collision.glb')
            save(hulls, collision)
            info['collision'] = {'path': collision.relative_to(args.output).as_posix(), 'sha256': digest(collision)}
        models[entry['source_asset']] = info
        print(f'BELMONTE CONVERT {index + 1}/{len(scene["meshes"])} {name}: {info["triangles"]} triangles', flush=True)
    if args.only:
        return
    result = {'version': 1, 'source': {'repository': 'Polozer/HarasValley', 'revision': args.revision,
                                      'level': scene['level'], 'scene_sha256': digest(args.source / 'scene.json')},
              'units': 'metres, Blender Z up; model files use glTF Y up',
              'meshes': list(models.values()), 'placements': scene['placements'],
              'planting': scene['vegetation'], 'signs': scene['signs'],
              'materials': scene['materials'], 'textures': scene['textures'], 'excluded': scene['excluded']}
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'source.json').write_text(json.dumps(result, separators=(',', ':')) + '\n')


if __name__ == '__main__':
    main()
