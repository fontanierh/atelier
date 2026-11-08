"""Vertical intersections with one explicitly owned, ordered triangle product."""
from dataclasses import dataclass
import math

import numpy as np


def _readonly(values):
    values = np.asarray(values)
    values.flags.writeable = False
    return values


@dataclass(frozen=True)
class Hits:
    owner: str
    stage: str
    query_shape: tuple
    query_ids: np.ndarray
    face_ids: np.ndarray
    barycentric: np.ndarray
    height: np.ndarray
    normal: np.ndarray


@dataclass(frozen=True)
class Upper:
    owner: str
    stage: str
    covered: np.ndarray
    face_ids: np.ndarray
    barycentric: np.ndarray
    height: np.ndarray
    normal: np.ndarray


class Surface:
    """@cc [owner:fontanierh,label:correctness] owned-triangle-query
    Query the supplied product's existing fan triangles without reshaping,
    welding, carving, changing winding or choosing between terrain owners.
    Face IDs MUST retain product triangle order. Intersections report every
    covered nonvertical face; holes MUST remain missing. Only explicit upper()
    selection chooses the highest intersection within this one owner/stage,
    with the first face ID breaking exact height ties. Returned normals are
    geometric unit normals in the original winding, not appearance normals.
    Product freshness MUST be established by the caller's verified build read;
    construction from arrays alone does not certify their source revision.
    """
    MAX_PAIRS = 262144
    EDGE_EPSILON = 1e-9

    def __init__(self, mesh, *, owner, stage, cell=32.):
        if not isinstance(owner, str) or not owner.strip() or stage not in ('natural', 'final'):
            raise ValueError('Triangle queries require an explicit owner and stage')
        if type(cell) not in (int, float) or not math.isfinite(cell) or cell <= 0:
            raise ValueError('Triangle query cell width must be finite and positive')
        self.owner, self.stage, self.cell = owner, stage, float(cell)
        self.triangles = mesh.vertices[mesh.triangles()]
        a, b, c = np.moveaxis(self.triangles, 1, 0)
        cross = np.cross(a-c, b-c)
        if not np.isfinite(cross).all():
            raise ValueError('Triangle query normals must be finite')
        scale = np.max(np.abs(cross), axis=1)
        scaled = np.divide(cross, scale[:, None], out=np.zeros_like(cross), where=scale[:, None] != 0)
        lengths = np.linalg.norm(scaled, axis=1)
        self.normals = np.divide(scaled, lengths[:, None], out=np.zeros_like(scaled), where=lengths[:, None] != 0)
        # Keep IDs in the complete product; vertical/zero-area faces have no
        # single-valued vertical intersection and are never invented as ground.
        usable = np.flatnonzero(cross[:, 2] != 0)
        self.bins = {}
        if len(usable):
            xy = self.triangles[usable, :, :2]
            low, high = xy.min(1), xy.max(1)
            margin = 2*self.EDGE_EPSILON*(high-low)
            low, high = low-margin, high+margin
            self.bounds = low.min(0), high.max(0)
            for face, lo, hi in zip(usable, low, high):
                for x in range(math.floor(lo[0]/cell), math.floor(hi[0]/cell)+1):
                    for y in range(math.floor(lo[1]/cell), math.floor(hi[1]/cell)+1):
                        self.bins.setdefault((x, y), []).append(face)
            self.bins = {key: _readonly(np.asarray(ids, dtype=np.int64)) for key, ids in self.bins.items()}
        else:
            self.bounds = None
        _readonly(self.triangles)
        _readonly(self.normals)

    def intersections(self, x, y):
        x, y = np.broadcast_arrays(np.asarray(x, float), np.asarray(y, float))
        if not np.isfinite(x).all() or not np.isfinite(y).all():
            raise ValueError('Triangle query coordinates must be finite')
        points = np.stack([x.ravel(), y.ravel()], 1)
        groups = []
        if self.bounds is not None:
            lo, hi = self.bounds
            rows = np.flatnonzero(np.all((points >= lo) & (points <= hi), axis=1))
            if len(rows):
                cells = np.floor(points[rows]/self.cell)
                if np.all((cells >= -(1 << 63)) & (cells < (1 << 63))):
                    keys, inverse, counts = np.unique(cells.astype(np.int64), axis=0,
                                                     return_inverse=True, return_counts=True)
                    order = np.argsort(inverse, kind='stable')
                    offsets = np.r_[0, np.cumsum(counts)]
                    cell_groups = ((tuple(key), rows[order[offsets[g]:offsets[g+1]]])
                                   for g, key in enumerate(keys))
                else:
                    # Construction uses Python integer keys. Keep those exact
                    # keys for distant finite coordinates rather than wrapping
                    # their cell IDs through a narrower NumPy integer type.
                    distant = {}
                    for row, cell in zip(rows, cells):
                        distant.setdefault(tuple(int(value) for value in cell), []).append(row)
                    cell_groups = ((key, np.asarray(ids, dtype=np.int64)) for key, ids in distant.items())
                for key, selected in cell_groups:
                    faces = self.bins.get(key)
                    if faces is None:
                        continue
                    a, b, c = np.moveaxis(self.triangles[faces], 1, 0)
                    den = (b[:, 1]-c[:, 1])*(a[:, 0]-c[:, 0]) + (c[:, 0]-b[:, 0])*(a[:, 1]-c[:, 1])
                    chunk = max(1, self.MAX_PAIRS//len(faces))
                    for start in range(0, len(selected), chunk):
                        query = selected[start:start+chunk]
                        px, py = points[query].T
                        u = ((b[:, 1]-c[:, 1])[:, None]*(px-c[:, 0, None]) +
                             (c[:, 0]-b[:, 0])[:, None]*(py-c[:, 1, None]))/den[:, None]
                        v = ((c[:, 1]-a[:, 1])[:, None]*(px-c[:, 0, None]) +
                             (a[:, 0]-c[:, 0])[:, None]*(py-c[:, 1, None]))/den[:, None]
                        on = (u >= -self.EDGE_EPSILON) & (v >= -self.EDGE_EPSILON) & (u+v <= 1+self.EDGE_EPSILON)
                        face, q = np.nonzero(on)
                        if len(q):
                            bary = np.stack([u[face, q], v[face, q], 1-u[face, q]-v[face, q]], 1)
                            height = u[face, q]*a[face, 2] + v[face, q]*b[face, 2] + bary[:, 2]*c[face, 2]
                            groups.append((query[q], faces[face], bary, height, self.normals[faces[face]]))
        if groups:
            values = [np.concatenate([row[k] for row in groups]) for k in range(5)]
            order = np.lexsort((values[1], values[0]))
            values = [value[order] for value in values]
        else:
            values = [np.empty(0, np.int64), np.empty(0, np.int64), np.empty((0, 3)), np.empty(0), np.empty((0, 3))]
        return Hits(self.owner, self.stage, x.shape, *map(_readonly, values))

    def upper(self, x, y, *, require=True):
        """Explicit top intersection within this owner; missing coverage fails by default."""
        hits = self.intersections(x, y)
        size = math.prod(hits.query_shape)
        covered = np.zeros(size, bool)
        faces = np.full(size, -1, dtype=np.int64)
        bary, normal = np.full((size, 3), np.nan), np.full((size, 3), np.nan)
        height = np.full(size, np.nan)
        if len(hits.query_ids):
            starts = np.r_[0, np.flatnonzero(np.diff(hits.query_ids))+1]
            maxima = np.maximum.reduceat(hits.height, starts)
            counts = np.diff(np.r_[starts, len(hits.height)])
            winners = hits.height == np.repeat(maxima, counts)
            best = np.minimum.reduceat(np.where(winners, np.arange(len(winners)), len(winners)), starts)
            rows = hits.query_ids[best]
            covered[rows] = True
            faces[rows], bary[rows], height[rows], normal[rows] = (
                hits.face_ids[best], hits.barycentric[best], hits.height[best], hits.normal[best])
        if require and not covered.all():
            missing = np.flatnonzero(~covered)
            raise ValueError(f'{self.owner}/{self.stage} has no triangle support for {len(missing)} queries; '
                             f'first query IDs {missing[:8].tolist()}')
        shape = hits.query_shape
        values = [covered.reshape(shape), faces.reshape(shape), bary.reshape(shape+(3,)),
                  height.reshape(shape), normal.reshape(shape+(3,))]
        return Upper(self.owner, self.stage, *map(_readonly, values))
