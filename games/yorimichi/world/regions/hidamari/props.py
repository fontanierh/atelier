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
    """The fitted tree (the scene's object `key`, as fit exported it) reduced to each of caldera.LODS after the first
    ('weld' or 'shell', trees.py), each exported as <key>_LOD<n>.fbx with LOD0's material slot, UVs and white vertex
    colours; then the lineup picture."""
    import bpy, bmesh
    src = bpy.data.objects[key]
    out, objs = [[info['triangles'], caldera.LODS[0][1]]], [src]

    def tris(obj):
        return sum(len(p.vertices)-2 for p in obj.data.polygons)

    def apply(obj, mod):
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier=mod.name)

    def decimate(obj, share):
        """Collapse obj to `share` of LOD0's triangles."""
        mod = obj.modifiers.new('decimate', 'DECIMATE'); mod.decimate_type = 'COLLAPSE'; mod.use_collapse_triangulate = True
        mod.ratio = min(1., share*info['triangles']/max(tris(obj), 1)); apply(obj, mod)
    for n, (share, screen, how) in enumerate(caldera.LODS[1:], 1):
        bpy.ops.object.select_all(action='DESELECT')
        obj = src.copy(); obj.data = src.data.copy(); bpy.context.scene.collection.objects.link(obj)
        obj.name = obj.data.name = f'{key}_LOD{n}'
        bm = bmesh.new(); bm.from_mesh(obj.data)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4); bm.to_mesh(obj.data); bm.free()
        if how == 'shell':
            h = src.dimensions.z
            mod = obj.modifiers.new('shell', 'SOLIDIFY'); mod.thickness = caldera.SHELL[0]*h; mod.offset = 0; apply(obj, mod)
            mod = obj.modifiers.new('remesh', 'REMESH'); mod.mode = 'VOXEL'; mod.voxel_size = caldera.SHELL[1]*h
            mod.adaptivity = 0; apply(obj, mod)
            obj.data.materials.clear(); obj.data.materials.append(src.data.materials[0])
            # the trunk below BASE[0] of the height decimated on its own, to BASE[1] of the triangles, then joined
            bm = bmesh.new(); bm.from_mesh(obj.data)
            bmesh.ops.bisect_plane(bm, geom=bm.verts[:]+bm.edges[:]+bm.faces[:], plane_co=(0, 0, caldera.BASE[0]*h),
                                   plane_no=(0, 0, 1))
            bm.to_mesh(obj.data); bm.free()
            bpy.ops.object.select_all(action='DESELECT'); obj.select_set(True); bpy.context.view_layer.objects.active = obj
            bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='DESELECT'); bpy.ops.object.mode_set(mode='OBJECT')
            for p in obj.data.polygons: p.select = p.center.z < caldera.BASE[0]*h
            bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.separate(type='SELECTED'); bpy.ops.object.mode_set(mode='OBJECT')
            base, = [o for o in bpy.context.selected_objects if o is not obj]
            decimate(base, caldera.BASE[1]*share); decimate(obj, (1-caldera.BASE[1])*share)
            bpy.ops.object.select_all(action='DESELECT'); obj.select_set(True); base.select_set(True)
            bpy.context.view_layer.objects.active = obj; bpy.ops.object.join()
        else:
            decimate(obj, share)
        if how == 'shell':
            obj.data.uv_layers.new(name=src.data.uv_layers.active.name)
            mod = obj.modifiers.new('uv', 'DATA_TRANSFER'); mod.object = src; mod.use_loop_data = True
            mod.data_types_loops = {'UV'}; mod.loop_mapping = 'POLYINTERP_NEAREST'; apply(obj, mod)
            col = obj.data.color_attributes.new(name='Color', type='FLOAT_COLOR', domain='POINT')
            col.data.foreach_set('color', [1., 1., 1., 0.]*len(obj.data.vertices))
        assert tris(obj) < out[-1][0] and len(obj.data.materials) == 1, (key, n, tris(obj), out)
        # still standing on its root (the planting sinks each tree TREE_SINK into the ground)
        low = min(v.co.z for v in obj.data.vertices)
        assert low < caldera.FLOAT, (key, n, 'stands', low, 'above the ground')
        obj.select_set(True); bpy.context.view_layer.objects.active = obj
        bpy.ops.export_scene.fbx(filepath=str(OUT/f'{obj.name}.fbx'), use_selection=True, apply_unit_scale=True,
                                 apply_scale_options='FBX_SCALE_ALL', axis_forward='-Y', axis_up='Z', object_types={'MESH'},
                                 mesh_smooth_type='FACE', bake_anim=False, use_custom_props=False, path_mode='STRIP')
        out.append([tris(obj), screen]); objs.append(obj)
    lineup(key, objs)
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
        key, info = kit.fit(slug, glb, f'HD_P_{slug}', size, TURN.get(slug, 0.), TARGET.get(slug, .07), slug in SOLID, OUT, foliage=slug in {'planter_box','bonsai_shelf','potted_plants'})
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
