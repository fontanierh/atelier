"""Build Belmonte from the committed environmental library, without Haras code."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import yori  # noqa: E402
import hashlib
import json
import shutil

import numpy as np
from PIL import Image
from atelier.gltf import glb_parts
from belmonte import layout as L, source, planting, terrain, appearance

OUT = yori.OUT / 'belmonte'


def finish_surfaces(data):
    """Current scenery and a Tuscan ground palette with neutral texture grain."""
    materials, images = {}, {}
    for path, entry in data['materials'].items():
        if path.endswith('MI_B_foliage'):
            continue
        scalars, vectors = entry['scalars'], entry['vectors']
        atlas = 'SalonPosters' in path or '/Atelier/' in path
        texture = entry['textures'].get('BaseColor') or entry['textures'].get('DryColor')
        name = 'MI_BM_' + hashlib.sha256(path.encode()).hexdigest()[:12]
        terrain = 'terrain_' in path
        colour = vectors.get('Target', vectors.get('Color', [1., 1., 1., 1.]))
        tint = np.array(vectors.get('Tint', [1., 1., 1., 1.])) * vectors.get('StableColor', [1., 1., 1., 1.])
        layers = {}
        if terrain:
            layers={layer:list(colour) for layer,colour in source.TERRAIN_LAYERS.items()}
        materials[path] = {'name': name, 'colour': colour, 'tint': tint.tolist(), 'terrain': terrain,
                           'layers': layers, 'tile_m': 9. if terrain else 1. if atlas else 1. / max(scalars.get('Scale', .25), .001),
                           'white_vertex': 'Target' in vectors or 'Color' in vectors,
                           'brightness': scalars.get('Brightness', 1.), 'atlas': atlas,
                           'water': 'water' in path.lower(), 'texture': None}
        if not texture:
            continue
        key = ('tuscan-ground' if terrain else texture) + (':atlas' if atlas else ':detail')
        if key not in images:
            if terrain:
                image_path=yori.ASSETS/'environment/textures/tuscan-ground.jpg'
                provenance=json.loads(image_path.with_suffix('.provenance.json').read_text())
                assert source.sha(image_path)==provenance['source_sha256'],image_path
            else:
                image_info = data['textures'][texture]
                image_path = source.LIBRARY / image_info['file']
                assert source.sha(image_path) == image_info['sha256'], image_path
            image = Image.open(image_path).convert('RGB')
            image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
            if not atlas:
                from surface_textures import neutral_detail
                image = neutral_detail(image)
            file = 'T_BM_' + hashlib.sha256(key.encode()).hexdigest()[:12] + '.png'
            image.save(OUT / 'textures' / file)
            images[key] = file
        materials[path]['texture'] = images[key]
    return materials


def surroundings():
    collar, seam = terrain.collar()
    entries = []
    for name, mesh in [('SM_BM_NorthApron', collar), ('SM_BM_NorthCountry', terrain.country())]:
        path = OUT / 'glb' / (name + '.glb')
        info = mesh.save(path, 'BM_000_Ground')
        appearance.paint_join(path, mesh)
        entries.append({'name': name, 'path': path.relative_to(OUT).as_posix(), 'sha256': source.sha(path),
                        'bounds_m': [info['min'], info['max']], 'triangles': info['triangles'], 'slots': ['Ground']})
    return entries, seam


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'glb').mkdir(exist_ok=True)
    (OUT / 'textures').mkdir(exist_ok=True)
    data = source.manifest()
    materials = finish_surfaces(data)
    by_asset, meshes, retained_slots = {}, [], {}
    for entry in data['meshes']:
        path = source.LIBRARY / entry['path']
        assert source.sha(path) == entry['sha256'], path
        destination = OUT / 'glb' / path.name
        shutil.copy2(path, destination)
        entry = dict(entry, path=destination.relative_to(OUT).as_posix())
        meshes.append(entry)
        by_asset[entry['source_asset']] = entry
        doc, _ = glb_parts(path.read_bytes())
        retained_slots[entry['source_asset']] = [int(material['name'].split('_')[1]) for material in doc['materials']]
        if 'collision' in entry:
            collision = source.LIBRARY / entry['collision']['path']
            assert source.sha(collision) == entry['collision']['sha256'], collision
            shutil.copy2(collision, OUT / 'glb' / collision.name)
    extra, seam = surroundings()
    meshes.extend(extra)
    grouped = {}
    for placement in data['placements']:
        entry = by_asset[placement['asset']]
        # glTF omits unused slots. The retained names pin their original index.
        slots = retained_slots[placement['asset']]
        names = [materials[placement['materials'][slot]]['name'] for slot in slots]
        bindings = tuple(f'/Game/Belmonte/Materials/{name}.{name}' for name in names)
        key = (entry['name'], bindings)
        grouped.setdefault(key, []).append(placement['transform'])
    groups = []
    for (name, bindings), transforms in grouped.items():
        water = any(word in name for word in ('Water', 'Foam'))
        entry = next(entry for entry in meshes if entry['name'] == name)
        span = max(np.subtract(entry['bounds_m'][1], entry['bounds_m'][0]))
        span *= max(max(abs(value) for value in transform['scale']) for transform in transforms)
        groups.append({'asset': f'/Game/Belmonte/Meshes/{name}.{name}', 'materials': list(bindings),
                       'plant': False, 'collision': not water, 'shadow': not water,
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
    plants, plant_report = planting.replacements(data, source.terrain().height)
    woods = planting.woodland(source.Surface(source.triangles(OUT / 'glb/SM_BM_NorthApron.glb')))
    for name, transforms in woods.items():
        plants.setdefault(name, []).extend(transforms)
    plant_report['connecting_woodland'] = sum(len(v) for v in woods.values())
    plant_report['tree_detail'] = 'Original detailed leaf geometry; no backdrop or _lo assets'
    for name, transforms in plants.items():
        tree = name.startswith(('Tree_', 'HD_'))
        grass = name.startswith('Grass_')
        groups.append({'asset': f'/Game/Japan/Assets/{name}.{name}', 'materials': [], 'plant': True,
                       'collision': tree, 'shadow': not grass, 'cull_cm': 8000 if grass else 36000 if not tree else 400000,
                       'transforms': transforms})
    signs = data['signs']
    for sign in signs:
        if sign['text'] == 'Votre écurie':
            sign['text'] = 'Haras de Belmonte'
    town_z = float(source.terrain().height(0., -18.)) + L.ORIGIN[2] + 1.
    runtime = {'version': 1, 'origin_cm': L.native_origin(), 'bounds_m': L.BOUNDS,
               'clearance_m': list(terrain.OUTER), 'groups': groups, 'signs': signs, 'railway_corridor': L.RAILWAY,
               'zones': [{'key': 'belmonte', 'name': 'Belmonte · town square', 'x': L.ORIGIN[0],
                          'y': L.ORIGIN[1] - 18., 'z': town_z, 'yaw': 90.,
                          'hint': 'Town, estates and countryside racecourses north of the volcano'},
                         {'key': 'belmonte_course', 'name': 'Belmonte · racecourse',
                          'x': 385., 'y': 4255. + L.NORTH_SHIFT, 'z': float(L.ORIGIN[2] + 30.2), 'yaw': 90.,
                          'hint': 'Explore the turf and sand course and its grandstands'},
                         {'key': 'belmonte_training', 'name': 'Belmonte · training grounds',
                          'x': 230., 'y': 4560. + L.NORTH_SHIFT, 'z': float(L.ORIGIN[2] + 30.2), 'yaw': 0.,
                          'hint': 'Countryside arenas and practice grounds'}]}
    (OUT / 'runtime.json').write_text(json.dumps(runtime, separators=(',', ':')) + '\n')
    (OUT / 'build-report.json').write_text(json.dumps({'meshes': meshes, 'materials': materials,
                                                     'planting': plant_report, 'seam': seam}, indent=1) + '\n')
    print(f'BELMONTE BUILD COMPLETE: {len(meshes)} meshes, {len(groups)} groups, {sum(len(v) for v in plants.values())} plants', flush=True)


if __name__ == '__main__':
    main()
