"""Port Yorimichi's transport into Hakuba as standing scenery: the Belmonte railway with its two trains.

    uv run python games/yorimichi/hakuba_port/transport.py --build build/yorimichi railway

Nothing moves and nothing is ridden: each vehicle stands where Yorimichi's service starts it. Each region's meshes
come from their own Yorimichi producer in plain Python and are written with `gltf.py`, painted per vertex; each
becomes a Hakuba prop under `games/hakuba/assets/props/<region>-<piece>/` and the region's placements are written
to `games/hakuba/assets/world/src/regions/<region>/placements.json`, as `port.py` writes them. A region must also be
listed once in Hakuba's `tools/export/src/world/regions.rs`.

- `railway`: the track, its tunnels' portals, viaducts, banks, buffer stops, turnouts, Belmonte's station and the
  road's overbridge, from `world/train/track.py` on the committed line (`assets/vehicles/belmonte-train/line.json`),
  and the two trains, one at each terminus, from the coach shells `world/train/build.py` wrote (`--train`, by
  default `<build>/belmonte-train`), each vehicle's outside at its middle detail. Sleepers are joined into their
  stretch of track. Pieces wholly under Hakuba's ground (inside the tunnels) and the tunnels' lamps are left out.
"""
import argparse
import json
import math
import os
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
YORIMICHI = HERE.parent
sys.path.insert(0, str(HERE))

import gltf  # noqa: E402
from contact import POINTS, ground_at, mosaic  # noqa: E402
from ground import settings  # noqa: E402
from port import HAKUBA, Model, Region, write  # noqa: E402


class Ground:
    """Hakuba's ground heights, to leave out what lies wholly under it."""

    def __init__(self):
        world = settings()
        self.heights = mosaic(world)
        self.south_west, self.step = np.array(world['south_west_m']), world['ground_step_m']

    def shows(self, points):
        """Whether any of `POINTS` map points, spread from low to high, is above the ground or off it, as
        `contact.py` checks a copy's body."""
        points = np.asarray(points, float)
        body = points[np.argsort(points[:, 2])[np.linspace(0, len(points) - 1, min(len(points), POINTS)).astype(int)]]
        under = ground_at(self.heights, self.south_west, self.step, body[:, 0], body[:, 1])
        return bool((~(body[:, 2] < under)).any())


def painted(meshes, colours):
    """Corner arrays of one or more `track.Mesh`es (map frame, relative to their origin): each polygon split into a fan
    of triangles with its face's normal, coloured by its material from `colours` (polygons of other materials are
    left out)."""
    position, normal, colour = [], [], []
    for mesh in meshes:
        verts = np.asarray(mesh.verts, float)
        for face, mat in zip(mesh.faces, mesh.mats):
            if mat not in colours:
                continue
            ring = verts[list(face)]
            n = np.cross(ring - ring.mean(axis=0), np.roll(ring, -1, axis=0) - ring.mean(axis=0)).sum(axis=0)
            length = np.linalg.norm(n)
            if length < 1e-12:
                continue
            for k in range(1, len(face) - 1):
                position += [ring[0], ring[k], ring[k + 1]]
            count = 3 * (len(face) - 2)
            normal += [n / length] * count
            colour += [colours[mat]] * count
    position = np.array(position)
    return position, np.array(normal), np.array(colour), np.arange(len(position)).reshape(-1, 3)


def moved(mesh, x, y, z, yaw, across=1.0):
    """A copy of `track.Mesh` `mesh` scaled `across` along its local y, turned `yaw` degrees and moved to (x, y, z)."""
    from train import track
    c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    out = track.Mesh()
    out.verts = [(x + c * vx - s * vy * across, y + s * vx + c * vy * across, z + vz) for vx, vy, vz in mesh.verts]
    # A mirror (a negative scale) reverses each polygon so that it still faces out.
    out.faces = [tuple(f) if across > 0 else tuple(reversed(f)) for f in mesh.faces]
    out.mats = list(mesh.mats)
    return out


