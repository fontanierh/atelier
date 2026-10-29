"""Port Crater Park, the skate park on the volcano's caldera floor, into Hakuba's `craterpark` region as static scenery.

    uv run python games/yorimichi/hakuba_port/crater_park.py --build build/yorimichi

The park's build step (`world.craterpark`) already holds every drawn piece as a mesh: `craterpark/v2/geometry.npz`,
one mesh per material and grid cell, in the park's native frame (metres, y up), with per-vertex normals, UVs and baked
occlusion, and each face's material and role; it must be built from the selected design. No Blender is needed: each
cell's meshes become one painted prop, `craterpark-cell-<x>-<z>`, its corners moved onto the island as Yorimichi's
placement moves the park (`craterpark.placement.native_to_island`), and coloured as Yorimichi's park materials colour
them (`unreal/Scripts/import_craterpark.py`), in linear RGB: a restyled texture's mean, or its texel under each corner
for the shrine's models and the Prado decal, times the material's tint; a flat material's sRGB base colour; the steel
coping's colour; each darkened by the corner's baked occlusion as the park's materials' cavity term darkens the
albedo. The riding surfaces, sides and rails, the faces Yorimichi's park collides with, are each prop's collision; the
coping is drawn only. The park's own ground is the volcano's terrain, already Hakuba's ground, so it is not a prop.
"""
import argparse
import json
import math
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
from painted import PAINT, glb  # noqa: E402
from port import HAKUBA, Model, Region, write  # noqa: E402

# As `import_craterpark.py`: the steel coping's sRGB colour, the warm tints over restyled textures and how much the
# baked occlusion takes from the albedo.
STEEL = (.62, .63, .64)
TINTS = {'material_024': (1.30, 1.06, .74)}
CAVITY = .3
# Textures that are a picture on their piece rather than a tiled surface: their texel under each corner is its colour.
PICTURES = {'material_031', 'material_046', 'material_047', 'material_048', 'material_049', 'material_060'}
COLLIDES = [dsl.ROLE[role] for role in dsl.COLLISION_ROLE if role != dsl.GROUND]


