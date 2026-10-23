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
from atelier.model_files import source_records, retain_files
from belmonte import layout as L, source, planting, terrain, appearance, model_pieces, ground_pieces, runtime_layout

OUT = yori.OUT / 'belmonte'

# Display text only: the committed scene library keeps its source strings, while the
# runtime signs are written in English. Keys are source labels, not identifiers.
SIGN_TRANSLATIONS = runtime_layout.SIGN_TRANSLATIONS


def clear_railway(plants):
    return runtime_layout.clear_railway(plants)


def finish_surfaces(data):
    from belmonte.material_preparation import finish
    return finish(data,OUT,yori.ASSETS,source.LIBRARY)


def surroundings():
    from hidamari import mountains
    from train import earthworks
    collar, seam = terrain.collar()
    entries = []
    (OUT / 'natural').mkdir(exist_ok=True)
    parts = [('SM_BM_NorthApron', collar, 2.5), ('SM_BM_NorthCountry', terrain.country(), 4.)]
    joins = [(0, terrain.OUTER[0]), (0, terrain.OUTER[2]), (1, terrain.OUTER[3])]
    # The coastal profile is nonlinear between the original coarse grid knots.
    # Both natural and carved products must share every boundary knot, even
    # where the railway does not reach.
    earthworks.stitch([p[1] for p in parts], L.ORIGIN, joins, whole_seam=True)
    for name, mesh, step in parts:
        # The natural ground stays beside the built one: the route study samples it, never the railway's own cuttings.
        mesh.save(OUT / 'natural' / (name + '.glb'), 'BM_000_Ground')
        # The valley's committed terrain is not carved: the apron's carving eases out towards their seam (the bank
        # mesh, train/track.py, covers the line there) so the rim stays closed.
        earthworks.quads(mesh, L.ORIGIN, step, hidden=lambda x, y: (x > mountains.BOUNDS[0]) & (x < mountains.BOUNDS[2]) & (y > mountains.BOUNDS[1]) & (y < L.SOUTH_JOIN),
                         weight=lambda x, y: earthworks.seam_weight(x, y, L.BOUNDS))
    # Apron and country are refined at different steps: their outer seam shares every vertex where the line crosses.
    earthworks.stitch([collar, parts[1][1]], L.ORIGIN, joins, whole_seam=True)
    for name, mesh, _ in parts:
        path = OUT / 'glb' / (name + '.glb')
        info = mesh.save(path, 'BM_000_Ground')
        appearance.paint_join(path, mesh)
        entries.append({'name': name, 'path': path.relative_to(OUT).as_posix(), 'sha256': source.sha(path),
                        'bounds_m': [info['min'], info['max']], 'triangles': info['triangles'], 'slots': ['Ground']})
    return entries, seam


def osteria_landing():
    return runtime_layout.osteria_landing(source.manifest())


# Local building-space TV placements (mesh_name, local_pivot_cm, local_yaw_deg, local_watch_cm, local_watch_yaw_deg, scale).
TV_BUILDING_SPOTS = runtime_layout.TV_BUILDING_SPOTS


def tv_spots(data=None):
    return runtime_layout.tv_spots(data or source.manifest())


def map_zones(town_z):
    return runtime_layout.map_zones(town_z,source.manifest())


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'glb').mkdir(exist_ok=True)
    (OUT / 'textures').mkdir(exist_ok=True)
    data = source.manifest()
    ground_pieces.placements(data)
    materials = finish_surfaces(data)
    by_asset, meshes, surfaces = {}, [], []
    for entry in data['meshes']:
        path = source.LIBRARY / entry['path']
        assert source.sha(path) == entry['sha256'], path
        destination = OUT / 'glb' / path.name
        if entry['name'] in terrain.VALLEY_CARVED_TILES:
            tris, bounds_m, _ = terrain.write_carved_valley_tile(path, destination)
            entry = dict(entry, path=destination.relative_to(OUT).as_posix(), sha256=source.sha(destination),
                         triangles=tris, bounds_m=bounds_m)
        else:
            shutil.copy2(path, destination)
            entry = dict(entry, path=destination.relative_to(OUT).as_posix())
        if ground_pieces.is_ground(entry['name']):
            surface, prepared = ground_pieces.prepare(entry, destination, OUT)
            surfaces.append(surface)
        else:
            prepared = model_pieces.prepare(entry, destination)
        meshes.extend(row[0] for row in prepared)
        by_asset[entry['source_asset']] = prepared
        if 'collision' in entry:
            collision = source.LIBRARY / entry['collision']['path']
            assert source.sha(collision) == entry['collision']['sha256'], collision
            shutil.copy2(collision, OUT / 'glb' / collision.name)
    extra, seam = surroundings()
    pieces = []
    for entry in extra:
        surface, prepared = ground_pieces.prepare(entry, OUT / entry['path'], OUT)
        surfaces.append(surface)
        pieces.extend(row[0] for row in prepared)
    extra = pieces
    meshes.extend(extra)
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
        water = any(word in name for word in ('Water', 'Foam'))
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
    plants, plant_report = planting.replacements(data, source.terrain().height)
    woods = planting.woodland(source.Surface(source.triangles(OUT / 'ground/glb/SM_BM_NorthApron.glb')))
    for name, transforms in woods.items():
        plants.setdefault(name, []).extend(transforms)
    plant_report['connecting_woodland'] = sum(len(v) for v in woods.values())
    plant_report['tree_detail'] = 'Original detailed leaf geometry; no backdrop or _lo assets'
    plant_report['railway_corridor_removed'] = clear_railway(plants)
    for name, transforms in plants.items():
        tree = name.startswith(('Tree_', 'HD_'))
        grass = name.startswith('Grass_')
        groups.append({'asset': f'/Game/Japan/Assets/{name}.{name}', 'materials': [], 'plant': True,
                       'collision': tree, 'shadow': not grass, 'cull_cm': 8000 if grass else 36000 if not tree else 400000,
                       'transforms': transforms})
    signs = [dict(sign, text=SIGN_TRANSLATIONS.get(sign['text'], sign['text'])) for sign in data['signs']]
    town_z = float(source.terrain().height(0., -18.)) + L.ORIGIN[2] + 1.
    runtime = {'version': 1, 'origin_cm': L.native_origin(), 'bounds_m': L.BOUNDS,
               'clearance_m': list(terrain.OUTER), 'groups': groups, 'signs': signs, 'railway_corridor': L.RAILWAY,
               'zones': map_zones(town_z), 'tv_spots': tv_spots(data)}
    # Current meshes/hulls are complete now. Retire only this producer's generated
    # model members, so a normal removal/rename cannot strand an invalid inventory.
    expected = [Path(name).relative_to('glb').as_posix()
                for _, name in source_records(meshes, collision_directory='glb')]
    ground_pieces.publish(OUT, surfaces, L.native_origin())
    retired = retain_files(OUT / 'glb', expected)
    if retired:
        print(f'BELMONTE retired {len(retired)} superseded generated model files', flush=True)
    (OUT / 'runtime.json').write_text(json.dumps(runtime, separators=(',', ':')) + '\n')
    (OUT / 'build-report.json').write_text(json.dumps({'meshes': meshes, 'materials': materials,
                                                     'planting': plant_report, 'seam': seam}, indent=1) + '\n')
    print(f'BELMONTE BUILD COMPLETE: {len(meshes)} meshes, {len(groups)} groups, {sum(len(v) for v in plants.values())} plants', flush=True)


if __name__ == '__main__':
    main()
