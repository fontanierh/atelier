"""Port Yorimichi's transport into Hakuba as standing scenery: the Belmonte railway with its two trains.

    uv run python games/yorimichi/hakuba_port/transport.py --build build/yorimichi railway

Nothing moves and nothing is ridden: each vehicle stands where Yorimichi's service starts it. Each region's meshes
come from their own Yorimichi producer in plain Python and are written with `painted.py`, drawn with the textures
Yorimichi's materials draw on them (each a Hakuba texture asset) times a colour per vertex; each becomes a Hakuba
prop under `games/hakuba/assets/props/<region>-<piece>/` and the region's placements are written to
`games/hakuba/assets/world/src/regions/<region>/placements.json`, as `port.py` writes them. A region must also be
listed once in Hakuba's `tools/export/src/world/regions.rs`.

- `railway`: the track, its tunnels' portals, viaducts, banks, buffer stops, turnouts, Belmonte's station and the
  road's overbridge, from `world/train/track.py` on the committed line (`assets/vehicles/belmonte-train/line.json`),
  and the two trains, one at each terminus, from the coach shells `world/train/build.py` wrote (`--train`, by
  default `<build>/belmonte-train`), each vehicle's outside at its full detail. Sleepers are joined into their
  stretch of track. Pieces wholly under Hakuba's ground (inside the tunnels) and the tunnels' lamps are left out.
  A track piece's Belmonte materials (`MI_B_*`, ballast, stone, timber, ...) are Belmonte's own, as Unreal binds them
  (`import_belmonte_track.py`): Belmonte's detail texture on the piece's planar UVs in metres over the material's tile,
  times its colour, tint and brightness and the detail's gain of 2 (`import_belmonte.py`'s `M_Belmonte`), drawn with
  the `belmonte-*` texture assets the Belmonte port names. The track's own materials (`MI_TK_*`, `MI_ST_*`) and the
  Belmonte ones without a texture keep their flat `track.MATERIALS` colour, as Unreal draws them. The coaches draw
  their own images (`railway-*` texture assets) times their base colour; glass is painted dark and the see-through
  crest decal is left out.
"""
import argparse
import json
import math
import os
import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
# A smooth non-metal's reflectance, glTF's default specular.
SHEEN = 0.04
YORIMICHI = HERE.parent
sys.path.insert(0, str(HERE))

import painted as glb  # noqa: E402
from contact import POINTS, ground_at, mosaic  # noqa: E402
from ground import settings  # noqa: E402
from port import HAKUBA, Model, Region, describe, kebab, settle_textures, write, write_texture  # noqa: E402


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


def fill(points):
    """Triangles (index triples) filling the simple polygon whose corners, in order, are the 2D `points`, each wound
    as the polygon: a fan when it is convex, else ear clipping, so a concave outline (a portal's wall around its arch)
    keeps its opening."""
    q = np.asarray(points, float) - np.mean(points, axis=0)
    count = len(q)
    area = 0.5 * np.sum(q[:, 0] * np.roll(q[:, 1], -1) - np.roll(q[:, 0], -1) * q[:, 1])
    order = list(range(count)) if area > 0 else list(range(count))[::-1]
    eps = 1e-9 * max(float(np.ptp(q, axis=0).max()), 1e-6) ** 2

    def turn(i, j, k):
        return (q[j, 0] - q[i, 0]) * (q[k, 1] - q[i, 1]) - (q[j, 1] - q[i, 1]) * (q[k, 0] - q[i, 0])

    if all(turn(order[k - 1], order[k], order[(k + 1) % count]) >= -eps for k in range(count)):
        return [(0, k, k + 1) for k in range(1, count - 1)]
    out = []
    while len(order) > 3:
        for k in range(len(order)):
            i, j, l = order[k - 1], order[k], order[(k + 1) % len(order)]
            if turn(i, j, l) <= eps:
                continue
            ear = q[[i, j, l]]
            if any(min(turn(i, j, p), turn(j, l, p), turn(l, i, p)) >= -eps
                   and not np.any(np.all(np.abs(ear - q[p]) <= 1e-9, axis=1)) for p in order if p not in (i, j, l)):
                continue
            out.append((i, j, l))
            del order[k]
            break
        else:
            raise ValueError('fill: no ear, the polygon is not simple')
    if abs(turn(*order)) > eps:
        out.append(tuple(order))
    return out if area > 0 else [(i, l, j) for i, j, l in out]


