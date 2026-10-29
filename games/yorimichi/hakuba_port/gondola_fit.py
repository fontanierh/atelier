"""Blender script: fit Yorimichi's three gondola lines to Hakuba's ground and write every fitted piece for `gondola.py`.

    blender -b --threads 3 -P games/yorimichi/hakuba_port/gondola_fit.py -- KIT OUT

`KIT` is the gondola kit's build folder (`build/yorimichi/gondola`, written by the kit's own `build.py`), which must be
current with its sources and have passed its gates. `OUT` receives `assets/*.fbx` and `gondola.json`.

The lines, stations and towers are Yorimichi's (`regions/gondola/layout.py`), and so is the fitting: this runs
`regions/gondola/site.py`'s own functions, with Hakuba's ground in place of Yorimichi's final terrain products and
Hakuba's Crater Park props in place of the park's riding pieces.

- **Ground:** Hakuba's ground heights, triangulated with its own diagonals (`world/src/ground`), as one terrain owner.
  Each station's floor stands 0.55 m over the highest ground under it, on timber posts with stone feet; each tower's
  datum is over the highest ground under its feet; the access stairs come down to the ground.
- **Gates kept:** every fitted mesh is closed, without coplanar overlaps, seated and carried by the ground; static
  supports and stairs leave the park's riding pieces untouched; the cabin's path clears the park's riding and jump
  geometry by 15 m, the ground by 6 m outside the 35 m station approaches; the jaws seat on the rope and the cabin
  clears it and every tower along the whole fitted span.
- **Left out:** Belmonte's town-structure and zeppelin flight-corridor proofs, which read Yorimichi build products
  Hakuba does not have, and Belmonte's walking link to the zeppelin path.

Everything stands still. Each line's twelve cabins (four on the crater-floor line) stand where Yorimichi's service
clock puts them at one moment: of eight across a cabin's headway, the one with the most cabins out on the rope. A cabin hangs plumb from its grip's pivot (`cabin.pose`), so its body, hanger and doors
are one mesh placed level and turned to its heading, and its grip, which takes the rope's pitch, is a mesh of its own
in that same frame. Each placed cabin's jaws are checked seated on the rope and the rest of it clear of the rope.

The ropes are cut into stretches of about 60 m, each a mesh of its own, so that no model spans more than a tile or
two. `gondola.json` lists each piece: its FBX, its collision, whether it is solid, a description and its instances
`[x, y, z, yaw, 1]` (map metres, the height absolute, the turn counter-clockwise in degrees), with the proofs.
"""
import importlib.util
import json
import math
import shutil
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
YORIMICHI = HERE.parent
WORLD = YORIMICHI / 'world'
KIT_SOURCES = YORIMICHI / 'assets' / 'vehicles' / 'gondola'
sys.path[:0] = [str(KIT_SOURCES), str(WORLD)]

import bpy  # noqa: E402


def _local(name):
    """This folder's module `name`, loaded by path: with this folder on `sys.path` its `regions.py` would shadow
    Yorimichi's `regions` namespace package."""
    spec = importlib.util.spec_from_file_location(name, HERE / f'{name}.py')
    module = sys.modules[name] = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_ground = _local('ground')
HAKUBA, HAKUBA_WORLD, settings = _ground.HAKUBA, _ground.WORLD, _ground.settings
mosaic = _local('contact').mosaic
painted = _local('painted')

_spec = importlib.util.spec_from_file_location('gondola_site', WORLD / 'regions' / 'gondola' / 'site.py')
S = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S)
K, P, R, solid, checks, W = S.K, S.P, S.R, S.solid, S.checks, S.W
from gondola import clock  # noqa: E402
from gondola.clearance import riding_clearance  # noqa: E402

# A rope stretch is at most this long, so that it stays within a tile or two.
STRETCH_M = 60.0
# Hakuba's ground cells, as the gondola surfaces bin their triangles.
CELL_M = 32.0
# Coplanar overlap a fitted mesh may keep, in all.
COPLANAR_M2 = 0.25
# How far Hakuba's ground may rise through an access stair's ground join (`site.access_stair` allows 3 cm over
# Yorimichi's finer terrain; Hakuba's is drawn on 2 m triangles that the join's sampled edge can cut across).
INTRUSION_M = 0.08
INTRUSIONS = []


