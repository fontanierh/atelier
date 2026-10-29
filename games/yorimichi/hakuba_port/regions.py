"""Each region's adapter: which of Yorimichi's built meshes become Hakuba props, how each is coloured, and where each
stands. An adapter takes the build folder and returns a `port.Region`; `ADAPTERS` names them."""
import functools
import json
import math
import sys
from pathlib import Path

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
            region.models[name] = Model(export_source(build, 'treehouse_surfaces', piece), slots=slots)
            region.groups.append((name, None, [[0.0, 0.0, 0.0, 0.0, 1.0]]))
    props = json.loads((out / 'props' / 'props.json').read_text())
    for key, instances in json.loads((out / 'runtime.json').read_text())['instances'].items():
        name = 'treehouse-' + kebab(key.removeprefix('TH_P_'))
        rule = {'vertex': True, 'decode': True, 'sample': str(out / 'props' / f'{key}.png'), 'gain': props[key]['gain']}
        region.models[name] = Model(export_source(build, 'treehouse_props', key), default=rule)
        region.groups.append((name, None, instances))
    return region



# Groups with more instances than this are ground cover (ferns, grass, leaf litter), which Hakuba scatters itself.
COVER = 5000


def runtime_groups(build, region, folder, exports, prefix, rule, collision=None):
    """A region Yorimichi's game stands from `<folder>/runtime.json`: groups of one mesh each, its material instances
    in slot order and its transforms, in centimetres from the region's origin in Unreal's frame (Y flipped). Meshes
    from other folders (the shared plants) are left out; `rule` turns a material instance's name into a colour rule
    or None to leave its slot out."""
    runtime = json.loads((build / folder / 'runtime.json').read_text())
    ox, oy, oz = runtime['origin_cm']
    merged = {}
    for group in runtime['groups']:
        asset = group['asset'].rsplit('.', 1)[-1]
        if len(group['transforms']) > COVER or not asset.startswith(prefix):
            continue
        source = next((export_source(build, step, asset) for step in exports
                       if (build / 'exports' / f'world.{step}.export' / asset).is_dir()), None)
        if source is None:
            continue
        export = json.loads((source.parent / 'export.json').read_text())
        slot_names = export['metadata']['slots']
        name = f'{region.name}-' + kebab(asset.removeprefix(prefix))
        if name not in region.models:
            slots = {}
            for slot, instance in zip(slot_names, group['materials']):
                colour = rule(instance.rsplit('.', 1)[-1])
                slots[slot] = colour if colour is not None else {'drop': True}
            hull = collision(asset) if collision else None
            region.models[name] = Model(source, slots=slots, collision=hull if hull and hull.exists() else None,
                                        solid=bool(group.get('collision')))
        afar = None if group.get('cull_cm', 0) == 0 else group['cull_cm'] >= 30000
        for transform in group['transforms']:
            tx, ty, tz = transform['translation_cm']
            qx, qy, qz, qw = transform['rotation_xyzw']
            yaw = -math.degrees(2 * math.atan2(qz, qw))
            merged.setdefault((name, afar), []).append(
                [(ox + tx) / 100, -(oy + ty) / 100, (oz + tz) / 100, yaw, transform['scale'][0]])
    region.groups += [(name, afar, instances) for (name, afar), instances in merged.items()]
    return region


def brinecove(build):
    """Brinecove, the pirate port on the western coast: its ground, quays, market, ships and buildings. A material's
    colour is its colour times its texture's mean; terrain uses its rock or meadow layer. Cut-out and see-through
    materials, such as leaves, flags and water, are left out."""
    report = json.loads((build / 'brinecove' / 'build-report.json').read_text())['materials']
    by_name = {entry['name']: entry for entry in report.values()}
    textures = build / 'brinecove' / 'textures'

    def rule(instance):
        entry = by_name.get(instance)
        if entry is None or entry['kind'] in ('masked', 'translucent'):
            return None
        colour = {'rgb': entry['colour'][:3]}
        if entry['kind'] == 'terrain':
            layer = entry['layers']['Rock' if entry['rock_only'] else 'Meadow']
            colour['mean'] = str(textures / layer)
        elif entry['texture']:
            colour['mean'] = str(textures / entry['texture'])
        return colour

    region = Region('brinecove', 'Brinecove, the pirate port on the western coast')
    return runtime_groups(build, region, 'brinecove', ['brinecove'], 'SM_BC_', rule)


