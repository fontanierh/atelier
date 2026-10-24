"""Actual-Graph Treehouse discovery observations; callbacks and helpers never execute."""
from copy import deepcopy
from dataclasses import FrozenInstanceError, fields, replace
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier import build, build_products, export_tasks, paths


REGIONS = {
    'treehouse_trees': ('Tree_Canopy_Maple', 'Tree_Canopy_Crimson', 'Tree_Canopy_Amber', 'Tree_Canopy_Ginkgo'),
    'treehouse_props': tuple('TH_P_' + slug for slug in (
        'backpack', 'barrel', 'basket', 'bell', 'bookshelf', 'crate_desk', 'futon',
        'globe', 'kamado', 'log_table', 'planter', 'stump_kettle', 'telescope')),
}


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
    selected = graph.select([f'world.{region}.geometry' for region in REGIONS])
    names = {f'world.{region}.geometry' for region in REGIONS}
    chosen = {step.name.split('.')[1]: step for step in selected if step.name in names}
    assert set(chosen) == set(REGIONS)
    return SimpleNamespace(root=root, steps=chosen)


@pytest.fixture(params=tuple(REGIONS))
def region(request):
    return request.param


@pytest.fixture
def discovery(profile, declarations, region):
    assert not declarations.root.exists()
    observed = profile.qualify_treehouse_discovery(
        declarations.steps[region], checkout=paths.REPO, output_root=declarations.root)
    assert not declarations.root.exists()
    return observed


def fresh(declarations, region='treehouse_trees'):
    return deepcopy(declarations.steps[region])


def qualify(profile, step, root, checkout=paths.REPO):
    return profile.qualify_treehouse_discovery(step, checkout=checkout, output_root=root)


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
    import types
    callback = types.FunctionType(fn.__code__, namespace, fn.__name__, fn.__defaults__, tuple(
        types.CellType(cells[name]) for name in fn.__code__.co_freevars))
    return replace(step, commands=[build.Call(step.commands[0].name, callback)], inputs=inputs, products=products)


def test_actual_graph_discovery_binds_exact_frozen_roles(declarations, discovery, region):
    step = declarations.steps[region]
    assert discovery.step == step.name and discovery.region == region
    assert discovery.products == ((step.products[0].name, step.products[0].paths),)
    assert discovery.code_inputs[:len(step.inputs)] == tuple(step.inputs)
    assert discovery.code_inputs[-1] == paths.REPO / 'platform/studio/atelier/export_tasks.py'
    assert len(discovery.code_inputs) == len(set(discovery.code_inputs)) == 7
    assert discovery.produced_inputs == tuple(row[1] for row in discovery.logical)
    assert discovery.logical == tuple(
        (parent, declarations.root / 'planned_exports' / region / parent,
         f'world.{region}.geometry.{parent}', f'{region}.geometry.{parent}', 'mesh_ir')
        for parent in REGIONS[region])
    assert discovery.callback.qualname == 'steps.<locals>.discover'
    assert discovery.inventory.qualname == 'inventory'
    assert discovery.callback.filename == discovery.inventory.filename == str(paths.REPO / 'games/yorimichi/region_exports.py')
    assert discovery.callback.binding_names == (
        'ValueError', 'atomic_json', 'dict', 'discovery', 'inventory', 'len', 'logical', 'map', 'region', 'sum')
    with pytest.raises(FrozenInstanceError):
        discovery.region = 'other'


def test_warm_planner_roots_and_record_are_preserved(profile, declarations, tmp_path, region, monkeypatch):
    root = tmp_path / 'warm'
    step = rebound(fresh(declarations, region), root)
    existing = {row[1] / 'plan.json': b'foreign plan' for row in profile_rows(root, region)}
    existing[root / 'planned_exports' / region / 'discovery.json'] = b'foreign discovery'
    for path, content in existing.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    before = {path: (path.read_bytes(), path.lstat()) for path in existing}
    reader = profile._source
    def sources_only(checkout, path):
        assert not Path(path).is_relative_to(root), 'generated outputs must remain unread'
        return reader(checkout, path)
    monkeypatch.setattr(profile, '_source', sources_only)
    observed = qualify(profile, step, root)
    assert observed.produced_inputs == tuple(row[1] for row in profile_rows(root, region))
    assert all((path.read_bytes(), path.lstat()) == before[path] for path in existing)


