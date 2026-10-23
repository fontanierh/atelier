"""Preserve authored parent instance/material/cull grouping through bounded pieces."""
import numpy as np


def logical_collision(name):
    """Original static parent collision policy, shared by runtime and source queries."""
    if not isinstance(name,str) or not name:raise ValueError('Invalid Belmonte logical parent name')
    return not any(word in name for word in ('Water','Foam'))


def groups(data,materials,by_asset,meshes,extra):
    grouped = {}
    for placement in data['placements']:
        for entry, slots, collides in by_asset[placement['asset']]:
            # Retained glTF names pin the original material slots for every piece.
            names = [materials[placement['materials'][slot]]['name'] for slot in slots]
            bindings = tuple(f'/Game/Belmonte/Materials/{name}.{name}' for name in names)
            # A child may omit a material that distinguished two original instance
            # groups. Keep their parent grouping, including its max-scale cull policy.
            parent_slots = entry.get('parent_material_slots', slots)
            parent_bindings = tuple(materials[placement['materials'][slot]]['name'] for slot in parent_slots)
            key = (entry['name'], bindings, collides, parent_bindings)
            grouped.setdefault(key, []).append(placement['transform'])
    groups = []
    for (name, bindings, collides, _parent_bindings), transforms in grouped.items():
        water = not logical_collision(name)
        entry = next(entry for entry in meshes if entry['name'] == name)
        policy_bounds = entry.get('parent_bounds_m', entry['bounds_m'])
        span = max(np.subtract(policy_bounds[1], policy_bounds[0]))
        span *= max(max(abs(value) for value in transform['scale']) for transform in transforms)
        groups.append({'asset': f'/Game/Belmonte/Meshes/{name}.{name}', 'materials': list(bindings),
                       'plant': False, 'collision': collides and not water, 'shadow': not water,
                       'parent_collision': not water,
                       'cull_cm': 50000 if span < 8. else 0, 'transforms': transforms})
    material_name = 'MI_BM_Ground'
    materials['Ground'] = {'name': material_name, 'colour': [.24, .30, .12, 1.], 'tint': [1., 1., 1., 1.],
                           'terrain': False, 'layers': {}, 'tile_m': 4., 'white_vertex': True,
                           'brightness': 1., 'atlas': False, 'water': False, 'texture': None, 'join': True}
    for entry in extra:
        name = entry['name']
        groups.append({'asset': f'/Game/Belmonte/Meshes/{name}.{name}',
                       'materials': [f'/Game/Belmonte/Materials/{material_name}.{material_name}'], 'plant': False,
                       'collision': True, 'shadow': True, 'cull_cm': 0,
                       'transforms': [{'translation_cm': [0., 0., 0.], 'rotation_xyzw': [0., 0., 0., 1.], 'scale': [1., 1., 1.]}]})
    return groups
