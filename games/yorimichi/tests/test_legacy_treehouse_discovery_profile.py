"""Actual-Graph Treehouse discovery observations; callbacks and helpers never execute."""
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier import build, build_products, export_tasks, paths


@pytest.fixture(scope='module')
def profile():
    source = paths.REPO / 'games/yorimichi/legacy_treehouse_discovery_profile.py'
    spec = importlib.util.spec_from_file_location('legacy_treehouse_discovery_test', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def declarations(tmp_path_factory):
    from atelier.build_v2.controller_entry import declaration_context
    root = tmp_path_factory.mktemp('treehouse-discovery-cold') / 'yorimichi'
    ctx = declaration_context('yorimichi')
    ctx.out = root
    steps = build.load_recipe('yorimichi').steps(ctx)
    build.check_declarations(steps)
    graph = build_products.Graph(steps)
    selected = graph.select(['world.treehouse_trees.geometry'])
    step = next(step for step in selected if step.name == 'world.treehouse_trees.geometry')
    return SimpleNamespace(root=root, step=step)


@pytest.fixture(scope='module')
def discovery(profile, declarations):
    assert not declarations.root.exists()
    observed = profile.qualify_treehouse_discovery(
        declarations.step, checkout=paths.REPO, output_root=declarations.root)
    assert not declarations.root.exists()
    return observed


def fresh(declarations):
    return deepcopy(declarations.step)


def qualify(profile, step, root, checkout=paths.REPO):
    return profile.qualify_treehouse_discovery(step, checkout=checkout, output_root=root)


def captured_function(function, checkout, name=None):
    """Load one finite helper through its captured logical source bytes."""
    from atelier.build_v2.legacy_qualification import CapturedCode, captured_spec
    original = paths.REPO / Path(function.__code__.co_filename).relative_to(paths.REPO)
    source_path = checkout / original.relative_to(paths.REPO)
    spec = captured_spec(name or function.__module__, CapturedCode(str(source_path), source_path.read_bytes()))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, function.__name__)
    """Load a finite source helper or provider under a private test module name."""
    module_file = function.__code__.co_filename if hasattr(function, '__code__') else function.__file__
    original = paths.REPO / Path(module_file).relative_to(paths.REPO)
    source_path = checkout / original.relative_to(paths.REPO)
    module_name = name or function.__name__
    namespace = {'__file__': str(source_path), '__name__': module_name,
                 '__package__': module_name.rpartition('.')[0]}
    exec(compile(source_path.read_bytes(), str(source_path), 'exec'), namespace)
    if not hasattr(function, '__code__'):
        return SimpleNamespace(**namespace)
    return namespace[function.__name__]


def rebound(step, root, checkout=None):
    old_root = step.products[0].paths[0].parents[2]
    old_checkout = Path(step.inputs[0]).parents[2]
    def output(value):
        return root / Path(value).relative_to(old_root)
    inputs = list(step.inputs)
    if checkout is not None:
        inputs = [checkout / value.relative_to(old_checkout) for value in inputs]
    products = [replace(step.products[0], paths=(output(step.products[0].paths[0]),))]
    fn = step.commands[0].fn
    cells = {name: cell.cell_contents for name, cell in zip(fn.__code__.co_freevars, fn.__closure__)}
    cells['discovery'] = output(cells['discovery'])
    cells['logical'] = [(parent, output(root_path), *rest) for parent, root_path, *rest in cells['logical']]
    namespace = fn.__globals__
    if checkout is not None:
        namespace = namespace.copy()
        inventory = captured_function(namespace['inventory'], checkout)
        namespace['inventory'] = inventory
        namespace['atomic_json'] = captured_function(namespace['atomic_json'], checkout)
        inventory.__globals__['member'] = captured_function(inventory.__globals__['member'], checkout)
    import types
    callback = types.FunctionType(fn.__code__, namespace, fn.__name__, fn.__defaults__, tuple(
        types.CellType(cells[name]) for name in fn.__code__.co_freevars))
    return replace(step, commands=[build.Call(step.commands[0].name, callback)], inputs=inputs, products=products)


