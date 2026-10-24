"""Finite metadata observations only: no native tools or producer bodies."""
from copy import deepcopy
from dataclasses import FrozenInstanceError, fields, replace
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier import build, build_products, paths


@pytest.fixture(scope='module')
def profile():
    source = paths.REPO / 'games/yorimichi/legacy_farhills_profile.py'
    spec = importlib.util.spec_from_file_location('farhills_profile_test', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def default_selection(craterpark_generator_by_choice, monkeypatch):
    for name in ('ATELIER_CRATERPARK_V4_DESIGN', 'ATELIER_CRATERPARK_EDITOR_PARK', 'ATELIER_CRATERPARK_EDITOR_LINES'):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(scope='module')
def declarations(tmp_path_factory):
    from atelier.build_v2.controller_entry import declaration_context
    with pytest.MonkeyPatch.context() as patch:
        for name in ('ATELIER_CRATERPARK_V4_DESIGN', 'ATELIER_CRATERPARK_EDITOR_PARK', 'ATELIER_CRATERPARK_EDITOR_LINES'):
            patch.delenv(name, raising=False)
        recipe = build.load_recipe('yorimichi')
        root = tmp_path_factory.mktemp('layout-profile').resolve() / 'cold'
        context = declaration_context('yorimichi')
        context.out = root
        raw = next(s for s in recipe.world_steps(context) if s.name == 'world.farhills')
        context = declaration_context('yorimichi')
        context.out = root
        steps = recipe.steps(context)
        build.check_declarations(steps)
        graph = build_products.Graph(steps)
        enriched = next(s for s in graph.select([raw.name]) if s.name == raw.name)
        assert graph.owners['treehouse.canopy_dimensions'] == 'world.treehouse_trees.data'
        assert any(p.name == 'treehouse.canopy_dimensions' and p.paths == (root/'treehouse-data/canopy/trees.json',)
                   for s in steps for p in s.products)
    assert not root.exists()
    return SimpleNamespace(root=root, raw=raw, enriched=enriched, recipe=recipe)


@pytest.fixture(params=('raw', 'enriched'))
def stage(request):
    return request.param


def fresh(declarations, stage='raw'):
    return deepcopy(getattr(declarations, stage))


def qualify(profile, step, root, checkout=paths.REPO):
    return profile.qualify_farhills(step, checkout=checkout, output_root=root)


def rebound(step, root, checkout=None):
    old = step.products[0].paths[0].parents[2]
    def path(value):
        if value.is_relative_to(old):
            return root / value.relative_to(old)
        return checkout / value.relative_to(paths.REPO) if checkout is not None else value
    return replace(step, commands=[replace(step.commands[0], script=path(step.commands[0].script))],
                   inputs=[path(p) for p in step.inputs], outputs=[path(p) for p in step.outputs],
                   products=[replace(p, paths=tuple(path(x) for x in p.paths)) for p in step.products])


@pytest.mark.parametrize('field,value', [('cutoff', True), ('heavy', False), ('cache', False), ('audit', True),
    ('batch', build.Batch('other')), ('verify', lambda: True), ('replan', True), ('reads', ['other']),
    ('products', [build_products.Product('fake', (Path('/tmp/fake'),))]), ('cutoff', 1), ('heavy', 1)])
def test_exact_controls_refuse(profile, declarations, stage, field, value):
    with pytest.raises(profile.UnsupportedFarHills, match='Step controls|products|named read'):
        qualify(profile, replace(fresh(declarations, stage), **{field: value}), declarations.root)


def test_private_metadata_refuses(profile, declarations, stage):
    step = fresh(declarations, stage)
    step.private_authority = True
    try:
        with pytest.raises(profile.UnsupportedFarHills, match='Step controls|products|named read'):
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
    with pytest.raises(profile.UnsupportedFarHills, match='input order'):
        qualify(profile, replace(step, inputs=inputs), declarations.root)


def test_actual_factory_full_graph_and_abi(profile, declarations, stage):
    step=fresh(declarations,stage);observed=qualify(profile,step,declarations.root)
    assert tuple(f.name for f in fields(observed)) == ('step','script','arguments','raw_inputs','produced_inputs','code_inputs','products')
    assert observed.script==step.commands[0].script and observed.arguments==()
    assert len(observed.raw_inputs)==88 and len(observed.code_inputs)==71
    expected=tuple(declarations.root/x for x in ('world.json','heightmap.npy','farhills.npy','megapark/trail.json','craterpark/v2/geometry.npz'))
    if stage=='enriched':expected+= (declarations.root/'treehouse-data/canopy/trees.json',)
    assert observed.produced_inputs==expected
    assert observed.raw_inputs==tuple(x for x in declarations.raw.inputs if x not in expected)
    assert observed.products==tuple((x.name,x.paths) for x in step.products)
    scanner=build._FastImportScanner.__bases__[0]()
    world=paths.REPO/'games/yorimichi/world'
    assert observed.code_inputs==tuple(scanner.local_imports(observed.script,(world,world/'regions',paths.STUDIO)))
    drop={world/'regions/megapark/forest.py',world/'regions/megapark/plants.py'}
    expected_inputs=list(declarations.raw.inputs)
    if stage=='enriched':expected_inputs.extend(p for p in observed.code_inputs if p not in expected_inputs and p not in drop)
    assert step.inputs==expected_inputs and step.outputs==[]
    assert step.commands[0].threads==3 and step.commands[0].factory_startup is True
    assert not hasattr(observed,'output_paths') and not hasattr(observed,'verifier')
    assert not declarations.root.exists()
    with pytest.raises(FrozenInstanceError):observed.step='other'


def test_warm_produced_excluded_before_read(profile, declarations, stage, tmp_path, monkeypatch):
    root = tmp_path.resolve() / 'warm'
    files={root/n:b'finite generated input' for n in ('world.json','heightmap.npy','farhills.npy','megapark/trail.json','craterpark/v2/geometry.npz')}
    files[root/'treehouse-data/canopy/trees.json']=b'finite canopy input'
    files.update({root/'terrain/FarHills'/n:b'finite product' for n in ('natural.npz','final.npz','manifest.json')})
    for p, data in files.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    before = {p: (p.read_bytes(), p.stat()) for p in files}
    reads = []
    reader = profile._read
    def observe(checkout, path):
        reads.append(path)
        assert not path.is_relative_to(root) and path.suffix not in ('.npz', '.bin')
        return reader(checkout, path)
    monkeypatch.setattr(profile, '_read', observe)
    qualify(profile, rebound(fresh(declarations, stage), root), root)
    assert reads
    assert all((p.read_bytes(), p.stat()) == value for p, value in before.items())


def finite_checkout(profile, step, tmp_path):
    import shutil
    observed = qualify(profile, step, step.products[0].paths[0].parents[2])
    checkout = tmp_path.resolve() / 'checkout'
    files = [*observed.code_inputs, paths.REPO / 'games/yorimichi/build.py',
             *(p for p in observed.raw_inputs if p.suffix in ('.py', '.json'))]
    for source in dict.fromkeys(files):
        dest = checkout / source.relative_to(paths.REPO)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
    for source in observed.raw_inputs:
        dest = checkout / source.relative_to(paths.REPO)
        if source.suffix in ('.bin','.glb'):
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b'finite raw terrain fixture')
        elif source.name in ('geometry', 'collision'):
            dest.mkdir(parents=True)
    root = tmp_path.resolve() / 'output'
    return checkout, rebound(step, root, checkout), root


