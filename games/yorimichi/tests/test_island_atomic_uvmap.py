"""Standalone Guardrail and Wires island pieces carry the one zero-filled UVMap the atomic validators require.

The actual planner `construct()` runs the actual `obj`/`mat`/`guardrail`/`wires` source of build_terrain.py on a
finite fixture, against a minimal mesh stand-in for Blender. No Blender, export or import runs here.
"""
import ast
import math
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

GAME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GAME / 'world'))
import plan_terrain  # noqa: E402

SOURCE = GAME / 'world/build_terrain.py'


class Vector:
    def __init__(self, values):
        self.v = [float(value) for value in values]

    x = property(lambda self: self.v[0])
    y = property(lambda self: self.v[1])

    @property
    def z(self):
        return self.v[2]

    @z.setter
    def z(self, value):
        self.v[2] = float(value)

    def __iter__(self):
        return iter(self.v)

    def __add__(self, other):
        return Vector(a + b for a, b in zip(self, other))

    def __sub__(self, other):
        return Vector(a - b for a, b in zip(self, other))

    def __mul__(self, scale):
        return Vector(a * scale for a in self)

    @property
    def length(self):
        return math.sqrt(sum(a * a for a in self))

    def normalized(self):
        return self * (1.0 / self.length)

    def cross(self, other):
        (a, b, c), (d, e, f) = self.v, other.v
        return Vector((b * f - c * e, c * d - a * f, a * e - b * d))

    def lerp(self, other, t):
        return Vector(a + (b - a) * t for a, b in zip(self, other))


class Layers(list):
    """A mesh's UV layers; a new layer holds one UV per loop, as in Blender."""

    def __init__(self, mesh):
        super().__init__()
        self.mesh = mesh

    def new(self, name):
        layer = SimpleNamespace(name=name, data=[SimpleNamespace(uv=None) for _ in self.mesh.loops])
        self.append(layer)
        return layer


class Mesh:
    def __init__(self, name):
        self.name, self.materials, self.uv_layers = name, [], Layers(self)

    def from_pydata(self, verts, edges, faces):
        self.vertices = [SimpleNamespace(co=Vector(v)) for v in verts]
        self.loops, self.polygons = [], []
        for face in faces:
            start = len(self.loops)
            self.loops += [SimpleNamespace(vertex_index=index) for index in face]
            self.polygons.append(SimpleNamespace(use_smooth=False, loop_indices=range(start, len(self.loops))))

    def update(self):
        pass


def blender():
    def material(name):
        inputs = {'Base Color': SimpleNamespace(), 'Roughness': SimpleNamespace()}
        return SimpleNamespace(name=name, node_tree=SimpleNamespace(nodes={'Principled BSDF': SimpleNamespace(inputs=inputs)}))

    module = ModuleType('bpy')
    module.data = SimpleNamespace(materials=SimpleNamespace(new=material), meshes=SimpleNamespace(new=Mesh),
                                  objects=SimpleNamespace(new=lambda name, me: SimpleNamespace(name=name, data=me)))
    module.context = SimpleNamespace(scene=SimpleNamespace(collection=SimpleNamespace(objects=SimpleNamespace(
        link=lambda ob: None))))
    module.ops = SimpleNamespace(wm=SimpleNamespace(read_factory_settings=lambda use_empty: None))
    return module


def snapshot(ob):
    me = ob.data
    return dict(vertices=[tuple(v.co) for v in me.vertices], loops=[loop.vertex_index for loop in me.loops],
                polygons=[list(p.loop_indices) for p in me.polygons], smooth=[p.use_smooth for p in me.polygons],
                materials=list(me.materials),
                uv_layers=[(layer.name, [tuple(uv.uv) for uv in layer.data]) for layer in me.uv_layers])


