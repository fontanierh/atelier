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
    "master-aerial": ((505, 455, 385), (0, 14, 0)),
    "east-causeway": ((315, 118, 82), (108, 8, 8)),
    "temple-mountain": ((188, 142, 122), (0, 34, 18)),
    "market-terraces": ((315, -248, 122), (176, -12, 16)),
    "baray-reservoir": ((-392, -242, 168), (-206, -12, 11)),
    "main-gate": ((22, -302, 88), (0, -184, 19)),
    "stone-bridges": ((126, -282, 73), (0, -220, 8)),
    "play-scale-check": ((252, -238, 98), (0, 0, 28)),
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
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.43, 0.61, 0.64, 1)
    world.node_tree.nodes["Background"].inputs[1].default_value = 0.72
    scene.world = world
    sun_data = bpy.data.lights.new("Review sun", "SUN")
    sun_data.energy = 4.4
    sun_data.angle = math.radians(4)
    sun = bpy.data.objects.new("Review sun", sun_data)
    scene.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(48), 0, math.radians(-32))
    fill_data = bpy.data.lights.new("Sky fill", "AREA")
    fill_data.energy = 1850
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
