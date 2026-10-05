"""Hidamari's clipped garden shrubs (Bush_HD_*), after the concepts' front gardens: a solid clipped core in dark leaf
colours, so a shrub never reads as a few paper cards, with small leaves standing out of its skin to break the outline.
Named Bush_* so the city treats them as the world's bushes do (JapanWorld.cpp: no collision, the camera's see-through
fade, their cull distance). Shapes are superellipsoids: exponent 2 a clipped ball, 4 a boxy hedge segment.
"""
import math, random
from mathutils import Matrix, Vector
from village import build as v

GREEN = [(.045, .085, .018), (.06, .11, .022), (.075, .13, .03), (.10, .16, .04), (.035, .07, .016)]
AZALEA = [(.32, .045, .02), (.42, .08, .02), (.24, .035, .018), (.06, .10, .02)]       # satsuki in autumn colour
AMBER = [(.50, .24, .02), (.36, .12, .02), (.62, .36, .05), (.06, .11, .022)]          # nanten, turning
CORE = (.022, .045, .011)
# name: (half extents x, y, z; exponent; leaves; leaf colours and weights)
KINDS = {
    'Bush_HD_Ball': ((.5, .5, .42), 2.4, 340, GREEN, (3, 3, 2, 1, 2)),
    'Bush_HD_Mound': ((.85, .65, .6), 2.6, 680, GREEN, (3, 3, 2, 1, 2)),
    'Bush_HD_Azalea': ((.7, .6, .45), 2.4, 560, AZALEA, (3, 2, 2, 2)),
    'Bush_HD_Amber': ((.55, .5, .7), 2.2, 500, AMBER, (2, 2, 1, 2)),
    'Bush_HD_Hedge': ((.8, .38, .5), 4.0, 560, GREEN, (3, 3, 2, 1, 2)),
}


def surface(extent, p, bumps, d):
    """The point of the clipped shape in direction d (a unit vector), lumpy where the bumps are."""
    x, y, z = (d[i]/extent[i] for i in range(3))
    s = (abs(x)**p+abs(y)**p+abs(z)**p)**(-1/p)
    s *= 1+sum(a*math.exp(-(d-c).length_squared/w) for c, a, w in bumps)
    return Vector((d.x*s, d.y*s, d.z*s))


def shrub(name):
    extent, p, leaves, colours, weights = KINDS[name]
    r = random.Random(sum(map(ord, name)))
    m = v.Mesh(name); cz = extent[2]-.06          # the centre: the shape sits on the ground, its foot just below
    bumps = [(Vector((r.uniform(-1, 1), r.uniform(-1, 1), r.uniform(-.2, 1))).normalized(), r.uniform(.03, .08),
              r.uniform(.15, .4)) for _ in range(7)]
    rings, n = 9, 16
    def at(i, k):
        lat = -math.pi/2*.8+i*(math.pi/2*1.8)/rings; lon = k*math.tau/n
        d = Vector((math.cos(lat)*math.cos(lon), math.cos(lat)*math.sin(lon), math.sin(lat)))
        return surface(extent, p, bumps, d)+Vector((0, 0, cz))
    grid = [[at(i, k) for k in range(n)] for i in range(rings+1)]
    top = surface(extent, p, bumps, Vector((0, 0, 1)))+Vector((0, 0, cz))
    for i in range(rings):
        for k in range(n):
            q = [grid[i][k], grid[i][(k+1) % n], grid[i+1][(k+1) % n], grid[i+1][k]]
            shade = .75+.5*max(0., min(1., (sum(c.z for c in q)/4)/(2*extent[2])))
            m.poly(q, tuple(c*shade for c in CORE))
    for k in range(n):m.poly([grid[rings][k], grid[rings][(k+1) % n], top], CORE)
    m.poly([grid[0][k] for k in range(n)][::-1], CORE)
    # the leaves: small pointed ovals tilted out of the skin, both faces, lighter towards the sun-facing top
    for _ in range(leaves):
        d = Vector((r.gauss(0, 1), r.gauss(0, 1), r.gauss(0, 1)+.25)).normalized()
        if d.z < -.55:continue
        s = surface(extent, p, bumps, d); normal = Vector((s.x/extent[0]**2, s.y/extent[1]**2, s.z/extent[2]**2)).normalized()
        pos = s*(1+r.uniform(-.02, .05))+Vector((0, 0, cz))
        size = r.uniform(.07, .12)
        frame = normal.to_track_quat('Z', 'Y').to_matrix().to_4x4()
        frame = frame@Matrix.Rotation(r.uniform(0, math.tau), 4, 'Z')@Matrix.Rotation(r.uniform(.5, 1.1), 4, 'X')
        light = .8+.45*max(0., normal.z)+r.uniform(-.1, .1)
        colour = tuple(min(1., c*light) for c in r.choices(colours, weights)[0])
        pts = [(0, -size, 0), (size*.42, -size*.25, .012), (size*.3, size*.45, .02), (0, size, 0),
               (-size*.3, size*.45, .02), (-size*.42, -size*.25, .012)]
        world = [Matrix.Translation(pos)@frame@Vector(q) for q in pts]
        m.poly(world, colour); m.poly(world[::-1], tuple(c*.8 for c in colour))
    return m


def builders():
    return {name: (lambda name=name: shrub(name)) for name in KINDS}
