"""Crater Park v2: the shared data model (plan/pipeline.md section 3.1). FROZEN API: change only through the coordinator.

Frame: native metres, y up. A plan point is (x, z); a 3D point is (x, y, z). Unreal: ue(p) = 100 * (x, z, y).
Winding: a face's front is counter-clockwise by the right-hand rule, so an upward face has cross(b - a, c - a).y > 0
(the same convention as r4's meshes in assets/craterpark/geometry).

What the other modules build on:
- `Tess`: tessellation tolerances. The spacing is the SMALLEST allowed by chord error, segment angle and maximum edge.
- `curves.Curve` (Line, Arc, Polyline, Spline): plan paths parameterised by arc length t in metres.
- `profile.Profile`: a 2D (x across or along, y up) chain of ('line', L), ('arc', R, to_deg) and ('corner', to_deg)
  parts, evaluated by its own arc length s, with per-part attributes (role, material) and named tags.
- `Height`: a longitudinal height curve y(t) along a path.
- `sweep.sweep(...)` -> `sweep.Patch`: E1, a profile swept along a path (transverse or longitudinal).
- `network.Network`: shared boundary samples, so both sides of a seam use the same vertices.
- `Mesh`: the one geometry container every primitive returns and every validator reads.
- `Rail`, `Park`: what a layout compiles to; generate.py splits and exports a `Park`.
"""
from dataclasses import dataclass, field
import math

import numpy as np

# ---------------------------------------------------------------- the Unreal contract's vocabulary
MATERIALS = tuple(f'material_{i:03d}' for i in range(29)) + ('coping_steel',)
"""Material ids, as assets/craterpark/materials.json plus the steel coping. Faces store an index into this tuple."""
MATERIAL = {name: i for i, name in enumerate(MATERIALS)}
CONCRETE = 'material_010'       # seamless transition concrete
DECK = 'material_000'           # concrete deck
SIDE_WALL = 'material_023'      # cast concrete, world triplanar
GROUND_MAT = 'material_024'     # hillside, snowy
LEDGE = 'material_002'
STEEL = 'coping_steel'

RIDING, SIDE, GROUND, COPING, RAIL, BASE = 'riding', 'side', 'ground', 'coping', 'rail', 'base'
ROLES = (RIDING, SIDE, GROUND, COPING, RAIL, BASE)
"""Face roles. riding: skated surfaces; side: walls and solid sides (collidable); ground: hillside; coping: render-only
tube; rail: render rail body; base: the buried bottom that closes a solid (never exported, kept for watertight checks)."""
ROLE = {name: i for i, name in enumerate(ROLES)}
TAGS = ('', 'takeoff', 'landing', 'lip', 'coping', 'crest', 'foot')
"""Face tags for the line validator and ride checks: a kicker's lip faces are 'takeoff', a landing ramp's 'landing'."""
TAG = {name: i for i, name in enumerate(TAGS)}
COLLISION_ROLE = {RIDING: 'original', SIDE: 'original', GROUND: 'mountain', RAIL: 'original'}
"""Face role -> the collision role name in UC_CP_<role>_<k>. Roles missing here (coping, base) have no collision."""
RENDER_ROLE = {RIDING: 'original', SIDE: 'original', GROUND: 'mountain', COPING: 'coping', RAIL: 'original'}
"""Face role -> the render entry's `role` in build.json. base is never drawn."""

UV_METRES = 9.0                 # metres per texture tile for concrete (additions.UV_METRES)


