"""Port Crater Park, the skate park on the volcano's caldera floor, into Hakuba's `craterpark` region as static scenery.

    uv run python games/yorimichi/hakuba_port/crater_park.py --build build/yorimichi

The park's build step (`world.craterpark`) already holds every drawn piece as a mesh: `craterpark/v2/geometry.npz`,
one mesh per material and grid cell, in the park's native frame (metres, y up), with per-vertex normals, UVs and baked
occlusion, and each face's material and role; it must be built from the selected design. No Blender is needed: each
cell's meshes become one prop, `craterpark-cell-<x>-<z>`, its corners moved onto the island as Yorimichi's placement
moves the park (`craterpark.placement.native_to_island`), with one primitive per material drawn as Yorimichi's park
materials draw it (`unreal/Scripts/import_craterpark.py`): a restyled texture on the mesh's own UVs, or world-aligned
every `metres` on the face's most facing axis, times the material's tint; a flat material's sRGB base colour; the
steel coping's colour. Each restyled texture becomes a texture asset, `craterpark-<name>`. Each corner's colour is the
park materials' cavity term, which darkens the albedo by the baked occlusion. Hakuba draws every surface matte, so the
lacquer's and the steel's sheen are not kept. The riding surfaces, sides and rails, the faces Yorimichi's park collides
with, are each prop's collision; the coping is drawn only. The park's own ground is the volcano's terrain, already
Hakuba's ground, so it is not a prop.
"""
import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
YORIMICHI = HERE.parent
sys.path[:0] = [str(YORIMICHI / 'world' / 'regions'), str(YORIMICHI / 'world'), str(HERE)]

from craterpark import placement  # noqa: E402
from craterpark.v2 import dsl, v4_config  # noqa: E402
from painted import SURFACE, glb  # noqa: E402
from port import HAKUBA, Model, Region, sha256, write, write_texture  # noqa: E402

# As `import_craterpark.py`: the steel coping's sRGB colour, the warm tints over restyled textures and how much the
# baked occlusion takes from the albedo.
STEEL = (.62, .63, .64)
TINTS = {'material_024': (1.30, 1.06, .74)}
CAVITY = .3
COLLIDES = [dsl.ROLE[role] for role in dsl.COLLISION_ROLE if role != dsl.GROUND]


