"""Actual-Graph Treehouse assembly observations; no assembly/helper execution."""
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier import build, build_products, export_assembly, export_manifest, model_files, paths


PARENTS = ('Tree_Canopy_Maple', 'Tree_Canopy_Crimson', 'Tree_Canopy_Amber', 'Tree_Canopy_Ginkgo')


@pytest.fixture(scope='module')
def profile():
    source = paths.REPO / 'games/yorimichi/legacy_treehouse_assembly_profile.py'
    spec = importlib.util.spec_from_file_location('legacy_treehouse_assembly_test', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def declarations(tmp_path_factory):
    from atelier.build_v2.controller_entry import declaration_context
    root = tmp_path_factory.mktemp('treehouse-assembly-cold') / 'yorimichi'
    for parent, triangles in zip(PARENTS, (2664, 2568, 2544, 2344)):
        folder = root / 'planned_exports/treehouse_trees' / parent
        folder.mkdir(parents=True)
        (folder / 'plan.json').write_text(json.dumps(dict(
            schema=1, parent=parent, complete=True, triangle_limit=32768,
            source_triangles=triangles,
            pieces=[dict(name=parent, payload=f'{parent}.npz', triangles=triangles)])))
    ctx = declaration_context('yorimichi')
    ctx.out = root
    steps = build.load_recipe('yorimichi').steps(ctx)
    build.check_declarations(steps)
    graph = build_products.Graph(steps)
    selected = graph.select(['world.treehouse_trees.assembled'])
    step = next(step for step in selected if step.name == 'world.treehouse_trees.assembled')
    return SimpleNamespace(root=root, step=step)


@pytest.fixture(scope='module')
def observation(profile, declarations):
    result = profile.qualify_treehouse_assembly(declarations.step, checkout=paths.REPO,
                                                output_root=declarations.root)
    assert not (declarations.root / 'atomic_regions/treehouse_trees').exists()
    assert all(not (path / 'payload.npz').exists() for path in result.produced_inputs)
    return result


def fresh(declarations):
    return deepcopy(declarations.step)


def qualify(profile, step, root, checkout=paths.REPO):
    return profile.qualify_treehouse_assembly(step, checkout=checkout, output_root=root)


def cells(step):
    fn = step.commands[0].fn
    return {name: cell.cell_contents for name, cell in zip(fn.__code__.co_freevars, fn.__closure__)}


def with_cells(step, changed):
    import types
    fn = step.commands[0].fn
    values = cells(step) | changed
    callback = types.FunctionType(fn.__code__, fn.__globals__, fn.__name__, fn.__defaults__,
        tuple(types.CellType(values[name]) for name in fn.__code__.co_freevars))
    return replace(step, commands=[build.Call(step.commands[0].name, callback)])


def rebound(step, root, checkout=None):
    current = cells(step)
    old_root = current['destination'].parents[1]
    old_checkout = Path(step.inputs[0]).parents[2]
    def output(value):
        return root / Path(value).relative_to(old_root)
    logical = [(parent, output(path), *rest) for parent, path, *rest in current['logical']]
    child_steps = []
    for child, key in current['children']:
        command = child.commands[0]
        args = list(command.args)
        args[1] = str(output(args[1]))
        args[3] = str(output(args[3]))
        inputs = [output(value) if Path(value).is_relative_to(old_root) else value for value in child.inputs]
        products = [replace(child.products[0], paths=(output(child.products[0].paths[0]),))]
        import types
        verify = types.FunctionType(child.verify.__code__, child.verify.__globals__, child.verify.__name__,
                                    (output(child.verify.__defaults__[0]), child.verify.__defaults__[1]),
                                    child.verify.__closure__)
        if checkout is not None:
            command = replace(command, script=checkout / command.script.relative_to(old_checkout))
            inputs = [value if Path(value).is_relative_to(root) else checkout / Path(value).relative_to(old_checkout)
                      for value in inputs]
        child_steps.append((replace(child, commands=[replace(command, args=tuple(args))], inputs=inputs,
                                    products=products, verify=verify), key))
    inputs = list(step.inputs)
    if checkout is not None:
        inputs = [checkout / value.relative_to(old_checkout) for value in inputs]
    result = replace(step, inputs=inputs,
                     products=[replace(step.products[0], paths=(output(step.products[0].paths[0]),))])
    return with_cells(result, {'logical': logical, 'children': child_steps,
                               'destination': output(current['destination'])})


def test_actual_graph_binds_exact_logical_children_and_products(declarations, observation):
    assert observation.step == 'world.treehouse_trees.assembled'
    assert observation.region == 'treehouse_trees'
    assert observation.products == (('treehouse_trees.atomic',
                                    (declarations.root / 'atomic_regions/treehouse_trees',)),)
    assert observation.code_inputs == tuple(declarations.step.inputs)
    assert observation.logical == tuple(
        (parent, declarations.root / f'planned_exports/treehouse_trees/{parent}',
         f'world.treehouse_trees.geometry.{parent}', f'treehouse_trees.geometry.{parent}', 'mesh_ir')
        for parent in PARENTS)
    assert observation.children == tuple(
        (parent, parent, f'world.treehouse_trees.export.{parent}', f'world.treehouse_trees.export.{parent}',
         declarations.root / f'exports/world.treehouse_trees.export/{parent}') for parent in PARENTS)
    assert observation.produced_inputs == tuple(row[4] for row in observation.children) + tuple(
        row[1] for row in observation.logical)
    assert observation.callback.qualname == 'steps.<locals>.assemble'
    assert observation.inventory.qualname == 'inventory'
    with pytest.raises(FrozenInstanceError):
        observation.region = 'other'


def test_positive_observation_returns_no_executable_callback(profile, declarations, observation):
    assert observation == qualify(profile, fresh(declarations), declarations.root)
    assert not callable(observation.callback) and not callable(observation.inventory)


def test_warm_produced_and_destination_bytes_are_preserved(profile, declarations, tmp_path):
    root = tmp_path / 'warm'
    step = rebound(fresh(declarations), root)
    paths_to_make = [root / f'planned_exports/treehouse_trees/{parent}/plan.json' for parent in PARENTS]
    paths_to_make += [root / f'exports/world.treehouse_trees.export/{parent}/{parent}.fbx' for parent in PARENTS]
    paths_to_make.append(root / 'atomic_regions/treehouse_trees/manifest.json')
    for path in paths_to_make:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'foreign generated bytes')
    before = {path: (path.read_bytes(), path.lstat()) for path in paths_to_make}
    qualify(profile, step, root)
    assert all((path.read_bytes(), path.lstat()) == before[path] for path in paths_to_make)


