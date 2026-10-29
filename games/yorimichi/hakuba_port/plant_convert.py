"""Blender script: writes one detail level of a Yorimichi tree, an FBX, as a GLB of triangle corners per material.

    blender --background --threads 3 --python plant_convert.py -- LEVEL.fbx OUT.glb SLOT=TEXTURE...

A mesh without a material, such as a collision hull, is left out. The GLB has one root node, `full`, with one
primitive per material slot holding each triangle corner's position, normal, UV and RGBA colour (the foliage's wind
weights, kept as stored); corners alike in every attribute share one vertex. A slot shows the Hakuba texture its
`SLOT=TEXTURE` pair names; a slot whose name starts with `Leaf` or ends with `_Impostor` is cut out at `CUTOFF` and
drawn from both sides. Blender's Z-up frame becomes glTF's Y-up one, and UVs flip to glTF's top-left origin.
`plants.py` joins the levels into one plant.
"""
import json
import struct
import sys

import bpy

CUTOFF = 0.4


def level(path):
    """{slot: (positions, normals, uvs, colours)} of the meshes in one FBX, in world space."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=path, colors_type='LINEAR')
    slots = {}
    for obj in bpy.context.scene.objects:
        if obj.type != 'MESH' or not obj.material_slots:
            print(f'skipping {obj.name}: no material', file=sys.stderr)
            continue
        mesh = obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh()
        mesh.calc_loop_triangles()
        matrix, rotation = obj.matrix_world, obj.matrix_world.to_3x3().inverted().transposed()
        uv = mesh.uv_layers.active.data
        colour = mesh.color_attributes.active_color
        corner = colour is not None and colour.domain == 'CORNER'
        for tri in mesh.loop_triangles:
            name = obj.material_slots[tri.material_index].material.name.split('.')[0]
            p, n, t, c = slots.setdefault(name, ([], [], [], []))
            for loop in tri.loops:
                vertex = mesh.loops[loop].vertex_index
                x, y, z = matrix @ mesh.vertices[vertex].co
                p.append((x, z, -y))
                nx, ny, nz = (rotation @ mesh.corner_normals[loop].vector).normalized()
                n.append((nx, nz, -ny))
                u, v = uv[loop].uv
                t.append((u, 1.0 - v))
                c.append(tuple(colour.data[loop if corner else vertex].color) if colour else (1.0, 1.0, 1.0, 1.0))
    return slots


def cut_out(name):
    return name.startswith('Leaf') or name.endswith('_Impostor')


def write(slots, textures, out):
    blob, views, accessors = bytearray(), [], []

    def add(rows, kind, target):
        flat = [v for row in rows for v in row]
        data = struct.pack(f'<{len(flat)}f', *flat) if kind != 'SCALAR' else struct.pack(f'<{len(flat)}I', *flat)
        views.append({'buffer': 0, 'byteOffset': len(blob), 'byteLength': len(data), 'target': target})
        blob.extend(data)
        blob.extend(b'\0' * (-len(blob) % 4))
        accessors.append({'bufferView': len(views) - 1, 'componentType': 5125 if kind == 'SCALAR' else 5126,
                          'count': len(rows), 'type': kind})
        return len(accessors) - 1

    names = sorted(slots, key=lambda n: (cut_out(n), n))
    missing = [name for name in names if name not in textures]
    assert not missing, f'no texture named for slots {missing}'
    primitives = []
    for name in names:
        corners, indices = {}, []
        for corner in zip(*slots[name]):
            indices.append((corners.setdefault(corner, len(corners)),))
        p, n, t, c = zip(*corners)
        position = add(p, 'VEC3', 34962)
        accessors[position]['min'] = [min(r[i] for r in p) for i in range(3)]
        accessors[position]['max'] = [max(r[i] for r in p) for i in range(3)]
        attributes = {'POSITION': position, 'NORMAL': add(n, 'VEC3', 34962), 'TEXCOORD_0': add(t, 'VEC2', 34962),
                      'COLOR_0': add(c, 'VEC4', 34962)}
        primitives.append({'attributes': attributes, 'indices': add(indices, 'SCALAR', 34963),
                           'material': len(primitives)})
    materials = []
    for i, name in enumerate(names):
        material = {'name': name, 'pbrMetallicRoughness': {'baseColorTexture': {'index': i}, 'metallicFactor': 0.0,
                                                           'roughnessFactor': 1.0},
                    'extensions': {'KHR_materials_specular': {'specularFactor': 0.0}}}
        if cut_out(name):
            material.update(alphaMode='MASK', alphaCutoff=CUTOFF, doubleSided=True)
        materials.append(material)
    gltf = {'asset': {'version': '2.0'}, 'scene': 0, 'scenes': [{'nodes': [0]}], 'nodes': [{'name': 'full', 'mesh': 0}],
            'meshes': [{'name': 'full', 'primitives': primitives}], 'accessors': accessors, 'bufferViews': views,
            'materials': materials, 'textures': [{'source': i, 'sampler': 0} for i in range(len(names))],
            'images': [{'uri': f'../../textures/{textures[n]}/{textures[n]}.ktx2'} for n in names],
            'samplers': [{'wrapS': 10497, 'wrapT': 10497, 'magFilter': 9729, 'minFilter': 9987}],
            'extensionsUsed': ['KHR_materials_specular'], 'buffers': [{'byteLength': len(blob)}]}
    text = json.dumps(gltf, separators=(',', ':')).encode()
    text += b' ' * (-len(text) % 4)
    with open(out, 'wb') as fh:
        fh.write(struct.pack('<III', 0x46546C67, 2, 12 + 8 + len(text) + 8 + len(blob)))
        fh.write(struct.pack('<II', len(text), 0x4E4F534A) + text)
        fh.write(struct.pack('<II', len(blob), 0x004E4942) + bytes(blob))


def main():
    args = sys.argv[sys.argv.index('--') + 1:]
    source, out = args[:2]
    write(level(source), dict(pair.split('=', 1) for pair in args[2:]), out)


main()
