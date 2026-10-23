#!/usr/bin/env python3
"""Build the Sunburst-textured procedural Kasa Ronin equipment and Roadside Mini-Camp meshes in Blender.

Exports:
- build/yorimichi/swordcamp/fbx/SM_*.fbx (with UCX collision boxes for camp props)
- build/yorimichi/swordcamp/site/*.glb (for the Three.js viewer)
- build/yorimichi/swordcamp/site/render_*.png (studio comparison renders)
"""
import json
import math
import random
import sys
from pathlib import Path

import bpy
from mathutils import Euler, Matrix, Vector

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
sys.path.insert(0, str(HERE.parents[1]))
import yori  # noqa: E402

OUT = yori.OUT / 'swordcamp'
ATLAS_PATH = OUT / 'swordcamp_atlas.jpg'
FBX_DIR = OUT / 'fbx'
SITE_ASSETS = OUT / 'site'


from swordcamp.mesh import ProcMesh
from swordcamp.parts.kasa import build_kasa
from swordcamp.parts.jingasa import build_jingasa
from swordcamp.parts.kabuto import build_kabuto
from swordcamp.parts.menpo import build_menpo
from swordcamp.parts.do import build_do
from swordcamp.parts.sode import build_sode
from swordcamp.parts.sashimono import build_sashimono
from swordcamp.parts.sword import build_sword
from swordcamp.parts.jinmaku import build_jinmaku
from swordcamp.parts.firepit import build_firepit
from swordcamp.parts.weapon_rack_clean import build_weapon_rack_clean
from swordcamp.parts.bales_and_chest import build_bales_and_chest

def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def make_material():
    m = bpy.data.materials.new('M_SwordCamp')
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes['Principled BSDF']
    bsdf.inputs['Roughness'].default_value = 0.88
    bsdf.inputs['Specular IOR Level'].default_value = 0.08
    tex = nt.nodes.new('ShaderNodeTexImage')
    tex.image = bpy.data.images.load(str(ATLAS_PATH))
    nt.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
    nt.nodes.active = tex
    return m


def export_fbx_and_glb(proc: ProcMesh, mat, fbx_name=None, glb_name=None):
    clear_scene()
    m = make_material()
    obj = proc.to_blender(m)
    objs = [obj]
    if fbx_name:
        for idx, (cc, cs) in enumerate(proc.colliders):
            bpy.ops.mesh.primitive_cube_add(size=1.0, location=cc)
            ucx = bpy.context.object
            ucx.name = f'UCX_{fbx_name}_{idx:02d}'
            ucx.scale = cs
            bpy.ops.object.transform_apply(scale=True)
            objs.append(ucx)
        bpy.ops.object.select_all(action='DESELECT')
        for o in objs:
            o.select_set(True)
        bpy.context.view_layer.objects.active = obj
        FBX_DIR.mkdir(parents=True, exist_ok=True)
        from atelier.blender.fbx import export_fbx as export_scene_fbx
        export_scene_fbx(
            filepath=str(FBX_DIR / f'{fbx_name}.fbx'),
            use_selection=True,
            apply_unit_scale=True,
            apply_scale_options='FBX_SCALE_ALL',
            axis_forward='-Y',
            axis_up='Z',
            object_types={'MESH'},
            mesh_smooth_type='FACE',
            bake_anim=False,
            use_custom_props=False,
            path_mode='STRIP',
        )
    if glb_name:
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        SITE_ASSETS.mkdir(parents=True, exist_ok=True)
        bpy.ops.export_scene.gltf(
            filepath=str(SITE_ASSETS / f'{glb_name}.glb'),
            use_selection=True,
            export_format='GLB',
            export_apply=True,
        )
    return len(obj.data.polygons)


