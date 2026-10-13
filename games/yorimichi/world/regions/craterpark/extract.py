"""Convert a crater-skate-park checkout to the committed library arrays, materials and textures (docs/CRATERPARK.md).

    python world/regions/craterpark/extract.py /path/to/crater-skate-park

Every mesh of readable/mountain/ is kept, helpers included: positions, UVs and triangles as float32/uint32 arrays, and
the faces drawn with `renderSkipTriangles` left out of view. Each array set is checked against the source's own
arraysSha256. Normal builds read only the committed library files.
"""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess

import numpy as np

SOURCE_REPOSITORY = 'https://github.com/fontanierh/crater-skate-park'
LIBRARY = Path(__file__).resolve().parents[3] / 'assets'
OUT = LIBRARY / 'craterpark'
KEPT = ('id', 'name', 'section', 'role', 'helper', 'material', 'doubleSided', 'vertexCount', 'triangleCount', 'bounds',
        'arraysSha256')


def sha(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def convert(item, root):
    mesh = json.loads((root / item['file']).read_text())
    positions = np.asarray(mesh['positions'], '<f4').reshape(-1, 3)
    uvs = np.asarray(mesh['uvs'], '<f4').reshape(-1, 2)
    triangles = np.asarray(mesh['triangles'], '<u4').reshape(-1, 3)
    digest = hashlib.sha256(positions.tobytes() + uvs.tobytes() + triangles.tobytes()).hexdigest()
    if digest != item['arraysSha256'] or len(positions) != len(uvs):
        raise ValueError('Arrays differ from the source checksum: ' + item['id'])
    if not np.array_equal(np.asarray(mesh['positions'], 'f8').reshape(-1, 3), positions):
        raise ValueError('Positions are not float32 values: ' + item['id'])
    path = OUT / 'geometry' / f"{item['id']}.npz"
    np.savez_compressed(path, positions=positions, uvs=uvs, triangles=triangles,
                        render_skip=np.asarray(item['renderSkipTriangles'], '<u4'))
    entry = {key: item[key] for key in KEPT}
    entry['npz'] = path.relative_to(OUT).as_posix()
    entry['render_skip'] = len(item['renderSkipTriangles'])
    entry['sha256'] = sha(path)
    return entry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('checkout', type=Path)
    args = parser.parse_args()
    repo = args.checkout.resolve()
    root = repo / 'readable/mountain'
    commit = subprocess.run(['git', '-C', str(repo), 'rev-parse', 'HEAD'], check=True, capture_output=True, text=True).stdout.strip()
    if subprocess.run(['git', '-C', str(repo), 'status', '--porcelain'], check=True, capture_output=True, text=True).stdout:
        raise SystemExit('The checkout has local changes; convert a clean commit.')
    scene = json.loads((root / 'scene.json').read_text())
    if scene['schema'] != 'crater-park-readable-scene/1':
        raise SystemExit('Unknown scene schema ' + scene['schema'])
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / 'geometry').mkdir(parents=True)
    (OUT / 'textures').mkdir()
    meshes = [convert(item, root) for item in scene['meshes']]
    materials = json.loads((root / 'materials.json').read_text())
    textures = {}
    for material in materials:
        if material['texture']:
            shutil.copyfile(root / material['texture'], OUT / material['texture'])
            textures[material['texture']] = sha(OUT / material['texture'])
    shutil.copyfile(root / 'materials.json', OUT / 'materials.json')
    shutil.copyfile(repo / 'identified-drop-in.json', OUT / 'drop-in.json')
    shutil.copyfile(repo / 'docs/mountain-preview.png', OUT / 'preview.png')
    out = {key: scene[key] for key in ('schema', 'layout', 'units', 'axes', 'uvConvention', 'source', 'counts', 'bounds',
                                       'horizontalFootprintMetres')}
    out.update(materials='materials.json', textures=textures, meshes=meshes)
    (OUT / 'scene.json').write_text(json.dumps(out, indent=1) + '\n')
    provenance = {
        'source': SOURCE_REPOSITORY, 'commit': commit, 'ownership': "The park's author, who contributed it to Yorimichi.",
        'scene_sha256': sha(root / 'scene.json'), 'materials_sha256': sha(root / 'materials.json'),
        'drop_in_sha256': sha(repo / 'identified-drop-in.json'),
        'conversion': 'readable/mountain JSON arrays -> float32/uint32 npz, bit-identical to each mesh\'s arraysSha256; '
                      'renderSkipTriangles as render_skip; textures, materials and the marked drop-in copied unchanged.',
        'left_out': 'readable/mountain/obj and meshes/*.json, which hold the same arrays; tools/, the Blender viewer.'}
    (OUT / 'provenance.json').write_text(json.dumps(provenance, indent=1) + '\n')
    contract = json.loads((LIBRARY / 'source-library.json').read_text())
    files = {name: entry for name, entry in contract['files'].items() if not name.startswith('craterpark/')}
    for path in sorted(OUT.rglob('*')):
        if path.is_file() and path.suffix in {'.npz', '.png'}:
            files[path.relative_to(LIBRARY).as_posix()] = {'bytes': path.stat().st_size, 'sha256': sha(path)}
    contract['files'] = dict(sorted(files.items()))
    (LIBRARY / 'source-library.json').write_text(json.dumps(contract, indent=2) + '\n')
    print(f'Converted {len(meshes)} meshes, {len(textures)} textures from {commit[:7]}', flush=True)


if __name__ == '__main__':
    main()