def profile_rows(root, region):
    return tuple((parent, root / 'planned_exports' / region / parent) for parent in REGIONS[region])


def test_callbacks_and_helpers_are_never_executed(profile, declarations, region):
    counters = []
    step = fresh(declarations, region)
    original = step.commands[0].fn
    def forbidden(*args, **kwargs):
        counters.append('executed')
        raise AssertionError('discovery callback executed')
    step.commands[0] = build.Call('discover ' + region, forbidden)
    with pytest.raises(profile.UnsupportedTreehouseDiscovery):
        qualify(profile, step, declarations.root)
    assert counters == []
    assert original.__qualname__ == 'steps.<locals>.discover'


@pytest.mark.parametrize('name', ['other', 'world.treehouse_trees.geometry.Tree_Canopy_Maple', 'world.treehouse_surfaces.geometry'])
def test_wrong_step_is_refused(profile, declarations, name, region):
    with pytest.raises(profile.UnsupportedTreehouseDiscovery):
        qualify(profile, replace(fresh(declarations, region), name=name), declarations.root)


@pytest.mark.parametrize('change', ['name', 'python', 'extra', 'wrapper'])
def test_wrong_call_or_wrapper_is_refused(profile, declarations, change, region):
    step = fresh(declarations, region)
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
def test_wrong_step_flags_are_refused(profile, declarations, change, region):
    step = fresh(declarations, region)
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
def test_wrong_reads_are_refused(profile, declarations, change, region):
    step = fresh(declarations, region)
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
def test_wrong_product_is_refused(profile, declarations, change, region):
    step = fresh(declarations, region)
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
def test_wrong_inputs_are_refused(profile, declarations, change, region):
    step = fresh(declarations, region)
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
def test_wrong_callback_closure_is_refused(profile, declarations, change, region):
    step = fresh(declarations, region)
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
def test_wrong_callback_or_inventory_source_binding_is_refused(profile, declarations, monkeypatch, change, region):
    try:
        step = fresh(declarations, region)
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
    finally:
        monkeypatch.undo()


@pytest.mark.parametrize('change', ['name-code', 'name-global', 'name-regex', 'name-flags', 'limit',
                                    'real-code', 'real-default', 'real-global', 'member-code',
                                    'member-global', 'atomic-code', 'atomic-global', 'member-wrapper'])
def test_poisoned_helper_source_or_binding_is_refused(profile, declarations, monkeypatch, change, region):
    try:
        import atelier.atomic_files as atomic_files
        import atelier.export_manifest as manifest
        import atelier.model_files as model_files
        step = fresh(declarations, region)
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
    finally:
        monkeypatch.undo()


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
    *(f'platform/studio/atelier/{name}.py' for name in (
        'export_assembly', 'atomic_files', 'file_copy', 'export_manifest', 'model_files', 'export_tasks'))])
def test_linked_source_reaches_intended_nofollow_refusal(profile, declarations, tmp_path, relative, region):
    checkout = finite_checkout(fresh(declarations, region), tmp_path)
    step = rebound(fresh(declarations, region), declarations.root, checkout)
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
        source.unlink()
        source.write_bytes(original_bytes)
    assert source in reached
    assert foreign.read_bytes() == original_bytes


