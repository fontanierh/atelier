"""Build the unplaced Jungle City proposal as modular Blender assets and one assembled GLB."""
from __future__ import annotations

import json
import math
import random
from pathlib import Path

import bpy
from mathutils import Vector


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
OUT = REPO / "build" / "yorimichi" / "jungle-city" / "models"
RNG = random.Random(7241)


def reset() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.render.engine = "BLENDER_EEVEE"
    make_materials()


def material(name: str, color: tuple[float, float, float], rough: float = 0.78,
             metallic: float = 0.0, emission: tuple[float, float, float] | None = None) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metallic
    if emission is not None:
        bsdf.inputs["Emission Color"].default_value = (*emission, 1)
        bsdf.inputs["Emission Strength"].default_value = 2.5
    return mat


MATS: dict[str, bpy.types.Material] = {}


def make_materials() -> None:
    MATS.clear()
    MATS.update({
        "earth": material("Jungle earth", (0.22, 0.25, 0.13)),
        "grass": material("Jungle grass", (0.12, 0.30, 0.13)),
        "sandstone": material("Warm carved sandstone", (0.58, 0.43, 0.27)),
        "sandstone_light": material("Sunlit sandstone", (0.75, 0.60, 0.39)),
        "laterite": material("Red laterite", (0.38, 0.16, 0.10)),
        "moss": material("Mossy stone", (0.23, 0.31, 0.17)),
        "roof": material("Dark teal roof tile", (0.055, 0.17, 0.16), 0.58),
        "timber": material("Aged timber", (0.22, 0.105, 0.055)),
        "thatch": material("Woven thatch", (0.53, 0.34, 0.14)),
        "water": material("Lotus reservoir water", (0.035, 0.31, 0.34), 0.18, 0.05),
        "leaf": material("Jungle canopy", (0.075, 0.28, 0.105)),
        "leaf_light": material("Sunlit canopy", (0.18, 0.43, 0.13)),
        "flower": material("Coral blossoms", (0.75, 0.20, 0.12)),
        "lantern": material("Warm lanterns", (1.0, 0.42, 0.08), 0.35, 0.0, (1.0, 0.19, 0.025)),
    })


def box(name: str, loc: tuple[float, float, float], scale: tuple[float, float, float], mat: str,
        collection: bpy.types.Collection, bevel: float = 0.0) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(MATS[mat])
    for coll in list(obj.users_collection):
        coll.objects.unlink(obj)
    collection.objects.link(obj)
    if bevel:
        mod = obj.modifiers.new("Soft worn edges", "BEVEL")
        mod.width = bevel
        mod.segments = 2
    return obj


def cylinder(name: str, loc: tuple[float, float, float], radius: float, depth: float, mat: str,
             collection: bpy.types.Collection, vertices: int = 12) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(MATS[mat])
    for coll in list(obj.users_collection):
        coll.objects.unlink(obj)
    collection.objects.link(obj)
    return obj


