"""Build the unplaced Jungle City proposal as separate Blender modules and one review scene."""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

import bpy
from mathutils import Vector


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
OUT = REPO / "build/yorimichi/jungle-city/models"
TEXTURES = REPO / "games/yorimichi/assets/jungle_city/textures"
HERO_MODELS = REPO / "games/yorimichi/assets/jungle_city/models"
RNG = random.Random(24101987)
MATS: dict[str, bpy.types.Material] = {}


def reset() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)


def material(name: str, texture: str, color: tuple[float, float, float], roughness: float = 0.78,
             metallic: float = 0.0, bump: float = 0.16) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Metallic"].default_value = metallic
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    image_path = TEXTURES / f"{texture}.jpg" if texture else None
    if image_path and image_path.is_file():
        image = bpy.data.images.load(str(image_path), check_existing=True)
        image.colorspace_settings.name = "sRGB"
        tex = nodes.new("ShaderNodeTexImage")
        tex.image = image
        tex.extension = "REPEAT"
        tex.interpolation = "Cubic"
        mapping = nodes.new("ShaderNodeMapping")
        mapping.inputs["Scale"].default_value = (1.0, 1.0, 1.0)
        coordinate = nodes.new("ShaderNodeTexCoord")
        links.new(coordinate.outputs["UV"], mapping.inputs["Vector"])
        links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
        links.new(tex.outputs["Color"], shader.inputs["Base Color"])
        if bump:
            bump_node = nodes.new("ShaderNodeBump")
            bump_node.inputs["Strength"].default_value = bump
            bump_node.inputs["Distance"].default_value = 0.08
            links.new(tex.outputs["Color"], bump_node.inputs["Height"])
            links.new(bump_node.outputs["Normal"], shader.inputs["Normal"])
    else:
        shader.inputs["Base Color"].default_value = (*color, 1.0)
    MATS[name] = mat
    return mat


def setup_materials() -> None:
    material("sandstone", "warm_carved_sandstone", (0.56, 0.39, 0.22), 0.82, bump=0.2)
    material("sandstone_light", "mossy_stair_stone", (0.68, 0.52, 0.32), 0.86, bump=0.18)
    material("laterite", "red_laterite_blocks", (0.34, 0.12, 0.065), 0.9, bump=0.24)
    material("roof", "dark_teal_roof_tile", (0.045, 0.15, 0.13), 0.7, bump=0.14)
    material("timber", "aged_tropical_timber", (0.26, 0.12, 0.055), 0.86, bump=0.18)
    material("leaf", "jungle_canopy", (0.055, 0.21, 0.095), 0.9, bump=0.1)
    material("leaf_light", "jungle_canopy", (0.10, 0.34, 0.13), 0.9, bump=0.08)
    material("flower", "jungle_canopy", (0.42, 0.10, 0.045), 0.86, bump=0.06)
    material("earth", "mossy_stair_stone", (0.17, 0.12, 0.055), 1.0, bump=0.12)
    material("grass", "jungle_canopy", (0.10, 0.26, 0.095), 1.0, bump=0.08)
    water = material("water", "", (0.018, 0.31, 0.39), 0.16, metallic=0.02, bump=0)
    shader = next((node for node in water.node_tree.nodes if node.type == "BSDF_PRINCIPLED"), None)
    if shader:
        shader.inputs["IOR"].default_value = 1.333
    lantern = material("lantern", "", (1.0, 0.16, 0.018), 0.42, bump=0)
    lantern_shader = next((node for node in lantern.node_tree.nodes if node.type == "BSDF_PRINCIPLED"), None)
    if lantern_shader:
        lantern_shader.inputs["Base Color"].default_value = (1.0, 0.12, 0.012, 1.0)
        if "Emission Color" in lantern_shader.inputs:
            lantern_shader.inputs["Emission Color"].default_value = (1.0, 0.08, 0.008, 1.0)
        if "Emission Strength" in lantern_shader.inputs:
            lantern_shader.inputs["Emission Strength"].default_value = 2.2


def place(obj: bpy.types.Object, mat: str, collection: bpy.types.Collection,
          bevel: float = 0.0) -> bpy.types.Object:
    obj.data.materials.append(MATS[mat])
    for source in list(obj.users_collection):
        source.objects.unlink(obj)
    collection.objects.link(obj)
    if bevel:
        modifier = obj.modifiers.new("Worn edges", "BEVEL")
        modifier.width = bevel
        modifier.segments = 2
    return obj


