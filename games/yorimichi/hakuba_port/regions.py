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
    """Belmonte and the Haras valley: the town, its ground, the hippodrome and the northern hills. A material draws as
    Belmonte's material does (`import_belmonte.py`): its colour, tint and brightness times its texture on the mesh's
    UVs over the material's tile in metres; a detail texture (one that is not an atlas) is neutral grey, so it counts
    twice. Terrain uses its green layer; water is left out."""
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
            colour.update(sample=str(textures / entry['texture']), tile=entry['tile_m'],
                          gain=1.0 if entry['atlas'] else 2.0)
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


# The zeppelin docks first at its first station, the Woodland air station, as Yorimichi's service starts. Its parts'
# offsets, in metres east, north and up, as the service attaches them: the deck gate from the ship's datum, a station's
# dock gate and gangway from the station's origin.
ZEPPELIN_DOCK = 0
ZEPPELIN_DECK_GATE = (-0.85, -1.70, 0.0)
ZEPPELIN_DOCK_GATE = (5.15, 1.04, 1.65)
ZEPPELIN_GANGWAY = (6.0, 1.04, 1.65)
ZEPPELIN_PARTS = {'ZP_Airship': 'hull, deck and envelope', 'ZP_Motors': 'motor pods',
                  'ZP_Propeller': 'propellers', 'ZP_Gate': 'deck and dock gates', 'ZP_Gangway': 'gangway'}


