"""Port Yorimichi's island forest into Hakuba's `forest` region: every tree, bush and tuft of grass the island's world,
Hidamari's city, Belmonte and Brinecove stand outside the regions Hakuba plants itself.

    uv run python games/yorimichi/hakuba_port/plants.py --build build/yorimichi [--models]

The island's world (`world.json`) stands its plants over the whole map; Yorimichi's map clears them inside
Hidamari's city and its north mountains, Belmonte and Brinecove, whose own plants replace them, and Hakuba's start
regions (`momiji-coast`, `momiji-village`, `woodland`) already hold theirs. The city (`hidamari/city.json`),
Belmonte and Brinecove (their `runtime.json`) add their own plants, kept everywhere. Each plant becomes the Hakuba
plant made from the same source model (`MODELS`), standing on Hakuba's ground at the depth it stood in its source.
Belmonte's and Brinecove's plants off Hakuba's ground, or well above it, stand on their ground props at their source
heights. Any other plant off Hakuba's ground, on a cliff, or of a model Hakuba has no plant for, is left out and
counted, as is any tree of the island's world or city closer than `TREE_SPACING_M` to a taller one.

`--models` first imports the tree models Hakuba lacks (`NEW`) as plants, with their full, middle and far detail levels
(`plant_convert.py`, one guarded Blender run each), and the leaf and bark textures they need (`TEXTURES`). It adds a
far version to Hakuba's own trees (`FAR`), moves every far version onto one atlas texture (`FAR_TEXTURE`), and imports
Brinecove's own plants from their GLBs, each material a texture of its colour.
"""
import argparse
import collections
import functools
import hashlib
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

from contact import ground_at, mosaic, supports
from ground import HAKUBA, WORLD, settings, triangles
from port import kebab

# Each Yorimichi plant model and the Hakuba plant made from it.
MODELS = {
    'Tree_Pine_A': 'garden-pine-a', 'Tree_Pine_B': 'garden-pine-b',
    'Tree_Maple_A': 'garden-maple-a', 'Tree_Maple_B': 'garden-maple-b',
    'Tree_Ginkgo': 'coast-ginkgo', 'Tree_Broad_A': 'coast-broad-a', 'Tree_Broad_B': 'coast-broad-b',
    'Tree_Cedar_A': 'coast-cedar-a', 'Tree_Cedar_B': 'garden-cedar-b',
    'Tree_Canopy_Amber': 'woodland-canopy-amber', 'Tree_Canopy_Crimson': 'woodland-canopy-crimson',
    'Tree_Canopy_Ginkgo': 'woodland-canopy-ginkgo', 'Tree_Canopy_Maple': 'woodland-canopy-maple',
    'Bush_Green_A': 'coast-green-a', 'Bush_Green_B': 'garden-green-b',
    'Bush_Ochre_A': 'coast-ochre-a', 'Bush_Ochre_B': 'coast-ochre-b',
    'Bush_Flower_A': 'coast-flower-a', 'Bush_Flower_B': 'garden-flower-b',
    'Grass_A': 'coast-grass-a', 'Grass_B': 'coast-grass-b', 'Litter': 'coast-litter',
    'Tree_Broad_C': 'coast-broad-c',
    'Tree_Forest_Ginkgo': 'forest-ginkgo', 'Tree_Forest_Maple': 'forest-maple', 'Tree_Forest_Oak': 'forest-oak',
    'Tree_Forest_Pine': 'forest-pine', 'Tree_Tuscan_Cypress': 'tuscan-cypress', 'Tree_Tuscan_Oak': 'tuscan-oak',
    'Tree_Tuscan_Olive': 'tuscan-olive', 'Tree_Tuscan_Pine': 'tuscan-pine',
}
# The models `--models` imports: each one's build folder, holding `<model>.fbx`, `<model>_LOD2.fbx` and a lower level,
# the full, middle and far detail levels, what it is and which level is its far version: the Forest and Tuscan trees'
# LOD3 is a few cards showing the tree's own renders.
NEW = {
    'Tree_Broad_C': ('foliage/Tree_Broad_C', 'a broadleaf tree of the island forest', 'LOD4'),
    'Tree_Forest_Ginkgo': ('forest/mesh-files', 'a ginkgo of the mountain forest around Hidamari', 'LOD3'),
    'Tree_Forest_Maple': ('forest/mesh-files', 'a maple of the mountain forest around Hidamari', 'LOD3'),
    'Tree_Forest_Oak': ('forest/mesh-files', 'an oak of the mountain forest around Hidamari', 'LOD3'),
    'Tree_Forest_Pine': ('forest/mesh-files', 'a pine of the mountain forest around Hidamari', 'LOD3'),
    'Tree_Tuscan_Cypress': ('forest/mesh-files', "a cypress of Belmonte's hills", 'LOD3'),
    'Tree_Tuscan_Oak': ('forest/mesh-files', "an oak of Belmonte's hills", 'LOD3'),
    'Tree_Tuscan_Olive': ('forest/mesh-files', "an olive tree of Belmonte's hills", 'LOD3'),
    'Tree_Tuscan_Pine': ('forest/mesh-files', "a stone pine of Belmonte's hills", 'LOD3'),
}
# Hakuba's own trees, made from the same sources, and the detail level each adds as its far version.
FAR = {name: 'LOD4' for name in ('Tree_Maple_A', 'Tree_Maple_B', 'Tree_Pine_A', 'Tree_Pine_B', 'Tree_Cedar_A',
                                 'Tree_Cedar_B', 'Tree_Broad_A', 'Tree_Broad_B', 'Tree_Ginkgo')}