@pytest.mark.parametrize('relative', [
    '', 'games', 'games/yorimichi', 'games/yorimichi/world', 'platform', 'platform/studio',
    'games/yorimichi/world/farhills_surface.py',
    'games/yorimichi/tools/craterpark_editor/shipped.json',
    'games/yorimichi/tools/craterpark_editor/data/outer.bin',
    'games/yorimichi/assets/vehicles/belmonte-train/line.json',
    'games/yorimichi/assets/belmonte/source.json',
    'games/yorimichi/assets/belmonte/meshes',
    'games/yorimichi/assets/belmonte/meshes/SM_BM_BT_Terrain_0_0.glb',
    'games/yorimichi/world/regions/craterpark/v2/curves.py',
    'games/yorimichi/tools/craterpark_editor/data',
    'games/yorimichi/assets/craterpark/geometry'])
def test_rebound_alias_checks_reached(profile, declarations, tmp_path, monkeypatch, relative):
    checkout, step, root = finite_checkout(profile, fresh(declarations), tmp_path)
    qualify(profile, step, root, checkout)
    target = checkout / relative
    foreign = tmp_path.resolve() / 'foreign'
    target.rename(foreign)
    target.symlink_to(foreign, target_is_directory=foreign.is_dir())
    reached = []
    checker = profile._role
    def observe(anchor, path, **kwargs):
        reached.append(path)
        return checker(anchor, path, **kwargs)
    monkeypatch.setattr(profile, '_role', observe)
    with pytest.raises(profile.UnsupportedFarHills, match='input role'):
        qualify(profile, step, root, checkout)
    assert any(p == target or target in p.parents for p in reached)
    assert not root.exists()


