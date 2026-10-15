"""Digests of the exported files an Unreal import reads, for the recipe's cutoff steps (build.py `digest_step`): the
import needs the digest step instead of the export, so an export that reruns and writes the same meshes leaves it
current.

Blender writes a different binary FBX for the same scene on every run: the header records the export time, and object
ids come from Python's per-process string hash. `fbx()` hashes the records without the time and with every id
replaced by its order of first appearance. A JSON file is hashed without its `...sha256` receipts: they hash raw
export bytes, and the files they describe are digested themselves.
"""
import hashlib
import json
import struct
from pathlib import Path

MAGIC = b'Kaydara FBX Binary  \x00'
SCALARS = {ord('Y'): 2, ord('C'): 1, ord('I'): 4, ord('F'): 4, ord('D'): 8, ord('L'): 8}
ARRAYS = set(b'fdlib')
TIME = b'CreationTimeStamp'                  # FBXHeaderExtension: the export time
ID_PARENTS = (b'Objects', b'Documents')      # their records' first property is the object's id
REPORTS = {'import-report.json'}             # written into export folders by the imports themselves


def records(data):
    """[(depth, parent, name, [(kind, bytes)])] of a binary FBX, the export time left out."""
    wide = struct.unpack_from('<I', data, 23)[0] >= 7500
    head = struct.Struct('<QQQB' if wide else '<IIIB')
    found = []

    def walk(at, end, depth, parent):
        while at < end:
            stop, count, _, length = head.unpack_from(data, at)
            if stop == 0:   # the null record that ends a list
                return
            name = data[at + head.size:at + head.size + length]
            at += head.size + length
            if name != TIME:
                props = []
                for _ in range(count):
                    kind = data[at]
                    at += 1
                    if kind in SCALARS:
                        size = SCALARS[kind]
                    elif kind in ARRAYS:     # length, encoding, stored bytes; then the (maybe deflated) values
                        size = 12 + struct.unpack_from('<I', data, at + 8)[0]
                    elif kind in b'SR':
                        size = 4 + struct.unpack_from('<I', data, at)[0]
                    else:
                        raise ValueError(f'unknown FBX property type {kind!r}')
                    props.append((kind, data[at:at + size]))
                    at += size
                found.append((depth, parent, name, props))
                walk(at, stop, depth + 1, name)
            at = stop
    walk(len(MAGIC) + 6, len(data), 0, b'')
    return found


def fbx(data):
    """sha256 of an FBX's content: binary records without the export time, ids numbered in order; other bytes as-is."""
    if not data.startswith(MAGIC):
        return hashlib.sha256(data).hexdigest()
    found = records(data)
    ids = {}
    for _, parent, _, props in found:
        if parent in ID_PARENTS and props and props[0][0] == ord('L'):
            ids.setdefault(props[0][1], len(ids))
    digest = hashlib.sha256()
    for depth, _, name, props in found:
        digest.update(struct.pack('<IB', depth, len(name)) + name + struct.pack('<I', len(props)))
        for kind, value in props:
            if kind == ord('L') and value in ids:
                value = b'id%d' % ids[value]
            digest.update(bytes([kind]) + struct.pack('<I', len(value)) + value)
    return digest.hexdigest()


def unreceipted(value):
    """A JSON value without its `...sha256` keys."""
    if isinstance(value, dict):
        return {k: unreceipted(v) for k, v in value.items() if not k.endswith('sha256')}
    if isinstance(value, list):
        return [unreceipted(v) for v in value]
    return value


def file(path):
    path = Path(path)
    if path.suffix.lower() == '.fbx':
        return fbx(path.read_bytes())
    if path.suffix == '.json':
        return hashlib.sha256(json.dumps(unreceipted(json.loads(path.read_text())), sort_keys=True).encode()).hexdigest()
    return hashlib.sha256(path.read_bytes()).hexdigest()


def files(root, names):
    """{name: digest} of files or folders under root (a folder: every file in it, but the imports' own reports)."""
    root, made = Path(root), {}
    for name in names:
        path = root / name
        if path.is_dir():
            for child in sorted(path.rglob('*')):
                if child.is_file() and child.name not in REPORTS:
                    made[child.relative_to(root).as_posix()] = file(child)
        elif path.is_file():
            made[name] = file(path)
        else:
            raise FileNotFoundError(f'{path}: the export did not write it')
    return made


def hidamari(out, north):
    """The Hidamari meshes the world import (north=False) or the volcano's (north=True, HD_North*) reads: their manifest
    entries and FBX digests. The world's forest ground also reads the snow mask's southern join (forest_ground.py)."""
    folder = Path(out) / 'hidamari'
    manifest = json.loads((folder / 'manifest.json').read_text())
    names = sorted(n for n in manifest if n.startswith('HD_North') == north)
    made = {'manifest': {n: manifest[n] for n in names}, 'files': files(folder / 'assets', [f'{n}.fbx' for n in names])}
    if not north:
        made['south_join_m'] = json.loads((folder / 'north_snow.json').read_text())['south_join_m']
    return made


def hidamari_props_exports(out):
    """@cc [owner:fontanierh,label:correctness] hidamari-props-consumed-exports
    The import identity MUST include the complete props manifest and every named FBX and PNG.
    Missing required exports MUST fail; review images MUST NOT affect the identity.
    """
    folder = Path(out) / 'hidamari' / 'props'
    manifest = json.loads((folder / 'props.json').read_text())
    if not isinstance(manifest, dict):
        raise ValueError('Hidamari props manifest must be an object')
    exports = {f'{name}{suffix}': folder / f'{name}{suffix}'
               for name in sorted(manifest) for suffix in ('.fbx', '.png')}
    for path in exports.values():
        if not path.is_file():
            raise FileNotFoundError(f'{path}: the prop export did not write it')
    return manifest, exports


def hidamari_props_present(out):
    """Check completeness without hashing meshes when the cutoff is otherwise current."""
    try:
        hidamari_props_exports(out)
        return True
    except (OSError, ValueError):
        return False


def hidamari_props(out):
    """Complete manifest and normalized export identities; never include the review images."""
    manifest, exports = hidamari_props_exports(out)
    return {'manifest': manifest, 'files': {name: file(path) for name, path in exports.items()}}


def record(output, made, log=None):
    """Write a digest (sorted JSON: a cutoff step's output); unchanged content leaves the file as it was."""
    output = Path(output)
    text = json.dumps(made, indent=1, sort_keys=True) + '\n'
    output.parent.mkdir(parents=True, exist_ok=True)
    if not output.exists() or output.read_text() != text:
        output.write_text(text)
    if log is not None:
        log.write(f'{output.name}: {hashlib.sha256(text.encode()).hexdigest()}\n')
