"""Island foliage shapes; specifications and LOD policy live separately from prop builders."""
import math
import random
from mathutils import Vector
import asset_mesh as A


def tree_maple(name, seed, height=6.5, spread=6.0):
    from forest_trees import tree
    return tree(name, 'maple', seed, height, spread, 'LeafMaple', library=A)


def tree_ginkgo(name, seed, height=9.0):
    from forest_trees import tree
    return tree(name, 'ginkgo', seed, height, 4.2, 'LeafGinkgo', library=A)


def bush_flower(name, seed, r=1.1):
    rng = random.Random(seed); M = A.Mesh(name)
    A.leaf_canopy(M, (0, 0, r * 0.7), (r, r, r * 0.7), 120, 0.55, A.MATS["Flower"], rng, normal_center=(0, 0, r * 0.25), vertical_bias=0.35)
    return M.build()


def tree_broad(name, seed, height=8.0, spread=4.2):
    from forest_trees import tree
    return tree(name, 'oak', seed, height, spread, 'LeafSmall', library=A)


def tree_pine(name, seed, height=14.0):
    from forest_trees import tree
    return tree(name, 'pine', seed, height, 6., 'LeafPine', library=A)


def tree_cedar(name, seed, height=16.0):
    from forest_trees import tree
    return tree(name, 'cedar', seed, height, 5., 'LeafCedar', library=A)


def bush(name, seed, m_name, r=1.4):
    """small-leaf bush mass (green or ochre), dark inside like the trees"""
    rng = random.Random(seed); M = A.Mesh(name)
    leaf = A.MATS[{"LeafBroad": "LeafSmall", "LeafOchre": "LeafOchreSmall"}.get(m_name, m_name)]
    A.leaf_canopy(M, (0, 0, r * 0.65), (r, r, r * 0.7), int(110 * r), 0.48, leaf, rng, normal_center=(0, 0, r * 0.2), vertical_bias=0.35)
    return M.build()


def grass_tuft(name, seed, lod=0):
    """Eight curved ribbons: 40 triangles, no intersecting rectangular cards."""
    rng = random.Random(seed); M = A.Mesh(name)
    # Most of each clump is green, with a few muted straw blades.
    for k in range(8):
        angle = k * math.tau / 8 + rng.uniform(-.4, .4)
        direction = Vector((math.cos(angle), math.sin(angle), 0))
        sideways = Vector((-math.sin(angle), math.cos(angle), 0))
        root = direction * rng.uniform(.06, .20) + Vector((0, 0, -.025))
        height, width, curl = rng.uniform(.32, .53), rng.uniform(.055, .095), rng.uniform(.14, .27)
        cell = rng.choices(range(4), weights=[4, 4, 1, 1])[0]
        u0, v0 = cell % 2 * .5, .5 - cell // 2 * .5
        levels = []
        for t in ((0., .48, .82), (0., .58), (0.,))[lod]:
            centre = root + direction * curl * t * t + Vector((0, 0, height * t))
            half = sideways * width * (1 - t ** 1.7) * .5
            levels.append((centre - half, centre + half, t))
        def uv(u, t): return (u0 + .5 * (.02 + .96 * u), v0 + .5 * (.02 + .96 * t))
        for (a, b, t), (d, c, q) in zip(levels, levels[1:]):
            M.quad([a, b, c, d], A.MATS['Grass'], [uv(0,t), uv(1,t), uv(1,q), uv(0,q)],
                   normal=(0,0,1), col=[(t*t, .6+.4*t)]*2 + [(q*q, .6+.4*q)]*2)
        a, b, t = levels[-1]
        tip = root + direction * curl + Vector((0, 0, height))
        M.quad([a, b, tip], A.MATS['Grass'], [uv(0,t),uv(1,t),uv(.5,1)],
               normal=(0,0,1), col=[(t*t,.6+.4*t)]*2+[(1.,1.)])
    return M.build()
