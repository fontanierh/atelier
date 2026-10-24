"""Actual-Graph one-piece Treehouse export observations; no native/helper execution."""
from copy import deepcopy
from dataclasses import FrozenInstanceError, fields, replace
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier import build, build_products, export_manifest, export_tasks, model_files, paths


PARENTS = ('Tree_Canopy_Maple', 'Tree_Canopy_Crimson', 'Tree_Canopy_Amber', 'Tree_Canopy_Ginkgo')
PROP_PARENTS = tuple('TH_P_' + slug for slug in (
    'backpack', 'barrel', 'basket', 'bell', 'bookshelf', 'crate_desk', 'futon',
    'globe', 'kamado', 'log_table', 'planter', 'stump_kettle', 'telescope'))
REGIONS = {'treehouse_trees': PARENTS, 'treehouse_props': PROP_PARENTS}
ALL_PARENTS = (*PARENTS, *PROP_PARENTS)


@pytest.fixture(scope='module')
def profile():
    source = paths.REPO / 'games/yorimichi/legacy_treehouse_export_profile.py'
    spec = importlib.util.spec_from_file_location('legacy_treehouse_export_test', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def declarations(tmp_path_factory):
    from atelier.build_v2.controller_entry import declaration_context
    root = tmp_path_factory.mktemp('treehouse-export-cold') / 'yorimichi'
    ctx = declaration_context('yorimichi')
    ctx.out = root
    recipe = build.load_recipe('yorimichi')
    cold_steps = recipe.steps(ctx)
    assert not any(step.name.startswith(('world.treehouse_trees.export.', 'world.treehouse_props.export.'))
                   for step in cold_steps), 'cold producers have no export children until plans exist'
    assert not root.exists()
    for region, parents in REGIONS.items():
        for parent in parents:
            folder = root / 'planned_exports' / region / parent
            folder.mkdir(parents=True)
            # Declaration metadata only: never a payload, native receipt or success stamp.
            (folder / 'plan.json').write_text(json.dumps(dict(
                schema=1, parent=parent, complete=True, triangle_limit=32768,
                source_triangles=1,
                pieces=[dict(name=parent, payload=f'{parent}.npz', triangles=1)])))
    steps = recipe.steps(ctx)
    build.check_declarations(steps)
    graph = build_products.Graph(steps)
    selected = graph.select([f'world.{region}.export' for region in REGIONS])
    names = {f'world.{region}.export.{parent}' for region, parents in REGIONS.items() for parent in parents}
    planners = {step.name: step for step in selected if step.name in names}
    assert len(planners) == 17
    return SimpleNamespace(root=root, steps=planners)


@pytest.fixture(scope='module')
def exports(profile, declarations):
    observed = {name: profile.qualify_treehouse_export(step, checkout=paths.REPO, output_root=declarations.root)
                for name, step in declarations.steps.items()}
    assert all(not task.primary_root.exists() for task in observed.values())
    assert all(not task.produced_inputs[0].exists() for task in observed.values())
    return observed


def fresh(declarations, parent='Tree_Canopy_Maple'):
    region = 'treehouse_props' if parent in PROP_PARENTS else 'treehouse_trees'
    return deepcopy(declarations.steps[f'world.{region}.export.{parent}'])


def qualify(profile, step, root, checkout=paths.REPO):
    return profile.qualify_treehouse_export(step, checkout=checkout, output_root=root)


def rebound(step, root, checkout=None):
    old_root = Path(step.commands[0].args[3]).parents[2]
    old_checkout = step.commands[0].script.parents[3]
    def output(value):
        return root / Path(value).relative_to(old_root)
    args = list(step.commands[0].args)
    args[1] = str(output(args[1]))
    args[3] = str(output(args[3]))
    command = replace(step.commands[0], args=tuple(args))
    inputs = [output(value) if Path(value).is_relative_to(old_root) else value for value in step.inputs]
    products = [replace(step.products[0], paths=(output(step.products[0].paths[0]),))]
    verify = step.verify
    if checkout is not None:
        command = replace(command, script=checkout / command.script.relative_to(old_checkout))
        inputs = [value if Path(value).is_relative_to(root) else checkout / Path(value).relative_to(old_checkout)
                  for value in inputs]
    import types
    verify = types.FunctionType(verify.__code__, verify.__globals__, verify.__name__,
                                (output(verify.__defaults__[0]), verify.__defaults__[1]), verify.__closure__)
    return replace(step, commands=[command], inputs=inputs, products=products, verify=verify)


def test_actual_graph_exports_bind_exact_tree_and_prop_roles(declarations, exports):
    for name, step in declarations.steps.items():
        parent = name.rsplit('.', 1)[1]
        region = name.split('.')[1]
        task = exports[name]
        assert task.step == name and task.parent == parent
        assert task.script == step.commands[0].script == paths.REPO / 'games/yorimichi/world/export_region_piece.py'
        assert task.arguments == step.commands[0].args
        assert task.raw_inputs == ()
        assert task.produced_inputs == (declarations.root / f'planned_exports/{region}/{parent}/{parent}.npz',)
        assert task.primary_root == declarations.root / f'exports/world.{region}.export/{parent}'
        assert task.products == ((name, (task.primary_root,)),)
        assert task.batch == (f'world.{region}.export atomic exports', (), 240.)
        assert task.batch == tuple(getattr(step.batch, field.name) for field in fields(build.Batch))
        assert task.code_inputs == (*step.inputs[:-1], paths.REPO / 'platform/studio/atelier/export_tasks.py')
        assert task.code_inputs.count(paths.REPO / 'games/yorimichi/world/mesh_pieces.py') == 2
        assert [index for index, path in enumerate(task.code_inputs) if path == paths.REPO / 'games/yorimichi/world/mesh_pieces.py'] == [1, len(task.code_inputs) - 2]
        assert task.verifier.qualname == 'steps.<locals>.<lambda>'
        assert task.verifier.binding_names == ('present',)
        with pytest.raises(FrozenInstanceError):
            task.parent = 'other'


def test_warm_payload_and_output_bytes_are_preserved(profile, declarations, tmp_path, monkeypatch):
    root = tmp_path / 'warm'
    before = {}
    for region, parents in REGIONS.items():
        for parent in parents:
            payload = root / f'planned_exports/{region}/{parent}/{parent}.npz'
            output = root / f'exports/world.{region}.export/{parent}/existing.fbx'
            payload.parent.mkdir(parents=True)
            output.parent.mkdir(parents=True)
            payload.write_bytes(b'foreign payload')
            output.write_bytes(b'foreign export')
            for path in (payload, output):
                before[path] = (path.read_bytes(), path.lstat())
    reader = profile._source
    def sources_only(checkout, path):
        assert not Path(path).is_relative_to(root), 'warm generated bytes must stay unopened'
        return reader(checkout, path)
    monkeypatch.setattr(profile, '_source', sources_only)
    for parent in ALL_PARENTS:
        task = qualify(profile, rebound(fresh(declarations, parent), root), root)
        assert task.produced_inputs[0] in before
    assert all((path.read_bytes(), path.lstat()) == state for path, state in before.items())


def test_positive_qualification_never_calls_original_callbacks_or_helpers(profile, declarations, exports):
    result = qualify(profile, fresh(declarations), declarations.root)
    assert result == exports['world.treehouse_trees.export.Tree_Canopy_Maple']
    assert type(result.verifier).__name__ == 'CallableObservation'
    assert not callable(result.verifier)


@pytest.mark.parametrize('parent', ['Tree_Canopy_Future', 'Tree_Canopy', 'Tree_Canopy_Maple.extra', ''])
def test_unknown_parent_or_piece_is_refused(profile, declarations, parent):
    with pytest.raises(profile.UnsupportedTreehouseExport):
        qualify(profile, replace(fresh(declarations), name='world.treehouse_trees.export.' + parent), declarations.root)


@pytest.mark.parametrize('change', ['script', 'payload', 'root', 'format', 'extra', 'order'])
@pytest.mark.parametrize('parent', ['Tree_Canopy_Maple', 'TH_P_backpack'])
def test_wrong_arguments_or_script_are_refused(profile, declarations, change, parent):
    step = fresh(declarations, parent)
    command = step.commands[0]
    args = list(command.args)
    if change == 'script':
        command = replace(command, script=command.script.with_name('other.py'))
    elif change == 'payload':
        args[1] = str(Path(args[1]).with_name('other.npz'))
    elif change == 'root':
        args[3] = str(Path(args[3]).with_name('other'))
    elif change == 'format':
        args[5] = '.glb'
    elif change == 'extra':
        args.append('--extra')
    else:
        args[0], args[2] = args[2], args[0]
    with pytest.raises(profile.UnsupportedTreehouseExport):
        qualify(profile, replace(step, commands=[replace(command, args=tuple(args))]), declarations.root)


@pytest.mark.parametrize('change', ['threads', 'factory', 'env', 'alias'])
@pytest.mark.parametrize('parent', ['Tree_Canopy_Maple', 'TH_P_backpack'])
def test_wrong_blender_controls_are_refused(profile, declarations, change, parent):
    step = fresh(declarations, parent)
    command = step.commands[0]
    if change == 'alias':
        class AliasBlender(type(command)):
            pass
        command = AliasBlender(**vars(command))
    else:
        command = replace(command, **{'threads': {'threads': 4}, 'factory': {'factory_startup': False},
                                      'env': {'env': ()}}[change])
    with pytest.raises(profile.UnsupportedTreehouseExport):
        qualify(profile, replace(step, commands=[command]), declarations.root)


@pytest.mark.parametrize('change', ['group', 'runtime', 'seconds', 'none', 'alias'])
@pytest.mark.parametrize('parent', ['Tree_Canopy_Maple', 'TH_P_backpack'])
def test_wrong_batch_is_refused(profile, declarations, change, parent):
    step = fresh(declarations, parent)
    if change == 'none':
        batch = None
    elif change == 'alias':
        class AliasBatch(type(step.batch)):
            pass
        batch = AliasBatch(**vars(step.batch))
    else:
        batch = replace(step.batch, **{'group': {'group': 'other'}, 'runtime': {'runtime_env': ('PATH',)},
                                      'seconds': {'max_seconds': 1.}}[change])
    with pytest.raises(profile.UnsupportedTreehouseExport):
        qualify(profile, replace(step, batch=batch), declarations.root)


@pytest.mark.parametrize('change', ['after', 'needs', 'reads', 'references', 'cache', 'audit', 'heavy',
                                    'toolchain', 'replan', 'controller', 'outputs', 'queries', 'alias'])
@pytest.mark.parametrize('parent', ['Tree_Canopy_Maple', 'TH_P_backpack'])
def test_wrong_step_flags_are_refused(profile, declarations, change, parent):
    step = fresh(declarations, parent)
    values = {'after': {'after': []}, 'needs': {'needs': ['world.textures']},
              'reads': {'reads': ['other']}, 'references': {'references': ['other']},
              'cache': {'cache': False}, 'audit': {'audit': True}, 'heavy': {'heavy': False},
              'toolchain': {'toolchain': False}, 'replan': {'replan': True},
              'controller': {'controller': object()}, 'outputs': {'outputs': [step.products[0].paths[0]]},
              'queries': {'queries': [object()]}}
    if change == 'alias':
        class AliasStep(type(step)):
            pass
        step = AliasStep(**vars(step))
    else:
        step = replace(step, **values[change])
    with pytest.raises(profile.UnsupportedTreehouseExport):
        qualify(profile, step, declarations.root)


@pytest.mark.parametrize('change', ['name', 'path', 'extra', 'optional', 'collection', 'alias'])
@pytest.mark.parametrize('parent', ['Tree_Canopy_Maple', 'TH_P_backpack'])
def test_wrong_product_is_refused(profile, declarations, change, parent):
    step = fresh(declarations, parent)
    products = list(step.products)
    if change == 'name':
        products[0] = replace(products[0], name='other')
    elif change == 'path':
        products[0] = replace(products[0], paths=(products[0].paths[0].with_name('other'),))
    elif change == 'extra':
        products.append(build_products.Product('other', (products[0].paths[0].with_name('other'),)))
    elif change == 'optional':
        products[0] = replace(products[0], optional_paths=(products[0].paths[0].with_suffix('.tmp'),))
    elif change == 'collection':
        products[0] = replace(products[0], collection='x', bounds=(0., 0., 0., 1., 1., 1.))
    else:
        class AliasProduct(type(products[0])):
            pass
        products[0] = AliasProduct(**vars(products[0]))
    with pytest.raises(profile.UnsupportedTreehouseExport):
        qualify(profile, replace(step, products=products), declarations.root)


@pytest.mark.parametrize('change', ['code', 'repeat-missing', 'repeat-moved', 'extra-repeat', 'payload', 'order', 'alias'])
@pytest.mark.parametrize('parent', ['Tree_Canopy_Maple', 'TH_P_backpack'])
def test_wrong_original_input_shape_is_refused(profile, declarations, change, parent):
    step = fresh(declarations, parent)
    inputs = list(step.inputs)
    mesh = paths.REPO / 'games/yorimichi/world/mesh_pieces.py'
    if change == 'code':
        inputs[0] = inputs[0].with_name('other.py')
    elif change == 'repeat-missing':
        inputs.remove(mesh)
    elif change == 'repeat-moved':
        inputs.remove(mesh)
        inputs.insert(0, mesh)
    elif change == 'extra-repeat':
        inputs.insert(-1, mesh)
    elif change == 'payload':
        inputs[-1] = inputs[-1].with_name('other.npz')
    elif change == 'order':
        inputs[0], inputs[1] = inputs[1], inputs[0]
    else:
        class AliasPath(type(inputs[0])):
            pass
        inputs[0] = AliasPath(str(inputs[0]))
    with pytest.raises(profile.UnsupportedTreehouseExport):
        qualify(profile, replace(step, inputs=inputs), declarations.root)


@pytest.mark.parametrize('change', ['verifier-code', 'default-root', 'default-parent', 'verifier-global',
                                    'present-code', 'present-global', 'present-builtin', 'validate-code',
                                    'validate-default', 'validate-global', 'validate-builtin', 'wrapper'])
@pytest.mark.parametrize('parent', ['Tree_Canopy_Maple', 'TH_P_backpack'])
def test_wrong_verifier_or_present_validate_binding_is_refused(profile, declarations, monkeypatch, change, parent):
    try:
        step = fresh(declarations, parent)
        if change == 'verifier-code':
            monkeypatch.setattr(step.verify, '__code__', step.verify.__code__.replace(co_name='other'))
        elif change == 'default-root':
            monkeypatch.setattr(step.verify, '__defaults__', (step.verify.__defaults__[0].with_name('other'), step.verify.__defaults__[1]))
        elif change == 'default-parent':
            monkeypatch.setattr(step.verify, '__defaults__', (step.verify.__defaults__[0], 'other'))
        elif change == 'verifier-global':
            monkeypatch.setitem(step.verify.__globals__, 'present', object())
        elif change.startswith('present-'):
            helper = export_tasks.present
            if change.endswith('-code'):
                monkeypatch.setattr(helper, '__code__', helper.__code__.replace(co_name='other'))
            elif change.endswith('-global'):
                monkeypatch.setitem(helper.__globals__, 'validate', object())
            else:
                namespace = helper.__globals__.copy()
                namespace['__builtins__'] = namespace['__builtins__'].copy()
                import types
                fn = types.FunctionType(helper.__code__, namespace, helper.__name__, helper.__defaults__, helper.__closure__)
                fn.__builtins__['OSError'] = object()
                monkeypatch.setattr(export_tasks, 'present', fn)
        elif change.startswith('validate-'):
            helper = export_manifest.validate
            if change.endswith('-code'):
                monkeypatch.setattr(helper, '__code__', helper.__code__.replace(co_name='other'))
            elif change.endswith('-default'):
                monkeypatch.setattr(helper, '__kwdefaults__', {'limit': 1})
            elif change.endswith('-global'):
                monkeypatch.setitem(helper.__globals__, 'math', object())
            else:
                namespace = helper.__globals__.copy()
                namespace['__builtins__'] = namespace['__builtins__'].copy()
                import types
                fn = types.FunctionType(helper.__code__, namespace, helper.__name__, helper.__defaults__, helper.__closure__)
                fn.__builtins__['zip'] = object()
                monkeypatch.setattr(export_manifest, 'validate', fn)
        else:
            step = replace(step, verify=lambda: True)
        with pytest.raises(profile.UnsupportedTreehouseExport):
            qualify(profile, step, declarations.root)
    finally:
        monkeypatch.undo()


@pytest.mark.parametrize('change', ['NAME-pattern', 'NAME-flags', 'PRIMARY', 'limit', 'name-code',
                                    'real-code', 'real-default', 'member-code', 'sha-code', 'sha-global',
                                    'regular-code', 'regular-global'])
@pytest.mark.parametrize('parent', ['Tree_Canopy_Maple', 'TH_P_backpack'])
def test_poisoned_helper_or_constant_is_refused(profile, declarations, monkeypatch, change, parent):
    try:
        if change == 'NAME-pattern':
            import re
            monkeypatch.setattr(export_manifest, 'NAME', re.compile('.*', re.ASCII))
        elif change == 'NAME-flags':
            import re
            monkeypatch.setattr(export_manifest, 'NAME', re.compile(export_manifest.NAME.pattern))
        elif change == 'PRIMARY':
            monkeypatch.setattr(export_manifest, 'PRIMARY', {'.fbx'})
        elif change == 'limit':
            monkeypatch.setattr(export_manifest, 'TRIANGLE_LIMIT', 1)
        else:
            helper = {'name': export_manifest.name, 'real': export_manifest.real_directory,
                      'member': model_files.member, 'sha': export_manifest.sha,
                      'regular': model_files.regular_files}[change.split('-')[0]]
            if change.endswith('-code'):
                monkeypatch.setattr(helper, '__code__', helper.__code__.replace(co_name='other'))
            elif change.endswith('-default'):
                monkeypatch.setattr(helper, '__kwdefaults__', {'create': True})
            else:
                monkeypatch.setitem(helper.__globals__, 'Path' if change.startswith(('sha', 'regular')) else 'hashlib', object())
        with pytest.raises(profile.UnsupportedTreehouseExport):
            qualify(profile, fresh(declarations, parent), declarations.root)
    finally:
        monkeypatch.undo()


def finite_checkout(step, tmp_path):
    import shutil
    checkout = tmp_path / 'checkout'
    original = step.commands[0].script.parents[3]
    for source in dict.fromkeys([*step.inputs[:-1], original / 'platform/studio/atelier/export_tasks.py']):
        target = checkout / source.relative_to(original)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return checkout


@pytest.mark.parametrize('relative', ['games/yorimichi/world/export_region_piece.py',
                                      'platform/studio/atelier/export_tasks.py',
                                      'platform/studio/atelier/export_manifest.py',
                                      'platform/studio/atelier/model_files.py'])
@pytest.mark.parametrize('parent', ['Tree_Canopy_Maple', 'TH_P_backpack'])
def test_linked_source_reaches_nofollow_refusal(profile, declarations, tmp_path, relative, parent):
    checkout = finite_checkout(fresh(declarations, parent), tmp_path)
    step = rebound(fresh(declarations, parent), declarations.root, checkout)
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
        with pytest.raises(profile.UnsupportedTreehouseExport):
            qualify(profile, step, declarations.root, checkout)
    finally:
        profile._source = original_reader
        source.unlink()
        source.write_bytes(original_bytes)
    assert source in reached
    assert foreign.read_bytes() == original_bytes


@pytest.mark.parametrize('kind', ['payload', 'payload-parent', 'output-root', 'output-parent', 'root'])
@pytest.mark.parametrize('parent', ['Tree_Canopy_Maple', 'TH_P_backpack'])
def test_linked_or_invalid_output_is_refused_without_changes(profile, declarations, tmp_path, kind, parent):
    root = tmp_path / 'output'
    step = rebound(fresh(declarations, parent), root)
    foreign = tmp_path / 'foreign'
    foreign.mkdir()
    marker = foreign / 'marker'
    marker.write_bytes(b'preserve output')
    payload = Path(step.commands[0].args[1])
    primary = Path(step.commands[0].args[3])
    if kind == 'payload':
        payload.parent.mkdir(parents=True)
        payload.symlink_to(marker)
        target = payload
    elif kind == 'payload-parent':
        payload.parent.parent.mkdir(parents=True)
        payload.parent.symlink_to(foreign, target_is_directory=True)
        target = payload.parent
    elif kind == 'root':
        root.symlink_to(foreign, target_is_directory=True)
        target = root
    elif kind == 'output-root':
        primary.parent.mkdir(parents=True)
        primary.symlink_to(foreign, target_is_directory=True)
        target = primary
    else:
        primary.parent.parent.mkdir(parents=True)
        primary.parent.symlink_to(foreign, target_is_directory=True)
        target = primary.parent
    try:
        with pytest.raises(profile.UnsupportedTreehouseExport, match='output.*linked'):
            qualify(profile, step, root)
    finally:
        target.unlink()
    assert marker.read_bytes() == b'preserve output'


def test_missing_source_is_honest_refusal(profile, declarations, tmp_path):
    with pytest.raises(profile.UnsupportedTreehouseExport):
        qualify(profile, fresh(declarations), declarations.root, tmp_path / 'absent')


@pytest.mark.parametrize('parent', ALL_PARENTS)
def test_wholly_cold_output_tail_and_payload_stay_absent(profile, declarations, tmp_path, parent):
    root = tmp_path / 'absent' / 'cold'
    observed = qualify(profile, rebound(fresh(declarations, parent), root), root)
    assert observed.parent == parent
    assert not root.exists()


@pytest.mark.parametrize('parent', ALL_PARENTS)
def test_each_parent_rejects_cross_constructor_after_role(profile, declarations, parent):
    step = fresh(declarations, parent)
    wrong_region = 'treehouse_trees' if parent in PROP_PARENTS else 'treehouse_props'
    with pytest.raises(profile.UnsupportedTreehouseExport, match='Step controls'):
        qualify(profile, replace(step, after=[f'world.{wrong_region}.geometry']), declarations.root)


@pytest.mark.parametrize('name', [
    'world.treehouse_props.export.TH_P_future', 'world.treehouse_props.export.TH_P_backpack.extra',
    'world.treehouse_props.export.Tree_Canopy_Maple', 'world.treehouse_trees.export.TH_P_backpack',
    'world.treehouse_props.export.th_p_backpack', 'world.treehouse_surfaces.export.TH_Structure',
    'world.other.export.TH_P_backpack'])
def test_unknown_region_parent_and_future_child_refuse(profile, declarations, name):
    with pytest.raises(profile.UnsupportedTreehouseExport, match='not an exact'):
        qualify(profile, replace(fresh(declarations, 'TH_P_backpack'), name=name), declarations.root)


@pytest.mark.parametrize('parent', ['Tree_Canopy_Maple', 'TH_P_backpack'])
@pytest.mark.parametrize('field,value', [('cache', 1), ('heavy', 1), ('toolchain', 1), ('audit', 0),
    ('needs', ()), ('after', ('world.treehouse_props.geometry',)), ('about', 'custom')])
def test_control_types_are_exact(profile, declarations, parent, field, value):
    with pytest.raises(profile.UnsupportedTreehouseExport, match='Step controls'):
        qualify(profile, replace(fresh(declarations, parent), **{field: value}), declarations.root)


@pytest.mark.parametrize('parent', ['Tree_Canopy_Maple', 'TH_P_backpack'])
@pytest.mark.parametrize('kind', ['step', 'command', 'batch', 'product'])
def test_unknown_metadata_is_refused(profile, declarations, parent, kind):
    step = fresh(declarations, parent)
    target = {'step': step, 'command': step.commands[0], 'batch': step.batch, 'product': step.products[0]}[kind]
    object.__setattr__(target, 'foreign', True)
    try:
        with pytest.raises(profile.UnsupportedTreehouseExport):
            qualify(profile, step, declarations.root)
    finally:
        object.__delattr__(target, 'foreign')


@pytest.mark.parametrize('parent', ['Tree_Canopy_Maple', 'TH_P_backpack'])
def test_generated_payload_relocated_into_code_is_never_read(profile, declarations, tmp_path, monkeypatch, parent):
    root = tmp_path / 'output'
    step = rebound(fresh(declarations, parent), root)
    payload = Path(step.commands[0].args[1])
    payload.parent.mkdir(parents=True)
    payload.write_bytes(b'foreign generated bytes, never Python')
    before = payload.read_bytes(), payload.lstat()
    reader = profile._source
    def sources_only(checkout, path):
        assert not Path(path).is_relative_to(root), 'generated payload was passed to source reader'
        return reader(checkout, path)
    monkeypatch.setattr(profile, '_source', sources_only)
    altered = replace(step, inputs=[*step.inputs, step.inputs[0]])
    with pytest.raises(profile.UnsupportedTreehouseExport, match='code source role|generated payload'):
        qualify(profile, altered, root)
    assert (payload.read_bytes(), payload.lstat()) == before


@pytest.mark.parametrize('parent', ['Tree_Canopy_Maple', 'TH_P_backpack'])
@pytest.mark.parametrize('role', ['checkout', 'world', 'studio'])
def test_linked_source_anchors_refuse_at_intended_check(profile, declarations, tmp_path, parent, role):
    step = fresh(declarations, parent)
    checkout = finite_checkout(step, tmp_path)
    step = rebound(step, declarations.root, checkout)
    target = {'checkout': checkout, 'world': checkout / 'games/yorimichi/world',
              'studio': checkout / 'platform/studio/atelier'}[role]
    foreign = tmp_path / 'foreign'
    target.rename(foreign)
    target.symlink_to(foreign, target_is_directory=True)
    try:
        with pytest.raises(profile.UnsupportedTreehouseExport, match='source anchor is not a real directory'):
            qualify(profile, step, declarations.root, checkout)
    finally:
        target.unlink()
        foreign.rename(target)


@pytest.mark.parametrize('parent', ['Tree_Canopy_Maple', 'TH_P_backpack'])
def test_new_import_candidate_is_anchored_before_scanner_reads(profile, declarations, tmp_path, monkeypatch, parent):
    step = fresh(declarations, parent)
    checkout = finite_checkout(step, tmp_path)
    step = rebound(step, declarations.root, checkout)
    script = step.commands[0].script
    original = script.read_bytes()
    source = script.parent / 'unknown_helper.py'
    foreign = tmp_path / 'foreign.py'
    foreign.write_bytes(b'raise AssertionError("helper must not execute")\n')
    source.symlink_to(foreign)
    script.write_bytes(original + b'\nimport unknown_helper\n')
    reached = []
    reader = profile._source
    def observe(anchor, path):
        reached.append(path)
        return reader(anchor, path)
    monkeypatch.setattr(profile, '_source', observe)
    try:
        with pytest.raises(profile.UnsupportedTreehouseExport, match='source is absent, linked or invalid'):
            qualify(profile, step, declarations.root, checkout)
        assert source in reached
    finally:
        script.write_bytes(original)
        source.unlink()


def test_all17_qualifications_never_call_exporter_verifier_or_helpers(profile, declarations):
    import sys
    called = []
    helpers = {'present', 'validate', 'name', 'real_directory', 'member', 'sha', 'regular_files'}
    def trace(frame, event, arg):
        if event == 'call':
            filename = Path(frame.f_code.co_filename).name
            function = frame.f_code.co_name
            if (filename == 'export_region_piece.py' or
                    (filename in ('export_tasks.py', 'export_manifest.py', 'model_files.py')
                     and (function in helpers or function == '<lambda>'))):
                called.append((filename, function))
        return trace
    previous = sys.gettrace()
    sys.settrace(trace)
    try:
        for step in declarations.steps.values():
            qualify(profile, step, declarations.root)
    finally:
        sys.settrace(previous)
    assert called == []


def test_export_observation_abi_is_unchanged(profile):
    assert tuple(field.name for field in fields(profile.TreehouseExport)) == (
        'step', 'parent', 'script', 'arguments', 'raw_inputs', 'produced_inputs', 'code_inputs',
        'products', 'primary_root', 'verifier', 'batch')


@pytest.mark.parametrize('parent', ['Tree_Canopy_Maple', 'TH_P_backpack'])
def test_non_directory_output_ancestor_refuses_without_changes(profile, declarations, tmp_path, parent):
    root = tmp_path / 'output'
    root.write_bytes(b'foreign file, never output directory')
    before = root.read_bytes(), root.lstat()
    with pytest.raises(profile.UnsupportedTreehouseExport, match='output ancestry is invalid'):
        qualify(profile, rebound(fresh(declarations, parent), root), root)
    assert (root.read_bytes(), root.lstat()) == before


@pytest.mark.parametrize('parent', ['Tree_Canopy_Maple', 'TH_P_backpack'])
def test_generated_import_candidate_is_refused_before_source_read(profile, declarations, tmp_path, monkeypatch, parent):
    step = fresh(declarations, parent)
    checkout = finite_checkout(step, tmp_path)
    root = checkout / 'games/yorimichi/world/generated'
    step = rebound(step, root, checkout)
    script = step.commands[0].script
    original = script.read_bytes()
    generated = root / 'unknown_helper.py'
    generated.parent.mkdir(parents=True)
    generated.write_bytes(b'foreign generated bytes must remain unopened')
    before = generated.read_bytes(), generated.lstat()
    script.write_bytes(original + b'\nimport generated.unknown_helper\n')
    reader = profile._source
    def sources_only(anchor, path):
        assert not Path(path).is_relative_to(root), 'generated candidate reached source reader'
        return reader(anchor, path)
    monkeypatch.setattr(profile, '_source', sources_only)
    try:
        with pytest.raises(profile.UnsupportedTreehouseExport, match='generated output cannot be an import source'):
            qualify(profile, step, root, checkout)
    finally:
        script.write_bytes(original)
    assert (generated.read_bytes(), generated.lstat()) == before