def belmonte(build):
    """Belmonte and the Haras valley: the town, its ground, the hippodrome and the northern hills. A material's colour
    is its colour, tint and brightness times its texture's mean (or, for an atlas, the texel under each corner), and
    terrain uses its green layer; water is left out."""
    report = json.loads((build / 'belmonte' / 'build-report.json').read_text())['materials']
    by_name = {entry['name']: entry for entry in report.values()}
    textures = build / 'belmonte' / 'textures'

    def rule(instance):
        entry = by_name.get(instance)
        if entry is None or entry['water']:
            return None
        rgb = [c * t * entry['brightness'] for c, t in zip(entry['colour'][:3], entry['tint'][:3])]
        if entry['terrain']:
            return {'rgb': [c * g for c, g in zip(rgb, entry['layers']['Green'])]}
        colour = {'rgb': rgb, 'vertex': entry['white_vertex'] is False}
        if entry['texture']:
            colour['sample' if entry['atlas'] else 'mean'] = str(textures / entry['texture'])
        return colour

    region = Region('belmonte', 'Belmonte and the Haras valley')
    region = runtime_groups(build, region, 'belmonte', ['belmonte_models', 'belmonte_ground', 'belmonte_north'],
                            'SM_BM_', rule, collision=lambda asset: build / 'belmonte' / 'glb' / f'{asset}_Collision.glb')
    # The valley villages are Belmonte's own backdrop, hundreds of metres up around its map; on the island's map
    # they would hang in the sky over the island and the sea.
    backdrop = {name for name in region.models if name.startswith('belmonte-bvv-village')}
    for name in backdrop:
        del region.models[name]
    region.groups = [group for group in region.groups if group[0] not in backdrop]
    return region



def hidamari(build):
    """Hidamari, the city east of the coast, with its ground, streets, harbour and the northern mountains behind it.
    Its parents are split into pieces in the parent's own frame; `city.json` stands each parent, and so all its pieces.
    The city's colour is its vertex colour (its textures are neutral detail around 1); a street prop samples its own
    atlas. Plants are left to Hakuba's plants. The city's flat sea is left out: Hakuba draws one sea at sea level
    under the whole island, and the city's copy lay on it as an off-coloured rectangle seen from the rim."""
    out = build / 'hidamari'
    instances = json.loads((out / 'city.json').read_text())['instances']
    region = Region('hidamari', 'Hidamari, the city east of the coast, and the northern mountains')
    skipped = []
    for step, rule_for in (('hidamari', lambda piece: {'vertex': True}),
                           ('hidamari_props', lambda piece: {'sample': str(out / 'props' / f'{piece}.png')})):
        parents = json.loads((build / 'atomic_regions' / step / 'logical-pieces.json').read_text())['parents']
        for parent, pieces in parents.items():
            placed = [list(map(float, i)) for i in instances.get(parent, [])]
            if not placed:
                skipped.append(parent)
                continue
            for piece in pieces:
                name = 'hidamari-' + kebab(piece.removeprefix('HD_P_').removeprefix('HD_'))
                if name == 'hidamari-sea':
                    continue
                region.models[name] = Model(export_source(build, step, piece), default=rule_for(piece))
                region.groups.append((name, None, placed))
    if skipped:
        print('hidamari: parents never placed:', ', '.join(skipped))
    return region



def _core(build):
    return json.loads((build / 'world.json').read_text())['instances']


def southwest(build):
    """The south-west fishing hamlet and Temple Island: houses, boat shed, dock, boats, stone walls, boulders, the
    temple and its leaning pines, coloured by their palette per vertex, standing where the island's layout put them."""
    instances = _core(build)
    region = Region('southwest', 'the south-west fishing hamlet and Temple Island')
    parents = json.loads((build / 'atomic_regions' / 'southwest' / 'logical-pieces.json').read_text())['parents']
    for parent, pieces in parents.items():
        for piece in pieces:
            name = 'southwest-' + kebab(piece.removeprefix('SW_'))
            region.models[name] = Model(export_source(build, 'southwest', piece), default={'vertex': True})
            region.groups.append((name, None, instances[parent]))
    return region