def shell_colours(doc, images):
    """Each coach material's linear colour: its base colour times its texture's mean. Glass is painted dark, as the
    trains' far shells draw their windows; other see-through materials (the crest decal) are left out."""
    colours = {}
    for k, material in enumerate(doc.get('materials', [])):
        pbr = material.get('pbrMetallicRoughness', {})
        if material.get('alphaMode') == 'BLEND':
            if 'Glass' in material.get('name', ''):
                colours[k] = np.array([0.02, 0.024, 0.03])
            continue
        colour = np.array(pbr.get('baseColorFactor', [1.0, 1.0, 1.0, 1.0])[:3], float)
        if 'baseColorTexture' in pbr:
            source = doc['textures'][pbr['baseColorTexture']['index']]['source']
            colour = colour * gltf.image_mean(images[source])
        colours[k] = np.clip(colour, 0.0, 1.0)
    return colours


def shell(path):
    """A coach shell GLB's corners, painted by `shell_colours`, in its own frame (x along the train, z up from the
    rail top)."""
    doc, images, parts = gltf.read(path)
    colours = shell_colours(doc, images)
    position, normal, colour = [], [], []
    for corners, normals, _, materials in parts:
        keep = np.array([m in colours for m in materials], bool)
        position.append(corners[keep].reshape(-1, 3))
        normal.append(normals[keep].reshape(-1, 3))
        colour.append(np.repeat([colours[m] for m in materials[keep]], 3, axis=0).reshape(-1, 3))
    position = np.concatenate(position)
    return position, np.concatenate(normal), np.concatenate(colour), np.arange(len(position)).reshape(-1, 3)