@pytest.mark.parametrize('change', ['name', 'call', 'wrapper'])
def test_wrong_step_or_call_is_refused(profile, declarations, change):
    step = fresh(declarations)
    if change == 'name':
        step = replace(step, name='other')
    elif change == 'call':
        step = replace(step, commands=[build.Call('other', step.commands[0].fn)])
    else:
        step = replace(step, commands=[build.Call(step.commands[0].name, lambda: None)])
    with pytest.raises(profile.UnsupportedTreehouseAssembly):
        qualify(profile, step, declarations.root)


@pytest.mark.parametrize('change', ['needs', 'reads', 'read-order', 'cache', 'audit', 'heavy', 'replan',
                                    'controller', 'after', 'references', 'outputs', 'batch', 'alias'])
def test_wrong_controls_needs_or_reads_are_refused(profile, declarations, change):
    step = fresh(declarations)
    values = {'needs': {'needs': []}, 'reads': {'reads': []}, 'read-order': {'reads': list(reversed(step.reads))},
              'cache': {'cache': True}, 'audit': {'audit': True}, 'heavy': {'heavy': True},
              'replan': {'replan': True}, 'controller': {'controller': object()},
              'after': {'after': ['world.other']}, 'references': {'references': ['other']},
              'outputs': {'outputs': [step.products[0].paths[0]]}, 'batch': {'batch': build.Batch('other')}}
    if change == 'alias':
        class AliasStep(type(step)):
            pass
        step = AliasStep(**vars(step))
    else:
        step = replace(step, **values[change])
    with pytest.raises(profile.UnsupportedTreehouseAssembly):
        qualify(profile, step, declarations.root)


@pytest.mark.parametrize('change', ['name', 'path', 'extra', 'optional', 'collection'])
def test_wrong_product_is_refused(profile, declarations, change):
    step = fresh(declarations)
    products = list(step.products)
    if change == 'name':
        products[0] = replace(products[0], name='other')
    elif change == 'path':
        products[0] = replace(products[0], paths=(products[0].paths[0].with_name('other'),))
    elif change == 'extra':
        products.append(build_products.Product('other', (products[0].paths[0].with_name('other'),)))
    elif change == 'optional':
        products[0] = replace(products[0], optional_paths=(products[0].paths[0].with_suffix('.tmp'),))
    else:
        products[0] = replace(products[0], collection='x', bounds=(0., 0., 0., 1., 1., 1.))
    with pytest.raises(profile.UnsupportedTreehouseAssembly):
        qualify(profile, replace(step, products=products), declarations.root)


