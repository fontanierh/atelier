"""Original coastal JSON declaration roles, without generated payload or producer execution."""
from copy import deepcopy
from dataclasses import replace
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest
from atelier import build,build_products,paths


@pytest.fixture(scope='module')
def profile():
    s=importlib.util.spec_from_file_location('coastal_data_observer',paths.REPO/'games/yorimichi/legacy_brinecove_data_profile.py')
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


@pytest.fixture(scope='module')
def declarations(tmp_path_factory):
    from atelier.build_v2.controller_entry import declaration_context
    recipe=build.load_recipe('yorimichi');ctx=declaration_context('yorimichi');ctx.out=tmp_path_factory.mktemp('coastal-data')/'cold'
    names={'world.brinecove.rim_data','world.brinecove.placements'}
    raw={s.name:s for s in recipe.world_steps(ctx) if s.name in names}
    steps=recipe.steps(ctx);build.check_declarations(steps);g=build_products.Graph(steps)
    return SimpleNamespace(raw=raw,full={n:g.by_name[n] for n in names},output=ctx.out)


@pytest.mark.parametrize('name',['world.brinecove.rim_data','world.brinecove.placements'])
@pytest.mark.parametrize('stage',['raw','full'])
def test_original_raw_full_factories(profile,declarations,name,stage):
    step=getattr(declarations,stage)[name]
    result=profile.qualify_brinecove_data(step,checkout=paths.REPO,output_root=declarations.output)
    assert result.step==name and result.arguments==step.commands[0].args
    assert result.products==((step.products[0].name,step.products[0].paths),)
    assert len(result.code_inputs)==(12 if name.endswith('rim_data') else 26)
    assert len(result.produced_inputs)==(1 if name.endswith('rim_data') else 2)
    assert not declarations.output.exists()


@pytest.mark.parametrize('name',['world.brinecove.rim_data','world.brinecove.placements'])
@pytest.mark.parametrize('field,value',[('cache',False),('cache',1),('heavy',True),('audit',True),
    ('toolchain',True),('replan',True),('cutoff',True),('reads',[]),('batch',build.Batch('fake'))])
def test_controls(profile,declarations,name,field,value):
    step=replace(declarations.raw[name]);setattr(step,field,value)
    with pytest.raises(profile.UnsupportedBrinecoveData):profile.qualify_brinecove_data(step,checkout=paths.REPO,output_root=declarations.output)


@pytest.mark.parametrize('change',['inputorder','extra','missing','argv','product','private'])
def test_membership_roles(profile,declarations,change):
    step=deepcopy(declarations.full['world.brinecove.placements'])
    if change=='inputorder':step.inputs.reverse()
    elif change=='extra':step.inputs.append(paths.REPO/'README.md')
    elif change=='missing':step.inputs.pop()
    elif change=='argv':step.commands[0]=replace(step.commands[0],args=step.commands[0].args+('--other',))
    elif change=='product':step.products=[build.Product('fake',(declarations.output/'fake.json',))]
    else:step.untrusted=True
    with pytest.raises(profile.UnsupportedBrinecoveData):profile.qualify_brinecove_data(step,checkout=paths.REPO,output_root=declarations.output)


def rebound(profile,declarations,tmp_path,name):
    checkout=tmp_path/'checkout';out=tmp_path/'output';step=deepcopy(declarations.raw[name]);code=profile.ROLES[name]['code']
    for n in (*code,'games/yorimichi/brinecove_atomic_build.py'):
        p=checkout/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((paths.REPO/n).read_bytes())
    def path(p):
        if p.is_relative_to(declarations.output):return out/p.relative_to(declarations.output)
        return checkout/p.relative_to(paths.REPO)
    for p in step.inputs:
        if p.suffix in ('.glb','.json') and p.is_relative_to(paths.REPO):
            q=path(p);q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(b'raw metadata fixture; never consumed')
    args=tuple(str(out/Path(a).relative_to(declarations.output)) if Path(a).is_absolute() and Path(a).is_relative_to(declarations.output) else a for a in step.commands[0].args)
    step=replace(step,inputs=[path(p) for p in step.inputs],commands=[build.Python(checkout/profile.ROLES[name]['script'],args)],
        products=[replace(p,paths=tuple(path(q) for q in p.paths)) for p in step.products])
    return checkout,out,step


@pytest.mark.parametrize('name',['world.brinecove.rim_data','world.brinecove.placements'])
def test_generated_and_raw_model_content_not_read_and_producer_not_called(profile,declarations,tmp_path,monkeypatch,name):
    import sys
    checkout,out,step=rebound(profile,declarations,tmp_path,name)
    generated=[out/'terrain/FarHills/final.npz'] if name.endswith('rim_data') else [out/'brinecove-data/final-rim.json',out/'digests/brinecove-source-library.json']
    output=step.products[0].paths[0]
    for p in (*generated,output):p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'generated content is not inspected')
    reads=[];original=profile._source;monkeypatch.setattr(profile,'_source',lambda root,p:(reads.append(p),original(root,p))[1])
    calls=[];old=sys.getprofile()
    def trace(frame,event,arg):
        if event=='call' and frame.f_code.co_filename==str(step.commands[0].script):calls.append(frame.f_code.co_name)
    try:
        sys.setprofile(trace);result=profile.qualify_brinecove_data(step,checkout=checkout,output_root=out)
    finally:sys.setprofile(old)
    assert result.step==name and not calls and not set(generated+[output])&set(reads)
    assert all(p.suffix=='.py' for p in reads) and output.read_bytes()==b'generated content is not inspected'


@pytest.mark.parametrize('alias',['models','script','output'])
def test_reached_aliases(profile,declarations,tmp_path,alias):
    checkout,out,step=rebound(profile,declarations,tmp_path,'world.brinecove.placements')
    if alias=='models':
        p=checkout/'games/yorimichi/assets/brinecove/models';saved=tmp_path/'models';p.rename(saved);p.symlink_to(saved,target_is_directory=True)
    elif alias=='script':
        p=step.commands[0].script;saved=tmp_path/'script.py';p.rename(saved);p.symlink_to(saved)
    else:
        actual=tmp_path/'actual';actual.mkdir();out.symlink_to(actual,target_is_directory=True)
    with pytest.raises(profile.UnsupportedBrinecoveData):profile.qualify_brinecove_data(step,checkout=checkout,output_root=out)