# ---------------------------------------------------------------- tessellation
@dataclass(frozen=True)
class Tess:
    """Tessellation tolerances. Along any curve the spacing is the SMALLEST of the chord-error spacing, the segment-angle
    spacing and `max_edge` (review point 4): an R 3.5 m arc at 2 mm chord gives 3.9 degree steps, so the 2 degree angle
    limit decides there."""
    chord: float = .002         # metres off the true curve at most
    angle: float = 2.0          # degrees of turn per segment at most (the ride dihedral limit)
    max_edge: float = 4.0       # metres

    def step_angle(self, radius):
        """Largest segment turn in radians on a circle of `radius` (array ok): min(chord rule, angle rule)."""
        r = np.maximum(np.abs(np.asarray(radius, 'f8')), 1e-9)
        chord = 2 * np.arccos(np.clip(1 - self.chord / r, -1., 1.))
        return np.minimum(chord, math.radians(self.angle))

    def density(self, curvature, stretch=1.0):
        """Samples per metre of parameter for a curve of `curvature` (1/m, array ok), whose edges are `stretch` times
        the parameter step long (an offset sweep's outer edge): max(|k| / step_angle, stretch / (max_edge / sqrt 2)).
        Grid edges stay within max_edge / sqrt 2 so a quad's diagonal stays within max_edge."""
        k = np.abs(np.asarray(curvature, 'f8'))
        turn = np.where(k > 1e-12, k / self.step_angle(1 / np.maximum(k, 1e-12)), 0.)
        return np.maximum(turn, np.asarray(stretch, 'f8') / (self.max_edge / math.sqrt(2)))


RIDING_TESS = Tess(.002, 2.0, 4.0)
SIDE_TESS = Tess(.005, 5.0, 4.0)
GROUND_TESS = Tess(.02, 8.0, 8.0)


# ---------------------------------------------------------------- longitudinal heights
class Height:
    """A height curve y(t) along a path's arc length t, with its slope dy/dt and curvature for sampling.
    Height.const(y), Height.linear(t0, y0, t1, y1), Height.of(fn, dfn) (dfn optional: numeric if absent)."""

    def __init__(self, fn, dfn=None):
        self.fn, self.dfn = fn, dfn

    @staticmethod
    def const(y):
        return Height(lambda t: np.full(np.shape(t), float(y)), lambda t: np.zeros(np.shape(t)))

    @staticmethod
    def linear(t0, y0, t1, y1):
        k = (y1 - y0) / (t1 - t0)
        return Height(lambda t: y0 + k * (np.asarray(t, 'f8') - t0), lambda t: np.full(np.shape(t), k))

    @staticmethod
    def of(fn, dfn=None):
        return Height(fn, dfn)

    def __call__(self, t):
        return np.asarray(self.fn(np.asarray(t, 'f8')), 'f8')

    def slope(self, t):
        t = np.asarray(t, 'f8')
        if self.dfn is not None:
            return np.asarray(self.dfn(t), 'f8')
        h = 1e-4
        return (self(t + h) - self(t - h)) / (2 * h)

    def curvature(self, t):
        """Curvature of the side profile (t, y(t)), for sampling density."""
        t = np.asarray(t, 'f8'); h = 1e-3
        d2 = (self.slope(t + h) - self.slope(t - h)) / (2 * h)
        return d2 / (1 + self.slope(t) ** 2) ** 1.5


def as_height(h):
    """A float, a Height or a callable as a Height."""
    if isinstance(h, Height):
        return h
    if callable(h):
        return Height.of(h)
    return Height.const(float(h))