def box(name: str, loc: tuple[float, float, float], scale: tuple[float, float, float], mat: str,
        collection: bpy.types.Collection, bevel: float = 0.0, rotation: float = 0.0) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(location=loc, rotation=(0, 0, rotation))
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return place(obj, mat, collection, bevel)


def cylinder(name: str, loc: tuple[float, float, float], radius: float, depth: float, mat: str,
             collection: bpy.types.Collection, vertices: int = 12, rotation=(0, 0, 0)) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=loc,
                                        rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    return place(obj, mat, collection)


def cone(name: str, loc: tuple[float, float, float], radius1: float, radius2: float, depth: float,
         mat: str, collection: bpy.types.Collection, vertices: int = 12) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cone_add(vertices=vertices, radius1=radius1, radius2=radius2, depth=depth,
                                    location=loc)
    obj = bpy.context.object
    obj.name = name
    return place(obj, mat, collection)


def sphere(name: str, loc: tuple[float, float, float], scale: tuple[float, float, float], mat: str,
           collection: bpy.types.Collection) -> bpy.types.Object:
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=1, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return place(obj, mat, collection)


def mesh_object(name: str, verts: list[tuple[float, float, float]], faces: list[tuple[int, ...]], mat: str,
                collection: bpy.types.Collection) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    return place(obj, mat, collection)


def roof_prism(name: str, centre: tuple[float, float, float], width: float, depth: float, height: float,
               mat: str, collection: bpy.types.Collection, rotation: float = 0.0) -> bpy.types.Object:
    x, y, z = centre
    w, d = width / 2, depth / 2
    verts = [(-w, -d, 0), (-w, d, 0), (w, -d, 0), (w, d, 0),
             (-w * .82, 0, height), (w * .82, 0, height)]
    faces = [(0, 2, 5, 4), (3, 1, 4, 5), (0, 4, 1), (2, 3, 5), (0, 1, 3, 2)]
    obj = mesh_object(name, verts, faces, mat, collection)
    obj.location = (x, y, z)
    obj.rotation_euler[2] = rotation
    return obj


def stair_run(name: str, start: Vector, direction: Vector, width: float, steps: int, rise: float,
              run: float, collection: bpy.types.Collection, mat: str = "sandstone_light") -> None:
    direction = direction.normalized()
    for index in range(steps):
        centre = start + direction * (run * (index + .5)) + Vector((0, 0, rise * (index + .5)))
        box(f"{name}_{index:02d}", centre, (width / 2, run / 2, rise / 2), mat, collection, .1,
            math.atan2(direction.y, direction.x))


def temple_tower(name: str, x: float, y: float, base_z: float, scale: float, collection: bpy.types.Collection) -> None:
    box(f"{name}_plinth", (x, y, base_z + 1.3 * scale), (5.2 * scale, 5.2 * scale, 1.3 * scale),
        "sandstone", collection, .28 * scale)
    box(f"{name}_body", (x, y, base_z + 5.5 * scale), (3.9 * scale, 3.9 * scale, 3.2 * scale),
        "sandstone_light", collection, .22 * scale)
    for level in range(4):
        z = base_z + (9.3 + level * 3.0) * scale
        radius = (5.4 - level * .72) * scale
        cone(f"{name}_tier_{level}", (x, y, z), radius, radius * .72, 2.7 * scale,
             "sandstone" if level % 2 == 0 else "sandstone_light", collection, 12)
        for side in range(4):
            angle = side * math.pi / 2
            px, py = x + math.cos(angle) * radius * .78, y + math.sin(angle) * radius * .78
            box(f"{name}_porch_{level}_{side}", (px, py, z),
                (1.1 * scale, 1.1 * scale, 1.65 * scale), "sandstone_light", collection, .12 * scale,
                angle)
    cone(f"{name}_lotus", (x, y, base_z + 22.8 * scale), 2.25 * scale, .62 * scale, 5.4 * scale,
         "sandstone", collection, 12)
    cone(f"{name}_finial", (x, y, base_z + 27.0 * scale), .68 * scale, .08 * scale, 3.2 * scale,
         "sandstone_light", collection, 10)


