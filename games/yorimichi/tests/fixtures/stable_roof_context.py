"""Observe roof entry state from the immutable original Barn, never production sibling replay."""
import argparse
import ast
import json
from pathlib import Path
import sys
import types

GAME = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(GAME / 'world'))
import yori  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import real_directory, sha  # noqa: E402
from atelier.build_inputs import local_imports  # noqa: E402
from village.atomic_sources import restore  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    baseline = real_directory(args.baseline); output = real_directory(args.output)
    if output.exists(): raise ValueError('Fresh immutable roof witness required')
    receipt = json.loads((baseline / 'guard/memory-health-tree.json').read_text())
    if receipt['state'] != 'child_exited' or not receipt['cleanup_complete'] or receipt['processes']:
        raise ValueError('Original complete Stable source census has not stopped')
    if json.loads((baseline / 'whole-result.json').read_text()).get('exit_code') != 0:
        raise ValueError('Original Stable enclosing source census did not succeed')
    if 'STABLE ORIGINAL CONTEXT COMPLETE' not in (baseline / 'guard/stdout.log').read_text():
        raise ValueError('Missing original Stable census marker')
    context_path = baseline / 'products/contexts.json'
    contexts = json.loads(context_path.read_text())
    if not contexts['complete'] or len(contexts['contexts']) != 21: raise ValueError('Incomplete original Stable context')
    yori.OUT = baseline / 'products/data'
    fixture = Path(__file__).with_name('stable-predecessor-283329c07.txt')
    if sha(fixture) != contexts['predecessor_sha256']: raise ValueError('Original Stable authority differs')
    source = GAME / 'world/regions/hidamari_stable/build.py'
    files = set(local_imports(source, (GAME / 'world', GAME / 'world/regions')))
    files.update((fixture, Path(__file__), context_path, baseline / 'whole-result.json',
                  baseline / 'products/result.json', baseline / 'guard/memory-health-tree.json',
                  baseline / 'products/data/treehouse/trees/trees.json', GAME / 'world/regions/hidamari/fonts/NotoSansJP.ttf'))
    before = {str(path): sha(path) for path in files}
    tree = ast.parse(fixture.read_text())
    tree.body = [n for n in tree.body if not (isinstance(n, ast.If)
        and ast.unparse(n.test) == "__name__ == '__main__'")]
    scope = types.ModuleType('stable_immutable_roof_witness'); scope.__file__ = str(fixture)
    sys.modules[scope.__name__] = scope
    exec(compile(tree, str(fixture), 'exec'), scope.__dict__)
    roof = scope.roof; observed = {}
    def observe(m, lod):
        observed[lod] = dict(state=json.loads(json.dumps(scope.v.R.getstate())), start=len(m.faces))
        return roof(m, lod)
    scope.roof = observe
    rows = {}
    for lod in (0, 1, 2):
        scope.palette(); restore(scope.v.R, contexts['contexts']['barn_LOD' + str(lod)])
        m = scope.v.Mesh('SM_HS_Stable_LOD' + str(lod)); scope.barn(m, lod)
        first = observed[lod]['start']; whole = contexts['semantic_face_ranges']['barn_LOD' + str(lod)]
        if whole != [0, len(m.faces)]: raise ValueError('Immutable Barn face range differs from complete census')
        contexts['contexts']['roof_LOD' + str(lod)] = observed[lod]['state']
        contexts['semantic_face_ranges']['barn_LOD' + str(lod)] = [0, first]
        contexts['semantic_face_ranges']['roof_LOD' + str(lod)] = [first, len(m.faces)]
        rows[lod] = dict(shell_triangles=sum(len(f)-2 for f in m.faces[:first]),
                         roof_triangles=sum(len(f)-2 for f in m.faces[first:]))
        print('IMMUTABLE STABLE BARN SPLIT ' + str(lod) + ' ' + json.dumps(rows[lod]), flush=True)
    contexts['roof_witness'] = dict(original_context_sha256=sha(context_path), parts=rows)
    if {str(path): sha(path) for path in files} != before: raise ValueError('Roof proof inputs changed')
    atomic_json(output / 'contexts.json', contexts)
    atomic_json(output / 'result.json', dict(complete=True, parts=rows, source_inputs=before,
        scope='actual immutable original Barn roof-entry states; source/GLB union remains separate'))
    print('STABLE IMMUTABLE ROOF CONTEXT COMPLETE', flush=True)


if __name__ == '__main__': main()