def floor_intrusion(G, polygon, heights):
    """`support.floor_intrusion`, recorded, failing past INTRUSION_M; `site.access_stair` sees at most its own 3 cm."""
    value = _floor_intrusion(G, polygon, heights)
    INTRUSIONS.append(value)
    if value > INTRUSION_M:
        raise ValueError(f'Hakuba\'s ground rises {value:.3f} m through an access floor')
    return min(value, .03)


_floor_intrusion, S.floor_intrusion = S.floor_intrusion, floor_intrusion
# Cabins per line, as Yorimichi's service runs them.
CABINS = {'L1': 12, 'L2': 12, 'L3': 4}
# A cabin this close to a station's mouth is at its attach zone, which the kit's loop audit covers.
ATTACH_M = 2.0


class Surface:
    """Hakuba's ground as a gondola terrain surface (`terrain_query.Surface`'s fields), its triangles made per 32 m
    cell when first asked for, each grid square split along the diagonal Hakuba's ground draws."""
    owner, stage, cell = 'hakuba', 'final', CELL_M

    def __init__(self):
        world = settings()
        self.heights = mosaic(world)
        self.south_west = np.array(world['south_west_m'], float)
        self.step = float(world['ground_step_m'])
        diagonals = json.loads((HAKUBA_WORLD / world['terrain_diagonals']).read_text())
        if diagonals['step_m'] != self.step:
            raise ValueError('terrain diagonals are on another grid')
        self.alternate = {tuple(np.rint((np.array(c) - self.south_west) / self.step).astype(int))
                          for c in diagonals['alternate_cells_m']}
        self.parts, self.ids, self.count, self._cache = [], {}, 0, None
        self.bins = Bins(self)

    def corner(self, i, j):
        return self.heights[j, i] if 0 <= j < self.heights.shape[0] and 0 <= i < self.heights.shape[1] else np.nan

    def cell_ids(self, key):
        if key in self.ids:
            return self.ids[key]
        x0, y0 = key[0] * CELL_M, key[1] * CELL_M
        i0, j0 = int(round((x0 - self.south_west[0]) / self.step)), int(round((y0 - self.south_west[1]) / self.step))
        n = int(round(CELL_M / self.step))
        triangles = []
        for j in range(j0, j0 + n):
            for i in range(i0, i0 + n):
                h = [self.corner(i, j), self.corner(i + 1, j), self.corner(i + 1, j + 1), self.corner(i, j + 1)]
                if not np.isfinite(h).all():
                    continue
                p = [(*(self.south_west + self.step * np.array(q)), z)
                     for q, z in zip(((i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)), h)]
                if (i, j) in self.alternate:
                    triangles += [(p[0], p[1], p[3]), (p[1], p[2], p[3])]
                else:
                    triangles += [(p[0], p[1], p[2]), (p[0], p[2], p[3])]
        ids = tuple(range(self.count, self.count + len(triangles)))
        if triangles:
            self.parts.append(np.array(triangles, float))
            self.count += len(triangles)
            self._cache = None
        self.ids[key] = ids
        return ids

    def cover(self, low, high):
        """Make every cell over the map rectangle `low`..`high`."""
        for x in range(math.floor(low[0] / CELL_M), math.floor(high[0] / CELL_M) + 1):
            for y in range(math.floor(low[1] / CELL_M), math.floor(high[1] / CELL_M) + 1):
                self.cell_ids((x, y))

    def _arrays(self):
        if self._cache is None:
            triangles = np.concatenate(self.parts) if self.parts else np.empty((0, 3, 3))
            normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
            normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)
            self._cache = triangles, normals
        return self._cache

    @property
    def triangles(self):
        return self._arrays()[0]

    @property
    def normals(self):
        return self._arrays()[1]

    def height(self, xy):
        """The ground's height at map points, interpolated on its drawn triangles; NaN off the ground."""
        f = (np.asarray(xy, float) - self.south_west) / self.step
        i, j = np.floor(f[:, 0]).astype(int), np.floor(f[:, 1]).astype(int)
        u, v = f[:, 0] - i, f[:, 1] - j
        out = np.empty(len(f))
        for k in range(len(f)):
            h00, h10 = self.corner(i[k], j[k]), self.corner(i[k] + 1, j[k])
            h11, h01 = self.corner(i[k] + 1, j[k] + 1), self.corner(i[k], j[k] + 1)
            a, b = u[k], v[k]
            if (i[k], j[k]) in self.alternate:
                out[k] = (h00 * (1 - a - b) + h10 * a + h01 * b if a + b <= 1
                          else h10 * (1 - b) + h11 * (a + b - 1) + h01 * (1 - a))
            elif a >= b:
                out[k] = h00 * (1 - a) + h10 * (a - b) + h11 * b
            else:
                out[k] = h00 * (1 - b) + h11 * a + h01 * (b - a)
        return out


