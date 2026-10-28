"""Each region's adapter: which of Yorimichi's built meshes become Hakuba props, how each is coloured, and where each
stands. An adapter takes the build folder and returns a `port.Region`; `ADAPTERS` names them."""
import json

from port import Model, Region, export_source, kebab


def treehouse(build):
    """The tree house in the northern woodland: its frame, rooms, dressing and trunks, standing where they were built,
    and its furniture. A surface's colour is its vertex colour, decoded from sRGB once more, times its texture's mean
    and gain; a prop samples its own baked texture."""
    out = build / 'treehouse'
    gains = json.loads((out / 'textures' / 'textures.json').read_text())
    slots = {f'TH_{slug}': {'vertex': True, 'decode': True, 'mean': str(out / 'textures' / f'{slug}.png'),
                            'gain': info['gain']} for slug, info in gains.items()}
    slots['TH_pane'] = {'drop': True}  # the windows' additive daylight glow
    region = Region('treehouse', 'the tree house in the northern woodland')
    surfaces = json.loads((out / 'surfaces.json').read_text())['parents']
    for parent, pieces in surfaces.items():
        for piece in pieces:
            name = 'treehouse-' + kebab(piece.removeprefix('TH_'))
            region.models[name] = Model(export_source(build, 'treehouse_surfaces', piece), slots=slots, recentre=True)
            region.groups.append((name, True, [None]))
    props = json.loads((out / 'props' / 'props.json').read_text())
    for key, instances in json.loads((out / 'runtime.json').read_text())['instances'].items():
        name = 'treehouse-' + kebab(key.removeprefix('TH_P_'))
        rule = {'vertex': True, 'decode': True, 'sample': str(out / 'props' / f'{key}.png'), 'gain': props[key]['gain']}
        region.models[name] = Model(export_source(build, 'treehouse_props', key), default=rule)
        region.groups.append((name, False, instances))
    return region


ADAPTERS = {'treehouse': treehouse}
