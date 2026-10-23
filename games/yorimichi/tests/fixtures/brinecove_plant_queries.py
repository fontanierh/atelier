"""All actual coastal prototype queries equal their independently exported GLBs."""
import argparse
from collections import Counter
import importlib.util
import json
import os
from pathlib import Path
import sys

import bpy

GAME = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(GAME / 'world'), str(GAME / 'world/regions')]
import yori  # noqa: E402,F401
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.build_inputs import local_imports  # noqa: E402
from atelier.export_manifest import real_directory, sha  # noqa: E402
from brinecove import export_foliage_model, foliage_names  # noqa: E402
import region_query  # noqa: E402


def rows(triangles):
    result = Counter()
    for triangle in triangles:
        row = tuple(tuple(float(value) for value in point) for point in triangle)
        result[min(row[index:]+row[:index] for index in range(3))] += 1
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    root = real_directory(args.output)
    if os.path.lexists(root): raise ValueError('Prototype query proof requires fresh evidence')
    definitions = foliage_names.definitions()
    script = GAME / 'assets/vehicles/ferry/terminals/world_probe.py'
    inputs = {Path(__file__), *definitions, Path(foliage_names.__file__).with_name('foliage_catalog.json')}
    for source in (script, Path(export_foliage_model.__file__)):
        inputs.update(local_imports(source, (GAME / 'world', GAME / 'world/regions')))
    def identities():
        result = {}
        for path in sorted(inputs):
            real_directory(path.parent)
            if path.is_symlink() or not path.is_file(): raise ValueError('Linked prototype proof input')
            result[str(path)] = sha(path)
        return result
    before = identities()
    spec = importlib.util.spec_from_file_location('previous_prototype_query', script)
    old = importlib.util.module_from_spec(spec); spec.loader.exec_module(old)
    results = []
    for definition in definitions:
        prototype = definition.stem
        query = root / 'queries' / (prototype+'.npz')
        current, control = root / 'current' / prototype, root / 'control' / prototype
        export_foliage_model.main(definition, current, query)
        geometry = region_query.load(query, owner=foliage_names.name(prototype), stage='final')
        actual = rows(region_query.triangles(geometry))
        old.clear_scene()
        expected = rows(old.triangles(old.import_file(current / 'model.glb')))
        assert actual == expected, prototype+' query differs from actual exported geometry'
        export_foliage_model.main(definition, control)
        assert (current/'model.glb').read_bytes() == (control/'model.glb').read_bytes(), prototype+' GLB changed'
        assert json.loads((current/'model.json').read_text()) == json.loads((control/'model.json').read_text())
        results.append(dict(prototype=prototype, triangles=sum(actual.values()), query_sha256=sha(query),
                            glb_sha256=sha(current/'model.glb')))
        print('PROTOTYPE QUERY VERIFIED '+prototype, flush=True)
    assert len(results) == 36 and identities() == before
    atomic_json(root/'result.json', dict(complete=True, prototypes=results, exact_query_triangle_cycles=True,
        unchanged_glb_bytes=True, inputs=before,
        scope='all coastal prototype source queries/exported geometry; full ferry sweep and native receiving remain pending'))
    print('COASTAL PROTOTYPE QUERY CANARY COMPLETE', flush=True)


if __name__ == '__main__': main()
