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
    source = paths.REPO / 'games/yorimichi/legacy_treehouse_profile.py'
    spec = importlib.util.spec_from_file_location('legacy_treehouse_profile_test', source)
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
    selected = graph.select(['world.treehouse_trees.geometry'])
    names = {f'world.treehouse_trees.geometry.{parent}' for parent in
             ('Tree_Canopy_Maple', 'Tree_Canopy_Crimson', 'Tree_Canopy_Amber', 'Tree_Canopy_Ginkgo')}
    planners = [step for step in selected if step.name in names]
    assert len(planners) == 4
    return SimpleNamespace(root=output_root, steps={step.name: step for step in planners})


@pytest.fixture(scope='module')
def planners(profile, declarations):
    assert not declarations.root.exists()
    observed = {name: profile.qualify_treehouse_planner(
        step, checkout=paths.REPO, output_root=declarations.root)
        for name, step in declarations.steps.items()}
    assert not declarations.root.exists(), 'cold qualification must not create the output root'
    return observed


def fresh(declarations, parent='Tree_Canopy_Maple'):
    """Deepcopy mutable declarations; each test owns its mutations."""
    return deepcopy(declarations.steps[f'world.treehouse_trees.geometry.{parent}'])


def rebound(step, output_root, checkout=None):
    """Apply real Context relocation, optionally to another complete source checkout."""
    old_root = Path(step.commands[0].args[5]).parents[2]
    source_checkout = step.commands[0].script
    old_checkout = source_checkout.parents[5]
    def path(value):
        return output_root / Path(value).relative_to(old_root)
    args = list(step.commands[0].args)
    args[3] = str(path(args[3]))
    args[5] = str(path(args[5]))
    if checkout is not None:
        args[1] = str(checkout / Path(args[1]).relative_to(old_checkout))
    command = step.commands[0]
    if checkout is not None:
        command = replace(command, script=checkout / command.script.relative_to(old_checkout))
    commands = [replace(command, args=tuple(args))]
    inputs = [path(value) if Path(value).is_relative_to(old_root) else
              checkout / Path(value).relative_to(old_checkout) if checkout is not None else value
              for value in step.inputs]
    products = [replace(product, paths=tuple(path(value) for value in product.paths)) for product in step.products]
    verify = step.verify
    if verify is not None:
        import types
        verify = types.FunctionType(verify.__code__, verify.__globals__, verify.__name__,
                                    (path(verify.__defaults__[0]), verify.__defaults__[1]), verify.__closure__)
    return replace(step, commands=commands, inputs=inputs, products=products, verify=verify)


def qualify(profile, step, root):
    return profile.qualify_treehouse_planner(step, checkout=paths.REPO, output_root=root)


def test_actual_graph_planners_bind_all_original_roles(profile, declarations, planners):
    for name, step in declarations.steps.items():
        task = planners[name]
        parent = name.rsplit('.', 1)[1]
        command, = step.commands
        assert task.step == name and task.parent == parent
        assert task.script == command.script == paths.REPO / 'games/yorimichi/world/regions/treehouse/plan_tree.py'
        assert task.arguments == command.args
        assert task.arguments == ('--parameters', str(task.raw_inputs[0]), '--record', str(task.record),
                                  '--output', str(task.primary_root))
        assert task.raw_inputs == (paths.REPO / f'games/yorimichi/assets/treehouse/export-parameters/{parent}.json',)
        assert task.produced_inputs == (declarations.root / 'textures/T_bark.jpg',
                                       declarations.root / 'textures/T_leaf_maple.png')
        assert task.code_inputs == tuple(step.inputs[:len(task.code_inputs)])
        assert step.inputs == [*task.code_inputs, *task.raw_inputs, *task.produced_inputs]
        assert task.products == ((f'treehouse_trees.geometry.{parent}', (task.primary_root,)),
                                 (f'treehouse.canopy_record.{parent}', (task.record,)))
        assert task.primary_root == declarations.root / 'planned_exports/treehouse_trees' / parent
        assert task.record == declarations.root / 'treehouse-data/canopy/records' / f'{parent}.json'
        assert task.batch == ('treehouse_trees logical geometry', (), 240.)
        assert task.verifier.filename == str(paths.REPO / 'games/yorimichi/region_exports.py')
        assert task.verifier.qualname == 'steps.<locals>.complete'
        assert task.verifier.binding_names == ('WORLD', 'str')
        assert len(task.verifier.source_digest) == 64
        with pytest.raises(FrozenInstanceError):
            task.parent = 'changed'