@pytest.mark.parametrize('change', ['source', 'runtime', 'order', 'extra', 'duplicate'])
def test_wrong_inputs_are_refused(profile, declarations, change):
    step = fresh(declarations)
    inputs = list(step.inputs)
    if change == 'source':
        inputs[0] = inputs[0].with_name('other.py')
    elif change == 'runtime':
        inputs[2] = inputs[2].with_name('other.py')
    elif change == 'order':
        inputs[1], inputs[2] = inputs[2], inputs[1]
    elif change == 'extra':
        inputs.append(paths.REPO / 'platform/studio/atelier/export_tasks.py')
    else:
        inputs.append(inputs[-1])
    with pytest.raises(profile.UnsupportedTreehouseAssembly):
        qualify(profile, replace(step, inputs=inputs), declarations.root)


@pytest.mark.parametrize('change', ['logical-parent', 'logical-root', 'encoding', 'destination', 'region',
                                    'callback-code', 'callback-default', 'inventory-code', 'inventory-global',
                                    'callback-global', 'callback-builtin'])
def test_wrong_callback_or_inventory_binding_is_refused(profile, declarations, monkeypatch, change):
    step = fresh(declarations)
    current = cells(step)
    if change.startswith('logical-') or change in ('destination', 'region'):
        logical = list(current['logical'])
        if change.startswith('logical-'):
            row = list(logical[0])
            index = 0 if change.endswith('parent') else 1 if change.endswith('root') else 4
            row[index] = 'other' if index != 1 else row[1].with_name('other')
            logical[0] = tuple(row)
            changed = {'logical': logical}
        else:
            changed = {'destination': current['destination'].with_name('other')} if change == 'destination' else {'region': 'other'}
        step = with_cells(step, changed)
    elif change == 'callback-code':
        monkeypatch.setattr(step.commands[0].fn, '__code__', step.commands[0].fn.__code__.replace(co_name='other'))
    elif change == 'callback-default':
        monkeypatch.setattr(step.commands[0].fn, '__defaults__', (None,))
    elif change == 'inventory-code':
        inventory = step.commands[0].fn.__globals__['inventory']
        monkeypatch.setattr(inventory, '__code__', inventory.__code__.replace(co_name='other'))
    elif change == 'inventory-global':
        monkeypatch.setitem(step.commands[0].fn.__globals__['inventory'].__globals__, 'json', object())
    elif change == 'callback-global':
        monkeypatch.setitem(step.commands[0].fn.__globals__, 'json', object())
    else:
        namespace = step.commands[0].fn.__globals__.copy()
        namespace['__builtins__'] = namespace['__builtins__'].copy()
        import types
        fn = step.commands[0].fn
        callback = types.FunctionType(fn.__code__, namespace, fn.__name__, fn.__defaults__, fn.__closure__)
        callback.__builtins__['dict'] = object()
        step = replace(step, commands=[build.Call(step.commands[0].name, callback)])
    with pytest.raises(profile.UnsupportedTreehouseAssembly):
        qualify(profile, step, declarations.root)


@pytest.mark.parametrize('change', ['missing', 'duplicate', 'foreign', 'wrong-order', 'wrong-key', 'child-control',
                                    'child-product', 'child-root', 'child-verifier', 'counterfeit'])
def test_counterfeit_or_changed_raw_child_is_refused(profile, declarations, change):
    step = fresh(declarations)
    current = cells(step)
    children = list(current['children'])
    if change == 'missing':
        children.pop()
    elif change == 'duplicate':
        children.append(children[-1])
    elif change == 'foreign':
        children[0] = (children[1][0], children[0][1])
    elif change == 'wrong-order':
        children[0], children[1] = children[1], children[0]
    elif change == 'wrong-key':
        children[0] = (children[0][0], 'other')
    elif change == 'counterfeit':
        children[0] = (object(), children[0][1])
    else:
        child, key = children[0]
        if change == 'child-control':
            child = replace(child, cache=False)
        elif change == 'child-product':
            child = replace(child, products=[replace(child.products[0], name='other')])
        elif change == 'child-root':
            child = replace(child, products=[replace(child.products[0], paths=(child.products[0].paths[0].with_name('other'),))])
        else:
            child = replace(child, verify=lambda: True)
        children[0] = (child, key)
    with pytest.raises(profile.UnsupportedTreehouseAssembly):
        qualify(profile, with_cells(step, {'children': children}), declarations.root)