def khmer_roof(name: str, x: float, y: float, z: float, width: float, depth: float, height: float,
               rotation: float, collection: bpy.types.Collection, upper: bool = False) -> None:
    roof_prism(f"{name}_lower", (x, y, z), width, depth, height, "roof", collection, rotation)
    if upper:
        roof_prism(f"{name}_upper", (x, y, z + height * .58), width * .72, depth * .72,
                   height * .72, "roof", collection, rotation)
    cylinder(f"{name}_ridge", (x, y, z + height * (1.02 if not upper else 1.30)),
             width * .035, depth * .94, "sandstone_light", collection, 8,
             (math.pi / 2, 0, rotation + math.pi / 2))
    for sign in (-1, 1):
        dx = math.cos(rotation) * sign * width * .39
        dy = math.sin(rotation) * sign * width * .39
        cone(f"{name}_finial_{sign}", (x + dx, y + dy, z + height * (1.14 if not upper else 1.43)),
             .5, .06, 2.4, "sandstone_light", collection, 8)


def house(name: str, x: float, y: float, rotation: float, width: float, depth: float,
          collection: bpy.types.Collection, two_story: bool = False) -> None:
    base_z = 5.4
    box(f"{name}_terrace", (x, y, base_z), (width * .64, depth * .70, .65), "sandstone", collection, .28,
        rotation)
    box(f"{name}_walls", (x, y, base_z + 3.6), (width * .46, depth * .44, 2.8), "timber", collection, .18,
        rotation)
    for sign in (-1, 1):
        offset = sign * width * .36
        px = x + math.cos(rotation) * offset
        py = y + math.sin(rotation) * offset
        for side in (-1, 1):
            lateral = side * depth * .33
            cylinder(f"{name}_post_{sign}_{side}",
                     (px - math.sin(rotation) * lateral, py + math.cos(rotation) * lateral, base_z + 3.4),
                     .24, 6.2, "timber", collection, 8)
    khmer_roof(f"{name}_roof", x, y, base_z + 6.3, width * 1.22, depth * 1.25, 3.2,
               rotation, collection, upper=two_story)
    if two_story:
        box(f"{name}_upper", (x, y, base_z + 10.2), (width * .37, depth * .34, 2.4), "timber", collection,
            .16, rotation)


def market_hall(name: str, x: float, y: float, rotation: float, collection: bpy.types.Collection) -> None:
    box(f"{name}_terrace", (x, y, 5.6), (16, 5.6, .85), "sandstone", collection, .32, rotation)
    for row in (-1, 1):
        for index in range(-3, 4):
            dx, dy = index * 4.3, row * 3.5
            px = x + math.cos(rotation) * dx - math.sin(rotation) * dy
            py = y + math.sin(rotation) * dx + math.cos(rotation) * dy
            cylinder(f"{name}_post_{row}_{index}", (px, py, 10.3), .32, 8.7,
                     "timber", collection, 10)
    khmer_roof(f"{name}_roof", x, y, 14.5, 36, 12, 5.3, rotation, collection, upper=True)


def shrine(name: str, x: float, y: float, scale: float, collection: bpy.types.Collection) -> None:
    box(f"{name}_base", (x, y, 5.2), (3.7 * scale, 3.7 * scale, 1.0 * scale), "sandstone", collection,
        .22 * scale)
    box(f"{name}_cell", (x, y, 9.2), (2.55 * scale, 2.55 * scale, 3.0 * scale), "sandstone_light",
        collection, .18 * scale)
    khmer_roof(f"{name}_roof", x, y, 12.2, 8.3 * scale, 8.3 * scale, 3.3 * scale, 0,
               collection, upper=False)


