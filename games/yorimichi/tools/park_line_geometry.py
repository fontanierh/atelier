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

    def project(self, positions, interval=None):
        q = np.asarray(positions)[..., [0, 2]]
        ids = np.arange(len(self.length))
        if interval is not None:
            lo,hi = interval
            if not np.isfinite([lo,hi]).all() or not 0 <= lo <= hi <= self.s[-1]:
                raise ValueError('projection interval must lie inside its path')
            ids = ids[(self.s[:-1] <= hi) & (self.s[1:] >= lo)]
        delta,length = self.delta[ids],self.length[ids]
        offset = q[:, None]-self.points[None, ids]
        low,high = (0.,1.) if interval is None else (
            np.maximum(0.,(lo-self.s[ids])/length),np.minimum(1.,(hi-self.s[ids])/length))
        t = np.clip(np.sum(offset*delta, axis=2)/length**2, low, high)
        nearest = self.points[None, ids]+t[..., None]*delta
        d2 = np.sum((q[:, None]-nearest)**2, axis=2)
        i = d2.argmin(1); row = np.arange(len(q))
        return self.s[ids[i]]+t[row, i]*length[i], np.sqrt(d2[row, i])


class RouteProgress:
    """@cc [owner:fontanierh,label:correctness] continuous-route-projection
    Consecutive 60 Hz observations MUST use a local station window, so crossing
    or stacked runs cannot teleport the follower or verdict to another leg.
    The window MUST include at least three observed frame travel distances in
    either direction, with a three-metre floor. It MUST NOT change simulation
    poses, velocities, collision or acceptance thresholds. Leaving that local
    route remains a measurable corridor failure, never a forced path correction.
    """
    def __init__(self,path,start=None):
        self.path,self.station = path,start
        if start is not None and (not np.isfinite(start) or not 0 <= start <= path.s[-1]):
            raise ValueError('route start must lie inside the path')

    def update(self,position,speed):
        window = max(3.,3.*float(speed)/60.)
        interval = None if self.station is None else (max(0.,self.station-window),
                                                      min(self.path.s[-1],self.station+window))
        s,lateral = self.path.project(np.asarray(position)[None],interval)
        self.station = float(s[0])
        return self.station,float(lateral[0])


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
    """@cc [owner:fontanierh,label:correctness] authored-route-corridors
    Width zones MUST be finite, positive, disjoint and inside the route. They
    MUST change acceptance only on their declared intervals; elsewhere the
    authored rideable width remains in force. Diagnostic width MUST NOT enter
    this calculation. The caller is responsible for supplying actual geometry
    widths; this metadata check does not certify the source mesh.
    """
    def __init__(self, spec, base, *, triangle_limit=100000):
        if triangle_limit not in (100000, 250000):
            raise ValueError('collision capacity must be the small or full-scene tier')
        self.spec = spec
        self.path = Path2D(spec['path'])
        self.labels = []
        self.sections = {}
        self.width = float(spec.get('lane_width_m', 80))
        self.design_width = float(spec.get('rideable_width_m', self.width))
        if min(self.width, self.design_width) <= 0:
            raise ValueError('lane widths must be positive')
        self.corridor_zones = spec.get('corridor_zones', [])
        if not isinstance(self.corridor_zones, list):
            raise ValueError('corridor_zones must be a list')
        self.corridor_zones = self.corridor_zones.copy()
        for i,zone in enumerate(self.corridor_zones):
            if not isinstance(zone, dict) or set(zone) != {'start_s_m', 'end_s_m', 'width_m'}:
                raise ValueError('corridor zones need start_s_m, end_s_m and width_m')
            a,b,w = (float(zone[k]) for k in ('start_s_m','end_s_m','width_m'))
            if not np.isfinite([a,b,w]).all() or not 0 <= a < b <= self.path.s[-1] or w <= 0:
                raise ValueError('corridor zone bounds/width must be finite and inside the route')
            self.corridor_zones[i] = dict(start_s_m=a,end_s_m=b,width_m=w)
        self.corridor_zones = sorted(self.corridor_zones, key=lambda z: z['start_s_m'])
        if any(a['end_s_m'] > b['start_s_m'] for a,b in zip(self.corridor_zones[:-1],self.corridor_zones[1:])):
            raise ValueError('corridor zones cannot overlap')
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
        if len(self.triangles) > triangle_limit or not np.isfinite(self.triangles).all():
            raise ValueError(f'nonfinite or oversized collision; selected capacity is {triangle_limit:,} triangles')
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
        self.spawn_m = float(s)
        return p, float(np.arctan2(direction[0], direction[1])), direction
