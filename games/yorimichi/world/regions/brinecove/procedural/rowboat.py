"""One Brinecove constructor or shared geometry primitive; no sibling generation."""
from brinecove.kit import local


def rowboat(b, x, y, z, yaw, scale=1.0):
    # A simple clinker rowboat: two side strips, a floor and a transom.
    def T(lx, ly, lz):
        return local(x, y, yaw, lx * scale, ly * scale) + (z + lz * scale,)
    for side in (-1, 1):
        b.panel(T(side * 1.4, -4.2, 1.2), T(side * 1.4, 4.2, 1.4),
                T(side * 1.0, 4.8, 0.4), T(side * 1.0, -4.8, 0.4), 'wood', thick=0.04)
        b.panel(T(side * 1.4, -4.2, 1.2), T(side * 1.4, 4.2, 1.4),
                T(side * 1.45, 4.2, 1.8), T(side * 1.45, -4.2, 1.6), 'wood_dark', thick=0.04)
    b.box((*local(x, y, yaw, 0, 0), z + 0.7 * scale), (2.0 * scale, 8.0 * scale, 0.2 * scale), 'wood_light', yaw)
    b.panel(T(-1.4, -4.2, 1.2), T(1.4, -4.2, 1.2), T(1.0, -4.8, 0.4), T(-1.0, -4.8, 0.4), 'wood', thick=0.04)
    b.beam(T(-1.6, 0, 1.5), T(1.6, 0, 1.5), 0.12, 'wood_dark')
    b.beam(T(0, -3.0, 1.1), T(0, 3.0, 1.3), 0.08, 'wood_dark')
