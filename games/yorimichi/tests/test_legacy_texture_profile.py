"""Finite actual-factory texture qualification; no producer or output execution."""
from dataclasses import FrozenInstanceError, replace
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier import build, build_inputs, build_products, paths


@pytest.fixture(scope='module')
def profile():
    source = paths.REPO / 'games/yorimichi/legacy_texture_profile.py'
    spec = importlib.util.spec_from_file_location('legacy_texture_profile_test', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def declarations(tmp_path_factory):
    recipe = build.load_recipe('yorimichi')
    output_root = tmp_path_factory.mktemp('texture-profile-cold') / 'yorimichi'
    ctx = SimpleNamespace(out=output_root)
    steps = recipe.texture_steps(ctx)
    return SimpleNamespace(recipe=recipe, root=output_root,
                           textures={step.name: step for step in steps if step.products},
                           aggregate=next(step for step in steps if not step.products))


@pytest.fixture(scope='module')
def tasks(profile, declarations):
    assert len(declarations.textures) == 22
    assert set(declarations.textures) == {f'world.textures.{name}' for name in profile.ROSTER}
    assert not declarations.root.exists(), 'cold fixture must begin with an absent output root'
    before = {name: (step.outputs[0].exists(),
                     step.outputs[0].read_bytes() if step.outputs[0].is_file() else None,
                     step.outputs[0].lstat() if step.outputs[0].exists() else None)
              for name, step in declarations.textures.items()}
    qualified = {name: profile.qualify_texture_step(
        step, checkout=paths.REPO, output_root=declarations.root)
        for name, step in declarations.textures.items()}
    after = {name: (step.outputs[0].exists(),
                    step.outputs[0].read_bytes() if step.outputs[0].is_file() else None,
                    step.outputs[0].lstat() if step.outputs[0].exists() else None)
             for name, step in declarations.textures.items()}
    assert after == before, 'qualification must not create, alter or adopt an existing output'
    assert not declarations.root.exists(), 'cold qualification must not create the absent output root'
    return qualified


def test_all_actual_factory_tasks_bind_exact_roles_and_input_order(profile, declarations, tasks):
    assert len(tasks) == 22
    code = None
    for name, step in declarations.textures.items():
        task = tasks[name]
        command, = step.commands
        texture = name.removeprefix('world.textures.')
        filename, _, assets = profile.ROSTER[texture]
        spec = declarations.recipe.WORLD / 'textures' / f'{texture}.json'
        expected_raw = (spec, *(declarations.recipe.ASSETS / 'environment/textures' / asset
                               for asset in assets))
        assert task.step == name and task.texture == texture
        assert task.script == command.script == declarations.recipe.WORLD / 'gen_textures.py'
        assert task.arguments == tuple(map(str, command.args))
        assert task.arguments[:2] == ('--texture', texture)
        assert task.arguments[3] == str(spec)
        assert task.arguments[5] == str(task.output)
        assert task.output == step.outputs[0] == step.products[0].paths[0]
        assert task.output == declarations.root / 'textures' / filename
        assert task.product == f'texture.{texture}'
        assert task.raw_inputs == expected_raw
        support = build_inputs.local_imports(task.script,
            (declarations.recipe.WORLD, declarations.recipe.REGIONS))
        assert task.code_inputs == tuple(support)
        assert step.inputs == [spec, *(path for path in support if path != task.script), *expected_raw[1:]]
        assert ('--assets' in task.arguments) is bool(assets)
        assert task.script.parent == declarations.recipe.WORLD
        if code is None:
            code = task.code_inputs
        assert task.code_inputs == code


def test_full_recipe_enriched_inputs_accept_exact_appended_script(profile, declarations, tasks):
    from atelier.build_v2.controller_entry import declaration_context
    recipe = build.load_recipe('yorimichi')
    ctx = declaration_context('yorimichi')
    ctx.out = declarations.root
    steps = recipe.steps(ctx)
    enriched = {step.name: step for step in steps if step.name in declarations.textures}
    assert len(enriched) == 22
    for name, step in enriched.items():
        assert step.inputs == [*declarations.textures[name].inputs, tasks[name].script]
        observed = profile.qualify_texture_step(
            step, checkout=paths.REPO, output_root=declarations.root)
        assert observed == tasks[name]
        assert observed.raw_inputs == tasks[name].raw_inputs
        assert observed.code_inputs == tasks[name].code_inputs


@pytest.mark.parametrize('change', ['wrong-position', 'duplicate', 'extra'])
def test_enriched_input_order_stays_closed(profile, declarations, change):
    step = declarations.textures['world.textures.white']
    script = step.commands[0].script
    inputs = [*step.inputs, script]
    if change == 'wrong-position':
        inputs.remove(script)
        inputs.insert(1, script)
    elif change == 'duplicate':
        inputs.append(script)
    else:
        inputs.append(declarations.recipe.WORLD / 'textures/bark.json')
    with pytest.raises(profile.UnsupportedTexture):
        qualify(profile, replace(step, inputs=inputs))


def test_asset_backed_tasks_have_only_their_selected_members(profile, tasks):
    expected = {
        'world.textures.bark': ('tree-bark.jpg',),
        'world.textures.bark_olive': ('tree-bark.jpg',),
        'world.textures.ground_detail': ('tuscan-ground.jpg', 'tuscan-ground.provenance.json'),
    }
    for name, assets in expected.items():
        raw = tasks[name].raw_inputs
        assert tuple(path.name for path in raw[1:]) == assets
        assert all(path.parent == paths.REPO / 'games/yorimichi/assets/environment/textures'
                   for path in raw[1:])
    assert all(len(task.raw_inputs) == 1 for name, task in tasks.items() if name not in expected)


def test_aggregate_is_not_an_executed_child(profile, declarations):
    assert declarations.aggregate.commands == []
    with pytest.raises(profile.UnsupportedTexture):
        profile.qualify_texture_step(declarations.aggregate,
                                     checkout=paths.REPO, output_root=declarations.root)


def test_observation_is_frozen_and_does_not_adopt_output(profile, tasks, tmp_path):
    task = tasks['world.textures.white']
    with pytest.raises(FrozenInstanceError):
        task.texture = 'changed'
    output = tmp_path / 'textures/T_white.png'
    output.parent.mkdir()
    output.write_bytes(b'foreign output; never a certificate')
    step = declarations_step('white', output)
    before = (output.read_bytes(), output.lstat())
    assert qualify(profile, step, tmp_path).output == output
    assert (output.read_bytes(), output.lstat()) == before


def declarations_step(name, output=None):
    root = paths.REPO / 'build/yorimichi'
    step = next(step for step in build.load_recipe('yorimichi').texture_steps(
        SimpleNamespace(out=root)) if step.name == f'world.textures.{name}')
    if output is not None:
        command, = step.commands
        args = list(command.args)
        args[args.index('--output') + 1] = output
        step = replace(step, outputs=[output], commands=[build.Python(command.script, tuple(args))],
                       products=[replace(step.products[0], paths=(output,))])
    return step


def qualify(profile, step, output_root=None):
    return profile.qualify_texture_step(
        step, checkout=paths.REPO, output_root=output_root or paths.REPO / 'build/yorimichi')


@pytest.mark.parametrize('name', ['future_texture', 'leaf_broad_extra', ''])
def test_unknown_or_future_member_is_refused(profile, declarations, name):
    step = replace(declarations.textures['world.textures.white'], name=f'world.textures.{name}')
    with pytest.raises(profile.UnsupportedTexture):
        qualify(profile, step)


@pytest.mark.parametrize('change', ['script', 'texture', 'spec', 'output', 'assets'])
def test_changed_script_or_argument_role_is_refused(profile, declarations, change):
    step = declarations.textures['world.textures.bark']
    command = step.commands[0]
    args = list(command.args)
    if change == 'script':
        command = build.Python(command.script.with_name('other.py'), command.args)
    elif change == 'texture':
        args[args.index('bark')] = 'white'
    elif change == 'spec':
        args[3] = str(declarations.recipe.WORLD / 'textures/white.json')
    elif change == 'output':
        args[5] = str(declarations.root / 'textures/T_white.png')
    else:
        args[args.index('--assets') + 1] = str(declarations.recipe.ASSETS / 'environment')
    step = replace(step, commands=[build.Python(command.script, tuple(args))])
    with pytest.raises(profile.UnsupportedTexture):
        qualify(profile, step)


@pytest.mark.parametrize('change', ['missing-spec', 'sibling-spec', 'extra-asset', 'missing-asset',
                                    'missing-code', 'input-order', 'whole-assets'])
def test_changed_source_membership_or_order_is_refused(profile, declarations, change):
    step = declarations.textures['world.textures.ground_detail']
    inputs = list(step.inputs)
    if change == 'missing-spec':
        inputs.pop(0)
    elif change == 'sibling-spec':
        inputs[0] = declarations.recipe.WORLD / 'textures/white.json'
    elif change == 'extra-asset':
        inputs.append(declarations.recipe.ASSETS / 'environment/textures/tree-bark.jpg')
    elif change == 'missing-asset':
        inputs.pop()
    elif change == 'missing-code':
        inputs.pop(1)
    elif change == 'input-order':
        inputs[1], inputs[2] = inputs[2], inputs[1]
    else:
        inputs[-2:] = [declarations.recipe.ASSETS]
    with pytest.raises(profile.UnsupportedTexture):
        qualify(profile, replace(step, inputs=inputs))


@pytest.mark.parametrize('change', ['name', 'output', 'extra', 'optional', 'spatial'])
def test_changed_product_or_output_claim_is_refused(profile, declarations, change):
    step = declarations.textures['world.textures.white']
    product, = step.products
    if change == 'name':
        step = replace(step, products=[replace(product, name='texture.other')])
    elif change == 'output':
        step = replace(step, outputs=[])
    elif change == 'extra':
        step = replace(step, outputs=[*step.outputs, step.outputs[0].with_suffix('.json')])
    elif change == 'optional':
        step = replace(step, products=[replace(product, optional_paths=(step.outputs[0].with_suffix('.json'),))])
    else:
        step = replace(step, products=[replace(product, collection='x', bounds=(0., 0., 0., 1., 1., 1.))])
    with pytest.raises(profile.UnsupportedTexture):
        qualify(profile, step)


@pytest.mark.parametrize('change', ['call', 'batch', 'replan', 'verify', 'needs', 'after', 'reads',
                                    'references', 'pool', 'deferred', 'optional', 'queries', 'toolchain',
                                    'controller', 'cutoff', 'checkpoint', 'candidate', 'cook',
                                    'checkpoint_outputs', 'explicit', 'heavy', 'cache', 'audit'])
def test_custom_or_mutating_step_control_is_refused(profile, declarations, change):
    step = declarations.textures['world.textures.white']
    values = {
        'call': {'commands': [build.Call('other', lambda ctx, log: None)]},
        'batch': {'batch': build.Batch('textures')},
        'replan': {'replan': True},
        'verify': {'verify': lambda: True},
        'needs': {'needs': ['world.other']},
        'after': {'after': ['world.other']},
        'reads': {'reads': ['texture.other']},
        'references': {'references': ['texture.other']},
        'pool': {'pool_roots': [declarations.root / 'textures']},
        'deferred': {'deferred_inputs': [object()]},
        'optional': {'optional_inputs': [step.inputs[0]]},
        'queries': {'queries': [object()]},
        'toolchain': {'toolchain': True},
        'controller': {'controller': object()},
        'cutoff': {'cutoff': True},
        'checkpoint': {'checkpoint_restore': lambda: None},
        'candidate': {'candidate_scope': object()},
        'cook': {'cook_recovery': object()},
        'checkpoint_outputs': {'checkpoint_outputs': (step.outputs[0],)},
        'explicit': {'explicit': True},
        'heavy': {'heavy': True},
        'cache': {'cache': False},
        'audit': {'audit': False},
    }
    with pytest.raises(profile.UnsupportedTexture):
        qualify(profile, replace(step, **values[change]))


@pytest.mark.parametrize('change', ['step', 'command', 'product'])
def test_alias_types_are_not_accepted(profile, declarations, change):
    step = declarations.textures['world.textures.white']
    if change == 'step':
        class AliasStep(type(step)):
            pass
        step = AliasStep(**vars(step))
    elif change == 'command':
        class AliasPython(type(step.commands[0])):
            pass
        step = replace(step, commands=[AliasPython(**vars(step.commands[0]))])
    else:
        class AliasProduct(type(step.products[0])):
            pass
        step = replace(step, products=[AliasProduct(**vars(step.products[0]))])
    with pytest.raises(profile.UnsupportedTexture):
        qualify(profile, step)


@pytest.mark.parametrize('relative', ['world/textures/white.json',
                                      'world/gen_textures.py',
                                      'assets/environment/textures/tree-bark.jpg'])
def test_linked_source_is_refused_without_changing_foreign_bytes(profile, declarations, tasks, tmp_path, relative):
    checkout = tmp_path / 'checkout'
    step = declarations.textures['world.textures.bark' if relative.startswith('assets') else 'world.textures.white']
    selected = [declarations.recipe.WORLD / 'texture_catalog.py',
                declarations.recipe.WORLD / 'textures/white.json',
                declarations.recipe.ASSETS / 'environment/textures/tree-bark.jpg']
    for path in dict.fromkeys([*selected, *tasks[step.name].code_inputs]):
        target = checkout / path.relative_to(paths.REPO)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(path)
    foreign = tmp_path / 'foreign'
    foreign.write_bytes(b'preserve source')
    linked = checkout / 'games/yorimichi' / relative
    linked.unlink()
    linked.symlink_to(foreign)
    with pytest.raises((profile.UnsupportedTexture, FileNotFoundError)):
        profile.qualify_texture_step(step, checkout=checkout, output_root=declarations.root)
    assert foreign.read_bytes() == b'preserve source'
    assert not declarations.root.exists()


@pytest.mark.parametrize('relative', ['world/textures', 'assets/environment',
                                      'assets/environment/textures'])
def test_linked_source_parent_is_refused_before_catalogue_execution(profile, declarations, tmp_path, relative):
    checkout = tmp_path / 'checkout'
    foreign = tmp_path / 'foreign'
    marker = foreign / 'marker'
    marker.parent.mkdir()
    marker.write_bytes(b'preserve linked parent')
    parent = checkout / 'games/yorimichi' / relative
    parent.parent.mkdir(parents=True)
    parent.symlink_to(foreign, target_is_directory=True)
    with pytest.raises(profile.UnsupportedTexture):
        profile.qualify_texture_step(declarations.textures['world.textures.white'],
                                     checkout=checkout, output_root=declarations.root)
    assert marker.read_bytes() == b'preserve linked parent'


def test_linked_checkout_is_refused_without_resolving_away_spelling(profile, declarations, tmp_path):
    real = tmp_path / 'real'
    (real / 'games').mkdir(parents=True)
    linked = tmp_path / 'linked'
    linked.symlink_to(real, target_is_directory=True)
    with pytest.raises((profile.UnsupportedTexture, OSError)):
        profile.qualify_texture_step(declarations.textures['world.textures.white'],
                                     checkout=linked, output_root=declarations.root)


@pytest.mark.parametrize('kind', ['output-root', 'output-parent', 'textures-parent'])
def test_linked_output_anchor_is_refused_without_touching_existing_bytes(profile, declarations, tmp_path, kind):
    foreign = tmp_path / 'foreign'
    foreign.mkdir()
    marker = foreign / 'marker'
    marker.write_bytes(b'preserve linked output')
    if kind == 'output-root':
        output_root = tmp_path / 'output'
        output_root.symlink_to(foreign, target_is_directory=True)
    else:
        output_root = tmp_path / 'parent/output'
        if kind == 'output-parent':
            output_root.parent.symlink_to(foreign, target_is_directory=True)
        else:
            output_root.mkdir(parents=True)
            (output_root / 'textures').symlink_to(foreign, target_is_directory=True)
    step = declarations_step('white', output_root / 'textures/T_white.png')
    with pytest.raises((profile.UnsupportedTexture, OSError)):
        profile.qualify_texture_step(step, checkout=paths.REPO, output_root=output_root)
    assert marker.read_bytes() == b'preserve linked output'


def test_missing_source_is_not_absence_authority(profile, declarations, tmp_path):
    checkout = tmp_path / 'checkout'
    step = declarations.textures['world.textures.white']
    with pytest.raises((FileNotFoundError, profile.UnsupportedTexture)):
        profile.qualify_texture_step(step, checkout=checkout, output_root=declarations.root)
    assert not checkout.exists()
    assert not declarations.root.exists()


def test_changed_generator_role_or_catalogue_is_refused(profile, declarations, monkeypatch):
    step = declarations.textures['world.textures.white']
    changed = dict(profile.ROSTER)
    filename, _, assets = changed.pop('white')
    changed['white'] = (filename, 'unknown_generator', assets)
    monkeypatch.setattr(profile, 'ROSTER', changed)
    with pytest.raises(profile.UnsupportedTexture):
        qualify(profile, step)
