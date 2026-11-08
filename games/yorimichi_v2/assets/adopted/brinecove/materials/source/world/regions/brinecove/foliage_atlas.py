"""Shared leaf atlas coordinates, independent of layout and placement."""

LEAF_CELLS = ((0.02, 0.02, 0.48, 0.48), (0.52, 0.02, 0.98, 0.48),
              (0.02, 0.52, 0.48, 0.98), (0.52, 0.52, 0.98, 0.98))
PALM_CELLS = (2, 3)


def cell_uvs(cell):
    u0, v0, u1, v1 = LEAF_CELLS[cell]
    return ((u0, v0), (u1, v0), (u1, v1), (u0, v1))
