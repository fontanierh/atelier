"""Ordered terrain geometry products, independent of scenery and DCC objects."""
from dataclasses import dataclass
from pathlib import Path
import io
import zipfile

from atelier.atomic_files import managed_temporary_parent

import numpy as np


@dataclass(frozen=True)
class Mesh:
    """Explicit polygon order plus its existing first-corner fan triangles."""
    vertices: np.ndarray
    indices: np.ndarray
    offsets: np.ndarray

    def __post_init__(self):
        v = np.array(self.vertices, dtype='<f8', copy=True)
        raw_indices, raw_offsets = np.asarray(self.indices), np.asarray(self.offsets)
        if raw_indices.dtype.kind not in 'iu' or raw_offsets.dtype.kind not in 'iu':
            raise ValueError('Terrain topology must contain integer indices')
        if v.ndim != 2 or v.shape[1] != 3 or not np.isfinite(v).all():
            raise ValueError('Terrain vertices must be finite N by 3 world metres')
        if raw_indices.ndim != 1 or raw_offsets.ndim != 1 or not len(raw_offsets):
            raise ValueError('Terrain polygon indices and offsets must be vectors')
        if raw_indices.size and (raw_indices.min() < 0 or raw_indices.max() >= len(v)):
            raise ValueError('Terrain polygon index outside vertex array')
        if raw_offsets[0] != 0 or raw_offsets[-1] != len(raw_indices):
            raise ValueError('Terrain polygon offsets do not cover the indices')
        # Compare before signed conversion, including unsigned malformed arrays.
        if any(int(b)-int(a) < 3 for a, b in zip(raw_offsets[:-1], raw_offsets[1:])):
            raise ValueError('Terrain polygons require at least three ordered corners')
        for name, a in [('vertices', v), ('indices', np.array(raw_indices, dtype='<i8', copy=True)),
                        ('offsets', np.array(raw_offsets, dtype='<i8', copy=True))]:
            a.flags.writeable = False
            object.__setattr__(self, name, a)

    @classmethod
    def from_polygons(cls, vertices, faces):
        sizes = np.array([len(face) for face in faces], dtype='<i8')
        offsets = np.r_[0, np.cumsum(sizes)]
        flat = [i for face in faces for i in face]
        indices = np.asarray(flat) if flat else np.empty(0, dtype='<i8')
        return cls(np.asarray(vertices, float).reshape(-1, 3), indices, offsets)

    def polygons(self):
        return [self.indices[a:b].tolist() for a, b in zip(self.offsets[:-1], self.offsets[1:])]

    def triangles(self):
        if np.all(np.diff(self.offsets) == 3):
            return self.indices.reshape(-1, 3)
        return np.asarray([(p[0], p[k], p[k+1]) for p in self.polygons()
                           for k in range(1, len(p)-1)], dtype='<i8').reshape(-1, 3)


def _identity(owner, stage, city):
    if not isinstance(owner, str) or not owner.strip() or stage not in ('natural', 'final') or type(city) is not bool:
        raise ValueError('Terrain product requires explicit owner, stage and city mode')


def save(path, mesh, *, owner, stage, city):
    """@cc [owner:fontanierh,label:correctness] ordered-terrain-product
    Persist ordered world-metre geometry without welding, resampling or moving
    triangulation ahead of deformation. Identical arrays and explicit owner,
    stage and city mode MUST yield identical product bytes. No revision/time or
    machine path enters the geometry identity. Managed scratch MUST use the existing
    held same-filesystem scope; default writes retain their sibling temporary path,
    identical ZIP bytes and atomic replacement, with no copy fallback.
    """
    _identity(owner, stage, city)
    arrays = {'schema': np.array(1, dtype='<i8'), 'owner': np.array(owner), 'stage': np.array(stage),
              'city': np.array(city), 'vertices': mesh.vertices, 'indices': mesh.indices,
              'offsets': mesh.offsets, 'triangles': mesh.triangles()}
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = managed_temporary_parent(path) / (path.name+'.tmp')
    try:
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_STORED) as archive:
            for name, array in sorted(arrays.items()):
                buffer = io.BytesIO()
                np.lib.format.write_array(buffer, np.asarray(array), allow_pickle=False)
                member = zipfile.ZipInfo(name+'.npy', date_time=(1980, 1, 1, 0, 0, 0))
                member.external_attr = 0o600 << 16
                archive.writestr(member, buffer.getvalue())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def load(path, *, owner, stage, city):
    """Read a matching owned product; missing, malformed or wrong-mode data fails."""
    _identity(owner, stage, city)
    with np.load(path, allow_pickle=False) as data:
        expected = {'schema', 'owner', 'stage', 'city', 'vertices', 'indices', 'offsets', 'triangles'}
        if set(data.files) != expected:
            raise ValueError('Unexpected terrain product fields')
        if (data['schema'].shape != () or data['schema'].dtype != np.dtype('<i8') or data['schema'].item() != 1 or
                data['owner'].shape != () or data['owner'].item() != owner or
                data['stage'].shape != () or data['stage'].item() != stage or
                data['city'].shape != () or data['city'].dtype.kind != 'b' or data['city'].item() != city):
            raise ValueError('Terrain product owner, stage or city mode mismatch')
        if (data['vertices'].dtype != np.dtype('<f8') or
                any(data[k].dtype != np.dtype('<i8') for k in ['indices', 'offsets', 'triangles'])):
            raise ValueError('Terrain product geometry has a noncanonical dtype')
        mesh = Mesh(data['vertices'], data['indices'], data['offsets'])
        if not np.array_equal(mesh.triangles(), data['triangles']):
            raise ValueError('Terrain product triangles differ from its ordered polygons')
    return mesh
