"""Complete logical city ownership over independently exported bounded meshes."""
import json
from pathlib import Path
import tempfile
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent/'world'))

from atelier.atomic_files import atomic_json
from atelier.file_copy import copy_file
from atelier.conventions import to_unreal
from atelier.export_manifest import real_directory, sha
from atelier.model_files import regular_files
from atelier import export_manifest
import city_tile_products as legacy
from regions.hidamari.logical_catalogue import ASSETS

SOURCES = ASSETS
DESTINATION = legacy.DESTINATION
native_bounds = legacy.native_bounds
collision_matches = legacy.collision_matches
protected_files = legacy.protected_files


def piece_material_paths(source, slots):
    """Preserve the former whole parent's material policy on every bounded child."""
    if source not in SOURCES or not isinstance(slots, list) or not slots or len(set(slots)) != len(slots):
        raise ValueError('Invalid logical city material owner')
    if all(isinstance(slot, str) and slot.startswith('HDS_') for slot in slots):
        return legacy.material_paths(slots)
    if len(slots) != 1 or not isinstance(slots[0], str) or not slots[0]:
        raise ValueError('Palette city sources require their original single material slot')
    if source == 'HD_NorthGate': material = 'M_NorthGate'
    elif source.startswith('HD_NorthRock'): material = 'MI_NorthRockCaps'
    elif source.startswith('HD_North'): material = 'M_NorthMountains'
    elif source == 'HD_Sea': material = 'M_HarborWater'
    elif source in ('HD_Harbor', 'HD_Boat'): material = 'M_Harbor'
    elif source == 'HD_PlazaWater': material = 'M_PlazaWater'
    elif source == 'HD_InlandWater': material = 'M_PondWater'
    elif source == 'HD_PlazaFloor': material = 'M_PlazaPaving'
    elif source == 'HD_ArcadeFloor': material = 'M_ArcadePaving'
    elif source.startswith(('HD_Arcade', 'HD_Plaza', 'HD_Shop_')) or source in (
            'HD_ClockHall', 'HD_Square', 'HD_Station', 'HD_Shrine', 'HD_Park', 'HD_Streets', 'HD_CivicGardens'):
        material = 'M_Arcade'
    else: material = 'M_Village'
    return {slots[0]: '/Game/Japan/Materials/' + material}


def production_groups(manifest):
    return legacy.production_groups(manifest, parents=SOURCES, version=3,
                                    material_bindings=piece_material_paths, whole_small=True)


def owned_tiles(asset_paths, destination):
    return legacy.owned_tiles(asset_paths, destination, parents=SOURCES, whole_small=True)


def obsolete_assets(previous, current, destination):
    return legacy.obsolete_assets(previous, current, destination, parents=SOURCES, whole_small=True)


def parents_retired(content):
    root = Path(content)/'Japan/Assets'
    if any(path.is_symlink() for path in (root.absolute(),*root.absolute().parents)): return False
    return all(not path.exists() and not path.is_symlink() for key in SOURCES for path in root.glob(key+'.*'))


def source_record(root, receipts):
    """@cc [owner:fontanierh,label:correctness] atomic-city-receiving-metadata
    The complete original slot table, authored frame, bounds and whole collision
    geometry MUST follow the logical owner, independently of spatial subdivision.
    Every current export MUST match its own planned geometry digest and bounded
    count; assembly MUST NOT construct, join or re-export mesh geometry.
    """
    import numpy as np
    from atelier import mesh_ir
    from region_mesh_parts import validate
    value = validate(root)
    if value['parent'] not in SOURCES or value.get('kind') is not None:
        raise ValueError('Unowned logical city source')
    first, _ = mesh_ir.decode((Path(root) / value['pieces'][0]['payload']).read_bytes())
    vertices = []
    for hull in first['collisions']:
        matrix = np.asarray(hull['matrix'], dtype=np.float64)
        points = np.asarray(hull['vertices'], dtype=np.float64)
        world = points @ matrix[:3, :3].T + matrix[:3, 3]
        vertices.append([[float(value) for value in to_unreal(point)] for point in world])
    rows = []
    for piece in value['pieces']:
        receipt = receipts[piece['name']]
        if (receipt['triangles'] != piece['triangles'] or receipt['metadata']['geometry_sha256'] != piece['sha256']
                or receipt['primary'] != piece['name'] + '.fbx'
                or receipt['bounds'] != [piece['min'], piece['max']]
                or receipt['metadata']['slots'] != value['slots']
                or receipt['metadata']['polygons'] != piece['polygons']
                or receipt['metadata']['collision_hulls'] != piece['collision_hulls']):
            raise ValueError('City export differs from its current geometry input')
        rows.append({key: piece[key] for key in ('name', 'triangles', 'collision_hulls', 'min', 'max')} |
                    dict(sha256=receipt['sha256'], uv_channels=receipt['metadata']['uv_channels']))
    bounds = dict(min=[min(row['min'][axis] for row in rows) for axis in range(3)],
                  max=[max(row['max'][axis] for row in rows) for axis in range(3)])
    result = dict(source_triangles=value['source_triangles'], source_collision_hulls=value['source_collision_hulls'],
                  source_collision_vertices=vertices, source_material_slots=value['slots'],
                  source_bounds=bounds, tiles=rows)
    piece_material_paths(value['parent'], value['slots'])
    return result


