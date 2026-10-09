"""Build the original scene, supporting ground and access into /Game/CommunityPark.

Geometry is batched by the shared source meshes without changing placements. Those rendered pieces do not block:
the skate rides one hidden collision mesh of the same triangles, welded across placements with the joint lips ramped
(collision.py).
The zero-area source triangles (source.json counts them) are omitted explicitly for
Unreal import; the committed source retains them. No other render face is removed or simplified.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import yori
from collections import Counter
import hashlib
import json
import shutil
import bpy
import numpy as np
from communitypark import layout as L
from communitypark.source import scene, SPEC
from communitypark.rails import paths
from communitypark.structures import SLENDER, build as build_structures
from communitypark.collision import riding_collision
from communitypark.murals import PANELS, build as build_murals
from communitypark.props import build as build_props
from hidamari.layout import north_surface
from hidamari.mountains import colours

OUT = yori.OUT / 'communitypark'
# The authored surfaces beside the source slots; materials.json carries them all to the Unreal import.
AUTHORED = [{'slot': 'CP_StructureSteel', 'colour': [.019, .034, .168], 'roughness': .6, 'metallic': .15},  # deep indigo once lit
            {'slot': 'CP_ServiceTimber', 'file': 'service-wood.jpg', 'roughness': .82, 'metallic': 0.}]
AUTHORED += [{'slot': 'CP_Mural_'+name.title(), 'file': f'mural-{name}.png', 'roughness': .8, 'metallic': 0., 'double_sided': True}
             for name in PANELS]


def mesh(name, vertices, faces, material, uv0=None, uv1=None, normals=None, colors=None):
    data = bpy.data.meshes.new(name)
    data.from_pydata(vertices, [], faces); data.update()
    obj = bpy.data.objects.new(name, data); bpy.context.collection.objects.link(obj)
    data.materials.append(material)
    for channel, values in enumerate((uv0, uv1)):
        layer = data.uv_layers.new(name=f'UV{channel}')
        for polygon in data.polygons:
            for loop_index, vertex_index in zip(polygon.loop_indices, polygon.vertices):
                u, v = values[vertex_index] if values is not None else (vertices[vertex_index][0]/2, vertices[vertex_index][1]/2)
                layer.data[loop_index].uv = (float(u), 1-float(v))
    if normals is not None:
        for polygon in data.polygons:
            polygon.use_smooth = True
        data.normals_split_custom_set_from_vertices(normals)
    if colors is not None:
        attr = data.color_attributes.new(name='Color', type='BYTE_COLOR', domain='CORNER')
        for polygon in data.polygons:
            for loop_index, vertex_index in zip(polygon.loop_indices, polygon.vertices):
                attr.data[loop_index].color = (*colors[vertex_index], 1.)
    return obj


def material(name, image=None, uv=None, colour=None, roughness=.5, metallic=0.):
    """A Principled material: an image map (on a named UV map, or the first) or a constant colour."""
    mat = bpy.data.materials.new(name); mat.use_nodes = True
    tree = mat.node_tree; bsdf = tree.nodes.get('Principled BSDF')
    if image is not None:
        tex = tree.nodes.new('ShaderNodeTexImage'); tex.image = bpy.data.images.load(str(image))
        if uv is not None:
            node = tree.nodes.new('ShaderNodeUVMap'); node.uv_map = uv; tree.links.new(node.outputs['UV'], tex.inputs['Vector'])
        tree.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
    if colour is not None:
        bsdf.inputs['Base Color'].default_value = (*colour, 1.)
    bsdf.inputs['Roughness'].default_value = roughness; bsdf.inputs['Metallic'].default_value = metallic
    return mat


def export(obj):
    bpy.ops.object.select_all(action='DESELECT'); obj.select_set(True); bpy.context.view_layer.objects.active = obj
    file = OUT / 'assets' / (obj.name+'.fbx')
    bpy.ops.export_scene.fbx(filepath=str(file), use_selection=True, apply_unit_scale=True,
                             apply_scale_options='FBX_SCALE_ALL', axis_forward='-Y', axis_up='Z',
                             object_types={'MESH'}, mesh_smooth_type='FACE', bake_anim=False)
    obj.data.calc_loop_triangles()
    used = np.unique([i for t in obj.data.loop_triangles for i in t.vertices])
    v = np.asarray([obj.data.vertices[int(i)].co[:] for i in used])
    return {'min': v.min(0).tolist(), 'max': v.max(0).tolist(), 'triangles': len(obj.data.loop_triangles),
            'sha256': hashlib.sha256(file.read_bytes()).hexdigest(),
            'material': obj.data.materials[0].name, 'uv_channels': len(obj.data.uv_layers)}


def source_materials(source):
    specs = source.write_textures(OUT / 'textures'); result = []
    # The restyle paints replace the library maps (tools/communitypark_textures.py).
    restyle = json.loads((OUT / 'restyle' / 'textures.json').read_text())
    for spec in specs:
        shutil.copyfile(OUT / 'restyle' / restyle[spec['name']]['png'], OUT / 'textures' / spec['file'])
        name = 'CP_'+spec['name'].replace('-', '_'); spec['slot'] = name
        result.append(material(name, OUT / 'textures' / spec['file'], 'UV1', roughness=spec['roughness'], metallic=spec['metallic']))
    # Authored additions: the cedar map is an existing Sunburst-authored project texture; murals use the restyle panels.
    shutil.copyfile(yori.ASSETS/'skatepark/textures/wood.jpg', OUT/'textures/service-wood.jpg')
    for name in PANELS:
        shutil.copyfile(OUT/'restyle'/f'panel-{name}.png', OUT/'textures'/f'mural-{name}.png')
    for spec in AUTHORED:
        result.append(material(spec['slot'], OUT/'textures'/spec['file'] if 'file' in spec else None, colour=spec.get('colour'),
                               roughness=spec['roughness'], metallic=spec['metallic']))
    (OUT / 'textures' / 'materials.json').write_text(json.dumps(specs+AUTHORED, indent=2)+'\n')
    return result


def build():
    (OUT / 'assets').mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    source = scene(); materials = source_materials(source); entries = []; report = {}
    spec = json.loads(SPEC.read_text()); skipped = 0

    def emit(name, vertices, faces, mat, *args, blocks=True, hidden=False, **options):
        obj = mesh(name, vertices, faces, mat, *args, **options)
        report[obj.name] = export(obj); entries.append({'name': obj.name, 'blocks': blocks} | ({'hidden': True} if hidden else {}))
    for index, item in enumerate(source.gltf['meshes']):
        vertices = []; normals = []; uv0 = []; uv1 = []; faces = []; slot = None
        for part in source.parts:
            if part['mesh'] != index:
                continue
            offset = len(vertices); t = part['vertices'][part['faces']]
            valid = np.linalg.norm(np.cross(t[:, 1]-t[:, 0], t[:, 2]-t[:, 0]), axis=1) > 1e-10
            skipped += int((~valid).sum()); faces.extend((part['faces'][valid]+offset).tolist())
            vertices.extend(part['vertices']); normals.extend(part['normals']); uv0.extend(part['uv0']); uv1.extend(part['uv1'])
            if slot is not None and slot != part['material']:
                raise ValueError('The pinned shared meshes must use one material each')
            slot = part['material']
        suffix = item['name'].split('/')[-1].replace('cmn_prp_dev_bk_', '').replace('_mesh', '')
        name = f'SM_CP_{index:02d}_{suffix}'
        emit(name, vertices, faces, materials[slot], uv0, uv1, normals, blocks=False)
    if skipped != spec['zero_area_faces'] or sum(v['triangles'] for v in report.values()) != spec['triangles']-skipped:
        raise ValueError('Source render geometry changed')
    vertices, faces, _, riding = riding_collision([(part['vertices'], part['faces']) for part in source.parts],
                                                  {k for k, part in enumerate(source.parts) if part['mesh'] in SLENDER},
                                                  [part['node'] for part in source.parts])
    emit('SM_CP_Collision', vertices.tolist(), faces.tolist(), materials[0], blocks=True, hidden=True)
    # The fine ground replaces the corresponding coarse mountain cells.
    x, y, z = L.grid(north_surface); h, w = x.shape
    world = np.stack((x, y, z), axis=-1); points = L.local(world).reshape(-1, 3)
    faces = [(j*w+i, j*w+i+1, (j+1)*w+i+1) for j in range(h-1) for i in range(w-1)]
    faces += [(j*w+i, (j+1)*w+i+1, (j+1)*w+i) for j in range(h-1) for i in range(w-1)]
    ground = material('CP_Ground', roughness=1.)
    vc = ground.node_tree.nodes.new('ShaderNodeVertexColor'); vc.layer_name = 'Color'
    ground.node_tree.links.new(vc.outputs['Color'], ground.node_tree.nodes.get('Principled BSDF').inputs['Base Color'])
    paint = colours(x, y, np.maximum(z, 47.)).reshape(-1, 3)
    ground_uv = world[..., :2].reshape(-1, 2)/6
    emit('SM_CP_Ground', points, faces, ground, ground_uv, ground_uv, colors=paint)
    # A four-metre ribbon follows the graded terrain and meets the main deck.
    p = L.access(); direction = np.gradient(p[:, :2], axis=0)
    normal = np.column_stack((-direction[:, 1], direction[:, 0])); normal /= np.linalg.norm(normal, axis=1)[:, None]
    left = p.copy(); right = p.copy(); left[:, :2] += normal*L.WIDTH/2; right[:, :2] -= normal*L.WIDTH/2
    top = L.local(np.stack((right, left), axis=1)).reshape(-1, 3)
    bottom = top.copy(); bottom[:, 2] -= .35; count = len(top)
    points = np.vstack((top, bottom)); faces = []
    for i in range(len(p)-1):
        a = 2*i; b = a+2
        faces.extend([(a, b, b+1), (a, b+1, a+1),
                      (a+count, b+count+1, b+count), (a+count, a+count+1, b+count+1),
                      (a, a+count, b+count), (a, b+count, b),
                      (a+1, b+1, b+count+1), (a+1, b+count+1, a+count+1)])
    for a, b in [(1, 0), (count-2, count-1)]:
        faces.extend([(a, b, b+count), (a, b+count, a+count)])
    emit('SM_CP_Access', points, faces, materials[0])
    # Authored additions carry the raised source pieces and provide a real ascent.
    structure_meshes, structure = build_structures(north_surface)
    made = {m.name: m for m in materials}
    for item in structure_meshes:
        emit(item.name, L.local(item.vertices), item.triangle_faces(), made[item.material], item.uv, item.uv)
    # Stencilled restyle panels on exposed walls; paint only, so no collision.
    mural_meshes, murals = build_murals()
    for item in mural_meshes:
        emit(item.name, L.local(item.vertices), item.triangle_faces(), made[item.material], item.uv, item.uv, blocks=False)
    # Benches, lanterns, planters and banners on the lawn; only the banner cloth is non-blocking.
    prop_meshes, props, planted = build_props(north_surface, [item['legs'] for item in structure['frame_footings']])
    for item in prop_meshes:
        emit(item.name, L.local(item.vertices), item.triangle_faces(), made[item.material], item.uv, item.uv,
             blocks=item.name != 'SM_CP_PropBanner')
    trees = L.screen_vegetation(north_surface)
    for name, rows in planted.items(): trees.setdefault(name, []).extend(rows)
    # Import seed prevents the legacy FBX factory opening its warning UI.
    obj = mesh('SM_CP_Seed', [(0, 0, 0), (.1, 0, 0), (0, .1, 0)], [(0, 1, 2)], materials[0]); export(obj)
    # The deck look bounds cover the whole source footprint, with the main deck's top.
    half = np.abs(source.triangles()[..., :2]).max((0, 1)).round(6)
    park = {'version': 1, 'key': 'communitypark', 'name': 'Hidamari Community Park', 'asset_root': '/Game/CommunityPark',
            'origin': L.ORIGIN.tolist(), 'yaw_deg': L.YAW,
            'deck': {'x': [-half[0], half[0]], 'y': [-half[1], half[1]], 'top_z': round(L.MAIN_DECK-L.ORIGIN[2], 3)},
            'meshes': entries, 'rails': paths(), 'clearance': L.clearance(), 'trees': trees, 'structures': structure,
            'spawns': {'park': {'pos': L.local(L.SPAWN).tolist(), 'yaw_deg': L.HEADING-L.YAW},
                       'path_top': {'pos': list(L.ACCESS[0]), 'yaw_deg': 90.}}}
    (OUT / 'park.json').write_text(json.dumps(park, indent=2)+'\n')
    report = {'source_instances': len(source.instances), 'source_triangles': spec['triangles'], 'zero_area_faces': skipped,
              'riding_triangles': spec['triangles']-skipped, 'riding_collision': riding, 'meshes': report,
              'murals': Counter(m['panel'] for m in murals), 'props': Counter(p['kind'] for p in props),
              'park_sha256': hashlib.sha256((OUT / 'park.json').read_bytes()).hexdigest(),
              'source_sha256': spec['sha256'], 'rails': len(park['rails'])}
    (OUT / 'build-report.json').write_text(json.dumps(report, indent=2)+'\n')
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / 'CommunityPark.blend'))
    print('COMMUNITY PARK BUILD COMPLETE', len(entries), 'meshes,', len(park['rails']), 'grind paths', flush=True)


if __name__ == '__main__':
    build()
