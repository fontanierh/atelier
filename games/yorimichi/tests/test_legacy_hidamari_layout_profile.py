"""Original declaration/Graph observations only; no producer or native execution."""
from copy import deepcopy
from dataclasses import FrozenInstanceError, fields, replace
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest
from atelier import build, build_products, paths

@pytest.fixture(scope='module')
def profile():
    spec=importlib.util.spec_from_file_location('hidamari_layout_profile_test',paths.REPO/'games/yorimichi/legacy_hidamari_layout_profile.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

@pytest.fixture(scope='module')
def declarations(tmp_path_factory):
    from atelier.build_v2.controller_entry import declaration_context
    with pytest.MonkeyPatch.context() as patch:
        for name in ('ATELIER_CRATERPARK_V4_DESIGN','ATELIER_CRATERPARK_EDITOR_PARK','ATELIER_CRATERPARK_EDITOR_LINES'):patch.delenv(name,raising=False)
        recipe=build.load_recipe('yorimichi');out=tmp_path_factory.mktemp('city-profile').resolve()/'cold'
        ctx=declaration_context('yorimichi');ctx.out=out
        raw=next(s for s in recipe.world_steps(ctx) if s.name=='world.hidamari.layout_data')
        ctx=declaration_context('yorimichi');ctx.out=out;steps=recipe.steps(ctx);build.check_declarations(steps);graph=build_products.Graph(steps)
        full=next(s for s in graph.select([raw.name]) if s.name==raw.name)
    assert graph.owners['terrain.FarHills.final']=='world.farhills'
    assert graph.owners['treehouse.canopy_dimensions']=='world.treehouse_trees.data'
    assert not out.exists()
    return SimpleNamespace(root=out,raw=raw,enriched=full,recipe=recipe)

def qualify(profile,step,out,checkout=paths.REPO):
    return profile.qualify_hidamari_layout(step,checkout=checkout,output_root=out)

def rebound(step,out,checkout=None):
    original=step.products[0].paths[0].parents[1]
    def path(p):
        if p.is_relative_to(original):return out/p.relative_to(original)
        return checkout/p.relative_to(paths.REPO) if checkout is not None else p
    return replace(step,commands=[replace(step.commands[0],script=path(step.commands[0].script),args=('--output',str(out/'hidamari/layout-data.json')))],
        inputs=[path(p) for p in step.inputs],products=[replace(p,paths=tuple(path(x) for x in p.paths)) for p in step.products])

def finite_checkout(profile,step,tmp_path):
    import shutil
    observed=qualify(profile,step,step.products[0].paths[0].parents[1]);checkout=tmp_path.resolve()/'checkout'
    files=[*observed.code_inputs,paths.REPO/'games/yorimichi/build.py',paths.REPO/'games/yorimichi/hidamari_build.py',
        *(p for p in observed.raw_inputs if p.suffix in ('.json','.py'))]
    for source in dict.fromkeys(files):
        dest=checkout/source.relative_to(paths.REPO);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)
    for p in observed.raw_inputs:
        dest=checkout/p.relative_to(paths.REPO)
        if p.suffix=='.bin':dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(b'finite raw terrain fixture')
        elif p.name in ('geometry','collision','props'):dest.mkdir(parents=True,exist_ok=True)
    out=tmp_path.resolve()/'output';return checkout,rebound(step,out,checkout),out


@pytest.fixture(autouse=True)
def default_selection(craterpark_generator_by_choice, monkeypatch):
    for name in ('ATELIER_CRATERPARK_V4_DESIGN', 'ATELIER_CRATERPARK_EDITOR_PARK', 'ATELIER_CRATERPARK_EDITOR_LINES'):
        monkeypatch.delenv(name, raising=False)

@pytest.fixture(params=('raw', 'enriched'))
def stage(request):
    return request.param

def fresh(declarations, stage='raw'):
    return deepcopy(getattr(declarations, stage))

@pytest.mark.parametrize('field,value', [('cutoff', True), ('heavy', False), ('cache', False), ('audit', True),
    ('batch', build.Batch('other')), ('verify', lambda: True), ('replan', True), ('reads', ['other']),
    ('products', [build_products.Product('fake', (Path('/tmp/fake'),))]), ('cutoff', 1), ('heavy', 1)])
