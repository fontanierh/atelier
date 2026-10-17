"""Suzu's silver hair: the crown, the parted fringe, side locks, the nape bun and its wooden comb.

Measured from the design sheet: the hair stands about 35 mm proud of the face, reaches down past the ears to the jaw
and gathers at the nape into a low round bun with a dark comb laid across it. It is a smooth crown with a few broad
soft locks rather than strand geometry: the game camera reads the mass, the centre part and the bun.
"""
import math

import bpy
from mathutils import Vector

import mesh_tools as G
from suzu_shapes import ball, rope

# Under-cap ring height -> (radius x, radius y, centre y, half-open angle at the face).
SHELL = [
    (1.045, .156, .146, .022, 1.22),
    (1.095, .180, .162, .022, 1.04),
    (1.155, .200, .180, .020, .90),
    (1.215, .208, .186, .018, .70),
    (1.275, .202, .182, .016, .50),
    (1.325, .184, .168, .014, .30),
    (1.368, .142, .132, .012, .12),
    (1.390, .082, .075, .010, .02),
    (1.400, .030, .028, .010, .00),
]
N = 21


def ring_at(z):
    for (z0, rx0, ry0, cy0, o0), (z1, rx1, ry1, cy1, o1) in zip(SHELL, SHELL[1:]):
        if z0 <= z <= z1:
            t = (z-z0)/(z1-z0)
            return (rx0+(rx1-rx0)*t, ry0+(ry1-ry0)*t, cy0+(cy1-cy0)*t, o0+(o1-o0)*t)
    return SHELL[-1][1:]


def shell_point(phi, z, bias=0.):
    """A point on the under-cap: phi 0 is the back of the head, increasing towards the left side."""
    rx, ry, cy, opening = ring_at(z)
    phi = min(phi, math.pi-opening-.02)
    return Vector(((rx+bias)*math.sin(phi), cy+(ry+bias)*math.cos(phi), z))


def shell_ring(rx, ry, cy, z, opening, n=N):
    start = 1.5*math.pi+opening
    span = 2*math.pi-2*opening
    return [Vector((rx*math.cos(start+span*i/(n-1)), cy+ry*math.sin(start+span*i/(n-1)), z)) for i in range(n)]


def soft_tube(name, path, radii, col, depth=.8, weights='head'):
    ob = G.tube(name, path, radii, col, weights, sides=10, depth=depth)
    for p in ob.data.polygons:
        p.use_smooth = True
    return ob