# The trees whose far version shows their renders, and the texture of those renders.
IMPOSTORS = ('Forest_Ginkgo', 'Forest_Maple', 'Forest_Oak', 'Forest_Pine', 'Tuscan_Cypress', 'Tuscan_Oak',
             'Tuscan_Olive', 'Tuscan_Pine')


def impostor(tree):
    return f'{kebab(tree)}-impostor'


# Each source material slot and the Hakuba texture it shows; a slot's own texture replaces its colour, as in the
# source.
SLOTS = {
    'Bark': 'garden-bark', 'BarkTuscan': 'olive-bark', 'BarkOlive': 'olive-bark',
    'LeafGinkgo': 'coast-ginkgo-leaves', 'LeafMaple': 'garden-maple', 'LeafPine': 'garden-pine',
    'LeafSmall': 'garden-leaves', 'LeafCedar': 'garden-cedar', 'LeafCypress': 'tuscan-cypress-leaves',
    'LeafOak': 'tuscan-oak-leaves',
    'LeafOlive': 'tuscan-olive-leaves', 'LeafStonePine': 'tuscan-stone-pine-leaves',
    **{f'Tree_{tree}_Impostor': impostor(tree) for tree in IMPOSTORS},
}
# The textures Hakuba lacks: each one's source image in the build folder.
TEXTURES = {
    'olive-bark': 'textures/T_bark_olive.jpg', 'tuscan-cypress-leaves': 'forest/textures/T_LeafCypress.png',
    'tuscan-oak-leaves': 'forest/textures/T_LeafOak.png', 'tuscan-olive-leaves': 'forest/textures/T_LeafOlive.png',
    'tuscan-stone-pine-leaves': 'forest/textures/T_LeafStonePine.png',
}
# The far versions' textures share one atlas, `FAR_TEXTURE`, so a far tile merges every tree it holds into one mesh:
# each texture fills a cell `FAR_CELL` texels wide, its edge texels repeated `FAR_GUTTER` deep around it so that coarse
# mip levels keep its own colours. The renders are only seen there, from their source image.
FAR_TEXTURE, FAR_CELL, FAR_GUTTER = 'far-plants', 512, 16
RENDERS = {impostor(tree): f'forest/assembled/Tree_{tree}_colour.png' for tree in IMPOSTORS}
# Brinecove's own plants, each `brinecove-<name>` in Hakuba. Having no far version, only its palms, the port's
# landmarks, are seen from middle tiles.
BRINECOVE = 'SM_BC_Plant_'
BRINECOVE_AFAR = ('brinecove-palm',)
BLENDER = os.environ.get('BLENDER', '/usr/local/bin/blender')
# The trees' wind, push and haze response, as Hakuba's other trees have it.
PROFILE = """[source_profile]
direction_amplitude_shade = [0.3, -0.95, 0.16, 0.5]
slow = [0.28, 0.11, 0.16, 0.6]
fast = [0.7, 0.2, 0.3, 0.5]
global_slow = [0.37, 0.04, 0.45, 1.0]
global_fast = [1.1, 0.07, 0.3, 0.15]
global_tail = [2.9, 0.15, 0.0, 0.0]
push_haze = [1.7, 0.7, 30.0, 9000.0]
haze_colour = [0.0932, 0.2301, 0.5328]
"""
PLANTS = ('Tree_', 'Bush_Green', 'Bush_Ochre', 'Bush_Flower', 'Grass_', 'Litter')
# Ground cover too small to see from middle-detail tiles.
NEAR = {'coast-grass-a', 'coast-grass-b', 'coast-litter'}
# The start regions' rectangle, [west, south, east, north], whose plants Hakuba already has.
START = (-300.0, -172.0, 300.0, 300.0)
# A plant stands this far into the ground at most, and never above it; where the source ground differs from Hakuba's
# by more than `MISMATCH_M`, it sinks by `SINK_M`. A small plant sinks by no more than `SINK_SHARE` of its height.
DEEPEST_M, MISMATCH_M, SINK_M, SINK_SHARE = -0.6, 2.0, -0.3, 0.2
# A region's plant that its source stands well above Hakuba's ground keeps that height only where a ported prop's
# surface, as the exported tiles draw it, is within `SEAT_M` under it or over it; over nothing it would float, so it
# stands on the ground as the island's plants do.
SEAT_M = 0.5
# The steepest ground a plant stands on: the most the ground rises a metre from its foot (about 56°).
CLIFF = 1.5
# The island's own trees stand as close as 1.5 m, in stands far denser than Hakuba's woods, which the browser could not
# draw at its frame rate: of two trees closer than this, the smaller is left out.
TREE_SPACING_M = 4.0