def tree(name: str, x: float, y: float, z: float, scale: float, collection: bpy.types.Collection,
         flowering: bool = False) -> None:
    trunk_height = 7.8 * scale
    cylinder(f"{name}_trunk", (x, y, z + trunk_height / 2), .58 * scale, trunk_height,
             "timber", collection, 9)
    for branch in range(3):
        angle = branch * math.tau / 3 + RNG.uniform(-.55, .55)
        length = 3.6 * scale
        cylinder(f"{name}_branch_{branch}",
                 (x + math.cos(angle) * length * .35, y + math.sin(angle) * length * .35,
                  z + trunk_height * .84), .26 * scale, length, "timber", collection, 8,
                 (0, math.pi / 2, angle))
    for cluster in range(4):
        angle = cluster * math.tau / 4 + RNG.uniform(-.45, .45)
        radius = RNG.uniform(2.1, 3.6) * scale
        cx = x + math.cos(angle) * RNG.uniform(1.2, 3.2) * scale
        cy = y + math.sin(angle) * RNG.uniform(1.2, 3.2) * scale
        cz = z + trunk_height + RNG.uniform(-1.0, 2.1) * scale
        mat = "flower" if flowering and cluster == 0 else ("leaf_light" if cluster % 2 else "leaf")
        sphere(f"{name}_canopy_{cluster}", (cx, cy, cz),
               (radius * 1.35, radius, radius * .72), mat, collection)


def terrain_grid(name: str, collection: bpy.types.Collection) -> None:
    nx, ny = 52, 42
    verts, faces = [], []
    for row in range(ny + 1):
        y = -270 + row * 540 / ny
        for column in range(nx + 1):
            x = -335 + column * 670 / nx
            edge = max(abs(x) / 335, abs(y) / 270)
            height = 1.2 + 8.5 * max(0, edge - .72) ** 1.35
            height += 2.1 * math.sin(x / 61) * math.cos(y / 67) + 1.05 * math.sin((x - y) / 37)
            if abs(x) < 250 and abs(y) < 205:
                height *= .24
            verts.append((x, y, height))
    for row in range(ny):
        for column in range(nx):
            a = row * (nx + 1) + column
            faces.append((a, a + 1, a + nx + 2, a + nx + 1))
    terrain = mesh_object(name, verts, faces, "earth", collection)
    terrain.data.materials.append(MATS["grass"])
    for polygon in terrain.data.polygons:
        polygon.material_index = 1 if polygon.center.z > 3.2 else 0


def build_terrain() -> None:
    coll = bpy.data.collections.new("01_Terrain")
    bpy.context.scene.collection.children.link(coll)
    terrain_grid("JungleCity_Terrain", coll)
    box("Central_Island", (0, 4, 3.0), (124, 102, 1.35), "grass", coll, 1.0)
    box("East_District_Island", (184, -15, 3.0), (64, 175, 1.15), "grass", coll, .8)
    box("West_District_Island", (-184, 10, 3.0), (55, 168, 1.15), "grass", coll, .8)


def build_waterworks() -> None:
    coll = bpy.data.collections.new("02_Waterworks")
    bpy.context.scene.collection.children.link(coll)
    for name, loc, scale in [
        ("Moat_N", (0, 119, 3.1), (136, 15, .65)), ("Moat_S", (0, -119, 3.1), (136, 15, .65)),
        ("Moat_E", (132, 0, 3.1), (15, 104, .65)), ("Moat_W", (-132, 0, 3.1), (15, 104, .65)),
        ("Outer_Moat_N", (0, 208, 2.8), (278, 18, .65)), ("Outer_Moat_S", (0, -208, 2.8), (278, 18, .65)),
        ("Outer_Moat_E", (252, 0, 2.8), (18, 190, .65)), ("Outer_Moat_W", (-252, 0, 2.8), (18, 190, .65)),
    ]:
        box(name, loc, scale, "water", coll, 1.0)
    box("West_Baray", (-218, -28, 3.15), (62, 132, .65), "water", coll, 1.2)
    box("East_Reflector", (198, 78, 3.15), (37, 68, .65), "water", coll, 1.0)
    for y in (-174, -148, -82, 72, 145, 177):
        box(f"Canal_EW_{y}", (0, y, 3.45), (245, 4.5, .32), "water", coll, .45)
    for x in (-172, -96, 96, 172, 218):
        box(f"Canal_NS_{x}", (x, 0, 3.48), (4.5, 193, .32), "water", coll, .45)
    box("Axis_Causeway_EW", (0, 0, 5.25), (316, 6.4, .75), "sandstone_light", coll, .34)
    box("Axis_Causeway_NS", (0, 0, 5.28), (6.4, 246, .75), "sandstone_light", coll, .34)
    for x, y in [(-88, 58), (88, 58), (-88, -55), (88, -55)]:
        box(f"Temple_Pool_{x}_{y}", (x, y, 5.35), (22, 34, .28), "water", coll, .8)
    for index in range(100):
        x = RNG.uniform(-275, 275)
        y = RNG.choice((-208, 208, RNG.uniform(-195, 195)))
        if abs(x) < 130 and abs(y) < 105:
            continue
        cylinder(f"Lotus_{index:03d}", (x, y, 4.05), RNG.uniform(1.0, 2.4), .12,
                 "leaf_light" if index % 5 else "flower", coll, 10)