def track_corners(meshes, looks):
    """Corner arrays of one or more `track.Mesh`es (map frame, relative to their origin): each polygon filled with
    triangles (`fill`) with its face's normal, its material's colour and its planar UVs in metres along the face's
    dominant axis (as `track_build.py` writes them) over that material's tile, and each triangle's index into `looks`,
    a list of (material name, linear colour, Hakuba texture or None, tile in metres). Polygons of other materials are
    left out."""
    index = {look[0]: k for k, look in enumerate(looks)}
    position, normal, colour, uv, face = [], [], [], [], []
    for mesh in meshes:
        verts = np.asarray(mesh.verts, float)
        for poly, mat in zip(mesh.faces, mesh.mats):
            if mat not in index:
                continue
            _, rgb, _, tile = looks[index[mat]]
            ring = verts[list(poly)]
            n = np.cross(ring - ring.mean(axis=0), np.roll(ring, -1, axis=0) - ring.mean(axis=0)).sum(axis=0)
            length = np.linalg.norm(n)
            if length < 1e-12:
                continue
            a, b = [k for k in range(3) if k != int(np.argmax(np.abs(n)))]
            triangles = fill(ring[:, [a, b]])
            for corners in triangles:
                for v in ring[list(corners)]:
                    position.append(v)
                    # Blender's V runs up the image, glTF's down it.
                    uv.append((v[a] / tile, (1.0 - v[b]) / tile))
            count = 3 * len(triangles)
            normal += [n / length] * count
            colour += [rgb] * count
            face += [index[mat]] * (count // 3)
    position = np.array(position)
    return (position, np.array(normal), np.array(colour), np.arange(len(position)).reshape(-1, 3), np.array(uv),
            np.array(face))


def track_looks(build):
    """Each track material's look, (name, linear colour, Hakuba texture or None, tile in metres): Belmonte's own for
    its textured `MI_B_*` materials, writing their texture assets where the Belmonte port has not, and the flat
    `track.MATERIALS` colour for the rest. The marker is editor-only and left out."""
    from train import track
    report = json.loads((build / 'belmonte' / 'build-report.json').read_text())['materials']
    belmonte = {key.rsplit('/', 1)[-1].split('.')[0]: entry for key, entry in report.items()}
    looks = []
    for name, rgba in track.MATERIALS.items():
        if name == 'MI_TK_Marker':
            continue
        entry = belmonte.get(name) if name.startswith('MI_B_') else None
        if entry and entry['texture'] and not entry['atlas']:
            image = build / 'belmonte' / 'textures' / entry['texture']
            texture = f'belmonte-{kebab(image.stem)}'
            if not (HAKUBA / 'assets' / 'textures' / texture).exists():
                write_texture(texture, image, describe(texture, 'belmonte'))
            rgb = [2.0 * c * t * entry['brightness'] for c, t in zip(entry['colour'][:3], entry['tint'][:3])]
            looks.append((name, rgb, texture, entry['tile_m']))
        else:
            looks.append((name, list(rgba[:3]), None, 1.0))
    return looks


def track_prop(parts, looks, output):
    """Write the track piece made of `track.Mesh`es `parts` as a prop, textured if any of its materials is; returns its
    origin and size, and the textures it draws."""
    position, normal, colour, triangles, uv, face = track_corners(parts, looks)
    used = np.unique(face)
    textures = sorted({looks[k][2] for k in used if looks[k][2]})
    if not textures:
        return (*glb.prop(position, normal, colour, triangles, output), [])
    materials = [{'name': looks[k][0], 'colour': [1.0, 1.0, 1.0], 'texture': looks[k][2], 'two_sided': False}
                 for k in used]
    return (*glb.prop(position, normal, colour, triangles, output, (uv, np.searchsorted(used, face), materials)),
            textures)


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


def shell(path, scratch):
    """A coach shell GLB's corners in its own frame (x along the train, z up from the rail top), each coloured by its
    material's base colour, with its UVs and each triangle's material, and the materials `painted.glb` draws: each
    image the shell's materials draw becomes the texture asset `railway-<image>`, written from `scratch`. Glass is
    painted dark, as the trains' far shells draw their windows; other see-through materials (the crest decal) are left
    out. Hakuba draws every surface matte, so an untextured paint's sheen, the 4 % a non-metal reflects, less the
    rougher it is, is folded into its colour: the glossy black engine reads as black paint, not a void."""
    doc, images, parts = glb.read(path)
    materials, chosen = [], {}
    for k, material in enumerate(doc.get('materials', [])):
        pbr = material.get('pbrMetallicRoughness', {})
        colour = np.clip(pbr.get('baseColorFactor', [1.0, 1.0, 1.0, 1.0])[:3], 0.0, 1.0)
        texture = None
        if material.get('alphaMode') == 'BLEND':
            if 'Glass' not in material.get('name', ''):
                continue
            colour = np.array([0.02, 0.024, 0.03])
        elif 'baseColorTexture' not in pbr:
            if pbr.get('metallicFactor', 1.0) < 0.5:
                colour = colour + SHEEN * (1.0 - pbr.get('roughnessFactor', 1.0))
        else:
            source = doc['textures'][pbr['baseColorTexture']['index']]['source']
            image = doc['images'][source]['name']
            texture = 'railway-' + kebab(image.removeprefix('T_BT_'))
            if not (scratch / texture).exists():
                (scratch / texture).write_bytes(images[source])
                write_texture(texture, scratch / texture, "The Belmonte train's "
                              f"{texture.removeprefix('railway-').replace('-', ' ')} texture.")
        chosen[k] = (len(materials), colour)
        materials.append({'name': material['name'], 'colour': [1.0, 1.0, 1.0], 'texture': texture,
                          'two_sided': bool(material.get('doubleSided'))})
    position, normal, colour, uv, face = [], [], [], [], []
    for corners, normals, uvs, kinds in parts:
        keep = np.array([m in chosen for m in kinds], bool)
        position.append(corners[keep].reshape(-1, 3))
        normal.append(normals[keep].reshape(-1, 3))
        uv.append(uvs[keep].reshape(-1, 2))
        face.append(np.array([chosen[m][0] for m in kinds[keep]], int))
        colour.append(np.repeat([chosen[m][1] for m in kinds[keep]], 3, axis=0).reshape(-1, 3))
    position, face = np.concatenate(position), np.concatenate(face)
    used = np.unique(face)
    materials = [materials[k] for k in used]
    textured = (np.concatenate(uv), np.searchsorted(used, face), materials)
    return (position, np.concatenate(normal), np.concatenate(colour), np.arange(len(position)).reshape(-1, 3),
            textured, sorted({m['texture'] for m in materials if m['texture']}))


def railway(build, shells, scratch):
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
    looks = track_looks(build)
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
        *origins[prop], textures = track_prop(parts, looks, out)
        region.models[prop] = Model(None, solid=solid, textures=textures, about=f'{about[0].upper() + about[1:]}, '
                                    'on the Belmonte railway' + (', drawn with its textures.' if textures else
                                                                 ', painted per vertex.'))
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
        *corners, textured, textures = shell(shells / vehicle['id'] / f'SM_BT_{title}_Exterior_LOD0.glb', scratch)
        origins[prop] = glb.prop(*corners, out, textured)
        region.models[prop] = Model(None, textures=textures, about=f"The Belmonte train's "
                                    f"{vehicle['title'].lower()}, from outside, standing at a terminus, drawn with "
                                    'its textures.')
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
        with tempfile.TemporaryDirectory() as scratch:
            region, origins = railway(build, (args.train or build / 'belmonte-train').resolve(), Path(scratch))
        write(region, origins)
        count = sum(len(i) for _, _, i in region.groups)
        print(f'{region.name}: {len(region.models)} props, {count} placements')
    settle_textures(args.region)


if __name__ == '__main__':
    main()
