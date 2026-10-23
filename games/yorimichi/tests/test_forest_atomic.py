"""The forest remains eight separately cached species with five authored levels each."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import pytest

GAME=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(GAME/'world'),str(GAME/'world/regions')]
from forest.specs import TUSCAN,FOREST  # noqa: E402
from forest_parameters import load  # noqa: E402


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def test_complete_species_parameters_match_immutable_placement_species():
    root=GAME/'assets/forest/export-parameters'
    assert {p.stem for p in root.glob('*.json')}==set(TUSCAN|FOREST)
    for name,args in (TUSCAN|FOREST).items():
        assert load(root/(name+'.json'))==(name,list(args))


def test_forest_every_level_has_own_constructor_export_and_complete_data_inputs(tmp_path):
    helper=module('forest_atomic_recipe',GAME/'forest_atomic_build.py')
    ctx=SimpleNamespace(out=tmp_path.resolve())
    steps=helper.steps(ctx)
    planners=[s for s in steps if s.name.startswith('world.forest.geometry.')]
    bakes=[s for s in steps if s.name.startswith('world.forest.impostor.')]
    assert len(planners)==40 and len(bakes)==8
    for step in planners:
        command=step.commands[0]
        assert command.factory_startup and command.threads==3 and step.cache and step.products
        files=[p for p in step.inputs if p.parent.name=='export-parameters']
        assert len(files)==1
        name=files[0].stem
        logical=step.name.rsplit('.',1)[-1]
        assert logical==name or logical in [name+f'_LOD{i}' for i in range(1,5)]
        assert not any('exports' in str(p.parts) for p in step.inputs if isinstance(p,Path))
        if logical==name:
            assert not step.reads
        else:
            assert 'forest.record.'+name in step.reads
        if logical.endswith('_LOD3'):
            assert 'forest.impostor_views.'+name in step.reads
    final=next(s for s in steps if s.name=='world.forest')
    assert final.cache and len(final.reads)==49
    assert {p.name for p in final.products}=={'forest.library','forest.mesh_files','forest.manifest'}


@pytest.mark.parametrize('mutation',[{'name':'Tree_Forest_Bad/escape'},{'args':['oak',True,10,10,'LeafSmall']},
                                    {'args':['oak',1,float('nan'),10,'LeafSmall']}])
def test_invalid_selected_forest_parameters_refuse(tmp_path,mutation):
    path=tmp_path/'Tree_Forest_Bad.json'
    value=dict(schema=1,name=path.stem,args=['oak',1,10,10,'LeafSmall']);value.update(mutation)
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError):load(path)


def test_forest_current_import_keeps_source_products_immutable_and_uniform_policy():
    text=(GAME/'unreal/Scripts/import_forest.py').read_text()
    assert "first=trees['Tree_Tuscan_Cypress']" in text
    assert "output/'import-report.json'" not in text and "output/'import.json'" not in text
    assert text.count('reuse_validator=forest_native.reusable_collision')==2
    assert 'before_import=lambda' in text and 'mesh.set_num_source_models(1)' in text