def test_warm_outputs_and_produced_inputs_are_not_adopted_or_changed(profile, declarations, planners, tmp_path):
    root = tmp_path / 'warm'
    parent = 'Tree_Canopy_Maple'
    paths_to_make = {
        root / f'planned_exports/treehouse_trees/{parent}/plan.json': b'foreign plan',
        root / f'treehouse-data/canopy/records/{parent}.json': b'foreign record',
        root / 'textures/T_bark.jpg': b'foreign bark',
        root / 'textures/T_leaf_maple.png': b'foreign leaf',
    }
    for path, content in paths_to_make.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    before = {path: (path.read_bytes(), path.lstat()) for path in paths_to_make}
    task = qualify(profile, rebound(fresh(declarations), root), root)
    assert task.primary_root.exists() and task.record.exists()
    assert all((path.read_bytes(), path.lstat()) == state for path, state in before.items())
    assert task.verifier == planners[f'world.treehouse_trees.geometry.{parent}'].verifier


def test_qualification_does_not_execute_verifier(profile, declarations, monkeypatch):
    step = fresh(declarations)
    def forbidden(*args, **kwargs):
        raise AssertionError('verifier executed during observation')
    monkeypatch.setattr(step.verify, '__code__', forbidden.__code__)
    with pytest.raises((UnsupportedOrigin, profile.UnsupportedTreehouse)):
        qualify(profile, step, declarations.root)


@pytest.mark.parametrize('parent', ['Tree_Canopy_Future', 'Tree_Canopy', '', 'Tree_Canopy_Maple.extra'])
def test_unknown_or_future_parent_is_refused(profile, declarations, parent):
    step = replace(fresh(declarations), name='world.treehouse_trees.geometry.' + parent)
    with pytest.raises(profile.UnsupportedTreehouse):
        qualify(profile, step, declarations.root)


@pytest.mark.parametrize('change', ['script', 'parameter', 'record', 'output', 'extra', 'order'])
def test_changed_script_or_arguments_are_refused(profile, declarations, change):
    step = fresh(declarations)
    command = step.commands[0]
    args = list(command.args)
    if change == 'script':
        command = build.Blender(command.script.with_name('other.py'), command.args,
                                threads=3, factory_startup=True, env=command.env)
    elif change == 'parameter':
        args[1] = str(Path(args[1]).with_name('Tree_Canopy_Amber.json'))
    elif change == 'record':
        args[3] = str(Path(args[3]).with_name('other.json'))
    elif change == 'output':
        args[5] = str(Path(args[5]).with_name('other'))
    elif change == 'extra':
        args.append('--extra')
    else:
        args[0], args[2] = args[2], args[0]
    step = replace(step, commands=[replace(command, args=tuple(args))])
    with pytest.raises(profile.UnsupportedTreehouse):
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
    with pytest.raises(profile.UnsupportedTreehouse):
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
    with pytest.raises(profile.UnsupportedTreehouse):
        qualify(profile, replace(step, batch=batch), declarations.root)