@pytest.mark.parametrize('kind', ['planner-root', 'planner-parent', 'discovery-parent', 'discovery-file'])
def test_linked_output_is_refused_without_changing_bytes(profile, declarations, tmp_path, kind, region):
    root = tmp_path / 'output'
    step = rebound(fresh(declarations, region), root)
    foreign = tmp_path / 'foreign'
    foreign.mkdir()
    marker = foreign / 'marker'
    marker.write_bytes(b'preserve output')
    planner = root / 'planned_exports' / region / REGIONS[region][0]
    discovery = root / 'planned_exports' / region / 'discovery.json'
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
    target = {'planner-root': planner, 'planner-parent': planner.parent,
              'discovery-parent': discovery.parent, 'discovery-file': discovery}[kind]
    before = marker.read_bytes(), marker.lstat()
    try:
        with pytest.raises(profile.UnsupportedTreehouseDiscovery, match='output.*linked'):
            qualify(profile, step, root)
    finally:
        target.unlink()
    assert (marker.read_bytes(), marker.lstat()) == before


def test_missing_source_is_honest_refusal(profile, declarations, tmp_path, region):
    with pytest.raises(profile.UnsupportedTreehouseDiscovery):
        qualify(profile, fresh(declarations, region), declarations.root, tmp_path / 'absent')
    assert not declarations.root.exists()


def test_fixed_source_roles_and_abi(profile, declarations, discovery, region):
    assert tuple(field.name for field in fields(profile.TreehouseDiscovery)) == (
        'step', 'region', 'products', 'code_inputs', 'produced_inputs', 'logical', 'callback', 'inventory')
    expected = (paths.REPO / 'games/yorimichi/region_exports.py',
        *(paths.STUDIO / 'atelier' / name for name in (
            'export_assembly.py', 'atomic_files.py', 'file_copy.py', 'export_manifest.py', 'model_files.py')))
    assert tuple(declarations.steps[region].inputs) == expected
    assert discovery.code_inputs == (*expected, paths.STUDIO / 'atelier/export_tasks.py')
    assert len(discovery.logical) == (4 if region == 'treehouse_trees' else 13)


def test_qualification_never_executes_runtime_inputs_or_original_helpers(profile, declarations, region, monkeypatch):
    import sys
    from atelier import export_assembly
    attempted = []
    def forbidden():
        attempted.append('runtime_inputs')
        raise AssertionError('runtime_inputs must not execute during qualification')
    monkeypatch.setattr(export_assembly, 'runtime_inputs', forbidden)
    called = []
    def trace(frame, event, arg):
        if event == 'call':
            filename = Path(frame.f_code.co_filename).name
            name = frame.f_code.co_name
            if ((filename == 'region_exports.py' and name in ('discover', 'inventory'))
                    or (filename == 'atomic_files.py' and name == 'atomic_json')
                    or (filename == 'export_manifest.py' and name in ('name', 'real_directory'))
                    or (filename == 'model_files.py' and name == 'member')):
                called.append((filename, name))
        return trace
    previous = sys.gettrace()
    sys.settrace(trace)
    try:
        qualify(profile, fresh(declarations, region), declarations.root)
    finally:
        sys.settrace(previous)
    assert attempted == called == []


@pytest.mark.parametrize('change', ['reads', 'product-name', 'product-root', 'call', 'logical', 'region'])
def test_cross_region_metadata_refuses(profile, declarations, region, change):
    step = fresh(declarations, region)
    other = next(name for name in REGIONS if name != region)
    foreign = fresh(declarations, other)
    if change == 'reads':
        step = replace(step, reads=foreign.reads)
    elif change == 'product-name':
        step = replace(step, products=[replace(step.products[0], name=foreign.products[0].name)])
    elif change == 'product-root':
        step = replace(step, products=[replace(step.products[0], paths=foreign.products[0].paths)])
    elif change == 'call':
        step = replace(step, commands=[build.Call(foreign.commands[0].name, step.commands[0].fn)])
    else:
        function = foreign.commands[0].fn
        cells = dict(zip(function.__code__.co_freevars, (cell.cell_contents for cell in function.__closure__)))
        step = callback_with_cells(step, {change: cells[change]})
    with pytest.raises(profile.UnsupportedTreehouseDiscovery):
        qualify(profile, step, declarations.root)


@pytest.mark.parametrize('field,value', [('replan', 1), ('cache', 0), ('heavy', 0), ('audit', 0),
    ('toolchain', 0), ('needs', ()), ('after', ()), ('about', 'custom')])
