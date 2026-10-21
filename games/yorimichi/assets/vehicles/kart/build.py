"""The go-kart: an open frame with a cream seat and a wheel the driver holds.

Metres; +X is the nose, the ground is z = 0, +Y the car's left. Four meshes, each with its own pivot:
SM_Kart_Body (the kart at rest, origin on the ground under its middle), SM_Kart_Wheel (one wheel, origin at
its axle, axis +Y) and SM_Kart_SteeringWheel (origin at the hub, axis +X, the plane the driver faces).
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402,F401
import json
import hashlib
import math

import bpy
from mathutils import Matrix, Vector
from village import build as v
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
import cockpit

OUT = yori.OUT / 'kart'; v.OUT = OUT

LAYOUT = cockpit.load()
RED = (.66, .25, .16); CREAM = (.59, .39, .19); DARK = (.17, .18, .19)
METAL = (.40, .40, .38); CHROME = (.57, .55, .48); TYRE = (.105, .11, .12)
HUB = (.76, .70, .57); AMBER = (.64, .22, .015); LAMP = (.70, .65, .54)
WHEEL_RADIUS, WHEEL_WIDTH = LAYOUT['wheel_radius'], LAYOUT['wheel_width']
TRACK_FRONT, TRACK_REAR = 1.10, 1.24
WHEELBASE, FRONT_AXLE = 1.50, .75
STEER_RADIUS, STEER_AT = LAYOUT['steering_radius'], tuple(LAYOUT['steering'])



class KartBody(v.Mesh):
    """Paint and split normals may improve the shell; its actual surfaces stay fixed."""
    def object(self, material):
        ob = super().object(material)
        mesh = ob.data
        at = {}
        for face in mesh.polygons:
            for index in face.vertices:
                key = tuple(round(float(v), 7) for v in mesh.vertices[index].co)
                at.setdefault(key, []).append(face.normal.copy())
        normals = [None] * len(mesh.vertices)
        for face in mesh.polygons:
            for index in face.vertices:
                key = tuple(round(float(v), 7) for v in mesh.vertices[index].co)
                normal = sum((n for n in at[key] if n.dot(face.normal) > .65), Vector()).normalized()
                normals[index] = tuple(normal)
            face.use_smooth = True
        mesh.normals_split_custom_set_from_vertices(normals)
        return ob


def finish_paint(m):
    """Broad warm paint variation, without moving or adding a vertex near the approved rider."""
    for face in m.faces:
        a, b, c = (Vector(m.vertices[i]) for i in face[:3])
        normal = (b-a).cross(c-a).normalized()
        for index in face:
            color = m.colors[index]
            if tuple(color[:3]) == RED:
                factor = .97 + .055 * max(-.5, normal.z)
                m.colors[index] = (*[v*factor for v in (.64, .285, .205)], color[3])


def geometry_hash(m):
    return hashlib.sha256(json.dumps({'vertices': m.vertices, 'faces': m.faces, 'colliders':
        [(p, size, tuple(rotation)) for p, size, rotation in m.colliders]}, separators=(',', ':')).encode()).hexdigest()


def bar(m, a, b, radius, color, n=12):
    """Closed round chassis/axle member in the kart's authored frame."""
    a, b = Vector(a), Vector(b)
    old = m.transform.copy()
    length = (b - a).length
    m.transform = old @ Matrix.Translation((a + b) / 2) @ (b - a).to_track_quat('Z', 'Y').to_matrix().to_4x4()
    m.lathe((0, 0, 0), [(-length / 2, radius), (length / 2, radius)], color, n=n)
    disc(m, -length / 2, radius, color, n=n)
    disc(m, length / 2, radius, color, n=n)
    m.transform = old


def coachwork(m, sections, color):
    """The rounded pod/nose cross-sections, closed at both ends; sections are x,y,z,width,height."""
    rings = [[(x, y + width * math.cos(i * math.tau / 16), z + height * math.sin(i * math.tau / 16))
              for i in range(16)] for x, y, z, width, height in sections]
    m.poly(rings[0][::-1], DARK)
    for a, b in zip(rings, rings[1:]):
        for i in range(16):
            # One existing facet becomes an ivory longitudinal band; geometry is untouched.
            exterior = sections[0][1] > 0
            paint = HUB if i == (1 if exterior else 6) else color
            m.poly([a[i], a[(i + 1) % 16], b[(i + 1) % 16], b[i]], paint)
    m.poly(rings[-1], DARK)


def check_end_face(face, axial_offset):
    a, b, c = (Vector(p) for p in face[:3])
    normal = (b - a).cross(c - a)
    assert normal.z * axial_offset > 0, 'end face winds through its own part'


