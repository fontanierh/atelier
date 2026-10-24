"""Original cutoff factory and complete in-process helper origins, without callback execution."""
from copy import deepcopy
from dataclasses import replace
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest
from atelier import build,build_products,paths


@pytest.fixture(scope='module')
def profile():
    spec=importlib.util.spec_from_file_location('brine_sources_observer',paths.REPO/'games/yorimichi/legacy_brinecove_sources_profile.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


@pytest.fixture(scope='module')
def declarations(tmp_path_factory):
    from atelier.build_v2.controller_entry import declaration_context
    recipe=build.load_recipe('yorimichi');ctx=declaration_context('yorimichi');ctx.out=tmp_path_factory.mktemp('brine-source-observe')/'cold'
    raw=recipe.brinecove_source_step(ctx.out);steps=recipe.steps(ctx);build.check_declarations(steps);graph=build_products.Graph(steps)
    return SimpleNamespace(raw=raw,full=graph.by_name[raw.name],output=ctx.out)


@pytest.mark.parametrize('stage',['raw','full'])
def test_actual_factory_callback_and_helpers_are_observed_without_execution(profile,declarations,stage):
    import sys
    step=getattr(declarations,stage);calls=[];old=sys.getprofile()
    source=paths.REPO/'games/yorimichi/world/source_registry.py'
    def trace(frame,event,arg):
        if event=='call' and frame.f_code.co_filename==str(source):calls.append(frame.f_code.co_name)
    try:
        sys.setprofile(trace)
        result=profile.qualify_brinecove_sources(step,checkout=paths.REPO,output_root=declarations.output)
    finally:sys.setprofile(old)
    assert not calls and not declarations.output.exists()
    assert result.output_paths==(declarations.output/'digests/brinecove-source-library.json',)
    assert result.produced_inputs==() and result.callback.qualname=='brinecove_source_step.<locals>.<lambda>'
    assert result.publisher.qualname=='publish' and result.models.qualname=='models'


@pytest.mark.parametrize('field,value',[('cache',True),('cutoff',False),('replan',True),('heavy',True),
    ('audit',True),('toolchain',True),('needs',['other']),('reads',['fake']),('products',[1]),('batch',build.Batch('fake'))])
def test_changed_controls_refuse(profile,declarations,field,value):
    step=replace(declarations.raw);setattr(step,field,value)
    with pytest.raises(profile.UnsupportedBrinecoveSources):profile.qualify_brinecove_sources(step,checkout=paths.REPO,output_root=declarations.output)


@pytest.mark.parametrize('change',['fn','label','output','inputorder','extra','private'])
def test_foreign_callback_or_role_refuses(profile,declarations,change):
    step=replace(declarations.raw)
    if change=='fn':step.commands=[build.Call(step.commands[0].name,lambda ctx,log:None)]
    elif change=='label':step.commands=[build.Call('other',step.commands[0].fn)]
    elif change=='output':step.outputs=[declarations.output/'foreign.json']
    elif change=='inputorder':step.inputs=list(reversed(step.inputs))
    elif change=='extra':step.inputs=[*step.inputs,paths.REPO/'README.md']
    else:step.fake_permission=True
    with pytest.raises(profile.UnsupportedBrinecoveSources):profile.qualify_brinecove_sources(step,checkout=paths.REPO,output_root=declarations.output)


@pytest.mark.parametrize('helper',['publish','models','managed_temporary_parent'])
def test_poisoned_real_helper_is_rejected_without_execution(profile,declarations,monkeypatch,helper):
    from atelier import atomic_files
    module=declarations.raw.commands[0].fn.__globals__['source_registry'];called=[]
    def foreign(*a,**k):called.append(True);raise AssertionError('helper executed')
    monkeypatch.setattr(atomic_files if helper=='managed_temporary_parent' else module,helper,foreign)
    with pytest.raises(profile.UnsupportedBrinecoveSources):profile.qualify_brinecove_sources(declarations.raw,checkout=paths.REPO,output_root=declarations.output)
    assert not called



def test_changed_callback_closure_refuses(profile,declarations):
    import types
    step=replace(declarations.raw);fn=step.commands[0].fn
    replacement=types.FunctionType(fn.__code__,fn.__globals__,closure=(types.CellType(declarations.output/'foreign.json'),))
    step.commands=[build.Call(step.commands[0].name,replacement)]
    with pytest.raises(profile.UnsupportedBrinecoveSources,match='bindings'):
        profile.qualify_brinecove_sources(step,checkout=paths.REPO,output_root=declarations.output)


def test_output_alias_refuses_before_helpers(profile,declarations,tmp_path):
    import types
    actual=tmp_path/'actual';actual.mkdir();out=tmp_path/'alias';out.symlink_to(actual,target_is_directory=True)
    output=out/'digests/brinecove-source-library.json';step=replace(declarations.raw,outputs=[output]);fn=step.commands[0].fn
    replacement=types.FunctionType(fn.__code__,fn.__globals__,closure=(types.CellType(output),))
    step.commands=[build.Call(step.commands[0].name,replacement)]
    with pytest.raises(profile.UnsupportedBrinecoveSources,match='ancestry'):
        profile.qualify_brinecove_sources(step,checkout=paths.REPO,output_root=out)


def test_warm_output_not_read_or_changed(profile,declarations,tmp_path,monkeypatch):
    import types
    out=tmp_path/'warm';output=out/'digests/brinecove-source-library.json';output.parent.mkdir(parents=True);output.write_bytes(b'not a source input')
    step=replace(declarations.raw,outputs=[output]);fn=step.commands[0].fn
    step.commands=[build.Call(fn=types.FunctionType(fn.__code__,fn.__globals__,closure=(types.CellType(output),)),name=step.commands[0].name)]
    before=output.stat().st_mtime_ns;original=profile._read;reads=[]
    monkeypatch.setattr(profile,'_read',lambda root,p:(reads.append(p),original(root,p))[1])
    assert profile.qualify_brinecove_sources(step,checkout=paths.REPO,output_root=out).output_paths==(output,)
    assert output not in reads and output.read_bytes()==b'not a source input' and output.stat().st_mtime_ns==before