def zeppelin(build):
    """The air stations and the trail up to the woodland station, and the airship docked at its first stop, the
    Woodland air station, standing still as the service starts there: its hull and envelope, motors, both propellers
    and its deck gate shut, the station's gangway let down to it, and every station's dock gate shut. Each part stands
    where Yorimichi's zeppelin service puts it, relative to the ship's or the station's datum. Everything is coloured
    by its palette per vertex, as Yorimichi's materials draw it (the envelope's own material shades the same vertex
    colour). Only the gangway is solid, as the service makes it walkable at the dock; the ship has no collision."""
    placed = {**_core(build), **json.loads((build / 'hidamari' / 'city.json').read_text())['instances']}
    line = json.loads((build / 'world.json').read_text())['zeppelin']
    region = Region('zeppelin', 'the air stations and the docked airship')
    for asset in ('ZP_Woodland', 'ZP_Belmonte', 'ZP_Trail', 'ZP_City', 'ZP_MegaPark'):
        if asset not in placed:
            continue
        name = 'zeppelin-' + kebab(asset.removeprefix('ZP_'))
        region.models[name] = Model(export_source(build, 'zeppelin', asset), default={'vertex': True})
        region.groups.append((name, None, placed[asset]))
    stations = line['stations']
    ship = stations[ZEPPELIN_DOCK]['ship']
    origin = stations[ZEPPELIN_DOCK]['origin']

    def at(datum, offset):
        return [datum[0] + offset[0], datum[1] + offset[1], datum[2] + offset[2], 0.0, 1.0]
    parts = {'ZP_Airship': [at(ship, (0, 0, 0))], 'ZP_Motors': [at(ship, (0, 0, 0))],
             'ZP_Propeller': [at(ship, c) for c in line['propeller_centers']],
             'ZP_Gate': [at(ship, ZEPPELIN_DECK_GATE)] + [at(s['origin'], ZEPPELIN_DOCK_GATE) for s in stations],
             'ZP_Gangway': [at(origin, ZEPPELIN_GANGWAY)]}
    for asset, rows in parts.items():
        name = 'zeppelin-' + kebab(asset.removeprefix('ZP_'))
        region.models[name] = Model(export_source(build, 'zeppelin', asset), default={'vertex': True},
                                    solid=asset == 'ZP_Gangway',
                                    about=f"The zeppelin line's {ZEPPELIN_PARTS[asset]}.")
        region.groups.append((name, None, rows))
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
    left out, and so are the park's own trees and parked cars, which are plants and the `kei` region's models."""
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


def kei(build):
    """The Mega Park car park's four kei cars (`assets/vehicles/kei/build.py`, assembled into `kei/assets`), flat
    shaded in their vertex colours as Yorimichi's village material draws them (`import_kei.py`), each solid with its
    box hulls, parked where `megapark/park.json` `props` parks it: its nose along `forward` and its roof along `up` in
    the park actor's frame, about the ground under its middle. The cars stand a few degrees out of upright on the car
    park's slope, so each car, placed once, takes its tilt into its own mesh and its heading as its placement's yaw."""
    import numpy as np
    park = json.loads((build / 'megapark' / 'park.json').read_text())
    x0, y0, z0 = park['location_cm']
    turn = math.radians(park['yaw_deg'])
    actor = np.array([[math.cos(turn), -math.sin(turn), 0.0], [math.sin(turn), math.cos(turn), 0.0], [0.0, 0.0, 1.0]])
    # Hakuba's y is Unreal's -y.
    flip = np.diag([1.0, -1.0, 1.0])
    region = Region('kei', "the Mega Park car park's kei cars")
    for entry in park['props']:
        asset = entry['mesh']
        if not asset.startswith('SM_Kei_'):
            continue
        forward, up = (flip @ actor @ np.asarray(entry[key], float) for key in ('forward', 'up'))
        up /= np.linalg.norm(up)
        forward -= up * (forward @ up)
        forward /= np.linalg.norm(forward)
        # The car's frame on the map: its nose (+x), its left (+y) and its roof (+z), as its builder makes it.
        frame = np.column_stack([forward, np.cross(up, forward), up])
        heading = math.atan2(forward[1], forward[0])
        c, s = math.cos(heading), math.sin(heading)
        tilt = np.array([[c, s, 0.0], [-s, c, 0.0], [0.0, 0.0, 1.0]]) @ frame
        name = 'kei-' + kebab(asset.removeprefix('SM_Kei_'))
        region.models[name] = Model(build / 'kei' / 'assets' / f'{asset}.fbx', default={'vertex': True},
                                    turn=np.round(tilt, 6).tolist())
        ux, uy, uz = actor @ np.asarray(entry['location_cm'], float) + (x0, y0, z0)
        region.groups.append((name, None, [[ux / 100, -uy / 100, uz / 100, math.degrees(heading), 1.0]]))
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


def flat(materials):
    """Colour rules for materials given as (sRGB 0-255, roughness, metallic): each its linear colour, a non-metal's
    sheen folded in as `transport.py` folds it, since Hakuba draws every surface matte."""
    from transport import SHEEN
    rules = {}
    for name, (rgb, roughness, metallic) in materials.items():
        linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in (v / 255 for v in rgb)]
        rules[name] = {'rgb': [c + (SHEEN * (1 - roughness) if metallic == 0 else 0.0) for c in linear]}
    return rules


def gondola(build):
    """The three gondola lines, standing still where `gondola_fit.py` fitted them to Hakuba's ground (its
    `gondola/hakuba/gondola.json`): the stations with their posts and stairs, the towers, the haul ropes and the
    cabins. A timber material draws the kit's procedural timber texture on the mesh's UVs in metres, as the kit's
    materials do; the others are their flat colours."""
    folder = build / 'gondola' / 'hakuba'
    data = json.loads((folder / 'gondola.json').read_text())
    slots = flat(data['materials'])
    for name, texture in data['textured_materials'].items():
        slots[name] = {'sample': str(folder / 'textures' / f'{texture}.png'), 'rgb': [1.0, 1.0, 1.0]}
    region = Region('gondola', 'the gondola lines between Hidamari, Belmonte and Crater Park')
    for piece in data['pieces']:
        name = 'gondola-' + kebab(Path(piece['fbx']).stem.removeprefix('GD_'))
        collision = folder / 'assets' / piece['collision'] if piece['collision'] else None
        region.models[name] = Model(folder / 'assets' / piece['fbx'], slots=slots, solid=piece['solid'],
                                    collision=collision, about=piece['about'][0].upper() + piece['about'][1:] + '.')
        region.groups.append((name, None, piece['instances']))
    return region


def ferry(build):
    """The passenger ferry, docked at Hidamari's berth, and its two terminals, in their materials' flat colours: the
    ship and the terminals draw no images. The Hidamari terminal is modelled in map metres, the Brinecove one in
    Brinecove's own frame, moved onto the map by its recorded offset. The hull, each landing and each brow are solid,
    so the walk from the quay onto the deck has collision all the way.

    The boarding gate is built about its hinge at the sill, so it stands in each of the ship's boarding openings as the
    source's ferry service hangs it (`ferry/service.py`'s `ship_data`): its hinge at the opening's sill, `width - 0.2`
    of rail running across the opening. Berthed with the brow down, the gate on the berth's side, starboard as every
    terminal berths the ship, stands swung open outboard (the source's `open_yaw`, given in Unreal's left-handed turn);
    the other stays shut."""
    ship = build / 'ferry'
    terminals = json.loads((ship / 'terminals' / 'manifest.json').read_text())
    site = json.loads((ship / 'terminals' / 'site.json').read_text())
    built = json.loads((ship / 'manifest.json').read_text())
    slots = flat({**built['materials'], **terminals['materials']})
    region = Region('ferry', 'the passenger ferry between Hidamari and Brinecove')
    berth = site['hidamari']['berth']
    docked = [[*berth['centre'], 0.0, berth['heading_deg'], 1.0]]
    for part in ('Hull', 'Superstructure', 'Funnel', 'Lifeboats', 'Rails', 'Masts', 'Fittings', 'BoardingGate'):
        hull = part == 'Hull'
        region.models[f'ferry-{kebab(part)}'] = Model(
            ship / 'assets' / f'FY_{part}.fbx', slots=slots, solid=hull,
            collision=ship / 'assets' / 'FY_Collision.fbx' if hull else None,
            about=f"The passenger ferry's {kebab(part).replace('-', ' ')}, docked at Hidamari.")
        if part != 'BoardingGate':
            region.groups.append((f'ferry-{kebab(part)}', True, docked))
    turn = math.radians(berth['heading_deg'])
    gates = []
    for opening in built['boarding_openings']:
        x, y, z = opening['centre']
        x -= (opening['width'] - 0.2) / 2
        swung = -90.0 if opening['side'] == 'starboard' else 0.0
        gates.append([berth['centre'][0] + x * math.cos(turn) - y * math.sin(turn),
                      berth['centre'][1] + x * math.sin(turn) + y * math.cos(turn), z,
                      berth['heading_deg'] + swung, 1.0])
    region.groups.append(('ferry-boarding-gate', True, gates))
    for key, prefix, landing in (('hidamari', 'HD', 'Jetty'), ('brinecove', 'BC', 'Landing')):
        terminal = terminals['terminals'][key]
        offset = (0.0, 0.0) if terminal['frame'] == 'world' else site[key]['origin_m']
        x, y, z = terminal['anchor']
        at = [[x + offset[0], y + offset[1], z, 0.0, 1.0]]
        for mesh in terminal['meshes']:
            part = mesh.removeprefix(f'FT_{prefix}_')
            name = f'ferry-{key}-{kebab(part)}'
            # The landing carries the terminal's fixed hulls; the brow, which swings in the source game, its own.
            own = part == landing
            region.models[name] = Model(
                ship / 'terminals' / 'assets' / f'{mesh}.fbx', slots=slots, solid=own or part == 'Brow',
                collision=ship / 'terminals' / 'assets' / f'FT_{prefix}_Collision.fbx' if own else None,
                about=f"The {kebab(part).replace('-', ' ')} of the ferry terminal at {key.title()}.")
            region.groups.append((name, None, at))
    return region


# Sunset Pier's layout, which places its meshes and trees in park-local metres.
SKATEPARK = Path(__file__).resolve().parents[1] / 'world' / 'regions' / 'skatepark' / 'park.json'
# Each logical pier mesh and what it is, by its name in `park.json`.
PIER_PARTS = {
    'SM_SkatePier': "deck, its terraces and its bowl's shell", 'SM_SkatePierPilings': 'pilings',
    'SM_SkateParkFeatures': 'skating features: rails, ledges, stairs, banks and transitions',
    'SM_SkatePath': 'path in from the coast', 'SM_SkateParkFurniture': 'benches, pavilion and lamps',
    'SM_SkateParkPlanting': 'stone gardens and grasses', 'SM_SkateParkDecals': 'floor paint and mural',
}
# The pier's material maps, by the material a slot names (`Pier_<material>`): painted steel draws steel's maps.
PIER_MAPS = {'painted': 'steel'}
# The path in from the coast runs over the ground, which owns its walking surface: the region's `layout.rs` lays it
# from `pier_path.py`'s triangles, and the path's props keep its skirts, edges and railings.
PIER_GROUND = {'SM_SkatePath': ['Pier_concrete']}


def skatepark(build):
    """Sunset Pier, the skate plaza on the sea south of Hidamari: the pieces `world.skatepark.assembled` exports, each
    stood at the park's origin from `park.json` (park-local metres east, north and up, turned by its `yaw_deg`), the
    board left out. A piece reaches across up to 170 m, so it is cut along Hakuba's tile grid into one model per tile
    it has faces in (`Model.keep`), each standing, and streaming, with its own tile. Its materials draw the pier's own
    finished albedo maps (`skatepark/textures`) on the meshes' UVs, which already count each map's repeat, as
    Yorimichi's materials do: the map times twice the linear vertex colour, which carries the palette and the baked
    shading, and the mural its map alone. The deck, pilings, features, path and furniture are solid, colliding with
    their own triangles as the source rides them; the planting and the floor paint are not. The path's vertices at
    the coast road's edge meet it (`seam.py`), as `pier_path.py` moves its walking surface's."""
    from ground import settings
    from seam import edge
    park = json.loads(SKATEPARK.read_text())
    if park['yaw_deg']:
        raise ValueError("Sunset Pier's tile cuts assume the park unturned")
    blocks = {mesh['name']: mesh['blocks'] for mesh in park['meshes']}
    folder = build / 'atomic_regions' / 'skatepark'
    textures = build / 'skatepark' / 'textures'
    maps = json.loads((textures / 'textures.json').read_text())
    exports = json.loads((folder / 'assets' / 'manifest.json').read_text())['exports']
    pieces = json.loads((folder / 'logical-pieces.json').read_text())['parents']
    world = settings()
    tile = world['tile_steps'] * world['ground_step_m']
    west, south = (s - o for s, o in zip(world['south_west_m'], park['origin']))
    region = Region('skatepark', 'Sunset Pier, the skate plaza on the sea south of Hidamari')
    at = [[*park['origin'], park['yaw_deg'], 1.0]]
    for parent, keys in pieces.items():
        for key in keys:
            row = next(row for row in exports if row['asset'] == key)
            slots = {}
            for slot in row['metadata']['slots']:
                material = slot.removeprefix('Pier_')
                image = str(textures / maps[PIER_MAPS.get(material, material)]['maps']['albedo'])
                slots[slot] = ({'sample': image} if material == 'mural' else
                               {'sample': image, 'vertex': True, 'decode': True, 'gain': 2.0})
            (x0, y0, _), (x1, y1, _) = row['bounds']
            meet = None
            if parent in PIER_GROUND:
                ox, oy, _ = park['origin']
                meet = (edge([x0 + ox, y0 + oy, x1 + ox, y1 + oy]) - park['origin']).tolist() or None
            for i in range(math.floor((x0 - west) / tile), math.floor((x1 - west) / tile) + 1):
                for j in range(math.floor((y0 - south) / tile), math.floor((y1 - south) / tile) + 1):
                    name = f"skatepark-{kebab(key.removeprefix('SM_Skate'))}-{i}-{j}"
                    keep = [west + i * tile, south + j * tile, west + (i + 1) * tile, south + (j + 1) * tile]
                    region.models[name] = Model(folder / 'assets' / row['primary'], slots=slots,
                                                solid=blocks[parent], keep=keep, ground_owned=PIER_GROUND.get(parent), meet=meet,
                                                about=f"A piece of Sunset Pier's {PIER_PARTS[parent]}.")
                    region.groups.append((name, None, at))


# Linear colours of the course's untextured surfaces, as `import_hippodrome.py` makes their materials.
HIPPODROME_SURFACES = {'HD_Stone': {'rgb': [0.36, 0.35, 0.32]}, 'HD_Rail': {'rgb': [0.86, 0.85, 0.80]}}


def hippodrome(build):
    """The Hidamari Hippodrome, the racecourse on the slope north of the city: its grass platform and the skirt down to
    the hillside, the dirt track and its rails, the grandstand, the judges' tower, the finish post and the tote board,
    as `hippodrome.py` writes them in `hippodrome/region`. Each stands where the venue data places it round the course
    origin, as Yorimichi's `AHippodrome` does: at the origin plus its offset, in map metres, turned by its yaw. The
    course draws its grass and dirt textures, its stone skirts and white rails the colours Yorimichi's import gives them
    (`HIPPODROME_SURFACES`); each structure draws its own image."""
    out = build / 'hippodrome' / 'region'
    data = json.loads((out / 'hippodrome.json').read_text())
    ox, oy, oz = data['origin']
    slots = {material: {'sample': str(out / 'textures' / image)} for material, image in data['textures'].items()}
    slots.update(HIPPODROME_SURFACES)
    for image in (out / 'textures').glob('HD_*.*'):
        slots.setdefault(image.stem, {'sample': str(image)})
    region = Region('hippodrome', 'the Hidamari Hippodrome on the slope north of the city')
    for mesh in data['meshes']:
        # The lane is the region's ground, levelled to its ramp and laid with dirt by its `layout.rs`.
        if mesh['name'] in ('SM_HD_Lane', 'SM_HD_LaneSkirt'):
            continue
        name = 'hippodrome-' + kebab(mesh['name'].removeprefix('SM_HD_'))
        region.models[name] = Model(out / 'glb' / f"{mesh['name']}.glb", slots=slots)
        x, y, z = mesh['at']
        region.groups.append((name, None, [[ox + x, oy + y, oz + z, mesh['yaw'], 1.0]]))
    return region


ADAPTERS = {
    'treehouse': treehouse, 'brinecove': brinecove, 'belmonte': belmonte, 'hidamari': hidamari,
    'southwest': southwest, 'shrines': shrines, 'zeppelin': zeppelin, 'sword-camp': sword_camp,
    'far-hills': far_hills, 'megapark': megapark, 'gondola': gondola, 'ferry': ferry, 'kei': kei,
    'skatepark': skatepark, 'hippodrome': hippodrome,
}
