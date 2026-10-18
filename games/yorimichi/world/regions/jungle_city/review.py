"""Render reproducible headless comparison views from the assembled Jungle City model."""
from __future__ import annotations

import json
import math
from pathlib import Path

import bpy
from mathutils import Vector


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
MODEL = REPO / "build" / "yorimichi" / "jungle-city" / "models" / "JungleCity.blend"
OUT = REPO / "build" / "yorimichi" / "jungle-city" / "reviews"
VIEWS = {
    "master-aerial": ((535, 515, 575), (0, 12, 0)),
    "east-causeway": ((390, 112, 116), (112, 8, 5)),
    "temple-mountain": ((215, 176, 182), (0, 34, 12)),
    "market-terraces": ((355, -338, 192), (178, -18, 18)),
    "baray-reservoir": ((-452, -282, 238), (-218, -18, 12)),
    "main-gate": ((18, -356, 122), (0, -188, 18)),
    "stone-bridges": ((148, -338, 88), (0, -224, 9)),
    "play-scale-check": ((305, -292, 142), (0, 0, 34)),
}


def look_at(obj, target: Vector) -> None:
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(MODEL))
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 800
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    world = bpy.data.worlds.new("Jungle City review sky")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.27, 0.42, 0.44, 1)
    world.node_tree.nodes["Background"].inputs[1].default_value = 0.28
    scene.world = world
    sun_data = bpy.data.lights.new("Review sun", "SUN")
    sun_data.energy = 3.2
    sun_data.angle = math.radians(4)
    sun = bpy.data.objects.new("Review sun", sun_data)
    scene.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(48), 0, math.radians(-32))
    fill_data = bpy.data.lights.new("Sky fill", "AREA")
    fill_data.energy = 1250
    fill_data.shape = "DISK"
    fill_data.size = 350
    fill = bpy.data.objects.new("Sky fill", fill_data)
    scene.collection.objects.link(fill)
    fill.location = (0, 0, 280)
    camera_data = bpy.data.cameras.new("Review camera")
    camera_data.lens = 42
    camera = bpy.data.objects.new("Review camera", camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    scene.view_settings.look = "AgX - Medium High Contrast"
    for name, (position, target) in VIEWS.items():
        camera.location = position
        look_at(camera, Vector(target))
        scene.render.filepath = str(OUT / f"{name}.png")
        bpy.ops.render.render(write_still=True)
        print(f"RENDERED {name}", flush=True)
    (OUT / "views.json").write_text(json.dumps({"schema": 1, "views": VIEWS}, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
