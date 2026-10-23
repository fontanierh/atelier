"""Selected authored canopy constructor, independent of export or species membership."""
import math, random
import numpy as np
from mathutils import Vector
import asset_mesh as A
SLOT = {'LeafMaple': 'LeafMaple', 'LeafCrimson': 'LeafMaple', 'LeafAmber': 'LeafMaple', 'LeafGinkgo': 'LeafMaple'}

def canopy_tree(name, seed, leaf, H, spread, lobes, cards):
    """A straight trunk forking at 55% of the height into a crown of one top lobe and a ring of side lobes."""
    rng = random.Random(seed); M = A.Mesh(name); bark = A.MATS['Bark']; leafm = A.MATS[SLOT[leaf]]
    lean = Vector((rng.uniform(-.5, .5), rng.uniform(-.5, .5), 0))
    mid = lean*.35+Vector((0, 0, H*.3)); fork = lean+Vector((0, 0, H*.55))
    M.tube((0, 0, -.3), mid, .46, .34, bark, n=10, uvscale=(1, .35))
    M.tube(mid, fork, .34, .24, bark, n=10, uvscale=(1, .35))
    centres = [(fork+Vector((0, 0, H*.25)), (spread*.3, spread*.3, H*.15))]
    a0 = rng.uniform(0, 2*math.pi)
    for i in range(lobes):
        a = a0+2*math.pi*i/lobes+rng.uniform(-.35, .35); r = spread*rng.uniform(.19, .25)
        c = lean+Vector((math.cos(a)*r, math.sin(a)*r, H*rng.uniform(.64, .74)))
        centres.append((c, (spread*rng.uniform(.24, .28), spread*rng.uniform(.24, .28), H*rng.uniform(.12, .15))))
    for c, _ in centres:
        end = fork+(c-fork)*.8
        M.tube(fork-Vector((0, 0, .4)), end, .17, .05, bark, n=6, uvscale=(1, .5))
        side = fork+(c-fork)*.45; off = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), .6)).normalized()*1.4
        M.tube(side, side+off, .07, .02, bark, n=5)
    vol = [r[0]*r[1]*r[2] for _, r in centres]; total = sum(vol)
    nc = lean+Vector((0, 0, H*.62))
    for (c, r), v in zip(centres, vol):
        A.leaf_canopy(M, c, r, int(cards*v/total), .8, leafm, rng, normal_center=nc, vertical_bias=.35)
    ob = M.build()
    leaf_i = ob.data.materials.find(SLOT[leaf])
    pts = np.array([ob.data.vertices[v].co[:] for p in ob.data.polygons if p.material_index == leaf_i for v in p.vertices])
    dims = dict(trunk_top=round(fork.z, 2), crown_lo=round(float(np.percentile(pts[:, 2], 3)), 2),
                crown_hi=round(float(pts[:, 2].max()), 2),
                radius=round(float(np.percentile(np.hypot(pts[:, 0]-lean.x, pts[:, 1]-lean.y), 92)), 2),
                leaf=leaf, slot=SLOT[leaf], triangles=sum(len(p.vertices)-2 for p in ob.data.polygons))
    return ob, dims