def build_temple() -> None:
    coll = bpy.data.collections.new("03_TempleMountain")
    bpy.context.scene.collection.children.link(coll)
    levels = [(112, 88, 6.2, 2.8), (91, 70, 11.8, 2.6), (70, 53, 17.0, 2.5),
              (50, 37, 22.1, 2.4), (31, 23, 27.0, 2.3)]
    for index, (sx, sy, z, half_height) in enumerate(levels):
        box(f"Temple_Terrace_{index}", (0, 7, z), (sx, sy, half_height),
            "sandstone" if index % 2 == 0 else "sandstone_light", coll, .65)
        for name, loc, scale, rotation in [
            ("N", (0, 7 + sy, z + 4.4), (sx + 2, 2.3, .72), 0),
            ("S", (0, 7 - sy, z + 4.4), (sx + 2, 2.3, .72), 0),
            ("E", (sx, 7, z + 4.4), (2.3, sy + 2, .72), math.pi / 2),
            ("W", (-sx, 7, z + 4.4), (2.3, sy + 2, .72), math.pi / 2),
        ]:
            box(f"Temple_Gallery_{index}_{name}", loc, scale, "roof", coll, .28, rotation)
        for x in range(int(-sx + 10), int(sx - 8), 12):
            for sign in (-1, 1):
                box(f"Temple_Niche_{index}_{sign}_{x}", (x, 7 + sign * (sy - 1.4), z + 3.7),
                    (1.25, 1.35, 3.55), "sandstone_light", coll, .18)
        for y in range(int(7 - sy + 10), int(7 + sy - 8), 12):
            for sign in (-1, 1):
                box(f"Temple_NicheSide_{index}_{sign}_{y}", (sign * (sx - 1.4), y, z + 3.7),
                    (1.35, 1.25, 3.55), "sandstone_light", coll, .18)
    stair_run("Temple_Main_Stair", Vector((0, -57, 5.8)), Vector((0, 1, 0)), 18, 34, .72, 1.55, coll)
    stair_run("Temple_West_Stair", Vector((-112, 7, 5.8)), Vector((1, 0, 0)), 15, 32, .72, 1.75, coll)
    temple_tower("Temple_Centre", 0, 7, 31.2, 1.34, coll)
    for x, y, scale in [(-35, -16, .74), (35, -16, .74), (-35, 30, .74), (35, 30, .74),
                        (-75, 7, .58), (75, 7, .58)]:
        temple_tower(f"Temple_Tower_{x}_{y}", x, y, 26.4, scale, coll)


def gate(name: str, x: float, y: float, rotation: float, collection: bpy.types.Collection) -> None:
    box(f"{name}_mass", (x, y, 16.2), (18.5, 8.2, 11.2), "laterite", collection, .62, rotation)
    for offset in (-8.2, 0, 8.2):
        px = x + math.cos(rotation) * offset
        py = y + math.sin(rotation) * offset
        box(f"{name}_passage_{offset}", (px, py, 12.6), (2.7, 9.2, 7.4),
            "sandstone_light", collection, .28, rotation)
        box(f"{name}_lintel_{offset}", (px, py, 21.3), (3.45, 2.0, 1.0), "sandstone", collection, .22,
            rotation)
    for sign in (-1, 1):
        offset = sign * 16.5
        px = x + math.cos(rotation) * offset
        py = y + math.sin(rotation) * offset
        box(f"{name}_tower_{sign}", (px, py, 18.5), (5.8, 5.8, 13.5), "laterite", collection, .5, rotation)
        khmer_roof(f"{name}_towerroof_{sign}", px, py, 31.8, 15.5, 15.5, 5.4, rotation, collection, True)
    khmer_roof(f"{name}_roof", x, y, 28.2, 43, 18.5, 6.2, rotation, collection, True)


