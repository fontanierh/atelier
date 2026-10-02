"""Where the BOTW asset library is, and what one of its entries is made of.

The library is a local extraction kept outside the repository (~/.cache/atelier/botw/library, see README.md): this
module only reads it. Standard library only.
"""
import json
import tomllib
from pathlib import Path

from atelier.paths import cache_dir

HERE = Path(__file__).resolve().parent
ROSTER = HERE / 'roster.toml'


def root():
    """The extracted library folder (it holds START_HERE.md, library/, viewer/)."""
    return cache_dir('botw') / 'library'


def available():
    return (root() / 'catalog' / 'archive-info.json').is_file()


def roster():
    return tomllib.loads(ROSTER.read_text())


def entry(entry_id):
    """An entry's asset.json with its single unit's files resolved to absolute paths."""
    found = sorted(root().glob(f'library/*/{entry_id}/asset.json'))
    if not found:
        raise FileNotFoundError(f'no library entry {entry_id!r} in {root()}')
    manifest = json.loads(found[0].read_text())
    units = manifest['units']
    if len(units) != 1:
        raise ValueError(f'{entry_id} has {len(units)} parts; only single-part rigs are imported')
    unit = units[0]
    folder = found[0].parent
    return {
        'id': manifest['id'], 'name': manifest['name'], 'kind': manifest['kind'], 'fps': manifest.get('fps', 30),
        'model': unit['model'], 'bones': unit['bone_count'], 'clip_count': unit['clip_count'],
        'glb': (folder / unit['asset']).resolve(), 'curves': (folder / unit['animation_asset']).resolve(),
        'weapon_bones': unit.get('weapon_bones', []),
    }


def sources():
    """Every library file the roster reads (the build hashes these, not the whole 5 GB library)."""
    if not available():
        return []
    files = []
    for character in roster()['character']:
        item = entry(character['id'])
        files += [item['glb'], item['curves']]
    return sorted(set(files))
