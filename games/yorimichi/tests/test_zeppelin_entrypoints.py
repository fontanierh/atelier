"""Real CLI/import boundaries work without ambient region or editable-install paths."""
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

GAME = Path(__file__).resolve().parents[1]
REGION = GAME / 'world/regions/zeppelin'
PLANNERS = ('airship', 'asset', 'belmonte', 'city', 'gangway', 'gate', 'megapark',
            'motors', 'propeller', 'trail', 'woodland')


def test_query_cli_publishes_real_woodland_queries_from_an_unrelated_directory(tmp_path):
    root = tmp_path / 'build'; data = root / 'yorimichi'; data.mkdir(parents=True)
    np.save(data / 'heightmap.npy', np.full((4, 4), 42.25))
    output = tmp_path / 'queries/station.json'
    env = dict(os.environ, ATELIER_BUILD_ROOT=str(root))
    result = subprocess.run([sys.executable, '-I', str(REGION / 'project_queries.py'),
                             '--asset', 'ZP_Woodland', '--output', str(output)],
                            cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    value = json.loads(output.read_text())
    assert value['schema'] == 1 and value['asset'] == 'ZP_Woodland'
    assert len(value['ground']) > 100
    assert all(height == pytest.approx(42.25, abs=1e-12, rel=0) for height in value['ground'].values())


@pytest.mark.parametrize('label', PLANNERS)
def test_actual_planner_entrypoint_bootstraps_regions_world_and_studio(tmp_path, label):
    # Only Blender's native modules are replaced. Zeppelin, yori, region_mesh_parts
    # and their actual Python dependencies must import from the source checkout.
    code = r'''
import importlib.abc, pathlib, runpy, sys, types
script = pathlib.Path(sys.argv[1]); world = script.parents[2]
assert 'zeppelin' not in sys.modules and 'yori' not in sys.modules
assert str(world) not in sys.path and str(world / 'regions') not in sys.path
bpy = types.ModuleType('bpy'); sys.modules['bpy'] = bpy
mathutils = types.ModuleType('mathutils')
class NativeBoundary:
    def __init__(self, *args, **kwargs): raise AssertionError('No native geometry in import/help check')
mathutils.Matrix = mathutils.Vector = NativeBoundary
sys.modules['mathutils'] = mathutils
class RequireBootstrap(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] == 'atelier' and 'yori' not in sys.modules:
            raise AssertionError('Studio imported before actual yori bootstrap')
sys.meta_path.insert(0, RequireBootstrap())
sys.argv = [str(script), '--', '--help']
try:
    runpy.run_path(str(script), run_name='__main__')
except SystemExit as exc:
    assert exc.code == 0
else:
    raise AssertionError('Actual planner main/help did not run')
assert pathlib.Path(sys.modules['zeppelin'].__file__).resolve().parent == script.parent
assert pathlib.Path(sys.modules['yori'].__file__).resolve() == world / 'yori.py'
assert pathlib.Path(sys.modules['region_mesh_parts'].__file__).resolve() == world / 'region_mesh_parts.py'
assert str(world) in sys.path and str(world / 'regions') in sys.path
print('ACTUAL ZEPPELIN PLANNER ENTRYPOINT READY', script.name)
'''
    result = subprocess.run([sys.executable, '-I', '-c', code, str(REGION / f'plan_{label}.py')],
                            cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'ACTUAL ZEPPELIN PLANNER ENTRYPOINT READY' in result.stdout


def test_all_eleven_planner_declarations_and_five_query_sites_are_covered(tmp_path):
    assert {p.stem.removeprefix('plan_') for p in REGION.glob('plan_*.py')} == set(PLANNERS)
    # Load the actual graph in its own process; no package state from other tests.
    code = r'''
import pathlib, runpy, sys, types
script = pathlib.Path(sys.argv[1])
module = runpy.run_path(str(script))
rows = module['steps'](types.SimpleNamespace(out=pathlib.Path(sys.argv[2])))
queries = [row for row in rows if row.name.startswith('world.zeppelin.query.')]
assert {row.name.rsplit('.', 1)[1] for row in queries} == {'ZP_Woodland', 'ZP_City', 'ZP_MegaPark', 'ZP_Belmonte', 'ZP_Trail'}
assert all(row.commands[0].script == script.parent / 'project_queries.py' for row in queries)
planners = [row for row in rows if row.name.startswith('world.zeppelin.geometry.')]
assert len(planners) == 10
assert {row.commands[0].script.name for row in planners} == {'plan_' + label + '.py' for label in sys.argv[3:]}
'''
    result = subprocess.run([sys.executable, '-I', '-c', code, str(REGION / 'atomic.py'), str(tmp_path / 'out'),
                             *(label for label in PLANNERS if label != 'asset')],
                            cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