def wall_tower(name: str, x: float, y: float, collection: bpy.types.Collection) -> None:
    box(f"{name}_base", (x, y, 13.2), (7.2, 7.2, 11.2), "laterite", collection, .5)
    box(f"{name}_gallery", (x, y, 25.2), (9.3, 9.3, 1.65), "sandstone", collection, .35)
    khmer_roof(f"{name}_roof", x, y, 27.1, 20, 20, 6.4, 0, collection, True)


def build_gates_walls() -> None:
    coll = bpy.data.collections.new("04_GatesAndWalls")
    bpy.context.scene.collection.children.link(coll)
    for name, loc, scale, rotation in [
        ("InnerWall_NW", (-64, 104, 13), (52, 3.8, 10), 0),
        ("InnerWall_NE", (64, 104, 13), (52, 3.8, 10), 0),
        ("InnerWall_SW", (-64, -104, 13), (52, 3.8, 10), 0),
        ("InnerWall_SE", (64, -104, 13), (52, 3.8, 10), 0),
        ("InnerWall_EN", (116, 56, 13), (3.8, 44, 10), math.pi / 2),
        ("InnerWall_ES", (116, -56, 13), (3.8, 44, 10), math.pi / 2),
        ("InnerWall_WN", (-116, 56, 13), (3.8, 44, 10), math.pi / 2),
        ("InnerWall_WS", (-116, -56, 13), (3.8, 44, 10), math.pi / 2),
        ("OuterWall_NW", (-124, 190, 11.5), (112, 3.4, 8.8), 0),
        ("OuterWall_NE", (124, 190, 11.5), (112, 3.4, 8.8), 0),
        ("OuterWall_SW", (-124, -190, 11.5), (112, 3.4, 8.8), 0),
        ("OuterWall_SE", (124, -190, 11.5), (112, 3.4, 8.8), 0),
        ("OuterWall_EN", (236, 105, 11.5), (3.4, 81, 8.8), math.pi / 2),
        ("OuterWall_ES", (236, -105, 11.5), (3.4, 81, 8.8), math.pi / 2),
        ("OuterWall_WN", (-236, 105, 11.5), (3.4, 81, 8.8), math.pi / 2),
        ("OuterWall_WS", (-236, -105, 11.5), (3.4, 81, 8.8), math.pi / 2),
    ]:
        box(name, loc, scale, "laterite", coll, .48, rotation)
    gate("Gate_E", 116, 0, math.pi / 2, coll)
    gate("Gate_W", -116, 0, math.pi / 2, coll)
    gate("Gate_N", 0, 104, 0, coll)
    gate("Gate_S", 0, -104, 0, coll)
    gate("OuterGate_E", 236, 0, math.pi / 2, coll)
    gate("OuterGate_W", -236, 0, math.pi / 2, coll)
    gate("OuterGate_N", 0, 190, 0, coll)
    gate("OuterGate_S", 0, -190, 0, coll)
    positions = []
    for x in (-236, -118, 118, 236):
        positions.extend([(x, -190), (x, 190)])
    for y in (-190, -95, 95, 190):
        positions.extend([(-236, y), (236, y)])
    positions.extend([(-116, -104), (116, -104), (-116, 104), (116, 104)])
    for index, (x, y) in enumerate(positions):
        wall_tower(f"WallTower_{index:02d}", x, y, coll)
    for axis in ("x", "y"):
        for sign in (-1, 1):
            for index in range(1, 7):
                distance = index * 38
                x, y = ((sign * distance, 0) if axis == "x" else (0, sign * distance))
                cylinder(f"Causeway_Lantern_{axis}_{sign}_{index}", (x, y, 8.3), .72, 5.2,
                         "sandstone_light", coll, 9)
                cone(f"Causeway_Flame_{axis}_{sign}_{index}", (x, y, 11.6), 1.12, .25, 2.5,
                     "lantern", coll, 9)


