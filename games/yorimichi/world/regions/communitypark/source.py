"""Decode the pinned scene for mesh building, terrain support and geometry audits.

Only standard glTF arrays are read. No game binaries or native extraction tools run.
The complete hierarchy is flattened once into park-local Blender metres, preserving
each placement, render triangle, normal and both UV channels.
"""
import hashlib
import json
import struct
from functools import lru_cache
from pathlib import Path
import numpy as np
import yori

SPEC = yori.ASSETS / 'communitypark' / 'source.json'
FILE = yori.OUT / 'communitypark' / 'source' / 'megapark-textured.glb'
FRAME = np.array([[1., 0., 0.], [0., 0., -1.], [0., 1., 0.]])
TYPES = {5120: 'i1', 5121: 'u1', 5122: '<i2', 5123: '<u2', 5125: '<u4', 5126: '<f4'}
WIDTH = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}


def node_matrix(node):
    if 'matrix' in node:
        return np.asarray(node['matrix'], float).reshape(4, 4).T
    x, y, z, w = node.get('rotation', [0., 0., 0., 1.])
    r = np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                  [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                  [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])
    m = np.eye(4)
    m[:3, :3] = r @ np.diag(node.get('scale', [1., 1., 1.]))
    m[:3, 3] = node.get('translation', [0., 0., 0.])
    return m


class Scene:
    def __init__(self, data):
        magic, version, size = struct.unpack_from('<III', data)
        if magic != 0x46546C67 or version != 2 or size != len(data):
            raise ValueError('Invalid glTF 2 binary header')
        count, kind = struct.unpack_from('<II', data, 12)
        if kind != 0x4E4F534A:
            raise ValueError('Missing glTF JSON chunk')
        self.gltf = json.loads(data[20:20+count])
        count, kind = struct.unpack_from('<II', data, 20+count)
        if kind != 0x004E4942:
            raise ValueError('Missing glTF binary chunk')
        self.buffer = data[len(data)-count:]
        self.parts = []
        self.instances = []
        for root in self.gltf['scenes'][self.gltf.get('scene', 0)]['nodes']:
            self._visit(root, np.eye(4))

    def accessor(self, index):
        a = self.gltf['accessors'][index]
        if 'sparse' in a or a.get('normalized', False):
            raise ValueError('The pinned scene must use plain, non-normalized accessors')
        v = self.gltf['bufferViews'][a['bufferView']]
        dtype = np.dtype(TYPES[a['componentType']]); width = WIDTH[a['type']]
        return np.ndarray((a['count'], width), dtype=dtype, buffer=self.buffer,
                          offset=v.get('byteOffset', 0)+a.get('byteOffset', 0),
                          strides=(v.get('byteStride', width*dtype.itemsize), dtype.itemsize))

    def _visit(self, index, parent):
        n = self.gltf['nodes'][index]; matrix = parent @ node_matrix(n)
        if 'mesh' in n:
            self.instances.append({'node': index, 'mesh': n['mesh'], 'name': n.get('name', str(index)), 'matrix': matrix})
            for p in self.gltf['meshes'][n['mesh']]['primitives']:
                if p.get('mode', 4) != 4:
                    raise ValueError('Only triangle primitives are accepted')
                attrs = {key: self.accessor(value) for key, value in p['attributes'].items()}
                positions = attrs['POSITION'].astype(float) @ matrix[:3, :3].T + matrix[:3, 3]
                normals = attrs['NORMAL'].astype(float) @ np.linalg.inv(matrix[:3, :3])
                normals /= np.linalg.norm(normals, axis=1, keepdims=True)
                faces = self.accessor(p['indices']).ravel().astype(int).reshape(-1, 3)
                self.parts.append({'node': index, 'mesh': n['mesh'], 'name': n.get('name', str(index)),
                                   'vertices': positions @ FRAME.T, 'normals': normals @ FRAME.T,
                                   'faces': faces, 'uv0': attrs['TEXCOORD_0'].astype(float),
                                   'uv1': attrs['TEXCOORD_1'].astype(float), 'material': p['material']})
        for child in n.get('children', []):
            self._visit(child, matrix)

    def triangles(self):
        return np.concatenate([p['vertices'][p['faces']] for p in self.parts])

    def write_textures(self, folder):
        folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)
        result = []
        for material in self.gltf['materials']:
            pbr = material['pbrMetallicRoughness']; ref = pbr['baseColorTexture']
            if ref.get('texCoord', 0) != 1:
                raise ValueError('Community park colour textures must sample UV1')
            texture = self.gltf['textures'][ref['index']]
            image = self.gltf['images'][texture['source']]
            if image['mimeType'] != 'image/png':
                raise ValueError('Expected embedded PNG colour map')
            view = self.gltf['bufferViews'][image['bufferView']]
            start = view.get('byteOffset', 0); file = material['name']+'.png'
            (folder/file).write_bytes(self.buffer[start:start+view['byteLength']])
            result.append({'name': material['name'], 'file': file, 'texcoord': 1,
                           'roughness': pbr['roughnessFactor'], 'metallic': pbr['metallicFactor'],
                           'double_sided': material.get('doubleSided', False)})
        return result


def available():
    """Whether atelier fetch could get the private source; without it the island has no community park."""
    return FILE.is_file()


@lru_cache(maxsize=1)
def scene():
    spec = json.loads(SPEC.read_text())
    if not FILE.is_file():
        raise FileNotFoundError('Community park source is missing; run atelier fetch yorimichi')
    data = FILE.read_bytes()
    if hashlib.sha256(data).hexdigest() != spec['sha256']:
        raise ValueError('Community park source checksum mismatch')
    value = Scene(data)
    counts = (len(value.instances), len(value.gltf['meshes']), len(value.triangles()), len(value.gltf['materials']))
    expected = tuple(spec[k] for k in ('mesh_instances', 'unique_meshes', 'triangles', 'materials'))
    if counts != expected:
        raise ValueError(f'Community park inventory changed: {counts} != {expected}')
    return value
