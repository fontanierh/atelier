"""Runtime-only atomic export inventory validation; no build controller imports."""
import hashlib
import json
import math
from pathlib import Path
import re
import stat

from .atomic_files import atomic_json
from .model_files import member, regular_files

NAME = re.compile(r'[A-Za-z][A-Za-z0-9_-]*', re.ASCII)
PRIMARY = {'.fbx', '.glb'}
TRIANGLE_LIMIT = 32_768


def name(value):
    if not isinstance(value, str) or not NAME.fullmatch(value):
        raise ValueError('Export task names must be explicit ASCII identifiers')
    return value


def real_directory(path, *, create=False):
    """Refuse lexical ancestor links, including broken destination links, before writes."""
    path = Path(path).absolute()
    for ancestor in reversed((path, *path.parents)):
        try:
            mode = ancestor.lstat().st_mode
        except FileNotFoundError:
            continue
        if not stat.S_ISDIR(mode):
            raise ValueError('Export roots and ancestors must be real directories')
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def validate(root, *, key, limit=TRIANGLE_LIMIT):
    """@cc [owner:fontanierh,label:correctness] atomic-export-membership
    Each atomic export MUST contain exactly one nonempty primary mesh and one receipt.
    Receipt identity, bounded positive triangle count, finite world bounds and all payload
    bytes MUST match. Missing, linked, foreign or extra members MUST refuse. A receipt
    MUST NOT substitute for current native material/collision/UV validation on receiving.
    """
    root = real_directory(root)
    key = name(key)
    receipt = root / 'export.json'
    members = regular_files(root)
    if 'export.json' not in members:
        raise ValueError('Atomic export receipt is missing')
    value = json.loads(receipt.read_text())
    primary = member(value.get('primary'))
    if (value.get('schema') != 1 or value.get('asset') != key
            or Path(primary).suffix not in PRIMARY or primary != key + Path(primary).suffix
            or members != {'export.json', primary}):
        raise ValueError('Atomic export contains foreign or incomplete membership')
    mesh = root / primary
    triangles = value.get('triangles')
    bounds = value.get('bounds')
    if type(triangles) is not int or not 0 < triangles <= limit:
        raise ValueError('Atomic export triangle budget is missing or exceeded')
    if (not isinstance(bounds, list) or len(bounds) != 2
            or any(not isinstance(row, list) or len(row) != 3 for row in bounds)
            or any(type(v) not in (int, float) or not math.isfinite(v) for row in bounds for v in row)
            or any(a > b for a, b in zip(*bounds))):
        raise ValueError('Atomic export has invalid bounds')
    if not mesh.stat().st_size or sha(mesh) != value.get('sha256'):
        raise ValueError('Atomic export payload differs from its receipt')
    return value


def publish_receipt(root, *, key, primary, triangles, bounds, metadata=None):
    """Finish only a completely written exclusive export; never manufacture build stamps."""
    root = real_directory(root)
    key, primary = name(key), member(primary)
    if regular_files(root) - {primary, 'export.json'} or not (root / primary).is_file():
        raise ValueError('Atomic export membership is incomplete or foreign')
    value = dict(schema=1, asset=key, primary=primary, triangles=triangles,
                 bounds=bounds, sha256=sha(root / primary), metadata=metadata or {})
    atomic_json(root / 'export.json', value)
    return validate(root, key=key)
