"""Painted panels on the park's exposed concrete walls (docs/COMMUNITY_PARK.md, "Restyle").

Large flat vertical source faces that see open air in front and open sky above get a stencilled mural from the
restyle panels (tools/communitypark_textures.py): faded indigo waves and mustard maples repeat at a fixed scale on
any wall; the vermilion sunburst is one composition, fitted to well-proportioned walls. Coplanar neighbours merge
into one painting. Each mural is a thin quad 1.5 cm proud of its wall with a concrete margin; it
has no collision, so riding and the clearance audits are unchanged.
"""
from collections import defaultdict
import numpy as np
from communitypark import layout as L
from communitypark.source import scene
from communitypark.structures import Mesh

PANELS = ('waves', 'sunburst', 'maples')
TILE = (4.5, 3.)   # metres covered by one repeat of a patterned panel
OFFSET, MARGIN, BASE = .015, .18, .25
UP = np.array([0., 0., 1.])


def _ray_hits(triangles, lo, hi, origin, direction, distance):
    end = origin+direction*distance
    near = np.all((lo <= np.maximum(origin, end)+.01) & (hi >= np.minimum(origin, end)-.01), axis=1)
    t = triangles[near]
    if not len(t): return False
    e1, e2 = t[:, 1]-t[:, 0], t[:, 2]-t[:, 0]; p = np.cross(direction, e2); det = (e1*p).sum(1)
    ok = abs(det) > 1e-9; inv = np.where(ok, 1/np.where(ok, det, 1), 0)
    s = origin-t[:, 0]; u = (s*p).sum(1)*inv; q = np.cross(s, e1); v = (q*direction).sum(1)*inv; d = (e2*q).sum(1)*inv
    return bool(np.any(ok & (u >= 0) & (v >= 0) & (u+v <= 1) & (d > 1e-3) & (d < distance)))


def walls():
    """Exposed flat wall sides as {normal, u, plane, u0, u1, z0, z1} in island metres."""
    source = scene(); everything = L.place(source.triangles()); lo, hi = everything.min(1), everything.max(1)
    found = []
    for part in source.parts:
        t = L.place(part['vertices'][part['faces']])
        n = np.cross(t[:, 1]-t[:, 0], t[:, 2]-t[:, 0]); area = np.linalg.norm(n, axis=1)/2
        n /= np.linalg.norm(n, axis=1, keepdims=True)+1e-12
        groups = defaultdict(list)
        for i in np.flatnonzero((abs(n[:, 2]) < .05) & (area > 1e-4)):
            flat = n[i, :2] if n[i, 0] > 1e-6 or (abs(n[i, 0]) <= 1e-6 and n[i, 1] > 0) else -n[i, :2]
            groups[(round(np.degrees(np.arctan2(flat[1], flat[0]))/2), round(float(t[i].mean(0)[:2]@flat)*20))].append((i, flat))
        for members in groups.values():
            index = [i for i, unused in members]; flat = members[0][1]
            normal = np.r_[flat, 0.]; u = np.r_[-flat[1], flat[0], 0.]; points = t[index].reshape(-1, 3)
            along, z = points@u, points[:, 2]; width, height = np.ptp(along), np.ptp(z)
            if width < 1.5 or height < 1. or area[index].sum()/(width*height) < .97: continue
            plane = float(points.mean(0)@normal)
            for side in (1., -1.):
                d = normal*side
                def clear(a, b):
                    o = u*(along.min()+a*width)+normal*plane+d*.03; o[2] = z.min()+b*height
                    return not _ray_hits(everything, lo, hi, o, d, 1.2) and not _ray_hits(everything, lo, hi, o+d*.3, UP, 60.)
                if all(clear(a, b) for a in np.linspace(.15, .85, 4) for b in np.linspace(.15, .85, 3)):
                    found.append({'normal': d, 'u': u*side, 'plane': plane*side, 'z0': float(z.min()), 'z1': float(z.max()),
                                  'u0': float((along*side).min()), 'u1': float((along*side).max())})
    return merge(found)


def merge(found):
    """Join coplanar walls that share an edge into one rectangle."""
    found = sorted(found, key=lambda w: (round(w['plane'], 2), w['u0'], w['z0']))
    changed = True
    while changed:
        changed = False
        for i, a in enumerate(found):
            for j in range(i+1, len(found)):
                b = found[j]
                if np.dot(a['normal'], b['normal']) < .999 or abs(a['plane']-b['plane']) > .01: continue
                side = abs(a['z0']-b['z0']) < .02 and abs(a['z1']-b['z1']) < .02 and (abs(a['u1']-b['u0']) < .02 or abs(b['u1']-a['u0']) < .02)
                stack = abs(a['u0']-b['u0']) < .02 and abs(a['u1']-b['u1']) < .02 and (abs(a['z1']-b['z0']) < .02 or abs(b['z1']-a['z0']) < .02)
                if side or stack:
                    a.update(u0=min(a['u0'], b['u0']), u1=max(a['u1'], b['u1']), z0=min(a['z0'], b['z0']), z1=max(a['z1'], b['z1']))
                    del found[j]; changed = True; break
            if changed: break
    return found


def build():
    meshes = {name: Mesh('SM_CP_Mural_'+name.title(), 'CP_Mural_'+name.title()) for name in PANELS}; records = []
    for k, wall in enumerate(walls()):
        u0, u1 = wall['u0']+MARGIN, wall['u1']-MARGIN; z0, z1 = wall['z0']+BASE, wall['z1']-MARGIN
        width, height = u1-u0, z1-z0
        framed = .67 <= width/height <= 2.2 and width*height >= 6.
        name = PANELS[k % 3] if framed else ('waves', 'maples')[k % 2]
        if name == 'sunburst':
            # One composition: cover the quad with the 3:2 panel, centred.
            scale = max(width/1.5, height); cu, cv = width/(scale*1.5), height/scale
            uv = [(.5-cu/2, .5+cv/2), (.5+cu/2, .5+cv/2), (.5+cu/2, .5-cv/2), (.5-cu/2, .5-cv/2)]
        else:
            uv = [(0, height/TILE[1]), (width/TILE[0], height/TILE[1]), (width/TILE[0], 0), (0, 0)]
        # Corners run bottom-left, bottom-right, top-right, top-left.
        corners = []
        for along, z in [(u0, z0), (u1, z0), (u1, z1), (u0, z1)]:
            p = wall['u']*along+wall['normal']*(wall['plane']+OFFSET); p[2] = z; corners.append(p)
        meshes[name].quad(corners, uv)
        records.append({'panel': name, 'width_m': round(width, 2), 'height_m': round(height, 2),
                        'centre': (wall['u']*(u0+u1)/2+wall['normal']*wall['plane']+UP*(z0+z1)/2).round(3).tolist()})
    return [m for m in meshes.values() if m.faces], records