def test_actual_graph_discovery_binds_exact_frozen_roles(declarations, discovery):
    step = declarations.step
    assert discovery.step == step.name and discovery.region == 'treehouse_trees'
    assert discovery.products == ((step.products[0].name, step.products[0].paths),)
    assert discovery.code_inputs[:len(step.inputs)] == tuple(step.inputs)
    assert discovery.code_inputs[-1] == paths.REPO / 'platform/studio/atelier/export_tasks.py'
    assert len(discovery.code_inputs) == len(set(discovery.code_inputs)) == 7
    assert discovery.produced_inputs == tuple(row[1] for row in discovery.logical)
    assert discovery.logical == tuple(
        (parent, declarations.root / 'planned_exports/treehouse_trees' / parent,
         f'world.treehouse_trees.geometry.{parent}', f'treehouse_trees.geometry.{parent}', 'mesh_ir')
        for parent in ('Tree_Canopy_Maple', 'Tree_Canopy_Crimson', 'Tree_Canopy_Amber', 'Tree_Canopy_Ginkgo'))
    assert discovery.callback.qualname == 'steps.<locals>.discover'
    assert discovery.inventory.qualname == 'inventory'
    assert discovery.callback.filename == discovery.inventory.filename == str(paths.REPO / 'games/yorimichi/region_exports.py')
    assert discovery.callback.binding_names == (
        'ValueError', 'atomic_json', 'dict', 'discovery', 'inventory', 'len', 'logical', 'map', 'region', 'sum')
    with pytest.raises(FrozenInstanceError):
        discovery.region = 'other'


def test_warm_planner_roots_and_record_are_preserved(profile, declarations, tmp_path):
    root = tmp_path / 'warm'
    step = rebound(fresh(declarations), root)
    existing = {row[1] / 'plan.json': b'foreign plan' for row in profile_rows(root)}
    existing[root / 'planned_exports/treehouse_trees/discovery.json'] = b'foreign discovery'
    for path, content in existing.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    before = {path: (path.read_bytes(), path.lstat()) for path in existing}
    observed = qualify(profile, step, root)
    assert observed.produced_inputs == tuple(row[1] for row in profile_rows(root))
    assert all((path.read_bytes(), path.lstat()) == before[path] for path in existing)


def profile_rows(root):
    return tuple((parent, root / 'planned_exports/treehouse_trees' / parent)
                 for parent in ('Tree_Canopy_Maple', 'Tree_Canopy_Crimson', 'Tree_Canopy_Amber', 'Tree_Canopy_Ginkgo'))


def test_callbacks_and_helpers_are_never_executed(profile, declarations):
    counters = []
    step = fresh(declarations)
    original = step.commands[0].fn
    def forbidden(*args, **kwargs):
        counters.append('executed')
        raise AssertionError('discovery callback executed')
    step.commands[0] = build.Call('discover treehouse_trees', forbidden)
    with pytest.raises(profile.UnsupportedTreehouseDiscovery):
        qualify(profile, step, declarations.root)
    assert counters == []
    assert original.__qualname__ == 'steps.<locals>.discover'


@pytest.mark.parametrize('name', ['other', 'world.treehouse_trees.geometry.Tree_Canopy_Maple', 'world.treehouse_props.geometry'])
def test_wrong_step_is_refused(profile, declarations, name):
    with pytest.raises(profile.UnsupportedTreehouseDiscovery):
        qualify(profile, replace(fresh(declarations), name=name), declarations.root)


@pytest.mark.parametrize('change', ['name', 'python', 'extra', 'wrapper'])
def test_wrong_call_or_wrapper_is_refused(profile, declarations, change):
    step = fresh(declarations)
    if change == 'name':
        commands = [build.Call('other', step.commands[0].fn)]
    elif change == 'python':
        commands = [build.Python(step.inputs[0], ())]
    elif change == 'extra':
        commands = [*step.commands, build.Call('other', step.commands[0].fn)]
    else:
        commands = [build.Call(step.commands[0].name, lambda: None)]
    with pytest.raises(profile.UnsupportedTreehouseDiscovery):
        qualify(profile, replace(step, commands=commands), declarations.root)


