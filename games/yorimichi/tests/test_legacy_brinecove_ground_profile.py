"""Real original recipe declarations; qualification never runs a constructor or verifier."""

from copy import deepcopy

from dataclasses import FrozenInstanceError, fields, replace

import importlib.util

from pathlib import Path

from types import SimpleNamespace, FunctionType

import pytest

from atelier import build, build_products, paths

@pytest.fixture(autouse=True)
def default_selection(craterpark_generator_by_choice, monkeypatch):
    for name in ('ATELIER_CRATERPARK_V4_DESIGN', 'ATELIER_CRATERPARK_EDITOR_PARK', 'ATELIER_CRATERPARK_EDITOR_LINES'):
        monkeypatch.delenv(name, raising=False)

def qualify(profile, step, out, checkout=paths.REPO):
    return profile.qualify_brinecove_ground(step, checkout=checkout, output_root=out)

@pytest.mark.parametrize('field,value', [('heavy', False), ('heavy', 1), ('cache', False), ('audit', True),
    ('toolchain', False), ('cutoff', True), ('replan', True), ('reads', []), ('needs', ['other']),
    ('after', ['other']), ('outputs', [Path('extra')]), ('deferred_inputs', [Path('other')]),
    ('optional_inputs', [Path('other')]), ('pool_roots', [Path('other')]), ('references', ['other']),
    ('queries', ['other']), ('controller', 'other'), ('checkpoint_restore', lambda: None),
    ('about', 'other'), ('name', 'world.brinecove.geometry.SM_BC_Hero_GalleonHull')])
def test_controls(profile, declarations, field, value):
    with pytest.raises(profile.UnsupportedBrinecoveGround):
        qualify(profile, replace(declarations.raw, **{field: value}), declarations.root)

@pytest.mark.parametrize('field,value', [('group', 'other'), ('runtime_env', ('other',)), ('max_seconds', 240)])
def test_batch(profile, declarations, field, value):
    step = declarations.raw
    with pytest.raises(profile.UnsupportedBrinecoveGround):
        qualify(profile, replace(step, batch=replace(step.batch, **{field: value})), declarations.root)

@pytest.mark.parametrize('field,value', [('threads', 1), ('threads', True), ('factory_startup', False), ('env', ()), ('script', Path('foreign'))])
def test_command(profile, declarations, field, value):
    step = declarations.raw
    with pytest.raises(profile.UnsupportedBrinecoveGround):
        qualify(profile, replace(step, commands=[replace(step.commands[0], **{field: value})]), declarations.root)

@pytest.mark.parametrize('change', ['order', 'duplicate', 'extra', 'missing', 'builder'])
def test_input_and_argument_shape(profile, declarations, change):
    step = deepcopy(declarations.raw)
    if change == 'order': step.inputs[-1], step.inputs[-2] = step.inputs[-2], step.inputs[-1]
    elif change == 'duplicate': step.inputs.append(step.inputs[0])
    elif change == 'extra': step.inputs.append(paths.REPO / 'games/yorimichi/build.py')
    elif change == 'missing': step.inputs.pop()
    else:
        args = list(step.commands[0].args); args[3] = 'harbor'
        step.commands = [replace(step.commands[0], args=tuple(args))]
    with pytest.raises(profile.UnsupportedBrinecoveGround): qualify(profile, step, declarations.root)

@pytest.mark.parametrize('index', [0, 1, 2])
@pytest.mark.parametrize('change', ['missing', 'extra', 'optional', 'name'])
def test_each_complete_product(profile, declarations, index, change):
    step = deepcopy(declarations.raw); product = step.products[index]
    if change == 'missing': step.products.pop(index)
    elif change == 'extra': step.products[index] = replace(product, paths=(*product.paths, declarations.root / 'other'))
    elif change == 'optional': step.products[index] = replace(product, optional_paths=product.paths)
    else: step.products[index] = replace(product, name='foreign')
    with pytest.raises(profile.UnsupportedBrinecoveGround): qualify(profile, step, declarations.root)

@pytest.mark.parametrize('change', ['defaults', 'global', 'builtin', 'replacement', 'kwdefaults', 'metadata'])
def test_actual_verifier_bindings(profile, declarations, change):
    step = replace(declarations.raw); original = step.verify
    namespace = dict(original.__globals__)
    fn = FunctionType(original.__code__, namespace, original.__name__, original.__defaults__, original.__closure__)
    fn.__qualname__ = original.__qualname__
    if change == 'defaults': fn.__defaults__ = (original.__defaults__[0], True)
    elif change == 'global': namespace['WORLD'] = Path('/foreign')
    elif change == 'builtin': namespace['str'] = lambda x: x
    elif change == 'replacement': fn = lambda: True
    elif change == 'kwdefaults': fn.__kwdefaults__ = {'unexpected': False}
    else: fn.__wrapped__ = original
    with pytest.raises(profile.UnsupportedBrinecoveGround): qualify(profile, replace(step, verify=fn), declarations.root)