def build_hair():
    start = len(G.PARTS)
    rows = [shell_ring(rx, ry, cy, z, o) for z, rx, ry, cy, o in SHELL]
    verts = [tuple(p) for row in rows for p in row]
    faces, colours = [], []
    for j in range(len(rows)-1):
        for i in range(N-1):
            faces.append((j*N+i, j*N+i+1, (j+1)*N+i+1, (j+1)*N+i))
            # Broad soft bands, not a checkerboard: the shading is the lighting's job.
            colours.append('hair_light' if i % 4 == 0 else 'hair')
    inner_top = len(verts)
    for j, row in enumerate(rows):
        centre = Vector((0, SHELL[j][3], SHELL[j][0]))
        for p in (row[0], row[-1]):
            q = p.lerp(centre, .17)
            verts.append((q.x, q.y, q.z))
    for j in range(len(rows)-1):
        a0, a1 = inner_top+2*j, inner_top+2*j+1
        b0, b1 = inner_top+2*(j+1), inner_top+2*(j+1)+1
        faces += [(j*N, (j+1)*N, b0, a0), (j*N+N-1, (j+1)*N+N-1, b1, a1)]
        colours += ['hair_dark', 'hair_dark']
    faces.append(tuple(range(N-1, -1, -1)))
    colours.append('hair')
    shell = G.mesh('Suzu crown', verts, faces, 'hair', 'head', face_colours=colours)
    for p in shell.data.polygons:
        p.use_smooth = True

    for s in (-1, 1):
        # Parted fringe: one broad soft roll from the centre part down over the temple.
        soft_tube('Parted fringe '+str(s),
                  [(s*.018, -.104, 1.396), (s*.050, -.126, 1.364), (s*.096, -.132, 1.322),
                   (s*.138, -.114, 1.268), (s*.158, -.090, 1.210), (s*.166, -.064, 1.152)],
                  [.012, .030, .040, .042, .034, .016], 'hair_light', depth=.80)
        G.ribbon('Fringe crease '+str(s),
                 [(s*.020, -.124, 1.380), (s*.070, -.146, 1.330), (s*.124, -.138, 1.268),
                  (s*.158, -.112, 1.208)], [.002, .005, .005, .003], 'hair_dark', 'head', thickness=.0015)
        # Side lock: temple past the ear to the jaw, pointed.
        soft_tube('Side lock '+str(s),
                  [(s*.154, -.074, 1.300), (s*.178, -.046, 1.232), (s*.184, -.036, 1.158),
                   (s*.174, -.048, 1.092), (s*.158, -.064, 1.042)],
                  [.026, .042, .044, .034, .012], 'hair', depth=.80)
        G.ribbon('Side lock crease '+str(s),
                 [(s*.168, -.102, 1.286), (s*.192, -.076, 1.214), (s*.190, -.066, 1.142),
                  (s*.176, -.078, 1.076)], [.002, .005, .004, .002], 'hair_dark', 'head', thickness=.0015)
        G.ribbon('Sideburn lock '+str(s), [(s*.150, -.122, 1.238), (s*.146, -.110, 1.162),
                                           (s*.140, -.084, 1.074)], [.016, .012, .004], 'hair_light', 'head',
                 normal=(0, -.92, -.2), thickness=.008)
        G.ribbon('Temple lock '+str(s), [(s*.120, -.130, 1.298), (s*.108, -.136, 1.256),
                                         (s*.104, -.128, 1.226)], [.007, .005, .003], 'hair_dark', 'head',
                 normal=(0, -1, 0), thickness=.004)

    # The centre part: a small flat tongue between the fringe rolls and a shallow groove, no spike.
    G.panel('Centre part tongue', [(-.024, -.104, 1.396), (.024, -.104, 1.396),
                                   (.014, -.126, 1.344), (-.014, -.126, 1.344)],
            [(0, 1, 2, 3)], 'hair', 'head', .008)
    G.ribbon('Centre part groove', [(0, -.112, 1.394), (0, -.124, 1.356), (0, -.132, 1.318)],
             [.002, .003, .002], 'hair_dark', 'head', thickness=.0015)
    for phi in (0., .40, -.40, .80, -.80):
        points = []
        for z in (1.085, 1.150, 1.215, 1.275, 1.325, 1.368):
            share = max(.0, min(1., (z-1.085)/.283))
            p = shell_point(phi*share, z, .003)
            points.append((p.x, p.y, p.z))
        G.ribbon('Gathered crown crease %+0.2f' % phi, points, [.003, .008, .008, .006, .005, .002],
                 'hair_dark', 'head', thickness=.002)

    # The low bun at the nape, its dark cord and the wooden comb.
    ball('Suzu hair bun', (0, .238, 1.080), .098, .094, .094, 'hair_light', 'bun', n=14, rings=6,
         face_colours=['hair', 'hair_light', 'hair_light', 'hair', 'hair_light'])
    rope('Bun cord', [(0+.060*math.cos(2*math.pi*i/14), .180, 1.080+.056*math.sin(2*math.pi*i/14))
                      for i in range(14)], .010, 'bun', col='cord', light='cord_light', dark='cord', sides=6,
         samples=3, twist=0)
    G.box('Comb spine', (0, .290, 1.152), (.126, .015, .014), 'wood', 'bun', .003, rotation=(-.34, 0, .03))
    for i in range(5):
        x = -.048+i*.024
        G.box('Comb tooth %d' % i, (x, .306, 1.122), (.008, .007, .040), 'wood_dark', 'bun', .001,
              rotation=(-.34, 0, .03))
    rope('Comb tassel', [(.060, .284, 1.158), (.072, .278, 1.130), (.076, .268, 1.106)],
         .006, 'bun', col='cord', light='cord_light', dark='cord', sides=5, samples=3)

    for ob in G.PARTS[start:]:
        bevel = ob.modifiers.new('Hair edge', 'BEVEL')
        bevel.width, bevel.segments = .0016, 1
        bevel.limit_method = 'ANGLE'
        bevel.angle_limit = .8
        bevel.harden_normals = True
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.modifier_apply(modifier=bevel.name)