@pytest.mark.parametrize('change', ['name', 'primary', 'record', 'extra', 'optional', 'collection', 'alias'])
def test_changed_products_or_owned_roots_are_refused(profile, declarations, change):
    step = fresh(declarations)
    products = list(step.products)
    if change == 'name':
        products[0] = replace(products[0], name='treehouse.other')
    elif change == 'primary':
        products[0] = replace(products[0], paths=(products[0].paths[0].with_name('other'),))
    elif change == 'record':
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
    with pytest.raises(profile.UnsupportedTreehouse):
        qualify(profile, replace(step, products=products), declarations.root)


@pytest.mark.parametrize('change', ['raw', 'produced', 'missing-code', 'code-order', 'extra', 'duplicate', 'alias'])
def test_changed_input_roles_or_order_are_refused(profile, declarations, change):
    step = fresh(declarations)
    inputs = list(step.inputs)
    if change == 'raw':
        inputs[-3] = inputs[-3].with_name('Tree_Canopy_Amber.json')
    elif change == 'produced':
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
    with pytest.raises(profile.UnsupportedTreehouse):
        qualify(profile, replace(step, inputs=inputs), declarations.root)


@pytest.mark.parametrize('change', ['needs', 'after', 'reads', 'references', 'outputs', 'cache', 'audit',
                                    'heavy', 'toolchain', 'replan', 'controller', 'queries', 'deferred',
                                    'checkpoint', 'candidate', 'explicit', 'cutoff', 'pool', 'alias'])