def shrines(build):
    """The island's torii and stone lanterns, coloured from the shared material list."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'world'))
    from material_specs import MATERIALS
    textures = build / 'textures'
    slots = {}
    for slot, spec in MATERIALS.items():
        rule = {'rgb': list(spec.get('color', (1.0, 1.0, 1.0)))}
        if 'texture' in spec and (textures / spec['texture']).exists():
            rule['mean'] = str(textures / spec['texture'])
        slots[slot] = rule
    instances = _core(build)
    region = Region('shrines', "the island's torii and stone lanterns")
    for asset in ('Torii', 'Lantern'):
        name = 'shrine-' + kebab(asset)
        region.models[name] = Model(export_source(build, 'props', asset), slots=slots)
        region.groups.append((name, None, instances[asset]))
    return region


def zeppelin(build):
    """The air stations and the trail up to the woodland station, coloured by their palette per vertex."""
    placed = {**_core(build), **json.loads((build / 'hidamari' / 'city.json').read_text())['instances']}
    region = Region('zeppelin', 'the air stations')
    for asset in ('ZP_Woodland', 'ZP_Belmonte', 'ZP_Trail', 'ZP_City', 'ZP_MegaPark'):
        if asset not in placed:
            continue
        name = 'zeppelin-' + kebab(asset.removeprefix('ZP_'))
        region.models[name] = Model(export_source(build, 'zeppelin', asset),
                                    default={'vertex': True}, slots={'ZeppelinFabric': {'rgb': [0.62, 0.6, 0.55]}})
        region.groups.append((name, None, placed[asset]))
    return region


def sword_camp(build):
    """The roadside camp's fire pit, curtain, weapon rack and bales, on the ground around its centre, facing the
    road; each samples the camp's atlas."""
    centre, road = (-54.0, -94.0), (-55.0, -71.0)
    fx, fy = road[0] - centre[0], road[1] - centre[1]
    length = math.hypot(fx, fy)
    fx, fy = fx / length, fy / length
    lx, ly = -fy, fx
    heading = math.degrees(math.atan2(fy, fx))
    atlas = {'sample': str(build / 'swordcamp' / 'swordcamp_atlas.jpg')}
    region = Region('sword-camp', 'the roadside sword camp')
    for asset, along, across, turn in (('SM_CampFirePit', 0.0, 0.0, 0.0), ('SM_CampJinmaku', -6.2, 0.0, 90.0),
                                       ('SM_CampWeaponRack', -2.4, 4.4, -35.0), ('SM_CampBales', -2.6, -4.4, 30.0)):
        name = 'camp-' + kebab(asset.removeprefix('SM_Camp'))
        region.models[name] = Model(export_source(build, 'swordcamp', asset), default=atlas)
        at = (centre[0] + fx * along + lx * across, centre[1] + fy * along + ly * across)
        region.groups.append((name, None, [[at[0], at[1], None, heading + turn, 1.0]]))
    return region