def railway(build, shells):
    """The Belmonte railway: every track, structure and station piece where `track.layout` puts it on the committed
    line, and the two trains standing at the termini."""
    # The banks meet Yorimichi's own ground, which its world module reads from the build.
    os.environ['ATELIER_BUILD_ROOT'] = str(build.parent)
    sys.path.insert(0, str(YORIMICHI / 'world'))
    from train import consist, route, track
    line_json = json.loads((YORIMICHI / 'assets' / 'vehicles' / 'belmonte-train' / 'line.json').read_text())
    alignment = route.alignment()
    samples = line_json['samples']
    rail, ground_z, kind = (np.array([p[key] for p in samples]) for key in ('rail_z', 'ground_z', 'class'))
    # route.json's structures and spirals, from the committed line's samples by route.py's own functions.
    structures = [dict(row, kind=str(row['kind']), name=str(row['name']))
                  for row in route.structures(alignment, rail, ground_z, kind)]
    spirals = [dict(start=float(sp['start']), end=float(sp['end'])) for sp in alignment.spirals]
    line = track.Line(dict(frame=line_json['frame'], samples=samples, passing_loop=line_json['passing_loop'],
                           summary=dict(structures=structures, spirals=spirals)))
    meshes, doc = track.layout(line)
    colours = {name: np.array(rgba[:3]) for name, rgba in track.MATERIALS.items() if name != 'MI_TK_Marker'}
    ground = Ground()
    region = Region('railway', 'the Belmonte railway between Hidamari and Belmonte')
    built, left_out = {}, []

    def add(name, about, parts, instances, solid=True):
        built[name] = (parts, about, solid, instances)

    # Track, each stretch with its sleepers; the loop's own rails; tunnel linings, banks, viaducts and the station.
    sleepers = doc['instances']['SM_TK_Sleeper']
    pieces = [(row, 'a hundred-metre stretch of track, with its sleepers') for row in doc['chunks']]
    pieces += [(row, "a stretch of a tunnel's lining") for tunnel in doc['tunnels'] for row in tunnel['lining']]
    pieces += [(row, 'a bank the track runs on') for row in doc['banks']]
    pieces += [(row, "a stretch of a viaduct's arches") for viaduct in doc['viaducts'] for row in viaduct['pieces']]
    pieces += [(row, "a piece of Belmonte's station") for row in doc['station']['pieces']]
    if doc.get('overbridge'):
        pieces.append((doc['overbridge'], "the road's stone bridge over the last cutting"))
    for row, about in pieces:
        parts = [meshes[row['name']][0]]
        ox, oy, oz = row['origin']
        if row['name'].startswith('SM_TK_Chunk_'):
            index = str(int(row['name'].rsplit('_', 1)[1]))
            parts += [moved(meshes['SM_TK_Sleeper'][0], x - ox, y - oy, z - oz, yaw, scale)
                      for x, y, z, yaw, scale in sleepers.get(index, [])]
        points = np.concatenate([np.asarray(m.verts, float) for m in parts]) + (ox, oy, oz)
        if not ground.shows(points):
            left_out.append(row['name'])
            continue
        add(row['name'], about, parts, [[ox, oy, oz, 0.0, 1.0]])
    # Instanced fittings; a mirrored turnout becomes its own piece.
    for name, about in (('SM_TK_Portal', "a tunnel's stone portal"), ('SM_TK_BufferStop', 'a buffer stop'),
                        ('SM_TK_StopBoard', 'a stop board')):
        add(name, about, [meshes[name][0]], [[x, y, z, yaw, 1.0] for x, y, z, yaw, _ in doc['instances'][name]])
    for k, (x, y, z, yaw, mirror) in enumerate(doc['instances']['SM_TK_Turnout']):
        add(f'SM_TK_Turnout_{k}', "a turnout at an end of the passing loop",
            [moved(meshes['SM_TK_Turnout'][0], 0.0, 0.0, 0.0, yaw, mirror)], [[x, y, z, 0.0, 1.0]])
    origins = {}
    for name, (parts, about, solid, instances) in built.items():
        prop = 'railway-' + name.removeprefix('SM_TK_').removeprefix('SM_ST_').lower().replace('_', '-')
        out = HAKUBA / 'assets' / 'props' / prop / 'src' / 'model.glb'
        out.parent.mkdir(parents=True, exist_ok=True)
        origins[prop] = gltf.prop(*painted(parts, colours), out)
        region.models[prop] = Model(None, solid=solid, about=f'{about[0].upper() + about[1:]}, on the Belmonte '
                                    'railway, painted per vertex.')
        region.groups.append((prop, None, instances))

    # The trains: train A waits at Hidamari, train B at Belmonte, each with its centre half a train from the stop at
    # the end of the line and its locomotive towards Belmonte, as Yorimichi's service starts them.
    offsets = consist.offsets()
    front, back = 0.0, -sum(v['length'] for v in consist.VEHICLES)
    half = (front - back) / 2
    centres = [track.STOP_OFFSET + half, line.length - track.STOP_OFFSET - half]
    for vehicle in consist.VEHICLES:
        title = ''.join(p.title() for p in vehicle['id'].split('-'))
        prop = 'railway-' + vehicle['id']
        out = HAKUBA / 'assets' / 'props' / prop / 'src' / 'model.glb'
        out.parent.mkdir(parents=True, exist_ok=True)
        origins[prop] = gltf.prop(*shell(shells / vehicle['id'] / f'SM_BT_{title}_Exterior_LOD1.glb'), out)
        region.models[prop] = Model(None, about=f"The Belmonte train's {vehicle['title'].lower()}, from outside, "
                                    'standing at a terminus, painted per vertex.')
        instances = []
        for centre in centres:
            s = centre + offsets[vehicle['id']] + half
            (x, y, z), _, _ = line.frame(s)
            instances.append([float(x), float(y), float(z), math.degrees(line.heading(s)), 1.0])
        region.groups.append((prop, None, instances))
    print(f'railway: {len(left_out)} pieces under the ground left out:', ', '.join(left_out))
    return region, origins


ADAPTERS = {'railway': railway}


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--build', type=Path, required=True, help="Yorimichi's build folder, build/yorimichi")
    parser.add_argument('--train', type=Path, help="the train's coach shells, by default <build>/belmonte-train")
    parser.add_argument('region', nargs='+', choices=sorted(ADAPTERS))
    args = parser.parse_args()
    build = args.build.resolve()
    for name in args.region:
        region, origins = railway(build, (args.train or build / 'belmonte-train').resolve())
        write(region, origins)
        count = sum(len(i) for _, _, i in region.groups)
        print(f'{region.name}: {len(region.models)} props, {count} placements')


if __name__ == '__main__':
    main()
