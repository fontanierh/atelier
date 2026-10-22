"""Run the actual map builder twice without an editor or deleting prior assets."""
import ast
from pathlib import Path
from types import SimpleNamespace

import pytest


class Node:
    def __init__(self):
        self.values = {}

    def set_editor_property(self, key, value):
        self.values[key] = value

    def get_editor_property(self, key):
        return self.values.get(key, 0)

    def __getattr__(self, key):
        if key.startswith('set_'):
            return lambda *args: None
        return self.values.setdefault(key, Node())


def builder(*, blank_fails=False, save_fails=False):
    source = Path(__file__).parents[1]/'unreal/Scripts/setup_project.py'
    function = next(n for n in ast.parse(source.read_text()).body if isinstance(n, ast.FunctionDef) and n.name == 'build_level')
    state = SimpleNamespace(world=None, maps={'/Game/Japan/Maps/Slice': 'prior saved map'}, saves=[], logs=[])
    def blank(partitioned):
        assert partitioned is False
        if blank_fails:
            return None
        state.world = SimpleNamespace(actors=[])
        return state.world
    def spawn(*args):
        actor = Node()
        state.world.actors.append(actor)
        return actor
    def save(world, path):
        assert world is state.world
        state.saves.append((world,path))
        if save_fails:
            return False
        state.maps[path] = world
        return True
    editor = SimpleNamespace(spawn_actor_from_class=spawn)
    enum = SimpleNamespace(STATIC='static', MOVABLE='movable', AEM_HISTOGRAM='histogram', LUMEN='lumen')
    unreal = SimpleNamespace(EditorActorSubsystem=object(), get_editor_subsystem=lambda kind: editor,
        EditorLoadingAndSavingUtils=SimpleNamespace(new_blank_map=blank, save_map=save),
        ComponentMobility=enum, AutoExposureMethod=enum, DynamicGlobalIlluminationMethod=enum,
        StaticMeshActor=object(), DirectionalLight=object(), SkyLight=object(), ExponentialHeightFog=object(),
        PostProcessVolume=object(), PlayerStart=object())
    for name in ('Vector','Vector4','Rotator','LinearColor','ExponentialHeightFogData','WeightedBlendables','WeightedBlendable'):
        setattr(unreal,name,lambda *a,**kw: (a,kw))
    scope = dict(unreal=unreal, opt=lambda obj,key,value: obj.set_editor_property(key,value),
                 soft_colour_grade=lambda settings: None, LOG=state.logs.append)
    exec(compile(ast.Module(body=[function],type_ignores=[]),str(source),'exec'),scope)
    state.run = lambda: scope['build_level'](object(), {'player_start':[0,0,0,0]}, {'_painterly':object()})
    return state


def test_repeat_map_build_populates_a_new_world_and_replaces_only_its_saved_map():
    state = builder()
    state.run()
    first = state.maps['/Game/Japan/Maps/Slice']
    assert len(first.actors) == 6
    state.run()
    second = state.maps['/Game/Japan/Maps/Slice']
    assert second is not first and len(second.actors) == 6
    assert len(state.maps) == 1 and len(state.saves) == 2
    assert len(state.logs) == 4


def test_blank_world_failure_refuses_before_population_or_save():
    state = builder(blank_fails=True)
    with pytest.raises(RuntimeError,match='replacement Slice'):
        state.run()
    assert state.saves == [] and state.maps['/Game/Japan/Maps/Slice'] == 'prior saved map'


def test_failed_map_save_does_not_report_completion():
    state = builder(save_fails=True)
    with pytest.raises(RuntimeError,match='Failed to save'):
        state.run()
    assert not any(line.startswith('level saved:') for line in state.logs)
