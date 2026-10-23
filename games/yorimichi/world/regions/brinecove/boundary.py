"""Final coastal boundary extraction, independent from town geometry constructors."""
import numpy as np
from terrain_product import load
from brinecove import region as R


def weld(vertices, triangles, decimals=4):
    """One vertex per position. The FarHills final product keeps each tile's corners separate, so its hole rim
    would list coincident points and the zipper below would emit zero-length triangles."""
    vertices, triangles = np.asarray(vertices), np.asarray(triangles)
    _, first, inverse = np.unique(vertices.round(decimals), axis=0, return_index=True, return_inverse=True)
    return vertices[first], inverse.reshape(-1)[triangles]


def rim(path):
    """FarHills' hole boundary from its final product (world.farhills)."""
    mesh = load(path, owner='FarHills', stage='final', city=True)
    vertices, triangles = np.asarray(mesh.vertices), np.asarray(mesh.triangles())
    vertices, triangles = weld(vertices, triangles)
    x0, y0, x1, y1 = R.OUTER_WORLD
    near = ((np.abs(vertices[:, 0] - x0) < .05) | (np.abs(vertices[:, 0] - x1) < .05)
            | (np.abs(vertices[:, 1] - y0) < .05) | (np.abs(vertices[:, 1] - y1) < .05))
    near &= (vertices[:, 0] > x0 - .05) & (vertices[:, 0] < x1 + .05) & (vertices[:, 1] > y0 - .05) & (vertices[:, 1] < y1 + .05)
    keep = near[triangles].sum(1) >= 2
    used = np.unique(triangles[keep])
    remap = {int(v): i for i, v in enumerate(used)}
    local = [[remap[int(v)] for v in t] for t in triangles[keep]]
    return R.rim_from_mesh(vertices[used].tolist(), local)

