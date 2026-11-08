"""Serialize one bounded service-body/door source packet after its complete source action."""
import argparse
import hashlib
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import yori  # noqa: E402,F401
from atelier.atomic_files import atomic_json
from atelier.export_manifest import real_directory, TRIANGLE_LIMIT
from atelier.model_files import regular_files, retain_files
from train.carriage_source import read
from train.carriage_mesh import geometry, glb


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True); parser.add_argument('--asset', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    value, binary = read(args.source, key=args.asset)
    info = geometry(value['document'], binary)
    data = glb(value['document'], binary)
    root = real_directory(args.output, create=True)
    expected = {'plan.json', args.asset + '.glbdata'}
    if regular_files(root) - expected: raise ValueError('Foreign carriage plan member')
    target = root / (args.asset + '.glbdata')
    if not target.exists() or target.read_bytes() != data: target.write_bytes(data)
    atomic_json(root / 'plan.json', dict(schema=1, parent=args.asset, complete=True, triangle_limit=TRIANGLE_LIMIT,
        source_triangles=info['triangles'], pieces=[dict(name=args.asset, payload=target.name,
            sha256=hashlib.sha256(data).hexdigest(), **info)]))
    retain_files(root, expected)
    print('CARRIAGE BOUNDED PLAN COMPLETE', args.asset, info['triangles'], flush=True)


if __name__ == '__main__': main()