@pytest.mark.parametrize('change', ['replan', 'cache', 'audit', 'heavy', 'toolchain', 'batch', 'controller',
                                    'needs', 'after', 'outputs', 'references', 'queries', 'candidate', 'alias'])
def test_wrong_step_flags_are_refused(profile, declarations, change):
    step = fresh(declarations)
    values = {'replan': {'replan': False}, 'cache': {'cache': True}, 'audit': {'audit': True},
              'heavy': {'heavy': True}, 'toolchain': {'toolchain': True},
              'batch': {'batch': build.Batch('other')}, 'controller': {'controller': object()},
              'needs': {'needs': ['world.textures']}, 'after': {'after': ['world.other']},
              'outputs': {'outputs': [step.products[0].paths[0]]}, 'references': {'references': ['other']},
              'queries': {'queries': [object()]}, 'candidate': {'candidate_scope': object()}}
    if change == 'alias':
        class AliasStep(type(step)):
            pass
        step = AliasStep(**vars(step))
    else:
        step = replace(step, **values[change])
    with pytest.raises(profile.UnsupportedTreehouseDiscovery):
        qualify(profile, step, declarations.root)


@pytest.mark.parametrize('change', ['missing', 'order', 'extra', 'duplicate'])
def test_wrong_reads_are_refused(profile, declarations, change):
    step = fresh(declarations)
    reads = list(step.reads)
    if change == 'missing':
        reads.pop()
    elif change == 'order':
        reads[0], reads[1] = reads[1], reads[0]
    elif change == 'extra':
        reads.append('treehouse.other')
    else:
        reads.append(reads[-1])
    with pytest.raises(profile.UnsupportedTreehouseDiscovery):
        qualify(profile, replace(step, reads=reads), declarations.root)


@pytest.mark.parametrize('change', ['name', 'path', 'extra', 'optional', 'collection', 'alias'])
def test_wrong_product_is_refused(profile, declarations, change):
    step = fresh(declarations)
    products = list(step.products)
    if change == 'name':
        products[0] = replace(products[0], name='other')
    elif change == 'path':
        products[0] = replace(products[0], paths=(products[0].paths[0].with_name('other.json'),))
    elif change == 'extra':
        products.append(build_products.Product('other', (step.products[0].paths[0].with_name('other.json'),)))
    elif change == 'optional':
        products[0] = replace(products[0], optional_paths=(products[0].paths[0].with_suffix('.tmp'),))
    elif change == 'collection':
        products[0] = replace(products[0], collection='x', bounds=(0., 0., 0., 1., 1., 1.))
    else:
        class AliasProduct(type(products[0])):
            pass
        products[0] = AliasProduct(**vars(products[0]))
    with pytest.raises(profile.UnsupportedTreehouseDiscovery):
        qualify(profile, replace(step, products=products), declarations.root)


@pytest.mark.parametrize('change', ['region-source', 'runtime', 'order', 'extra', 'duplicate'])
def test_wrong_inputs_are_refused(profile, declarations, change):
    step = fresh(declarations)
    inputs = list(step.inputs)
    if change == 'region-source':
        inputs[0] = inputs[0].with_name('other.py')
    elif change == 'runtime':
        inputs[2] = inputs[2].with_name('other.py')
    elif change == 'order':
        inputs[1], inputs[2] = inputs[2], inputs[1]
    elif change == 'extra':
        inputs.append(paths.REPO / 'platform/studio/atelier/export_tasks.py')
    else:
        inputs.append(inputs[-1])
    with pytest.raises(profile.UnsupportedTreehouseDiscovery):
        qualify(profile, replace(step, inputs=inputs), declarations.root)


def callback_with_cells(step, changes):
    import types
    fn = step.commands[0].fn
    cells = {name: cell.cell_contents for name, cell in zip(fn.__code__.co_freevars, fn.__closure__)}
    cells.update(changes)
    callback = types.FunctionType(fn.__code__, fn.__globals__, fn.__name__, fn.__defaults__,
        tuple(types.CellType(cells[name]) for name in fn.__code__.co_freevars))
    return replace(step, commands=[build.Call(step.commands[0].name, callback)])


