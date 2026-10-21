"""Exact ownership of generated city visibility pieces inside one native tag."""
import re
import math
from atelier.conventions import to_unreal

SOURCES = ('HD_Terrain', 'HD_Streets', 'HD_Square')
CELL = r'(?:0|-?[1-9][0-9]*)'


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
