"""Independent original island constructors; no mesh export occurs in this module."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parent)); import yori  # noqa: E402,F401
import os, math
import bpy
import numpy as np
import shorelines
import coastal_surface
from mathutils import Vector

OUT = str(yori.OUT)
TEX = str(yori.TEXTURES)
LOAD_TEXTURES = False


def backdrop_owned(x, y, *, city):
    """@cc [owner:fontanierh,label:correctness] backdrop-replacement-ownership
    Omit ground only where an exported fine terrain owns its replacement.
    Without a city, FarHills MUST retain the former HD_Terrain footprint.
    """
    from farhills_surface import owns_fine_ground
    return owns_fine_ground(x, y, city=city)


def ocean_mesh(*, city):
    """@cc [owner:fontanierh,label:correctness] fallback-ocean-ownership
    Preserve the open-ocean partition with a city; without HD_Sea, add its
    missing harbor rectangle at the same datum, without overlaps.
    """
    vertices,faces=shorelines.sea_mesh()
    if not city:
        x0,y0,x1,y1=shorelines.HARBOR_RECT
        i=len(vertices)
        vertices.extend([(x0,y0,0.),(x1,y0,0.),(x1,y1,0.),(x0,y1,0.)])
        faces.append((i,i+1,i+2,i+3))
    return vertices,faces


def mat(name, color=(0.5, 0.5, 0.5), texture=None):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]; b.inputs["Base Color"].default_value = (*color, 1); b.inputs["Roughness"].default_value = 1.0
    if texture and LOAD_TEXTURES:
        t = m.node_tree.nodes.new("ShaderNodeTexImage"); t.image = bpy.data.images.load(os.path.join(TEX, texture)); m.node_tree.links.new(t.outputs["Color"], b.inputs["Base Color"])
    return m


def obj(name, verts, faces, m, uvs=None, smooth=True):
    me = bpy.data.meshes.new(name); me.from_pydata(verts, [], faces); me.update(); me.materials.append(m)
    for p in me.polygons: p.use_smooth = smooth
    if uvs:
        uv = me.uv_layers.new(name="UVMap").data
        for p in me.polygons:
            for li in p.loop_indices:
                uv[li].uv = uvs(me.vertices[me.loops[li].vertex_index].co)
    ob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(ob); return ob


def coastal_colours(ob):
    """Linear palette plus its coverage; the importer uses these on opaque ground."""
    points=np.asarray([v.co[:] for v in ob.data.vertices])
    normals=np.asarray([v.normal.z for v in ob.data.vertices])
    colours,amount=shorelines.paint(points[:,0],points[:,1],points[:,2],normals)
    attribute=ob.data.color_attributes.new(name='Color',type='FLOAT_COLOR',domain='POINT')
    attribute.data.foreach_set('color',np.c_[colours,amount].astype('f4').ravel())
    return amount


def rock_surface(ob):
    """Separate exposed FarHills faces without altering positions or normals."""
    assert ob.name == 'FarHills'
    me=ob.data
    centres=np.asarray([p.center[:] for p in me.polygons])
    nz=np.asarray([p.normal.z for p in me.polygons])
    selected=coastal_surface.rock_faces(*centres.T,nz)
    owned=[i for i,m in enumerate(me.materials) if m.name.split('.')[0]=='FarForest']
    selected &= np.isin([p.material_index for p in me.polygons],owned)
    if not selected.any():return
    # Preserve every unselected corner's previous point color, including alpha.
    original=me.color_attributes['Color']
    assert original.domain in {'POINT','CORNER'}
    rgba=np.empty((len(original.data),4),dtype='f4')
    original.data.foreach_get('color',rgba.ravel())
    vertices=np.asarray([loop.vertex_index for loop in me.loops])
    colours=(rgba[vertices] if original.domain=='POINT' else rgba).copy()
    me.color_attributes.remove(original)
    attr=me.color_attributes.new(name='Color',type='FLOAT_COLOR',domain='CORNER')
    me.materials.append(mat('CoastRock'))
    slot=len(me.materials)-1
    face_colours=coastal_surface.face_colour(*centres[selected].T,nz[selected])
    for index,colour in zip(np.flatnonzero(selected),face_colours):
        face=me.polygons[index]
        face.material_index=slot
        colours[face.loop_start:face.loop_start+face.loop_total]=[*colour,1.]
    attr.data.foreach_set('color',colours.ravel())
    print('coastal rock surface: %d faces, existing geometry/normals retained'%selected.sum(),flush=True)



def terrain(W=None, H=None, final=None, *, city=True):
    n = W["n"]; size = W["size"]; step = size / (n - 1)
    ground = mat("Ground", (0.4, 0.5, 0.22), "T_ground.jpg")
    # terrain grid
    verts = [(-size / 2 + i * step, -size / 2 + j * step, float(H[j, i])) for j in range(n) for i in range(n)]
    faces = []
    for j in range(n - 1):
        for i in range(n - 1):
            a = j * n + i; faces.append((a, a + 1, a + n + 1, a + n))
    terrain = obj("Terrain", verts, faces, ground, uvs=lambda co: (co.x / 6.0, co.y / 6.0))
    coastal_colours(terrain)
    terrain.data.materials.append(mat('Coast'))
    for face in terrain.data.polygons:
        if float(shorelines.weight(face.center.x,face.center.y)) > 0.:
            face.material_index=1
    return terrain


def road(W=None, H=None, final=None, *, city=True):
    road_m = mat("Road", (0.36, 0.36, 0.37), "T_road.jpg")
    # road strip
    R = np.array(W["road"]); w = W["road_width"] / 2
    T = np.gradient(R[:, :2], axis=0); T /= np.linalg.norm(T, axis=1)[:, None]; Nn = np.stack([-T[:, 1], T[:, 0]], 1)
    rv, rf, ruv = [], [], []
    for i in range(len(R)):
        for s in (-1, 1):
            rv.append((float(R[i, 0] + Nn[i, 0] * w * s), float(R[i, 1] + Nn[i, 1] * w * s), float(R[i, 2] + 0.06)))
    for i in range(len(R) - 1):
        a = 2 * i; rf.append((a + 2, a + 3, a + 1, a))      # counter-clockwise from above so the strip faces up
    road = obj("Road", rv, rf, road_m, smooth=True)
    uv = road.data.uv_layers.new(name="UVMap").data
    for p in road.data.polygons:
        for li in p.loop_indices:
            vi = road.data.loops[li].vertex_index; i, s = vi // 2, vi % 2
            uv[li].uv = (s, i / 8.0)
    return road


def lane(W=None, H=None, final=None, *, city=True):
    n = W["n"]; size = W["size"]; step = size / (n - 1)
    # south-west detour: the shore lane as a sunken sand strip and the cove's sand pad (material slot Sand -> MI_Sand)
    SW = W.get("southwest"); lane = sand = None
    if SW:
        sand_m = mat("Sand", (0.50, 0.41, 0.25))
        def hsample(x, y):
            fx = (x + size / 2) / step; fy = (y + size / 2) / step
            i = int(np.clip(np.floor(fx), 0, n - 2)); j = int(np.clip(np.floor(fy), 0, n - 2)); tx = fx - i; ty = fy - j
            return float(H[j, i] * (1 - tx) * (1 - ty) + H[j, i + 1] * tx * (1 - ty) + H[j + 1, i] * (1 - tx) * ty + H[j + 1, i + 1] * tx * ty)
        L = np.array(SW["lane"]); w = 1.1
        T = np.gradient(L[:, :2], axis=0); T /= np.linalg.norm(T, axis=1)[:, None]; Nn = np.stack([-T[:, 1], T[:, 0]], 1)
        lv, lf = [], []
        for i in range(len(L)):
            wig = w * (1.0 + 0.25 * np.sin(i * 1.7))       # ragged edges
            for s_ in (-1, 1):
                x = float(L[i, 0] + Nn[i, 0] * wig * s_); y = float(L[i, 1] + Nn[i, 1] * wig * s_)
                lv.append((x, y, hsample(x, y) + 0.05))
        for i in range(len(L) - 1):
            a = 2 * i; lf.append((a + 2, a + 3, a + 1, a))
        lane = obj("Lane", lv, lf, sand_m, uvs=lambda co: (co.x / 6.0, co.y / 6.0), smooth=True)
        # Sand now belongs to the ground's Coast section. The former raised
        # sand disc left a second surface only 5 cm above the beach.
        print("southwest lane %d verts; beach painted on ground" % len(lv),flush=True)
    return lane


def guardrail(W=None, H=None, final=None, *, city=True):
    # guardrail: one continuous W-beam strip along the downhill edge (runs from world.json), posts every 2 m
    paint = mat("Paint", (0.86, 0.86, 0.84))
    gv, gf = [], []
    prof = [(0.0, 0.85), (0.06, 0.80), (0.0, 0.72), (0.06, 0.64), (0.0, 0.58)]
    for run in W.get("rail_runs", []):
        pts = np.array(run)                          # [[x, y, z, nx, ny], ...] at 1 m: position on the rail line, outward normal
        rings = []
        for i in range(len(pts)):
            x, y, z, nx, ny = pts[i]
            ring = [(x + nx * py, y + ny * py, z + pz) for (py, pz) in prof]
            base = len(gv); gv += ring; rings.append(base)
            if i % 2 == 0:
                # post: a thin box from the ground to the rail
                px0, py0 = x, y; b = len(gv)
                for (dx, dy, dz) in ((-0.05, -0.05, -0.3), (0.05, -0.05, -0.3), (0.05, 0.05, -0.3), (-0.05, 0.05, -0.3), (-0.05, -0.05, 0.72), (0.05, -0.05, 0.72), (0.05, 0.05, 0.72), (-0.05, 0.05, 0.72)):
                    gv.append((px0 + dx, py0 + dy, z + dz))
                for f in ((0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7), (4, 5, 6, 7)):
                    gf.append(tuple(b + k for k in f))
        for i in range(len(rings) - 1):
            a, b = rings[i], rings[i + 1]
            for k in range(len(prof) - 1):
                gf.append((a + k, a + k + 1, b + k + 1, b + k)); gf.append((b + k, b + k + 1, a + k + 1, a + k))
    rail = obj("Guardrail", gv, gf, paint, smooth=True) if gv else None
    return rail


def wires(W=None, H=None, final=None, *, city=True):
    metal = mat("Metal", (0.12, 0.12, 0.13))
    # wires: catenaries between consecutive poles, 5 per span
    wv, wf = [], []
    A = W["anchors"]
    for k in range(len(A) - 1):
        for (p0, p1) in zip(A[k], A[k + 1]):
            p0, p1 = Vector(p0), Vector(p1); Lspan = (p1 - p0).length; sag = 0.035 * Lspan
            segs = 14; ring_prev = None
            d = (p1 - p0).normalized(); side = d.cross(Vector((0, 0, 1))).normalized(); r = 0.03
            for s_ in range(segs + 1):
                t = s_ / segs; p = p0.lerp(p1, t); p.z -= sag * 4 * t * (1 - t)
                ring = [p + side * r, p + Vector((0, 0, r)), p - side * r, p - Vector((0, 0, r))]
                base = len(wv); wv += [tuple(q) for q in ring]
                if ring_prev is not None:
                    for q in range(4):
                        a, b = ring_prev + q, ring_prev + (q + 1) % 4; wf.append((a, b, base + (q + 1) % 4, base + q))
                ring_prev = base
    wires = obj("Wires", wv, wf, metal, smooth=True)
    return wires


def farhills(W=None, H=None, final=None, *, city=True):
    # A rolling forest-floor backdrop under the detailed distant canopy.
    far = mat("FarForest", (.055, .11, .035))
    # Include the exact fine-terrain boundaries, then omit their interiors.
    # Shaping both buried and visible ground onto one coast would recreate the
    # original coplanar flicker under the new beaches.
    hills = obj("FarHills", final.vertices.tolist(), final.polygons(), far, uvs=lambda co: (co.x / 180.0, co.y / 180.0))
    coastal_colours(hills)
    rock_surface(hills)
    return hills


def sea(W=None, H=None, final=None, *, city=True):
    water = mat("Water", (0.3, 0.44, 0.58), "T_water.jpg")
    vertices, faces = ocean_mesh(city=city)
    return obj("Sea", vertices, faces, water, uvs=lambda co: (co.x / 24., co.y / 24.), smooth=False)