def build_city() -> None:
    coll = bpy.data.collections.new("05_MarketAndHousing")
    bpy.context.scene.collection.children.link(coll)
    zones = []
    for y in range(-168, 169, 38):
        for x in range(142, 225, 32):
            zones.append((x + RNG.uniform(-3, 3), y + RNG.uniform(-4, 4), math.pi / 2))
    for y in (-171, -145):
        for x in range(-215, 216, 34):
            if abs(x) >= 128:
                zones.append((x + RNG.uniform(-3, 3), y, 0))
    for y in (138, 166):
        for x in range(-215, 216, 34):
            if abs(x) >= 128:
                zones.append((x + RNG.uniform(-3, 3), y, 0))
    for y in range(-145, 146, 38):
        for x in (-284, -264, 270, 290):
            zones.append((x, y + RNG.uniform(-4, 4), math.pi / 2))
    for index, (x, y, rotation) in enumerate(zones):
        house(f"House_{index:03d}", x, y, rotation, RNG.uniform(13.5, 20.5),
              RNG.uniform(10.5, 15.5), coll, index % 9 == 0)
    for index, (x, y, rotation) in enumerate([
        (165, -118, 0), (202, -118, 0), (165, -67, 0), (202, -67, 0),
        (165, 67, math.pi / 2), (202, 67, math.pi / 2), (-185, 122, 0), (-222, 122, 0),
    ]):
        market_hall(f"MarketHall_{index}", x, y, rotation, coll)


def build_jungle() -> None:
    coll = bpy.data.collections.new("06_Jungle")
    bpy.context.scene.collection.children.link(coll)
    points = []
    for _ in range(270):
        x, y = RNG.uniform(-326, 326), RNG.uniform(-258, 258)
        if abs(x) >= 265 or abs(y) >= 218:
            points.append((x, y))
    for x in (-314, -292, 292, 314):
        for y in range(-242, 243, 27):
            points.append((x + RNG.uniform(-7, 7), y + RNG.uniform(-9, 9)))
    for index, (x, y) in enumerate(points):
        tree(f"JungleTree_{index:03d}", x, y, 3.0, RNG.uniform(.72, 1.62), coll, index % 19 == 0)
    inner = []
    for x in (-222, -188, -155, -121, 121, 155, 188, 222):
        for y in range(-178, 179, 31):
            inner.append((x + RNG.uniform(-5, 5), y + RNG.uniform(-8, 8)))
    for y in (-151, -120, 118, 151):
        for x in range(-105, 106, 29):
            inner.append((x + RNG.uniform(-4, 4), y + RNG.uniform(-4, 4)))
    for index, (x, y) in enumerate(inner):
        tree(f"CityGrove_{index:03d}", x, y, 5.4, RNG.uniform(.55, .92), coll, index % 13 == 0)
    for index, (x, y) in enumerate([(-302, -142), (-298, 126), (298, -154), (303, 153),
                                    (-166, 239), (169, -239), (-274, 226), (276, 226)]):
        tree(f"GuardianFig_{index}", x, y, 3.1, 2.35, coll, index % 2 == 0)


def build_props() -> None:
    coll = bpy.data.collections.new("07_PropsAndShrines")
    bpy.context.scene.collection.children.link(coll)
    for index in range(32):
        angle = index * math.tau / 32
        shrine(f"ProcessionalShrine_{index:02d}", math.cos(angle) * 96,
               7 + math.sin(angle) * 77, RNG.uniform(.72, 1.08), coll)
    for index in range(52):
        if index < 26:
            x, y = -232 + index * 18.5, RNG.choice((-198, 198))
        else:
            x, y = RNG.choice((-244, 244)), -174 + (index - 26) * 14.2
        cylinder(f"PromenadeLantern_{index:02d}", (x, y, 7.2), .58, 4.4, "sandstone_light", coll, 9)
        cone(f"PromenadeFlame_{index:02d}", (x, y, 10.1), .86, .18, 1.9, "lantern", coll, 9)