def disc(m, z, r, color, n=20):
    pts = [(r * math.cos(i * 2 * math.pi / n), r * math.sin(i * 2 * math.pi / n), z) for i in range(n)]
    for k in range(n):
        tri = [(0, 0, z), pts[k], pts[(k + 1) % n]]
        face = tri if z >= 0 else tri[::-1]
        check_end_face(face, z)
        m.poly(face, color)


def ring(m, z, outer, inner, color, n=20):
    a = [(outer * math.cos(i * 2 * math.pi / n), outer * math.sin(i * 2 * math.pi / n), z) for i in range(n)]
    b = [(inner * math.cos(i * 2 * math.pi / n), inner * math.sin(i * 2 * math.pi / n), z) for i in range(n)]
    for k in range(n):
        quad = [a[k], a[(k + 1) % n], b[(k + 1) % n], b[k]]
        face = quad if z >= 0 else quad[::-1]
        check_end_face(face, z)
        m.poly(face, color)


def tube(m, z0, z1, r, color, n=20, inward=False):
    a = [(r * math.cos(i * 2 * math.pi / n), r * math.sin(i * 2 * math.pi / n), z0) for i in range(n)]
    b = [(r * math.cos(i * 2 * math.pi / n), r * math.sin(i * 2 * math.pi / n), z1) for i in range(n)]
    for k in range(n):
        quad = [a[k], a[(k + 1) % n], b[(k + 1) % n], b[k]]
        face = quad[::-1] if inward else quad
        p, q, t = (Vector(v) for v in face[:3])
        radial = Vector((p.x, p.y, 0))
        assert ((q - p).cross(t - p).dot(radial) < 0) == inward, 'radial wall winding'
        m.poly(face, color)


def signed_volume(m):
    """Positive when a closed part's faces wind outward (the one-sided material culls the rest)."""
    total = 0.0
    for face in m.faces:
        p0 = Vector(m.vertices[face[0]])
        for k in range(1, len(face) - 1):
            total += p0.dot(Vector(m.vertices[face[k]]).cross(Vector(m.vertices[face[k + 1]]))) / 6.0
    return total


def check_normals(m, axis, inner_radius=None, outer_radii=()):
    """Per-face winding check: end faces face out of the part, walls face their own side.

    Fails the reversed end faces 16b11f12 shipped (their flat normals pointed through the part) and the
    outward-wound inner rim wall.
    """
    unit = {'X': Vector((1, 0, 0)), 'Y': Vector((0, 1, 0)), 'Z': Vector((0, 0, 1))}[axis]
    for face in m.faces:
        pts = [Vector(m.vertices[i]) for i in face]
        normal = Vector((0, 0, 0))
        for k in range(1, len(pts) - 1):
            normal += (pts[k] - pts[0]).cross(pts[k + 1] - pts[0])
        if normal.length < 1e-12:
            continue
        centre = sum(pts, Vector((0, 0, 0))) / len(pts)
        axial = normal.dot(unit)
        offset = centre.dot(unit)
        flat = abs(axial) > .7 * normal.length
        if flat and abs(offset) > 1e-4:
            assert (axial > 0) == (offset > 0), (m.name, 'end face winds through the part', centre, normal)
        elif not flat:
            radial = centre - unit * offset
            if radial.length < 1e-6:
                continue
            alignment = normal.dot(radial) / (normal.length * radial.length)
            if abs(alignment) < .5:
                continue   # a sliver or a face that is not radial; the end-face rule covers its plane
            if inner_radius is not None and abs(radial.length - inner_radius) < .004:
                assert alignment < 0, (m.name, 'inner wall winds outward', centre, normal)
            elif any(abs(radial.length - r) < .004 for r in outer_radii):
                assert alignment > 0, (m.name, 'outer wall winds inward', centre, normal)


def winding_selftest():
    """A negative end face wound toward +Z, as 16b11f12 shipped, must fail check_normals."""
    try:
        check_end_face([(0, 0, -1), (1, 0, -1), (0, 1, -1)], -1)
    except AssertionError:
        pass
    else:
        raise AssertionError('end-face guard missed the original defect')
    m = v.Mesh('selftest')
    pts = [(math.cos(i * 2 * math.pi / 8), math.sin(i * 2 * math.pi / 8), -1.0) for i in range(8)]
    for k in range(8):
        m.poly([(0, 0, -1.0), pts[k], pts[(k + 1) % 8]], (.5, .5, .5))
    try:
        check_normals(m, 'Z')
    except AssertionError:
        return
    raise AssertionError('winding check missed a reversed negative end face')