@pytest.mark.parametrize('relative', ['', 'terrain', 'terrain/FarHills/natural.npz', 'terrain/FarHills/final.npz', 'terrain/FarHills/manifest.json', 'craterpark/v2/geometry.npz', 'world.json', 'heightmap.npy', 'farhills.npy', 'megapark/trail.json', 'treehouse-data/canopy/trees.json'])
def test_output_aliases_reached(profile, declarations, tmp_path, relative):
    root = tmp_path.resolve() / 'output'
    foreign = tmp_path.resolve() / 'foreign'
    foreign.mkdir()
    marker = foreign / 'marker'
    marker.write_bytes(b'untouched')
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to(marker if target.suffix else foreign, target_is_directory=not target.suffix)
    before = marker.read_bytes(), marker.stat()
    with pytest.raises(profile.UnsupportedFarHills, match='output'):
        qualify(profile, rebound(fresh(declarations, 'enriched'), root), root)
    assert (marker.read_bytes(), marker.stat()) == before


@pytest.mark.parametrize('kind', ['missing', 'changed', 'extra-import', 'enrichment', 'factory', 'raw-role'])
def test_source_structure_and_closure_refuse(profile, declarations, tmp_path, kind):
    checkout, step, root = finite_checkout(profile, fresh(declarations), tmp_path)
    source = checkout / ('games/yorimichi/build.py' if kind in ('factory', 'enrichment', 'raw-role')
                         else 'games/yorimichi/world/regions/craterpark/v2/curves.py')
    original = source.read_text()
    if kind == 'missing':
        source.unlink()
    elif kind == 'changed':
        source.write_text(original + '\nCHANGED = True\n')
    elif kind == 'extra-import':
        source.write_text(original + '\nfrom craterpark.v2 import unknown_helper\n')
        source.with_name('unknown_helper.py').write_text('raise AssertionError("never execute")\n')
    else:
        before, after = {'factory': ("cache=True, heavy=True, about='authoritative FarHills", "cache=False, heavy=True, about='authoritative FarHills"),
            'enrichment': ('if f not in step.inputs', 'if f in step.inputs'),
            'raw-role': ("ASSETS / 'craterpark' / 'scene.json'", "ASSETS / 'craterpark' / 'other.json'")}[kind]
        assert before in original
        source.write_text(original.replace(before, after))
    with pytest.raises(profile.UnsupportedFarHills):
        qualify(profile, step, root, checkout)


@pytest.mark.parametrize('change', ['args', 'script', 'commands', 'needs', 'outputs', 'unknown'])
def test_exact_command_roles_refuse(profile, declarations, change):
    step = fresh(declarations)
    if change in ('args', 'script'):
        step.commands = [replace(step.commands[0], **({'args': ('--other',)} if change == 'args'
                        else {'script': step.commands[0].script.with_name('other.py')}))]
    elif change == 'commands':
        step.commands.append(build.Call('foreign', lambda: None))
    elif change == 'needs':
        step.needs = []
    elif change == 'outputs':
        step.outputs.append(declarations.root/'other.json')
    else:
        step.unknown = True
    with pytest.raises(profile.UnsupportedFarHills):
        qualify(profile, step, declarations.root)


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
    with pytest.raises(profile.UnsupportedFarHills, match='context'):
        qualify(profile, fresh(declarations), declarations.root)


