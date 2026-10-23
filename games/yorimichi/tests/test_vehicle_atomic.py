"""Vehicle source isolation and independent cached export ownership."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from atelier.build import check_modules

GAME=Path(__file__).resolve().parents[1]


def load(key,path):
    spec=importlib.util.spec_from_file_location(key,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def test_sailboat_selected_function_edit_changes_only_one_source_product(tmp_path):
    sources=load('vehicle_sources_test',GAME/'world/vehicle_sources.py')
    text=(GAME/'assets/vehicles/sailboat/build.py').read_text()
    original=sources.projection(text,'sailboat')
    edited=sources.projection(text.replace("(.02,0,-.03),(-2.22,0,-.03)","(.02,0,-.03),(-2.24,0,-.03)"),'sailboat')
    assert {key for key in original if original[key]!=edited[key]}=={'SB_Boom'}
    assert set(original)=={'SB_Hull','SB_Sail','SB_Boom','SB_Rudder','SB_Wake'}
    for key,row in original.items():
        assert 'def main' not in row['program'] and 'export(' not in row['program']
        assert 'OUT' not in row['program']
    sources.publish('sailboat',tmp_path.resolve())
    assert {path.stem for path in tmp_path.iterdir()}==set(original)
    assert all(json.loads((tmp_path/(key+'.json')).read_text())==row for key,row in original.items())


def test_complete_sailboat_recipe_has_independent_factory_plans_and_no_native_report_overlap(tmp_path):
    recipe=load('vehicle_recipe_test',GAME/'vehicle_atomic_build.py')
    steps=recipe.steps(SimpleNamespace(out=tmp_path.resolve()),'sailboat')
    plans=[step for step in steps if step.name.startswith('world.vehicle_sailboat.geometry.')]
    assert len(plans)==5
    for step in plans:
        key=step.name.rsplit('.',1)[1]
        assert step.cache and step.commands[0].factory_startup and step.commands[0].threads==3
        assert step.reads==['vehicle_sailboat.source.'+key]
        assert step.products[1].name=='vehicle_sailboat.report.'+key
    assembled=next(step for step in steps if step.name=='world.sailboat')
    assert assembled.products[0].paths==(tmp_path/'sailboat/assets',tmp_path/'sailboat/manifest.json')
    assert not any('export' in product for step in plans for product in step.reads)
    check_modules(steps)


def test_selected_part_cannot_invoke_a_sibling_constructor():
    sources=load('vehicle_sibling_refusal',GAME/'world/vehicle_sources.py')
    text=(GAME/'assets/vehicles/sailboat/build.py').read_text().replace("m=v.Mesh('SB_Boom')","m=hull()")
    with pytest.raises(ValueError,match='sibling'):sources.projection(text,'sailboat')


def test_kei_pickup_crate_edit_does_not_change_other_selected_variants(tmp_path):
    sources=load('kei_source_projection',GAME/'world/vehicle_sources.py')
    text=(GAME/'assets/vehicles/kei/build.py').read_text()
    original=sources.projection(text,'kei');edited=sources.projection(text.replace('(.56, .46, .36)','(.58, .46, .36)'),'kei')
    assert {key for key in original if original[key]!=edited[key]}=={'SM_Kei_Pickup'}
    assert len(original)==4
    recipe=load('kei_atomic_recipe_test',GAME/'vehicle_atomic_build.py')
    plans=[step for step in recipe.steps(SimpleNamespace(out=tmp_path.resolve()),'kei')
           if step.name.startswith('world.vehicle_kei.geometry.')]
    assert len(plans)==4 and all(step.cache and step.commands[0].factory_startup for step in plans)


def test_kart_geometry_reads_only_selected_cockpit_fields_and_keeps_full_layout_separate(tmp_path):
    sources=load('kart_source_projection',GAME/'world/vehicle_sources.py')
    text=(GAME/'assets/vehicles/kart/build.py').read_text();layout=sources.cockpit_layout()
    original=sources.projection(text,'kart',layout=layout)
    changed=dict(layout,wheel_width=layout['wheel_width']+.01)
    edited=sources.projection(text,'kart',layout=changed)
    assert {key for key in original if original[key]!=edited[key]}=={'SM_Kart_Wheel'}
    assert original['SM_Kart_Seat']['data']=={'layout':{}}
    assert set(original['SM_Kart_Body']['data']['layout'])=={'body_half_extents','wheel_radius'}
    for row in original.values():assert 'def winding_selftest' in row['program'] and 'def geometry_hash' in row['program']
    output=tmp_path/'sources';cockpit=tmp_path/'kart/cockpit.json'
    sources.publish('kart',output.resolve(),layout_output=cockpit.resolve())
    assert json.loads(cockpit.read_text())==layout
    recipe=load('kart_atomic_recipe_test',GAME/'vehicle_atomic_build.py')
    steps=recipe.steps(SimpleNamespace(out=tmp_path.resolve()),'kart')
    assert steps[0].products[-1].name=='vehicle_kart.cockpit'
    assert 'vehicle_kart.cockpit' in steps[-1].reads


def test_bike_semantic_leaf_projections_keep_basket_geometry_independent(tmp_path):
    sources=load('bike_source_projection',GAME/'world/vehicle_sources.py')
    text=(GAME/'assets/vehicles/bike/build.py').read_text()
    original=sources.projection(text,'bike')
    changed=sources.projection(text.replace('13, 3, 4, 40','14, 3, 4, 40'),'bike')
    assert {key for key in original if original[key]!=changed[key]}=={'BK_Steer_BasketShell'}
    changed=sources.projection(text.replace('m.tube(rim + [rim[0]], .0085','m.tube(rim + [rim[0]], .0086'),'bike')
    assert {key for key in original if original[key]!=changed[key]}=={'BK_Steer_BasketRim'}
    assert len(original)==11 and 'BK_Steer' not in original
    for row in original.values():
        assert 'def parts(' not in row['program'] and 'def steer(' not in row['program'] and 'def basket(' not in row['program']
    layout=tmp_path/'layout-source.json'
    sources.publish('bike',(tmp_path/'sources').resolve(),layout_output=layout.resolve())
    program=json.loads(layout.read_text())['program']
    assert 'def layout(' in program and 'class Mesh' not in program
    recipe=load('bike_atomic_recipe',GAME/'vehicle_atomic_build.py')
    steps=recipe.steps(SimpleNamespace(out=tmp_path.resolve()),'bike')
    plans=[step for step in steps if step.name.startswith('world.vehicle_bike.geometry.')]
    assert len(plans)==11 and all(step.cache and step.commands[0].factory_startup for step in plans)
    data=next(step for step in steps if step.name=='world.bike.layout')
    assert data.reads==['vehicle_bike.layout_source'] and data.commands[0].threads==3
    assert 'vehicle_bike.layout' in steps[-1].reads
    check_modules(steps)