def wheel():
    m = v.Mesh('SM_Kart_Wheel')
    m.transform = Matrix.Rotation(math.radians(-90), 4, 'X')
    half = WHEEL_WIDTH / 2
    rim = WHEEL_RADIUS * .56
    m.lathe((0, 0, 0), [(-half, rim), (-half, WHEEL_RADIUS * .83), (-half * .85, WHEEL_RADIUS * .95),
                        (-half * .55, WHEEL_RADIUS), (half * .55, WHEEL_RADIUS),
                        (half * .85, WHEEL_RADIUS * .95), (half, WHEEL_RADIUS * .83), (half, rim)], TYRE, n=40)
    for z in (-half, half):
        ring(m, z, rim, rim * .88, HUB, n=32)
        disc(m, z * .80, rim * .90, HUB, n=32)
        tube(m, min(z * .80, z), max(z * .80, z), rim * .88, HUB, n=32, inward=True)
        disc(m, z * .83, .030, DARK, n=16)
        for i in range(3):
            angle = math.tau * i / 3
            bar(m, (.051 * math.cos(angle), .051 * math.sin(angle), z * .80),
                (.051 * math.cos(angle), .051 * math.sin(angle), z * .84), .006, METAL, n=8)
    return m


def nose(m):
    # A swept U-shaped fairing: raised rounded ends and a low curved centre, as in the reference.
    sections = []
    for y in (-.64, -.62, -.57, -.48, -.32, 0, .32, .48, .57, .62, .64):
        t = abs(y) / .64
        front, back = 1.13 - .02 * t * t, .84 + .17 * t * t
        bottom, top = .075 + .055 * t * t, .18 + .12 * t ** 3
        sections.append([(front - .025, y, bottom), (front, y, bottom + .035),
                         (front - .025, y, top - .025), (back + .035, y, top),
                         (back, y, top - .04), (back + .025, y, bottom)])
    # The section is counterclockwise in X/Z; its normal points -Y.
    m.poly(sections[0], RED)
    for a, b in zip(sections, sections[1:]):
        for i in range(len(a)):
            j = (i + 1) % len(a)
            band = .32 <= abs((a[0][1]+b[0][1])*.5) <= .48
            paint = DARK if i in (0, 5) else HUB if band and i in (1, 2, 3) else RED
            m.poly([a[j], a[i], b[i], b[j]], paint)
    m.poly(sections[-1][::-1], RED)


def steering_wheel():
    m = v.Mesh('SM_Kart_SteeringWheel')
    m.transform = Matrix.Rotation(math.radians(90), 4, 'Y')
    radius = LAYOUT['steering_tube_radius']
    for i in range(48):
        for j in range(12):
            def point(a, b):
                return ((STEER_RADIUS + radius * math.cos(b)) * math.cos(a),
                        (STEER_RADIUS + radius * math.cos(b)) * math.sin(a), radius * math.sin(b))
            a, b = i * math.tau / 48, j * math.tau / 12
            da, db = math.tau / 48, math.tau / 12
            m.poly([point(a, b), point(a + da, b), point(a + da, b + db), point(a, b + db)], DARK)
    for angle in (90, 210, 330):
        a = math.radians(angle)
        m.beam((0, 0, 0), ((STEER_RADIUS - .016) * math.cos(a), (STEER_RADIUS - .016) * math.sin(a), 0), .024, .008, METAL)
    m.lathe((0, 0, 0), [(-.018, .030), (.018, .030)], CHROME, n=16)
    disc(m, -.018, .030, DARK, n=16); disc(m, .018, .030, DARK, n=16)
    return m