# ---------------------------------------------------------------- meshes
@dataclass
class Mesh:
    """Triangles with attributes. Vertices are split at creases (a crease edge has two vertices per position, one per
    side, each with its side's normal). Per vertex: V positions (n, 3) f8, N unit normals (n, 3), UV (n, 2) in texture
    tiles, AO (n,) occlusion 1 open .. 0 closed. Per face: F (m, 3) i8 counter-clockwise from the front, material (m,)
    index into MATERIALS, role (m,) index into ROLES, feature (m,) index into `features` (names), tag (m,) index into
    TAGS.
    `seams`: name -> ordered vertex indices along a boundary shared with another region (network seams, for tests)."""
    V: np.ndarray
    F: np.ndarray
    N: np.ndarray = None
    UV: np.ndarray = None
    AO: np.ndarray = None
    material: np.ndarray = None
    role: np.ndarray = None
    feature: np.ndarray = None
    features: tuple = ()
    seams: dict = field(default_factory=dict)
    tag: np.ndarray = None

    def __post_init__(self):
        self.V = np.asarray(self.V, 'f8').reshape(-1, 3)
        self.F = np.asarray(self.F, 'i8').reshape(-1, 3)
        n, m = len(self.V), len(self.F)
        self.N = vertex_normals(self.V, self.F) if self.N is None else np.asarray(self.N, 'f8').reshape(n, 3)
        self.UV = np.zeros((n, 2)) if self.UV is None else np.asarray(self.UV, 'f8').reshape(n, 2)
        self.AO = np.ones(n) if self.AO is None else np.asarray(self.AO, 'f8').reshape(n)
        for key, default in (('material', 0), ('role', 0), ('feature', 0), ('tag', 0)):
            value = getattr(self, key)
            setattr(self, key, np.full(m, default, 'i4') if value is None else
                    np.broadcast_to(np.asarray(value, 'i4'), (m,)).copy())
        self.features = tuple(self.features) or ('unnamed',)

    @staticmethod
    def part(V, F, *, material=CONCRETE, role=RIDING, feature='unnamed', N=None, UV=None, AO=None, seams=None, tag=''):
        """A mesh with one material (id), role (name), feature (name) and tag (name) on every face."""
        return Mesh(V, F, N, UV, AO, MATERIAL[material], ROLE[role], 0, (feature,), dict(seams or {}), TAG[tag])

    @staticmethod
    def empty():
        return Mesh(np.zeros((0, 3)), np.zeros((0, 3), 'i8'))

    @staticmethod
    def concat(meshes):
        """One mesh from many (no welding): vertex indices offset, feature tables merged by name, seams prefixed by
        nothing (later names win)."""
        meshes = [m for m in meshes if len(m.F) or len(m.V)]
        if not meshes:
            return Mesh.empty()
        names = []
        for m in meshes:
            names += [f for f in m.features if f not in names]
        index = {f: i for i, f in enumerate(names)}
        V, F, N, UV, AO, mat, role, feat, tag, seams, base = [], [], [], [], [], [], [], [], [], {}, 0
        for m in meshes:
            V.append(m.V); F.append(m.F + base); N.append(m.N); UV.append(m.UV); AO.append(m.AO)
            mat.append(m.material); role.append(m.role); tag.append(m.tag)
            feat.append(np.asarray([index[f] for f in m.features], 'i4')[m.feature])
            seams.update({k: np.asarray(v) + base for k, v in m.seams.items()})
            base += len(m.V)
        return Mesh(np.concatenate(V), np.concatenate(F), np.concatenate(N), np.concatenate(UV), np.concatenate(AO),
                    np.concatenate(mat), np.concatenate(role), np.concatenate(feat), tuple(names), seams,
                    np.concatenate(tag))

    def subset(self, mask):
        """The faces where `mask` (m,) holds, with only the vertices they use (seams dropped)."""
        F = self.F[mask]
        used = np.unique(F); remap = np.full(len(self.V), -1, 'i8'); remap[used] = np.arange(len(used))
        return Mesh(self.V[used], remap[F], self.N[used], self.UV[used], self.AO[used], self.material[mask],
                    self.role[mask], self.feature[mask], self.features, {}, self.tag[mask])

    def where(self, role=None, material=None):
        """The faces of a role name (or names) and/or material id."""
        mask = np.ones(len(self.F), bool)
        if role is not None:
            mask &= np.isin(self.role, [ROLE[r] for r in ([role] if isinstance(role, str) else role)])
        if material is not None:
            mask &= self.material == MATERIAL[material]
        return self.subset(mask)

    def triangles(self):
        """(m, 3, 3) corner positions."""
        return self.V[self.F]

    def face_normals(self):
        """(m, 3) unit face normals (zero for degenerate faces)."""
        t = self.triangles()
        n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
        length = np.linalg.norm(n, axis=1, keepdims=True)
        return n / np.maximum(length, 1e-300)

    def areas(self):
        t = self.triangles()
        return .5 * np.linalg.norm(np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]), axis=1)

    def welded(self, tol=1e-6):
        """(P, F): positions merged within `tol` (grid rounding) and faces on them: the topology, ignoring creases and
        UV seams. For watertight, T-junction and dihedral checks."""
        key = np.round(self.V / tol).astype('i8')
        P_key, inverse = np.unique(key, axis=0, return_inverse=True)
        inverse = inverse.ravel()
        P = np.zeros((len(P_key), 3)); np.add.at(P, inverse, self.V)
        P /= np.bincount(inverse, minlength=len(P_key))[:, None]
        return P, inverse[self.F]

    def to_arrays(self, prefix=''):
        """A dict of plain arrays for np.savez (features as a unicode array)."""
        return {prefix + 'V': self.V, prefix + 'F': self.F, prefix + 'N': self.N, prefix + 'UV': self.UV,
                prefix + 'AO': self.AO, prefix + 'material': self.material, prefix + 'role': self.role,
                prefix + 'feature': self.feature, prefix + 'features': np.asarray(self.features, 'U'),
                prefix + 'tag': self.tag}

    @staticmethod
    def from_arrays(a, prefix=''):
        return Mesh(a[prefix + 'V'], a[prefix + 'F'], a[prefix + 'N'], a[prefix + 'UV'], a[prefix + 'AO'],
                    a[prefix + 'material'], a[prefix + 'role'], a[prefix + 'feature'],
                    tuple(str(x) for x in a[prefix + 'features']), {},
                    a[prefix + 'tag'] if prefix + 'tag' in a else None)