@pytest.mark.parametrize('change', ['parent', 'root', 'task', 'product', 'encoding', 'order', 'extra', 'discovery', 'region'])
def test_wrong_callback_closure_is_refused(profile, declarations, change):
    step = fresh(declarations)
    fn = step.commands[0].fn
    cells = {name: cell.cell_contents for name, cell in zip(fn.__code__.co_freevars, fn.__closure__)}
    logical = list(cells['logical'])
    if change in ('parent', 'root', 'task', 'product', 'encoding'):
        row = list(logical[0])
        index = {'parent': 0, 'root': 1, 'task': 2, 'product': 3, 'encoding': 4}[change]
        row[index] = 'other' if change != 'root' else row[1].with_name('other')
        logical[0] = tuple(row)
    elif change == 'order':
        logical[0], logical[1] = logical[1], logical[0]
    elif change == 'extra':
        logical.append(logical[-1])
    changes = {'logical': logical}
    if change == 'discovery':
        changes = {'discovery': cells['discovery'].with_name('other.json')}
    elif change == 'region':
        changes = {'region': 'other'}
    with pytest.raises(profile.UnsupportedTreehouseDiscovery):
        qualify(profile, callback_with_cells(step, changes), declarations.root)


@pytest.mark.parametrize('change', ['callback-code', 'callback-default', 'inventory-code', 'inventory-default',
                                    'inventory-global', 'callback-global', 'builtin', 'inventory-builtin'])
def test_wrong_callback_or_inventory_source_binding_is_refused(profile, declarations, monkeypatch, change):
    step = fresh(declarations)
    callback = step.commands[0].fn
    inventory = callback.__globals__['inventory']
    if change == 'callback-code':
        monkeypatch.setattr(callback, '__code__', callback.__code__.replace(co_name='other'))
    elif change == 'callback-default':
        monkeypatch.setattr(callback, '__defaults__', (None,))
    elif change == 'inventory-code':
        monkeypatch.setattr(inventory, '__code__', inventory.__code__.replace(co_name='other'))
    elif change == 'inventory-default':
        monkeypatch.setattr(inventory, '__kwdefaults__', {'encoding': 'encoded_glb'})
    elif change == 'inventory-global':
        monkeypatch.setitem(inventory.__globals__, 'os', object())
    elif change == 'callback-global':
        monkeypatch.setitem(callback.__globals__, 'atomic_json', object())
    else:
        namespace = callback.__globals__.copy() if change == 'builtin' else inventory.__globals__.copy()
        namespace['__builtins__'] = namespace['__builtins__'].copy()
        import types
        fn = callback if change == 'builtin' else inventory
        rebound_fn = types.FunctionType(fn.__code__, namespace, fn.__name__, fn.__defaults__, fn.__closure__)
        rebound_fn.__kwdefaults__ = fn.__kwdefaults__
        if change == 'builtin':
            rebound_fn.__builtins__['len'] = object()
            step = replace(step, commands=[build.Call(step.commands[0].name, rebound_fn)])
        else:
            rebound_fn.__builtins__['set'] = object()
            monkeypatch.setitem(callback.__globals__, 'inventory', rebound_fn)
    with pytest.raises(profile.UnsupportedTreehouseDiscovery):
        qualify(profile, step, declarations.root)


@pytest.mark.parametrize('change', ['name-code', 'name-global', 'name-regex', 'name-flags', 'limit',
                                    'real-code', 'real-default', 'real-global', 'member-code',
                                    'member-global', 'atomic-code', 'atomic-global', 'member-wrapper'])
