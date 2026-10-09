"""Build the Hidamari Hippodrome (layout.py, docs/HIPPODROME.md) for the Unreal import: no Blender needed.

Writes build/yorimichi/hippodrome/region/:
- glb/SM_HD_<Part>.glb: the course's own meshes, in metres round the platform's centre (ORIGIN at PLATFORM_Z): the
  grass platform, its skirt down to the terraced ground, the dirt track, the lane from the city street, and the white
  rails with their posts. Each is one material slot named after its surface (HD_Grass, HD_Dirt, HD_Stone, HD_Rail).
- glb/SM_HD_<Structure>.glb: the Tripo structures (assets/hippodrome/props), scaled to their sizes with their bases
  at z = 0, front still on +X.
- textures/*.png: the tiling grass and dirt colour maps.
- hippodrome.json: what the game reads (Content/Data/hippodrome/hippodrome.json once imported): the origin, every mesh
  with its placement and whether it blocks, the course geometry the race runs on, where the race master and the
  starting gate stand, and the island's clearance polygons (JapanWorld removes trees and grass inside them).

The meshes are written in glTF's axes as Blender exports them: (x, z, -y) for Blender (x, y, z).
"""
import hashlib, json, math, struct, sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))              # games/yorimichi/world
import yori   # noqa: E402
from hippodrome import layout as L   # noqa: E402
from hidamari import layout as H   # noqa: E402

OUT = yori.OUT / 'hippodrome' / 'region'
PROPS = yori.ASSETS / 'hippodrome' / 'props'
UV_METRES = 4.          # one texture repeat per 4 m


# ------------------------------------------------------------------ glTF
def write_glb(path, positions, normals, uvs, indices, material):
    """One static mesh with one material slot; positions and normals in Blender axes (metres)."""
    p = np.asarray(positions, np.float32); n = np.asarray(normals, np.float32); t = np.asarray(uvs, np.float32)
    i = np.asarray(indices, np.uint32).reshape(-1)
    gl = lambda v: np.stack([v[:, 0], v[:, 2], -v[:, 1]], 1).astype(np.float32)
    p, n = gl(p), gl(n)
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
    chunks, views, accessors = bytearray(), [], []

    def add(array, kind, ctype, target, minmax=False):
        chunks.extend(b'\x00' * (-len(chunks) % 4))
        views.append({'buffer': 0, 'byteOffset': len(chunks), 'byteLength': array.nbytes, 'target': target})
        chunks.extend(array.tobytes())
        acc = {'bufferView': len(views) - 1, 'componentType': ctype, 'count': len(array), 'type': kind}
        if minmax:
            acc['min'] = [float(v) for v in array.min(0)]; acc['max'] = [float(v) for v in array.max(0)]
        accessors.append(acc)
        return len(accessors) - 1

    attributes = {'POSITION': add(p, 'VEC3', 5126, 34962, True), 'NORMAL': add(n, 'VEC3', 5126, 34962),
                  'TEXCOORD_0': add(t, 'VEC2', 5126, 34962)}
    index = add(i, 'SCALAR', 5125, 34963)
    gltf = {'asset': {'version': '2.0', 'generator': 'yorimichi hippodrome'}, 'scene': 0,
            'scenes': [{'nodes': [0]}], 'nodes': [{'name': path.stem, 'mesh': 0}],
            'meshes': [{'name': path.stem, 'primitives': [{'attributes': attributes, 'indices': index, 'material': 0}]}],
            'materials': [{'name': material, 'pbrMetallicRoughness': {'baseColorFactor': [.8, .8, .8, 1.],
                                                                       'metallicFactor': 0., 'roughnessFactor': .9}}],
            'buffers': [{'byteLength': len(chunks)}], 'bufferViews': views, 'accessors': accessors}
    _save(path, gltf, chunks)
    return {'triangles': len(i) // 3, 'min': [float(v) for v in np.asarray(positions).min(0)],
            'max': [float(v) for v in np.asarray(positions).max(0)], 'material': material}