def linear(c):
    c = np.asarray(c, np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


class Colours:
    """Each park material's linear colour rule: (flat colour, texture pixels or None, whether sampled per corner)."""

    def __init__(self, build):
        textures = build / 'craterpark' / 'textures'
        restyle = json.loads((textures / 'textures.json').read_text())
        self.rules = {'coping_steel': (linear(STEEL), None, False)}
        for spec in json.loads((placement.SOURCE / 'materials.json').read_text()):
            entry = (restyle['textures'].get(spec['texture']) if spec['texture'] else None) \
                or restyle.get('world_aligned', {}).get(spec['id'])
            if entry is None:
                self.rules[spec['id']] = (linear(spec['baseColor']), None, False)
                continue
            pixels = linear(np.asarray(Image.open(textures / entry['png']).convert('RGB'), np.float32) / 255.0)
            tint = linear(TINTS.get(spec['id'], (1.0, 1.0, 1.0)))
            if spec['id'] in PICTURES:
                self.rules[spec['id']] = (tint, pixels, True)
            else:
                self.rules[spec['id']] = (tint * pixels.reshape(-1, 3).mean(axis=0), None, False)

    def corners(self, material, uv, occlusion):
        """The linear RGBA of corners of one material, alpha 0 (no motion), from their UVs and baked occlusion."""
        flat, pixels, sampled = self.rules[material]
        rgb = np.broadcast_to(flat, (len(uv), 3)).copy()
        if sampled:
            h, w, _ = pixels.shape
            u, v = np.mod(uv[:, 0], 1.0), np.mod(uv[:, 1], 1.0)
            rgb *= pixels[(v * (h - 1)).astype(int), (u * (w - 1)).astype(int)]
        rgb *= (1.0 - CAVITY + CAVITY * np.clip(occlusion, 0.0, 1.0))[:, None]
        return np.hstack([np.clip(rgb, 0.0, 1.0), np.zeros((len(uv), 1))]).astype(np.float32)


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


def cell_arrays(geometry, prefixes, colours):
    """One cell's corners in map metres, their normals and colours, its drawn triangles and its collision ones."""
    turn = island(np.zeros(3))
    positions, normals, rgba, drawn, solid = [], [], [], [], []
    base = 0
    for prefix in prefixes:
        V, F = geometry[prefix + 'V'], geometry[prefix + 'F']
        material, role = geometry[prefix + 'material'], geometry[prefix + 'role']
        keep = role != dsl.ROLE[dsl.BASE]
        # Each face's material owns its corners: a corner shared by two materials is split.
        F, material, role = F[keep], material[keep], role[keep]
        corners = F.ravel()
        face_material = np.repeat(material, 3)
        positions.append(island(V[corners]))
        normals.append(island(geometry[prefix + 'N'][corners]) - turn)
        colour = np.zeros((len(corners), 4), np.float32)
        uv, occlusion = geometry[prefix + 'UV'][corners], geometry[prefix + 'AO'][corners]
        for m in np.unique(material):
            sel = face_material == m
            colour[sel] = colours.corners(dsl.MATERIALS[int(m)], uv[sel], occlusion[sel])
        rgba.append(colour)
        triangles = base + np.arange(len(corners)).reshape(-1, 3)
        drawn.append(triangles)
        solid.append(triangles[np.isin(role, COLLIDES)])
        base += len(corners)
    normal = np.concatenate(normals)
    normal /= np.maximum(np.linalg.norm(normal, axis=1, keepdims=True), 1e-12)
    return (np.concatenate(positions), normal.astype(np.float32), np.concatenate(rgba), np.concatenate(drawn),
            np.concatenate(solid))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--build', type=Path, required=True, help="Yorimichi's build folder, build/yorimichi")
    args = parser.parse_args()
    build = args.build.resolve()
    geometry = np.load(build / 'craterpark' / 'v2' / 'geometry.npz', allow_pickle=False)
    index, by_cell = cells(geometry)
    if index.get('v4', {}).get('source_sha256') != v4_config.provenance()['source_sha256']:
        raise SystemExit('the build\'s park geometry is not the selected design; rebuild world.craterpark first')
    colours = Colours(build)
    region = Region('craterpark', 'Crater Park, the concrete and wooden skate park on the caldera floor of the volcano')
    origins, triangles = {}, 0
    for (x, z), prefixes in sorted(by_cell.items()):
        name = f'craterpark-cell-{x}-{z}'.replace('--', '-m')
        position, normal, colour, drawn, solid = cell_arrays(geometry, prefixes, colours)
        used = position[np.unique(drawn)]
        low, high = used.min(axis=0), used.max(axis=0)
        origin = np.array([(low[0] + high[0]) / 2, (low[1] + high[1]) / 2, low[2] + 0.01])
        parts = [('full', {'vertex_paint': PAINT}, position - origin, normal, colour, drawn)]
        if len(solid):
            parts.append(('collision', None, position - origin, normal, None, solid))
        out = HAKUBA / 'assets' / 'props' / name / 'src' / 'model.glb'
        out.parent.mkdir(parents=True, exist_ok=True)
        glb(parts, out)
        about = "A cell of Crater Park, the skate park on the volcano's caldera floor, its colours painted per vertex."
        region.models[name] = Model(out, about=about, solid=bool(len(solid)))
        region.groups.append((name, None, [[0.0, 0.0, 0.0, 0.0, 1.0]]))
        origins[name] = (origin.tolist(), float(max(high - low)))
        triangles += len(drawn)
    write(region, origins)
    design = index.get('editor_playtest', {})
    print(f'craterpark: {len(region.models)} props, {triangles} triangles, design rev {design.get("rev")}, '
          f'source {index["v4"]["source_sha256"][:12]}')


if __name__ == '__main__':
    main()
