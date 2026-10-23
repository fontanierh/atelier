"""Measure original city constructor context and compare extracted geometry without exporting meshes."""
import argparse
import gc
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys

import bpy
import numpy as np

GAME = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(GAME / 'world'))
import yori  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.build_cache import copy_file  # noqa: E402
from atelier.build_inputs import local_imports  # noqa: E402
from atelier.export_manifest import real_directory, sha  # noqa: E402
from mesh_pieces import capture  # noqa: E402

INPUTS = ('world.json', 'heightmap.npy', 'farhills.npy', 'megapark/trail.json',
          'craterpark/v2/geometry.npz')
SELECTED = {
    'HD_Temple': ('temple_mesh', 'temple'), 'HD_Pavilion': ('pavilion_mesh', 'pavilion'),
    'HD_Playground': ('playground_mesh', 'playground'), 'HD_Boat': ('boat_mesh', 'boat'),
    'HD_Lighthouse': ('lighthouse_mesh', 'lighthouse'),
    'HD_Streets': ('streets_mesh', 'streets'), 'HD_Harbor': ('harbor_mesh', 'harbor'),
    'HD_Square': ('square_mesh', 'square'), 'HD_Park': ('park_mesh', 'park'),
    'HD_InlandWater': ('water_mesh', 'inland_water'),
}


def signature(source, surfaces):
    if surfaces.textured(source.name):
        obj, _ = surfaces.mesh_object(source)
    else:
        material = bpy.data.materials.get('HidamariPalette') or bpy.data.materials.new('HidamariPalette')
        obj = source.object(material)
    mesh = obj.data
    data = capture(mesh)
    def array(a):
        return dict(shape=list(a.shape), dtype=str(a.dtype), sha256=hashlib.sha256(a.tobytes()).hexdigest())
    result = {key: array(value) for key, value in data.items() if isinstance(value, np.ndarray)}
    result.update(selection=data['selection'], slots=[m.name for m in data['slots']],
        uvs=[(name, array(values)) for name, values in data['uvs']],
        colours=[(name, domain, kind, array(values)) for name, domain, kind, values in data['colours']],
        matrix=[list(row) for row in obj.matrix_world],
        colliders=[(tuple(c), tuple(s), tuple(r)) for c, s, r in source.colliders],
        triangles=int(sum(data['counts'] - 2)))
    bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.meshes.remove(mesh)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--donor', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    root = real_directory(args.output)
    if os.path.lexists(root):
        raise ValueError('City context evidence requires a fresh root')
    donor = real_directory(args.donor)
    inputs = {name: donor / name for name in INPUTS}
    for path in inputs.values():
        real_directory(path.parent)
        if path.is_symlink() or not path.is_file():
            raise ValueError('City context requires every declared current input')
    regions = GAME / 'world/regions'
    sources = set(local_imports(regions / 'hidamari/build.py', (GAME / 'world', regions)))
    sources.update(p for p in (regions / 'hidamari').rglob('*.py') if '__pycache__' not in p.parts)
    sources.add(regions / 'hidamari/fonts/NotoSansJP.ttf')
    sources.add(Path(__file__))
    def identities():
        return {str(p): sha(p) for p in sorted(sources | set(inputs.values()))}
    before = identities()
    for name, path in inputs.items():
        target = root / 'data' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        copy_file(path, target)
        assert sha(target) == before[str(path)]
    yori.OUT = root / 'data'
    bpy.ops.wm.read_factory_settings(use_empty=True)
    from hidamari import build, surfaces
    from village import mesh as kernel
    city = build.generate()
    builders = build.asset_builders(city)
    contexts, results = {}, {}
    draws = [0]
    next_random = kernel.R.random
    def counted():
        draws[0] += 1
        return next_random()
    kernel.R.random = counted
    for key, constructor in builders.items():
        palette, random_state = dict(kernel.PALETTE), kernel.R.getstate()
        contexts[key] = dict(seed=76, prefix_draws=draws[0], palette=palette)
        source = constructor()
        assert source.name == key
        after_palette, after_state, after_draws = dict(kernel.PALETTE), kernel.R.getstate(), draws[0]
        if key in SELECTED:
            reference = signature(source, surfaces)
            del source
            module, function = SELECTED[key]
            selected = getattr(importlib.import_module('hidamari.' + module), function)
            kernel.PALETTE.clear(); kernel.PALETTE.update(palette)
            kernel.R.setstate(random_state)
            actual = selected(city) if key == 'HD_Streets' else selected()
            observed = signature(actual, surfaces)
            assert observed == reference, (key, 'selected ordered geometry/corners/channels/collision changed')
            results[key] = reference
            del actual, observed, reference
            kernel.PALETTE.clear(); kernel.PALETTE.update(after_palette)
            kernel.R.setstate(after_state); draws[0] = after_draws
        else:
            del source
        gc.collect()
        atomic_json(root / 'progress.json', dict(completed=len(contexts), total=len(builders), asset=key))
        print(f'CITY CONTEXT {len(contexts)}/{len(builders)} {key}; checked {len(results)} selected constructors', flush=True)
    assert set(results) == set(SELECTED)
    assert identities() == before, 'City source or donor changed during context validation'
    atomic_json(root / 'contexts.json', contexts)
    atomic_json(root / 'result.json', dict(complete=True, ordered_attribute_hash_equality=True,
        selected=results, logical_assets=len(contexts), sources=before,
        scope='selected source geometry only; no atomic export or native receiving acceptance'))
    print('HIDAMARI ATOMIC CONTEXT COMPLETE', flush=True)


if __name__ == '__main__':
    main()