def _save(path, gltf, binary):
    binary = bytes(binary) + b'\x00' * (-len(binary) % 4)
    gltf['buffers'] = [{'byteLength': len(binary)}]
    text = json.dumps(gltf, separators=(',', ':')).encode()
    text += b' ' * (-len(text) % 4)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(struct.pack('<III', 0x46546C67, 2, 12 + 8 + len(text) + 8 + len(binary)) +
                     struct.pack('<II', len(text), 0x4E4F534A) + text + struct.pack('<II', len(binary), 0x004E4942) + binary)


def _read(path):
    data = path.read_bytes()
    length = struct.unpack_from('<I', data, 12)[0]
    gltf = json.loads(data[20:20 + length])
    return gltf, bytearray(data[20 + length + 8:])


# ------------------------------------------------------------------ geometry
class Mesh:
    def __init__(self):
        self.p, self.n, self.t, self.i = [], [], [], []

    def quad(self, a, b, c, d, uv=None, normal=None):
        """Quad a-b-c-d counter-clockwise seen from its front."""
        a, b, c, d = (np.asarray(v, float) for v in (a, b, c, d))
        nrm = np.cross(b - a, d - a) if normal is None else np.asarray(normal, float)
        nrm = nrm / max(np.linalg.norm(nrm), 1e-9)
        base = len(self.p)
        self.p += [a, b, c, d]; self.n += [nrm] * 4
        self.t += uv or [(a[0] / UV_METRES, a[1] / UV_METRES), (b[0] / UV_METRES, b[1] / UV_METRES),
                         (c[0] / UV_METRES, c[1] / UV_METRES), (d[0] / UV_METRES, d[1] / UV_METRES)]
        self.i += [base, base + 1, base + 2, base, base + 2, base + 3]

    def box(self, centre, half, yaw=0.):
        """An axis box turned by `yaw` (radians) about z."""
        c, s = math.cos(yaw), math.sin(yaw)
        corner = lambda x, y, z: (centre[0] + x * c - y * s, centre[1] + x * s + y * c, centre[2] + z)
        hx, hy, hz = half
        v = {k: corner(*k) for k in [(sx * hx, sy * hy, sz * hz) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]}
        g = lambda sx, sy, sz: v[(sx * hx, sy * hy, sz * hz)]
        self.quad(g(-1, -1, 1), g(1, -1, 1), g(1, 1, 1), g(-1, 1, 1))
        self.quad(g(-1, -1, -1), g(-1, 1, -1), g(1, 1, -1), g(1, -1, -1))
        self.quad(g(-1, -1, -1), g(1, -1, -1), g(1, -1, 1), g(-1, -1, 1))
        self.quad(g(1, 1, -1), g(-1, 1, -1), g(-1, 1, 1), g(1, 1, 1))
        self.quad(g(1, -1, -1), g(1, 1, -1), g(1, 1, 1), g(1, -1, 1))
        self.quad(g(-1, 1, -1), g(-1, -1, -1), g(-1, -1, 1), g(-1, 1, 1))

    def save(self, path, material):
        return write_glb(path, self.p, self.n, self.t, self.i, material)


def ground(x, y):
    return float(H.north_height(np.array([x]), np.array([y]))[0])