def finite(profile, declarations, tmp_path):
    import shutil
    step = declarations.raw; checkout = tmp_path / 'source'; out = tmp_path / 'output'
    for role in profile.CODE_DIGESTS:
        source = paths.REPO / role; target = checkout / role
        target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target)
    for source in step.inputs:
        target = checkout / source.relative_to(paths.REPO)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists(): shutil.copy2(source, target)
    def path(p):
        if p.is_relative_to(paths.REPO): return checkout / p.relative_to(paths.REPO)
        return out / p.relative_to(declarations.root)
    c = step.commands[0]
    args = tuple(str(path(Path(a))) if a.startswith('/') else a for a in c.args)
    namespace = dict(step.verify.__globals__); namespace['WORLD'] = checkout / 'games/yorimichi/world'
    from atelier.build_v2.legacy_qualification import CapturedCode, _code_tree
    captured = CapturedCode(str(checkout / 'games/yorimichi/region_exports.py'), (checkout / 'games/yorimichi/region_exports.py').read_bytes())
    code = next(code for code in _code_tree(captured.compiled()) if code.co_qualname == 'steps.<locals>.complete')
    verifier = FunctionType(code, namespace, step.verify.__name__, (path(step.verify.__defaults__[0]), False))
    verifier.__qualname__ = step.verify.__qualname__
    rebound = replace(step, commands=[replace(c, script=path(c.script), args=args)], inputs=[path(p) for p in step.inputs],
        products=[replace(p, paths=tuple(path(x) for x in p.paths)) for p in step.products], verify=verifier)
    # Input tail is sorted in physical checkout space by the original constructor.
    return checkout, out, rebound

@pytest.mark.parametrize('role', ['games/yorimichi/world/regions/brinecove/plan_ground.py',
    'games/yorimichi/world/regions/brinecove/ground.py',
    'games/yorimichi/world/regions/brinecove/logical_catalogue.py', 'games/yorimichi/region_exports.py',
    'platform/studio/atelier/build_batch_worker.py'])
def test_source_mutations_reach_pin(profile, declarations, tmp_path, role):
    checkout, out, step = finite(profile, declarations, tmp_path)
    qualify(profile, step, out, checkout)
    source = checkout / role; source.write_bytes(source.read_bytes() + b'\nmutation = True\n')
    with pytest.raises(profile.UnsupportedBrinecoveGround, match='source structure'): qualify(profile, step, out, checkout)

@pytest.mark.parametrize('kind', ['source-file', 'source-parent', 'checkout-parent', 'output-parent', 'output-root'])
def test_reached_aliases(profile, declarations, tmp_path, kind):
    checkout, out, step = finite(profile, declarations, tmp_path)
    qualify(profile, step, out, checkout)
    if kind == 'source-file': target = checkout / 'games/yorimichi/world/regions/brinecove/plan_ground.py'
    elif kind == 'source-parent': target = checkout / 'games/yorimichi/world/regions/brinecove/procedural'
    elif kind == 'checkout-parent': target = checkout / 'games'
    elif kind == 'output-root': target = out; target.mkdir()
    else: target = out / 'brinecove/query-data'; target.mkdir(parents=True)
    saved = target.with_name(target.name + '-saved'); target.rename(saved); target.symlink_to(saved, target_is_directory=saved.is_dir())
    with pytest.raises(profile.UnsupportedBrinecoveGround): qualify(profile, step, out, checkout)

def test_no_generated_reads_or_callbacks(profile, declarations, tmp_path, monkeypatch):
    import sys
    checkout, out, step = finite(profile, declarations, tmp_path)
    generated = [*qualify(profile, step, out, checkout).produced_inputs, *(p for product in step.products for p in product.paths)]
    for p in generated:
        if p == step.products[0].paths[0]: p.mkdir(parents=True)
        else: p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(b'preserve warm payload')
    before = {p: p.read_bytes() for p in generated if p.is_file()}
    original = profile._read; reads = []; calls = []
    def read(home, p):
        assert not p.is_relative_to(out); reads.append(p); return original(home, p)
    monkeypatch.setattr(profile, '_read', read)
    def trace(frame, event, arg):
        if event == 'call' and '/world/' in frame.f_code.co_filename: calls.append(frame.f_code.co_name)
        return trace
    previous = sys.gettrace(); sys.settrace(trace)
    try: result = qualify(profile, step, out, checkout)
    finally: sys.settrace(previous)
    assert not calls
    assert set(result.code_inputs) <= set(reads)
    assert before == {p: p.read_bytes() for p in before}

