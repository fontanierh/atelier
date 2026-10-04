"""Where the BOTW asset library is, and what one of its entries is made of.

The library is a local extraction kept outside the repository (~/.cache/atelier/botw/library, see README.md); Link and
his clothing come from the botw-extract repository's extended catalog (~/.cache/atelier/botw/botw-extract). This
module only reads them. Standard library only.
"""
import functools
import json
import tomllib
from pathlib import Path

from atelier.paths import cache_dir

HERE = Path(__file__).resolve().parent
ROSTER = HERE / 'roster.toml'


def root():
    """The extracted library folder (it holds START_HERE.md, library/, viewer/)."""
    return cache_dir('botw') / 'library'


def extract():
    """The botw-extract clone with its metadata and viewer packs restored (README.md)."""
    return cache_dir('botw') / 'botw-extract'


def mechanics():
    """The extract's recovered player mechanics: action timelines, action and player parameters (moves.py)."""
    return extract() / 'gameplay' / 'recovered' / 'mechanics.json'


def available():
    return (root() / 'catalog' / 'archive-info.json').is_file()


@functools.cache
def _extended(name):
    """An extended catalog file's entries by id (catalog.json: characters, clothing.json: Link's clothing)."""
    path = extract() / 'playground' / 'private' / name
    if not path.is_file():
        return {}
    return {item['id']: item for item in json.loads(path.read_text())['entries']}


def roster():
    return tomllib.loads(ROSTER.read_text())


def entry(entry_id):
    """An entry's asset.json (or extended catalog record) with its single unit's files resolved to absolute paths."""
    found = sorted(root().glob(f'library/*/{entry_id}/asset.json'))
    if found:
        manifest, folder = json.loads(found[0].read_text()), found[0].parent
    elif entry_id in _extended('catalog.json'):
        manifest, folder = _extended('catalog.json')[entry_id], extract() / 'viewer' / 'public'
    else:
        raise FileNotFoundError(f'no library entry {entry_id!r} in {root()} or {extract()}')
    units = manifest['units']
    if len(units) != 1:
        raise ValueError(f'{entry_id} has {len(units)} parts; only single-part rigs are imported')
    unit = units[0]
    return {
        'id': manifest['id'], 'name': manifest['name'], 'kind': manifest['kind'], 'fps': manifest.get('fps', 30),
        'model': unit['model'], 'bones': unit['bone_count'], 'clip_count': unit['clip_count'],
        'glb': (folder / unit['asset']).resolve(), 'curves': (folder / unit['animation_asset']).resolve(),
        'weapon_bones': unit.get('weapon_bones', []),
    }


def garment(garment_id):
    """A piece of Link's clothing: its slot, whether it is the default outfit's, and its GLB."""
    item = _extended('clothing.json').get(garment_id)
    if item is None:
        raise FileNotFoundError(f'no clothing {garment_id!r} in {extract()}')
    return {'id': garment_id, 'name': item['name'], 'slot': item['slot'], 'default': item['default'],
            'glb': (extract() / 'viewer' / 'public' / item['unit']['asset']).resolve()}


def sources():
    """Every library file the roster reads (the build hashes these, not the whole 5 GB library)."""
    if not available():
        return []
    files = []
    for character in roster()['character']:
        item = entry(character['id'])
        files += [item['glb'], item['curves']] + [garment(g)['glb'] for g in character.get('outfit', [])]
        if character.get('moves'):
            files.append(mechanics())
            for slot in tomllib.loads((HERE / character['moves']).read_text()).get('equipment', {}).values():
                files += [entry(slot['id'])['glb'], entry(slot['id'])['curves']]
    return sorted(set(files))
