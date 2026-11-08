"""Project canonical validated course geometry into independent logical source packets.

This is a geometry-data projection, before any render export. Render tiles already
have exact role/material ownership; collision retains the same ordered faces.
"""
import argparse
import io
import json
from pathlib import Path
import sys
import tempfile
sys.path[:0] = [str(Path(__file__).resolve().parents[3]), str(Path(__file__).resolve().parents[2])]
import numpy as np  # noqa: E402
from craterpark.v2 import dsl, export  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import name as mesh_name, real_directory, sha  # noqa: E402
from atelier.model_files import regular_files, retain_files  # noqa: E402


def packet(path, arrays):
    stream = io.BytesIO(); np.savez(stream, **arrays)
    payload = stream.getvalue()
    if path.is_symlink():
        raise ValueError('Linked canonical park packet')
    if not path.is_file() or path.read_bytes() != payload:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.packet-', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
        try:
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def project(source, output):
    real_directory(Path(source).parent)
    if Path(source).is_symlink() or not Path(source).is_file():
        raise ValueError('Canonical course geometry must be a regular unlinked source')
    output = real_directory(output)
    current = regular_files(output) if output.exists() else set()
    previous = output / 'inputs.json'
    owned = set()
    if current:
        if not previous.is_file() or previous.is_symlink():
            raise ValueError('Unrecorded canonical park inputs')
        old = json.loads(previous.read_text())
        if old.get('schema') != 1 or old.get('complete') is not True:
            raise ValueError('Invalid previous canonical park inputs')
        owned = {row['packet'] for row in old['assets']} | {'metadata.npz', 'inputs.json'}
        if current - owned or any(Path(p).name != p for p in owned):
            raise ValueError('Foreign canonical park inputs')
    with np.load(source, allow_pickle=False) as geometry:
        index = json.loads(str(geometry['index']))
        export.validate_geometry(index)
        expected = []
        for spec in index['render']:
            key = mesh_name(spec['name'])
            if not key.startswith('SM_CP_'):
                raise ValueError('Foreign canonical render owner')
            expected.append(key)
        for i, spec in enumerate(index['collision']):
            key = mesh_name(spec['name'])
            if not key.startswith('UC_CP_'):
                raise ValueError('Foreign canonical collision owner')
            count = len(geometry[f'c{i}'])
            expected.extend([key] if count <= 32768 else
                            [key + f'_Piece{start // 32768:03d}' for start in range(0,count,32768)])
        expected.append('SM_CP_ImportSeed')
        if len({key.casefold() for key in expected}) != len(expected):
            raise ValueError('Duplicate canonical course destination ownership')
        assets = []
        output.mkdir(parents=True, exist_ok=True)
        for i, spec in enumerate(index['render']):
            mesh = dsl.Mesh.from_arrays(geometry, f'r{i}_')
            if not 0 < len(mesh.F) <= 32768:
                raise ValueError('Canonical render logical owner exceeds atomic budget')
            arrays = mesh.to_arrays('m_')
            arrays['spec'] = np.asarray(json.dumps(dict(spec, kind='render')))
            name = spec['name']; path = output / (name + '.npz')
            packet(path, arrays)
            assets.append(dict(name=name, packet=path.name, sha256=sha(path), kind='render'))
        for i, spec in enumerate(index['collision']):
            triangles = np.asarray(geometry[f'c{i}'], 'f8')
            for start in range(0, len(triangles), 32768):
                name = spec['name'] if len(triangles) <= 32768 else spec['name'] + f'_Piece{start // 32768:03d}'
                path = output / (name + '.npz')
                packet(path, dict(triangles=triangles[start:start + 32768],
                    native_origin=export.origin_of(triangles.reshape(-1,3)),
                    spec=np.asarray(json.dumps(dict(spec, name=name, kind='collision', logical_parent=spec['name'])))))
                assets.append(dict(name=name, packet=path.name, sha256=sha(path), kind='collision'))
        seed = 'SM_CP_ImportSeed'
        packet(output / (seed + '.npz'), dict(spec=np.asarray(json.dumps(dict(name=seed, kind='seed')))))
        assets.append(dict(name=seed, packet=seed + '.npz', sha256=sha(output / (seed + '.npz')), kind='seed'))
        metadata = dict(index=geometry['index'])
        metadata.update({f'rail{i}': geometry[f'rail{i}'] for i in range(len(index['rails']))})
        packet(output / 'metadata.npz', metadata)
    names = [row['name'].casefold() for row in assets]
    if len(names) != len(set(names)):
        raise ValueError('Duplicate canonical park logical ownership')
    value = dict(schema=1, complete=True, assets=assets)
    atomic_json(previous, value)
    retain_files(output, ['inputs.json', 'metadata.npz', *(r['packet'] for r in assets)])
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    value = project(args.source, args.output)
    print('CRATERPARK LOGICAL INPUTS COMPLETE', len(value['assets']), flush=True)


if __name__ == '__main__':
    main()
