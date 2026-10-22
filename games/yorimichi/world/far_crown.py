"""A tree's farthest LOD as one opaque, single-colour crown (Blender side, shared by both tree producers).

The leaf cards of the level being replaced give the crown its shape and colour:
- shape: a hexagonal bipyramid (8 vertices, 12 triangles), each vertex on the cards' convex hull along its direction
  from the hull's box centre, measured in the frame that maps that box to a cube, then scaled about the centre to
  the hull's volume (capped so the LOD's bounds stay within the importer's tolerance);
- colour: the area-weighted mean of the cards' colours as M_Foliage shows them (leaf atlas, instance tint, interior
  shade), linear.

The crown replaces the whole level, bark included: at these distances a trunk is far below a pixel. Its one slot
is named after the tree (``<tree>_Crown``); the importer gives it an instance of the opaque M_Painted with that
colour and dithered LOD blending, owned by the tree's import step, so no shared material changes.
"""
import math

import numpy as np

# The leaf instance tints shared_materials applies on top of the texture; a crown bakes the same tint.
# Kept here, not in material_specs, so a crown never invalidates every other asset export.
LEAF_TINTS = {'LeafGinkgo': (1.0, .72, .42)}
# The importer's LOD bounds tolerance is 1.15 of LOD0's diagonal; stay inside it.
MAX_DIAGONAL = 1.12


def slot(tree):
    return tree + '_Crown'


def _linear(c):
    return np.where(c <= .04045, c / 12.92, ((c + .055) / 1.055) ** 2.4)


class LeafAtlas:
    """Linear alpha-weighted mean colour of each 2x2 atlas quadrant (asset_mesh card cells), with the leaf
    instance's tint, as M_Foliage shows the cards that pass its 0.4 clip. A quadrant with no opaque texel falls
    back to the whole texture."""
    def __init__(self, material, tint=(1., 1., 1.)):
        image = next(n.image for n in material.node_tree.nodes if n.type == 'TEX_IMAGE')
        width, height = image.size
        pixels = np.array(image.pixels[:], dtype='f4').reshape(height, width, 4)
        whole = pixels[pixels[..., 3] >= .4][:, :3]
        whole = whole if len(whole) else pixels.reshape(-1, 4)[:, :3]
        self.means = {}
        for column in (0, 1):
            for row in (0, 1):
                cell = pixels[row * height // 2:(row + 1) * height // 2, column * width // 2:(column + 1) * width // 2]
                kept = cell[cell[..., 3] >= .4][:, :3]
                linear = _linear(kept if len(kept) else whole).mean(axis=0)
                self.means[column, row] = np.array([float(c) * t for c, t in zip(linear, tint)])

    def colour(self, u, v, g):
        """g: vertex colour G, 0 deep inside the crown .. 1 on its shell (M_Foliage darkens the interior)."""
        return self.means[int(u >= .5), int(v >= .5)] * (.5 + .5 * g)


def _cards(obj, leaf, tint):
    """Points, and (colour, area) per card face, of the leaf slot's faces."""
    me = obj.data
    index = next(i for i, m in enumerate(me.materials) if m and m.name == leaf.name)
    atlas = LeafAtlas(leaf, tint)
    uvs = me.uv_layers.active.data
    shades = me.color_attributes['Col'].data
    points, colours, areas = [], [], []
    for polygon in me.polygons:
        if polygon.material_index != index:
            continue
        loops = list(polygon.loop_indices)
        u = sum(uvs[i].uv[0] for i in loops) / len(loops)
        v = sum(uvs[i].uv[1] for i in loops) / len(loops)
        g = sum(shades[i].color[1] for i in loops) / len(loops)
        colours.append(atlas.colour(u, v, g)); areas.append(polygon.area)
        points += [tuple(me.vertices[me.loops[i].vertex_index].co) for i in loops]
    assert len(points) >= 4, (obj.name, 'no leaf cards for a crown')
    return np.array(points), np.array(colours), np.array(areas)


def _hull_volume(points):
    import bmesh
    hull = bmesh.new()
    for p in points:
        hull.verts.new(p)
    result = bmesh.ops.convex_hull(hull, input=hull.verts[:], use_existing_faces=False)
    loose = {g for g in result['geom_interior'] + result['geom_unused'] if isinstance(g, bmesh.types.BMVert)}
    bmesh.ops.delete(hull, geom=list(loose), context='VERTS')
    volume = hull.calc_volume(signed=False)
    hull.free()
    return volume


def bipyramid(points, diagonal_limit):
    """(vertices [8,3], triangles [12,3] outward, scale) fitted to points; Blender is Z-up."""
    ring = [(math.cos(a), math.sin(a), 0.) for a in np.arange(6) * math.pi / 3]
    directions = np.array(ring + [(0., 0., 1.), (0., 0., -1.)])
    faces = np.array([(i, (i + 1) % 6, 6) for i in range(6)] + [(i, 7, (i + 1) % 6) for i in range(6)])
    lo, hi = points.min(0), points.max(0)
    centre, half = (lo + hi) / 2, np.maximum((hi - lo) / 2, 1e-4)
    support = (((points - centre) / half) @ directions.T).max(0)
    vertices = centre + directions * support[:, None] * half
    for k, (a, b, c) in enumerate(faces):
        if np.dot(np.cross(vertices[b] - vertices[a], vertices[c] - vertices[a]), vertices[[a, b, c]].mean(0) - centre) < 0:
            faces[k] = (a, c, b)
    tri = vertices[faces] - centre
    volume = abs(np.einsum('ij,ij->i', tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum()) / 6
    scale = (_hull_volume(points) / volume) ** (1 / 3)
    diagonal = np.linalg.norm(vertices.max(0) - vertices.min(0))
    scale = min(scale, diagonal_limit / diagonal)
    return centre + (vertices - centre) * scale, faces, scale


def replace(obj, leaf, crown_material, reference_diagonal, tint=(1., 1., 1.)):
    """Make obj (a generated LOD level) the crown: one 12-triangle bipyramid on crown_material, nothing else.
    Returns the crown's linear colour, which the importer sets on the crown instance."""
    points, colours, areas = _cards(obj, leaf, tint)
    colour = (colours * areas[:, None]).sum(0) / areas.sum()
    vertices, faces, scale = bipyramid(points, MAX_DIAGONAL * reference_diagonal)
    diagonal = float(np.linalg.norm(vertices.max(0) - vertices.min(0)))
    # The importer refuses a level under 0.8 of LOD0's diagonal; a crown that small would also read as a gap.
    assert diagonal >= .85 * reference_diagonal, (obj.name, 'crown far smaller than the tree', diagonal, reference_diagonal)
    me = obj.data
    me.clear_geometry()
    me.from_pydata([tuple(v) for v in vertices], [], [tuple(int(i) for i in f) for f in faces])
    me.materials.clear()
    me.materials.append(crown_material)
    for polygon in me.polygons:
        polygon.material_index = 0
        polygon.use_smooth = True
    # The exporter and the legacy FBX import expect UV0 (lightmap channel) and the Col layer every level carries.
    if not me.uv_layers:
        me.uv_layers.new(name='UVMap')
    if 'Col' not in me.color_attributes:
        me.color_attributes.new('Col', 'BYTE_COLOR', 'CORNER')
    me.color_attributes.active_color = me.color_attributes['Col']
    for loop in me.color_attributes['Col'].data:
        loop.color = (1., 1., 1., 1.)
    me.update()
    return {'slot': crown_material.name, 'colour': [float(c) for c in colour], 'scale': round(float(scale), 3),
            'triangles': len(faces)}
