"""Cold graph expansion, conserved park source packets and native retirement boundaries."""
import importlib.util
import io
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace

import numpy as np
import pytest

GAME = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(GAME / 'world'), str(GAME / 'world/regions')]
from craterpark.v2 import atomic_inputs, dsl  # noqa: E402


def module(label, path):
    spec = importlib.util.spec_from_file_location(label, path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


def source_geometry(path, *, change=0):
    # Two distinct finished logical riding tiles, plus an ordered collision owner.
    vertices = np.asarray([[0,0,0],[0,0,1],[1,0,0]], 'f8')
    faces = np.asarray([[0,1,2]])
    arrays = {}
    index = dict(render=[], collision=[dict(name='UC_CP_Riding', role='riding')], rails=[])
    for i in range(2):
        mesh = dsl.Mesh(vertices + [i * 128, change if i == 0 else 0, 0], faces,
                        np.asarray([[0,1,0]] * 3), np.asarray([[0,0],[0,1],[1,0]]),
                        np.asarray([.2,.4,.8]), np.zeros(1,'i4'), np.zeros(1,'i4'), np.zeros(1,'i4'), ('ramp',))
        arrays.update(mesh.to_arrays(f'r{i}_'))
        index['render'].append(dict(name=f'SM_CP_Tile{i}', role='riding'))
    arrays['c0'] = np.repeat(vertices[faces], 32770, axis=0)
    arrays['index'] = np.asarray(json.dumps(index))
    np.savez(path, **arrays)


@pytest.fixture
def old_selection(monkeypatch):
    monkeypatch.setenv('ATELIER_CRATERPARK_EDITOR_PARK', 'off')
    monkeypatch.delenv('ATELIER_CRATERPARK_V4_DESIGN', raising=False)


def test_projection_conserves_channels_collision_order_and_one_edit_locality(tmp_path, old_selection):
    root = tmp_path.resolve(); source = root / 'geometry.npz'
    source_geometry(source)
    output = root / 'inputs'
    value = atomic_inputs.project(source, output)
    assert len(value['assets']) == 5  # two render, two bounded collision, seed
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in output.glob('*.npz')}
    source_geometry(source, change=.25)
    atomic_inputs.project(source, output)
    changed = [p.name for p in output.glob('*.npz') if before[p.name] != (p.read_bytes(),p.stat().st_mtime_ns)]
    assert changed == ['SM_CP_Tile0.npz']
    with np.load(source) as data, np.load(output/'SM_CP_Tile1.npz') as packet:
        for key, expected in dsl.Mesh.from_arrays(data, 'r1_').to_arrays('m_').items():
            assert np.array_equal(packet[key], expected)
    with np.load(source) as data, np.load(output/'UC_CP_Riding_Piece000.npz') as first, \
            np.load(output/'UC_CP_Riding_Piece001.npz') as second:
        assert len(first['triangles']) == 32768 and len(second['triangles']) == 2
        assert np.array_equal(np.concatenate([first['triangles'],second['triangles']]), data['c0'])
        assert np.array_equal(first['native_origin'], second['native_origin'])
        assert np.array_equal(first['native_origin'], atomic_inputs.export.origin_of(data['c0'].reshape(-1,3)))


def test_projection_link_refusal_precedes_any_write(tmp_path, old_selection):
    root = tmp_path.resolve(); source = root/'geometry.npz'; source_geometry(source)
    output = root/'inputs'; atomic_inputs.project(source,output)
    external = root/'external'; external.write_bytes(b'private')
    (output/'SM_CP_Tile0.npz').unlink(); (output/'SM_CP_Tile0.npz').symlink_to(external)
    before = (output/'SM_CP_Tile1.npz').read_bytes()
    with pytest.raises(ValueError):
        atomic_inputs.project(source,output)
    assert external.read_bytes() == b'private'
    assert (output/'SM_CP_Tile1.npz').read_bytes() == before


