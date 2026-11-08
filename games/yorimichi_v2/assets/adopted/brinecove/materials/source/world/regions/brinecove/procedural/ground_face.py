"""One Brinecove constructor or shared geometry primitive; no sibling generation."""
from brinecove import rocks
from brinecove.geom import _surface_scale as surface_scale


def ground_face(b, a, bb, c, d, mat, gx, gy, sl):
    """Two ground triangles. They project straight down: per-face box projection flips axis between neighbouring
    triangles on 45-degree slopes, which painted the hills as a diamond checkerboard. Cliffs instead project onto
    the vertical plane along their smoothed contour, which turns slowly enough to stay continuous; straight down,
    a cliff's texture smeared into vertical streaks."""
    k = 1.0 / max(0.05, surface_scale(mat))
    if sl > 1.1:
        ux, uy, _ = rocks.uphill(gx, gy, 14.0)
        uv = lambda p: ((p[0] * -uy + p[1] * ux) * k, p[2] * k)  # noqa: E731
    else:
        uv = lambda p: (p[0] * k, p[1] * k)  # noqa: E731
    b.face((a, bb, c), mat, [uv(a), uv(bb), uv(c)])
    b.face((a, c, d), mat, [uv(a), uv(c), uv(d)])