def render_showcase(proc: ProcMesh, out_png: Path, cam_loc, cam_target, ortho_scale=None, res=(1536, 1024)):
    clear_scene()
    m = make_material()
    proc.to_blender(m)
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_WORKBENCH'
    sc.display.shading.light = 'STUDIO'
    sc.display.shading.color_type = 'TEXTURE'
    sc.display.shading.show_cavity = True
    sc.display.shading.cavity_type = 'BOTH'
    sc.display.shading.show_shadows = True
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.film_transparent = False
    world = bpy.data.worlds.new('StudioWorld')
    world.color = (0.76, 0.76, 0.77)
    sc.world = world
    cam_data = bpy.data.cameras.new('Cam')
    if ortho_scale:
        cam_data.type = 'ORTHO'
        cam_data.ortho_scale = ortho_scale
    else:
        cam_data.lens = 42
    cam = bpy.data.objects.new('Cam', cam_data)
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.location = Vector(cam_loc)
    cam.rotation_euler = (Vector(cam_target) - cam.location).to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = str(out_png)
    bpy.ops.render.render(write_still=True)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    FBX_DIR.mkdir(parents=True, exist_ok=True)
    assert ATLAS_PATH.is_file(), f'Missing {ATLAS_PATH}; run world.swordcamp_atlas first'
    showcase = '--showcase' in sys.argv
    manifest = {}
    assets = [
        ('SM_RoninKasa', lambda m: build_kasa(m)),
        ('SM_GuardJingasa', lambda m: build_jingasa(m)),
        ('SM_CaptainKabuto', lambda m: build_kabuto(m)),
        ('SM_RoninMenpo', lambda m: build_menpo(m)),
        ('SM_RoninDo', lambda m: build_do(m)),
        ('SM_RoninSode', lambda m: build_sode(m)),
        ('SM_RoninSashimono', lambda m: build_sashimono(m)),
        ('SM_RoninKatana', lambda m: build_sword(m, blade_len=0.72, hilt_len=0.24, curve=0.030, sheathed=False)),
        ('SM_RoninNodachi', lambda m: build_sword(m, blade_len=1.06, hilt_len=0.34, curve=0.046, sheathed=False)),
        ('SM_RoninWakizashi', lambda m: build_sword(m, blade_len=0.46, hilt_len=0.16, curve=0.018, sheathed=True, red_saya=False)),
        ('SM_CampJinmaku', lambda m: build_jinmaku(m)),
        ('SM_CampFirePit', lambda m: build_firepit(m)),
        ('SM_CampWeaponRack', lambda m: build_weapon_rack_clean(m)),
        ('SM_CampBales', lambda m: build_bales_and_chest(m)),
    ]
    for name, fn in assets:
        pm = ProcMesh(name)
        fn(pm)
        polys = export_fbx_and_glb(pm, None, fbx_name=name, glb_name=name.lower() if showcase else None)
        manifest[name] = {'polygons': polys, 'colliders': len(pm.colliders)}
        print(f'[swordcamp] Built {name}: {polys} polygons, {len(pm.colliders)} colliders', flush=True)

    if showcase:
        SITE_ASSETS.mkdir(parents=True, exist_ok=True)
        kit_ronin = ProcMesh('RoninArmorKit')
        build_kasa(kit_ronin, origin=(-0.72, 0.0, 0.45))
        build_jingasa(kit_ronin, origin=(0.0, 0.0, 0.45))
        build_kabuto(kit_ronin, origin=(0.68, 0.0, 0.45))
        old = kit_ronin.push((-0.72, -0.05, -0.02), rot=(0, 0, -90), scale=(1.28, 1.28, 1.28))
        build_menpo(kit_ronin)
        kit_ronin.xf = old
        old = kit_ronin.push((0.0, 0.0, -0.05), rot=(0, 0, -90))
        build_do(kit_ronin)
        kit_ronin.xf = old
        old = kit_ronin.push((-0.38, 0.0, -0.04), rot=(0, -8, -72))
        build_sode(kit_ronin)
        kit_ronin.xf = old
        old = kit_ronin.push((0.38, 0.0, -0.04), rot=(0, 8, -108))
        build_sode(kit_ronin)
        kit_ronin.xf = old
        old = kit_ronin.push((0.82, 0.0, -0.32), rot=(0, 0, 0))
        build_sashimono(kit_ronin)
        kit_ronin.xf = old
        old = kit_ronin.push((-0.68, 0.0, -0.34), rot=(0, 90, 0))
        build_sword(kit_ronin, blade_len=0.72, hilt_len=0.24, curve=0.030, sheathed=False)
        kit_ronin.xf = old
        old = kit_ronin.push((-0.74, 0.0, -0.50), rot=(0, 90, 0))
        build_sword(kit_ronin, blade_len=1.06, hilt_len=0.34, curve=0.046, sheathed=False)
        kit_ronin.xf = old
        export_fbx_and_glb(kit_ronin, None, glb_name='ronin_kit_scene')
        render_showcase(kit_ronin, SITE_ASSETS / 'render_ronin_kit.png', cam_loc=(0.0, -2.9, 0.15), cam_target=(0.0, 0.0, 0.10), ortho_scale=2.45)

        kit_camp = ProcMesh('CampPropsKit')
        old = kit_camp.push((-1.45, 0.55, 0.35), rot=(0, 0, 18), scale=(0.68, 0.68, 0.68))
        build_jinmaku(kit_camp)
        kit_camp.xf = old
        old = kit_camp.push((1.35, 0.45, 0.35), scale=(0.85, 0.85, 0.85))
        build_firepit(kit_camp)
        kit_camp.xf = old
        old = kit_camp.push((-1.35, -0.65, -0.95), rot=(0, 0, -68), scale=(0.88, 0.88, 0.88))
        build_weapon_rack_clean(kit_camp)
        kit_camp.xf = old
        old = kit_camp.push((1.25, -0.65, -0.88), rot=(0, 0, -14), scale=(0.95, 0.95, 0.95))
        build_bales_and_chest(kit_camp)
        kit_camp.xf = old
        export_fbx_and_glb(kit_camp, None, glb_name='camp_kit_scene')
        render_showcase(kit_camp, SITE_ASSETS / 'render_camp_kit.png', cam_loc=(0.0, -6.2, 2.45), cam_target=(0.0, 0.0, 0.10), ortho_scale=5.75)

    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print('SWORDCAMP PROCEDURAL BUILD COMPLETE', flush=True)


if __name__ == '__main__':
    main()