def vertex_normals(V, F):
    """Area-weighted vertex normals (fallback when a primitive has no analytic ones); +y for an unused vertex."""
    V = np.asarray(V, 'f8'); F = np.asarray(F, 'i8')
    n = np.zeros((len(V), 3))
    if len(F):
        t = V[F]; face = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
        for i in range(3):
            np.add.at(n, F[:, i], face)
    length = np.linalg.norm(n, axis=1, keepdims=True)
    return np.where(length > 1e-12, n / np.maximum(length, 1e-12), [0., 1., 0.])


# ---------------------------------------------------------------- what a layout compiles to
@dataclass
class Rail:
    """A grind line: `points` (k, 3) native metres along the grind edge (every 0.5 m), `closed` for a loop (points not
    repeated). The exporter names them cp_lip_### in order."""
    points: np.ndarray
    closed: bool = False
    feature: str = ''

    def __post_init__(self):
        self.points = np.asarray(self.points, 'f8').reshape(-1, 3)


@dataclass
class RideLine:
    """A designed riding line: `features` in riding order, the centre `path` (k, 3) native metres, the `spawn`
    ((x, y, z), yaw degrees about +y, 0 facing native +x), the `finish` point (3,), the intended `entry_speed`
    (low, high) m/s, and `airs` [(takeoff feature, landing feature)]."""
    name: str
    features: list
    path: np.ndarray
    spawn: tuple
    finish: tuple
    entry_speed: tuple = (0., 0.)
    airs: list = field(default_factory=list)

    def __post_init__(self):
        self.path = np.asarray(self.path, 'f8').reshape(-1, 3)


@dataclass
class Park:
    """A compiled layout: one `mesh` (every face of every feature, base faces included), the `rails`, the designed
    `lines` [RideLine], and free-form `checks` (dicts: lips, landing zones, speed hints). Spawn in park.json stays the
    marked drop-in (assets/craterpark/drop-in.json)."""
    mesh: Mesh
    rails: list = field(default_factory=list)
    lines: list = field(default_factory=list)
    checks: list = field(default_factory=list)


# Re-exports: the geometry API in one import (from craterpark.v2.dsl import ...).
from .curves import Curve, Line, Arc, Polyline, Spline   # noqa: E402,F401
from .profile import Profile                              # noqa: E402,F401
