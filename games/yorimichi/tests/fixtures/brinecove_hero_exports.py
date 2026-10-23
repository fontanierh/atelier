"""Actual committed coastal hero geometry, texture and slot parity across atomic exports."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import sys

import bpy

GAME = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(GAME / 'world'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'native'))
import yori  # noqa: E402,F401
from glb_corners import read as corners  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.build_inputs import local_imports  # noqa: E402
from atelier.export_manifest import real_directory, sha  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    root = real_directory(args.output)
    if os.path.lexists(root): raise ValueError('Hero canary requires fresh evidence')
    region = GAME / 'world/regions/brinecove'
    sources = {Path(__file__), Path(corners.__code__.co_filename)}
    for script in ('build.py', 'plan_hero.py'):
        sources.update(local_imports(region / script, (GAME / 'world', GAME / 'world/regions')))
    sources.update(local_imports(GAME / 'world/export_region_piece.py', (GAME / 'world', GAME / 'world/regions')))
    sources.update(p for p in (GAME / 'assets/brinecove/models').iterdir()
                   if p.suffix == '.glb' or p.name.endswith('.provenance.json'))
    def identities():
        result = {}
        for path in sorted(sources):
            real_directory(path.parent)
            if path.is_symlink() or not path.is_file(): raise ValueError('Hero proof requires regular inputs')
            result[str(path)] = sha(path)
        return result
    before = identities()
    from brinecove import build as previous
    from brinecove.plan_hero import main as planner, key
    from export_region_piece import main as exporter
    from region_mesh_parts import validate
    bpy.ops.wm.read_factory_settings(use_empty=True)
    previous.OUT = root / 'controls'
    (previous.OUT / 'glb').mkdir(parents=True)
    (previous.OUT / 'textures').mkdir()
    materials = {}
    models, groups = previous.hero_models(materials)
    results = {}
    for model, group in zip(models, groups):
        slug = model['name'].removeprefix('SM_BC_Hero_')
        candidates = ['pirate-queen-statue', 'galleon-hull', 'harbor-capstan']
        slug = next(value for value in candidates if key(value) == model['name'])
        control = corners(previous.OUT / model['path'])
        plan, metadata = root / 'planned' / slug, root / 'materials' / slug
        planner(['--slug', slug, '--metadata-output', str(metadata), '--output', str(plan)])
        value = validate(plan)
        material_data = json.loads((metadata / 'materials.json').read_text())
        assert material_data['materials'] == {k: v for k, v in materials.items() if k.startswith('hero_' + slug + '_')}
        for filename, digest in material_data['files'].items():
            assert sha(previous.OUT / 'textures' / filename) == digest
        actual = Counter()
        for row in value['pieces']:
            output = root / 'exports' / row['name']
            exporter(['--input', str(plan / row['payload']), '--output', str(output), '--format', '.glb'])
            actual.update(corners(output / (row['name'] + '.glb')))
        assert actual == control, (slug, 'complete serialized corners/material names changed')
        assert sum(row['triangles'] for row in value['pieces']) == model['triangles']
        results[slug] = dict(pieces=len(value['pieces']), triangles=model['triangles'],
            texture_files=material_data['files'], unchanged_parent_group=group)
        print('COASTAL HERO EXPORT MATCH', slug, results[slug]['pieces'], flush=True)
    assert len(results) == 3 and identities() == before
    atomic_json(root / 'result.json', dict(complete=True, assets=results,
        serialized_geometry_equal=True, exact_material_texture_equal=True, inputs=before,
        scope='actual committed hero exporter conservation; Unreal receiving remains pending'))
    print('COASTAL HERO EXPORT CANARY COMPLETE', flush=True)


if __name__ == '__main__': main()