@pytest.mark.parametrize('field,value', [
    ('deferred_inputs', [Path('other')]), ('after', ['other']), ('pool_roots', [Path('other')]),
    ('explicit', True), ('references', ['other']), ('optional_inputs', [Path('other')]),
    ('queries', ['other']), ('toolchain', True), ('cook_recovery', 'other'),
    ('checkpoint_previous_needs', []), ('checkpoint_restore', lambda: None),
    ('checkpoint_outputs', (Path('other'),)), ('candidate_scope', 'other'),
    ('controller', 'other'), ('about', 'changed'), ('name', 'world.other'),
    ('inputs', ()), ('outputs', ())])
def test_remaining_exact_fields(profile, declarations, field, value):
    with pytest.raises(profile.UnsupportedFarHills):
        qualify(profile, replace(fresh(declarations), **{field: value}), declarations.root)


def test_raw_metadata_is_data_not_pinned_code(profile, declarations, tmp_path):
    import json
    checkout, step, root = finite_checkout(profile, fresh(declarations), tmp_path)
    original = qualify(profile, step, root, checkout)
    for p in original.raw_inputs:
        if p.name in ('shipped.json', 'terrain.json', 'scene.json'):
            value = json.loads(p.read_bytes())
            value['observation_test_note'] = 'raw data changes remain data identity'
            p.write_text(json.dumps(value))
    assert qualify(profile, step, root, checkout) == original
    assert not root.exists()


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
    with pytest.raises(profile.UnsupportedFarHills):
        qualify(profile, step, declarations.root)


@pytest.mark.parametrize('index',range(3))
def test_all_products_required(profile,declarations,index):
    step=fresh(declarations);step.products.pop(index)
    with pytest.raises(profile.UnsupportedFarHills,match='products'):qualify(profile,step,declarations.root)

@pytest.mark.parametrize('change',['name','path','order','extra','collection','bounds','optional'])
def test_exact_products(profile,declarations,change):
    step=fresh(declarations)
    if change=='order':step.products.reverse()
    elif change=='extra':step.products.append(step.products[0])
    else:
        p=step.products[0]
        values={'name':{'name':'other'},'path':{'paths':(declarations.root/'foreign.npz',)},
            'collection':{'collection':True},'bounds':{'bounds':lambda:None},'optional':{'optional_paths':(declarations.root/'optional',)}}
        for field,value in values[change].items():
            object.__setattr__(p,field,value)
    with pytest.raises(profile.UnsupportedFarHills):qualify(profile,step,declarations.root)

@pytest.mark.parametrize('field,value',[('threads',1),('threads',True),('factory_startup',False),('env',(('FOREIGN','yes'),))])
def test_exact_blender_controls(profile,declarations,field,value):
    step=fresh(declarations);step.commands=[replace(step.commands[0],**{field:value})]
    with pytest.raises(profile.UnsupportedFarHills,match='Blender'):qualify(profile,step,declarations.root)

@pytest.mark.parametrize('index',range(5))
def test_every_produced_input_required(profile,declarations,index):
    step=fresh(declarations);produced=qualify(profile,step,declarations.root).produced_inputs
    step.inputs.remove(produced[index])
    with pytest.raises(profile.UnsupportedFarHills,match='input order'):qualify(profile,step,declarations.root)

def test_full_returned_closure_checked(profile,declarations,monkeypatch):
    original=qualify(profile,fresh(declarations),declarations.root)
    scanner=build._FastImportScanner.__bases__[0]
    monkeypatch.setattr(scanner,'local_imports',lambda self,*args:list(original.code_inputs[:-1]))
    with pytest.raises(profile.UnsupportedFarHills,match='sorted source closure differs'):
        qualify(profile,fresh(declarations),declarations.root)

@pytest.mark.parametrize('name',['forest.py','plants.py'])
def test_enriched_dropped_roles_refuse(profile,declarations,name):
    step=fresh(declarations,'enriched');step.inputs.append(paths.REPO/'games/yorimichi/world/regions/megapark'/name)
    with pytest.raises(profile.UnsupportedFarHills,match='input order'):qualify(profile,step,declarations.root)

@pytest.mark.parametrize('member',['../foreign.glb','/foreign.glb','meshes//bad.glb','meshes/./bad.glb','meshes/../bad.glb','meshes/bad.py','meshes\\bad.glb'])
def test_unsafe_raw_member_refuses(profile,declarations,tmp_path,member):
    import json
    checkout,step,root=finite_checkout(profile,fresh(declarations),tmp_path)
    source=checkout/'games/yorimichi/assets/belmonte/source.json';j=json.loads(source.read_bytes())
    terrain=next(m for m in j['meshes'] if m['name'].startswith('SM_BM_BT_Terrain_'));terrain['path']=member
    source.write_text(json.dumps(j))
    with pytest.raises(profile.UnsupportedFarHills,match='raw terrain'):qualify(profile,step,root,checkout)