def test_exact_controls_refuse(profile, declarations, stage, field, value):
    with pytest.raises(profile.UnsupportedHidamariLayout, match='Step controls|product|named read'):
        qualify(profile, replace(fresh(declarations, stage), **{field: value}), declarations.root)

def test_private_metadata_refuses(profile, declarations, stage):
    step = fresh(declarations, stage)
    step.private_authority = True
    try:
        with pytest.raises(profile.UnsupportedHidamariLayout, match='Step controls|product|named read'):
            qualify(profile, step, declarations.root)
    finally:
        del step.private_authority

@pytest.mark.parametrize('change', ['partial', 'extra', 'order', 'duplicate', 'missing-raw'])
def test_only_two_exact_input_stages(profile, declarations, change):
    step = fresh(declarations, 'enriched')
    inputs = list(step.inputs)
    if change == 'partial':
        inputs.pop()
    elif change == 'extra':
        inputs.append(step.commands[0].script)
    elif change == 'order':
        inputs[-1], inputs[-2] = inputs[-2], inputs[-1]
    elif change == 'duplicate':
        inputs.insert(0, inputs[0])
    else:
        inputs.pop(3)
    with pytest.raises(profile.UnsupportedHidamariLayout, match='ordered inputs'):
        qualify(profile, replace(step, inputs=inputs), declarations.root)

def test_no_producer_selector_provenance_or_probe(profile, declarations, stage, monkeypatch):
    import shutil
    import subprocess
    import sys
    calls = []
    def forbidden(*args, **kwargs):
        calls.append('forbidden')
        raise AssertionError('executed a provider or probe')
    for name in ('editor_path', 'input_paths', 'editor_lines', 'selected', 'provenance', 'load_document'):
        monkeypatch.setattr(declarations.recipe.craterpark_v4, name, forbidden)
    monkeypatch.setattr(shutil, 'which', forbidden)
    monkeypatch.setattr(subprocess, 'run', forbidden)
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    import numpy as np
    from PIL import Image
    monkeypatch.setattr(np, 'save', forbidden)
    monkeypatch.setattr(Image, 'fromarray', forbidden)
    def trace(frame, event, arg):
        if event == 'call' and '/games/yorimichi/world/' in frame.f_code.co_filename:
            calls.append(frame.f_code.co_name)
        return trace
    previous = sys.gettrace()
    sys.settrace(trace)
    try:
        qualify(profile, fresh(declarations, stage), declarations.root)
    finally:
        sys.settrace(previous)
    assert calls == []

@pytest.mark.parametrize('name,value', [
    ('ATELIER_CRATERPARK_EDITOR_PARK', 'off'),
    ('ATELIER_CRATERPARK_EDITOR_PARK', '/foreign/park.json'),
    ('ATELIER_CRATERPARK_V4_DESIGN', '/foreign/design.json'),
    ('ATELIER_CRATERPARK_EDITOR_LINES', 'L1')])
