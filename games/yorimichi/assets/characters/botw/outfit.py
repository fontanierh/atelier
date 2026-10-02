"""Dress Link's library body in clothing from the extended catalog (roster `outfit`), as one rigged GLB for bake.py.

Each garment GLB carries its own copy of Link's skeleton, at the same rest pose, plus the cloth bones it adds (the
Champion's Tunic's skirt chains). The garment's meshes, materials and textures are appended to the body; its skins are
rebuilt on the body's bones, by name, and its extra bones are added under their parents at their rest pose (they stay
there: no curve drives them, as in the library viewer). The body parts a garment covers are dropped, by the library
viewer's own rules (avatar.js, updateBodyVisibility), except for the belts: the viewer hides them under real upper
clothing, but the Champion's Tunic is open at the waist where they sit.

Plain Python, like bake.py.
"""
import re

import bake

# The library viewer's body visibility, belts kept: (body mesh name pattern, the slot that hides it, only for real
# clothing).
COVERED = [
    (r'Armor_Default_Head', 'head', False), (r'Armor_Default_Upper', 'upper', False),
    (r'Armor_Default_Lower', 'lower', False), (r'^Skin__Mt_Upper_Skin', 'upper', True),
    (r'^Skin__Mt_Lower_Skin|^Skin__Mt_Underwear', 'lower', True), (r'^Earring__', 'head', True),
]


def _view(gltf, binary, index):
    view = gltf['bufferViews'][index]
    start = view.get('byteOffset', 0)
    return bytes(binary[start:start + view['byteLength']]), view


def _append(body, binary, garment, data):
    """Copy the garment's accessors, images, samplers, textures, materials and meshes into the body; returns the
    index maps (accessor, material, mesh)."""
    views = {}

    def view(index):
        if index not in views:
            chunk, source = _view(garment, data, index)
            binary.extend(b'\x00' * (-len(binary) % 4))
            copied = {k: v for k, v in source.items() if k not in ('buffer', 'byteOffset')}
            body['bufferViews'].append({'buffer': 0, 'byteOffset': len(binary), **copied})
            binary.extend(chunk)
            views[index] = len(body['bufferViews']) - 1
        return views[index]

    accessors = {}
    for i, accessor in enumerate(garment.get('accessors', [])):
        body['accessors'].append({**accessor, 'bufferView': view(accessor['bufferView'])})
        accessors[i] = len(body['accessors']) - 1
    images = {}
    for i, image in enumerate(garment.get('images', [])):
        body.setdefault('images', []).append({**image, 'bufferView': view(image['bufferView'])})
        images[i] = len(body['images']) - 1
    samplers = {}
    for i, sampler in enumerate(garment.get('samplers', [])):
        body.setdefault('samplers', []).append(sampler)
        samplers[i] = len(body['samplers']) - 1
    textures = {}
    for i, texture in enumerate(garment.get('textures', [])):
        copied = {**texture, 'source': images[texture['source']]}
        if 'sampler' in texture:
            copied['sampler'] = samplers[texture['sampler']]
        body.setdefault('textures', []).append(copied)
        textures[i] = len(body['textures']) - 1

    def retexture(value):
        if isinstance(value, dict):
            return {k: (textures[v] if k == 'index' else retexture(v)) for k, v in value.items()}
        return value

    materials = {}
    for i, material in enumerate(garment.get('materials', [])):
        body['materials'].append(retexture(material))
        materials[i] = len(body['materials']) - 1
    meshes = {}
    for i, mesh in enumerate(garment.get('meshes', [])):
        primitives = []
        for primitive in mesh['primitives']:
            copied = {**primitive, 'attributes': {k: accessors[v] for k, v in primitive['attributes'].items()}}
            if 'indices' in primitive:
                copied['indices'] = accessors[primitive['indices']]
            if 'material' in primitive:
                copied['material'] = materials[primitive['material']]
            copied.pop('targets', None)
            primitives.append(copied)
        body['meshes'].append({**mesh, 'primitives': primitives})
        meshes[i] = len(body['meshes']) - 1
    return accessors, meshes


def dress(body_glb, garments, out_glb):
    """Write `out_glb`: the body with `garments` [{'glb', 'slot', 'default'}] on, and the covered body parts removed."""
    body, binary = bake.read_glb(body_glb)
    names = {node.get('name'): i for i, node in enumerate(body['nodes'])}
    for garment_spec in garments:
        garment, data = bake.read_glb(garment_spec['glb'])
        accessors, meshes = _append(body, binary, garment, data)
        parents = {child: i for i, node in enumerate(garment['nodes']) for child in node.get('children', [])}
        joints = {joint for skin in garment['skins'] for joint in skin['joints']}
        mapped = {}

        def bone(index):
            """The body node for garment joint `index`, adding a cloth bone (and its missing parents) at rest."""
            if index in mapped:
                return mapped[index]
            node = garment['nodes'][index]
            if node.get('name') in names:
                mapped[index] = names[node['name']]
                return mapped[index]
            parent = bone(parents[index])
            copied = {k: v for k, v in node.items() if k in ('name', 'translation', 'rotation', 'scale', 'matrix')}
            body['nodes'].append(copied)
            mapped[index] = names[node['name']] = len(body['nodes']) - 1
            body['nodes'][parent].setdefault('children', []).append(mapped[index])
            return mapped[index]

        for joint in sorted(joints):
            bone(joint)
        skins = {}
        for i, skin in enumerate(garment['skins']):
            body['skins'].append({'joints': [bone(j) for j in skin['joints']],
                                  'inverseBindMatrices': accessors[skin['inverseBindMatrices']]})
            skins[i] = len(body['skins']) - 1
        scene = body['scenes'][body.get('scene', 0)]['nodes']
        for node in garment['nodes']:
            if 'mesh' in node:
                body['nodes'].append({'name': node['name'], 'mesh': meshes[node['mesh']], 'skin': skins[node['skin']]})
                scene.append(len(body['nodes']) - 1)
    worn = {g['slot']: g for g in garments}
    covered = [pattern for pattern, slot, real in COVERED if slot in worn and not (real and worn[slot].get('default'))]
    dropped = [i for i, node in enumerate(body['nodes']) if 'mesh' in node and any(re.search(p, node.get('name', ''))
                                                                                   for p in covered)]
    _drop_nodes(body, set(dropped))
    bake.write_glb(out_glb, body, binary)
    return {'garments': [g['id'] for g in garments], 'dropped': len(dropped), 'bones': len(names)}


def _drop_nodes(gltf, dropped):
    """Remove mesh nodes (leaves) and the meshes only they used, renumbering every reference."""
    keep = [i for i in range(len(gltf['nodes'])) if i not in dropped]
    renumber = {old: new for new, old in enumerate(keep)}
    nodes = [gltf['nodes'][i] for i in keep]
    for node in nodes:
        if 'children' in node:
            node['children'] = [renumber[c] for c in node['children'] if c in renumber]
    for skin in gltf.get('skins', []):
        skin['joints'] = [renumber[j] for j in skin['joints']]
        if 'skeleton' in skin:
            skin['skeleton'] = renumber[skin['skeleton']]
    for scene in gltf['scenes']:
        scene['nodes'] = [renumber[n] for n in scene['nodes'] if n in renumber]
    used = sorted({node['mesh'] for node in nodes if 'mesh' in node})
    meshes = {old: new for new, old in enumerate(used)}
    gltf['meshes'] = [gltf['meshes'][i] for i in used]
    for node in nodes:
        if 'mesh' in node:
            node['mesh'] = meshes[node['mesh']]
    gltf['nodes'] = nodes