def test_legitimate_new_raw_member_uses_data_identity(profile,declarations,tmp_path):
    import json
    checkout,step,root=finite_checkout(profile,fresh(declarations),tmp_path)
    source=checkout/'games/yorimichi/assets/belmonte/source.json';j=json.loads(source.read_bytes())
    added={'name':'SM_BM_BT_Terrain_extra','path':'meshes/SM_BM_BT_Terrain_extra.glb'};j['meshes'].append(added)
    source.write_text(json.dumps(j));path=source.parent/added['path'];path.write_bytes(b'finite raw mesh')
    index=step.inputs.index(checkout/'games/yorimichi/world/regions/megapark/placement.py');step.inputs.insert(index,path)
    observed=qualify(profile,step,root,checkout)
    assert path in observed.raw_inputs and path not in observed.code_inputs and not root.exists()

@pytest.mark.parametrize('relative,before,after',[
    ('games/yorimichi/build.py','if f.resolve() not in drop','if f.resolve() in drop'),
    ('games/yorimichi/world/farhills_surface.py',"directory/'natural.npz'","directory/'other.npz'"),
    ('games/yorimichi/world/terrain_product.py','managed_temporary_parent(path)', 'path.parent')])
def test_relevant_source_counter_mutations(profile,declarations,tmp_path,relative,before,after):
    checkout,step,root=finite_checkout(profile,fresh(declarations),tmp_path)
    source=checkout/relative;text=source.read_text();assert before in text;source.write_text(text.replace(before,after))
    with pytest.raises(profile.UnsupportedFarHills,match='source structure differs'):qualify(profile,step,root,checkout)


def test_full_named_owner_and_stage_pairing(profile,declarations):
    full=fresh(declarations,'enriched');raw=fresh(declarations,'raw')
    assert raw.reads==[] and full.reads==['treehouse.canopy_dimensions']
    assert len(qualify(profile,raw,declarations.root).produced_inputs)==5
    assert len(qualify(profile,full,declarations.root).produced_inputs)==6
    for step,reads in ((raw,full.reads),(full,raw.reads)):
        with pytest.raises(profile.UnsupportedFarHills,match='input order'):
            qualify(profile,replace(step,reads=reads),declarations.root)


def test_unknown_candidate_refuses_before_content(profile,declarations,tmp_path,monkeypatch):
    checkout,step,root=finite_checkout(profile,fresh(declarations),tmp_path)
    extra=checkout/'games/yorimichi/world/numpy.py';extra.write_text('raise AssertionError("never execute")\n')
    original=profile._read
    def reader(anchor,source):
        assert source!=extra
        return original(anchor,source)
    monkeypatch.setattr(profile,'_read',reader)
    with pytest.raises(profile.UnsupportedFarHills,match='unknown source import target'):
        qualify(profile,step,root,checkout)

@pytest.mark.parametrize('fault',['duplicate-name','duplicate-path','case-alias'])
def test_ambiguous_manifest_members_refuse(profile,declarations,tmp_path,fault):
    import json
    checkout,step,root=finite_checkout(profile,fresh(declarations),tmp_path)
    source=checkout/'games/yorimichi/assets/belmonte/source.json';j=json.loads(source.read_bytes())
    m=next(x for x in j['meshes'] if x['name'].startswith('SM_BM_BT_Terrain_'));x=dict(m)
    if fault=='duplicate-name':x['path']='meshes/different.glb'
    elif fault=='duplicate-path':x['name']='SM_BM_BT_Terrain_other'
    else:x['name']=m['name'].swapcase();x['path']=m['path'].swapcase()
    if fault=='case-alias':
        # Keep the original case-sensitive selected prefix, alias the member path.
        x['name']='SM_BM_BT_Terrain_other'
    j['meshes'].append(x);source.write_text(json.dumps(j))
    with pytest.raises(profile.UnsupportedFarHills,match='invalid raw terrain'):
        qualify(profile,step,root,checkout)
