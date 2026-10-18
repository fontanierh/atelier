"""Exercise the authored surf expression and both actual water material builders.

Native shader compilation and near/grazing visual comparison remain required.
"""
import importlib.util
from pathlib import Path
import re
import sys
from types import SimpleNamespace

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / 'unreal/Scripts'


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name+'.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_deep_water_cannot_make_surf_at_a_background_depth_discontinuity():
    sea = load('sea_look')
    # Evaluate the actual emitted HLSL width/edge expressions. Large derivatives
    # model the native white line at the submerged country mesh's outer edge.
    width = re.search(r'float w=(.*);', sea.LOOK).group(1)
    edge = re.search(r'float edge=saturate\((.*)\);', sea.LOOK).group(1)
    for fp in [0., .05, 2., 32., 10000.]:
        w = eval(width, {'__builtins__': {}}, dict(min=min, fp=fp))
        assert .35 <= w <= 1.35
        for wob in [0., .5, 1.]:
            for depth in [3., 32., 500.]:
                value = eval(edge, {'__builtins__': {}}, dict(l=depth, w=w, wob=wob))
                assert max(0., min(1., value)) == 0.
            assert eval(edge, {'__builtins__': {}}, dict(l=0., w=w, wob=wob)) == 1.


@pytest.mark.parametrize('owner', ['import_southwest', 'harbor_material'])
def test_water_material_owners_build_shared_depth_look_with_per_pixel_fog(monkeypatch, owner):
    class Node:
        def __init__(self, **kwargs):
            self.values = kwargs
        def set_editor_property(self, name, value):
            self.values[name] = value

    class Enum:
        def __getattr__(self, name):
            return name

    material, nodes = Node(), []
    def create(material, cls, *args):
        node = Node(kind=cls)
        nodes.append(node)
        return node

    mel = SimpleNamespace(delete_all_material_expressions=lambda *args: None,
                          create_material_expression=create,
                          connect_material_expressions=lambda *args: True,
                          connect_material_property=lambda *args: True,
                          recompile_material=lambda *args: None,
                          layout_material_expressions=lambda *args: None)
    class Unreal:
        def __getattr__(self, name):
            return name if name.startswith('MaterialExpression') else Enum()
    fake = Unreal()
    fake.EditorAssetLibrary = SimpleNamespace(does_asset_exist=lambda *args: True,
                                              load_asset=lambda *args: material,
                                              save_loaded_asset=lambda *args: None)
    fake.MaterialEditingLibrary = mel
    fake.CustomInput = Node
    fake.Material = Node
    fake.MaterialFactoryNew = Node
    fake.LinearColor = lambda *args: args
    monkeypatch.setitem(sys.modules, 'unreal', fake)
    monkeypatch.setitem(sys.modules, 'import_village', SimpleNamespace())
    sea = load('sea_look')
    monkeypatch.setitem(sys.modules, 'sea_look', sea)
    monkeypatch.syspath_prepend(str(SCRIPTS))
    module = load(owner)
    actual = module.sea_material() if owner == 'import_southwest' else module.material(water=True)
    assert actual is material
    assert material.values['compute_fog_per_pixel'] is True
    assert material.values['blend_mode'] == 'BLEND_TRANSLUCENT'
    looks = [n for n in nodes if n.values.get('code') == sea.LOOK]
    assert len(looks) == 1
    assert 'L' in [n.values['input_name'] for n in looks[0].values['inputs']]
