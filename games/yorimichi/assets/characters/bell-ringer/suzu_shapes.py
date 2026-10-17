"""Small shapes the kit does not have: a rounded eye pill, a twisted rope and a faceted ball.

Metres, Z up, forward -Y. Everything becomes one flat-shaded, vertex-coloured mesh part in mesh_tools.PARTS.
"""
import math

from mathutils import Vector

import mesh_tools as G


def pill(name, centre, half_w, half_h, depth, col, weights, *, normal=(0, -1, 0), sides=3, surface=None,
         corner=None):
    """A vertical rounded pill (anime eye): two half-circle ends joined by straight sides, `depth` thick.

    `centre` is the middle of the front face; the plate extends along `normal`. `surface(x, z)` bends the plate
    onto the face instead of leaving a flat tile proud of the skin."""
    cx, cy, cz = centre
    nx, ny, nz = Vector(normal).normalized()
    w = half_w
    r = min(w, corner if corner is not None else w*.45)   # a small radius reads as a tall anime pill, not an oval
    outline = []

    def arc(cx0, cz0, a0, a1):
        for i in range(sides+1):
            a = math.radians(a0+(a1-a0)*i/sides)
            outline.append((cx0 + r*math.cos(a), cz0 + r*math.sin(a)))

    arc(cx+w-r, cz+half_h-r, 90, 0)        # top right
    arc(cx+w-r, cz-half_h+r, 0, -90)       # bottom right
    arc(cx-w+r, cz-half_h+r, -90, -180)    # bottom left
    arc(cx-w+r, cz+half_h-r, 180, 90)      # top left
    front = [(x, surface(x, z) if surface else cy, z) for x, z in outline]
    back = [(x+nx*depth, (surface(x, z) if surface else cy)+ny*depth, z+nz*depth) for x, z in outline]
    n = len(outline)
    faces = [tuple(range(n-1, -1, -1)), tuple(range(n, 2*n))]        # front cap, back cap
    faces += [(i, (i+1) % n, n+(i+1) % n, n+i) for i in range(n)]
    return G.mesh(name, front+back, faces, col, weights)


def catmull(points, samples=8):
    """A closed or open Catmull-Rom polyline through `points`, for a rope that bends instead of kinking."""
    pts = [Vector(p) for p in points]
    out = []
    for i in range(len(pts)-1):
        a, b, c, d = pts[max(0, i-1)], pts[i], pts[i+1], pts[min(len(pts)-1, i+2)]
        for k in range(samples):
            t = k/samples
            t2, t3 = t*t, t*t*t
            out.append(tuple(.5*((2*b)+(-a+c)*t+(2*a-5*b+4*c-d)*t2+(-a+3*b-3*c+d)*t3)))
    out.append(tuple(pts[-1]))
    return out


def rope(name, points, radius, weights, *, col='rope', light='rope_light', dark='rope_dark', sides=8,
         samples=6, twist=1.35, braid=True):
    """A closed-loop or open straw rope with a twisted silhouette and alternating strand colours.

    The radius breathes four times around the section and the colour bands advance with the twist, so the
    low-poly tube reads as braided straw from the game's camera."""
    path = catmull(points, samples)
    if (Vector(points[0])-Vector(points[-1])).length < .004:      # a loop: drop the duplicated end, wrap the faces
        path.pop()
        closed = True
    else:
        closed = False
    verts, faces, colours = [], [], []
    count = len(path)
    for i, p in enumerate(path):
        centre = Vector(p)
        before = Vector(path[i-1] if i > 0 else (path[-2] if closed else path[0]))
        after = Vector(path[(i+1) % count] if (i+1 < count or closed) else path[-1])
        tangent = (after-before).normalized()
        side = tangent.cross(Vector((0, -1, 0)))
        if side.length < .1:
            side = tangent.cross(Vector((0, 0, 1)))
        side.normalize()
        normal = tangent.cross(side).normalized()
        phase = twist*i/samples*2*math.pi
        for k in range(sides):
            a = 2*math.pi*k/sides
            rr = radius*(1+.16*math.cos(4*a+phase))
            verts.append(tuple(centre+side*(rr*math.cos(a))+normal*(rr*math.sin(a))))
    segments = count if closed else count-1
    for j in range(segments):
        band = int(j//(samples*.62)) % 3
        colour = light if band == 0 else dark if band == 2 else col
        for k in range(sides):
            a, b = j*sides+k, j*sides+(k+1) % sides
            c, d = ((j+1) % count)*sides+k, ((j+1) % count)*sides+(k+1) % sides
            faces.append((a, b, d, c))
            colours.append(colour)
    if not closed:
        faces.append(tuple(range(sides-1, -1, -1)))
        colours.append(col)
        faces.append(tuple((count-1)*sides+k for k in range(sides)))
        colours.append(col)
    ob = G.mesh(name, verts, faces, col, weights, face_colours=colours)
    for p in ob.data.polygons:
        p.use_smooth = True
    if braid:
        # One strand wound round the main tube: the sheet's rope is a two-ply twisted straw rope.
        strand, turns = [], max(1, round(count/samples*.9))
        for i, p in enumerate(path):
            centre = Vector(p)
            before = Vector(path[i-1] if i > 0 else (path[-2] if closed else path[0]))
            after = Vector(path[(i+1) % count] if (i+1 < count or closed) else path[-1])
            tangent = (after-before).normalized()
            side = tangent.cross(Vector((0, -1, 0)))
            if side.length < .1:
                side = tangent.cross(Vector((0, 0, 1)))
            side.normalize()
            normal = tangent.cross(side).normalized()
            a = 2*math.pi*turns*i/count
            strand.append(tuple(centre+(side*math.cos(a)+normal*math.sin(a))*(radius*.78)))
        strand.append(strand[0]) if closed else None
        strand_ob = G.tube(name+' strand', strand, [radius*.34]*len(strand), light, weights, sides=5)
        for p in strand_ob.data.polygons:
            p.use_smooth = True
    return ob


def ball(name, centre, rx, ry, rz, col, weights, *, n=12, rings=5, face_colours=None):
    """A faceted low-poly ball (the hair knot, the bell's clapper)."""
    cx, cy, cz = centre
    verts = []
    for j in range(1, rings):
        v = math.pi*j/rings
        z = cz - rz*math.cos(v)
        r = math.sin(v)
        for i in range(n):
            a = 2*math.pi*i/n
            verts.append((cx+rx*r*math.cos(a), cy+ry*r*math.sin(a), z))
    verts += [(cx, cy, cz-rz), (cx, cy, cz+rz)]
    bottom, top = len(verts)-2, len(verts)-1
    faces, colours = [], []
    for i in range(n):
        faces.append((bottom, (i+1) % n, i))
        colours.append(face_colours[0] if face_colours else col)
    for j in range(rings-2):
        for i in range(n):
            a, b = j*n+i, j*n+(i+1) % n
            faces.append((a, b, b+n, a+n))
            colours.append(face_colours[(j+1) % len(face_colours)] if face_colours else col)
    for i in range(n):
        faces.append(((rings-2)*n+i, (rings-2)*n+(i+1) % n, top))
        colours.append(face_colours[-1] if face_colours else col)
    ob = G.mesh(name, verts, faces, col, weights, face_colours=colours)
    for p in ob.data.polygons:
        p.use_smooth = True
    return ob