def inside(rows, rectangle):
    west, south, east, north = rectangle
    return (rows[:, 0] > west) & (rows[:, 0] < east) & (rows[:, 1] > south) & (rows[:, 1] <= north)


def sources(build):
    """(source name, rows, kept off the ground) for each plant group in the island's world, cleared as Yorimichi's map
    clears it, then in Hidamari's city, Belmonte and Brinecove."""
    island = json.loads((build / 'world.json').read_text())['instances']
    city = json.loads((build / 'hidamari' / 'city.json').read_text())
    cleared = [(300.0, -450.0, 2200.0, 1600.0), tuple(city['north_bounds']), START,
               tuple(json.loads((build / 'belmonte' / 'runtime.json').read_text())['clearance_m']),
               tuple(json.loads((build / 'products' / 'brinecove' / 'map.json').read_text())['clearance_m'])]
    for name, rows in island.items():
        if name.startswith(PLANTS) and rows:
            rows = np.array([row[:5] for row in rows], float)
            yield name, rows[~np.any([inside(rows, rectangle) for rectangle in cleared], axis=0)], False
    for name, rows in city['instances'].items():
        if name.startswith(PLANTS) and rows:
            yield name, np.array([row[:5] for row in rows], float), False
    # Belmonte stands its plants from its runtime groups.
    runtime = json.loads((build / 'belmonte' / 'runtime.json').read_text())
    ox, oy, oz = runtime['origin_cm']
    for group in runtime['groups']:
        name = group['asset'].rsplit('.', 1)[-1]
        if name.startswith(PLANTS):
            yield name, transforms(group, ox, oy, oz), True
    # So does Brinecove, its plants (`SM_BC_Plant_*`) its own models.
    runtime = json.loads((build / 'brinecove' / 'runtime.json').read_text())
    ox, oy, oz = runtime['origin_cm']
    for group in runtime['groups']:
        name = group['asset'].rsplit('.', 1)[-1]
        if name.startswith(BRINECOVE):
            yield name, transforms(group, ox, oy, oz), True


def transforms(group, ox, oy, oz):
    """A runtime group's transforms, in centimetres from its region's origin in Unreal's frame (Y flipped), as rows."""
    rows = []
    for transform in group['transforms']:
        tx, ty, tz = transform['translation_cm']
        _, _, qz, qw = transform['rotation_xyzw']
        rows.append([(ox + tx) / 100, -(oy + ty) / 100, (oz + tz) / 100, -math.degrees(2 * math.atan2(qz, qw)),
                     transform['scale'][0]])
    return np.array(rows, float)


