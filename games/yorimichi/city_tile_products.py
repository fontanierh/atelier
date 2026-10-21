"""Exact ownership of generated city visibility pieces inside one native tag."""
import re
import math
import copy
import hashlib
import json
from pathlib import Path
from atelier.conventions import to_unreal

SOURCES = ('HD_Terrain', 'HD_Streets', 'HD_Square')
CELL = r'(?:0|-?[1-9][0-9]*)'
STREETS = 'HD_Streets'
STREETS_DESTINATION = '/Game/Japan/Assets'


def streets_owned_package(package):
    if not isinstance(package, str) or not package.startswith(STREETS_DESTINATION+'/'):
        return False
    name = package[len(STREETS_DESTINATION)+1:]
    return name == STREETS or tile_name(STREETS, name)


def require_sources(sources):
    if not isinstance(sources, dict) or set(sources) != set(SOURCES):
        raise ValueError('City tile import requires all three production surfaces')


def native_bounds(tile):
    """Blender world metres -> Unreal centimetres, including handedness."""
    low, high = tile['min'], tile['max']
    if (len(low) != 3 or len(high) != 3 or any(type(v) not in (float, int) or not math.isfinite(v) for v in (*low, *high))
            or any(a > b for a, b in zip(low, high))):
        raise ValueError('Invalid city piece bounds')
    a, b = to_unreal(low), to_unreal(high)
    return ((a[0], b[1], a[2]), (b[0], a[1], b[2]))


def tile_name(source, name):
    return isinstance(name, str) and re.fullmatch(re.escape(source) + '_cell_' + CELL + '_' + CELL + r'(?:_Piece[0-3]{1,16})?', name) is not None


def streets_source(manifest):
    """@cc [owner:fontanierh,label:correctness] bounded-streets-complete-membership
    Production Streets MUST use the complete bounded face partition with its original
    slots, bounds and complex collision policy. Missing membership, duplicate names,
    changed coverage or unsupported authored collision MUST refuse. A hidden original
    MUST NOT substitute for any piece's rendering, collision or vegetation preparation.
    """
    if manifest.get('complete') is not True or manifest.get('tag') != 'v1_128m':
        raise ValueError('Missing completed city surface partition')
    require_sources(manifest.get('sources'))
    source = manifest['sources'][STREETS]
    slots = source.get('source_slots')
    if (manifest.get('triangle_limit') != 32768 or not isinstance(slots, list) or not slots
            or any(not isinstance(slot, str) or not re.fullmatch('HDS_[A-Za-z0-9_]+', slot) for slot in slots)
            or len(slots) != len(set(slots)) or type(source.get('source_collision_boxes')) is not int
            or source['source_collision_boxes'] != 0):
        raise ValueError('Unsupported Streets material/collision membership')
    native_bounds(dict(min=source['source_min'], max=source['source_max']))
    tiles = source.get('tiles')
    if not isinstance(tiles, list) or not tiles:
        raise ValueError('Missing Streets pieces')
    names = set()
    for tile in tiles:
        name = tile.get('name')
        if (not tile_name(STREETS, name) or name in names or type(tile.get('triangles')) is not int
                or not 0 < tile['triangles'] <= 32768 or not isinstance(tile.get('sha256'), str)
                or not re.fullmatch('[0-9a-f]{64}', tile['sha256'])):
            raise ValueError('Invalid or duplicate Streets piece')
        names.add(name)
        native_bounds(tile)
    if sum(tile['triangles'] for tile in tiles) != source.get('source_triangles'):
        raise ValueError('Incomplete Streets triangle coverage')
    for axis in range(3):
        if (abs(min(tile['min'][axis] for tile in tiles)-source['source_min'][axis]) > .001
                or abs(max(tile['max'][axis] for tile in tiles)-source['source_max'][axis]) > .001):
            raise ValueError('Incomplete Streets bounds coverage')
    return source


def streets_instances(city, manifest):
    """Publish the actual current piece roster at every original placement, without altering source queries."""
    source = streets_source(manifest)
    result = copy.deepcopy(city)
    instances = result['instances']
    placements = instances.pop(STREETS, None)
    if (not isinstance(placements, list) or not placements
            or any(not isinstance(p, list) or len(p) != 5
                   or any(type(v) not in (int, float) or not math.isfinite(v) for v in p) or p[4] <= 0
                   for p in placements)):
        raise ValueError('Missing or invalid original Streets placements')
    for tile in source['tiles']:
        if tile['name'] in instances:
            raise ValueError('Duplicate Streets runtime piece')
        instances[tile['name']] = copy.deepcopy(placements)
    return result


def streets_source_key(source):
    return hashlib.sha256(json.dumps(source, sort_keys=True, allow_nan=False).encode()).hexdigest()


def streets_present(out, content, *, inventory):
    """Ordinary current-step checks require every saved piece and supported sidecar."""
    try:
        out, content = Path(out), Path(content)
        source = streets_source(json.loads((out/'city_surface_tiles/v1_128m/manifest.json').read_text()))
        report = json.loads((out/'native-city-streets.json').read_text())
        packages = [STREETS_DESTINATION+'/'+tile['name'] for tile in source['tiles']]
        bindings = report.get('bindings')
        if (report.get('source') != streets_source_key(source)
                or not isinstance(bindings, dict) or set(bindings) != set(source['source_slots'])
                or any(not isinstance(value, str) or not value.startswith('/Game/') for value in bindings.values())
                or report.get('files') != inventory(content, packages)):
            return False
        return not (content/'Japan/Assets/HD_Streets.uasset').exists()
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False


def owned_tiles(asset_paths, destination):
    """Enumerate only generated tile names inside the owner's exact tag root."""
    report = {source: [] for source in SOURCES}
    for asset in asset_paths:
        if not isinstance(asset, str) or not asset.startswith(destination + '/'):
            continue
        name = asset[len(destination) + 1:].split('.')[0]
        for source, tiles in report.items():
            if tile_name(source, name):
                if asset != destination + '/' + name + '.' + name:
                    raise ValueError('Invalid generated city tile object path')
                tiles.append({'name': name, 'asset': asset})
                break
    return report


def obsolete_assets(previous, current, destination):
    """@cc [owner:fontanierh,label:correctness] retire-only-superseded-city-pieces
    Only previously inventoried owned tiles inside this exact destination MAY
    retire, after every current tile has imported and validated. Source packages,
    other tags and current pieces MUST never enter the deletion list. Invalid
    ownership evidence MUST refuse rather than widen the deletion scope.
    """
    if not isinstance(destination, str) or not re.fullmatch('/Game/Experiments/CitySurfaces/[A-Za-z0-9_]+', destination):
        raise ValueError('Invalid city tile destination')

    def inventory(report):
        if not isinstance(report, dict):
            raise ValueError('Invalid city tile ownership report')
        found = set()
        for source, tiles in report.items():
            if source not in SOURCES or not isinstance(tiles, list):
                raise ValueError('Invalid city tile source membership')
            for tile in tiles:
                if not isinstance(tile, dict):
                    raise ValueError('Invalid city tile record')
                name = tile.get('name')
                if not tile_name(source, name):
                    raise ValueError('Invalid city tile package name')
                asset = destination + '/' + name + '.' + name
                if tile.get('asset') != asset or asset in found:
                    raise ValueError('Invalid or duplicate city tile package ownership')
                found.add(asset)
        return found

    return sorted(inventory(previous) - inventory(current))
