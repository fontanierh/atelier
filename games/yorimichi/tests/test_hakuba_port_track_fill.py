"""The railway port fills each track polygon with triangles wound as the polygon, covering it once and no more.

A fan over a concave outline, a tunnel portal's wall around its arch or a viaduct spandrel over its arch, once folded
across the opening with triangles wound both ways: the arch was closed and drawn inside out.
"""
import math
import sys
from pathlib import Path

import numpy as np

YORIMICHI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(YORIMICHI / 'hakuba_port'))
sys.path.insert(0, str(YORIMICHI / 'world'))
import transport  # noqa: E402
from train import track  # noqa: E402


def area(points):
    """The signed area of a 2D polygon, positive counter-clockwise."""
    x, y = np.asarray(points, float).T
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def covers(triangle, point):
    """Whether the 2D triangle contains `point` strictly inside."""
    a, b, c = triangle
    sides = [(q[0] - p[0]) * (point[1] - p[1]) - (q[1] - p[1]) * (point[0] - p[0]) for p, q in ((a, b), (b, c), (c, a))]
    return all(s > 1e-9 for s in sides) or all(s < -1e-9 for s in sides)


def assert_filled(points, triangles, opening=None):
    """Every triangle wound as the polygon, their areas summing to its own (so none overlaps), and none over
    `opening`, a point outside the polygon."""
    points = np.asarray(points, float)
    whole = area(points)
    parts = [area(points[list(t)]) for t in triangles]
    assert all(math.copysign(1.0, p) == math.copysign(1.0, whole) and abs(p) > 0 for p in parts)
    assert math.isclose(sum(parts), whole, rel_tol=1e-9)
    if opening is not None:
        assert not any(covers(points[list(t)], opening) for t in triangles)


def portal_outline():
    """The portal's face wall, as `track.portal_mesh` outlines it: the wall around the tunnel's horseshoe opening."""
    return [(-6.5, track.TUNNEL_BASE), *track.horseshoe(12), (6.5, track.TUNNEL_BASE), (6.5, 9.0), (-6.5, 9.0)]


def spandrel_outline():
    """A viaduct span's spandrel, as `track.viaduct_mesh` outlines it: the deck line on top, the arch underneath."""
    arch = [(10.0 - 9.0 * math.cos(t), 2.0 + 9.0 * math.sin(t)) for t in np.linspace(0.05, math.pi - 0.05, 16)]
    return [(0.0, 2.0), *arch, (20.0, 2.0), (20.0, 12.5), (0.0, 12.0)]


def test_concave_outlines_keep_their_opening():
    for outline, opening in ((portal_outline(), (0.0, 2.0)), (spandrel_outline(), (10.0, 6.0))):
        for points in (outline, outline[::-1]):
            assert_filled(points, transport.fill(points), opening)
        # The fan the port once used folds over the opening.
        fan = [(0, k, k + 1) for k in range(1, len(outline) - 1)]
        assert any(covers(np.asarray(outline)[list(t)], opening) for t in fan)


def test_convex_polygons_keep_their_fan():
    square = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    assert transport.fill(square) == [(0, 1, 2), (0, 2, 3)]


def test_portal_triangles_face_out():
    mesh = track.portal_mesh(0)
    looks = [(name, [0.5, 0.5, 0.5], None, 1.0) for name in sorted(set(mesh.mats))]
    position, normal, _, triangles, _, _ = transport.track_corners([mesh], looks)
    corners = position[triangles]
    winding = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    # Each triangle is wound to face along its polygon's normal; none is degenerate or turned inside out.
    facing = np.einsum('ij,ij->i', winding, normal[triangles[:, 0]])
    assert (facing > 1e-9).all()
    # And together they cover each face once: the triangles' area is the polygons' own.
    polygons = sum(np.linalg.norm(np.cross(r - r.mean(0), np.roll(r, -1, 0) - r.mean(0)).sum(0)) / 2
                   for r in (np.asarray(mesh.verts, float)[list(f)] for f in mesh.faces))
    assert math.isclose(float(np.linalg.norm(winding, axis=1).sum() / 2), polygons, rel_tol=1e-6)
