"""Separate original Stable constructor states before independently cached geometry."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import yori  # noqa: E402,F401
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import real_directory  # noqa: E402
from atelier.build_cache import copy_file  # noqa: E402
from atelier.model_files import regular_files, retain_files  # noqa: E402
from hidamari_stable.catalogue import SOURCES, context_key  # noqa: E402
from hidamari_stable import layout  # noqa: E402
from village.atomic_sources import restore  # noqa: E402
from hidamari_stable.query_inputs import generated  # noqa: E402


def publish(contexts, output, *, enabled):
    import random
    if not enabled: raise ValueError('Hidamari Stable is disabled; normal task must not fabricate receiving artifacts')
    if (contexts.get('schema') != 1 or contexts.get('complete') is not True
            or set(contexts.get('contexts', {})) != {context_key(key) for key in SOURCES}):
        raise ValueError('Incomplete original Stable constructor context')
    for state in contexts['contexts'].values(): restore(random.Random(), state)
    output = real_directory(output, create=True)
    expected = {key + '.json' for key in SOURCES}
    for path in output.iterdir():
        if path.name not in expected or path.is_symlink() or not path.is_file():
            raise ValueError('Foreign Stable source data member')
    for key in SOURCES:
        state = contexts['contexts'][context_key(key)]
        atomic_json(output / (key + '.json'), dict(schema=1, asset=key, random_state=state))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--query-output', type=Path, required=True)
    parser.add_argument('--data-root', type=Path, required=True)
    args = parser.parse_args(argv)
    path = yori.ASSETS / 'hidamari-stable/construction-contexts.json'
    real_directory(path.parent)
    if path.is_symlink() or not path.is_file(): raise ValueError('Missing original Stable constructor states')
    if not layout.is_enabled(): raise ValueError('Hidamari Stable is disabled')
    source_root = real_directory(args.data_root)
    inputs = {name: source_root / name for name in generated()}
    for source in inputs.values():
        real_directory(source.parent)
        if source.is_symlink() or not source.is_file(): raise ValueError('Missing complete Stable canonical query input')
    query = real_directory(args.query_output, create=True)
    allowed = {'world.json', 'heightmap.npy', 'farhills.npy', 'megapark/trail.json',
               'treehouse/trees/trees.json', 'craterpark/v2/geometry.npz'}
    if regular_files(query) - allowed: raise ValueError('Foreign Stable query input')
    for name, source in inputs.items():
        target = query / name; real_directory(target.parent, create=True); copy_file(source, target)
    retain_files(query, set(inputs))
    publish(json.loads(path.read_text()), args.output, enabled=True)


if __name__ == '__main__': main()
