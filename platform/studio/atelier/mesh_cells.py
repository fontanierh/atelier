"""Bound floor-grid cells using the shared complete-face subdivision mechanism."""
import math

from .mesh_partition import face_groups

def cell_face_groups(vertices, faces, cell_size, *, triangle_limit, locations=None):
    """@cc [owner:fontanierh,label:correctness] bounded-world-mesh-cells
    Every complete source face MUST belong to exactly one returned cell/piece.
    Existing floor-grid cell names MUST remain unchanged below the triangle
    budget. Over-budget cells MUST use the same bounded subdivision mechanism,
    without changing positions, winding or caller-owned corner attributes.
    """
    if type(cell_size) not in (int, float) or not math.isfinite(cell_size) or cell_size <= 0:
        raise ValueError('Invalid world mesh cell size')
    if type(triangle_limit) is not int or triangle_limit < 1:
        raise ValueError('Invalid world mesh triangle budget')
    if locations is not None and len(locations) != len(faces):
        raise ValueError('Spatial assignment locations must cover every face')
    buckets, centers = {}, []
    for index, face in enumerate(faces):
        if len(face) < 3 or any(type(i) is not int or not 0 <= i < len(vertices) for i in face):
            raise ValueError('Invalid world mesh face')
        points = [vertices[i] for i in face]
        if any(len(p) != 3 or not all(math.isfinite(v) for v in p) for p in points):
            raise ValueError('Invalid world mesh position')
        location = locations[index] if locations is not None else tuple(
            math.fsum(p[axis] / len(points) for p in points) for axis in (0, 1))
        if len(location) != 2 or not all(math.isfinite(v) for v in location):
            raise ValueError('Invalid world mesh face center')
        centers.append(location)
        key = tuple(math.floor(v / cell_size) for v in location)
        buckets.setdefault(key, []).append(index)
    result = []
    for (x, y), indices in sorted(buckets.items()):
        bounds = (x * cell_size, y * cell_size, (x + 1) * cell_size, (y + 1) * cell_size)
        groups = face_groups(vertices, [faces[i] for i in indices], bounds, triangle_limit=triangle_limit,
                             locations=[centers[i] for i in indices])
        result.extend((x, y, suffix, tuple(indices[i] for i in members)) for suffix, members in groups)
    return result
