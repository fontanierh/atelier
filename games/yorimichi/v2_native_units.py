"""Compose native replacement owners over the ordinary source producer declarations."""
from copy import deepcopy


def shared_materials(rows, *, checkout):
    """Return independent texture/graph owners; no old native task or cache runs."""
    import importlib.util
    from pathlib import Path
    def load(name):
        spec = importlib.util.spec_from_file_location('native_' + name,
            Path(checkout) / 'games/yorimichi' / (name + '.py'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    texture = load('v2_texture_units')
    materials_source = load('v2_material_units')
    textures = texture.texture_units(rows, checkout=checkout)
    if len(textures['textures']) != 22:
        raise ValueError('Shared material library requires all 22 original texture producers')
    materials = materials_source.author_units(textures['textures'], checkout=checkout)
    native_code = texture._code(checkout)
    units = deepcopy(textures['units']) + deepcopy(materials['units'])
    for unit in units:
        unit['code'] = sorted(set(unit['code']) | set(native_code))
    return {'units': units,
            'staged_inputs': {**textures['staged'], **materials['staged_inputs']},
            'content_slots': {**textures['slots'], **materials['content_slots']},
            'packages': {**{row['package']: row for row in textures['textures'].values()},
                         **materials['packages']},
            'targets': tuple(unit['id'] for unit in materials['units'])}
