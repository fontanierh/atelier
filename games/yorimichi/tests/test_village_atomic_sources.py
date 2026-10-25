"""Selected Village geometry, RNG and placement ownership remain independent."""
import importlib.util
import json
from pathlib import Path
import random
import sys
from types import SimpleNamespace

import pytest

from atelier.build import check_modules

GAME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GAME / 'world'))
import yori  # noqa: E402,F401
from village.atomic_sources import ASSETS, HEIGHTS, current_palette, project, restore  # noqa: E402


def contexts():
    return {key: dict(state=json.loads(json.dumps(random.Random(76+i).getstate())), palette_keys=sorted(current_palette()))
            for i, key in enumerate(ASSETS)}


def world():
    return dict(road=[[0, 0, 0], [1, 1, 0]], road_width=2.,
                village=dict(paths=[[[0, 0, 0], [1, 1, 0]]], buildings=[dict(asset=ASSETS[0], width=8., depth=6.,
                             position=[1., 2., 3.], yaw=0.)], planting_beds=[[10., 10., 1., 1.]]),
                instances={key: [[0, 0, 0, 0]] for key in ASSETS})


def test_full_state_preserves_uniform_choice_and_getrandbits_together():
    original = random.Random(76)
    for _ in range(17): original.choice(range(5)); original.uniform(-1, 1)
    state = json.loads(json.dumps(original.getstate()))
    expected = [(original.choice(range(5)), original.uniform(-1, 1), original.getrandbits(17)) for _ in range(31)]
    current = random.Random(); restore(current, state)
    assert [(current.choice(range(5)), current.uniform(-1, 1), current.getrandbits(17)) for _ in range(31)] == expected


@pytest.mark.parametrize('state', [[], [3, [], None], [3, [True]*625, None], [3, [-1]*625, None],
                                 [3, [0]*624+[625], None], [3, [0]*625, 0.]])
def test_malformed_or_partial_random_context_refuses(state):
    with pytest.raises(ValueError): restore(random.Random(), state)


def test_placement_and_unrelated_world_edits_do_not_change_geometry_data():
    w = world(); frozen = contexts(); before = project(w, frozen)
    w['instances'][ASSETS[0]][0][0] = 99.; w['boats'] = ['new']
    assert project(w, frozen) == before
    w['road_width'] = 4.
    current = project(w, frozen)
    assert [key for key in ASSETS if current[key] != before[key]] == ['Village_Ground']


def test_path_change_only_reaches_actual_ground_edge_and_planting_consumers():
    w = world(); frozen = contexts(); before = project(w, frozen)
    w['village']['paths'][0][0][0] = 5.
    current = project(w, frozen)
    assert {key for key in ASSETS if before[key] != current[key]} == {'Village_Ground', 'Village_Edges', 'Village_Planting'}


def test_only_consumed_palette_values_enter_selected_geometry_inputs():
    selected = contexts()
    for entry in selected.values(): entry['palette_keys'] = ['wood']
    selected['Village_Garden']['palette_keys'] = ['stone']
    palette = current_palette(); before = project(world(), selected, palette=palette)
    palette['water'] = (.1, .1, .1)
    assert project(world(), selected, palette=palette) == before
    palette['stone'] = (.2, .2, .2)
    after = project(world(), selected, palette=palette)
    assert [key for key in ASSETS if before[key] != after[key]] == ['Village_Garden']


def test_normal_graph_has_twelve_explicit_factories_and_separate_selected_inputs(tmp_path):
    assert HEIGHTS == {'Village_Garden', 'Village_Ground', 'Village_Edges', 'Village_Planting'}
    spec = importlib.util.spec_from_file_location('village_atomic_recipe_test', GAME / 'village_atomic_build.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    steps = module.steps(SimpleNamespace(out=tmp_path))
    planners = [step for step in steps if step.name.startswith('world.village.geometry.')]
    assert len(planners) == 12
    for step in planners:
        key = step.name.rsplit('.', 1)[1]
        assert step.cache and step.commands[0].factory_startup and step.commands[0].threads == 3
        assert step.reads == ['village.source.' + key] + (['village.final_heightmap'] if key in HEIGHTS else [])
        assert not any(p.name == 'construction-contexts.json' for p in step.inputs)
    assert steps[-2].name == 'world.village' and steps[-1].name == 'world.village.import'
    check_modules(steps)


def test_heightmap_temporary_uses_existing_managed_scratch_without_changing_npy(tmp_path,monkeypatch):
    import io
    import numpy as np
    from atelier.atomic_files import managed_temporaries
    from village.atomic_sources import publish
    scratch=tmp_path/'scratch';scratch.mkdir();output=tmp_path/'projection'
    value=np.arange(9,dtype=np.float64).reshape(3,3)
    save=np.save;names=[]
    def record(stream,*args,**kwargs):
        names.append(Path(stream.name));return save(stream,*args,**kwargs)
    monkeypatch.setattr(np,'save',record)
    with managed_temporaries(scratch):publish(world(),value,output,contexts())
    assert names[0].parent==scratch
    expected=io.BytesIO();save(expected,value,allow_pickle=False)
    assert (output/'heightmap.npy').read_bytes()==expected.getvalue()
    assert list(scratch.iterdir())==[]