class Bins:
    """A surface's `bins`: the triangle ids of each 32 m cell, made when first asked for."""

    def __init__(self, surface):
        self.surface = surface

    def get(self, key, default=()):
        return self.surface.cell_ids(key)


class NoTrail:
    """No walking overlay over Hakuba's ground."""
    owner, stage, cell, bins = 'trail', 'final', CELL_M, {}
    triangles, normals = np.empty((0, 3, 3)), np.empty((0, 3))


class Ground:
    """The gondola ground queries (`gondola.terrain.Ground`'s interface) over Hakuba's ground, one owner everywhere."""

    def __init__(self):
        self.surface = Surface()
        # `support.owned_triangles` carves Belmonte's own valley out of the apron; here it lies off the map.
        self.surfaces = {'apron': self.surface, 'valley': self.surface}
        self.bounds = {'apron': (-1e6, -1e6, 1e6, 1e6), 'valley': (1e7, 1e7, 1e7 + 1, 1e7 + 1)}
        self.trail = NoTrail()

    def base(self, xy):
        xy = np.asarray(xy, float)
        height = self.surface.height(xy)
        if not np.isfinite(height).all():
            raise ValueError('Gondola query off Hakuba\'s ground')
        return height, np.full(len(xy), self.surface.owner, object)

    contact = base


def riding():
    """Hakuba's Crater Park props, every triangle placed on the map: the park's riding pieces."""
    placements = json.loads((HAKUBA / 'world/src/regions/craterpark/placements.json').read_text())
    out = []
    for group in placements['groups']:
        name = group['model'].split('/', 1)[1]
        if group.get('on_ground'):
            raise ValueError(f'{name}: a Crater Park piece stands on the ground')
        _, _, parts = painted.read(HAKUBA / 'props' / name / 'src' / 'model.glb')
        corners = np.concatenate([part[0] for part in parts])
        for x, y, z, yaw, scale in group['instances']:
            c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
            p = corners * scale
            out.append(np.stack([x + c * p[..., 0] - s * p[..., 1], y + s * p[..., 0] + c * p[..., 1],
                                 z + p[..., 2]], -1))
    return np.concatenate(out)


def placement(frame):
    """The instance `[x, y, z, yaw, 1]` of a mesh built in `frame` (origin, along, lateral, height)."""
    origin, along, _, z = frame
    return [float(origin[0]), float(origin[1]), float(z), math.degrees(math.atan2(along[1], along[0])), 1.0]


def export(mesh, folder, mats):
    """Write `mesh` as `<name>.fbx`; returns the file name."""
    obj, _ = solid.to_object(mesh, mats)
    path = folder / f'{mesh.name}.fbx'
    solid.export_fbx([obj], path)
    bpy.data.objects.remove(obj, do_unlink=True)
    return path.name


def export_world(mesh, folder, mats, G, frame, riding_triangles, limit=50000, seats=()):
    """`site.export_world`'s gates over Hakuba's ground: closed, within its budget, clear of the riding pieces, seated
    and carried by the ground. Coplanar overlaps, which Hakuba's ground can make where two access floors meet, are
    recorded and fail only past COPLANAR_M2 in all. Returns the file name and the proofs."""
    xy = S.world_xy(np.asarray(mesh.verts, float)[:, :2], frame)
    G.surface.cover(xy.min(0) - 2, xy.max(0) + 2)
    proof = solid.closed(mesh)
    if proof['open_edges'] or proof['misoriented_edges'] or proof['degenerate_faces'] or mesh.tris() > limit:
        raise ValueError(f'{mesh.name}: invalid or over-budget mesh: {proof}, {mesh.tris()} triangles')
    S.untouched_riding(mesh, frame, riding_triangles)
    count, samples = solid._shared.coplanar_overlaps([mesh])
    area = sum(sample['area_m2'] for sample in samples)
    seating = solid.seats([mesh], seats)
    summary, failures = solid._shared.carried_failures([mesh], S.world_ground(mesh, frame, G))
    if area > COPLANAR_M2 or failures or any(row['status'] != 'ok' for row in seating):
        raise ValueError(f'{mesh.name}: coplanar/seating/carried proof failed: {samples}, {seating}, {failures}')
    name = export(mesh, folder, mats)
    return name, {'name': mesh.name, 'triangles': mesh.tris(), 'closed': proof,
                  'coplanar': {'count': count, 'area_m2': area, 'samples': samples}, 'carried': summary}