def cone(name: str, loc: tuple[float, float, float], radius1: float, radius2: float, depth: float,
         mat: str, collection: bpy.types.Collection, vertices: int = 12) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cone_add(vertices=vertices, radius1=radius1, radius2=radius2, depth=depth, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(MATS[mat])
    for coll in list(obj.users_collection):
        coll.objects.unlink(obj)
    collection.objects.link(obj)
    return obj


def mesh_object(name: str, verts: list[tuple[float, float, float]], faces: list[tuple[int, ...]],
                mat: str, collection: bpy.types.Collection) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    obj.data.materials.append(MATS[mat])
    collection.objects.link(obj)
    return obj


def stair_run(name: str, start: Vector, direction: Vector, width: float, steps: int,
              rise: float, run: float, collection: bpy.types.Collection, mat: str = "sandstone_light") -> None:
    direction = direction.normalized()
    for i in range(steps):
        centre = start + direction * (run * (i + 0.5)) + Vector((0, 0, rise * (i + 0.5)))
        obj = box(f"{name}_{i:02d}", centre, (width / 2, run / 2, rise / 2), mat, collection, 0.12)
        obj.rotation_euler[2] = math.atan2(direction.y, direction.x)


def lotus_tower(name: str, x: float, y: float, base_z: float, height: float, collection: bpy.types.Collection,
                scale: float = 1.0) -> None:
    box(f"{name}_plinth", (x, y, base_z + 1.2 * scale), (3.8 * scale, 3.8 * scale, 1.2 * scale), "sandstone", collection, .35)
    box(f"{name}_body", (x, y, base_z + 5.2 * scale), (2.8 * scale, 2.8 * scale, 3.0 * scale), "sandstone_light", collection, .25)
    for level in range(3):
        z = base_z + (8.0 + level * 2.0) * scale
        cone(f"{name}_lotus_{level}", (x, y, z), (3.7 - level * .55) * scale, (2.5 - level * .45) * scale,
             1.8 * scale, "sandstone", collection, 12)
    cone(f"{name}_spire", (x, y, base_z + (height - 1.4) * scale), 1.45 * scale, .16 * scale,
         4.4 * scale, "sandstone_light", collection, 12)


def tree(name: str, x: float, y: float, z: float, scale: float, collection: bpy.types.Collection,
         flowering: bool = False) -> None:
    trunk_h = 7.5 * scale
    cylinder(f"{name}_trunk", (x, y, z + trunk_h / 2), .65 * scale, trunk_h, "timber", collection, 9)
    crown_z = z + trunk_h
    for i in range(4):
        angle = i * math.tau / 4 + RNG.uniform(-.35, .35)
        dx, dy = math.cos(angle) * 2.4 * scale, math.sin(angle) * 2.4 * scale
        cone(f"{name}_crown_{i}", (x + dx, y + dy, crown_z + RNG.uniform(-.8, 1.4) * scale),
             4.8 * scale, 1.1 * scale, 6.2 * scale, "flower" if flowering and i == 0 else ("leaf_light" if i % 2 else "leaf"),
             collection, 9)


def build_terrain() -> None:
    coll = bpy.data.collections.new("01_Terrain")
    bpy.context.scene.collection.children.link(coll)
    nx, ny = 44, 36
    verts, faces = [], []
    for j in range(ny + 1):
        y = -260 + j * 520 / ny
        for i in range(nx + 1):
            x = -325 + i * 650 / nx
            edge = max(abs(x) / 325, abs(y) / 260)
            h = 2.0 + 7.0 * max(0, edge - .70) ** 1.5
            h += 2.4 * math.sin(x / 57) * math.cos(y / 63) + 1.2 * math.sin((x + y) / 31)
            if abs(x) < 235 and abs(y) < 195:
                h *= .35
            verts.append((x, y, h))
    for j in range(ny):
        for i in range(nx):
            a = j * (nx + 1) + i
            faces.append((a, a + 1, a + nx + 2, a + nx + 1))
    terrain = mesh_object("JungleCity_Terrain", verts, faces, "earth", coll)
    terrain.data.materials.append(MATS["grass"])
    for poly in terrain.data.polygons:
        poly.material_index = 1 if poly.center.z > 4.0 else 0
    box("CentralCity_Platform", (0, 0, 1.6), (228, 182, 1.6), "grass", coll, 1.2)


def build_waterworks() -> None:
    coll = bpy.data.collections.new("02_Waterworks")
    bpy.context.scene.collection.children.link(coll)
    # Moat and central island platform.
    for name, loc, scale in [
        ("Moat_N", (0, 168, 3.0), (215, 18, .7)), ("Moat_S", (0, -168, 3.0), (215, 18, .7)),
        ("Moat_E", (197, 0, 3.0), (18, 150, .7)), ("Moat_W", (-197, 0, 3.0), (18, 150, .7)),
    ]:
        box(name, loc, scale, "water", coll, 1.5)
    box("Inner_Island", (0, 0, 4.2), (177, 130, 1.4), "sandstone", coll, 1.2)
    # West baray, east reflecting basin and feeder canals.
    box("West_Baray", (-257, -28, 3.3), (52, 112, .8), "water", coll, 2.2)
    box("East_Reflecting_Basin", (255, 42, 3.3), (42, 82, .8), "water", coll, 2.0)
    box("North_Spill_Canal", (-112, 215, 3.0), (112, 8, .6), "water", coll, 1.0)
    box("South_Market_Canal", (175, -190, 3.0), (84, 9, .6), "water", coll, 1.0)
    for x in (-145, -76, 76, 145):
        box(f"Inner_Canal_NS_{x}", (x, 0, 5.85), (4.5, 119, .22), "water", coll, .7)
    for y in (-105, -52, 54, 107):
        box(f"Inner_Canal_EW_{y}", (0, y, 5.85), (166, 4.5, .22), "water", coll, .7)
    box("Axis_Causeway_EW", (0, 0, 6.1), (226, 7.5, .42), "sandstone_light", coll, .45)
    box("Axis_Causeway_NS", (0, 0, 6.15), (7.5, 178, .42), "sandstone_light", coll, .45)
    box("Temple_Court_Pool_W", (-112, 12, 5.85), (23, 38, .22), "water", coll, 1.0)
    box("Temple_Court_Pool_E", (112, 12, 5.85), (23, 38, .22), "water", coll, 1.0)
    for x, y, length, rot in [(-112, 168, 48, 0), (0, 168, 48, 0), (112, 168, 48, 0),
                              (-112, -168, 48, 0), (0, -168, 48, 0), (112, -168, 48, 0),
                              (197, 0, 50, math.pi / 2), (-197, 0, 50, math.pi / 2)]:
        box(f"Bridge_{x}_{y}", (x, y, 5.0), (10, length / 2, 1.2), "sandstone_light", coll, .5).rotation_euler[2] = rot
    for x, y in [(-257, -140), (-257, 84), (255, -40), (255, 124), (-112, 215), (287, -190)]:
        cylinder("LotusCluster", (x, y, 4.3), 2.5, .25, "leaf_light", coll, 12)


def build_temple() -> None:
    coll = bpy.data.collections.new("03_TempleMountain")
    bpy.context.scene.collection.children.link(coll)
    levels = [(72, 58, 5.2), (57, 45, 10.2), (43, 34, 15.2), (30, 24, 20.2), (18, 15, 25.2)]
    for i, (sx, sy, z) in enumerate(levels):
        box(f"Temple_Terrace_{i}", (0, 12, z), (sx, sy, 2.5), "sandstone" if i % 2 == 0 else "moss", coll, .8)
        box(f"Temple_GalleryRoof_N_{i}", (0, 12 + sy, z + 5.2), (sx + 2.2, 2.3, .75), "roof", coll, .32)
        box(f"Temple_GalleryRoof_S_{i}", (0, 12 - sy, z + 5.2), (sx + 2.2, 2.3, .75), "roof", coll, .32)
        box(f"Temple_GalleryRoof_E_{i}", (sx, 12, z + 5.2), (2.3, sy + 2.2, .75), "roof", coll, .32)
        box(f"Temple_GalleryRoof_W_{i}", (-sx, 12, z + 5.2), (2.3, sy + 2.2, .75), "roof", coll, .32)
        # Gallery rhythm around every terrace.
        for x in range(int(-sx + 8), int(sx - 6), 13):
            box(f"Temple_Niche_N_{i}_{x}", (x, 12 + sy - 1.1, z + 3.4), (1.1, 1.3, 3.3), "sandstone_light", coll, .25)
            box(f"Temple_Niche_S_{i}_{x}", (x, 12 - sy + 1.1, z + 3.4), (1.1, 1.3, 3.3), "sandstone_light", coll, .25)
        for y in range(int(12 - sy + 8), int(12 + sy - 6), 13):
            box(f"Temple_Niche_E_{i}_{y}", (sx - 1.1, y, z + 3.4), (1.3, 1.1, 3.3), "sandstone_light", coll, .25)
            box(f"Temple_Niche_W_{i}_{y}", (-sx + 1.1, y, z + 3.4), (1.3, 1.1, 3.3), "sandstone_light", coll, .25)
    for x in range(-82, 83, 12):
        box(f"Temple_Colonnade_N_{x}", (x, 78, 8.3), (1.2, 1.2, 4.8), "sandstone_light", coll, .22)
        box(f"Temple_Colonnade_S_{x}", (x, -54, 8.3), (1.2, 1.2, 4.8), "sandstone_light", coll, .22)
    for y in range(-42, 67, 12):
        box(f"Temple_Colonnade_E_{y}", (82, y, 8.3), (1.2, 1.2, 4.8), "sandstone_light", coll, .22)
        box(f"Temple_Colonnade_W_{y}", (-82, y, 8.3), (1.2, 1.2, 4.8), "sandstone_light", coll, .22)
    stair_run("Temple_Main_Stair", Vector((0, -52, 5.7)), Vector((0, 1, 0)), 15, 32, .72, 2.05, coll)
    stair_run("Temple_West_Stair", Vector((-75, 12, 5.7)), Vector((1, 0, 0)), 12, 31, .72, 2.15, coll)
    lotus_tower("Temple_Centre", 0, 12, 27.5, 31, coll, 1.48)
    for x, y in [(-27, -8), (27, -8), (-27, 32), (27, 32)]:
        lotus_tower(f"Temple_Corner_{x}_{y}", x, y, 22.5, 18, coll, .88)
    for x in [-56, -28, 28, 56]:
        cylinder(f"Naga_Post_{x}", (x, -53, 7.4), .85, 4.8, "sandstone_light", coll, 10)
        cone(f"Naga_Head_{x}", (x, -55, 10.1), 1.6, .35, 3.0, "sandstone_light", coll, 10)


def gate(name: str, x: float, y: float, rotation: float, coll: bpy.types.Collection) -> None:
    group = []
    group.append(box(f"{name}_Mass", (x, y, 15), (16, 7, 12), "laterite", coll, .7))
    for offset in [-7, 0, 7]:
        group.append(box(f"{name}_Passage_{offset}", (x + offset * math.cos(rotation), y + offset * math.sin(rotation), 12),
                         (2.4, 8.0, 7.5), "sandstone", coll, .35))
    group.append(box(f"{name}_Roof", (x, y, 29), (19, 9, 2.2), "roof", coll, .5))
    group.append(cone(f"{name}_Crown", (x, y, 34), 8.5, 2.2, 7.5, "roof", coll, 8))
    for obj in group:
        obj.rotation_euler[2] = rotation


def wall_tower(name: str, x: float, y: float, coll: bpy.types.Collection) -> None:
    box(f"{name}_Base", (x, y, 15.5), (7.2, 7.2, 13.5), "laterite", coll, .55)
    box(f"{name}_Gallery", (x, y, 30), (9.0, 9.0, 1.8), "sandstone", coll, .35)
    cone(f"{name}_Roof", (x, y, 35), 10.2, 3.2, 7.5, "roof", coll, 8)
    cone(f"{name}_Finial", (x, y, 41), 1.6, .18, 4.0, "sandstone_light", coll, 10)


def build_gates_walls() -> None:
    coll = bpy.data.collections.new("04_GatesAndWalls")
    bpy.context.scene.collection.children.link(coll)
    box("Wall_North", (0, 151, 12), (198, 3.8, 10), "laterite", coll, .5)
    box("Wall_South", (0, -151, 12), (198, 3.8, 10), "laterite", coll, .5)
    box("Wall_East", (198, 0, 12), (3.8, 147, 10), "laterite", coll, .5)
    box("Wall_West", (-198, 0, 12), (3.8, 147, 10), "laterite", coll, .5)
    gate("East_Gate", 198, 0, math.pi / 2, coll)
    gate("West_Gate", -198, 0, math.pi / 2, coll)
    gate("North_Gate", 0, 151, 0, coll)
    gate("South_Gate", 0, -151, 0, coll)
    for index, (x, y) in enumerate([(-198, -151), (198, -151), (-198, 151), (198, 151),
                                    (-98, -151), (98, -151), (-98, 151), (98, 151),
                                    (-198, -72), (-198, 72), (198, -72), (198, 72)]):
        wall_tower(f"WallTower_{index:02d}", x, y, coll)
    for x, y, rot in [(198, 0, 0), (-198, 0, 0), (0, 151, math.pi / 2), (0, -151, math.pi / 2)]:
        for sign in [-1, 1]:
            dx = sign * 55 * (1 if rot == 0 else 0)
            dy = sign * 55 * (1 if rot != 0 else 0)
            cylinder(f"Causeway_Lantern_{x}_{y}_{sign}", (x + dx, y + dy, 10), 1.1, 7.5, "sandstone_light", coll, 10)
            cone(f"Causeway_Flame_{x}_{y}_{sign}", (x + dx, y + dy, 14.8), 1.4, .35, 2.8, "lantern", coll, 10)


def pavilion(name: str, x: float, y: float, rot: float, size: float, coll: bpy.types.Collection,
             two_story: bool = False) -> None:
    box(f"{name}_Base", (x, y, 5.5), (size * 8, size * 5, 1.2), "sandstone", coll, .45).rotation_euler[2] = rot
    box(f"{name}_Hall", (x, y, 11.5), (size * 6.8, size * 4.1, 5.0), "timber", coll, .35).rotation_euler[2] = rot
    roof = cone(f"{name}_Roof", (x, y, 18.0), size * 9.0, size * 5.0, 4.0, "roof", coll, 4)
    roof.rotation_euler[2] = rot + math.pi / 4
    roof.scale.x = 1.35
    roof.scale.y = .72
    bpy.context.view_layer.objects.active = roof
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    for post in (-5.8, -2.0, 2.0, 5.8):
        px = x + post * size * math.cos(rot)
        py = y + post * size * math.sin(rot)
        cylinder(f"{name}_Post_{post}", (px, py, 10.5), .32 * size, 7.2, "sandstone_light", coll, 8)
    if two_story:
        box(f"{name}_Upper", (x, y, 23.0), (size * 4.5, size * 3.1, 3.4), "timber", coll, .3).rotation_euler[2] = rot
        roof2 = cone(f"{name}_UpperRoof", (x, y, 28.2), size * 6.5, size * 3.4, 3.4, "roof", coll, 4)
        roof2.rotation_euler[2] = rot + math.pi / 4
        roof2.scale.x = 1.3
        roof2.scale.y = .72
        bpy.context.view_layer.objects.active = roof2
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    ridge = cylinder(f"{name}_RoofRidge", (x, y, 19.6 if not two_story else 29.5), .28 * size, 11 * size, "sandstone_light", coll, 8)
    ridge.rotation_euler[1] = math.pi / 2
    ridge.rotation_euler[2] = rot
    cone(f"{name}_RoofFinial", (x, y, 22.0 if not two_story else 32.0), .65 * size, .1, 2.5 * size, "sandstone_light", coll, 8)


def build_market() -> None:
    coll = bpy.data.collections.new("05_MarketAndHousing")
    bpy.context.scene.collection.children.link(coll)
    for x1, x2, y in [(-174, -156, -132), (-146, -128, -132), (-118, -100, -132),
                      (100, 118, -132), (128, 146, -132), (156, 174, -132),
                      (-174, -156, 132), (-146, -128, 132), (-118, -100, 132),
                      (100, 118, 132), (128, 146, 132), (156, 174, 132)]:
        box(f"Market_Terrace_{x1}_{y}", ((x1+x2)/2, y, 5.4), ((x2-x1)/2, 25, 1.0), "sandstone", coll, .4)
    for row, y in enumerate([-124, -94, -70, 84, 110, 136]):
        for col, x in enumerate([-166, -136, -106, -84, 84, 106, 136, 166]):
            pavilion(f"Market_{row}_{col}", x, y, 0 if row % 2 else math.pi / 2, .82 + RNG.uniform(-.08, .12), coll,
                     two_story=(row + col) % 5 == 0)
    for i, y in enumerate((-112, -82, 86, 116)):
        pavilion(f"Market_LongHall_W_{i}", -146, y, 0, 1.18, coll, i == 1)
        pavilion(f"Market_LongHall_E_{i}", 146, y, 0, 1.18, coll, i == 2)
    for i, (x, y) in enumerate([(-255, -125), (-255, -78), (-255, 72), (252, -112), (252, -58), (252, 112),
                                (-142, 218), (-86, 218), (86, 218), (142, 218)]):
        pavilion(f"CanalHouse_{i}", x, y, math.pi / 2 if abs(x) > 220 else 0, .78, coll, i % 3 == 0)


def build_jungle() -> None:
    coll = bpy.data.collections.new("06_Jungle")
    bpy.context.scene.collection.children.link(coll)
    points = []
    for _ in range(175):
        x, y = RNG.uniform(-315, 315), RNG.uniform(-252, 252)
        if abs(x) < 225 and abs(y) < 183:
            continue
        points.append((x, y))
    for x in [-292, -270, 275, 300]:
        for y in range(-225, 226, 32):
            points.append((x + RNG.uniform(-8, 8), y + RNG.uniform(-10, 10)))
    for index, (x, y) in enumerate(points):
        scale = RNG.uniform(.72, 1.55)
        tree(f"JungleTree_{index:03d}", x, y, 3.2, scale, coll, flowering=index % 17 == 0)
    inner_points = []
    for x in (-186, -158, -124, -90, 90, 124, 158, 186):
        for y in (-132, -112, -88, -62, 66, 90, 116, 140):
            inner_points.append((x + RNG.uniform(-4, 4), y + RNG.uniform(-5, 5)))
    for index, (x, y) in enumerate(inner_points):
        tree(f"CityGrove_{index:03d}", x, y, 6.0, RNG.uniform(.52, .78), coll, flowering=index % 11 == 0)
    # Monumental figs around the baray and temple approach.
    for index, (x, y) in enumerate([(-304, -152), (-300, 118), (298, -155), (300, 154), (-155, 232), (154, -232)]):
        tree(f"GuardianFig_{index}", x, y, 3.2, 2.15, coll, flowering=index % 2 == 0)


def build_props() -> None:
    coll = bpy.data.collections.new("07_PropsAndShrines")
    bpy.context.scene.collection.children.link(coll)
    for i, (x, y) in enumerate([(-145, -205), (-62, -205), (62, -205), (145, -205), (-145, 205), (-62, 205),
                                (62, 205), (145, 205), (-245, -142), (-245, 118), (245, -142), (245, 118)]):
        box(f"Shrine_{i}_Base", (x, y, 5.4), (5.2, 5.2, 1.4), "sandstone", coll, .4)
        box(f"Shrine_{i}_Cell", (x, y, 10), (3.5, 3.5, 3.4), "sandstone_light", coll, .3)
        cone(f"Shrine_{i}_Roof", (x, y, 15), 5.2, 1.2, 4.2, "roof", coll, 8)
        cone(f"Shrine_{i}_Finial", (x, y, 19), 1.2, .15, 3.2, "sandstone_light", coll, 10)
    for i in range(18):
        angle = i * math.tau / 18
        x, y = math.cos(angle) * 112, 12 + math.sin(angle) * 84
        cylinder(f"Processional_Lantern_{i}", (x, y, 8.2), .75, 5.5, "sandstone_light", coll, 9)
        cone(f"Processional_Flame_{i}", (x, y, 12), 1.15, .25, 2.4, "lantern", coll, 9)


MODULES = [
    ("terrain", "01_Terrain"),
    ("waterworks", "02_Waterworks"),
    ("temple_mountain", "03_TempleMountain"),
    ("gates_and_walls", "04_GatesAndWalls"),
    ("market_district", "05_MarketAndHousing"),
    ("jungle", "06_Jungle"),
    ("props_and_shrines", "07_PropsAndShrines"),
]


def export_module(slug: str, collection_name: str) -> dict:
    collection = bpy.data.collections[collection_name]
    bpy.ops.object.select_all(action="DESELECT")
    for obj in collection.all_objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = next(iter(collection.all_objects))
    path = OUT / f"{slug}.glb"
    bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_selection=True,
                              export_apply=True, export_yup=True, export_materials="EXPORT")
    blend = OUT / f"{slug}.blend"
    bpy.data.libraries.write(str(blend), {collection}, fake_user=True, compress=True)
    return {"model": str(path.relative_to(REPO)), "blend": str(blend.relative_to(REPO)),
            "objects": len(collection.all_objects), "bytes": path.stat().st_size}


