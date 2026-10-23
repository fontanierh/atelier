"""One independently consumed logical asset constructor."""
import math
import random
from mathutils import Vector
from swordcamp.mesh import ProcMesh, UV_BAMBOO, UV_BARK, UV_CAST_IRON_TILE, UV_COBBLE, UV_EMBER, UV_GREEN_BAMBOO, UV_IRON, UV_LANTERN, UV_ROPE, UV_STONE_TILE

def build_firepit(m: ProcMesh, origin=(0, 0, 0)):
    old = m.push(origin)
    rng = random.Random(108)
    n_stones = 14
    for i in range(n_stones):
        a = 2 * math.pi * i / n_stones
        r = 0.78 + rng.uniform(-0.04, 0.04)
        sx, sy, sz = 0.34 + rng.uniform(-0.04, 0.05), 0.28 + rng.uniform(-0.03, 0.04), 0.24 + rng.uniform(-0.03, 0.05)
        m.box((r * math.cos(a), r * math.sin(a), sz * 0.45), (sx, sy, sz), UV_COBBLE if i % 2 == 0 else UV_STONE_TILE,
              bevel=0.06, rot=(rng.uniform(-6, 6), rng.uniform(-6, 6), math.degrees(a) + rng.uniform(-12, 12)))
    m.tube((0, 0, 0.0), (0, 0, 0.14), 0.62, 0.28, UV_EMBER, segs=16)
    m.tube((0, 0, 0.14), (0, 0, 0.24), 0.28, 0.08, UV_LANTERN, segs=12)
    for i in range(6):
        a = 2 * math.pi * i / 6 + 0.25
        p0 = (0.48 * math.cos(a), 0.48 * math.sin(a), 0.08)
        p1 = (0.10 * math.cos(a + 0.4), 0.10 * math.sin(a + 0.4), 0.28)
        m.tube(p0, p1, 0.058, 0.048, UV_BARK if i % 2 == 0 else UV_EMBER, segs=8)
    apex = Vector((0, 0, 1.62))
    for i in range(3):
        a = 2 * math.pi * i / 3 + 0.52
        base = Vector((0.82 * math.cos(a), 0.82 * math.sin(a), 0.04))
        top = apex + Vector((-0.09 * math.cos(a), -0.09 * math.sin(a), 0.18))
        m.tube(base, top, 0.042, 0.032, UV_GREEN_BAMBOO, segs=10)
        for f in (0.2, 0.4, 0.6, 0.8):
            pt = base.lerp(top, f)
            m.torus(tuple(pt), 0.040, 0.006, UV_BAMBOO, n_maj=10, n_min=6)
    for k in range(6):
        m.torus((0, 0, 1.50 + k * 0.032), 0.085 - k * 0.003, 0.022, UV_ROPE, n_maj=14, n_min=6)
    for k in range(5):
        m.torus((0, 0, 1.44 - k * 0.055), 0.026, 0.008, UV_IRON, n_maj=10, n_min=6, axis='X' if k % 2 == 0 else 'Y')
    kz = 0.72
    prof = [(0.0, 0.11), (0.04, 0.21), (0.13, 0.24), (0.22, 0.19), (0.26, 0.12), (0.28, 0.13)]
    for (z0, r0), (z1, r1) in zip(prof[:-1], prof[1:]):
        m.tube((0, 0, kz + z0), (0, 0, kz + z1), r0, r1, UV_CAST_IRON_TILE, segs=18, cap=False)
    m.tube((0, 0, kz + 0.28), (0, 0, kz + 0.31), 0.11, 0.02, UV_IRON, segs=14)
    m.tube((0, 0, kz + 0.31), (0, 0, kz + 0.34), 0.028, 0.022, UV_IRON, segs=10)
    m.tube((0.18, 0, kz + 0.15), (0.29, 0, kz + 0.25), 0.036, 0.022, UV_IRON, segs=10)
    m.torus((0, 0, kz + 0.28), 0.16, 0.014, UV_IRON, n_maj=14, n_min=6, axis='Y', arc=math.pi)
    m.add_collider((0, 0, 0.55), (1.75, 1.75, 1.1))
    m.xf = old