def test_exact_default_control_types(profile, declarations, region, field, value):
    with pytest.raises(profile.UnsupportedTreehouseDiscovery, match='Step controls'):
        qualify(profile, replace(fresh(declarations, region), **{field: value}), declarations.root)


@pytest.mark.parametrize('kind', ['step', 'call', 'product', 'read', 'path'])
def test_type_aliases_refuse(profile, declarations, region, kind):
    step = fresh(declarations, region)
    if kind in ('step', 'call', 'product'):
        original = {'step': step, 'call': step.commands[0], 'product': step.products[0]}[kind]
        class Alias(type(original)):
            pass
        alias = Alias(**vars(original))
        if kind == 'step':
            step = alias
        elif kind == 'call':
            step = replace(step, commands=[alias])
        else:
            step = replace(step, products=[alias])
    elif kind == 'read':
        class AliasStr(str):
            pass
        step = replace(step, reads=[AliasStr(step.reads[0]), *step.reads[1:]])
    else:
        original = step.products[0].paths[0]
        class AliasPath(type(original)):
            pass
        step = replace(step, products=[replace(step.products[0], paths=(AliasPath(str(original)),))])
    with pytest.raises(profile.UnsupportedTreehouseDiscovery):
        qualify(profile, step, declarations.root)


@pytest.mark.parametrize('kind', ['callback', 'inventory', 'atomic_json', 'name'])
def test_non_function_helpers_refuse_without_execution(profile, declarations, region, monkeypatch, kind):
    step = fresh(declarations, region)
    try:
        if kind == 'callback':
            step = replace(step, commands=[build.Call(step.commands[0].name, object())])
        elif kind == 'name':
            monkeypatch.setattr(export_tasks, 'name', object())
        else:
            monkeypatch.setitem(step.commands[0].fn.__globals__, kind, object())
        with pytest.raises(profile.UnsupportedTreehouseDiscovery):
            qualify(profile, step, declarations.root)
    finally:
        monkeypatch.undo()


@pytest.mark.parametrize('kind', ['checkout', 'game', 'studio'])
def test_linked_source_ancestor_reaches_intended_check(profile, declarations, tmp_path, region, kind, monkeypatch):
    step = fresh(declarations, region)
    checkout = finite_checkout(step, tmp_path)
    step = rebound(step, declarations.root, checkout)
    target = {'checkout': checkout, 'game': checkout / 'games/yorimichi',
              'studio': checkout / 'platform/studio/atelier'}[kind]
    foreign = tmp_path / 'foreign'
    target.rename(foreign)
    target.symlink_to(foreign, target_is_directory=True)
    reached = []
    reader = profile._source
    def observe(anchor, path):
        reached.append(path)
        return reader(anchor, path)
    monkeypatch.setattr(profile, '_source', observe)
    expected = (checkout / 'games/yorimichi/region_exports.py' if kind == 'game'
                else checkout / 'platform/studio/atelier/export_assembly.py')
    try:
        with pytest.raises(profile.UnsupportedTreehouseDiscovery, match=(
                'checkout is not a real anchored directory' if kind == 'checkout'
                else 'source is absent, linked or invalid')):
            qualify(profile, step, declarations.root, checkout)
        if kind != 'checkout':
            assert expected in reached
    finally:
        target.unlink()
        foreign.rename(target)


def test_wholly_absent_output_tail_is_not_created(profile, declarations, tmp_path, region):
    root = tmp_path / 'missing' / 'nested' / 'output'
    observed = qualify(profile, rebound(fresh(declarations, region), root), root)
    assert observed.region == region
    assert not root.exists()


def test_non_directory_output_ancestor_refuses_without_changes(profile, declarations, tmp_path, region):
    root = tmp_path / 'output'
    root.write_bytes(b'foreign output file')
    before = root.read_bytes(), root.lstat()
    with pytest.raises(profile.UnsupportedTreehouseDiscovery, match='output ancestry is invalid'):
        qualify(profile, rebound(fresh(declarations, region), root), root)
    assert (root.read_bytes(), root.lstat()) == before