def assemble() -> dict:
    reset()
    for slug, _ in MODULES:
        bpy.ops.import_scene.gltf(filepath=str(OUT / f"{slug}.glb"))
    # Ground-lighting metadata is saved in the blend; the viewer supplies its own lights.
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "JungleCity.blend"), compress=True)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.export_scene.gltf(filepath=str(OUT / "JungleCity.glb"), export_format="GLB", use_selection=True,
                              export_apply=True, export_yup=True, export_materials="EXPORT")
    return {"model": "build/yorimichi/jungle-city/models/JungleCity.glb",
            "blend": "build/yorimichi/jungle-city/models/JungleCity.blend",
            "bytes": (OUT / "JungleCity.glb").stat().st_size}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    reset()
    build_terrain()
    build_waterworks()
    build_temple()
    build_gates_walls()
    build_market()
    build_jungle()
    build_props()
    modules = [dict(slug=slug, **export_module(slug, collection)) for slug, collection in MODULES]
    assembled = assemble()
    manifest = {
        "schema": 1,
        "proposal": "Jungle City",
        "status": "unplaced-review-only",
        "extent_metres": [650, 520],
        "modules": modules,
        "assembled": assembled,
        "generator": "games/yorimichi/world/regions/jungle_city/build.py",
        "blender_version": bpy.app.version_string,
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("JUNGLE CITY BUILD COMPLETE", flush=True)
    print(json.dumps(manifest, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