@pytest.fixture
def island(monkeypatch):
    """The actual build_terrain source for obj/mat/guardrail/wires; the other keys are obj()-built stand-ins."""
    bpy = blender()
    tree = ast.parse(SOURCE.read_text(), filename=str(SOURCE))
    functions = [node for node in tree.body
                 if isinstance(node, ast.FunctionDef) and node.name in {'obj', 'mat', 'guardrail', 'wires'}]
    assert len(functions) == 4
    scope = dict(bpy=bpy, np=np, Vector=Vector, LOAD_TEXTURES=False)
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(SOURCE), 'exec'), scope)
    module = ModuleType('build_terrain')
    made = {}

    def recorded(key, constructor):
        def run(*args, **kwargs):
            ob = constructor(*args, **kwargs)
            made[key] = (ob, snapshot(ob))
            return ob
        return run

    quad = ([(0., 0., 0.), (1., 0., 0.), (1., 1., 0.), (0., 1., 0.)], [(0, 1, 2, 3)])
    planar = lambda co: (co.x / 6.0, co.y / 6.0)
    stand_ins = dict(terrain=planar, road=None, lane=planar, farhills=planar, sea=None)
    for name, uvs in stand_ins.items():
        constructor = (lambda name, uvs: lambda W, H, final, *, city: scope['obj'](
            name.title(), *quad, scope['mat'](name), uvs=uvs))(name, uvs)
        setattr(module, name, recorded(name, constructor))
    for name in ('guardrail', 'wires'):
        setattr(module, name, recorded(name, scope[name]))
    monkeypatch.setitem(sys.modules, 'bpy', bpy)
    monkeypatch.setitem(sys.modules, 'build_terrain', module)
    return SimpleNamespace(scope=scope, module=module, made=made, recorded=recorded)


def world():
    return dict(rail_runs=[[[0., 0., 0., 1., 0.], [1., 0., 0., 1., 0.], [2., 0., 0., 1., 0.]]],
                anchors=[[[0., 0., 3.], [0., 1., 3.]], [[10., 0., 3.], [10., 1., 3.]]])


def source(key):
    return dict(schema=1, asset=key, enabled=True, world=world(), city=True)


@pytest.mark.parametrize('key', ['Guardrail', 'Wires'])
def test_guardrail_and_wires_get_exactly_one_zero_filled_uvmap(island, key):
    result = plan_terrain.construct(key, source(key))
    made, before = island.made[key.lower()]
    assert result is made, 'the constructor object itself reaches the planner'
    assert before['uv_layers'] == [], 'the constructor makes no UV layer of its own'
    me = result.data
    assert [layer.name for layer in me.uv_layers] == ['UVMap']
    uvs = me.uv_layers[0].data
    assert me.loops and len(uvs) == len(me.loops) == sum(len(p.loop_indices) for p in me.polygons)
    assert all(tuple(loop.uv) == (0.0, 0.0) for loop in uvs)
    after = snapshot(result)
    for field in ('vertices', 'loops', 'polygons', 'smooth', 'materials'):
        assert after[field] == before[field], field
    assert all(after['smooth'])


@pytest.mark.parametrize('key', ['Terrain', 'Road', 'Lane', 'FarHills', 'Sea'])
def test_every_other_island_key_keeps_its_uv_layers_unchanged(island, key):
    result = plan_terrain.construct(key, source(key))
    made, before = island.made[key.lower()]
    assert result is made
    assert snapshot(result) == before


@pytest.mark.parametrize('key', ['Guardrail', 'Wires'])
def test_a_preexisting_uv_layer_on_guardrail_or_wires_is_refused_untouched(island, key):
    real = island.scope[key.lower()]

    def with_uvs(*args, **kwargs):
        ob = real(*args, **kwargs)
        layer = ob.data.uv_layers.new(name='Authored')
        for loop in layer.data:
            loop.uv = (0.5, 0.25)
        return ob
    setattr(island.module, key.lower(), island.recorded(key.lower(), with_uvs))
    with pytest.raises(ValueError, match='already has a UV layer'):
        plan_terrain.construct(key, source(key))
    made, before = island.made[key.lower()]
    assert snapshot(made) == before, 'the refused layer is neither overwritten nor joined by a second one'
    assert [layer.name for layer in made.data.uv_layers] == ['Authored']


def test_existing_refusals_still_precede_the_uv_step(island):
    with pytest.raises(ValueError, match='foreign'):
        plan_terrain.construct('Guardrail', dict(source('Guardrail'), asset='Wires'))
    island.module.guardrail = lambda *args, **kwargs: None
    with pytest.raises(ValueError, match='no geometry'):
        plan_terrain.construct('Guardrail', source('Guardrail'))