@pytest.mark.parametrize('change', ['Item-fields', 'NAME', 'PRIMARY', 'limit', 'name-code', 'real-code',
                                    'member-code', 'sha-code', 'regular-code', 'retain-code', 'validate-code',
                                    'copy-code', 'clone-code', 'destination-code', 'assemble-code', 'atomic-code'])
def test_poisoned_helper_or_constant_is_refused(profile, declarations, monkeypatch, change):
    import atelier.atomic_files as atomic_files
    import atelier.export_assembly as assembly
    import atelier.file_copy as file_copy
    if change == 'Item-fields':
        monkeypatch.setattr(assembly.Item, '__dataclass_fields__', {})
    elif change == 'NAME':
        import re
        monkeypatch.setattr(export_manifest, 'NAME', re.compile('.*', re.ASCII))
    elif change == 'PRIMARY':
        monkeypatch.setattr(export_manifest, 'PRIMARY', {'.fbx'})
    elif change == 'limit':
        monkeypatch.setattr(export_manifest, 'TRIANGLE_LIMIT', 1)
    else:
        helpers = {'name': export_manifest.name, 'real': export_manifest.real_directory,
                   'member': model_files.member, 'sha': export_manifest.sha,
                   'regular': model_files.regular_files, 'retain': model_files.retain_files,
                   'validate': export_manifest.validate, 'copy': file_copy.copy_file,
                   'clone': file_copy.clone_function.__wrapped__,
                   'destination': assembly.destination_members, 'assemble': assembly.assemble,
                   'atomic': atomic_files.atomic_json}
        helper = helpers[change.split('-')[0]]
        monkeypatch.setattr(helper, '__code__', helper.__code__.replace(co_name='other'))
    with pytest.raises(profile.UnsupportedTreehouseAssembly):
        qualify(profile, fresh(declarations), declarations.root)


def finite_checkout(step, tmp_path):
    import shutil
    checkout = tmp_path / 'checkout'
    original = Path(step.inputs[0]).parents[2]
    sources = [*step.inputs, original / 'games/yorimichi/legacy_treehouse_export_profile.py',
               original / 'platform/studio/atelier/export_tasks.py']
    for child, key in cells(step)['children']:
        sources.extend(child.inputs[:-1])
    for source in dict.fromkeys(sources):
        target = checkout / source.relative_to(original)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return checkout


@pytest.mark.parametrize('relative', ['games/yorimichi/region_exports.py',
                                      'games/yorimichi/legacy_treehouse_export_profile.py',
                                      'platform/studio/atelier/export_assembly.py',
                                      'platform/studio/atelier/export_manifest.py',
                                      'platform/studio/atelier/file_copy.py',
                                      'platform/studio/atelier/atomic_files.py'])
def test_linked_source_reaches_nofollow_refusal(profile, declarations, tmp_path, relative):
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
        with pytest.raises(profile.UnsupportedTreehouseAssembly):
            qualify(profile, step, declarations.root, checkout)
    finally:
        profile._source = original_reader
    assert source in reached
    assert foreign.read_bytes() == original_bytes


@pytest.mark.parametrize('kind', ['destination', 'destination-parent', 'export-root', 'planner-root'])
def test_linked_output_is_refused_without_changes(profile, declarations, tmp_path, kind):
    root = tmp_path / 'output'
    step = rebound(fresh(declarations), root)
    foreign = tmp_path / 'foreign'
    foreign.mkdir()
    marker = foreign / 'marker'
    marker.write_bytes(b'preserve output')
    destination = root / 'atomic_regions/treehouse_trees'
    produced = root / 'exports/world.treehouse_trees.export/Tree_Canopy_Maple'
    if kind == 'destination':
        destination.parent.mkdir(parents=True)
        destination.symlink_to(foreign, target_is_directory=True)
    elif kind == 'destination-parent':
        destination.parent.parent.mkdir(parents=True)
        destination.parent.symlink_to(foreign, target_is_directory=True)
    elif kind == 'export-root':
        produced.parent.mkdir(parents=True)
        produced.symlink_to(foreign, target_is_directory=True)
    else:
        produced = root / 'planned_exports/treehouse_trees/Tree_Canopy_Maple'
        produced.parent.mkdir(parents=True)
        produced.symlink_to(foreign, target_is_directory=True)
    with pytest.raises(profile.UnsupportedTreehouseAssembly):
        qualify(profile, step, root)
    assert marker.read_bytes() == b'preserve output'


def test_missing_source_is_honest_refusal(profile, declarations, tmp_path):
    with pytest.raises(profile.UnsupportedTreehouseAssembly):
        qualify(profile, fresh(declarations), declarations.root, tmp_path / 'absent')