def megapark(build):
    """The Super Ultra Mega Park in the western foothills: its 32 authored models and the hillside seam that meets the
    air station's footbridge, standing where `megapark/park.json` stands them, as one body turned about the park
    actor. A material draws its diffuse image (the restyled one where the restyle replaced it) on the mesh's first UVs,
    as Yorimichi's park material does (`import_megapark.py`, `material`: B = lerp(diffuse, decal, decal alpha) *
    lerp(1, macro overlay, its opacity)). The decal runs on the third UVs and the macro overlay on the first at 0.3 or
    0.7 times their scale, so neither can be laid into the diffuse image: each is folded in by its mean, the material's
    colour being the mean of B over the mean of the diffuse, in linear RGB. The baked lightmap's occlusion (second UVs)
    is left out. The park has no tints or vertex colours. Cut-out materials (ground cover, sign cut-outs, lamp glow) are
    left out, and so are the park's own trees and parked cars, which are plants and another region's models."""
    import numpy as np
    from PIL import Image
    out = build / 'megapark'
    report = json.loads((out / 'build.json').read_text())
    park = json.loads((out / 'park.json').read_text())
    restyle = json.loads((out / 'textures' / 'textures.json').read_text())['textures']
    source = Path(__file__).resolve().parents[1] / 'assets' / 'megapark'
    if json.loads((source / 'provenance.json').read_text())['converted_manifest_sha256'] != report['source_sha256']:
        raise SystemExit(f'{source}: not the park source this build read')

    def texture(tid):
        if tid in restyle:
            return out / 'textures' / restyle[tid]['png']
        return source / report['textures'][tid]['png']

    @functools.cache
    def pixels(tid):
        """A texture's linear RGB and its alpha, each texel's."""
        rgba = np.asarray(Image.open(texture(tid)).convert('RGBA'), np.float64).reshape(-1, 4) / 255.0
        rgb = rgba[:, :3]
        return np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4), rgba[:, 3:]

    slots = {}
    for key, material in report['materials'].items():
        ids = material.get('retail_texture_ids', {})
        if material.get('alpha_mode', 0) != 0 or 'diffuse' not in ids:
            slots[key] = {'drop': True}
            continue
        # B = lerp(diffuse, decal, decal alpha) * lerp(1, macro, MacroOpacity), as the park's material draws it.
        diffuse = pixels(ids['diffuse'])[0].mean(0)
        colour = diffuse
        if 'decal' in ids:
            decal, alpha = pixels(ids['decal'])
            colour = colour * (1.0 - alpha.mean()) + (decal * alpha).mean(0)
        if 'macrooverlay' in ids:
            try:
                opacity = float(material['retail_parameters']['macroOverlayOpacity'][0])
            except (KeyError, ValueError):
                opacity = 0.0
            colour = colour * (1.0 + opacity * (pixels(ids['macrooverlay'])[0].mean(0) - 1.0))
        slots[key] = {'sample': str(texture(ids['diffuse'])),
                      'rgb': [round(float(c / max(d, 1e-4)), 4) for c, d in zip(colour, diffuse)]}
    x0, y0, z0 = park['location_cm']
    turn = math.radians(park['yaw_deg'])
    region = Region('megapark', 'the Super Ultra Mega Park in the western foothills')
    for entry in park['render']:
        asset = entry['name']
        name = 'megapark-' + asset.removeprefix('SM_MP_').lower()
        region.models[name] = Model(export_source(build, 'megapark', asset), slots=slots)
        # Unreal's frame: the actor turns its children by its yaw; Hakuba's y is Unreal's -y, and its turn the opposite.
        ox, oy, oz = entry['origin_cm']
        ux = x0 + ox * math.cos(turn) - oy * math.sin(turn)
        uy = y0 + ox * math.sin(turn) + oy * math.cos(turn)
        region.groups.append((name, None, [[ux / 100, -uy / 100, (z0 + oz) / 100, -park['yaw_deg'], 1.0]]))
    return region


def far_hills(build):
    """The far hills: the island's coarse land between and around the regions, in cells. Cells wholly under the sea
    or south of the island's tiles are left out."""
    hills = json.loads((build / 'terrain' / 'island.json').read_text())['parents']['FarHills']
    region = Region('far-hills', "the island's far hills")
    forest = {'rgb': [0.11, 0.2, 0.07]}
    rock = {'rgb': [0.3, 0.27, 0.24]}
    for mesh in hills['meshes']:
        if mesh['max'][2] <= 0.5 or mesh['max'][1] < -1324.0:
            continue
        name = 'far-hills-' + kebab(mesh['name'].removeprefix('FarHills_'))
        region.models[name] = Model(export_source(build, 'island', mesh['name']),
                                    slots={'FarForest': forest, 'CoastRock': rock})
        region.groups.append((name, True, [[0.0, 0.0, 0.0, 0.0, 1.0]]))
    return region


ADAPTERS = {
    'treehouse': treehouse, 'brinecove': brinecove, 'belmonte': belmonte, 'hidamari': hidamari,
    'southwest': southwest, 'shrines': shrines, 'zeppelin': zeppelin, 'sword-camp': sword_camp,
    'far-hills': far_hills, 'megapark': megapark,
}