@functools.cache
def height(model):
    """How far a Hakuba plant reaches above its origin."""
    tris, _ = triangles(HAKUBA / 'plants' / model / 'src' / 'model.glb')
    return float(tris.reshape(-1, 3)[:, 1].max())


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def import_models(build):
    """Writes each texture of `TEXTURES` and each plant of `NEW` as a Hakuba asset, and adds a far version to each of
    Hakuba's own trees in `FAR`, then moves the far versions onto their atlas."""
    for name, source in TEXTURES.items():
        source = build / source
        folder = HAKUBA / 'textures' / name / 'src'
        folder.mkdir(parents=True, exist_ok=True)
        image = f'texture{source.suffix}'
        shutil.copyfile(source, folder / image)
        leaf = source.suffix == '.png'
        (folder / 'manifest.toml').write_text('# Original texture used by the island forest\'s trees.\n'
                                              f'path = "{image}"\nsha256 = "{sha256(source)}"\n')
        settings = ['alpha_shadow = true', f'source = "src/{image}"', 'alpha_cutoff = 0.4', 'mip_colour = "average"']
        (folder.parent / 'asset.toml').write_text('\n'.join(['# Source texture for the island forest\'s trees.',
                                                             'kind = "texture"'] + (settings if leaf else
                                                             [f'source = "src/{image}"'])) + '\n')
    for model, (folder, about, far) in NEW.items():
        levels = {'full': build / folder / f'{model}.fbx', 'middle': build / folder / f'{model}_LOD2.fbx',
                  'far': build / folder / f'{model}_{far}.fbx'}
        out = HAKUBA / 'plants' / MODELS[model] / 'src'
        out.mkdir(parents=True, exist_ok=True)
        write_plant_glb({level: leaves(converted(fbx)) if level == 'far' else converted(fbx)
                         for level, fbx in levels.items()}, out / 'model.glb')
        images = glb_json(out / 'model.glb')['images']
        textures = list(dict.fromkeys(Path(image['uri']).parent.name for image in images))
        (out / 'manifest.toml').write_text(
            '# Original foliage geometry and source detail levels.\npath = "model.glb"\n'
            f'sha256 = "{sha256(out / "model.glb")}"\nauthoring_fbx_sha256 = "{sha256(levels["full"])}"\n'
            f'authoring_lod2_fbx_sha256 = "{sha256(levels["middle"])}"\n'
            f'authoring_far_fbx_sha256 = "{sha256(levels["far"])}"\nconversion = "Blender FBX import; full LOD0, '
            f'middle LOD2 and far {far} retain per-corner positions, normals, UVs and RGBA"\n')
        (out.parent / 'asset.toml').write_text(
            f'# Source foliage: {about}.\nkind = "plant"\nshadow_distance_m = 80.0\nsource = "src/model.glb"\n'
            f'textures = {json.dumps(textures)}\n\n{PROFILE}')
        print(f'{MODELS[model]}: {textures}')
    for model, far in FAR.items():
        out = HAKUBA / 'plants' / MODELS[model] / 'src'
        nodes = read_plant_glb(out / 'model.glb')
        nodes['far'] = leaves(converted(build / 'foliage' / model / f'{model}_{far}.fbx'))
        write_plant_glb(nodes, out / 'model.glb')
        manifest = [line for line in (out / 'manifest.toml').read_text().splitlines()
                    if not line.startswith(('sha256', 'authoring_far', 'far_conversion'))]
        manifest.insert(2, f'sha256 = "{sha256(out / "model.glb")}"')
        manifest += [f'authoring_far_fbx_sha256 = "{sha256(build / "foliage" / model / f"{model}_{far}.fbx")}"',
                     f'far_conversion = "Blender FBX import of {far}, retaining per-corner positions, normals, UVs and '
                     'RGBA"']
        (out / 'manifest.toml').write_text('\n'.join(manifest) + '\n')
        print(f'{MODELS[model]}: far {far}')
    far_atlas(build)


def far_atlas(build):
    """Moves every plant's far version onto `FAR_TEXTURE`, an atlas of the textures they show, and records each
    plant's new source."""
    from PIL import Image
    plants = {}
    for source in sorted((HAKUBA / 'plants').glob('*/src/model.glb')):
        nodes = read_plant_glb(source)
        if 'far' in nodes:
            plants[source] = nodes
    textures = sorted({primitive['texture'] for nodes in plants.values() for primitive in nodes['far']})
    columns = math.ceil(math.sqrt(len(textures)))
    rows = math.ceil(len(textures) / columns)
    atlas = np.zeros((rows * FAR_CELL, columns * FAR_CELL, 4), np.uint8)
    images, inner = {}, FAR_CELL - 2 * FAR_GUTTER
    for k, texture in enumerate(textures):
        images[texture] = build / RENDERS[texture] if texture in RENDERS else next(
            (HAKUBA / 'textures' / texture / 'src').glob('texture.*'))
        # Premultiplied, so that the clear texels' colour never darkens the leaves' edges.
        cell = Image.open(images[texture]).convert('RGBA').convert('RGBa').resize((inner, inner), Image.LANCZOS)
        cell = np.pad(np.asarray(cell.convert('RGBA')), ((FAR_GUTTER,) * 2, (FAR_GUTTER,) * 2, (0, 0)), mode='edge')
        row, column = divmod(k, columns)
        atlas[row * FAR_CELL:(row + 1) * FAR_CELL, column * FAR_CELL:(column + 1) * FAR_CELL] = cell
    folder = HAKUBA / 'textures' / FAR_TEXTURE / 'src'
    folder.mkdir(parents=True, exist_ok=True)
    Image.fromarray(atlas, 'RGBA').save(folder / 'texture.png')
    (folder / 'manifest.toml').write_text(
        "# The plants' far textures, each in a cell of this atlas, row by row.\npath = \"texture.png\"\n"
        f'sha256 = "{sha256(folder / "texture.png")}"\n'
        + ''.join(f'authoring_{texture.replace("-", "_")}_sha256 = "{sha256(images[texture])}"\n'
                  for texture in textures))
    (folder.parent / 'asset.toml').write_text(
        "# Source texture for the plants' far versions.\nkind = \"texture\"\nsource = \"src/texture.png\"\n"
        'alpha_cutoff = 0.4\nmip_colour = "average"\n')
    size = np.array([columns, rows], np.float32) * FAR_CELL
    for source, nodes in plants.items():
        for primitive in nodes['far']:
            row, column = divmod(textures.index(primitive['texture']), columns)
            corner = np.array([column, row], np.float32) * FAR_CELL + FAR_GUTTER
            primitive['TEXCOORD_0'] = ((corner + primitive['TEXCOORD_0'] * inner) / size).astype('<f4')
            primitive.update(material='FarPlants', texture=FAR_TEXTURE)
        write_plant_glb(nodes, source)
        manifest = (source.parent / 'manifest.toml').read_text().splitlines()
        manifest = [f'sha256 = "{sha256(source)}"' if line.startswith('sha256') else line for line in manifest]
        (source.parent / 'manifest.toml').write_text('\n'.join(manifest) + '\n')
        shown = list(dict.fromkeys(Path(image['uri']).parent.name for image in glb_json(source)['images']))
        asset = (source.parent.parent / 'asset.toml').read_text().splitlines()
        asset = [f'textures = {json.dumps(shown)}' if line.startswith('textures') else line for line in asset]
        (source.parent.parent / 'asset.toml').write_text('\n'.join(asset) + '\n')
    print(f'{FAR_TEXTURE}: {len(textures)} textures, {len(plants)} plants')


