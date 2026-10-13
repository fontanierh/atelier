"""Draw current town, water and course geometry on the island's world map."""
import numpy as np

from . import layout as L, planting, source


def colour(name):
    if any(word in name for word in ('Water', 'Pond')):
        return (112, 164, 176)
    if any(word in name for word in ('Course', 'Arenas', 'Pave', 'Ponte')):
        return (202, 176, 133)
    if any(word in name for word in ('Infield', 'Grounds', 'Gardens', 'Yard')):
        return (149, 169, 103)
    return (167, 106, 73)


def draw(draw, project, scale):
    data = source.manifest()
    models = {entry['source_asset']: entry for entry in data['meshes']}
    cache, faces, colours = {}, [], []
    prefixes = ('SM_BM_BT_blk_', 'SM_BM_BH_', 'SM_BM_BE_', 'SM_BM_BHip_',
                'SM_BM_BVV_Farm_', 'SM_BM_BC_Water_', 'SM_BM_BC_Pave', 'SM_BM_BC_Ponte')
    for placement in data['placements']:
        model = models[placement['asset']]
        name = model['name']
        if not name.startswith(prefixes):
            continue
        if name not in cache:
            cache[name] = source.triangles(source.LIBRARY / model['path'])
        transform = placement['transform']
        # Models are Blender metres; placement data retains the native scene's
        # Unreal centimetres and quaternion. Mirror into that frame and back.
        native = cache[name] * np.array([100., -100., 100.]) * transform['scale']
        native = planting.rotate(transform['rotation_xyzw'], native) + transform['translation_cm']
        world = native / np.array([100., -100., 100.]) + L.ORIGIN
        normal = np.cross(world[:, 1] - world[:, 0], world[:, 2] - world[:, 0])
        world = world[normal[:, 2] > 1e-7]
        faces.extend(world)
        colours.extend([colour(name)] * len(world))
    faces = np.asarray(faces)
    for index in np.argsort(faces[:, :, 2].mean(1)):
        draw.polygon([project(x, y) for x, y, _ in faces[index]], fill=colours[index])


def trees(runtime, prefixes):
    """Use the actual replacement placements, including the connecting woods."""
    points = []
    for group in runtime['groups']:
        name = group['asset'].split('.')[-1]
        if group['plant'] and name.startswith(prefixes):
            for transform in group['transforms']:
                x, y, _ = transform['translation_cm']
                points.append((x / 100. + L.ORIGIN[0], -y / 100. + L.ORIGIN[1]))
    return np.asarray(points, float).reshape(-1, 2)
