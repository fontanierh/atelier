"""Authored line collision for the offline park validator (metres, native y up)."""
from pathlib import Path
import sys
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'world/regions'))
from craterpark.additions import hermite, profile
from park_audit_geometry import BVH, normals


class Path2D:
    def __init__(self, points):
        self.points = np.asarray(points, 'f8')
        if self.points.ndim != 2 or self.points.shape[1] != 2 or len(self.points) < 2:
            raise ValueError('path must contain at least two [x,z] points')
        self.delta = np.diff(self.points, axis=0)
        self.length = np.linalg.norm(self.delta, axis=1)
        if not np.isfinite(self.points).all() or (self.length <= 1e-8).any():
            raise ValueError('path must be finite with distinct consecutive points')
        self.s = np.r_[0., np.cumsum(self.length)]

    def at(self, distance):
        distance = np.asarray(distance)
        if (distance < -1e-8).any() or (distance > self.s[-1]+1e-8).any():
            raise ValueError('section extends beyond its path')
        i = np.clip(np.searchsorted(self.s, distance, side='right')-1, 0, len(self.length)-1)
        t = np.clip((distance-self.s[i])/self.length[i], 0, 1)
        return self.points[i]+t[..., None]*self.delta[i], self.delta[i]/self.length[i, None]

    def project(self, positions):
        q = np.asarray(positions)[..., [0, 2]]
        offset = q[:, None]-self.points[None, :-1]
        t = np.clip(np.sum(offset*self.delta, axis=2)/self.length**2, 0, 1)
        nearest = self.points[None, :-1]+t[..., None]*self.delta
        d2 = np.sum((q[:, None]-nearest)**2, axis=2)
        i = d2.argmin(1); row = np.arange(len(q))
        return self.s[i]+t[row, i]*self.length[i], np.sqrt(d2[row, i])


def section_knots(section):
    if 'knots' in section:
        k = np.asarray(section['knots'], 'f8')
    else:
        spec = section['profile']
        k = np.asarray(profile(spec['y'], spec.get('angle_deg', 0), spec['parts'], step=.5), 'f8')
    if k.ndim != 2 or k.shape[1] != 3 or len(k) < 2 or not np.isfinite(k).all():
        raise ValueError('profile knots must be finite [distance,height,angle_deg] triples')
    if abs(k[0, 0]) > 1e-8 or (np.diff(k[:, 0]) <= 1e-8).any():
        raise ValueError('profile distances must increase from zero (no vertical/overhanging height fields)')
    if (np.abs(k[:, 2]) >= 89.9).any():
        raise ValueError('vertical or overhanging profiles require explicit triangle input')
    return k