def leaves(primitives):
    """A far version's cut-out parts, its leaves or its renders: its trunk is a pixel wide from where it shows, and
    leaving it out halves what a far tile draws."""
    return [primitive for primitive in primitives if primitive['masked']]


def converted(fbx):
    """The primitives of one detail level of a tree, converted by `plant_convert.py` in a guarded Blender run."""
    script = Path(__file__).resolve().parent / 'plant_convert.py'
    with tempfile.TemporaryDirectory() as scratch:
        # The converter is given every slot's texture and names those its model's slots show.
        command = [sys.executable, '-m', 'atelier.safety.guarded', '--report', str(Path(scratch) / 'guard'),
                   '--timeout', '1800', '--small', '4', '--kind', 'job', '--purpose',
                   f'hakuba port: convert {fbx.name}', '--',
                   BLENDER, '--background', '--threads', '3', '--python', str(script), '--',
                   str(fbx), str(Path(scratch) / 'level.glb'), *(f'{slot}={texture}' for slot, texture in SLOTS.items())]
        subprocess.run(['nice', '-n', '10', *command], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return read_plant_glb(Path(scratch) / 'level.glb')['full']


def read_plant_glb(path):
    """{node name: [primitive]} of a plant source GLB, each primitive its attributes, indices and material."""
    data = Path(path).read_bytes()
    size = int.from_bytes(data[12:16], 'little')
    gltf, blob = json.loads(data[20:20 + size]), data[28 + size:]

    def read(index):
        accessor = gltf['accessors'][index]
        view = gltf['bufferViews'][accessor['bufferView']]
        assert 'byteStride' not in view, f'{path}: interleaved attributes'
        assert not accessor.get('normalized'), f'{path}: quantised attributes'
        kind = {5126: '<f4', 5125: '<u4', 5123: '<u2', 5121: 'u1'}[accessor['componentType']]
        width = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}[accessor['type']]
        start = view.get('byteOffset', 0) + accessor.get('byteOffset', 0)
        return np.frombuffer(blob, kind, accessor['count'] * width, start).reshape(-1, width)

    nodes = {}
    for node in gltf['nodes']:
        primitives = []
        for primitive in gltf['meshes'][node['mesh']]['primitives']:
            material = gltf['materials'][primitive['material']]
            image = gltf['textures'][material['pbrMetallicRoughness']['baseColorTexture']['index']]['source']
            primitives.append({
                'material': material['name'], 'texture': Path(gltf['images'][image]['uri']).parent.name,
                'masked': material.get('alphaMode') == 'MASK', 'double': bool(material.get('doubleSided')),
                **{key: read(index).astype('<f4') for key, index in primitive['attributes'].items()},
                'indices': read(primitive['indices']).astype('<u4').reshape(-1)})
        nodes[node['name']] = primitives
    return nodes


def afar(model):
    """Whether middle tiles show a plant."""
    return model not in NEAR and (not model.startswith('brinecove-') or model.startswith(BRINECOVE_AFAR))


def brinecove_name(asset):
    """`SM_BC_Plant_CoverFern0` -> `brinecove-cover-fern0`."""
    return 'brinecove-' + kebab(asset.removeprefix(BRINECOVE))


def srgb(linear):
    linear = np.clip(linear, 0.0, 1.0)
    return np.where(linear <= 0.0031308, 12.92 * linear, 1.055 * linear ** (1 / 2.4) - 0.055)


