"""Finite metadata checks for the actual original five city projections."""
from copy import deepcopy
from dataclasses import replace
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from atelier import build, build_products, paths


@pytest.fixture(scope='module')
def profile():
    spec = importlib.util.spec_from_file_location('city_projection_observer',
        paths.REPO/'games/yorimichi/legacy_hidamari_projection_profile.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def declarations(tmp_path_factory):
    from atelier.build_v2.controller_entry import declaration_context
    recipe = build.load_recipe('yorimichi')
    ctx = declaration_context('yorimichi'); ctx.out = tmp_path_factory.mktemp('city-projections')/'cold'
    raw = {s.name: s for s in recipe.world_steps(ctx) if s.name.startswith('world.hidamari.data.')}
    steps = recipe.steps(ctx); build.check_declarations(steps); graph = build_products.Graph(steps)
    full = {name: graph.by_name[name] for name in raw}
    assert graph.owners['hidamari.city_data'] == 'world.hidamari.layout_data'
    assert not ctx.out.exists()
    return SimpleNamespace(raw=raw, full=full, output=ctx.out)


@pytest.mark.parametrize('stage', ['raw', 'full'])
@pytest.mark.parametrize('asset', ['HD_CivicGardens','HD_Streets','HD_PlazaShopApproaches','HD_Wires','HD_LaneEdges'])
def test_all_actual_original_projection_stages(profile, declarations, stage, asset):
    step = getattr(declarations, stage)['world.hidamari.data.'+asset]
    result = profile.qualify_hidamari_projection(step, checkout=paths.REPO, output_root=declarations.output)
    assert result.step == step.name and result.arguments == step.commands[0].args
    assert len(result.code_inputs) == 7 and result.raw_inputs == result.code_inputs
    assert result.produced_inputs == (declarations.output/'hidamari/layout-data.json',)
    assert result.products == (('hidamari.data.'+asset,
        (declarations.output/'hidamari/constructor-data'/(asset+'.json'),)),)
    assert not declarations.output.exists()


@pytest.mark.parametrize('field,value', [('cache',False),('cache',1),('heavy',True),('replan',True),
    ('audit',True),('toolchain',True),('cutoff',True),('batch',build.Batch('fake')),
    ('needs',['unrelated']),('after',['other']),('reads',[]),('controller','foreign')])
def test_exact_controls(profile,declarations,field,value):
    step = deepcopy(next(iter(declarations.raw.values())))
    setattr(step,field,value)
    with pytest.raises(profile.UnsupportedHidamariProjection):
        profile.qualify_hidamari_projection(step,checkout=paths.REPO,output_root=declarations.output)


@pytest.mark.parametrize('change',['extra','reverse','duplicate','missing','argv','product','private'])
def test_exact_roles(profile,declarations,change):
    step = deepcopy(next(iter(declarations.full.values())))
    if change=='extra':step.inputs.append(step.inputs[0].parent/'foreign.py')
    elif change=='reverse':step.inputs.reverse()
    elif change=='duplicate':step.inputs.append(step.inputs[-1])
    elif change=='missing':step.inputs.pop()
    elif change=='argv':step.commands[0]=replace(step.commands[0],args=step.commands[0].args+('--extra',))
    elif change=='product':step.products=[build.Product('fake',(declarations.output/'fake',))]
    else:step.permission=True
    with pytest.raises(profile.UnsupportedHidamariProjection):
        profile.qualify_hidamari_projection(step,checkout=paths.REPO,output_root=declarations.output)


def rebound(profile,declarations,tmp_path):
    checkout=tmp_path/'checkout'; out=tmp_path/'output'
    for name in (*profile.CODE,'games/yorimichi/hidamari_build.py'):
        target=checkout/name;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes((paths.REPO/name).read_bytes())
    original=deepcopy(next(iter(declarations.raw.values())))
    source=out/'hidamari/layout-data.json';output=out/'hidamari/constructor-data/HD_CivicGardens.json'
    step=replace(original,inputs=[checkout/p.relative_to(paths.REPO) for p in original.inputs],
        commands=[build.Python(checkout/profile.CODE[0],('--source',str(source),'--asset','HD_CivicGardens','--output',str(output)))],
        products=[build.Product('hidamari.data.HD_CivicGardens',(output,))])
    return checkout,out,step


def test_warm_generated_payloads_never_read_and_producer_not_executed(profile,declarations,tmp_path,monkeypatch):
    import sys
    checkout,out,step=rebound(profile,declarations,tmp_path)
    source=out/'hidamari/layout-data.json';output=step.products[0].paths[0]
    source.parent.mkdir(parents=True);source.write_bytes(b'not opened city payload')
    output.parent.mkdir();output.write_bytes(b'not opened projection')
    before=(source.read_bytes(),output.read_bytes());reads=[];original=profile._source
    monkeypatch.setattr(profile,'_source',lambda root,path:(reads.append(path),original(root,path))[1])
    calls=[];old=sys.getprofile()
    def trace(frame,event,arg):
        if event=='call' and frame.f_code.co_filename==str(checkout/profile.CODE[0]):calls.append(frame.f_code.co_name)
    try:
        sys.setprofile(trace)
        result=profile.qualify_hidamari_projection(step,checkout=checkout,output_root=out)
    finally:sys.setprofile(old)
    assert result.step==step.name and not calls
    assert source not in reads and output not in reads
    assert before==(source.read_bytes(),output.read_bytes())


@pytest.mark.parametrize('alias',['checkout','output','script','ancestor','constructor'])
def test_reached_alias_refusal(profile,declarations,tmp_path,alias):
    checkout,out,step=rebound(profile,declarations,tmp_path)
    if alias=='checkout':
        linked=tmp_path/'alias';linked.symlink_to(checkout,target_is_directory=True)
        step=replace(step,inputs=[linked/p.relative_to(checkout) for p in step.inputs],
            commands=[replace(step.commands[0],script=linked/profile.CODE[0])]);checkout=linked
    elif alias=='output':
        actual=tmp_path/'actual-output';actual.mkdir();out.symlink_to(actual,target_is_directory=True)
    elif alias=='ancestor':
        parent=checkout/'platform/studio/atelier';moved=tmp_path/'moved';parent.rename(moved);parent.symlink_to(moved,target_is_directory=True)
    else:
        p=checkout/(profile.CODE[0] if alias=='script' else 'games/yorimichi/hidamari_build.py')
        saved=tmp_path/'saved.py';p.rename(saved);p.symlink_to(saved)
    with pytest.raises(profile.UnsupportedHidamariProjection):
        profile.qualify_hidamari_projection(step,checkout=checkout,output_root=out)


@pytest.mark.parametrize('name',['games/yorimichi/world/regions/hidamari/city_data.py',
    'platform/studio/atelier/atomic_files.py','games/yorimichi/hidamari_build.py'])
def test_original_source_mutations_refuse(profile,declarations,tmp_path,name):
    checkout,out,step=rebound(profile,declarations,tmp_path)
    p=checkout/name;p.write_text(p.read_text()+'\nforeign_execution = 1\n')
    # The constructor binding is the exact function, so mutate within its body.
    if name.endswith('hidamari_build.py'):
        text=p.read_text().replace('out = ctx.out','out = ctx.out\n    foreign_execution = 1',1);p.write_text(text)
    with pytest.raises(profile.UnsupportedHidamariProjection):
        profile.qualify_hidamari_projection(step,checkout=checkout,output_root=out)


@pytest.mark.parametrize('field,value',[('name',None),('paths',[]),('optional_paths',[])])
def test_product_field_types_refuse(profile,declarations,field,value):
    step=deepcopy(next(iter(declarations.raw.values())))
    object.__setattr__(step.products[0],field,value)
    with pytest.raises(profile.UnsupportedHidamariProjection):
        profile.qualify_hidamari_projection(step,checkout=paths.REPO,output_root=declarations.output)


def test_unknown_scanner_candidate_refuses_before_read(profile,declarations,tmp_path,monkeypatch):
    checkout,out,step=rebound(profile,declarations,tmp_path)
    scanner=build._FastImportScanner.__bases__[0];original=scanner.resolve
    foreign=checkout/'games/yorimichi/world/foreign.py';foreign.write_text('must_not_execute = True\n')
    observed=[];read=profile._source
    monkeypatch.setattr(profile,'_source',lambda root,path:(observed.append(path),read(root,path))[1])
    def resolve(self,root,parts):
        return [*original(self,root,parts),foreign]
    monkeypatch.setattr(scanner,'resolve',resolve)
    with pytest.raises(profile.UnsupportedHidamariProjection,match='unknown imported'):
        profile.qualify_hidamari_projection(step,checkout=checkout,output_root=out)
    assert foreign not in observed