def platform(z0):
    """The grass top (a grid, so it shades and collides well) and the stone skirt falling outwards to the ground."""
    x0, y0, x1, y1 = L.PLATFORM
    ox, oy = L.ORIGIN
    top, skirt = Mesh(), Mesh()
    xs, ys = np.linspace(x0, x1, int((x1 - x0) // 8) + 1), np.linspace(y0, y1, int((y1 - y0) // 8) + 1)
    for a, b in zip(xs[:-1], xs[1:]):
        for c, d in zip(ys[:-1], ys[1:]):
            top.quad((a - ox, c - oy, 0), (b - ox, c - oy, 0), (b - ox, d - oy, 0), (a - ox, d - oy, 0), normal=(0, 0, 1))
    # The skirt: round the rectangle (counter-clockwise), every metre from the platform edge out and down to just
    # below the ground.
    ring = [(x, y0) for x in np.arange(x0, x1, 1.)] + [(x1, y) for y in np.arange(y0, y1, 1.)] + \
           [(x, y1) for x in np.arange(x1, x0, -1.)] + [(x0, y) for y in np.arange(y1, y0, -1.)]
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    lane_x = L.LANE[0][0]

    def out(x, y):
        dx = (L.SKIRT if x >= x1 - 1e-6 else -L.SKIRT if x <= x0 + 1e-6 else 0.)
        dy = (L.SKIRT if y >= y1 - 1e-6 else -L.SKIRT if y <= y0 + 1e-6 else 0.)
        return x + dx, y + dy

    for (ax, ay), (bx, by) in zip(ring, ring[1:] + ring[:1]):
        if ay <= y0 + 1e-6 and by <= y0 + 1e-6 and abs((ax + bx) / 2 - lane_x) < L.LANE_WIDTH / 2:
            continue   # the lane comes in here
        (oax, oay), (obx, oby) = out(ax, ay), out(bx, by)
        za, zb = ground(oax, oay) - z0 - .4, ground(obx, oby) - z0 - .4
        skirt.quad((ax - ox, ay - oy, 0), (oax - ox, oay - oy, za), (obx - ox, oby - oy, zb), (bx - ox, by - oy, 0),
                   uv=[(0, 0), (L.SKIRT / UV_METRES, za / UV_METRES), (L.SKIRT / UV_METRES, zb / UV_METRES), (0, 0.25)])
    return top, skirt


def track():
    """The dirt ribbon, 3 cm over the grass, every metre of the lap; u runs across, v along."""
    mesh = Mesh()
    steps = int(L.LAP)
    half = L.WIDTH / 2
    ox, oy = L.ORIGIN
    for k in range(steps):
        s0, s1 = k * L.LAP / steps, (k + 1) * L.LAP / steps
        (ix0, iy0, _), (ex0, ey0, _) = L.centre(s0, -half), L.centre(s0, half)
        (ix1, iy1, _), (ex1, ey1, _) = L.centre(s1, -half), L.centre(s1, half)
        v0, v1 = s0 / UV_METRES, s1 / UV_METRES
        mesh.quad((ex0 - ox, ey0 - oy, .03), (ex1 - ox, ey1 - oy, .03), (ix1 - ox, iy1 - oy, .03), (ix0 - ox, iy0 - oy, .03),
                  uv=[(0, v0), (0, v1), (L.WIDTH / UV_METRES, v1), (L.WIDTH / UV_METRES, v0)], normal=(0, 0, 1))
    return mesh


def rails():
    """White rails each side of the track: posts every RAIL_POST_STEP and two bars, broken at the walk-in gaps."""
    mesh = Mesh()
    ox, oy = L.ORIGIN
    for offset in (-(L.WIDTH / 2 + .3), L.WIDTH / 2 + .3):
        steps = int(L.LAP / L.RAIL_POST_STEP)
        for k in range(steps):
            s0, s1 = k * L.LAP / steps, (k + 1) * L.LAP / steps
            x0, y0, h0 = L.centre(s0, offset)
            x1, y1, _ = L.centre(s1, offset)
            gap = lambda x, y: abs(y - oy) > L.RADIUS - 1 and y < oy and any(abs(x - gx) < w / 2 for gx, w in L.RAIL_GAPS)
            if gap(x0, y0) or gap(x1, y1):
                continue
            mesh.box((x0 - ox, y0 - oy, L.RAIL_HEIGHT / 2), (.06, .06, L.RAIL_HEIGHT / 2), h0)
            length = math.hypot(x1 - x0, y1 - y0)
            yaw = math.atan2(y1 - y0, x1 - x0)
            mid = ((x0 + x1) / 2 - ox, (y0 + y1) / 2 - oy)
            for z, thick in ((L.RAIL_HEIGHT - .05, .07), (L.RAIL_HEIGHT * .55, .04)):
                mesh.box((mid[0], mid[1], z), (length / 2 + .03, .05, thick), yaw)
    return mesh


def lane(z0):
    """The lane from the street up to the platform: a straight ramp, with its own skirts down to the ground."""
    mesh, sides = Mesh(), Mesh()
    (lx, ya), (_, yb) = L.LANE
    ox, oy = L.ORIGIN
    w = L.LANE_WIDTH / 2
    n = int(yb - ya)
    zs = np.linspace(L.LANE_START_Z, z0 + .02, n + 1)
    ys = np.linspace(ya, yb, n + 1)
    for k in range(n):
        za, zb = zs[k] - z0, zs[k + 1] - z0
        mesh.quad((lx - w - ox, ys[k] - oy, za), (lx + w - ox, ys[k] - oy, za), (lx + w - ox, ys[k + 1] - oy, zb),
                  (lx - w - ox, ys[k + 1] - oy, zb), uv=[(0, ys[k] / UV_METRES), (L.LANE_WIDTH / UV_METRES, ys[k] / UV_METRES),
                                                       (L.LANE_WIDTH / UV_METRES, ys[k + 1] / UV_METRES), (0, ys[k + 1] / UV_METRES)])
        for side in (-1, 1):
            x = lx + side * w
            ga, gb = ground(x + side * 1.5, ys[k]) - z0 - .4, ground(x + side * 1.5, ys[k + 1]) - z0 - .4
            a, b = (x - ox, ys[k] - oy, za), (x - ox, ys[k + 1] - oy, zb)
            c, d = (x + side * 1.5 - ox, ys[k + 1] - oy, min(gb, zb - .3)), (x + side * 1.5 - ox, ys[k] - oy, min(ga, za - .3))
            sides.quad(*((a, d, c, b) if side > 0 else (a, b, c, d)))
    return mesh, sides


def structure(slug, spec):
    """A Tripo model scaled to its size (front axis, across, height) with its base at z = 0; glTF axes kept."""
    gltf, binary = _read(PROPS / slug / f'{slug}.glb')
    primitive = gltf['meshes'][0]['primitives'][0]
    view = lambda accessor: gltf['bufferViews'][gltf['accessors'][accessor]['bufferView']]
    count = lambda accessor: gltf['accessors'][accessor]['count']

    def array(accessor):
        v = view(accessor)
        start = v.get('byteOffset', 0) + gltf['accessors'][accessor].get('byteOffset', 0)
        return np.frombuffer(bytes(binary[start:start + count(accessor) * 12]), np.float32).reshape(-1, 3).copy()

    pos, nrm = array(primitive['attributes']['POSITION']), array(primitive['attributes']['NORMAL'])
    lo, hi = pos.min(0), pos.max(0)
    depth, across, height = spec['size']
    scale = np.array([depth / (hi[0] - lo[0]), height / (hi[1] - lo[1]), across / (hi[2] - lo[2])], np.float32)
    pos = (pos - np.array([(lo[0] + hi[0]) / 2, lo[1], (lo[2] + hi[2]) / 2], np.float32)) * scale
    nrm = nrm / scale
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-9)
    for accessor, values in ((primitive['attributes']['POSITION'], pos), (primitive['attributes']['NORMAL'], nrm)):
        v = view(accessor)
        start = v.get('byteOffset', 0) + gltf['accessors'][accessor].get('byteOffset', 0)
        binary[start:start + values.nbytes] = values.astype(np.float32).tobytes()
    acc = gltf['accessors'][primitive['attributes']['POSITION']]
    acc['min'] = [float(v) for v in pos.min(0)]; acc['max'] = [float(v) for v in pos.max(0)]
    name = 'SM_HD_' + ''.join(part.title() for part in slug.split('_'))
    gltf['meshes'][0]['name'] = gltf['nodes'][0]['name'] = name
    gltf['materials'][0]['name'] = 'HD_' + ''.join(part.title() for part in slug.split('_'))
    _save(OUT / 'glb' / f'{name}.glb', gltf, binary)
    return name, {'triangles': sum(count(p['indices']) // 3 for m in gltf['meshes'] for p in m['primitives']),
                  'min': [float(pos[:, 0].min()), float(-pos[:, 2].max()), float(pos[:, 1].min())],
                  'max': [float(pos[:, 0].max()), float(-pos[:, 2].min()), float(pos[:, 1].max())],
                  'material': gltf['materials'][0]['name']}


# ------------------------------------------------------------------ textures
def tiling_noise(size, seed, falloff):
    """Tileable noise: white noise filtered in the frequency domain, normalised to 0..1."""
    rng = np.random.default_rng(seed)
    f = np.fft.fftfreq(size)
    radius = np.sqrt(f[None, :] ** 2 + f[:, None] ** 2) + 1. / size
    field = np.real(np.fft.ifft2(np.fft.fft2(rng.standard_normal((size, size))) / radius ** falloff))
    return (field - field.min()) / (field.max() - field.min())


def textures():
    from PIL import Image
    folder = OUT / 'textures'
    folder.mkdir(parents=True, exist_ok=True)
    size = 512
    soft, fine = tiling_noise(size, 11, 1.4), tiling_noise(size, 12, .6)
    # Raked dirt: warm ochre with darker worn patches and pale grit.
    dirt0, dirt1, grit = np.array([.62, .46, .30]), np.array([.47, .33, .21]), np.array([.78, .66, .50])
    mix = np.clip((soft - .35) * 2.2, 0, 1)[..., None]
    dirt = dirt0 * (1 - mix) + dirt1 * mix
    speck = (fine > .78)[..., None]
    dirt = np.where(speck, dirt * .6 + grit * .4, dirt) * (.92 + .16 * fine[..., None])
    rake = .04 * np.sin(np.arange(size) / size * 2 * np.pi * 24)[:, None, None]   # furrows along the track (v)
    dirt = np.clip(dirt + rake, 0, 1)
    Image.fromarray((dirt * 255).astype(np.uint8)).save(folder / 'T_HD_Dirt.png')
    # Turf: the island's soft greens, mown in broad stripes.
    g0, g1 = np.array([.42, .58, .30]), np.array([.33, .50, .24])
    mix = np.clip((soft - .3) * 1.8, 0, 1)[..., None]
    stripes = (np.sin(np.arange(size) / size * 2 * np.pi * 2)[None, :, None] > 0) * .05
    grass = np.clip((g0 * (1 - mix) + g1 * mix) * (.9 + .2 * fine[..., None]) + stripes, 0, 1)
    Image.fromarray((grass * 255).astype(np.uint8)).save(folder / 'T_HD_Grass.png')
    return {'HD_Dirt': 'T_HD_Dirt.png', 'HD_Grass': 'T_HD_Grass.png'}


# ------------------------------------------------------------------ main
def main():
    z0 = L.platform_height(H.north_height)
    ox, oy = L.ORIGIN
    glb = OUT / 'glb'
    report, meshes = {}, []
    top, skirt = platform(z0)
    lane_top, lane_sides = lane(z0)
    for name, mesh, material in [('SM_HD_Ground', top, 'HD_Grass'), ('SM_HD_Skirt', skirt, 'HD_Stone'),
                                 ('SM_HD_Track', track(), 'HD_Dirt'), ('SM_HD_Rails', rails(), 'HD_Rail'),
                                 ('SM_HD_Lane', lane_top, 'HD_Dirt'), ('SM_HD_LaneSkirt', lane_sides, 'HD_Stone')]:
        report[name] = mesh.save(glb / f'{name}.glb', material)
        meshes.append({'name': name, 'at': [0., 0., 0.], 'yaw': 0., 'blocks': True})
    for slug, spec in L.STRUCTURES.items():
        name, info = structure(slug, spec)
        report[name] = info
        x, y = spec['at']
        meshes.append({'name': name, 'slug': slug, 'at': [x - ox, y - oy, 0.], 'yaw': spec['yaw'], 'blocks': True})
    for name in report:
        report[name]['sha256'] = hashlib.sha256((glb / f'{name}.glb').read_bytes()).hexdigest()

    data = {
        'key': 'hippodrome', 'asset_root': '/Game/Hippodrome', 'origin': [ox, oy, z0], 'yaw_deg': 0.,
        'meshes': meshes, 'textures': textures(),
        'course': {'origin': [ox, oy], 'half': L.HALF, 'radius': L.RADIUS, 'width': L.WIDTH, 'lap': round(L.LAP, 3),
                   'finish_x': L.FINISH_X, 'direction': 'counter-clockwise', 'z': z0},
        'return': {'at': [L.RETURN['at'][0] - ox, L.RETURN['at'][1] - oy, 0.], 'yaw': L.RETURN['yaw']},
        'clearance': L.clearance(),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'hippodrome.json').write_text(json.dumps(data, indent=1) + '\n')
    (OUT / 'build-report.json').write_text(json.dumps({'platform_z': z0, 'meshes': report}, indent=1) + '\n')
    print(f'platform at {z0} m; ' + ', '.join(f"{k} {v['triangles']}" for k, v in report.items()))
    print('HIPPODROME BUILD COMPLETE')


if __name__ == '__main__':
    main()
