"""Normal city layout and per-constructor projections have complete independent owners."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

from atelier.build import check_modules

GAME = Path(__file__).resolve().parents[1]
REGION = GAME / 'world/regions/hidamari'


def test_city_layout_is_required_factory_data_without_geometry_constructors(tmp_path):
    spec = importlib.util.spec_from_file_location('hidamari_data_graph', GAME / 'hidamari_build.py')
    recipe = importlib.util.module_from_spec(spec); spec.loader.exec_module(recipe)
    out = tmp_path.resolve()
    steps = recipe.layout_steps(SimpleNamespace(out=out), terrain_inputs=[GAME / 'assets/vehicles/belmonte-train/line.json'])
    check_modules(steps)
    layout = steps[0]
    assert layout.name == 'world.hidamari.layout_data'
    assert layout.cache and layout.commands[0].factory_startup and layout.commands[0].threads == 3
    assert layout.reads == ['terrain.FarHills.final']
    assert out / 'treehouse/trees/trees.json' in layout.inputs
    assert REGION / 'location.json' in layout.inputs
    assert REGION / 'layout.py' in layout.inputs
    assert REGION / 'build.py' not in layout.inputs
    assert not any(p.is_relative_to(REGION / 'kit') or p.is_relative_to(REGION / 'logical') for p in layout.inputs)
    for step, asset in zip(steps[1:], recipe.DATA_ASSETS):
        assert step.reads == ['hidamari.city_data']
        assert step.cache and not step.needs
        assert step.products[0].name == 'hidamari.data.' + asset
        assert all(p.suffix not in ('.fbx', '.glb') for p in step.inputs)
        assert REGION / 'layout.py' not in step.inputs


def test_normal_city_producer_requires_the_new_data_owner(tmp_path):
    from test_volcano_layers import RECIPE
    steps = {step.name: step for step in RECIPE.world_steps(SimpleNamespace(out=tmp_path.resolve()))}
    assert 'hidamari.city_data' in steps['world.hidamari'].reads
    assert steps['world.hidamari.layout_data'].products[0].name == 'hidamari.city_data'
    for asset in ('HD_CivicGardens', 'HD_Streets', 'HD_PlazaShopApproaches', 'HD_Wires', 'HD_LaneEdges'):
        assert steps['world.hidamari.data.' + asset].reads == ['hidamari.city_data']


def test_complete_city_mesh_graph_has_separate_constructor_parameters_and_no_sibling_sources(tmp_path):
    spec = importlib.util.spec_from_file_location('hidamari_mesh_graph', GAME / 'hidamari_build.py')
    recipe = importlib.util.module_from_spec(spec); spec.loader.exec_module(recipe)
    out = tmp_path.resolve()
    steps = recipe.mesh_steps(SimpleNamespace(out=out))
    planners = {s.name.rsplit('.', 1)[-1]: s for s in steps if '.geometry.' in s.name}
    assert len(planners) == 86
    assert all(REGION / 'logical_catalogue.py' not in step.inputs for step in planners.values())
    assert all(s.cache and s.commands[0].factory_startup and s.commands[0].threads == 3 for s in planners.values())
    for key in ('HD_Shop_00', 'HD_Shop_01', 'HD_Boat'):
        step = planners[key]
        assert not step.needs and not step.reads
        assert REGION / 'logical' / (key + '.py') in step.inputs
        assert REGION / 'build.py' not in step.inputs
        assert REGION / 'layout.py' not in step.inputs
        assert out / 'heightmap.npy' not in step.inputs
        assert GAME / 'assets/hidamari/export-parameters' / (key + '.json') in step.inputs
        for sibling in set(planners) - {key}:
            assert REGION / 'logical' / (sibling + '.py') not in step.inputs
            assert GAME / 'assets/hidamari/export-parameters' / (sibling + '.json') not in step.inputs
    for key in recipe.DATA_ASSETS:
        assert 'hidamari.data.' + key in planners[key].reads
    for key, step in planners.items():
        query = out / 'hidamari/query-data' / (key + '.npz')
        assert next(p for p in step.products if p.name == 'hidamari.query.' + key).paths == (query,)
        assert '--query-output' in step.commands[0].args
    harbor = planners['HD_Harbor']
    assert next(p for p in harbor.products if p.name == 'hidamari.source.HD_Harbor').paths == (
        out / 'hidamari/source-data/HD_Harbor',)
    assert all('--source-output' not in step.commands[0].args for key, step in planners.items() if key != 'HD_Harbor')
    for key in ('HD_Terrain', 'HD_NorthMountains'):
        assert {p.name for p in planners[key].products} == {'hidamari.geometry.' + key,
            'hidamari.query.' + key,
            *('terrain.' + key + '.' + stage for stage in ('natural', 'final', 'provenance'))}
    check_modules(steps)