def test_changed_step_flags_or_type_are_refused(profile, declarations, change):
    step = fresh(declarations)
    values = {
        'needs': {'needs': []}, 'after': {'after': ['world.other']}, 'reads': {'reads': ['treehouse.other']},
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
    with pytest.raises(profile.UnsupportedTreehouse):
        qualify(profile, step, declarations.root)


def test_unknown_step_attribute_is_refused(profile, declarations):
    step = fresh(declarations)
    step.custom_authority = True
    with pytest.raises(profile.UnsupportedTreehouse):
        qualify(profile, step, declarations.root)


@pytest.mark.parametrize('change', ['code', 'default-root', 'encoded', 'WORLD', 'str', 'wrapper'])
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
    if change == 'code':
        monkeypatch.setattr(function, '__code__', function.__code__.replace(co_name='changed'))
    elif change == 'default-root':
        monkeypatch.setattr(function, '__defaults__', (function.__defaults__[0].with_name('other'), False))
    elif change == 'encoded':
        monkeypatch.setattr(function, '__defaults__', (function.__defaults__[0], True))
    elif change == 'WORLD':
        monkeypatch.setitem(function.__globals__, 'WORLD', function.__globals__['WORLD'].with_name('other'))
    elif change == 'str':
        monkeypatch.setitem(function.__builtins__, 'str', bytes)
    else:
        def wrapper(*args, **kwargs):
            return function(*args, **kwargs)
        step = replace(step, verify=wrapper)
    try:
        with pytest.raises(profile.UnsupportedTreehouse):
            qualify(profile, step, declarations.root)
    finally:
        if change == 'str':
            function.__builtins__['str'] = str


def finite_checkout(step, tmp_path):
    """Copy only the declaration's finite source roles and fixed source directories."""
    import shutil
    checkout = tmp_path / 'checkout'
    original_checkout = step.commands[0].script.parents[5]
    sources = [*step.inputs, step.commands[0].script,
               original_checkout / 'games/yorimichi/region_exports.py']
    for source in dict.fromkeys(sources):
        source = Path(source)
        if not source.is_relative_to(original_checkout):
            continue
        target = checkout / source.relative_to(original_checkout)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    for relative in ('games/yorimichi/world/regions/treehouse',
                     'games/yorimichi/assets/treehouse/export-parameters',
                     'platform/studio/atelier/blender'):
        (checkout / relative).mkdir(parents=True, exist_ok=True)
    return checkout


@pytest.mark.parametrize('relative', ['world/regions/treehouse/plan_tree.py', 'region_exports.py',
                                      'assets/treehouse/export-parameters/Tree_Canopy_Maple.json'])
def test_linked_source_file_is_refused_before_read(profile, declarations, tmp_path, relative):
    checkout = finite_checkout(fresh(declarations), tmp_path)
    rebound_step = rebound(fresh(declarations), declarations.root, checkout)
    source = checkout / 'games/yorimichi' / relative
    original_bytes = source.read_bytes()
    foreign = tmp_path / 'foreign'
    foreign.write_bytes(original_bytes)
    source.unlink()
    source.symlink_to(foreign)
    reached = []
    original_reader = profile._source_bytes
    def observing_reader(checkout_arg, path_arg):
        reached.append(Path(path_arg))
        return original_reader(checkout_arg, path_arg)
    profile._source_bytes = observing_reader
    try:
        with pytest.raises(profile.UnsupportedTreehouse):
            qualify_checkout(profile, rebound_step, checkout, declarations.root)
    finally:
        profile._source_bytes = original_reader
    assert source in reached, 'the intended linked source must reach the anchored reader'
    assert foreign.read_bytes() == original_bytes


def qualify_checkout(profile, step, checkout, root):
    return profile.qualify_treehouse_planner(step, checkout=checkout, output_root=root)


def test_linked_source_parent_is_refused_before_source_inspection(profile, declarations, tmp_path):
    checkout = finite_checkout(fresh(declarations), tmp_path)
    step = rebound(fresh(declarations), declarations.root, checkout)
    parent = checkout / 'games/yorimichi/world/regions/treehouse'
    foreign = tmp_path / 'foreign'
    parent.rename(foreign)
    parent.symlink_to(foreign, target_is_directory=True)
    with pytest.raises(profile.UnsupportedTreehouse, match='source directory is linked'):
        qualify_checkout(profile, step, checkout, declarations.root)
    assert (foreign / 'plan_tree.py').is_file()


@pytest.mark.parametrize('kind', ['primary-root', 'primary-parent', 'record-parent', 'produced-parent', 'linked-output'])
def test_linked_or_invalid_output_role_is_refused_without_changes(profile, declarations, tmp_path, kind):
    root = tmp_path / 'output'
    foreign = tmp_path / 'foreign'
    foreign.mkdir()
    marker = foreign / 'marker'
    marker.write_bytes(b'preserve foreign output')
    parent = 'Tree_Canopy_Maple'
    primary = root / 'planned_exports/treehouse_trees' / parent
    record = root / 'treehouse-data/canopy/records' / f'{parent}.json'
    if kind == 'primary-root':
        primary.parent.mkdir(parents=True)
        primary.symlink_to(foreign, target_is_directory=True)
    elif kind == 'primary-parent':
        primary.parent.parent.mkdir(parents=True)
        primary.parent.symlink_to(foreign, target_is_directory=True)
    elif kind == 'record-parent':
        record.parent.parent.mkdir(parents=True)
        record.parent.symlink_to(foreign, target_is_directory=True)
    elif kind == 'produced-parent':
        root.mkdir(parents=True)
        (root / 'textures').symlink_to(foreign, target_is_directory=True)
    else:
        record.parent.mkdir(parents=True)
        record.symlink_to(marker)
    with pytest.raises(profile.UnsupportedTreehouse):
        qualify(profile, rebound(fresh(declarations), root), root)
    assert marker.read_bytes() == b'preserve foreign output'


def test_missing_checkout_is_an_honest_refusal(profile, declarations, tmp_path):
    checkout = tmp_path / 'absent'
    with pytest.raises(profile.UnsupportedTreehouse):
        qualify_checkout(profile, fresh(declarations), checkout, declarations.root)
    assert not checkout.exists() and not declarations.root.exists()


def test_batch_observation_preserves_exact_dataclass_field_order(declarations, planners):
    step = declarations.steps['world.treehouse_trees.geometry.Tree_Canopy_Maple']
    task = planners[step.name]
    assert task.batch == tuple(getattr(step.batch, field.name) for field in fields(build.Batch))
