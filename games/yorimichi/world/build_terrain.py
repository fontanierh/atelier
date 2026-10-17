"""Terrain + road + wires (one FBX) and the sea plane from build/yorimichi/world.json + heightmap.npy

    blender -b --python games/yorimichi/world/build_terrain.py
-> build/yorimichi/terrain.fbx (objects Terrain, Road, Wires: material slots Ground, Road, Metal), build/yorimichi/assets/Sea.fbx
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parent)); import yori  # noqa: E402,F401
import sys, os, json, math
import bpy, bmesh
import numpy as np
import shorelines
from mathutils import Vector

OUT = str(yori.OUT)
TEX = str(yori.TEXTURES)


def mat(name, color=(0.5, 0.5, 0.5), texture=None):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]; b.inputs["Base Color"].default_value = (*color, 1); b.inputs["Roughness"].default_value = 1.0
    if texture:
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


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    W = json.load(open(os.path.join(OUT, "world.json"))); H = np.load(os.path.join(OUT, "heightmap.npy"))
    n = W["n"]; size = W["size"]; step = size / (n - 1)
    ground = mat("Ground", (0.4, 0.5, 0.22), "T_ground.jpg"); road_m = mat("Road", (0.36, 0.36, 0.37), "T_road.jpg")
    metal = mat("Metal", (0.12, 0.12, 0.13)); water = mat("Water", (0.3, 0.44, 0.58), "T_water.jpg")
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
    # A rolling forest-floor backdrop under the detailed distant canopy.
    far = mat("FarForest", (.055, .11, .035))
    fn = 96; fsz = 6400.0; fstep = fsz / (fn - 1)
    FZ = np.load(os.path.join(OUT, "farhills.npy"))
    fx_ = np.linspace(-fsz / 2, fsz / 2, fn); FX, FY = np.meshgrid(fx_, fx_)
    if os.path.exists(os.path.join(OUT,"hidamari","city.json")):
        from hidamari.layout import backdrop_grid,north_height
        from hidamari.mountains import contains
        from megapark.trail import in_approach
        FZ=backdrop_grid().copy()
        # The detailed northern surface replaces this coarse, textured backdrop.
        # Cover the entire replacement footprint, including the final coarse row.
        # The old inset rectangle exposed a tall pale wall at the northern edge.
        # So does the Mega Park trail's approach ground north of the square (megapark/trail.py).
        mask=contains(FX,FY)|in_approach(FX,FY)
        FZ[mask]=np.minimum(FZ[mask],north_height(FX,FY,carved=False)[mask]-25)
        from belmonte import terrain as belmonte_terrain
        FZ=belmonte_terrain.old_backdrop(FZ,FX,FY)

    # Include the exact fine-terrain boundaries, then omit their interiors.
    # Shaping both buried and visible ground onto one coast would recreate the
    # original coplanar flicker under the new beaches.
    from belmonte.terrain import grid_height
    from hidamari.layout import coastal_backdrop_height,terrain_axes
    # All cells share the fine shoreline edge knots, including adjacent far cells.
    fine_y=np.unique(np.r_[np.linspace(-300.,300.,n),terrain_axes()[1]])
    fine_y=fine_y[(fine_y>=-300.) & (fine_y<=-100.)]
    xs=np.unique(np.r_[fx_,-300.,300.,1420.]);ys=np.unique(np.r_[fx_,fine_y,-300.,300.,500.])
    xx,yy=np.meshgrid(xs,ys);z=grid_height(fx_,fx_,FZ,xx,yy)
    def owned(x,y):
        return (-300.<x<300. and -300.<y<300.) or (300.<x<1420. and -300.<y<500.)
    fverts,ffaces=shorelines.grid_mesh(xs,ys,z,hidden=owned,shape=coastal_backdrop_height)
    print('coastal far hills: %d vertices, %d quads'%(len(fverts),len(ffaces)),flush=True)
    from train import earthworks  # the Belmonte railway's cuttings through the far hills (RAILWAY_EARTHWORKS=0: none)
    from hidamari.mountains import contains as under_foothills
    fverts, ffaces, _ = earthworks.polygons(fverts, ffaces, 4., hidden=under_foothills)
    hills = obj("FarHills", fverts, ffaces, far, uvs=lambda co: (co.x / 180.0, co.y / 180.0))
    coastal_colours(hills)
    # export terrain fbx
    bpy.ops.object.select_all(action="DESELECT")
    for o in [terrain, road, wires, hills] + ([rail] if rail else []) + ([lane] if lane else []): o.select_set(True)
    bpy.context.view_layer.objects.active = terrain
    path = os.path.join(OUT, "terrain.fbx")
    bpy.ops.export_scene.fbx(filepath=path, use_selection=True, apply_unit_scale=True, apply_scale_options="FBX_SCALE_ALL", axis_forward="-Y", axis_up="Z",
                             object_types={"MESH"}, mesh_smooth_type="FACE", bake_anim=False, path_mode="COPY", embed_textures=False)
    print("terrain:", len(terrain.data.polygons), "faces, road", len(road.data.polygons), "wires", len(wires.data.polygons), "->", path)
    # sea plane (separate asset, no collision)
    # The sea reaches past the sky dome (a 20 km sphere, JapanWorld.cpp): every view ray that goes below the horizon meets
    # water, never the dome's lower half. At 3.4 km it stopped short, and a band of the dome's below-horizon colour showed
    # between the sea's far edge and the horizon.
    sea_vertices,sea_faces=shorelines.sea_mesh()
    sea = obj("Sea", sea_vertices, sea_faces, water, uvs=lambda co: (co.x / 24.0, co.y / 24.0), smooth=False)
    bpy.ops.object.select_all(action="DESELECT"); sea.select_set(True); bpy.context.view_layer.objects.active = sea
    os.makedirs(os.path.join(OUT, "assets"), exist_ok=True)
    bpy.ops.export_scene.fbx(filepath=os.path.join(OUT, "assets", "Sea.fbx"), use_selection=True, apply_unit_scale=True, apply_scale_options="FBX_SCALE_ALL", axis_forward="-Y", axis_up="Z",
                             object_types={"MESH"}, mesh_smooth_type="FACE", bake_anim=False, path_mode="COPY", embed_textures=False)
    print("sea exported")


main()
