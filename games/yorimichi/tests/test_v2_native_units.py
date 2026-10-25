"""Shared native constructor composition uses actual source texture declarations."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier.build_v2.recipe_dependencies import extract

ROOT = Path(__file__).resolve().parents[3]
GAME = ROOT / 'games/yorimichi'


def load(name):
    spec = importlib.util.spec_from_file_location(name, GAME / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rows():
    return extract(load('build').texture_steps(SimpleNamespace(out=ROOT / 'build/yorimichi')),
                   checkout=ROOT, build_root=ROOT / 'build')


def test_real_shared_library_joins_individual_raw_finish_and_graph_owners():
    graph = load('v2_native_units').shared_materials(rows(), checkout=ROOT)
    units = {unit['id']: unit for unit in graph['units']}
    assert len(units) == 84 and len(graph['targets']) == 40
    assert len(graph['packages']) == 62
    assert all(units[name]['op']['kind'] == 'unreal.author' for name in graph['targets'])
    for unit in units.values():
        assert len(unit['outputs']) == 1
        assert unit['script'] in unit['code']
        assert 'platform/build-v2/unreal/AtelierBuildWorker/Source/AtelierBuildWorker/Private/AtelierBuildWorkerLibrary.cpp' in unit['code']
        for incoming in unit['inputs']:
            owner = incoming['source']['unit']
            assert owner in units or owner.startswith('world.textures.')
            if owner in units:
                assert incoming['source']['item'] in {item['id'] for item in units[owner]['outputs']}
    assert units['unreal.materials.MI_LeafMaple']['inputs']
    assert any(row['source']['unit'] == 'unreal.texture.finish.leaf_maple'
               for row in units['unreal.materials.MI_LeafMaple']['inputs'])


def test_missing_texture_does_not_produce_an_incomplete_material_selection():
    with pytest.raises(ValueError, match='all 22'):
        load('v2_native_units').shared_materials(rows()[1:], checkout=ROOT)
