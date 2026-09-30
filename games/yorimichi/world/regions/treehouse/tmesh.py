"""A textured version of the village Mesh: every face also gets a material slot (a texture slug from
tools/treehouse_textures.py) and UVs in texture tiles.

Surfaces are projected along a grain: `with m.use('wood_plank', grain=(1, 0, 0)):` makes u follow the grain (the
texture's left-to-right) in the face plane and v cross it; with no grain a face uses its dominant plane, u level.
Boards jitter their texture offset so neighbours do not repeat. Lathes wrap u round the axis (arc length) and v up
it. Pictures (maps, noren, quilts...) pass explicit 0..1 UVs with `m.poly(points, color, uv=[...])`.
"""
import math, random
from contextlib import contextmanager
import bpy
import numpy as np
from mathutils import Vector
from village.build import Mesh, PALETTE

# metres per texture tile (treehouse_textures.py SURFACES); pictures are 1
TILE = dict(wood_plank=1.2, wood_timber=1.2, wood_pale=1.2, bark=1.6, shingle=1.6, moss=1.0, stone=1.2, plaster=1.5,
            canvas=1.0, indigo=.8, paper=.6, tile=1.0, hull=1.5, straw=.8, iron=.8, rope=.3)
# Textures whose painted grain runs up and down (bark, shakes): their grain goes on v.
VERTICAL = {'bark', 'shingle'}
RJ = random.Random(4242)


class TMesh(Mesh):
    def __init__(self, name, kind='wood_plank'):
        super().__init__(name)
        self.kinds = []; self.uvs = []; self.kind = kind; self.grain = None; self.jit = (0., 0.)

    @contextmanager
    def use(self, kind=None, grain=None, jitter=False):
        old = (self.kind, self.grain, self.jit)
        if kind: self.kind = kind
        if grain is not None: self.grain = self.transform.to_3x3()@Vector(grain)
        if jitter: self.jit = (RJ.random()*7.3, RJ.random()*5.1)
        try: yield
        finally: self.kind, self.grain, self.jit = old

    def poly(self, points, color, uv=None):
        before = len(self.faces)
        super().poly(points, color)
        if len(self.faces) == before: return
        face = self.faces[-1]; P = [Vector(self.vertices[i]) for i in face]
        if uv is not None and len(uv) == len(points) == len(P):
            self.uvs.append([tuple(q) for q in uv])
        else:
            self.uvs.append(self.project(P))
        self.kinds.append(self.kind)

    def project(self, P):
        n = Vector((0, 0, 0))
        for k in range(1, len(P)-1): n += (P[k]-P[0]).cross(P[k+1]-P[0])
        n = n.normalized() if n.length > 1e-12 else Vector((0, 0, 1))
        g = self.grain
        if g is not None and abs(g.normalized().dot(n)) < .9:
            u = (g-n*g.dot(n)).normalized()
        elif abs(n.z) > .7:
            u = Vector((1, 0, 0))
        else:
            u = Vector((0, 0, 1)).cross(n).normalized()
        v = n.cross(u)
        if self.kind in VERTICAL: u, v = v, u     # grain along the texture's up-down
        t = TILE.get(self.kind, 1.); ju, jv = self.jit
        return [(p.dot(u)/t+ju, p.dot(v)/t+jv) for p in P]

    def lathe(self, center, profile, color, n=12):
        x, y, z = center; t = TILE.get(self.kind, 1.); ju, jv = self.jit
        rm = max(.05, sum(r for _, r in profile)/len(profile))
        rings = [[(x+r*math.cos(i*2*math.pi/n), y+r*math.sin(i*2*math.pi/n), z+zz) for i in range(n)] for zz, r in profile]
        for (za, _), (zb, _), a, b in zip(profile[:-1], profile[1:], rings[:-1], rings[1:]):
            for k in range(n):
                s0, s1 = 2*math.pi*rm*k/n/t+ju, 2*math.pi*rm*(k+1)/n/t+ju
                uv = [(s0, za/t+jv), (s1, za/t+jv), (s1, zb/t+jv), (s0, zb/t+jv)]
                self.poly([a[k], a[(k+1) % n], b[(k+1) % n], b[k]], color, uv=uv)

    def object(self, materials):
        data = bpy.data.meshes.new(self.name); data.from_pydata(self.vertices, [], self.faces); data.update()
        slots = sorted(set(self.kinds)); index = {k: i for i, k in enumerate(slots)}
        for k in slots: data.materials.append(materials(k))
        data.polygons.foreach_set('material_index', [index[k] for k in self.kinds])
        layer = data.uv_layers.new(name='UVMap')
        flat = [uv for face in self.uvs for uv in face]
        layer.data.foreach_set('uv', np.array(flat, dtype=np.float32).ravel())
        col = data.color_attributes.new(name='Color', type='FLOAT_COLOR', domain='POINT')
        col.data.foreach_set('color', np.array(self.colors, dtype=np.float32).ravel())
        obj = bpy.data.objects.new(self.name, data); bpy.context.collection.objects.link(obj)
        return obj


def export(m, materials, out):
    """Like village.build.export, with one material slot per texture slug."""
    obj = m.object(materials); objs = [obj]
    for i, (c, s, rotation) in enumerate(m.colliders):
        bpy.ops.mesh.primitive_cube_add(size=1, location=c, rotation=rotation)
        ob = bpy.context.object; ob.name = f'UCX_{m.name}_{i:02d}'; ob.scale = s
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True); objs.append(ob)
    bpy.ops.object.select_all(action='DESELECT')
    for ob in objs: ob.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.export_scene.fbx(filepath=str(out/f'{m.name}.fbx'), use_selection=True, apply_unit_scale=True,
                             apply_scale_options='FBX_SCALE_ALL', axis_forward='-Y', axis_up='Z', object_types={'MESH'},
                             mesh_smooth_type='FACE', bake_anim=False, use_custom_props=False)
    b = np.array(m.vertices)
    info = {'triangles': sum(len(f)-2 for f in m.faces), 'vertices': len(m.vertices), 'slots': sorted(set(m.kinds)),
            'collision_boxes': len(m.colliders), 'min': b.min(0).round(3).tolist(), 'max': b.max(0).round(3).tolist()}
    for ob in objs[1:]: bpy.data.objects.remove(ob, do_unlink=True)
    return obj, info


def material_factory():
    cache = {}

    def get(kind):
        if kind not in cache:
            mat = bpy.data.materials.new('TH_'+kind); mat.use_nodes = True
            vc = mat.node_tree.nodes.new('ShaderNodeVertexColor'); vc.layer_name = 'Color'
            mat.node_tree.links.new(vc.outputs['Color'], mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'])
            cache[kind] = mat
        return cache[kind]
    return get


_ = PALETTE