def test_poisoned_helper_source_or_binding_is_refused(profile, declarations, monkeypatch, change):
    import atelier.atomic_files as atomic_files
    import atelier.export_manifest as manifest
    import atelier.model_files as model_files
    step = fresh(declarations)
    if change.startswith('name-'):
        helper = manifest.name
    elif change.startswith('real-'):
        helper = manifest.real_directory
    elif change.startswith('member-'):
        helper = model_files.member
    else:
        helper = atomic_files.atomic_json
    if change.endswith('-code'):
        monkeypatch.setattr(helper, '__code__', helper.__code__.replace(co_name='other'))
    elif change.endswith('-default'):
        monkeypatch.setattr(helper, '__kwdefaults__', {'create': True})
    elif change.endswith('-global'):
        key = {'name': 'NAME', 'real': 'Path', 'member': 'PurePosixPath', 'atomic': 'json'}[change.split('-')[0]]
        monkeypatch.setitem(helper.__globals__, key, object())
    elif change == 'name-regex':
        import re
        monkeypatch.setattr(manifest, 'NAME', re.compile('.*', re.ASCII))
    elif change == 'name-flags':
        import re
        monkeypatch.setattr(manifest, 'NAME', re.compile(manifest.NAME.pattern))
    elif change == 'limit':
        monkeypatch.setattr(export_tasks, 'TRIANGLE_LIMIT', 1)
    elif change == 'member-wrapper':
        monkeypatch.setattr(model_files, 'member', lambda value: value)
    with pytest.raises(profile.UnsupportedTreehouseDiscovery):
        qualify(profile, step, declarations.root)


def finite_checkout(step, tmp_path):
    import shutil
    checkout = tmp_path / 'checkout'
    original = Path(step.inputs[0]).parents[2]
    for source in [*step.inputs, original / 'platform/studio/atelier/export_tasks.py']:
        target = checkout / source.relative_to(original)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return checkout


@pytest.mark.parametrize('relative', ['games/yorimichi/region_exports.py',
                                      'platform/studio/atelier/export_manifest.py',
                                      'platform/studio/atelier/model_files.py',
                                      'platform/studio/atelier/atomic_files.py'])
def test_linked_source_reaches_intended_nofollow_refusal(profile, declarations, tmp_path, relative):
    checkout = finite_checkout(fresh(declarations), tmp_path)
    step = rebound(fresh(declarations), declarations.root, checkout)
    source = checkout / relative
    original_bytes = source.read_bytes()
    foreign = tmp_path / 'foreign'
    foreign.write_bytes(original_bytes)
    source.unlink()
    source.symlink_to(foreign)
    reached = []
    original_reader = profile._source
    def observing_reader(checkout_arg, path_arg):
        reached.append(Path(path_arg))
        return original_reader(checkout_arg, path_arg)
    profile._source = observing_reader
    try:
        with pytest.raises(profile.UnsupportedTreehouseDiscovery):
            qualify(profile, step, declarations.root, checkout)
    finally:
        profile._source = original_reader
    assert source in reached
    assert foreign.read_bytes() == original_bytes


@pytest.mark.parametrize('kind', ['planner-root', 'planner-parent', 'discovery-parent', 'discovery-file'])
def test_linked_output_is_refused_without_changing_bytes(profile, declarations, tmp_path, kind):
    root = tmp_path / 'output'
    step = rebound(fresh(declarations), root)
    foreign = tmp_path / 'foreign'
    foreign.mkdir()
    marker = foreign / 'marker'
    marker.write_bytes(b'preserve output')
    planner = root / 'planned_exports/treehouse_trees/Tree_Canopy_Maple'
    discovery = root / 'planned_exports/treehouse_trees/discovery.json'
    if kind == 'planner-root':
        planner.parent.mkdir(parents=True)
        planner.symlink_to(foreign, target_is_directory=True)
    elif kind == 'planner-parent':
        planner.parent.parent.mkdir(parents=True)
        planner.parent.symlink_to(foreign, target_is_directory=True)
    elif kind == 'discovery-parent':
        discovery.parent.parent.mkdir(parents=True)
        discovery.parent.symlink_to(foreign, target_is_directory=True)
    else:
        discovery.parent.mkdir(parents=True)
        discovery.symlink_to(marker)
    with pytest.raises(profile.UnsupportedTreehouseDiscovery):
        qualify(profile, step, root)
    assert marker.read_bytes() == b'preserve output'


def test_missing_source_is_honest_refusal(profile, declarations, tmp_path):
    with pytest.raises(profile.UnsupportedTreehouseDiscovery):
        qualify(profile, fresh(declarations), declarations.root, tmp_path / 'absent')
    assert not declarations.root.exists()
