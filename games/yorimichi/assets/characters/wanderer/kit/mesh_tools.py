"""Small flat-shaded mesh primitives. Metres, Z up, forward -Y."""
import math
import bpy
import bmesh
from mathutils import Vector

PARTS = []
PALETTE = {
    'skin': 'F0B27A', 'skin_shadow': 'D99461', 'ear': 'D08B59',
    'hair': '42363A', 'hair_light': '493C3E', 'hair_dark': '382F36',
    'ink': '2D292D', 'yellow': 'E1AC48', 'yellow_light': 'E8B64F',
    'yellow_dark': 'C99338', 'cream': 'DED8CC', 'cream_light': 'E8E1D3',
    'cream_shadow': 'BFBEB7', 'blue': '475B70', 'blue_dark': '3D4E60',
    'blue_light': '506379', 'red': 'A95236', 'red_dark': '83472F',
    'leather': '73533F', 'leather_dark': '543D32', 'leather_light': '81634A',
    'sole': 'A88965',
}

def colour(name):
    h = PALETTE.get(name, name)
    c = [int(h[i:i+2], 16)/255 for i in (0, 2, 4)]
    return tuple(x/12.92 if x <= .04045 else ((x+.055)/1.055)**2.4 for x in c)+(1,)

def material():
    m = bpy.data.materials.get('CapeBoy_Palette')
    if m:
        return m
    m = bpy.data.materials.new('CapeBoy_Palette')
    m.use_nodes = True
    bs = m.node_tree.nodes.get('Principled BSDF')
    vc = m.node_tree.nodes.new('ShaderNodeVertexColor')
    vc.layer_name = 'Colour'
    m.node_tree.links.new(vc.outputs['Color'], bs.inputs['Base Color'])
    m.node_tree.links.new(vc.outputs['Color'], bs.inputs['Emission Color'])
    bs.inputs['Emission Strength'].default_value = .30
    bs.inputs['Roughness'].default_value = 1
    bs.inputs['Specular IOR Level'].default_value = 0
    return m

def mesh(name, verts, faces, col, weights='pelvis', face_colours=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    me.materials.append(material())
    ca = me.color_attributes.new(name='Colour', type='FLOAT_COLOR', domain='CORNER')
    for p in me.polygons:
        p.use_smooth = False
        c = colour(face_colours[p.index] if face_colours else col)
        for i in p.loop_indices:
            ca.data[i].color = c
    for i, v in enumerate(verts):
        ws = weights(v) if callable(weights) else weights[i] if isinstance(weights, list) else weights
        if isinstance(ws, str):
            ws = {ws: 1}
        total = sum(ws.values())
        for bone, weight in ws.items():
            if weight > 1e-6:
                group = ob.vertex_groups.get(bone) or ob.vertex_groups.new(name=bone)
                group.add([i], weight/total, 'REPLACE')
    PARTS.append(ob)
    return ob

def weights_z(z, levels):
    if z <= levels[0][0]:
        return {levels[0][1]: 1}
    for (a, na), (b, nb) in zip(levels, levels[1:]):
        if a <= z <= b:
            if na == nb:
                return {na: 1}
            t = (z-a)/(b-a)
            return {na: 1-t, nb: t}
    return {levels[-1][1]: 1}

def torso(p):
    return weights_z(p[2], [(.72, 'pelvis'), (.81, 'spine'), (.96, 'chest'), (1.055, 'neck')])

def loft(name, rings, col, weights='pelvis', n=10, cap=True, phase=0):
    """rings = centre x,y,z and x/y radii."""
    verts = [(x+rx*math.cos(2*math.pi*i/n+phase), y+ry*math.sin(2*math.pi*i/n+phase), z)
             for x, y, z, rx, ry in rings for i in range(n)]
    faces = []
    for j in range(len(rings)-1):
        for i in range(n):
            a, b = j*n+i, j*n+(i+1)%n
            faces.append((a, b, b+n, a+n))
    if cap:
        faces += [tuple(range(n-1, -1, -1)), tuple((len(rings)-1)*n+i for i in range(n))]
    return mesh(name, verts, faces, col, weights)

def tube(name, points, radii, col, weights, sides=8, depth=1):
    pts = list(map(Vector, points))
    verts = []
    for i, p in enumerate(pts):
        tangent = (pts[min(i+1, len(pts)-1)]-pts[max(0, i-1)]).normalized()
        side = tangent.cross(Vector((0, -1, 0))).normalized()
        normal = tangent.cross(side).normalized()
        for k in range(sides):
            a = 2*math.pi*k/sides
            verts.append(tuple(p+side*(radii[i]*math.cos(a))+normal*(radii[i]*depth*math.sin(a))))
    faces = []
    for j in range(len(pts)-1):
        for i in range(sides):
            a, b = j*sides+i, j*sides+(i+1)%sides
            faces.append((a, b, b+sides, a+sides))
    faces += [tuple(range(sides-1, -1, -1)), tuple((len(pts)-1)*sides+i for i in range(sides))]
    return mesh(name, verts, faces, col, weights)

def box(name, loc, size, col, weights='pelvis', bevel=.005, rotation=None):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    ob = bpy.context.object
    ob.scale = size
    if rotation:
        ob.rotation_euler = rotation
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        mod = ob.modifiers.new('Single plane edge bevel', 'BEVEL')
        mod.width, mod.segments = bevel, 1
        bpy.ops.object.modifier_apply(modifier=mod.name)
    verts = [tuple(ob.matrix_world@v.co) for v in ob.data.vertices]
    faces = [tuple(p.vertices) for p in ob.data.polygons]
    bpy.data.objects.remove(ob, do_unlink=True)
    return mesh(name, verts, faces, col, weights)

def panel(name, points, faces, col, weights, thickness=.008, normal=(0, -1, 0)):
    n = len(points)
    shift = Vector(normal)*thickness
    verts = list(points)+[tuple(Vector(p)-shift) for p in points]
    all_faces = list(faces)+[tuple(i+n for i in reversed(f)) for f in faces]
    edges = {}
    for f in faces:
        for a, b in zip(f, f[1:]+f[:1]):
            key = tuple(sorted((a, b)))
            edges[key] = edges.get(key, 0)+1
    for (a, b), count in edges.items():
        if count == 1:
            all_faces.append((a, b, b+n, a+n))
    return mesh(name, verts, all_faces, col, weights)

def ribbon(name, points, widths, col, weights, normal=(0, -1, 0), thickness=.007):
    pts, N, v = list(map(Vector, points)), Vector(normal), []
    for i, p in enumerate(pts):
        t = (pts[min(i+1, len(pts)-1)]-pts[max(0, i-1)]).normalized()
        side = t.cross(N).normalized()
        width = widths[i] if isinstance(widths, list) else widths
        v += [tuple(p-side*width/2), tuple(p+side*width/2)]
    faces = [(i*2, i*2+1, i*2+3, i*2+2) for i in range(len(pts)-1)]
    return panel(name, v, faces, col, weights, thickness, normal)