def linear(c):
    c = np.asarray(c, np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


class Materials:
    """Each park material as Hakuba draws it, by its id: {'name', 'colour' (linear), 'texture' (an asset name or None),
    'two_sided', 'metres' (a world-aligned texture's repeat, or None)}; and each texture asset's restyled entry."""

    def __init__(self, build):
        self.folder = build / 'craterpark' / 'textures'
        restyle = json.loads((self.folder / 'textures.json').read_text())
        self.specs = {'coping_steel': {'name': 'coping steel', 'colour': linear(STEEL), 'texture': None,
                                       'two_sided': False, 'metres': None}}
        self.textures = {}
        for spec in json.loads((placement.SOURCE / 'materials.json').read_text()):
            painted = restyle['textures'].get(spec['texture']) if spec['texture'] else None
            aligned = restyle.get('world_aligned', {}).get(spec['id'])
            entry = painted or aligned
            metal = spec.get('finish') == 'metal'
            texture = None
            if entry and not metal:
                texture = 'craterpark-' + Path(entry['png']).stem.replace('_', '-')
                self.textures[texture] = entry
            colour = TINTS.get(spec['id'], (1.0, 1.0, 1.0)) if entry else spec['baseColor']
            self.specs[spec['id']] = {'name': spec['id'], 'colour': linear(colour[:3]), 'texture': texture,
                                      'two_sided': bool(spec['doubleSided']),
                                      'metres': float(aligned['metres']) if aligned and not painted else None}

    def write_textures(self):
        """Each restyled texture as a texture asset."""
        for name, entry in self.textures.items():
            source = self.folder / entry['png']
            assert sha256(source) == entry['sha256'], entry['png']
            write_texture(name, source, f'Crater Park\'s restyled {entry["slug"].replace("_", " ")} texture: '
                          f'{entry["how"]}.')

    def corners(self, material, uv, position, normal, occlusion):
        """Corners of one material: their texture positions and linear RGBA, the cavity's darkening, alpha 1."""
        spec = self.specs[material]
        if spec['metres']:
            # World-aligned on the axis the face looks along most, image rows running down.
            axis = np.abs(normal).argmax(axis=1)
            u = np.where(axis == 0, position[:, 1], position[:, 0])
            v = np.where(axis == 2, -position[:, 1], -position[:, 2])
            uv = np.stack([u, v], axis=1) / spec['metres']
        shade = 1.0 - CAVITY + CAVITY * linear(np.clip(occlusion, 0.0, 1.0))
        return uv.astype(np.float32), np.hstack([np.repeat(shade[:, None], 3, axis=1),
                                                 np.ones((len(uv), 1))]).astype(np.float32)


def island(native):
    """Native (x, y up, z) points or directions -> island map metres, x east, y north, z up."""
    return placement.native_to_island(native)


def cells(geometry):
    """The render meshes by cell: {(x, z): [mesh prefix, ...]}, from the names `SM_CP_<role>_<material>_<x>_<z>`."""
    index = json.loads(str(geometry['index']))
    by_cell = {}
    for i, spec in enumerate(index['render']):
        x, z = re.fullmatch(r'SM_CP_\w+?_(-?\d+)_(-?\d+)', spec['name']).groups()
        by_cell.setdefault((int(x), int(z)), []).append(f'r{i}_')
    return index, by_cell


def cell_arrays(geometry, prefixes, materials):
    """One cell's corners in map metres, their normals, colours and texture positions, its drawn triangles, each
    triangle's material id and its collision triangles."""
    turn = island(np.zeros(3))
    positions, normals, rgba, uvs, drawn, face_materials, solid = [], [], [], [], [], [], []
    base = 0
    for prefix in prefixes:
        V, F = geometry[prefix + 'V'], geometry[prefix + 'F']
        material, role = geometry[prefix + 'material'], geometry[prefix + 'role']
        keep = role != dsl.ROLE[dsl.BASE]
        # Each face's material owns its corners: a corner shared by two materials is split.
        F, material, role = F[keep], material[keep], role[keep]
        corners = F.ravel()
        face_material = np.repeat(material, 3)
        position = island(V[corners])
        positions.append(position)
        normals.append(island(geometry[prefix + 'N'][corners]) - turn)
        a, b, c = position[0::3], position[1::3], position[2::3]
        facing = np.repeat(np.cross(b - a, c - a), 3, axis=0)
        colour = np.zeros((len(corners), 4), np.float32)
        uv = geometry[prefix + 'UV'][corners].astype(np.float64)
        occlusion = geometry[prefix + 'AO'][corners]
        for m in np.unique(material):
            sel = face_material == m
            uv[sel], colour[sel] = materials.corners(dsl.MATERIALS[int(m)], uv[sel], position[sel], facing[sel],
                                                     occlusion[sel])
        rgba.append(colour)
        uvs.append(uv.astype(np.float32))
        triangles = base + np.arange(len(corners)).reshape(-1, 3)
        drawn.append(triangles)
        face_materials.append([dsl.MATERIALS[int(m)] for m in material])
        solid.append(triangles[np.isin(role, COLLIDES)])
        base += len(corners)
    normal = np.concatenate(normals)
    normal /= np.maximum(np.linalg.norm(normal, axis=1, keepdims=True), 1e-12)
    return (np.concatenate(positions), normal.astype(np.float32), np.concatenate(rgba), np.concatenate(uvs),
            np.concatenate(drawn), np.concatenate(face_materials), np.concatenate(solid))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--build', type=Path, required=True, help="Yorimichi's build folder, build/yorimichi")
    args = parser.parse_args()
    build = args.build.resolve()
    geometry = np.load(build / 'craterpark' / 'v2' / 'geometry.npz', allow_pickle=False)
    index, by_cell = cells(geometry)
    if index.get('v4', {}).get('source_sha256') != v4_config.provenance()['source_sha256']:
        raise SystemExit('the build\'s park geometry is not the selected design; rebuild world.craterpark first')
    materials = Materials(build)
    materials.write_textures()
    region = Region('craterpark', 'Crater Park, the concrete and wooden skate park on the caldera floor of the volcano')
    origins, triangles = {}, 0
    for (x, z), prefixes in sorted(by_cell.items()):
        name = f'craterpark-cell-{x}-{z}'.replace('--', '-m')
        position, normal, colour, uv, drawn, face_material, solid = cell_arrays(geometry, prefixes, materials)
        used = position[np.unique(drawn)]
        low, high = used.min(axis=0), used.max(axis=0)
        origin = np.array([(low[0] + high[0]) / 2, (low[1] + high[1]) / 2, low[2] + 0.01])
        ids, local = np.unique(face_material, return_inverse=True)
        specs = [materials.specs[i] for i in ids]
        parts = [('full', SURFACE, position - origin, normal, colour, drawn, uv, local)]
        if len(solid):
            parts.append(('collision', None, position - origin, normal, None, solid))
        out = HAKUBA / 'assets' / 'props' / name / 'src' / 'model.glb'
        out.parent.mkdir(parents=True, exist_ok=True)
        glb(parts, out, specs)
        about = "A cell of Crater Park, the skate park on the volcano's caldera floor, with its own textures."
        textures = sorted({spec['texture'] for spec in specs if spec['texture']})
        region.models[name] = Model(out, about=about, solid=bool(len(solid)), textures=textures)
        region.groups.append((name, None, [[0.0, 0.0, 0.0, 0.0, 1.0]]))
        origins[name] = (origin.tolist(), float(max(high - low)))
        triangles += len(drawn)
    write(region, origins)
    design = index.get('editor_playtest', {})
    print(f'craterpark: {len(region.models)} props, {triangles} triangles, design rev {design.get("rev")}, '
          f'source {index["v4"]["source_sha256"][:12]}')


if __name__ == '__main__':
    main()