def import_brinecove(build):
    """Writes each of Brinecove's plants as a Hakuba plant from its GLB, and each material it shows as a texture: the
    material's colour times its texture, or the colour alone. Wood stands still in the wind (red 0); every other part
    sways (red 1). Brinecove's plants have one detail level."""
    report = {entry['name']: entry for entry in
              json.loads((build / 'brinecove' / 'build-report.json').read_text())['materials'].values()}
    made = set()
    for source in sorted((build / 'brinecove' / 'glb').glob(f'{BRINECOVE}*.glb')):
        if source.stem.endswith('_Collision'):
            continue
        data = source.read_bytes()
        size = int.from_bytes(data[12:16], 'little')
        gltf, blob = json.loads(data[20:20 + size]), data[28 + size:]

        def read(index):
            accessor = gltf['accessors'][index]
            view = gltf['bufferViews'][accessor['bufferView']]
            kind = {5126: '<f4', 5125: '<u4', 5123: '<u2', 5121: 'u1'}[accessor['componentType']]
            width = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}[accessor['type']]
            assert 'byteStride' not in view, f'{source.name}: interleaved attributes'
            assert not accessor.get('normalized'), f'{source.name}: quantised attributes'
            start = view.get('byteOffset', 0) + accessor.get('byteOffset', 0)
            return np.frombuffer(blob, kind, accessor['count'] * width, start).reshape(-1, width)

        assert len(gltf['meshes']) == 1 and all(set(node) <= {'name', 'mesh'} for node in gltf['nodes']), \
            f'{source.name}: one mesh in an identity frame'
        primitives = []
        for mesh in gltf['meshes']:
            for primitive in mesh['primitives']:
                name = gltf['materials'][primitive['material']]['name']
                entry = report[f'MI_{name}']
                texture = 'brinecove-' + kebab(name.removeprefix('BC_'))
                if texture not in made:
                    made.add(texture)
                    write_colour_texture(build, entry, texture)
                attributes = primitive['attributes']
                positions = read(attributes['POSITION']).astype('<f4')
                indices = read(primitive['indices']).astype('<u4').reshape(-1, 3)
                a, b, c = (positions[indices[:, k]].astype(float) for k in range(3))
                # Hakuba's exporter refuses a triangle without area.
                indices = indices[np.linalg.norm(np.cross(b - a, c - a), axis=1) > 0].reshape(-1)
                wind = 0.0 if ('wood' in name or 'trunk' in name) else 1.0
                primitives.append({
                    'material': name, 'texture': texture, 'masked': entry['kind'] == 'masked',
                    'double': bool(gltf['materials'][primitive['material']].get('doubleSided')) or wind > 0,
                    'POSITION': positions, 'NORMAL': read(attributes['NORMAL']).astype('<f4'),
                    'TEXCOORD_0': read(attributes['TEXCOORD_0']).astype('<f4'),
                    'COLOR_0': np.tile(np.array([wind, 1.0, wind, 1.0], '<f4'), (len(positions), 1)),
                    'indices': indices})
        model = brinecove_name(source.stem)
        out = HAKUBA / 'plants' / model / 'src'
        out.mkdir(parents=True, exist_ok=True)
        write_plant_glb({'full': primitives}, out / 'model.glb')
        textures = list(dict.fromkeys(p['texture'] for p in primitives))
        (out / 'manifest.toml').write_text(
            '# Original foliage geometry.\npath = "model.glb"\n'
            f'sha256 = "{sha256(out / "model.glb")}"\nauthoring_glb_sha256 = "{sha256(source)}"\n'
            'conversion = "the source GLB\'s triangles, one primitive per material, with wind weights by material"\n')
        about = 'ground cover' if source.stem.startswith(f'{BRINECOVE}Cover') else 'a plant'
        # A plant standing on its foot, rather than reaching below it, declares its lowest height.
        lowest = min(float(p['POSITION'][p['indices'], 1].min()) for p in primitives)
        surface = f'surface_height_m = {np.float32(lowest)}\n' if lowest >= 0 else ''
        (out.parent / 'asset.toml').write_text(
            f'# Source foliage: {about} of Brinecove\'s hills.\nkind = "plant"\n'
            + ('' if about == 'ground cover' else 'shadow_distance_m = 80.0\n') + surface
            + f'source = "src/model.glb"\ntextures = {json.dumps(textures)}\n\n{PROFILE}')
        print(f'{model}: {textures}')


