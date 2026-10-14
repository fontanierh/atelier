"""Painterly Japan-countryside props (Blender headless) -> build/yorimichi/assets/<Name>.fbx (+ check render)

    blender -b --python games/yorimichi/world/build_assets.py -- [--render]

Metres, Z up; the FBX exporter converts to Unreal centimetres. Foliage is exported by
build_foliage_lods.py, one specification per asset.
Material slot names are what the Unreal setup script keys on: LeafBroad, LeafCedar, LeafPine,
LeafOchre, Grass, Bark, Concrete, Paint, Stone, Vermilion, Plaster, Tile, Wood, Feather,
FeatherDark, Sky, Metal.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parent)); import yori  # noqa: E402,F401
import sys, os, math, random, argparse
import bpy, bmesh
from mathutils import Vector

from asset_mesh import Mesh, MATS, materials, export


def parse():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--render", action="store_true")
    ap.add_argument("--only", default="")
    return ap.parse_args(argv)


# ------------------------------------------------------------------ prop geometry


def rock(name, seed, size):
    rng = random.Random(seed); M = Mesh(name)
    M.rock((0, 0, 0), size, MATS["Rock"], rng, moss=MATS["Moss"])
    return M.build()


def pole(name, lamp=False):
    M = Mesh(name); c = MATS["Concrete"]; k = MATS["Metal"]
    M.tube((0, 0, -0.5), (0, 0, 11.0), 0.17, 0.11, c, n=10, uvscale=(1, 0.3), cap=True)
    for z, w in ((10.3, 2.4), (9.4, 2.0)):
        M.box((0, 0, z), (0.12, w, 0.12), MATS["Wood"])
        M.box((0, 0, z + 0.08), (0.16, w + 0.1, 0.05), k)
        for sgn in (-1, 1):                                                       # diagonal braces under the crossarm
            M.tube((0, sgn * w * 0.4, z - 0.06), (0, 0, z - 0.7), 0.025, 0.025, k, n=4)
        for y in (-w / 2 + 0.15, 0.0 if z > 10 else None, w / 2 - 0.15):
            if y is None: continue
            M.tube((0, y, z + 0.06), (0, y, z + 0.28), 0.05, 0.04, MATS["Paint"], n=6, cap=True)
    if lamp:
        M.tube((0, 0, 7.4), (0, 1.5, 7.9), 0.04, 0.035, k, n=6)
        M.box((0, 1.5, 7.9), (0.26, 0.6, 0.16), k)
    return M.build()


def guardrail(name, length=2.0):
    """one 2 m section of white W-beam guardrail with its post at the origin; rail runs along +X"""
    M = Mesh(name); p = MATS["Paint"]
    M.tube((0, 0, -0.3), (0, 0, 0.72), 0.05, 0.05, p, n=6, cap=True)
    prof = [(0.0, 0.85), (0.06, 0.80), (0.0, 0.72), (0.06, 0.64), (0.0, 0.58)]     # (y, z) W profile
    x0, x1 = -length / 2, length / 2
    for (y0, z0), (y1, z1) in zip(prof[:-1], prof[1:]):
        M.quad([(x0, y0, z0), (x1, y0, z0), (x1, y1, z1), (x0, y1, z1)], p, smooth=True)
        M.quad([(x0, y1, z1), (x1, y1, z1), (x1, y0, z0), (x0, y0, z0)], p, smooth=True)
    return M.build()


def lantern(name):
    M = Mesh(name); s = MATS["Stone"]
    # A buried stone footing supports every corner on the island's sloping path.
    # Keep the pedestal top at .24 m and the lantern body at its existing height.
    M.box((0, 0, -0.08), (0.7, 0.7, 0.64), s); M.box((0, 0, 0.30), (0.45, 0.45, 0.12), s)
    M.tube((0, 0, 0.36), (0, 0, 0.95), 0.10, 0.09, s, n=8, cap=True)
    M.box((0, 0, 1.02), (0.44, 0.44, 0.10), s); M.box((0, 0, 1.24), (0.34, 0.34, 0.34), s)
    M.box((0, 0, 1.48), (0.62, 0.62, 0.12), s); M.tube((0, 0, 1.54), (0, 0, 1.72), 0.22, 0.05, s, n=4, cap=True)
    return M.build()


def torii(name):
    M = Mesh(name); v = MATS["Vermilion"]; k = MATS["Tile"]
    for y in (-1.6, 1.6):
        M.tube((0, y, -0.3), (0, y, 4.6), 0.17, 0.14, v, n=10, cap=True)
    M.box((0, 0, 4.75), (0.30, 4.6, 0.30), v)            # kasagi
    M.box((0, 0, 5.02), (0.36, 4.9, 0.20), k)            # dark top
    M.box((0, 0, 3.55), (0.22, 4.0, 0.24), v)            # nuki
    M.box((0, 0, 4.15), (0.22, 0.34, 0.6), v)            # gakuzuka
    return M.build()


def leaf_mesh(name):
    """one small leaf card for the wind-blown leaf system (origin at the centre, lying in the XY plane)"""
    M = Mesh(name); rng = random.Random(77)
    M.card((0, 0, 0), (0.24, 0.28), 0, 90, MATS["LeafMaple"], 1, [(0, 0, 1)] * 4, col=0.0)
    return M.build()


def litter(name):
    M = Mesh(name)
    M.quad([(-0.5, -0.5, 0.02), (0.5, -0.5, 0.02), (0.5, 0.5, 0.02), (-0.5, 0.5, 0.02)], MATS["Litter"], [(0, 0), (1, 0), (1, 1), (0, 1)], normal=[(0, 0, 1)] * 4)
    return M.build()


def sky_dome(name):
    bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=24, radius=1.0)
    for f in bm.faces: f.normal_flip()
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(ob)
    me.materials.append(MATS["Sky"])
    uv = me.uv_layers.new(name="UVMap").data
    for p in me.polygons:
        p.use_smooth = True
        us = []
        for li in p.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            u = 0.5 + math.atan2(co.y, co.x) / (2 * math.pi)
            v = 0.5 + math.asin(max(-1, min(1, co.z))) / math.pi
            us.append([u, v])
        # fix the seam wrap
        if max(x[0] for x in us) - min(x[0] for x in us) > 0.5:
            for x in us:
                if x[0] < 0.5: x[0] += 1.0
        for k, li in enumerate(p.loop_indices):
            uv[li].uv = us[k]
    return ob


def bird_parts():
    """body (with head/tail) and two wings as separate objects; wing origins at the shoulders"""
    f = MATS["Feather"]; fd = MATS["FeatherDark"]
    B = Mesh("BirdBody")
    B.tube((-0.28, 0, 0), (0.22, 0, 0.02), 0.06, 0.09, f, n=8, cap=True)
    B.tube((0.22, 0, 0.02), (0.36, 0, 0.06), 0.09, 0.05, f, n=8, cap=True)
    B.tube((0.36, 0, 0.06), (0.44, 0, 0.09), 0.05, 0.045, f, n=8, cap=True)
    B.tube((0.44, 0, 0.09), (0.54, 0, 0.08), 0.045, 0.005, MATS["Vermilion"], n=6, cap=True)   # beak
    B.quad([(-0.28, -0.06, 0.0), (-0.28, 0.06, 0.0), (-0.50, 0.12, 0.02), (-0.50, -0.12, 0.02)], f)
    B.quad([(-0.50, -0.12, 0.02), (-0.50, 0.12, 0.02), (-0.28, 0.06, 0.0), (-0.28, -0.06, 0.0)], f)
    body = B.build()
    wings = []
    for s, nm in ((1, "BirdWingL"), (-1, "BirdWingR")):
        W = Mesh(nm)
        pts = [(0.12, 0, 0), (-0.14, 0, 0), (-0.20, s * 0.42, 0.0), (0.10, s * 0.42, 0.0)]
        W.quad(pts if s > 0 else list(reversed(pts)), f); W.quad(list(reversed(pts)) if s > 0 else pts, f)
        tip = [(0.10, s * 0.42, 0.0), (-0.20, s * 0.42, 0.0), (-0.30, s * 0.80, 0.02), (0.02, s * 0.80, 0.02)]
        W.quad(tip if s > 0 else list(reversed(tip)), fd); W.quad(list(reversed(tip)) if s > 0 else tip, fd)
        wings.append(W.build())
    return [body] + wings


def main():
    a = parse()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    materials()
    builders = {
        "Leaf": lambda: leaf_mesh("Leaf"),
        "Litter": lambda: litter("Litter"),
        "Rock_A": lambda: rock("Rock_A", 36, (1.8, 1.4, 1.0)),
        "Rock_B": lambda: rock("Rock_B", 37, (1.1, 0.9, 0.7)),
        "Rock_C": lambda: rock("Rock_C", 38, (2.6, 2.0, 1.3)),
        "Pole": lambda: pole("Pole"),
        "Pole_Lamp": lambda: pole("Pole_Lamp", lamp=True),
        "Guardrail": lambda: guardrail("Guardrail"),
        "Lantern": lambda: lantern("Lantern"),
        "Torii": lambda: torii("Torii"),
        "SkyDome": lambda: sky_dome("SkyDome"),
    }
    built = {}
    for name, fn in builders.items():
        if a.only and name not in a.only.split(","): continue
        ob = fn(); built[name] = ob; export(ob, name)
    for ob in bird_parts():
        built[ob.name] = ob; export(ob, ob.name)
    if a.render:
        # one tile per asset (EEVEE, alpha-hashed foliage), composited into renders/japan/assets.jpg
        sc = bpy.context.scene; sc.render.engine = "BLENDER_EEVEE"; sc.render.resolution_x, sc.render.resolution_y = 420, 520
        w = bpy.data.worlds.new("W"); sc.world = w; w.use_nodes = True
        w.node_tree.nodes["Background"].inputs[0].default_value = (0.62, 0.72, 0.85, 1); w.node_tree.nodes["Background"].inputs[1].default_value = 1.2
        sun = bpy.data.lights.new("Sun", "SUN"); sun.energy = 3.0; sun.angle = math.radians(6); so = bpy.data.objects.new("Sun", sun); sc.collection.objects.link(so)
        so.rotation_euler = (math.radians(50), 0, math.radians(-30))
        cam = bpy.data.cameras.new("Cam"); co = bpy.data.objects.new("Cam", cam); sc.collection.objects.link(co); sc.camera = co
        cam.lens = 45; sc.view_settings.view_transform = "Standard"
        tiles = []
        tmpdir = str(yori.REVIEW / "tiles"); os.makedirs(tmpdir, exist_ok=True)
        for name, ob in built.items():
            if name == "SkyDome": continue
            for o in built.values(): o.hide_render = (o is not ob)
            d = max(ob.dimensions.x, ob.dimensions.y, ob.dimensions.z)
            c = Vector((0, 0, ob.dimensions.z * 0.5 + (ob.bound_box[0][2])))
            dist = d * 1.9 + 0.5
            co.location = c + Vector((-0.55, -1.0, 0.45)).normalized() * dist
            co.rotation_euler = (c - Vector(co.location)).to_track_quat("-Z", "Y").to_euler()
            sc.render.filepath = os.path.join(tmpdir, f"{name}.png"); bpy.ops.render.render(write_still=True)
            tiles.append((name, sc.render.filepath))
        print("tiles", tmpdir)


if __name__ == "__main__":
    main()