def test_current_default_context_required(profile, declarations, monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(profile.UnsupportedHidamariLayout, match='context'):
        qualify(profile, fresh(declarations), declarations.root)

@pytest.mark.parametrize('field,value', [
    ('deferred_inputs', [Path('other')]), ('after', ['other']), ('pool_roots', [Path('other')]),
    ('explicit', True), ('references', ['other']), ('optional_inputs', [Path('other')]),
    ('queries', ['other']), ('toolchain', False), ('cook_recovery', 'other'),
    ('checkpoint_previous_needs', []), ('checkpoint_restore', lambda: None),
    ('checkpoint_outputs', (Path('other'),)), ('candidate_scope', 'other'),
    ('controller', 'other'), ('about', 'changed'), ('name', 'world.other'),
    ('inputs', ()), ('outputs', ())])
def test_remaining_exact_fields(profile, declarations, field, value):
    with pytest.raises(profile.UnsupportedHidamariLayout):
        qualify(profile, replace(fresh(declarations), **{field: value}), declarations.root)

@pytest.mark.parametrize('kind', ['step-subclass', 'command-subclass', 'missing-name', 'missing-command-field'])
def test_malformed_exact_types(profile, declarations, kind):
    step = fresh(declarations)
    if kind == 'step-subclass':
        class Foreign(type(step)):
            pass
        step = Foreign(**vars(step))
    elif kind == 'command-subclass':
        class Foreign(type(step.commands[0])):
            pass
        step.commands = [Foreign(**vars(step.commands[0]))]
    elif kind == 'missing-name':
        del step.name
    else:
        object.__delattr__(step.commands[0], 'script')
    with pytest.raises(profile.UnsupportedHidamariLayout):
        qualify(profile, step, declarations.root)

def test_full_returned_closure_checked(profile,declarations,monkeypatch):
    original=qualify(profile,fresh(declarations),declarations.root)
    scanner=build._FastImportScanner.__bases__[0]
    monkeypatch.setattr(scanner,'local_imports',lambda self,*args:list(original.code_inputs[:-1]))
    with pytest.raises(profile.UnsupportedHidamariLayout,match='sorted source closure differs'):
        qualify(profile,fresh(declarations),declarations.root)

def test_unknown_candidate_refuses_before_content(profile,declarations,tmp_path,monkeypatch):
    checkout,step,root=finite_checkout(profile,fresh(declarations),tmp_path)
    extra=checkout/'games/yorimichi/world/numpy.py';extra.write_text('raise AssertionError("never execute")\n')
    original=profile._read
    def reader(anchor,source):
        assert source!=extra
        return original(anchor,source)
    monkeypatch.setattr(profile,'_read',reader)
    with pytest.raises(profile.UnsupportedHidamariLayout,match='unknown source import target'):
        qualify(profile,step,root,checkout)



def test_actual_raw_and_full_graph_abi(profile,declarations,stage):
    step=fresh(declarations,stage);result=qualify(profile,step,declarations.root)
    assert tuple(f.name for f in fields(result))==('step','script','arguments','raw_inputs','produced_inputs','code_inputs','products')
    assert len(result.code_inputs)==71 and len(result.raw_inputs)==89
    assert declarations.raw.inputs==declarations.enriched.inputs and len(step.inputs)==94
    base=tuple(declarations.root/n for n in ('world.json','heightmap.npy','farhills.npy','megapark/trail.json','treehouse/trees/trees.json','terrain/FarHills/final.npz'))
    expected=base+((declarations.root/'treehouse-data/canopy/trees.json',) if stage=='enriched' else ())
    assert result.produced_inputs==expected
    assert result.raw_inputs==tuple(p for p in step.inputs if p not in expected)
    assert result.products==(('hidamari.city_data',(declarations.root/'hidamari/layout-data.json',)),)
    assert result.arguments==('--output',str(declarations.root/'hidamari/layout-data.json'))
    scanner=build._FastImportScanner.__bases__[0]();world=paths.REPO/'games/yorimichi/world'
    assert result.code_inputs==tuple(scanner.local_imports(result.script,(world,world/'regions',paths.STUDIO)))
    assert step.commands[0].env==(('PYTHONHASHSEED','0'),) and step.toolchain is True
    assert len(result.raw_inputs)>len(set(result.raw_inputs))  # Original duplicate roles preserved.
    assert not declarations.root.exists()
    with pytest.raises(FrozenInstanceError):result.step='other'


def test_warm_generated_never_offered_to_reader(profile,declarations,stage,tmp_path,monkeypatch):
    out=tmp_path.resolve()/'warm';step=rebound(fresh(declarations,stage),out)
    files={out/n:b'pre-existing generated bytes' for n in ('world.json','heightmap.npy','farhills.npy','megapark/trail.json','treehouse/trees/trees.json','terrain/FarHills/final.npz','treehouse-data/canopy/trees.json','hidamari/layout-data.json')}
    for p,data in files.items():p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    before={p:(p.read_bytes(),p.lstat()) for p in files};seen=[];original=profile._read
    def reader(anchor,p):
        assert not p.is_relative_to(out);seen.append(p);return original(anchor,p)
    monkeypatch.setattr(profile,'_read',reader);qualify(profile,step,out)
    assert seen and all((p.read_bytes(),p.lstat())==v for p,v in before.items())

@pytest.mark.parametrize('relative',['','games','games/yorimichi/world/regions/hidamari','platform/studio',
    'games/yorimichi/hidamari_build.py','games/yorimichi/build.py','games/yorimichi/world/regions/hidamari/layout_data.py',
    'games/yorimichi/world/regions/hidamari/location.json','games/yorimichi/assets/hidamari/props',
    'games/yorimichi/tools/craterpark_editor/data','games/yorimichi/world/terrain_product.py'])
def test_source_alias_negative_reaches_anchor(profile,declarations,tmp_path,monkeypatch,relative):
    checkout,step,out=finite_checkout(profile,fresh(declarations),tmp_path);qualify(profile,step,out,checkout)
    target=checkout/relative;foreign=tmp_path.resolve()/'foreign';target.rename(foreign);target.symlink_to(foreign,target_is_directory=foreign.is_dir())
    seen=[];original=profile._role
    def role(anchor,p,**kwargs):seen.append(p);return original(anchor,p,**kwargs)
    monkeypatch.setattr(profile,'_role',role)
    with pytest.raises(profile.UnsupportedHidamariLayout,match='input role'):qualify(profile,step,out,checkout)
    assert any(p==target or target in p.parents for p in seen) and not out.exists()

@pytest.mark.parametrize('relative',['','hidamari/layout-data.json','terrain/FarHills/final.npz','treehouse/trees/trees.json','treehouse-data/canopy/trees.json'])
def test_output_aliases_reached(profile,declarations,tmp_path,relative):
    out=tmp_path.resolve()/'output';foreign=tmp_path.resolve()/'foreign';foreign.mkdir();marker=foreign/'marker';marker.write_bytes(b'untouched')
    target=out/relative;target.parent.mkdir(parents=True,exist_ok=True);target.symlink_to(marker if target.suffix else foreign,target_is_directory=not target.suffix)
    before=(marker.read_bytes(),marker.stat())
    with pytest.raises(profile.UnsupportedHidamariLayout,match='output'):qualify(profile,rebound(fresh(declarations,'enriched'),out),out)
    assert (marker.read_bytes(),marker.stat())==before

@pytest.mark.parametrize('source,before,after',[
    ('games/yorimichi/hidamari_build.py','cache=True, toolchain=True, heavy=True','cache=False, toolchain=True, heavy=True'),
    ('games/yorimichi/build.py','if f not in step.inputs','if f in step.inputs'),
    ('games/yorimichi/world/regions/hidamari/layout_data.py','layout.generate()','layout.foreign()'),
    ('games/yorimichi/world/terrain_product.py','managed_temporary_parent(path)','path.parent')])
def test_source_constructor_changes_refuse(profile,declarations,tmp_path,source,before,after):
    checkout,step,out=finite_checkout(profile,fresh(declarations),tmp_path);p=checkout/source;s=p.read_text();assert before in s;p.write_text(s.replace(before,after))
    with pytest.raises(profile.UnsupportedHidamariLayout,match='source'):qualify(profile,step,out,checkout)

@pytest.mark.parametrize('field,value',[('env',()),('env',(('PYTHONHASHSEED','1'),)),('threads',True),('threads',1),('factory_startup',False),('args',())])
def test_exact_native_settings(profile,declarations,field,value):
    step=fresh(declarations);step.commands=[replace(step.commands[0],**{field:value})]
    with pytest.raises(profile.UnsupportedHidamariLayout,match='Blender'):qualify(profile,step,declarations.root)

@pytest.mark.parametrize('reads',[[],['treehouse.canopy_dimensions'],['treehouse.canopy_dimensions','terrain.FarHills.final'],['terrain.FarHills.final','terrain.FarHills.final']])
def test_exact_named_read_roles(profile,declarations,reads):
    with pytest.raises(profile.UnsupportedHidamariLayout,match='named reads'):qualify(profile,replace(fresh(declarations),reads=reads),declarations.root)
