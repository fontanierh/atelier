"""Actual full-recipe Treehouse planner qualification; no planner or verifier execution."""
from copy import deepcopy
from dataclasses import FrozenInstanceError, fields, replace
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier import build, build_products, paths
from atelier.build_v2.legacy_qualification import UnsupportedOrigin


@pytest.fixture(scope='module')
def profile():
    source = paths.REPO / 'games/yorimichi/legacy_treehouse_props_profile.py'
    spec = importlib.util.spec_from_file_location('legacy_treehouse_props_profile_test', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def declarations(tmp_path_factory):
    from atelier.build_v2.controller_entry import declaration_context
    output_root = tmp_path_factory.mktemp('treehouse-profile-cold') / 'yorimichi'
    ctx = declaration_context('yorimichi')
    ctx.out = output_root
    steps = build.load_recipe('yorimichi').steps(ctx)
    build.check_declarations(steps)
    graph = build_products.Graph(steps)
    selected = graph.select(['world.treehouse_props.geometry'])
    names = {f'world.treehouse_props.geometry.{parent}' for parent in
             tuple('TH_P_' + slug for slug in ('backpack', 'barrel', 'basket', 'bell', 'bookshelf',
                'crate_desk', 'futon', 'globe', 'kamado', 'log_table', 'planter', 'stump_kettle', 'telescope'))}
    planners = [step for step in selected if step.name in names]
    assert len(planners) == 13
    return SimpleNamespace(root=output_root, steps={step.name: step for step in planners})


@pytest.fixture(scope='module')
def planners(profile, declarations):
    assert not declarations.root.exists()
    observed = {name: profile.qualify_treehouse_prop(
        step, checkout=paths.REPO, output_root=declarations.root)
        for name, step in declarations.steps.items()}
    assert not declarations.root.exists(), 'cold qualification must not create the output root'
    return observed


def fresh(declarations, parent='TH_P_backpack'):
    """Deepcopy mutable declarations; each test owns its mutations."""
    return deepcopy(declarations.steps[f'world.treehouse_props.geometry.{parent}'])


def rebound(step, output_root, checkout=None):
    """Apply real Context relocation, optionally to another complete source checkout."""
    old_root = Path(step.commands[0].args[7]).parents[2]
    old_checkout = paths.REPO
    def path(value):
        value = Path(value)
        if value.is_relative_to(old_root):
            return output_root / value.relative_to(old_root)
        return checkout / value.relative_to(old_checkout) if checkout is not None else value
    command = step.commands[0]
    args = tuple(str(path(v)) if i % 2 else v for i, v in enumerate(command.args))
    command = replace(command, script=path(command.script), args=args)
    products = [replace(p, paths=tuple(path(v) for v in p.paths)) for p in step.products]
    import types
    function = step.verify
    namespace = function.__globals__.copy()
    code = function.__code__
    if checkout is not None:
        namespace['WORLD'] = path(namespace['WORLD'])
        code = code.replace(co_filename=str(path(code.co_filename)))
    verify = types.FunctionType(code, namespace, function.__name__,
        (path(function.__defaults__[0]), function.__defaults__[1]), function.__closure__)
    return replace(step, commands=[command], inputs=[path(v) for v in step.inputs],
                   products=products, verify=verify)


def qualify(profile, step, root):
    return profile.qualify_treehouse_prop(step, checkout=paths.REPO, output_root=root)


def test_actual_graph_planners_bind_all_original_roles(profile, declarations, planners):
    for name, step in declarations.steps.items():
        task = planners[name]
        parent = name.rsplit('.', 1)[1]
        command, = step.commands
        assert task.step == name and task.parent == parent
        assert task.script == command.script == paths.REPO / 'games/yorimichi/world/regions/treehouse/plan_prop.py'
        assert task.arguments == command.args
        assert task.arguments == ('--parameters', str(task.raw_inputs[0]), '--source', str(task.raw_inputs[1]),
                                  '--data', str(task.data_root), '--output', str(task.primary_root))
        assert task.raw_inputs == (paths.REPO / f'games/yorimichi/assets/treehouse/export-parameters/{parent}.json',
            paths.REPO / f'games/yorimichi/assets/treehouse/props/{parent[5:]}/{parent[5:]}.glb')
        assert task.produced_inputs == ()
        assert task.code_inputs == tuple(step.inputs[:len(task.code_inputs)])
        assert step.inputs == [*task.code_inputs, *task.raw_inputs, *task.produced_inputs]
        assert task.products == ((f'treehouse_props.geometry.{parent}', (task.primary_root,)),
                                 (f'treehouse.prop_data.{parent}', (task.data_root,)))
        assert task.primary_root == declarations.root / 'planned_exports/treehouse_props' / parent
        assert task.data_root == declarations.root / 'treehouse-data/props' / parent
        assert task.batch == ('treehouse_props logical geometry', (), 240.)
        assert task.verifier.filename == str(paths.REPO / 'games/yorimichi/region_exports.py')
        assert task.verifier.qualname == 'steps.<locals>.complete'
        assert task.verifier.binding_names == ('WORLD', 'str')
        assert len(task.verifier.source_digest) == 64
        with pytest.raises(FrozenInstanceError):
            task.parent = 'changed'


def test_warm_outputs_are_not_adopted_or_changed(profile, declarations, planners, tmp_path, monkeypatch):
    root = tmp_path / 'warm'
    markers = {}
    for parent in profile.PARENTS:
        for relative, content in ((f'planned_exports/treehouse_props/{parent}/plan.json', b'foreign plan'),
                                  (f'treehouse-data/props/{parent}/record.json', b'foreign data')):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            markers[path] = (path.read_bytes(), path.lstat())
    reader = profile._source_bytes
    def sources_only(checkout, path):
        assert not Path(path).is_relative_to(root), 'generated outputs must remain unopened'
        return reader(checkout, path)
    monkeypatch.setattr(profile, '_source_bytes', sources_only)
    for parent in profile.PARENTS:
        task = qualify(profile, rebound(fresh(declarations, parent), root), root)
        assert task.primary_root.exists() and task.data_root.exists()
        assert task.verifier == planners[f'world.treehouse_props.geometry.{parent}'].verifier
    assert all((path.read_bytes(), path.lstat()) == state for path, state in markers.items())


def test_qualification_does_not_execute_verifier(profile, declarations, monkeypatch):
    step = fresh(declarations)
    def forbidden(*args, **kwargs):
        raise AssertionError('verifier executed during observation')
    original = step.verify.__code__
    try:
        step.verify.__code__ = forbidden.__code__
        with pytest.raises((UnsupportedOrigin, profile.UnsupportedTreehouseProp)):
            qualify(profile, step, declarations.root)
    finally:
        step.verify.__code__ = original


@pytest.mark.parametrize('parent', ['TH_P_future', 'TH_P_', '', 'TH_P_backpack.extra'])
def test_unknown_or_future_parent_is_refused(profile, declarations, parent):
    step = replace(fresh(declarations), name='world.treehouse_props.geometry.' + parent)
    with pytest.raises(profile.UnsupportedTreehouseProp):
        qualify(profile, step, declarations.root)


@pytest.mark.parametrize('change', ['script', 'parameter', 'source', 'data', 'output', 'extra', 'order'])
def test_changed_script_or_arguments_are_refused(profile, declarations, change):
    step = fresh(declarations)
    command = step.commands[0]
    args = list(command.args)
    if change == 'script':
        command = build.Blender(command.script.with_name('other.py'), command.args,
                                threads=3, factory_startup=True, env=command.env)
    elif change == 'parameter':
        args[1] = str(Path(args[1]).with_name('TH_P_basket.json'))
    elif change == 'source':
        args[3] = str(Path(args[3]).with_name('other.glb'))
    elif change == 'data':
        args[5] = str(Path(args[5]).with_name('other'))
    elif change == 'output':
        args[7] = str(Path(args[7]).with_name('other'))
    elif change == 'extra':
        args.append('--extra')
    else:
        args[0], args[2] = args[2], args[0]
    step = replace(step, commands=[replace(command, args=tuple(args))])
    with pytest.raises(profile.UnsupportedTreehouseProp):
        qualify(profile, step, declarations.root)


@pytest.mark.parametrize('change', ['threads', 'factory', 'env', 'alias'])
def test_changed_blender_controls_are_refused(profile, declarations, change):
    step = fresh(declarations)
    command = step.commands[0]
    if change == 'alias':
        class AliasBlender(type(command)):
            pass
        command = AliasBlender(**vars(command))
    else:
        command = replace(command, **{
            'threads': {'threads': 4}, 'factory': {'factory_startup': False}, 'env': {'env': ()},
        }[change])
    with pytest.raises(profile.UnsupportedTreehouseProp):
        qualify(profile, replace(step, commands=[command]), declarations.root)


@pytest.mark.parametrize('change', ['group', 'runtime', 'seconds', 'none', 'alias'])
def test_changed_batch_fields_are_refused(profile, declarations, change):
    step = fresh(declarations)
    if change == 'none':
        batch = None
    elif change == 'alias':
        class AliasBatch(type(step.batch)):
            pass
        batch = AliasBatch(**vars(step.batch))
    else:
        batch = replace(step.batch, **{
            'group': {'group': 'other'}, 'runtime': {'runtime_env': ('PATH',)},
            'seconds': {'max_seconds': 241.},
        }[change])
    with pytest.raises(profile.UnsupportedTreehouseProp):
        qualify(profile, replace(step, batch=batch), declarations.root)


@pytest.mark.parametrize('change', ['name', 'primary', 'data', 'extra', 'optional', 'collection', 'alias'])
def test_changed_products_or_owned_roots_are_refused(profile, declarations, change):
    step = fresh(declarations)
    products = list(step.products)
    if change == 'name':
        products[0] = replace(products[0], name='treehouse.other')
    elif change == 'primary':
        products[0] = replace(products[0], paths=(products[0].paths[0].with_name('other'),))
    elif change == 'data':
        products[1] = replace(products[1], paths=(products[1].paths[0].with_name('other.json'),))
    elif change == 'extra':
        products.append(build_products.Product('treehouse.extra', (products[0].paths[0] / 'extra',)))
    elif change == 'optional':
        products[1] = replace(products[1], optional_paths=(products[1].paths[0].with_suffix('.tmp'),))
    elif change == 'collection':
        products[0] = replace(products[0], collection='x', bounds=(0., 0., 0., 1., 1., 1.))
    else:
        class AliasProduct(type(products[0])):
            pass
        products[0] = AliasProduct(**vars(products[0]))
    with pytest.raises(profile.UnsupportedTreehouseProp):
        qualify(profile, replace(step, products=products), declarations.root)


@pytest.mark.parametrize('change', ['raw', 'raw-order', 'missing-code', 'code-order', 'extra', 'duplicate', 'alias'])
def test_changed_input_roles_or_order_are_refused(profile, declarations, change):
    step = fresh(declarations)
    inputs = list(step.inputs)
    if change == 'raw':
        inputs[-2] = inputs[-2].with_name('TH_P_basket.json')
    elif change == 'raw-order':
        inputs[-2], inputs[-1] = inputs[-1], inputs[-2]
    elif change == 'missing-code':
        inputs.pop(0)
    elif change == 'code-order':
        inputs[0], inputs[1] = inputs[1], inputs[0]
    elif change == 'extra':
        inputs.append(paths.REPO / 'games/yorimichi/region_exports.py')
    elif change == 'duplicate':
        inputs.append(inputs[-1])
    else:
        class AliasPath(type(inputs[0])):
            pass
        inputs[0] = AliasPath(str(inputs[0]))
    with pytest.raises(profile.UnsupportedTreehouseProp):
        qualify(profile, replace(step, inputs=inputs), declarations.root)


@pytest.mark.parametrize('change', ['needs', 'after', 'reads', 'references', 'outputs', 'cache', 'audit',
                                    'heavy', 'toolchain', 'replan', 'controller', 'queries', 'deferred',
                                    'checkpoint', 'candidate', 'explicit', 'cutoff', 'pool', 'alias'])
def test_changed_step_flags_or_type_are_refused(profile, declarations, change):
    step = fresh(declarations)
    values = {
        'needs': {'needs': ['world.other']}, 'after': {'after': ['world.other']}, 'reads': {'reads': ['treehouse.other']},
        'references': {'references': ['treehouse.other']}, 'outputs': {'outputs': [step.products[0].paths[0]]},
        'cache': {'cache': False}, 'audit': {'audit': True}, 'heavy': {'heavy': False},
        'toolchain': {'toolchain': False}, 'replan': {'replan': True}, 'controller': {'controller': object()},
        'queries': {'queries': [object()]}, 'deferred': {'deferred_inputs': [object()]},
        'checkpoint': {'checkpoint_restore': lambda: None}, 'candidate': {'candidate_scope': object()},
        'explicit': {'explicit': True}, 'cutoff': {'cutoff': True}, 'pool': {'pool_roots': [declarations.root]},
    }
    if change == 'alias':
        class AliasStep(type(step)):
            pass
        step = AliasStep(**vars(step))
    else:
        step = replace(step, **values[change])
    with pytest.raises(profile.UnsupportedTreehouseProp):
        qualify(profile, step, declarations.root)


def test_unknown_step_attribute_is_refused(profile, declarations):
    step = fresh(declarations)
    step.custom_authority = True
    with pytest.raises(profile.UnsupportedTreehouseProp):
        qualify(profile, step, declarations.root)


@pytest.mark.parametrize('change', ['code', 'default-root', 'encoded', 'default-type', 'WORLD', 'WORLD-type', 'str', 'closure', 'wrapper'])
def test_changed_verifier_source_or_binding_is_refused(profile, declarations, monkeypatch, change):
    step = fresh(declarations)
    function = step.verify
    if change == 'str':
        import types
        namespace = function.__globals__.copy()
        namespace['__builtins__'] = function.__builtins__.copy()
        function = types.FunctionType(function.__code__, namespace, function.__name__,
                                     function.__defaults__, function.__closure__)
        step = replace(step, verify=function)
    original_code, original_defaults = function.__code__, function.__defaults__
    original_world = function.__globals__['WORLD']
    original_str = function.__builtins__['str']
    if change == 'code':
        monkeypatch.setattr(function, '__code__', function.__code__.replace(co_name='changed'))
    elif change == 'default-root':
        monkeypatch.setattr(function, '__defaults__', (function.__defaults__[0].with_name('other'), False))
    elif change == 'encoded':
        monkeypatch.setattr(function, '__defaults__', (function.__defaults__[0], True))
    elif change == 'default-type':
        monkeypatch.setattr(function, '__defaults__', (function.__defaults__[0], 0))
    elif change == 'WORLD-type':
        class AliasPath(type(original_world)):
            pass
        monkeypatch.setitem(function.__globals__, 'WORLD', AliasPath(str(original_world)))
    elif change == 'closure':
        import types
        cell = (lambda value: lambda: value)(object()).__closure__[0]
        changed = function.__code__.replace(co_freevars=('foreign',))
        step = replace(step, verify=types.FunctionType(changed, function.__globals__, function.__name__,
                       function.__defaults__, (cell,)))
    elif change == 'WORLD':
        monkeypatch.setitem(function.__globals__, 'WORLD', function.__globals__['WORLD'].with_name('other'))
    elif change == 'str':
        monkeypatch.setitem(function.__builtins__, 'str', bytes)
    else:
        def wrapper(*args, **kwargs):
            return function(*args, **kwargs)
        step = replace(step, verify=wrapper)
    try:
        with pytest.raises(profile.UnsupportedTreehouseProp):
            qualify(profile, step, declarations.root)
    finally:
        function.__code__, function.__defaults__ = original_code, original_defaults
        function.__globals__['WORLD'] = original_world
        function.__builtins__['str'] = original_str



def finite_checkout(step, tmp_path, monkeypatch):
    """Copy only finite declared source roles; never copy/read the large raw GLB."""
    import shutil
    from atelier import source_imports
    checkout = tmp_path / 'checkout'
    for source in dict.fromkeys([*step.inputs[:-1], paths.REPO / 'games/yorimichi/region_exports.py']):
        target = checkout / source.relative_to(paths.REPO)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    model = checkout / step.inputs[-1].relative_to(paths.REPO)
    model.parent.mkdir(parents=True, exist_ok=True)
    model.write_bytes(b'raw role sentinel, not Blender geometry')
    relocated = rebound(step, tmp_path / 'output', checkout)
    # Rebind the existing scanner's installed roots to the complete finite source
    # fixture. No resolver is replaced, no whole game or generated output is copied.
    monkeypatch.setattr(paths, 'REPO', checkout)
    monkeypatch.setattr(paths, 'STUDIO', checkout / 'platform/studio')
    monkeypatch.setattr(paths, 'HARNESS', checkout / 'platform/harness')
    monkeypatch.setattr(source_imports, '__file__', str(checkout / 'platform/studio/atelier/source_imports.py'))
    return checkout, relocated, tmp_path / 'output'


def test_finite_rebound_reaches_all_checks(profile, declarations, tmp_path, monkeypatch):
    checkout, step, root = finite_checkout(fresh(declarations), tmp_path, monkeypatch)
    task = profile.qualify_treehouse_prop(step, checkout=checkout, output_root=root)
    assert task.raw_inputs[-1].read_bytes() == b'raw role sentinel, not Blender geometry'
    assert task.code_inputs == tuple(step.inputs[:-2])
    assert not root.exists()


@pytest.mark.parametrize('relative', ['world/regions/treehouse/plan_prop.py', 'region_exports.py',
    'world/regions/treehouse/prop_geometry.py', 'world/region_mesh_parts.py',
    'assets/treehouse/export-parameters/TH_P_backpack.json'])
def test_linked_source_is_refused_before_scanner_read(profile, declarations, tmp_path, monkeypatch, relative):
    checkout, step, root = finite_checkout(fresh(declarations), tmp_path, monkeypatch)
    source = checkout / 'games/yorimichi' / relative
    original_bytes = source.read_bytes()
    foreign = tmp_path / 'foreign'
    foreign.write_bytes(original_bytes)
    source.unlink()
    source.symlink_to(foreign)
    reached = []
    reader = profile._source_bytes
    def observing_reader(anchor, path):
        reached.append(path)
        return reader(anchor, path)
    monkeypatch.setattr(profile, '_source_bytes', observing_reader)
    try:
        with pytest.raises(profile.UnsupportedTreehouseProp, match='source is absent, linked or invalid'):
            profile.qualify_treehouse_prop(step, checkout=checkout, output_root=root)
        assert source in reached
    finally:
        source.unlink()
        source.write_bytes(original_bytes)
    assert foreign.read_bytes() == original_bytes


@pytest.mark.parametrize('kind', ['root', 'parent', 'raw-parent', 'model'])
def test_linked_source_anchors_and_raw_model_are_refused(profile, declarations, tmp_path, monkeypatch, kind):
    checkout, step, root = finite_checkout(fresh(declarations), tmp_path, monkeypatch)
    if kind == 'root':
        target = checkout
    elif kind == 'parent':
        target = checkout / 'games/yorimichi/world/regions/treehouse'
    elif kind == 'raw-parent':
        target = checkout / 'games/yorimichi/assets/treehouse/props/backpack'
    else:
        target = checkout / 'games/yorimichi/assets/treehouse/props/backpack/backpack.glb'
    foreign = tmp_path / 'foreign'
    target.rename(foreign)
    target.symlink_to(foreign, target_is_directory=kind != 'model')
    try:
        with pytest.raises(profile.UnsupportedTreehouseProp, match={
            'root': 'checkout is not', 'parent': 'source directory is linked',
            'raw-parent': 'raw model is absent', 'model': 'raw model is absent',
        }[kind]):
            profile.qualify_treehouse_prop(step, checkout=checkout, output_root=root)
    finally:
        target.unlink()
        foreign.rename(target)
    assert not root.exists()


@pytest.mark.parametrize('field,value', [('name', 'TH_P_barrel'), ('slug', 'barrel')])
def test_parameter_cannot_select_another_prop(profile, declarations, tmp_path, monkeypatch, field, value):
    import json
    checkout, step, root = finite_checkout(fresh(declarations), tmp_path, monkeypatch)
    parameter = step.inputs[-2]
    original = parameter.read_bytes()
    altered = json.loads(original)
    altered[field] = value
    parameter.write_text(json.dumps(altered))
    try:
        with pytest.raises(profile.UnsupportedTreehouseProp, match='parameter parent or slug differs'):
            profile.qualify_treehouse_prop(step, checkout=checkout, output_root=root)
    finally:
        parameter.write_bytes(original)
    assert parameter.read_bytes() == original and not root.exists()


@pytest.mark.parametrize('kind', ['primary', 'primary-parent', 'data', 'data-parent', 'root'])
def test_linked_outputs_are_refused_without_read_or_write(profile, declarations, tmp_path, kind):
    root = tmp_path / 'output'
    foreign = tmp_path / 'foreign'
    foreign.mkdir()
    marker = foreign / 'marker'
    marker.write_bytes(b'foreign output retained')
    target = {
        'primary': root / 'planned_exports/treehouse_props/TH_P_backpack',
        'primary-parent': root / 'planned_exports/treehouse_props',
        'data': root / 'treehouse-data/props/TH_P_backpack',
        'data-parent': root / 'treehouse-data/props', 'root': root,
    }[kind]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to(foreign, target_is_directory=True)
    before = marker.read_bytes(), marker.lstat()
    try:
        with pytest.raises(profile.UnsupportedTreehouseProp, match='output ancestor is linked or invalid'):
            qualify(profile, rebound(fresh(declarations), root), root)
    finally:
        target.unlink()
    assert (marker.read_bytes(), marker.lstat()) == before


def test_qualifier_never_calls_producer_or_verifier_or_reads_raw_model(profile, declarations, monkeypatch):
    import sys
    called = []
    def trace(frame, event, arg):
        if event == 'call':
            source = Path(frame.f_code.co_filename)
            if (source.name in ('plan_prop.py', 'prop_geometry.py', 'region_mesh_parts.py')
                    or frame.f_code.co_name == 'complete'):
                called.append((source.name, frame.f_code.co_name))
        return trace
    reader = profile._source_bytes
    def source_only(checkout, path):
        assert Path(path).suffix != '.glb'
        assert not Path(path).is_relative_to(declarations.root)
        return reader(checkout, path)
    monkeypatch.setattr(profile, '_source_bytes', source_only)
    previous = sys.gettrace()
    sys.settrace(trace)
    try:
        qualify(profile, fresh(declarations), declarations.root)
    finally:
        sys.settrace(previous)
    assert called == []


def test_observation_field_order(profile):
    assert tuple(f.name for f in fields(profile.TreehousePropPlanner)) == (
        'step', 'parent', 'script', 'arguments', 'raw_inputs', 'produced_inputs', 'code_inputs',
        'products', 'primary_root', 'data_root', 'verifier', 'batch')


@pytest.mark.parametrize('field,value', [('cache', 1), ('heavy', 1), ('toolchain', 1),
    ('audit', 0), ('after', ()), ('needs', ()), ('about', 'custom')])
def test_default_control_types_are_exact(profile, declarations, field, value):
    with pytest.raises(profile.UnsupportedTreehouseProp):
        qualify(profile, replace(fresh(declarations), **{field: value}), declarations.root)


def test_batch_observation_field_order(declarations, planners):
    step = declarations.steps['world.treehouse_props.geometry.TH_P_backpack']
    assert planners[step.name].batch == tuple(getattr(step.batch, f.name) for f in fields(build.Batch))


def test_new_linked_import_is_checked_before_scanner_read(profile, declarations, tmp_path, monkeypatch):
    checkout, step, root = finite_checkout(fresh(declarations), tmp_path, monkeypatch)
    script = step.commands[0].script
    original = script.read_bytes()
    source = script.parent / 'never_declared.py'
    foreign = tmp_path / 'foreign.py'
    foreign.write_bytes(b'raise AssertionError("source body must not execute")\n')
    source.symlink_to(foreign)
    script.write_bytes(original + b'\nimport never_declared\n')
    reached = []
    reader = profile._source_bytes
    def observing_reader(anchor, path):
        reached.append(path)
        return reader(anchor, path)
    monkeypatch.setattr(profile, '_source_bytes', observing_reader)
    try:
        with pytest.raises(profile.UnsupportedTreehouseProp, match='source is absent, linked or invalid'):
            profile.qualify_treehouse_prop(step, checkout=checkout, output_root=root)
        assert source in reached
    finally:
        script.write_bytes(original)
        source.unlink()
    assert not root.exists()


@pytest.mark.parametrize('kind', ['command', 'batch', 'product'])
def test_unknown_metadata_attributes_are_refused(profile, declarations, kind):
    step = fresh(declarations)
    target = {'command': step.commands[0], 'batch': step.batch, 'product': step.products[0]}[kind]
    object.__setattr__(target, 'foreign', True)
    try:
        with pytest.raises(profile.UnsupportedTreehouseProp):
            qualify(profile, step, declarations.root)
    finally:
        object.__delattr__(target, 'foreign')
