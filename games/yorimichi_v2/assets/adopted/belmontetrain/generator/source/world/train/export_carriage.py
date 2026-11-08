"""Publish one bounded carriage primary, preserving its complete original GLB bytes."""
import argparse
import hashlib
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import yori  # noqa: E402,F401
from atelier.export_manifest import real_directory, publish_receipt, name
from atelier.gltf import glb_parts
from atelier.model_files import regular_files
from train.carriage_mesh import geometry


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True); parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--format', choices=['.glb'], required=True)
    args = parser.parse_args(argv); source = args.input; real_directory(source.parent)
    if source.is_symlink() or not source.is_file() or source.suffix != '.glbdata': raise ValueError('Foreign carriage export source')
    key = name(source.stem); data = source.read_bytes(); info = geometry(*glb_parts(data))
    root = real_directory(args.output, create=True); primary = key + '.glb'
    if regular_files(root) - {primary, 'export.json'}: raise ValueError('Foreign carriage export product')
    with tempfile.NamedTemporaryFile(dir=root, prefix='.carriage-', delete=False) as stream:
        temporary = Path(stream.name); stream.write(data)
    try:
        if source.read_bytes() != data: raise ValueError('Carriage input changed during publication')
        temporary.replace(root / primary)
    finally: temporary.unlink(missing_ok=True)
    publish_receipt(root, key=key, primary=primary, triangles=info['triangles'], bounds=info['bounds'],
        metadata=dict(slots=info['slots'], geometry_sha256=hashlib.sha256(data).hexdigest(), role='render'))
    print('CARRIAGE ATOMIC EXPORT COMPLETE', key, info['triangles'], flush=True)


if __name__ == '__main__': main()