def write_colour_texture(build, entry, name):
    """A material's colour times its texture (or the colour alone, a few texels), as an sRGB texture asset."""
    from PIL import Image
    colour = np.array(entry['colour'][:3], np.float32)
    if entry['texture']:
        image = Image.open(build / 'brinecove' / 'textures' / entry['texture']).convert('RGBA')
        image = np.asarray(image, np.float32) / 255
        rgb = image[..., :3]
        linear = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4) * colour
        pixels = np.concatenate([srgb(linear), image[..., 3:]], axis=-1)
    else:
        pixels = np.concatenate([np.broadcast_to(srgb(colour), (4, 4, 3)), np.ones((4, 4, 1))], axis=-1)
    folder = HAKUBA / 'textures' / name / 'src'
    folder.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.round(pixels * 255).astype(np.uint8), 'RGBA').save(folder / 'texture.png')
    (folder / 'manifest.toml').write_text(
        f'# Brinecove\'s {entry["name"].removeprefix("MI_BC_").replace("_", " ")} material, its colour '
        + ('times its texture' if entry['texture'] else 'alone') + '.\npath = "texture.png"\n'
        f'sha256 = "{sha256(folder / "texture.png")}"\n'
        + (f'authoring_texture_sha256 = "{sha256(build / "brinecove" / "textures" / entry["texture"])}"\n'
           if entry['texture'] else ''))
    lines = ['# Source texture for Brinecove\'s plants.', 'kind = "texture"']
    if entry['kind'] == 'masked':
        lines += ['alpha_shadow = true', 'source = "src/texture.png"', 'alpha_cutoff = 0.4', 'mip_colour = "average"']
    else:
        lines.append('source = "src/texture.png"')
    (folder.parent / 'asset.toml').write_text('\n'.join(lines) + '\n')


def write_plant_glb(nodes, out):
    """A plant source GLB: a root node per detail level (`full`, and optionally `middle` and `far`), each with a
    primitive per material."""
    blob, views, accessors = bytearray(), [], []

    def add(array, kind, target):
        data = array.tobytes()
        views.append({'buffer': 0, 'byteOffset': len(blob), 'byteLength': len(data), 'target': target})
        blob.extend(data)
        blob.extend(b'\0' * (-len(blob) % 4))
        accessors.append({'bufferView': len(views) - 1, 'componentType': 5125 if kind == 'SCALAR' else 5126,
                          'count': len(array), 'type': kind})
        return len(accessors) - 1

    materials, images, meshes = {}, {}, []
    for name, primitives in nodes.items():
        gltf_primitives = []
        for primitive in primitives:
            position = add(primitive['POSITION'], 'VEC3', 34962)
            accessors[position]['min'] = primitive['POSITION'].min(0).tolist()
            accessors[position]['max'] = primitive['POSITION'].max(0).tolist()
            attributes = {'POSITION': position}
            for key, kind in (('NORMAL', 'VEC3'), ('TEXCOORD_0', 'VEC2'), ('COLOR_0', 'VEC4')):
                attributes[key] = add(primitive[key], kind, 34962)
            key = (primitive['material'], primitive['texture'], primitive['masked'], primitive['double'])
            materials.setdefault(key, len(materials))
            images.setdefault(primitive['texture'], len(images))
            gltf_primitives.append({'attributes': attributes, 'indices': add(primitive['indices'], 'SCALAR', 34963),
                                    'material': materials[key]})
        meshes.append({'name': name, 'primitives': gltf_primitives})
    gltf_materials = []
    for material, texture, masked, double in materials:
        entry = {'name': material,
                 'pbrMetallicRoughness': {'baseColorTexture': {'index': images[texture]}, 'metallicFactor': 0.0,
                                          'roughnessFactor': 1.0},
                 'extensions': {'KHR_materials_specular': {'specularFactor': 0.0}}}
        if masked:
            entry.update(alphaMode='MASK', alphaCutoff=0.4)
        if double:
            entry['doubleSided'] = True
        gltf_materials.append(entry)
    gltf = {'asset': {'version': '2.0'}, 'scene': 0, 'scenes': [{'nodes': list(range(len(meshes)))}],
            'nodes': [{'name': mesh['name'], 'mesh': k} for k, mesh in enumerate(meshes)], 'meshes': meshes,
            'accessors': accessors, 'bufferViews': views, 'materials': gltf_materials,
            'textures': [{'source': i, 'sampler': 0} for i in range(len(images))],
            'images': [{'uri': f'../../textures/{texture}/{texture}.ktx2'} for texture in images],
            'samplers': [{'wrapS': 10497, 'wrapT': 10497, 'magFilter': 9729, 'minFilter': 9987}],
            'extensionsUsed': ['KHR_materials_specular'], 'buffers': [{'byteLength': len(blob)}]}
    text = json.dumps(gltf, separators=(',', ':')).encode()
    text += b' ' * (-len(text) % 4)
    with open(out, 'wb') as fh:
        fh.write(struct.pack('<III', 0x46546C67, 2, 12 + 8 + len(text) + 8 + len(blob)))
        fh.write(struct.pack('<II', len(text), 0x4E4F534A) + text)
        fh.write(struct.pack('<II', len(blob), 0x004E4942) + bytes(blob))


def glb_json(path):
    data = Path(path).read_bytes()
    return json.loads(data[20:20 + int.from_bytes(data[12:16], 'little')])