def test_real_cold_controller_projects_then_reloads_before_assembly(tmp_path, monkeypatch, old_selection):
    from atelier import build, build_checkpoints, paths
    from atelier.build import Call, Product, Step
    hook = module('crater_atomic_cold', GAME/'craterpark_atomic_build.py')
    root = tmp_path.resolve(); (root/'uv.lock').write_text('fixture')
    monkeypatch.setattr(paths,'REPO',root); monkeypatch.setattr(paths,'build_root',lambda:root/'build')
    monkeypatch.setattr(build_checkpoints,'configured',lambda ctx:None)
    monkeypatch.setenv('ATELIER_CACHE',str(root/'cache'))
    out = root/'build/fixture'; source = root/'geometry.npz'; source_geometry(source)
    ctx = SimpleNamespace(game='fixture',out=out,logs=out/'logs',stamps=out/'stamps',cook_mode=build.CookMode.DEFAULT)
    monkeypatch.setattr(build,'Context',lambda *a,**kw:ctx)
    trace=[]
    original_load=hook.load
    def load(label,path):
        if path.name != 'region_exports.py':
            return original_load(label,path)
        def graph(ctx,region,assets,after):
            assert len(assets)==5
            exports=[]; reads=[]
            for asset in assets:
                target=ctx.out/'test-exports'/(asset.key+'.bin')
                def export(ctx,log,asset=asset,target=target):
                    trace.append(asset.key)
                    target.parent.mkdir(parents=True,exist_ok=True)
                    target.write_bytes(Path(asset.inputs[0]).read_bytes())
                product='test.export.'+asset.key; reads.append(product)
                exports.append(Step('world.craterpark.export.'+asset.key,[Call('observed isolated export',export)],
                    inputs=list(asset.inputs),after=after,products=[Product(product,(target,))]))
            destination=ctx.out/'atomic_regions/craterpark'
            def complete(ctx,log):
                trace.append('children')
                destination.mkdir(parents=True,exist_ok=True)
                (destination/'manifest.json').write_text('validated children')
            return exports+[Step('world.craterpark.assembled',[Call('observed child graph',complete)],
                         needs=after,reads=reads,products=[Product('craterpark.atomic',(destination,))])]
        return SimpleNamespace(LogicalAsset=lambda *a,**kw:SimpleNamespace(key=a[0],**kw),steps=graph)
    monkeypatch.setattr(hook,'load',load)
    def recipe(ctx):
        def geometry(ctx,log):
            trace.append('geometry'); target=out/'craterpark/v2/geometry.npz'
            target.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(source,target)
        steps=[Step('world.craterpark_geometry',[Call('course',geometry)],inputs=[source],
                    outputs=[out/'craterpark/v2/geometry.npz'])]
        steps.extend(hook.steps(ctx))
        for step in steps:
            if step.name=='world.craterpark.inputs':
                def project(ctx,log):
                    trace.append('projection'); atomic_inputs.project(out/'craterpark/v2/geometry.npz',out/'craterpark-inputs')
                step.commands=[Call('canonical projection',project)]
                step.cache=False
            elif step.name=='world.craterpark' and step.reads:
                def assemble(ctx,log):
                    trace.append('assembly')
                    for path in step.products[0].paths:
                        if path.suffix:
                            path.parent.mkdir(parents=True,exist_ok=True);path.write_text('complete')
                        else:
                            path.mkdir(parents=True,exist_ok=True);(path/'manifest.json').write_text('complete')
                # Include actual projected metadata products without Blender for this graph-only regression.
                step.reads=['craterpark.atomic','craterpark.source_inputs']
                step.commands=[Call('placement assembly',assemble)]
                step.cache=False
        return steps
    monkeypatch.setattr(build,'load_recipe',lambda game:SimpleNamespace(steps=recipe))
    assert build.build('fixture',['world.craterpark'])==0
    assert trace[:2]==['geometry','projection']
    assert set(trace[2:-2])=={'SM_CP_Tile0','SM_CP_Tile1','UC_CP_Riding_Piece000','UC_CP_Riding_Piece001','SM_CP_ImportSeed'}
    assert trace[-2:]==['children','assembly']
    trace.clear()
    source_geometry(source,change=.5)
    assert build.build('fixture',['world.craterpark'])==0
    assert trace==['geometry','projection','SM_CP_Tile0','children','assembly']