def _members(manifest):
    """Only a complete prior owner report grants retirement authority."""
    if manifest.get('version') == 2:
        legacy.production_groups(manifest)
    else:
        production_groups(manifest)
    return {source + '/' + row['name'] + '.fbx'
            for source, record in manifest['sources'].items() for row in record['tiles']}


def assemble(out, log=print):
    """@cc [owner:fontanierh,label:correctness;performance] atomic-city-file-assembly
    Require all logical planners and independently certified exports before writing.
    Copy exact primary bytes only. An old complete inventory grants exact retirement
    authority; linked, foreign or incomplete trees MUST refuse before mutation.
    Publish complete current membership before retiring superseded owned files.
    """
    out = Path(out)
    destination = real_directory(out / 'city_surface_tiles/v1_128m')
    source_root = real_directory(out / 'atomic_regions/hidamari/assets')
    assembly = json.loads((source_root / 'manifest.json').read_text())
    if assembly.get('schema') != 1 or assembly.get('complete') is not True or not assembly.get('exports'):
        raise ValueError('Incomplete city atomic export assembly')
    receipts = {}
    for row in assembly['exports']:
        export_manifest.name(row['asset'])
        if row['asset'].casefold() in {name.casefold() for name in receipts}:
            raise ValueError('Duplicate city atomic export')
        if row['primary'] != row['asset'] + '.fbx' or sha(source_root / row['primary']) != row['sha256']:
            raise ValueError('Changed city atomic primary')
        receipts[row['asset']] = row
    if regular_files(source_root) != {'manifest.json', *(row['primary'] for row in receipts.values())}:
        raise ValueError('Foreign city atomic source members')
    sources = {key: source_record(out / 'planned_exports/hidamari' / key, receipts) for key in SOURCES}
    current = dict(version=3, complete=True, tag='v1_128m', triangle_limit=32768, sources=sources)
    production_groups(current)
    members = _members(current)
    if {Path(name).stem for name in members} != set(receipts):
        raise ValueError('Foreign or missing atomic city exports')
    actual = regular_files(destination) if destination.exists() else set()
    previous = set()
    if 'manifest.json' in actual:
        previous = _members(json.loads((destination / 'manifest.json').read_text()))
    elif actual:
        raise ValueError('Existing city assembly lacks complete ownership')
    # Earlier source assemblies published one validated submanifest per source.
    submanifests = set()
    for source in SOURCES:
        relative = source + '/manifest.json'
        if relative in actual:
            old = json.loads((destination / relative).read_text())
            if (old.get('version') != 2 or old.get('complete') is not True
                    or set(old.get('sources', {})) != {source}):
                raise ValueError('Invalid previous city source inventory')
            submanifests.add(relative)
    allowed = members | previous | submanifests | {'manifest.json', 'import-report.json'}
    directories = {str(path.relative_to(destination)) for path in destination.rglob('*') if path.is_dir()}
    if actual - allowed or directories - set(SOURCES):
        raise ValueError('Foreign city assembly members')
    for relative in members:
        target = destination / relative
        if target.is_symlink(): raise ValueError('Linked city primary')
    destination.mkdir(parents=True, exist_ok=True)
    for source, record in sources.items():
        folder = destination / source
        folder.mkdir(exist_ok=True)
        for row in record['tiles']:
            primary = row['name'] + '.fbx'
            target = folder / primary
            if target.is_file() and sha(target) == row['sha256']: continue
            with tempfile.NamedTemporaryFile(prefix='.atomic-city-', dir=folder, delete=False) as stream:
                staging = Path(stream.name)
            try:
                staging.unlink()
                copy_file(source_root / primary, staging)
                if sha(staging) != row['sha256']:
                    raise ValueError('City export changed during assembly')
                staging.replace(target)
            finally:
                staging.unlink(missing_ok=True)
    for name in members:
        if sha(destination / name) != receipts[Path(name).stem]['sha256']:
            raise ValueError('City primary changed before publication')
    atomic_json(destination / 'manifest.json', current)
    for name in (previous | submanifests) - members:
        (destination / name).unlink(missing_ok=True)
    log('CITY ATOMIC PIECES assembled ' + str(len(members)))
    return current


if __name__=='__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    assemble(parser.parse_args().out)