@pytest.mark.parametrize('value', [True, object()])
def test_private_step_metadata_refuses(profile, declarations, value):
    step = replace(declarations.raw); step.unreviewed = value
    with pytest.raises(profile.UnsupportedBrinecoveGround, match='controls'): qualify(profile, step, declarations.root)

@pytest.mark.parametrize('index', [0, 1, 2])
def test_product_leaf_aliases(profile, declarations, tmp_path, index):
    checkout, out, step = finite(profile, declarations, tmp_path)
    qualify(profile, step, out, checkout)
    target = step.products[index].paths[0]
    target.parent.mkdir(parents=True, exist_ok=True)
    saved = tmp_path / 'foreign'
    if index == 0: saved.mkdir()
    else: saved.write_bytes(b'foreign')
    target.symlink_to(saved, target_is_directory=index == 0)
    with pytest.raises(profile.UnsupportedBrinecoveGround): qualify(profile, step, out, checkout)

@pytest.fixture(scope='module')
def profile():
    patch = pytest.MonkeyPatch(); patch.syspath_prepend(str(paths.REPO / 'games/yorimichi'))
    spec = importlib.util.spec_from_file_location('brinecove_ground_test_profile', paths.REPO / 'games/yorimichi/legacy_brinecove_ground_profile.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    yield module
    patch.undo()

@pytest.fixture(scope='module')
def declarations(tmp_path_factory, profile):
    from atelier.build_v2.controller_entry import declaration_context
    with pytest.MonkeyPatch.context() as patch:
        for name in ('ATELIER_CRATERPARK_V4_DESIGN', 'ATELIER_CRATERPARK_EDITOR_PARK', 'ATELIER_CRATERPARK_EDITOR_LINES'):
            patch.delenv(name, raising=False)
        recipe = build.load_recipe('yorimichi'); out = tmp_path_factory.mktemp('coastal-ground-profile').resolve() / 'absent'
        ctx = declaration_context('yorimichi'); ctx.out = out
        name = 'world.brinecove.geometry.SM_BC_Ground'
        raw = next(s for s in recipe.world_steps(ctx) if s.name == name)
        ctx = declaration_context('yorimichi'); ctx.out = out
        steps = recipe.steps(ctx); build.check_declarations(steps); graph = build_products.Graph(steps)
        full = next(s for s in graph.select([name]) if s.name == name)
    assert graph.owners['terrain.Brinecove.final'] == name
    for product in raw.reads:
        assert product in graph.owners
    assert not out.exists()
    return SimpleNamespace(root=out, raw=raw, full=full)

@pytest.mark.parametrize('stage', ['raw', 'full'])
def test_actual_ground_declaration(profile, declarations, stage):
    step = getattr(declarations, stage); result = qualify(profile, step, declarations.root)
    assert result.step == step.name
    assert result.raw_inputs == tuple(step.inputs)
    assert len(result.produced_inputs) == 10
    assert result.produced_inputs[0] == declarations.root / 'brinecove-data/final-rim.json'
    assert result.produced_inputs[1:] == tuple(Path(step.commands[0].args[i+1]) for i,v in enumerate(step.commands[0].args) if v == '--paving')
    assert set(result.code_inputs) == set(step.inputs)
    assert len(result.code_inputs) == 44
    assert result.products == tuple((p.name,p.paths) for p in step.products)
    assert len(fields(result)) == 8
    with pytest.raises(FrozenInstanceError):result.step = 'other'
    assert not declarations.root.exists()

@pytest.mark.parametrize('change', ['missing-rim', 'missing-paving', 'reordered-paving', 'duplicate-paving', 'extra-paving'])
def test_complete_ordered_named_reads(profile, declarations, change):
    step = replace(declarations.raw); reads = list(step.reads)
    if change == 'missing-rim': reads.pop(0)
    elif change == 'missing-paving': reads.pop()
    elif change == 'reordered-paving': reads[2],reads[3] = reads[3],reads[2]
    elif change == 'duplicate-paving': reads[2] = reads[1]
    else: reads.append('brinecove.paving.other')
    with pytest.raises(profile.UnsupportedBrinecoveGround):qualify(profile, replace(step,reads=reads), declarations.root)




def test_foreign_name_refuses_without_equality_execution(profile, declarations):
    calls = []
    class Foreign:
        def __eq__(self, value):
            calls.append(value)
            raise AssertionError('executed foreign metadata')
    with pytest.raises(profile.UnsupportedBrinecoveGround):
        qualify(profile, replace(declarations.raw, name=Foreign()), declarations.root)
    assert calls == []