class Editor:
    def __init__(self,content,names,refs=None):
        self.content=content;self.names=set(names);self.refs=refs or {};self.deleted=[]
        for package in names:
            path=content/(package[6:]+'.uasset');path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'asset')
    def list_assets(self,destination,**kw):
        return [p+'.'+p.rsplit('/',1)[-1] for p in sorted(self.names) if p.startswith(destination+'/')]
    def does_asset_exist(self,p):return p in self.names
    def find_package_referencers_for_asset(self,p,**kw):return self.refs.get(p,[])
    def delete_asset(self,p):
        self.deleted.append(p);self.names.remove(p);(self.content/(p[6:]+'.uasset')).unlink();return True


def test_combined_native_retirement_refuses_all_then_retires_and_repeats(tmp_path):
    native=module('park_atomic_native_test',GAME/'unreal/Scripts/park_atomic_native.py')
    destination='/Game/CraterPark/Meshes/'
    names={destination+n for n in ('SM_CP_Parent','UC_CP_Old','SM_CP_Current','UC_CP_Current')}
    editor=Editor(tmp_path.resolve(),names,{destination+'UC_CP_Old':['/Game/Foreign']})
    previous=native.inventory(editor,'/Game/CraterPark','CP')
    report=dict(render=[dict(name='SM_CP_Current')],collision=[dict(name='UC_CP_Current')])
    with pytest.raises(ValueError,match='external references'):
        native.retire(editor,previous,report,'/Game/CraterPark','CP',tmp_path.resolve())
    assert editor.deleted==[]
    editor.refs={}
    retired=native.retire(editor,previous,report,'/Game/CraterPark','CP',tmp_path.resolve())
    assert set(retired)=={destination+'SM_CP_Parent',destination+'UC_CP_Old'}
    assert native.retire(editor,native.inventory(editor,'/Game/CraterPark','CP'),report,
                         '/Game/CraterPark','CP',tmp_path.resolve())==[]


def test_native_reuse_admission_precedes_owner_mutation_and_preserves_policy():
    import ast
    path=GAME/'unreal/Scripts/import_megapark.py'
    tree=ast.parse(path.read_text()); function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='import_mesh')
    calls=[]; packets=[]
    class Reuse:
        def imported(self,package):calls.append(('imported',package))
        def defer_validated(self,package):calls.append(('defer',package))
    reuse=Reuse(); mesh=object(); hit=[True]
    def admit(*args,**kwargs):
        calls.append('admit');packets.append((kwargs['functions'],kwargs['validation_functions']))
        return (mesh if hit[0] else None),reuse
    def raw(*args):calls.append('raw');return mesh
    namespace=dict(Path=Path,__file__=str(path),ROOT='/Game/MegaPark',common_fbx_mesh=admit,
                   _park_options_match=lambda mesh:True,_source_mesh=raw,
                   _finish_mesh=lambda mesh:calls.append('finish'))
    exec(compile(ast.Module(body=[function],type_ignores=[]),str(path),'exec'),namespace)
    assert namespace['import_mesh'](Path('one.fbx'),'SM_MP_One') is mesh
    assert calls==['admit','finish',('defer','/Game/MegaPark/Meshes/SM_MP_One')]
    calls.clear();hit[0]=False
    assert namespace['import_mesh'](Path('two.fbx'),'SM_CP_Two',vertex_colors=True) is mesh
    assert calls==['admit','raw',('imported','/Game/MegaPark/Meshes/SM_CP_Two'),'finish',
                   ('defer','/Game/MegaPark/Meshes/SM_CP_Two')]
    assert packets==[(('_source_mesh',),('_park_options_match',))]*2


def test_native_raw_and_validator_closures_are_supported_without_exemptions():
    from atelier.mesh_reuse import native_policy
    path=GAME/'unreal/Scripts/import_megapark.py'
    assert native_policy(path.read_text(),('_source_mesh',),path)
    assert native_policy(path.read_text(),('_park_options_match',),path)
