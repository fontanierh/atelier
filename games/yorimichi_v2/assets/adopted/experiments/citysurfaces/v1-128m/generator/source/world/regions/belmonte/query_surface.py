"""Canonical upward triangle queries, independent of geometry construction and export."""
import numpy as np


class Surface:
    """Upward triangle intersections, indexed in 32 m cells for map and planting."""
    CELL = 32.

    def __init__(self, faces, values=None):
        faces = np.asarray(faces, float)
        a, b, c = faces[:, 0], faces[:, 1], faces[:, 2]
        normal = np.cross(b - a, c - a)
        keep = np.abs(normal[:, 2]) > 1e-8
        self.faces = faces[keep]
        self.values = None if values is None else np.asarray(values, float)[keep]
        self.bins = {}
        lo = np.floor(self.faces[:, :, :2].min(1) / self.CELL).astype(int)
        hi = np.floor(self.faces[:, :, :2].max(1) / self.CELL).astype(int)
        for index, (low, high) in enumerate(zip(lo, hi)):
            for x in range(low[0], high[0] + 1):
                for y in range(low[1], high[1] + 1):
                    self.bins.setdefault((x, y), []).append(index)

    def height(self, x, y):
        return self.sample(x, y)

    def colour(self, x, y):
        assert self.values is not None
        return self.sample(x, y, self.values)

    def sample(self, x, y, values=None):
        x, y = np.broadcast_arrays(np.asarray(x, float), np.asarray(y, float))
        query = np.stack([x.ravel(), y.ravel()], 1)
        cells = np.floor(query / self.CELL).astype(int)
        result = np.full((len(query), 3) if values is not None else len(query), np.nan)
        keys, inverse = np.unique(cells, axis=0, return_inverse=True)
        for group, key in enumerate(keys):
            indices = self.bins.get(tuple(key))
            if not indices:
                continue
            selected = np.flatnonzero(inverse == group)
            a, b, c = np.moveaxis(self.faces[indices], 1, 0)
            e, f = b[:, :2] - a[:, :2], c[:, :2] - a[:, :2]
            p = query[selected, None, :] - a[None, :, :2]
            determinant = e[:, 0] * f[:, 1] - e[:, 1] * f[:, 0]
            u = (p[:, :, 0] * f[:, 1] - p[:, :, 1] * f[:, 0]) / determinant
            v = (e[:, 0] * p[:, :, 1] - e[:, 1] * p[:, :, 0]) / determinant
            covered = (u >= -1e-7) & (v >= -1e-7) & (u + v <= 1 + 1e-7)
            z = a[:, 2] + u * (b[:, 2] - a[:, 2]) + v * (c[:, 2] - a[:, 2])
            best = np.max(np.where(covered, z, -np.inf), axis=1)
            if values is None:
                result[selected] = np.where(np.isfinite(best), best, np.nan)
            else:
                chosen = np.argmax(np.where(covered, z, -np.inf), axis=1)
                rows = np.arange(len(selected))
                barycentric = np.stack([1-u[rows, chosen]-v[rows, chosen], u[rows, chosen], v[rows, chosen]], 1)
                colour = (values[np.asarray(indices)[chosen]] * barycentric[:, :, None]).sum(1)
                result[selected] = np.where(np.isfinite(best)[:, None], colour, np.nan)
        return result.reshape(x.shape + ((3,) if values is not None else ()))

