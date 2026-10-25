"""Narrow fixed views of the forest's whole source Items for Scripts/import_forest.py's native owners.

- ``species``: world.forest's trees.json (forest.manifest) split into one <name>.json per committed species, each
  exactly its assembled entry, after the whole manifest checks against the committed roster;
- ``leaves``: world.forest_textures' library (forest.textures) as one T_<leaf>.png per committed Tuscan leaf, after
  its textures.json lists exactly those slots and their files.
"""
import json
import math
from pathlib import Path
import re

NAME = re.compile('[A-Za-z][A-Za-z0-9_]*\\Z')
FIELDS = {'height', 'spread', 'leaf', 'triangles', 'screen_sizes', 'impostor', 'impostor_slot', 'impostor_bark', 'crown',
          'trunk_hulls'}


def _json(path):
    def pairs(rows):
        value = {}
        for key, item in rows:
            if key in value:
                raise ValueError('Duplicate forest source field')
            value[key] = item
        return value
    return json.loads(Path(path).read_bytes(), object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite forest source value')))


def _regular(path):
    path = Path(path)
    if path.is_symlink() or path.resolve() != path or not path.is_file():
        raise ValueError('Forest source is absent or aliased: ' + str(path))
    return path


def entry(name, value):
    """One assembled species entry, as import_forest and import_foliage_lods read it."""
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise ValueError(f'{name}: assembled forest entry fields differ')
    sizes, counts = value['screen_sizes'], value['triangles']
    if (not isinstance(sizes, list) or len(sizes) != 5 or not isinstance(counts, list) or len(counts) != 5
            or any(type(n) is not int or n <= 0 for n in counts)
            or any(type(s) not in (int, float) or not math.isfinite(s) for s in sizes)
            or type(value['height']) not in (int, float) or value['height'] <= 0
            or value['impostor_slot'] != name + '_Impostor' or not NAME.fullmatch(str(value['impostor_bark']))
            or not NAME.fullmatch(str(value['leaf']))
            or not isinstance(value['crown'], dict) or value['crown'].get('slot') != name + '_Crown'
            or not isinstance(value['trunk_hulls'], list) or len(value['trunk_hulls']) != 1):
        raise ValueError(f'{name}: assembled forest entry differs from the original LOD policy')
    impostor = value['impostor']
    atlases = impostor.get('atlases') if isinstance(impostor, dict) else None
    if (impostor.get('normal_space') != 'camera-right-up-outward'
            or atlases != {kind: f'{name}_{kind}.png' for kind in ('colour', 'normal')}):
        raise ValueError(f'{name}: impostor record differs from its baked atlases')
    return value


def species(manifest=None, output=None, names=None):
    """@cc [owner:fontanierh,label:correctness] forest-species-views
    The whole assembled trees.json MUST list exactly the committed species, each
    entry with the original LOD/impostor/crown/hull fields, before any output;
    each output is exactly one species' entry.
    """
    trees = _json(_regular(manifest))
    if not isinstance(trees, dict) or sorted(trees) != sorted(names):
        raise ValueError('Assembled forest species differ from the committed roster')
    rows = {name: entry(name, trees[name]) for name in names}
    if output.exists():
        raise ValueError('Forest species output must be fresh')
    output.mkdir(parents=True)
    for name, value in rows.items():
        (output / (name + '.json')).write_text(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n')


def leaves(library=None, output=None, slots=None):
    """@cc [owner:fontanierh,label:correctness] forest-leaf-views
    The whole forest texture library MUST list exactly the committed leaf slots,
    each with its own regular PNG, before any output; each output is one slot's bytes.
    """
    library = Path(library)
    textures = _json(_regular(library / 'textures.json'))
    if not isinstance(textures, dict) or sorted(textures) != sorted(slots):
        raise ValueError('Forest leaf textures differ from the committed leaves')
    files = {}
    for slot in slots:
        value = textures[slot]
        if not isinstance(value, dict) or value.get('file') != f'T_{slot}.png':
            raise ValueError(f'{slot}: forest leaf texture file differs')
        files[slot] = _regular(library / value['file']).read_bytes()
    if output.exists():
        raise ValueError('Forest leaf output must be fresh')
    output.mkdir(parents=True)
    for slot, data in files.items():
        (output / f'T_{slot}.png').write_bytes(data)
