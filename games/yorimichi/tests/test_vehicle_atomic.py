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
