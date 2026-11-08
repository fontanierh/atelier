"""Snapshot, invoke the pinned CPU mesher, and load its arrays as compiler Meshes."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import numpy as np

from .. import dsl

HERE = Path(__file__).resolve().parent


def sha(data):
    return hashlib.sha256(data).hexdigest()


def snapshot(source, destination, *, terrain_dir=None):
    """@cc [owner:fontanierh,label:correctness] immutable-editor-input
    Copy the live document once; compilation MUST read that copy. Never modify
    the source. Terrain and geometry inputs MUST be identified by byte hashes.
    """
    source, destination = Path(source), Path(destination)
    terrain_dir = Path(terrain_dir) if terrain_dir else source.parent / 'data'
    destination.mkdir(parents=True, exist_ok=False)
    data = source.read_bytes()
    doc = json.loads(data)
    if doc.get('schema') != 'craterpark-editor/1':
        raise ValueError('unsupported editor schema')
    (destination / 'park.json').write_bytes(data)
    terrain_bytes = (terrain_dir / 'terrain.json').read_bytes()
    meta = json.loads(terrain_bytes)
    names = [meta['inner']['layers']['natural'], meta['inner']['layers']['dug'], meta['outer']['file']]
    (destination / 'data').mkdir()
    (destination / 'data' / 'terrain.json').write_bytes(terrain_bytes)
    for name in names:
        if not isinstance(name, str) or Path(name).name != name:
            raise ValueError('terrain filenames must be basenames')
        (destination / 'data' / name).write_bytes((terrain_dir / name).read_bytes())
    pin = json.loads((HERE / 'pin.json').read_text())
    # When supplied alongside the live document, a newer editor is a loud version
    # mismatch even if it only changed the meaning of an existing parameter.
    editor_source = source.parent / 'pieces.js'
    if editor_source.exists():
        js = editor_source.read_bytes()
        if sha(js) != pin['pieces_sha256']:
            raise ValueError('live pieces.js differs from pinned compiler; update the vendor and parity tests')
        (destination / 'pieces.js').write_bytes(js)
    manifest = {'schema': 'craterpark-editor-snapshot/1', 'rev': doc.get('rev'),
                'pieces_sha256': pin['pieces_sha256'], 'files': {}}
    for file in sorted(destination.rglob('*')):
        if file.is_file():
            manifest['files'][str(file.relative_to(destination))] = sha(file.read_bytes())
    (destination / 'snapshot.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return destination


@dataclass
class Piece:
    metadata: dict
    mesh: dsl.Mesh
    colors: np.ndarray
    centerline: np.ndarray


@dataclass
class Scene:
    """Diagnostic compiler geometry, deliberately not an accepted production Park.

    Source triangles, seams, raw normals and colors are retained. Material roles,
    topology, routes, supports and physics still require production certification.
    """
    metadata: dict
    pieces: list[Piece]
    terrain: list[dsl.Mesh]


def read_array(directory, spec, columns):
    name = spec['file']
    if Path(name).name != name:
        raise ValueError('invalid compiler array filename')
    data = (Path(directory) / name).read_bytes()
    if sha(data) != spec['sha256']:
        raise ValueError(f'compiler array hash mismatch: {name}')
    dtype = {'f64': '<f8', 'f32': '<f4', 'u32': '<u4'}[spec['type']]
    a = np.frombuffer(data, dtype=dtype)
    if len(a) != spec['count'] or len(a) % columns or not np.isfinite(a).all():
        raise ValueError(f'invalid compiler array: {name}')
    return a.reshape(-1, columns)


def load(directory):
    """Preserve indexed geometry exactly; no welding, winding repair or remeshing."""
    directory = Path(directory)
    index = json.loads((directory / 'index.json').read_text())
    pin = json.loads((HERE / 'pin.json').read_text())
    if index['schema'] != 'craterpark-editor-mesh/1' or index['pieces_sha256'] != pin['pieces_sha256']:
        raise ValueError('editor mesh provenance mismatch')
    pieces = []
    for entry in index['pieces']:
        arrays = {key: read_array(directory, value, 3) for key, value in entry['arrays'].items()}
        mesh = dsl.Mesh.part(arrays['pos'], arrays['idx'], N=arrays['nor'], feature=entry['id'])
        pieces.append(Piece(entry, mesh, arrays['col'], arrays['center']))
    ground = []
    for entry in index['ground']:
        arrays = {key: read_array(directory, value, 3) for key, value in entry['arrays'].items()}
        ground.append(dsl.Mesh.part(arrays['pos'], arrays['idx'], role=dsl.GROUND,
                                   material=dsl.GROUND_MAT, feature=entry['id']))
    return Scene(index, pieces, ground)


def compile_snapshot(directory, output, *, timeout=120):
    """@cc [owner:fontanierh,label:correctness] no-editor-fallback
    Invoke only the pinned Node bridge on verified snapshot bytes. A failed bridge
    MUST raise, never return an older scene or fall back to another layout.
    """
    directory, output = Path(directory), Path(output)
    manifest = json.loads((directory / 'snapshot.json').read_text())
    pin = json.loads((HERE / 'pin.json').read_text())
    if manifest['pieces_sha256'] != pin['pieces_sha256']:
        raise ValueError('snapshot geometry version mismatch')
    for name, digest in manifest['files'].items():
        file = (directory / name).resolve()
        if not file.is_relative_to(directory.resolve()) or sha(file.read_bytes()) != digest:
            raise ValueError(f'snapshot input changed: {name}')
    node = shutil.which('node')
    if not node:
        raise RuntimeError('the editor compiler requires Node.js')
    output.mkdir(parents=True, exist_ok=False)
    command = [node, '--max-old-space-size=1024', str(HERE / 'bridge.cjs'),
               str(directory / 'park.json'), str(directory / 'data'), str(output)]
    with (output / 'node.log').open('w') as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=timeout, check=False)
    if result.returncode:
        raise ValueError(f'editor compiler failed: {(output / "node.log").read_text()[-3000:]}')
    scene = load(output)
    if scene.metadata['park_sha256'] != manifest['files']['park.json']:
        raise ValueError('bridge read a different document')
    scene.metadata['snapshot'] = manifest
    return scene
