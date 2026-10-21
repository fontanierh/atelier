"""Bound complete mesh faces in fixed spatial cells without moving or retriangulating them."""
import math


def face_groups(vertices, faces, bounds, *, triangle_limit, max_depth=16, locations=None):
    """@cc [owner:fontanierh,label:correctness] bounded-spatial-face-partition
    Every input face MUST appear exactly once, intact, in the returned index groups.
    Every group MUST fit triangle_limit under fan triangle accounting. Coordinates and
    per-face/corner attributes MUST remain owned by the caller and MUST NOT be rewritten.
    Optional locations MUST completely bind the caller's existing face-to-cell assignments.
    Spatial suffixes MUST derive from fixed supplied bounds, never the observed mesh extent.
    Coincident faces that cannot fit a bounded cell MUST refuse rather than publish a monolith.
    """
    if type(triangle_limit) is not int or triangle_limit < 1 or type(max_depth) is not int or not 0 <= max_depth <= 24:
        raise ValueError('Invalid spatial mesh budget')
    if len(bounds) != 4 or not all(math.isfinite(value) for value in bounds):
        raise ValueError('Spatial mesh bounds must be finite')
    x0, y0, x1, y1 = bounds
    if x1 <= x0 or y1 <= y0:
        raise ValueError('Spatial mesh bounds must have positive area')
    if locations is not None and len(locations) != len(faces):
        raise ValueError('Spatial assignment locations must cover every face')
    centers, weights = [], []
    for face_index, face in enumerate(faces):
        if len(face) < 3 or len(face) - 2 > triangle_limit:
            raise ValueError('A complete face does not fit the spatial mesh budget')
        if any(type(index) is not int or not 0 <= index < len(vertices) for index in face):
            raise ValueError('Invalid spatial mesh vertex index')
        points = [vertices[index] for index in face]
        if any(len(point) != 3 or not all(math.isfinite(value) for value in point) for point in points):
            raise ValueError('Spatial mesh coordinates must be finite three-vectors')
        x = math.fsum(point[0] / len(points) for point in points)
        y = math.fsum(point[1] / len(points) for point in points)
        if locations is not None:
            location = locations[face_index]
            if len(location) != 2 or not all(math.isfinite(value) for value in location):
                raise ValueError('Spatial assignment locations must be finite pairs')
            x, y = location
        if not x0 <= x <= x1 or not y0 <= y <= y1:
            raise ValueError('Spatial face center lies outside its declared cell')
        centers.append((x, y))
        weights.append(len(face) - 2)
    result = []

    def visit(indices, cell, suffix):
        if sum(weights[index] for index in indices) <= triangle_limit:
            if indices:
                result.append((suffix, tuple(indices)))
            return
        if len(suffix) >= max_depth:
            raise ValueError('Coincident geometry exceeds the bounded spatial mesh budget')
        a, b, c, d = cell
        mx, my = (a + c) / 2, (b + d) / 2
        buckets = [[] for _ in range(4)]
        for index in indices:
            x, y = centers[index]
            buckets[(x >= mx) + 2 * (y >= my)].append(index)
        cells = ((a, b, mx, my), (mx, b, c, my), (a, my, mx, d), (mx, my, c, d))
        for quadrant, (bucket, subcell) in enumerate(zip(buckets, cells)):
            if bucket:
                visit(bucket, subcell, suffix + str(quadrant))

    visit(list(range(len(faces))), tuple(bounds), '')
    return result