def spaced(trees, skipped):
    """`trees`, (model, row, depth), less each tree closer than `TREE_SPACING_M` to a taller one."""
    cells, kept = collections.defaultdict(list), []
    for tree in sorted(trees, key=lambda tree: -height(tree[0]) * tree[1][4]):
        x, y = tree[1][:2]
        cx, cy = math.floor(x / TREE_SPACING_M), math.floor(y / TREE_SPACING_M)
        if any((x - ox) ** 2 + (y - oy) ** 2 < TREE_SPACING_M ** 2 for i in (-1, 0, 1) for j in (-1, 0, 1)
               for ox, oy in cells[cx + i, cy + j]):
            skipped['beside a taller tree'] += 1
            continue
        cells[cx, cy].append((x, y))
        kept.append(tree)
    return kept


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--build', type=Path, required=True, help="Yorimichi's build folder, build/yorimichi")
    parser.add_argument('--models', action='store_true', help="first import the tree models Hakuba lacks")
    args = parser.parse_args()
    if args.models:
        import_models(args.build.resolve())
        import_brinecove(args.build.resolve())
    world = settings()
    heights = mosaic(world)
    south_west, step = np.array(world['south_west_m']), world['ground_step_m']
    groups, skipped, trees = collections.defaultdict(list), collections.Counter(), []
    # The ported props as the last export drew them, which a region's plants may stand on.
    drawn = supports(world)
    for name, rows, kept in sources(args.build.resolve()):
        model = MODELS.get(name) or (brinecove_name(name) if name.startswith(BRINECOVE) else None)
        if model is None:
            skipped[name] += len(rows)
            continue
        # Rounded as written, so the ground is read where the exporter reads it.
        rows[:, :2] = rows[:, :2].round(3)
        ground = ground_at(heights, south_west, step, rows[:, 0], rows[:, 1])
        # A plant on a cliff, the ground steeper than `CLIFF` across its foot, is left out.
        rise = np.nanmax([np.abs(ground_at(heights, south_west, step, rows[:, 0] + dx, rows[:, 1] + dy) - ground)
                          for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))], axis=0)
        cliff = rise > CLIFF
        skipped['on a cliff'] += int(cliff.sum())
        rows, ground = rows[~cliff], ground[~cliff]
        off = np.isnan(ground)
        if kept:
            # Off Hakuba's ground, or well above it on a ported prop, the plant keeps its source height; well above
            # it over no prop, it stands on the ground.
            with np.errstate(invalid='ignore'):
                off |= rows[:, 2] - ground > MISMATCH_M
            surface = drawn.heights(rows[off, 0], rows[off, 1], rows[off, 2])
            with np.errstate(invalid='ignore'):
                off[off] = np.isnan(ground[off]) | (rows[off, 2] - surface <= SEAT_M)
            groups[model, False].extend([round(x, 3), round(y, 3), round(z, 3), round(yaw % 360.0, 2), round(scale, 4)]
                                        for x, y, z, yaw, scale in rows[off].tolist())
        else:
            skipped['off the ground'] += int(off.sum())
        rows, ground = rows[~off], ground[~off]
        depth = rows[:, 2] - ground
        deepest = np.maximum(DEEPEST_M, -SINK_SHARE * height(model) * rows[:, 4])
        depth = np.clip(np.where(np.abs(depth) > MISMATCH_M, SINK_M, depth), deepest, 0.0)
        if not kept and name.startswith('Tree_'):
            trees.extend((model, row, d) for row, d in zip(rows.tolist(), depth.tolist()))
            continue
        groups[model, True].extend([round(x, 3), round(y, 3), round(d, 3), round(yaw % 360.0, 2), round(scale, 4)]
                             for (x, y, _, yaw, scale), d in zip(rows.tolist(), depth.tolist()))
    for model, (x, y, _, yaw, scale), d in spaced(trees, skipped):
        groups[model, True].append([round(x, 3), round(y, 3), round(d, 3), round(yaw % 360.0, 2), round(scale, 4)])
    for model, _ in groups:
        assert (HAKUBA / 'plants' / model / 'asset.toml').is_file(), f'no Hakuba plant {model}'
    placements = [{'model': f'plants/{model}', 'afar': afar(model), 'on_ground': on_ground, 'instances': rows}
                  for (model, on_ground), rows in sorted(groups.items()) if rows]
    folder = WORLD / 'src' / 'regions' / 'forest'
    folder.mkdir(parents=True, exist_ok=True)
    text = json.dumps({'groups': placements}, separators=(',', ':'))
    (folder / 'placements.json').write_text(text.replace('{"model"', '\n{"model"') + '\n')
    for (model, on_ground), rows in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        print(f'{model}{"" if on_ground else " (source height)"}: {len(rows)}')
    print(f'forest: {sum(map(len, groups.values()))} plants; left out: {dict(skipped)}')


if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    main()
