"""Hidamari's Tripo street props into game meshes (Blender, headless).

    atelier build yorimichi world.hidamari_props

For every prop in tools/hidamari_props.py with a GLB in assets/hidamari/props/<slug>/, the tree house's steps
(world/regions/treehouse/props.py fit): turned so its front faces -y (TURN), its longest side scaled to its size in
metres, stood on z = 0 centred on its footprint, white vertex colours, one material slot and a collision box for the
solid ones. Writes build/yorimichi/hidamari/props/HD_P_<slug>.fbx and .png (its texture), four check views each, and
props.json (gain: the texture's mean brightness brought to TARGET). layout.py places them (HD_P_<slug> in city.json).

The caldera's four conifers (craterpark/v2/trees.py) are fitted the same way, upright to their height, with no
collision, plus their distance LODs: <key>_LOD<n>.fbx, LOD0 welded or remeshed and decimated to each share of its
triangles, each still standing on its root (trees.py LODS, BASE, FLOAT; props.json `lods`: [triangles, screen size]
per LOD) and lods-<key>.png, LOD0 to the last side by side. import_hidamari.py imports them with the props; the crater floor (craterpark/v2/editor_floor.py) plants
them through park.json `trees`.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2])); import yori  # noqa: E402,F401
import json, math, sys
sys.path.insert(0, str(yori.GAME/'tools'))
from hidamari_props import PROPS, OUT as SRC
from treehouse import props as kit
from craterpark.v2 import trees as caldera

OUT = yori.OUT/'hidamari'/'props'
# degrees about z applied after import so the prop's front faces -y (checked on the views)
TURN = {s: -90 for s in ('kei_truck', 'vending_machine', 'bus_stop', 'garbage_station', 'jizo', 'komainu', 'potted_plants',
                         'produce_stand', 'sake_barrels', 'water_basin', 'ac_unit', 'propane_tanks', 'hokora', 'tanuki',
                         'fire_buckets', 'drink_crates', 'planter_box', 'laundry_stand', 'street_bench', 'bonsai_shelf',
                         'yatai', 'kei_car', 'taxi', 'town_bus', 'bicycle_shelter')}
TURN['curve_mirror'] = 180
# the palette brightness (linear luminance) each prop's texture is brought to; .07 unless given
TARGET = dict(vending_machine=.16, postbox=.06, stone_lantern=.10, komainu=.10, jizo=.08, water_basin=.08,
              phone_booth=.10, kei_truck=.18, scooter=.12, ac_unit=.15, propane_tanks=.11, laundry_stand=.12,
              curve_mirror=.09, kei_car=.16, taxi=.09, town_bus=.12, bicycle_shelter=.08, lantern_sign=.09,
              # the wooden ones mostly stand in shade (garden gaps, lot seams, under their own roofs)
              hokora=.09, tanuki=.09, planter_box=.09, yatai=.09, drink_crates=.09, fire_buckets=.09, bonsai_shelf=.09)
SOLID = {'vending_machine', 'kei_truck', 'postbox', 'phone_booth', 'stone_lantern', 'komainu', 'jizo', 'water_basin',
         'sake_barrels', 'produce_stand', 'garbage_station', 'bus_stop', 'ac_unit', 'propane_tanks', 'hokora', 'tanuki',
         'fire_buckets', 'drink_crates', 'planter_box', 'street_bench', 'bonsai_shelf', 'yatai', 'kei_car', 'taxi', 'town_bus',
         'bicycle_shelter', 'lantern_sign'}


def lods(key, info):
    """Build the original conifer chain and diagnostic lineup through the shared selected constructor."""
    import bpy
    from hidamari.prop_lod_geometry import make_lod
    src=bpy.data.objects[key];out=[[info['triangles'],caldera.LODS[0][1]]];objs=[src]
    settings={name:getattr(caldera,name) for name in ('LODS','SHELL','BASE','FLOAT')}
    for n in range(1,len(caldera.LODS)):
        obj,row=make_lod(src,info,key,n,settings)
        assert row[0]<out[-1][0],(key,n,row,out)
        bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);bpy.context.view_layer.objects.active=obj
        from atelier.blender.fbx import export_fbx
        export_fbx(filepath=str(OUT/f'{obj.name}.fbx'),use_selection=True,apply_unit_scale=True,
            apply_scale_options='FBX_SCALE_ALL',axis_forward='-Y',axis_up='Z',object_types={'MESH'},
            mesh_smooth_type='FACE',bake_anim=False,use_custom_props=False,path_mode='STRIP')
        out.append(row);objs.append(obj)
    lineup(key,objs)
    return out

def lineup(key, objs):
    """lods-<key>.png: the LODs side by side, textured, from the front (a check that the last keeps the silhouette)."""
    import bpy
    from mathutils import Vector
    sc = bpy.context.scene
    img = bpy.data.images.load(str(OUT/f'{key}.png'), check_existing=True)
    mat = objs[0].data.materials[0]; mat.use_nodes = True; nt = mat.node_tree
    t = nt.nodes.new('ShaderNodeTexImage'); t.image = img
    nt.links.new(t.outputs['Color'], nt.nodes['Principled BSDF'].inputs['Base Color']); nt.nodes.active = t
    hi = max(o.dimensions.z for o in objs); step = max(max(o.dimensions.x, o.dimensions.y) for o in objs)*1.1
    for i, o in enumerate(objs): o.location.x = i*step
    sc.render.resolution_x, sc.render.resolution_y = 300*len(objs), 360
    cam = bpy.data.objects.new('lineup', bpy.data.cameras.new('lineup')); sc.collection.objects.link(cam); sc.camera = cam
    cam.data.type = 'ORTHO'; cam.data.ortho_scale = max(step*len(objs), hi*len(objs)*300/360)*1.02
    mid = Vector(((len(objs)-1)*step/2, 0, hi/2)); cam.location = mid+Vector((0, -40, 0)); cam.rotation_euler = (math.pi/2, 0, 0)
    sc.render.filepath = str(OUT/f'lods-{key}.png'); bpy.ops.render.render(write_still=True)
    for o in objs: o.location.x = 0
    bpy.data.objects.remove(cam); nt.nodes.remove(t)


def main():
    report = {}
    for slug, (_, size) in PROPS.items():
        glb = SRC/slug/f'{slug}.glb'
        if not glb.exists(): continue
        key, info = kit.fit(slug, glb, f'HD_P_{slug}', size, TURN.get(slug, 0.), TARGET.get(slug, .07), slug in SOLID, OUT)
        report[key] = info; print(key, info, flush=True)
    for key, (folder, _, height, crown) in caldera.TREES.items():
        key, info = kit.fit(folder, caldera.source(key), key, height, 0., caldera.TARGET, False, OUT, upright=True)
        # editor_floor keeps the riding clear by caldera.TREES' crown: the model must not reach farther.
        assert info['crown'] <= crown*1.02, (key, 'crown reaches', info['crown'], 'over', crown)
        info['lods'] = lods(key, info)
        report[key] = info; print(key, info, flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/'props.json').write_text(json.dumps(report, indent=1)+'\n')
    print('HIDAMARI PROPS COMPLETE', len(report), flush=True)


if __name__ == '__main__':
    main()