def kart():
    m = KartBody('SM_Kart_Body')
    # Swept tubular rails and a graphite tray; the cockpit has no knee-height dashboard.
    for sign in (-1, 1):
        points = [(-.92, sign * .40, .19), (-.65, sign * .43, .17), (-.25, sign * .42, .15),
                  (.30, sign * .38, .14), (.68, sign * .32, .17), (.86, sign * .34, .17)]
        for a, b in zip(points, points[1:]): bar(m, a, b, .020, RED)
        coachwork(m, [(-.48, sign * .49, .22, .045, .060), (-.42, sign * .49, .245, .115, .115),
                      (-.15, sign * .49, .25, .125, .12), (.25, sign * .48, .22, .11, .09),
                      (.43, sign * .47, .20, .065, .065), (.47, sign * .47, .19, .035, .045)], RED)
    for x in (-.78, -.30, .30, .70): bar(m, (x, -.39, .14), (x, .39, .14), .018, RED)
    m.box((-.02, 0, .115), (1.54, .76, .025), DARK, bevel=.01)
    nose(m)
    bar(m, (.96, -.54, .115), (.96, .54, .115), .025, DARK)
    bar(m, (-.95, -.58, .18), (-.95, .58, .18), .022, DARK)
    # Front uprights and tie rods, rear axle and brakes.
    for sign in (-1, 1):
        bar(m, (.50, sign * .29, .19), (.75, sign * .55, WHEEL_RADIUS), .018, METAL)
        bar(m, (.30, sign * .05, .19), (.72, sign * .51, .16), .008, CHROME)
        bar(m, (.75, sign * .50, .12), (.75, sign * .50, .22), .017, CHROME)
    bar(m, (-.75, -.62, WHEEL_RADIUS * 1.08), (-.75, .62, WHEEL_RADIUS * 1.08), .020, METAL)
    bar(m, (-.75, -.28, .1566), (-.75, -.25, .1566), .092, METAL, n=24)
    m.box((-.75, -.29, .23), (.10, .07, .08), RED, bevel=.01)
    # Compact finned motor and a guarded drive behind the bucket.
    m.box((-.74, .26, .31), (.26, .25, .23), METAL, bevel=.025)
    for z in (.28, .31, .34, .37, .40, .43):
        m.box((-.74, .26, z), (.28, .28, .012), DARK, bevel=.004)
    bar(m, (-.77, .39, .32), (-.77, .45, .32), .07, DARK, n=20)
    m.box((-.75, .44, .20), (.31, .055, .08), METAL, bevel=.015)
    for a, b in zip([(-.78, .16, .39), (-.91, .14, .41), (-.94, -.10, .38)],
                    [(-.91, .14, .41), (-.94, -.10, .38), (-.90, -.30, .35)]): bar(m, a, b, .025, CHROME)
    # Column clears the lap; small pedals remain below the ankle targets.
    # The fitted telescopic column is a separate runtime part; it follows wheel height/tilt.
    bar(m, (.39, 0, .18), (.47, 0, .18), .024, DARK)
    for sign in (-1, 1):
        m.box((.36, sign * .17, .135), (.16, .11, .025), METAL, bevel=.008)
        for y in (-.035, 0, .035): m.box((.39, sign * .17 + y, .15), (.065, .008, .008), DARK)
    m.collider((0, 0, LAYOUT['body_half_extents'][2]), tuple(2 * n for n in LAYOUT['body_half_extents']))
    return m


def seat():
    """Moulded bucket, tobacco pads and rolled edge; pivot is authored in cockpit.json."""
    m = v.Mesh('SM_Kart_Seat')
    m.box((0, 0, 0), (.48, .48, .065), DARK, bevel=.025)
    m.box((.01, 0, .045), (.40, .39, .045), CREAM, bevel=.018)
    m.transform = Matrix.Translation(Vector((-.19, 0, .28))) @ Matrix.Rotation(math.radians(-20), 4, 'Y')
    m.box((0, 0, 0), (.055, .48, .59), DARK, bevel=.025)
    m.box((.035, 0, -.03), (.025, .38, .40), CREAM, bevel=.012)
    for sign in (-1, 1): bar(m, (.01, sign * .225, -.25), (.01, sign * .225, .25), .018, DARK)
    m.transform = Matrix.Identity(4)
    return m


def main():
    winding_selftest()
    OUT.mkdir(parents=True, exist_ok=True); (OUT / 'assets').mkdir(exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    mat = bpy.data.materials.new('KartPalette'); mat.use_nodes = True
    vc = mat.node_tree.nodes.new('ShaderNodeVertexColor'); vc.layer_name = 'Color'
    mat.node_tree.links.new(vc.outputs['Color'], mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'])
    manifest = {}
    for make in (kart, seat, wheel, steering_wheel):
        m = make()
        shape = geometry_hash(m)
        if m.name == 'SM_Kart_Body': finish_paint(m)
        assert geometry_hash(m) == shape, 'finish pass moved collision or render geometry'
        ob, report = v.export(m, mat)
        report['geometry_sha256'] = shape
        manifest[m.name] = report
        if m.name in ('SM_Kart_Seat', 'SM_Kart_Wheel', 'SM_Kart_SteeringWheel'):
            volume = signed_volume(m)
            assert volume > 0.0, (m.name, 'faces wind inward', volume)
            # Winding is checked at each end/radial primitive before its placement transform.
            # A whole assembly's centre cannot classify the caps of its offset spokes or bucket.
            print('WINDING', m.name, round(volume, 6))
        bpy.data.objects.remove(ob, do_unlink=True)
    triangles = sum(a['triangles'] for a in manifest.values())
    assert triangles <= 6000, ('kart triangle budget exceeded', triangles)
    manifest['layout'] = LAYOUT
    (OUT / 'cockpit.json').write_text(json.dumps(LAYOUT, indent=2) + '\n')
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print('KART BUILD COMPLETE', sum(a['triangles'] for k, a in manifest.items() if k != 'layout'), 'triangles')


if __name__ == '__main__':
    main()
