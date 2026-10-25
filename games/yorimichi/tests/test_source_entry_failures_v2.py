"""Reached cold-source entrypoints and complete offline restyle declarations."""
import ast
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

from atelier.build import Python, Step
from atelier.build_v2 import recipe_dependencies

GAME=Path(__file__).resolve().parents[1]
CHECKOUT=GAME.parents[1]


def tool():
    path=GAME/'tools/megapark_textures.py'
    spec=importlib.util.spec_from_file_location('megapark_finish_inputs_test',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_hippodrome_reached_entries_import_without_inherited_package_path(tmp_path):
    folder=GAME/'world/regions/hippodrome'
    scripts=sorted(folder.glob('plan_*.py'))+[folder/'project_queries.py',folder/'venue_data.py',folder/'atomic.py']
    program='import runpy\nfor path in '+repr(list(map(str,scripts)))+':\n runpy.run_path(path,run_name="source_import_check")\n'
    result=subprocess.run([sys.executable,'-B','-c',program],cwd=tmp_path,
                          env={**os.environ,'PYTHONPATH':''},capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stderr


def test_megapark_actual_constructor_captures_complete_offline_inputs_and_outputs():
    module=tool()
    tree=ast.parse((GAME/'build.py').read_text())
    call=next(n for n in ast.walk(tree)if isinstance(n,ast.Call)and isinstance(n.func,ast.Name)
              and n.func.id=='Step'and n.args and isinstance(n.args[0],ast.Constant)
              and n.args[0].value=='world.megapark_restyle')
    out=CHECKOUT/'build/yorimichi'
    step=eval(compile(ast.Expression(call),str(GAME/'build.py'),'eval'),
              {'Step':Step,'Python':Python,'TOOLS':GAME/'tools','out':out,
               '_load_helper_module':lambda name,path:module})
    assert step.outputs==[out/'megapark/textures',out/'megapark/lettering/NotoSansJP-Black.ttf']
    assert GAME/'world/yori.py'in step.inputs
    assert all(path.is_file()or path==module.PAINTED for path in step.inputs)
    rows=recipe_dependencies.extract([step],checkout=CHECKOUT,build_root=CHECKOUT/'build')
    assert 'games/yorimichi/world/yori.py'in rows[0]['code']
    assert 'games/yorimichi/world/regions/megapark/placement.py'in rows[0]['code']
    records=json.loads((module.SOURCE/'map.json').read_text())
    expected=set(module.RECOLOUR)
    expected.update(tid for tid,(slug,how)in module.SIGNS.items()
                    if all((module.PAINTED/(name+'.jpg')).is_file()
                           for name in [slug]+(['waves']if how!='fit'else[])))
    expected.update(p['retail_texture_ids']['lightmap']for m in records['models']for p in m['meshes']
                    if 'lightmap'in p.get('retail_texture_ids',{})
                    and p['retail_texture_ids']['lightmap']in records['textures'])
    assert {module.SOURCE/records['textures'][tid]['png']for tid in expected}<=set(step.inputs)


def test_encoded_plan_verifier_binds_without_home_or_build_controller_imports(tmp_path):
    from types import SimpleNamespace
    import region_exports
    step=region_exports.steps(SimpleNamespace(out=CHECKOUT/'build/verifier-home-test'),region='hippodrome',assets=[
        region_exports.LogicalAsset('SM_HD_FinishPost',GAME/'world/regions/hippodrome/plan_finish_post.py',
                                    suffix='.glb',encoding='encoded_glb')])[0]
    row=recipe_dependencies.extract([step],checkout=CHECKOUT,build_root=CHECKOUT/'build')[0]
    program='''
import json,sys
from pathlib import Path
from atelier.build_v2.recipe_job import bind
value=json.load(sys.stdin)
def no_home(cls):raise AssertionError('a source verifier may not load machine/home controls')
Path.home=classmethod(no_home)
assert bind(value['binding'],Path(value['view']))() is False
assert 'atelier.build' not in sys.modules
'''
    result=subprocess.run([sys.executable,'-B','-c',program],input=json.dumps({'binding':row['verify'],'view':str(CHECKOUT)}),
                          cwd=tmp_path,env={k:v for k,v in os.environ.items()if k not in ('HOME','PYTHONPATH')},
                          capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stdout+result.stderr
