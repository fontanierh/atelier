"""Selected Gondola command ownership and complete ordinary graph declarations."""
from contextlib import contextmanager
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

GAME = Path(__file__).resolve().parents[1]


def load(name,path):
    spec = importlib.util.spec_from_file_location(name,path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


commands = load('gondola_commands_test',GAME / 'assets/vehicles/gondola/commands.py')
graph = load('gondola_graph_test',GAME / 'gondola_atomic_build.py')


class Mesh:
    def __init__(self,name):
        self.name = name; self.events = []; self.parts = []; self.origins = []

    @contextmanager
    def at(self,*args,**kwargs):
        self.events.append(('enter',args,kwargs))
        try: yield
        finally: self.events.append(('exit',))

    def box(self,*args,**kwargs):
        self.events.append(('box',args,kwargs))
        self.parts.append((0,1)); self.origins.append('replay')


def test_selected_replay_retains_nested_order_and_author_origin():
    recorder = commands.Recorder('GD_Selected')
    with recorder.at((2,3,4),yaw=37):
        recorder.box((1,2,3),(4,5,6),'GD_Timber')
        with recorder.at((0,1,0)):
            recorder.box((7,8,9),(1,1,1),'GD_Stone')
    mesh = commands.replay(dict(schema=1,asset=recorder.name,commands=recorder.commands),Mesh)
    assert [row[0] for row in mesh.events] == ['enter','box','enter','box','exit','exit']
    assert mesh.events[1][1] == ([1,2,3],[4,5,6],'GD_Timber')
    assert mesh.origins == [row[4] for row in recorder.commands if row[0] == 'primitive']
    assert all('test_gondola_atomic_build.py:' in origin for origin in mesh.origins)


@pytest.mark.parametrize('stream',[
    [['exit','at']], [['enter','at',[],{}]],
    [['enter','at',[],{}],['exit','wall']],
    [['primitive','unknown',[],{},'source:1']],
    [['primitive','box',[float('nan')],{},'source:1']],
])
def test_invalid_stream_refuses_before_any_geometry(stream):
    constructed = []
    class Tracked(Mesh):
        def __init__(self,name): constructed.append(name); super().__init__(name)
    with pytest.raises(ValueError):
        commands.replay(dict(schema=1,asset='GD_Selected',commands=stream),Tracked)
    assert constructed == []


def test_unknown_source_operation_and_unpublished_height_refuse():
    recorder = commands.Recorder('GD_Selected')
    with pytest.raises(AttributeError): recorder.new_primitive()
    height = commands.thaw(dict(height_samples=[[1.,2.,3.],[4.,5.,6.]]))
    assert height(1.,2.) == 3.
    with pytest.raises(ValueError): height(1.,2.000000001)


def test_kit_planners_own_one_selected_source_and_query(tmp_path):
    steps = graph.kit_steps(SimpleNamespace(out=tmp_path))
    parameters,render,collision = graph.kit_names()
    planners = [step for step in steps if step.name.startswith('world.gondola_kit.geometry.')]
    assert len(planners) == len(render) == 23
    for step,key in zip(planners,render):
        assert step.reads == ['gondola_kit.source.'+key]
        assert len(step.products) == 2
        assert step.products[1].name == 'gondola_kit.query.'+key
        assert step.commands[0].threads == 3
        assert step.commands[0].factory_startup is True
    collisions = [step for step in steps if step.name.startswith('world.gondola_kit.collision.')]
    assert len(collisions) == len(collision) == 10
    assert len({path for step in planners+collisions for product in step.products for path in product.paths}) == 56
    final = next(step for step in steps if step.name == 'world.gondola_kit')
    assert final.reads[:3] == ['gondola_kit.atomic','gondola_kit.audit','gondola_kit.textures']
