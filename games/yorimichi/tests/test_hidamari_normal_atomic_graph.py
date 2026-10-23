"""The actual city recipe has no whole export or query/cut dependency cycle."""
import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier.build import Blender, Python, check_modules
from test_volcano_layers import RECIPE

GAME = Path(__file__).resolve().parents[1]


def test_normal_city_exports_and_ferry_cut_have_explicit_independent_direction(tmp_path):
    ctx = SimpleNamespace(out=tmp_path.resolve(),game='yorimichi',uproject=None)
    steps = {step.name:step for step in RECIPE.steps(ctx)}
    check_modules(list(steps.values()))
    city = steps['world.hidamari']
    assert isinstance(city.commands[0],Python) and city.cache
    assert len([key for key in city.reads if key.startswith('hidamari.geometry.')])==86
    planners = {key:step for key,step in steps.items() if key.startswith('world.hidamari.geometry.')}
    assert len(planners)==86 and all(step.cache for step in planners.values())
    assert all(step.commands[0].factory_startup and step.commands[0].threads==3 for step in planners.values())
    assert all(command.script!=GAME/'world/regions/hidamari/build.py'
               for step in steps.values() for command in step.commands if isinstance(command,Blender))
    probes = steps['world.ferry_probes']
    assert 'hidamari.query.HD_Harbor.raw' in probes.reads and 'hidamari.query.HD_Harbor' not in probes.reads
    assert 'brinecove.query_data' in probes.reads and 'brinecove.clearance' not in probes.reads
    assert 'world.hidamari.city' not in probes.needs
    assert len([key for key in probes.reads if key.startswith('hidamari.query.')])==86
    assert isinstance(steps['world.hidamari_ferry_cut'].commands[0],RECIPE.Call)
    assembly = steps['world.city_tiles']
    assert assembly.cache and isinstance(assembly.commands[0],Python)
    assert 'hidamari.atomic' in assembly.reads and 'city.atomic_manifest' in {p.name for p in assembly.products}
    assert 'city.atomic_manifest' in steps['world.city_trees'].reads
    assert not any(command.script==GAME/'world/city_tree_lods.py'
                   for step in steps.values() for command in step.commands if isinstance(command,Blender))
    # Follow actual data dependencies as well as explicit predecessor names.
    producers = {product.name:step.name for step in steps.values() for product in step.products}
    done,active = set(),set()
    def visit(key):
        if key not in steps or key in done:return
        assert key not in active, 'City/ferry cycle at '+key
        active.add(key);step=steps[key]
        for predecessor in [*step.needs,*step.after,*(producers[name] for name in step.reads if name in producers)]:
            visit(predecessor)
        active.remove(key);done.add(key)
    for key in steps:visit(key)


def metadata(tmp_path,monkeypatch):
    monkeypatch.syspath_prepend(str(GAME));monkeypatch.syspath_prepend(str(GAME/'world'))
    module = importlib.import_module('hidamari_metadata')
    city = tmp_path/'hidamari';city.mkdir()
    (city/'layout-data.json').write_text(json.dumps(dict(instances={'HD_Station':[[1,2,3,4,1]]})))
    (city/'north_snow.json').write_text(json.dumps(dict(south_join_m=55)))
    for key in module.ASSETS:
        folder = tmp_path/'planned_exports/hidamari'/key;folder.mkdir(parents=True)
        (folder/'plan.json').write_text(json.dumps(dict(schema=1,complete=True,parent=key,
            source_triangles=2,source_collision_hulls=0,slots=['HDS_road'],
            pieces=[dict(triangles=2,min=[0,0,0],max=[1,1,1])])) )
    return module,city


def test_material_projection_stops_geometry_changes_but_keeps_current_slot_membership(tmp_path,monkeypatch):
    module,city = metadata(tmp_path,monkeypatch)
    module.assemble(tmp_path,lambda _:None)
    before = module.material_inputs(tmp_path,False)
    placement = (city/'city.json').read_bytes()
    path = tmp_path/'planned_exports/hidamari/HD_Station/plan.json'
    value = json.loads(path.read_text());value['pieces'][0]['max']=[2,2,2];value['source_triangles']=3;value['pieces'][0]['triangles']=3
    path.write_text(json.dumps(value));module.assemble(tmp_path,lambda _:None)
    assert module.material_inputs(tmp_path,False)==before and (city/'city.json').read_bytes()==placement
    value['slots']=['HDS_paint'];path.write_text(json.dumps(value));module.assemble(tmp_path,lambda _:None)
    assert module.material_inputs(tmp_path,False)!=before
    assert not (city/'assets').exists()


def test_metadata_preflights_all_destinations_before_any_write(tmp_path,monkeypatch):
    module,city = metadata(tmp_path,monkeypatch)
    outside = tmp_path/'outside.json';outside.write_text('keep')
    (city/'manifest.json').symlink_to(outside)
    with pytest.raises(ValueError,match='regular'):module.assemble(tmp_path)
    assert outside.read_text()=='keep' and not (city/'city.json').exists()