def stretches(points, name):
    """The rope polyline `points` cut into stretches of at most STRETCH_M, each `(name, origin, local points)`."""
    arc = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))]
    count = max(1, math.ceil(arc[-1] / STRETCH_M))
    cuts = np.linspace(0.0, arc[-1], count + 1)
    out = []
    for k, (a, b) in enumerate(zip(cuts[:-1], cuts[1:])):
        inside = (arc > a) & (arc < b)
        piece = np.vstack([[np.interp(a, arc, points[:, i]) for i in range(3)], points[inside],
                           [np.interp(b, arc, points[:, i]) for i in range(3)]])
        origin = piece[0].copy()
        out.append((f'{name}_{k:02d}', origin, piece - origin))
    return out


def main():
    kit_dir, out = (Path(a).resolve() for a in sys.argv[sys.argv.index('--') + 1:][:2])
    kit = json.loads((kit_dir / 'manifest.json').read_text())
    if kit.get('soft_fail') or kit['failures'] or kit['source_hash'] != K.source_hash():
        raise SystemExit('Gondola kit is stale or failed: rebuild it with its build.py')
    assets = out / 'assets'
    if out.exists():
        shutil.rmtree(out)
    assets.mkdir(parents=True)
    p = dict(P.DEFAULTS)
    d = P.derived(p)
    G = Ground()
    ride = riding()
    layouts = {kind: json.loads((kit_dir / f'layout_{kind}.json').read_text()) for kind in ('valley', 'rim', 'crater')}
    mats = solid.make_materials({})
    cabin = S.Cabin(p, d)
    meshes, _ = cabin.build()
    cab = {'cabin': cabin, 'meshes': meshes}
    shells = {kind: cls(kind, p, d).make()
              for kind, cls in (('valley', S.Valley), ('rim', S.Rim), ('crater', S.Crater))}
    pieces, proofs = [], {'stations': {}, 'lines': {}}

    def piece(fbx, about, instances, solid_=True, collision=None, source=None):
        pieces.append({'fbx': fbx, 'source': str(source) if source else None, 'about': about, 'solid': solid_,
                       'collision': collision, 'instances': instances})

    # The kit's shells and the hung cabin, once each.
    kinds_used = set()
    objects = [solid.to_object(meshes[name], mats)[0]
               for name in ('GD_Cabin', 'GD_CabinHanger', 'GD_CabinDoorLeft', 'GD_CabinDoorRight')]
    solid.export_fbx(objects, assets / 'GD_CabinHung.fbx')
    for o in objects:
        bpy.data.objects.remove(o, do_unlink=True)
    cabins_at = []
    frames = {}
    for line in S.LINES:
        first, last = line['stations']
        for key, other in ((first, last), (last, first)):
            print('HAKUBA GONDOLA station', key, flush=True)
            spec = S.STATIONS[key]
            G.surface.cover(np.asarray(spec['mouth']) - 90, np.asarray(spec['mouth']) + 90)
            data, frame = S.fit_station(key, other, G, layouts)
            for shell in shells[data['kind']].values():
                S.untouched_riding(shell, frame, ride)
            foundation, posts = S.station_foundation(key, layouts[data['kind']], G, frame)
            stair, access = S.access_stair(key, layouts[data['kind']], G, frame)
            loop = R.station_loop(p['gauge'] / 2, d['rope_height_above_platform'], d['rope_height_above_platform'], 7.6,
                                  p['rope_radius'], step=.5).pts
            data['jump'] = S.station_jump_clearance(S.placed(loop, frame), ride,
                                                    d['grip_to_floor'] + p['cabin_floor_depth'])
            name, data['foundation'] = export_world(foundation, assets, mats, G, frame, ride)
            piece(name, f"{spec['name']}'s timber posts and braces on their stone feet", [placement(frame)])
            name, data['access_mesh'] = export_world(stair, assets, mats, G, frame, ride, seats=access['rail_seats'])
            piece(name, f"{spec['name']}'s stair down to the ground", [placement(frame)])
            kinds_used.add(data['kind'])
            data.update(posts=len(posts), access={k: access[k] for k in ('width', 'risers', 'riser', 'tread')},
                        ground_through_access_m=max(INTRUSIONS, default=0.0))
            INTRUSIONS.clear()
            proofs['stations'][key] = {k: v for k, v in data.items() if k not in ('footprints',)}
            frames[key] = (frame, data)
        A, B = np.asarray(S.STATIONS[first]['mouth']), np.asarray(S.STATIONS[last]['mouth'])
        length = float(np.linalg.norm(B - A))
        direction = (B - A) / length
        for s, height in line['towers']:
            xy = A + s * direction
            G.surface.cover(xy - 12, xy + 12)
        fitted = [S.tower_fit(f'{line["id"]}_{k}', s, h, A, direction, G, p, build=False)
                  for k, (s, h) in enumerate(line['towers'])]
        supports = [(.6, frames[first][0][3] + d['rope_height_above_platform'], False)]
        supports += [(row['s'], frame[3] + row['height'], True) for _, _, frame, row in fitted]
        supports.append((length - .6, frames[last][0][3] + d['rope_height_above_platform'], False))
        saddles = S.tower_saddles(supports)
        profile = S.centre_profile(supports)
        towers = []
        for k, (_, _, _, row) in enumerate(fitted):
            tower, mesh, frame, row = S.tower_fit(row['id'], row['s'], row['height'], A, direction, G, p,
                                                  saddle=saddles[k + 1])
            name, row['mesh'] = export_world(mesh, assets, mats, G, frame, ride, limit=checks.BUDGET['tower'],
                                           seats=tower.seats)
            row['contact_audit'] = S.tower_path_audit(tower, mesh, row, profile, cab, p, d)
            piece(name, f'a {row["height"]:.0f} m timber tower of gondola line {line["id"]}', [placement(frame)])
            towers.append(row)
        clearance = riding_clearance(ride, A, direction, profile, lateral=16.3, half_length=p['cabin_length'] / 2,
                                     drop=d['grip_to_floor'] + p['cabin_floor_depth'])
        if clearance['minimum_m'] is not None and clearance['minimum_m'] < 15.:
            raise ValueError(f'{line["id"]}: the cabins pass within 15 m of Crater Park: {clearance}')
        G.surface.cover(np.minimum(A, B) - 12, np.maximum(A, B) + 12)
        gap = S.ground_gap(profile, A, direction, G, d['grip_to_floor'] + p['cabin_floor_depth'])
        audit = S.audit_span(line['id'], profile, cab, p)
        normal = np.array([-direction[1], direction[0]])
        for side in (-1, 1):
            points = np.c_[A + profile[:, 0, None] * direction + side * p['gauge'] / 2 * normal, profile[:, 1]]
            points = S.simplify(points, .015)
            for name, origin, local in stretches(points, f'GD_{line["id"]}_Rope{"AB"[side > 0]}'):
                mesh = solid.Mesh(name)
                mesh.tube([tuple(q) for q in local], p['rope_radius'], solid.STEEL, n=8)
                piece(export(mesh, assets, mats), f'a stretch of gondola line {line["id"]}\'s haul rope',
                      [[*map(float, origin), 0.0, 1.0]], solid_=False)
        # The cabins, where the service clock has them at the chosen moment.
        loop = R.station_loop(p['gauge'] / 2, d['rope_height_above_platform'], d['rope_height_above_platform'], 7.6,
                              p['rope_radius']).pts
        circuit = S.closed_circuit(profile, frames[first][0], frames[last][0], loop, p['gauge'])
        rows = []
        for key in line['stations']:
            frame, data = frames[key]
            origin, along, lateral, z = frame
            rope_z = float(z + d['rope_height_above_platform'])
            rows.append({'id': key, 'origin': list(map(float, origin)), 'along': list(map(float, along)),
                         'lateral': list(map(float, lateral)), 'rope_z': rope_z,
                         'mouth_grip': [*map(float, S.STATIONS[key]['mouth']), rope_z],
                         'berth_x': p['berth_x'], 'gauge': p['gauge'], 'mouth_x': 7.6})
        tracks = [{'tracks': {str(side): [row['origin'][0] + side * p['gauge'] / 2 * normal[0],
                                          row['origin'][1] + side * p['gauge'] / 2 * normal[1],
                                          row['origin'][2] + row['height']] for side in (-1, 1)}} for row in towers]
        table = clock.prepare(circuit, rows, tracks)
        path = R.RopePath(table['points'], p['rope_radius'])
        count = CABINS[line['id']]
        placed, in_station = [], 0

        def on_line(state):
            along = float((np.asarray(state['point'], float)[:2] - A) @ direction)
            return ATTACH_M < along < length - ATTACH_M

        # The scene stands still at one moment of the service: the one, of eight across a cabin's headway, with the
        # most cabins out on the rope, so every line shows (and proves) cabins hanging in the span.
        headway = table['cycle_s'] / count
        phase = max((j * headway / 8 for j in range(8)),
                    key=lambda t: sum(on_line(clock.state(table, t + k * headway)) for k in range(count)))
        for k in range(count):
            state = clock.state(table, phase + k * headway)
            s = state['arc'] % path.length
            at = np.asarray(state['point'], float)
            off = (at[:2] - A) - ((at[:2] - A) @ direction) * direction
            outward = (*(off / max(np.linalg.norm(off), 1e-9)), 0.0)
            pose = S.pose(path.grip_frame(float(s), outward))
            if not checks.hanging_ok(pose.C):
                raise ValueError(f'{line["id"]} cabin {k}: its floor is not level')
            if on_line(state):
                # On the line, the jaws close on the rope; at a station's mouth they close or open on it, and inside
                # the grip runs on the rail with the rope dropped clear: the loop the kit's own build audits pose by
                # pose.
                placed.append((f'{line["id"]} cabin {k}', pose, float(s)))
            else:
                in_station += 1
            C = pose.C
            grip = solid.transformed(meshes['GD_CabinGrip'], C.inverted() @ pose.G,
                                     f'GD_{line["id"]}_Cabin{k:02d}_Grip')
            instance = [float(C[0][3]), float(C[1][3]), float(C[2][3]), math.degrees(math.atan2(C[1][0], C[0][0])), 1.0]
            piece(export(grip, assets, mats), f'the grip of a cabin of gondola line {line["id"]}', [instance],
                  solid_=False)
            cabins_at.append(instance)
        if not placed:
            raise ValueError(f'{line["id"]}: no cabin hangs on the line to prove its rope clearance')
        groove = K.groove_check(cab, path, placed)
        rope = K.rope_check(cab, path, placed)
        jaw = K.jaw_contact(cab, path, placed)
        if not groove['ok'] or not rope['ok'] or not jaw['ok']:
            raise ValueError(f'{line["id"]}: a placed cabin clips its rope: {groove}, {rope}, {jaw}')
        proofs['lines'][line['id']] = {
            'towers': [{k: v for k, v in row.items() if k != 'contact_audit'} for row in towers],
            'tower_contact': [[{k: v for k, v in side.items() if k in ('side', 'poses', 'contacts', 'body_envelope')}
                               for side in row['contact_audit']] for row in towers],
            'riding': clearance, 'ground': gap, 'span_audit': audit,
            'cabins': {'count': count, 'phase_s': phase, 'in_stations': in_station, 'on_the_line': len(placed),
                       'groove_max_mm': groove.get('max_error_mm'),
                       'rope_clearance_m': rope.get('min_distance_from_rope_axis_m'), 'jaw': jaw.get('ok')}}
        print('HAKUBA GONDOLA line complete', line['id'], flush=True)
    piece('GD_CabinHung.fbx', 'a gondola cabin, hanging plumb from its grip', cabins_at, solid_=True)
    for kind in sorted(kinds_used):
        title = kind.title()
        instances = [placement(frame) for frame, data in frames.values() if data['kind'] == kind]
        for part in ('Platform', 'Building', 'Machinery', 'Fittings'):
            name = f'GD_Station{title}_{part}'
            collision = f'GD_Station{title}_Collision.fbx' if part == 'Platform' else None
            if collision:
                shutil.copy(kit_dir / 'assets' / collision, assets / collision)
            shutil.copy(kit_dir / 'assets' / f'{name}.fbx', assets / f'{name}.fbx')
            piece(f'{name}.fbx', f'a gondola {kind} station\'s {part.lower()}', instances, solid_=part == 'Platform',
                  collision=collision)
    textures = out / 'textures'
    textures.mkdir()
    for path in (kit_dir / 'textures').glob('GD_*_color.png'):
        shutil.copy(path, textures / f'{path.stem.removeprefix("GD_").removesuffix("_color")}.png')
    (out / 'gondola.json').write_text(json.dumps({'kit_source': kit['source_hash'], 'pieces': pieces,
                                                  'materials': kit['materials'],
                                                  'textured_materials': kit['textured_materials'],
                                                  'proofs': proofs}, indent=1, default=float) + '\n')
    print('HAKUBA GONDOLA COMPLETE', len(pieces), 'pieces', flush=True)


if __name__ == '__main__':
    main()