class LineWorld:
    def __init__(self, spec, base):
        self.spec = spec
        self.path = Path2D(spec['path'])
        self.labels = []
        self.sections = {}
        self.width = float(spec.get('lane_width_m', 80))
        self.design_width = float(spec.get('rideable_width_m', self.width))
        if min(self.width, self.design_width) <= 0:
            raise ValueError('lane widths must be positive')
        tris = []
        if 'sections' in spec:
            for section in spec['sections']:
                name = section['id']
                if name in self.sections:
                    raise ValueError('duplicate section id: '+name)
                k = section_knots(section)
                start = float(section.get('start_m', 0))
                step = float(spec.get('mesh_step_m', .25))
                if step <= 0:
                    raise ValueError('mesh_step_m must be positive')
                if k[-1, 0]/step > 24900:
                    raise ValueError('section too large for a small offline job; reduce scope')
                local = np.unique(np.r_[np.arange(0, k[-1, 0], step), k[:, 0], k[-1, 0]])
                if len(local) > 25000:
                    raise ValueError('section too large for a small offline job; reduce scope')
                xz, direction = self.path.at(local+start)
                side = np.stack([direction[:, 1], -direction[:, 0]], axis=1)*self.width/2
                h = hermite(k[:, 0], k[:, 1], np.tan(np.radians(k[:, 2])), local)
                a = np.column_stack([xz[:, 0]-side[:, 0], h, xz[:, 1]-side[:, 1]])
                b = np.column_stack([xz[:, 0]+side[:, 0], h, xz[:, 1]+side[:, 1]])
                t = np.stack([np.stack([a[:-1], a[1:], b[1:]], 1),
                              np.stack([a[:-1], b[1:], b[:-1]], 1)], 1).reshape(-1, 3, 3)
                n, _ = normals(t)
                t[n[:, 1] < 0] = t[n[:, 1] < 0][:, [0, 2, 1]]
                tris.append(t)
                self.labels.extend([name]*len(t))
                self.sections[name] = {**section, 'end_m': start+float(k[-1, 0])}
            self.triangles = np.concatenate(tris) if tris else np.empty((0, 3, 3))
        else:
            source = spec.get('mesh')
            if source:
                with np.load((base/source).resolve(), allow_pickle=False) as data:
                    self.triangles = np.asarray(data['positions'], 'f8')[data['triangles']] if 'positions' in data else np.asarray(data['triangles'], 'f8')
            else:
                self.triangles = np.asarray(spec['triangles'], 'f8')
            self.labels = ['untagged']*len(self.triangles)
            for region in spec.get('surface_regions', []):
                self.sections[region['id']] = region
                ids = region.get('faces')
                if ids is None:
                    lo, hi = np.asarray(region['box_min']), np.asarray(region['box_max'])
                    c = self.triangles.mean(1)
                    ids = np.flatnonzero(((c >= lo) & (c <= hi)).all(1))
                for i in ids:
                    self.labels[int(i)] = region['id']
        if self.triangles.ndim != 3 or self.triangles.shape[1:] != (3, 3) or not len(self.triangles):
            raise ValueError('expected nonempty triangle soup (F,3,3)')
        if len(self.triangles) > 100000 or not np.isfinite(self.triangles).all():
            raise ValueError('nonfinite or oversized collision; small jobs are limited to 100,000 triangles')
        self.normal, self.area = normals(self.triangles)
        self.tree = BVH(self.triangles)
        self.labels = np.asarray(self.labels)

    @property
    def finish_m(self):
        ends = [s['end_m'] for s in self.sections.values() if 'end_m' in s]
        return float(self.spec.get('finish_s_m', (max(ends) if ends else self.path.s[-1])-2))

    def support(self, point, rise=.35, drop=2.):
        """Infer the highest upward surface under the animated root; not a simulator contact query."""
        p = np.asarray(point)
        ids = []
        def visit(node):
            if node is None or p[0] < node.lo[0]-1e-7 or p[0] > node.hi[0]+1e-7 or p[2] < node.lo[2]-1e-7 or p[2] > node.hi[2]+1e-7:
                return
            if node.lo[1] > p[1]+rise or node.hi[1] < p[1]-drop:
                return
            if node.ids is not None:
                ids.extend(node.ids.tolist())
            else:
                visit(node.left); visit(node.right)
        visit(self.tree.root)
        if not ids:
            return None
        ids = np.asarray(ids)
        t = self.triangles[ids]; a = t[:, 0]; u = t[:, 1]-a; v = t[:, 2]-a
        d = p-a; det = u[:, 0]*v[:, 2]-u[:, 2]*v[:, 0]
        safe = np.where(np.abs(det) > 1e-15, det, 1.)
        b = (d[:, 0]*v[:, 2]-d[:, 2]*v[:, 0])/safe
        c = (u[:, 0]*d[:, 2]-u[:, 2]*d[:, 0])/safe
        h = a[:, 1]+b*u[:, 1]+c*v[:, 1]
        valid = (np.abs(det)>1e-15)&(b>=-1e-7)&(c>=-1e-7)&(b+c<=1+1e-7)&(h<=p[1]+rise)&(h>=p[1]-drop)&(self.normal[ids, 1]>.05)
        if not valid.any():
            return None
        best = np.flatnonzero(valid)[np.argmax(h[valid])]
        face = int(ids[best]); name = str(self.labels[face])
        return dict(face=face, surface=name, role=self.sections.get(name, {}).get('role', 'untagged'),
                    height_m=float(h[best]), normal=self.normal[face].tolist())

    def spawn(self):
        if 'spawn' in self.spec:
            p = np.asarray(self.spec['spawn'], 'f8')
            s = self.path.project(p[None])[0][0]
        else:
            s = float(self.spec.get('spawn_s_m', 1.))
            xz, _ = self.path.at(s)
            p = np.array([xz[0], float(self.triangles[:, :, 1].max())+1, xz[1]])
            support = self.support(p, rise=0, drop=float(np.ptp(self.triangles[:, :, 1]))+3)
            if support is None:
                raise ValueError('spawn is not over a riding surface')
            p[1] = support['height_m']+.05
        _, direction = self.path.at(s)
        return p, float(np.arctan2(direction[0], direction[1])), direction