def load_hero_assets() -> None:
    if not HERO_MODELS.is_dir():
        return
    coll = bpy.data.collections.new("08_HeroAssets")
    bpy.context.scene.collection.children.link(coll)
    placements = {
        "hero_prang": ((0, 7, 28), 34, 0),
        "monumental_gate": ((0, -190, 3), 43, 0),
        "naga_bridge": ((0, -228, 3.6), 34, 0),
        "reservoir_pavilion": ((-218, 83, 3.2), 18, 0),
        "market_hall": ((183, -138, 5.2), 38, math.pi / 2),
        "guardian_statue": ((-7, -230, 3.8), 10, 0),
        "great_fig_tree": ((-302, 128, 2.6), 31, 0),
        "stilt_house": ((273, 88, 3.0), 17, math.pi / 2),
    }
    for slug, (location, target_height, rotation) in placements.items():
        source = HERO_MODELS / f"{slug}.glb"
        if not source.is_file():
            continue
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=str(source))
        imported = list(set(bpy.data.objects) - before)
        meshes = [obj for obj in imported if obj.type == "MESH"]
        if not meshes:
            continue
        bounds = [obj.matrix_world @ Vector(corner) for obj in meshes for corner in obj.bound_box]
        minimum = Vector((min(p.x for p in bounds), min(p.y for p in bounds), min(p.z for p in bounds)))
        maximum = Vector((max(p.x for p in bounds), max(p.y for p in bounds), max(p.z for p in bounds)))
        factor = target_height / max(maximum.z - minimum.z, .001)
        root = bpy.data.objects.new(f"Hero_{slug}", None)
        coll.objects.link(root)
        root.empty_display_type = "PLAIN_AXES"
        for obj in imported:
            if obj.parent is None:
                obj.parent = root
        root.scale = (factor, factor, factor)
        root.rotation_euler[2] = rotation
        root.location = (location[0] - (minimum.x + maximum.x) * .5 * factor,
                         location[1] - (minimum.y + maximum.y) * .5 * factor,
                         location[2] - minimum.z * factor)


def join_collection(collection: bpy.types.Collection) -> int:
    objects = [obj for obj in collection.all_objects if obj.type == "MESH"]
    triangles = sum(sum(len(p.vertices) - 2 for p in obj.data.polygons) for obj in objects)
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    if objects:
        bpy.context.view_layer.objects.active = objects[0]
        bpy.ops.object.join()
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.cube_project(cube_size=6.0, correct_aspect=True, scale_to_bounds=False)
        bpy.ops.object.mode_set(mode="OBJECT")
    return triangles


def export_module(slug: str, collection_name: str) -> dict:
    collection = bpy.data.collections[collection_name]
    triangles = join_collection(collection)
    objects = list(collection.all_objects)
    if not objects:
        raise RuntimeError(f"module {slug} is empty")
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    path = OUT / f"{slug}.glb"
    bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_selection=True,
                              export_apply=True, export_yup=True, export_materials="EXPORT")
    blend = OUT / f"{slug}.blend"
    bpy.data.libraries.write(str(blend), {collection}, fake_user=True, compress=True)
    return {"model": str(path.relative_to(REPO)), "blend": str(blend.relative_to(REPO)),
            "objects": len(objects), "triangles": triangles, "bytes": path.stat().st_size}


MODULES = [
    ("terrain", "01_Terrain"), ("waterworks", "02_Waterworks"),
    ("temple_mountain", "03_TempleMountain"), ("gates_and_walls", "04_GatesAndWalls"),
    ("market_district", "05_MarketAndHousing"), ("jungle", "06_Jungle"),
    ("props_and_shrines", "07_PropsAndShrines"), ("hero_assets", "08_HeroAssets"),
]


def assemble() -> dict:
    reset()
    setup_materials()
    for slug, _ in MODULES:
        path = OUT / f"{slug}.glb"
        if path.is_file():
            bpy.ops.import_scene.gltf(filepath=str(path))
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
    setup_materials()
    stages = (
        ("terrain", build_terrain), ("waterworks", build_waterworks),
        ("temple", build_temple), ("gates and walls", build_gates_walls),
        ("market and housing", build_city), ("jungle", build_jungle),
        ("props", build_props), ("hero assets", load_hero_assets),
    )
    for name, builder in stages:
        print(f"JUNGLE CITY STAGE {name}", flush=True)
        builder()
    print("JUNGLE CITY STAGE module export", flush=True)
    modules = []
    for slug, collection_name in MODULES:
        collection = bpy.data.collections.get(collection_name)
        if collection and collection.all_objects:
            modules.append(dict(slug=slug, **export_module(slug, collection_name)))
    print("JUNGLE CITY STAGE assemble", flush=True)
    assembled = assemble()
    manifest = {
        "schema": 2, "proposal": "Jungle City", "status": "unplaced-review-only",
        "extent_metres": [670, 540], "modules": modules, "assembled": assembled,
        "generator": "games/yorimichi/world/regions/jungle_city/build.py",
        "blender_version": bpy.app.version_string,
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("JUNGLE CITY BUILD COMPLETE", flush=True)
    print(json.dumps(manifest, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
