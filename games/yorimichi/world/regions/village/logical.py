"""One original Village constructor with its own exact predecessor random state."""
from village import build, mesh
from village.atomic_sources import ASSETS, restore


def construct(key, source, heights=None):
    if (key not in ASSETS or source.get('schema') != 1 or source.get('asset') != key
            or not isinstance(source.get('world'), dict) or not isinstance(source.get('parameters'), dict)):
        raise ValueError('Missing or foreign selected Village data')
    restore(mesh.R, source['random_state'])
    palette = source.get('palette')
    if not isinstance(palette, dict) or not palette: raise ValueError('Missing selected Village palette values')
    mesh.PALETTE.clear(); mesh.PALETTE.update(palette)
    build.WORLD = source['world']; build.HEIGHTS = heights; mesh.HEIGHTS = heights
    if key in {row[0] for row in build.BUILDINGS}:
        params = source['parameters']; m = mesh.Mesh(key)
        w, d = params['width'], params['depth']
        if key.endswith('TeaHouse'): build.tea_house(m, w, d)
        elif key.endswith('CottageA'): build.cottage(m, w, d, 'A')
        elif key.endswith('CottageB'): build.cottage(m, w, d, 'B')
        elif key.endswith('Workshop'): build.workshop(m, w, d)
        elif key.endswith('Storehouse'): build.storehouse(m, w, d)
        else: raise ValueError('Missing explicit Village building constructor')
    elif key in ('Village_Garden', 'Village_Sign'):
        m = mesh.Mesh(key)
        getattr(build, 'garden' if key == 'Village_Garden' else 'sign')(m)
    elif key in ('Village_Ground', 'Village_Edges'):
        m = getattr(build, 'ground' if key == 'Village_Ground' else 'edges')(source['world'], heights)
    else:
        from village import decorations
        function = dict(Village_Details='furnish', Village_Planting='planting', Village_Threshold='threshold')[key]
        m = getattr(decorations, function)(build)
    if m.name != key: raise ValueError('Selected Village constructor returned another owner')
    return m
