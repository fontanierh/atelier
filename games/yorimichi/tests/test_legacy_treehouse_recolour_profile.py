"""Actual full-recipe canopy recolour observations; no Blender or image execution."""
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier import build, build_products, paths


@pytest.fixture(scope='module')
def profile():
    source = paths.REPO / 'games/yorimichi/legacy_treehouse_recolour_profile.py'
    spec = importlib.util.spec_from_file_location('legacy_treehouse_recolour_test', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def declarations(tmp_path_factory):
    from atelier.build_v2.controller_entry import declaration_context
    # The full recipe inventories unrelated retained exports. Give those read-only
    # recipe scans a real source-owned anchor; qualification itself uses a cold tmp root.
    ctx = declaration_context('yorimichi')
    ctx.out = paths.REPO / 'build/yorimichi'
    steps = build.load_recipe('yorimichi').steps(ctx)
    build.check_declarations(steps)
    graph = build_products.Graph(steps)
    selected = graph.select(['world.treehouse_trees.recolour'])
    step = next(step for step in selected if step.name == 'world.treehouse_trees.recolour')
    root = tmp_path_factory.mktemp('treehouse-recolour-cold') / 'yorimichi'
    return SimpleNamespace(root=root, step=rebound(step, root))


@pytest.fixture(scope='module')
def observation(profile, declarations):
    assert not declarations.root.exists()
    result = qualify(profile, declarations.step, declarations.root)
    assert not declarations.root.exists()
    return result


def fresh(declarations):
    return deepcopy(declarations.step)


def qualify(profile, step, root, checkout=paths.REPO):
    return profile.qualify_treehouse_recolour(step, checkout=checkout, output_root=root)


def rebound(step, root, checkout=None):
    old_root = Path(step.commands[0].args[1]).parents[2]
    old_checkout = step.commands[0].script.parents[5]
    def output(value):
        return root / Path(value).relative_to(old_root)
    command = replace(step.commands[0], args=('--recolour', str(output(step.commands[0].args[1]))))
    inputs = [output(value) if value == old_root / 'textures/T_leaf_maple.png' else value
              for value in step.inputs]
    if checkout is not None:
        command = replace(command, script=checkout / command.script.relative_to(old_checkout))
        inputs = [checkout / value.relative_to(old_checkout) if value != old_root / 'textures/T_leaf_maple.png'
                  else value for value in inputs]
    products = [replace(step.products[0], paths=(output(step.products[0].paths[0]),))]
    return replace(step, commands=[command], inputs=inputs, products=products,
                   outputs=[output(value) for value in step.outputs])


def test_actual_full_graph_binds_exact_recolour_roles(declarations, observation):
    step = declarations.step
    root = declarations.root
    assert observation.step == 'world.treehouse_trees.recolour'
    assert observation.script == step.commands[0].script
    assert observation.arguments == ('--recolour', str(root / 'treehouse-data/canopy/recoloured'))
    assert observation.raw_inputs == ()
    assert observation.produced_inputs == (root / 'textures/T_leaf_maple.png',)
    assert observation.code_inputs == tuple(step.inputs[:-1])
    assert observation.products == (('treehouse.canopy_recolours',
                                    (root / 'treehouse-data/canopy/recoloured',)),)
    assert step.outputs == [root / 'treehouse-data/canopy/recoloured/T_leaf_crimson.png',
                            root / 'treehouse-data/canopy/recoloured/T_leaf_amber.png']
    assert step.cache is True and step.heavy is True and step.audit is False
    assert step.toolchain is False and step.verify is None and step.batch is None
    assert step.needs == ['world.textures'] and not step.reads
    with pytest.raises(FrozenInstanceError):
        observation.step = 'other'


def test_positive_observation_has_no_callable_or_native_authority(profile, declarations, observation):
    assert observation == qualify(profile, fresh(declarations), declarations.root)
    assert type(observation).__name__ == 'TreehouseRecolour'
    assert all(not callable(value) for value in vars(observation).values())
    assert not hasattr(observation, 'verify') and not hasattr(observation, 'batch')


def test_warm_input_product_and_required_png_bytes_are_preserved(profile, declarations, tmp_path):
    root = tmp_path / 'warm'
    step = rebound(fresh(declarations), root)
    generated = [root / 'textures/T_leaf_maple.png', *step.outputs]
    for path in generated:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'foreign generated image bytes')
    before = {path: (path.read_bytes(), path.lstat()) for path in generated}
    observed = qualify(profile, step, root)
    assert observed.produced_inputs == (generated[0],)
    assert all((path.read_bytes(), path.lstat()) == before[path] for path in generated)


@pytest.mark.parametrize('missing', [0, 1])
def test_each_missing_required_png_remains_an_observation_not_current(profile, declarations, missing, tmp_path):
    root = tmp_path / f'missing-{missing}'
    step = rebound(fresh(declarations), root)
    present = step.outputs[1 - missing]
    present.parent.mkdir(parents=True)
    present.write_bytes(b'one existing atlas is not completion')
    before = present.read_bytes(), present.lstat()
    observed = qualify(profile, step, root)
    assert not step.outputs[missing].exists()
    assert (present.read_bytes(), present.lstat()) == before
    assert observed.products == (('treehouse.canopy_recolours', (present.parent,)),)
    assert not build.outputs_present(step)


@pytest.mark.parametrize('name', ['world.treehouse_trees.data', 'world.treehouse_trees', 'other'])
def test_unknown_step_is_refused(profile, declarations, name):
    with pytest.raises(profile.UnsupportedTreehouseRecolour):
        qualify(profile, replace(fresh(declarations), name=name), declarations.root)


@pytest.mark.parametrize('change', ['script', 'python', 'destination', 'extra', 'order', 'missing'])
def test_wrong_script_or_arguments_are_refused(profile, declarations, change):
    step = fresh(declarations)
    command = step.commands[0]
    args = list(command.args)
    if change == 'script':
        command = replace(command, script=command.script.with_name('trees.py'))
    elif change == 'python':
        command = build.Python(command.script, command.args)
    elif change == 'destination':
        args[1] = str(Path(args[1]).with_name('other'))
    elif change == 'extra':
        args.extend(['--record', 'foreign'])
    elif change == 'order':
        args.reverse()
    else:
        args.pop()
    with pytest.raises(profile.UnsupportedTreehouseRecolour):
        qualify(profile, replace(step, commands=[replace(command, args=tuple(args))]), declarations.root)


@pytest.mark.parametrize('change', ['threads', 'env', 'factory', 'cache', 'heavy', 'audit', 'toolchain',
                                    'verify', 'batch', 'replan', 'controller', 'needs', 'after',
                                    'references', 'reads', 'queries', 'alias'])
def test_wrong_controls_are_refused(profile, declarations, change):
    step = fresh(declarations)
    if change in {'threads', 'env', 'factory'}:
        command = step.commands[0]
        values = {'threads': {'threads': 4}, 'env': {'env': (('PYTHONHASHSEED', '0'),)},
                  'factory': {'factory_startup': False}}
        step = replace(step, commands=[replace(command, **values[change])])
    else:
        values = {'cache': {'cache': False}, 'heavy': {'heavy': False}, 'audit': {'audit': True},
                  'toolchain': {'toolchain': True}, 'verify': {'verify': lambda: True},
                  'batch': {'batch': build.Batch('foreign')}, 'replan': {'replan': True},
                  'controller': {'controller': object()}, 'needs': {'needs': []},
                  'after': {'after': ['other']}, 'references': {'references': ['other']},
                  'reads': {'reads': ['other']}, 'queries': {'queries': [object()]}}
        if change == 'alias':
            class AliasStep(type(step)):
                pass
            step = AliasStep(**vars(step))
        else:
            step = replace(step, **values[change])
    with pytest.raises(profile.UnsupportedTreehouseRecolour):
        qualify(profile, step, declarations.root)


def test_unknown_step_attribute_is_refused(profile, declarations):
    step = fresh(declarations)
    step.extra_authority = True
    with pytest.raises(profile.UnsupportedTreehouseRecolour):
        qualify(profile, step, declarations.root)


@pytest.mark.parametrize('change', ['missing', 'extra', 'duplicate', 'order', 'name', 'directory', 'alias'])
def test_wrong_required_outputs_are_refused(profile, declarations, change):
    step = fresh(declarations)
    outputs = list(step.outputs)
    if change == 'missing':
        outputs.pop()
    elif change == 'extra':
        outputs.append(outputs[-1].with_name('T_leaf_maple.png'))
    elif change == 'duplicate':
        outputs.append(outputs[-1])
    elif change == 'order':
        outputs.reverse()
    elif change == 'name':
        outputs[0] = outputs[0].with_name('T_leaf_ginkgo.png')
    elif change == 'directory':
        outputs[0] = outputs[0].parent
    else:
        class AliasPath(type(outputs[0])):
            pass
        outputs[0] = AliasPath(str(outputs[0]))
    with pytest.raises(profile.UnsupportedTreehouseRecolour):
        qualify(profile, replace(step, outputs=outputs), declarations.root)


@pytest.mark.parametrize('change', ['name', 'path', 'extra', 'optional', 'collection', 'alias'])
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
        products[0] = replace(products[0], optional_paths=(products[0].paths[0] / 'extra.png',))
    elif change == 'collection':
        products[0] = replace(products[0], collection='x', bounds=(0., 0., 0., 1., 1., 1.))
    else:
        class AliasProduct(type(products[0])):
            pass
        products[0] = AliasProduct(**vars(products[0]))
    with pytest.raises(profile.UnsupportedTreehouseRecolour):
        qualify(profile, replace(step, products=products), declarations.root)


@pytest.mark.parametrize('change', ['script', 'order', 'extra', 'duplicate', 'missing-maple', 'raw', 'alias'])
def test_wrong_inputs_are_refused(profile, declarations, change):
    step = fresh(declarations)
    inputs = list(step.inputs)
    if change == 'script':
        inputs[4] = inputs[4].with_name('other.py')
    elif change == 'order':
        inputs[0], inputs[1] = inputs[1], inputs[0]
    elif change == 'extra':
        inputs.append(paths.REPO / 'games/yorimichi/region_exports.py')
    elif change == 'duplicate':
        inputs.append(inputs[-1])
    elif change == 'missing-maple':
        inputs.pop()
    elif change == 'raw':
        inputs.append(paths.REPO / 'games/yorimichi/assets/treehouse/export-parameters/Tree_Canopy_Maple.json')
    else:
        class AliasPath(type(inputs[0])):
            pass
        inputs[0] = AliasPath(str(inputs[0]))
    with pytest.raises(profile.UnsupportedTreehouseRecolour):
        qualify(profile, replace(step, inputs=inputs), declarations.root)


def finite_checkout(step, tmp_path):
    import shutil
    checkout = tmp_path / 'checkout'
    original = step.commands[0].script.parents[5]
    for source in step.inputs[:-1]:
        target = checkout / source.relative_to(original)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return checkout


@pytest.mark.parametrize('relative', ['games/yorimichi/world/regions/treehouse/canopy_data.py',
                                      'games/yorimichi/world/regions/treehouse/trees.py',
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
        with pytest.raises(profile.UnsupportedTreehouseRecolour):
            qualify(profile, step, declarations.root, checkout)
    finally:
        profile._source = original_reader
    assert source in reached
    assert foreign.read_bytes() == original_bytes


@pytest.mark.parametrize('kind', ['destination', 'destination-parent', 'crimson', 'amber', 'maple'])
def test_linked_or_invalid_generated_path_is_refused_without_changes(profile, declarations, tmp_path, kind):
    root = tmp_path / 'output'
    step = rebound(fresh(declarations), root)
    foreign = tmp_path / 'foreign'
    foreign.mkdir()
    marker = foreign / 'marker'
    marker.write_bytes(b'preserve generated data')
    destination = root / 'treehouse-data/canopy/recoloured'
    target = {'crimson': step.outputs[0], 'amber': step.outputs[1],
              'maple': root / 'textures/T_leaf_maple.png'}.get(kind)
    if kind == 'destination':
        destination.parent.mkdir(parents=True)
        destination.symlink_to(foreign, target_is_directory=True)
    elif kind == 'destination-parent':
        destination.parent.parent.mkdir(parents=True)
        destination.parent.symlink_to(foreign, target_is_directory=True)
    else:
        target.parent.mkdir(parents=True)
        target.symlink_to(marker)
    with pytest.raises(profile.UnsupportedTreehouseRecolour):
        qualify(profile, step, root)
    assert marker.read_bytes() == b'preserve generated data'


def test_missing_source_is_honest_refusal(profile, declarations, tmp_path):
    with pytest.raises(profile.UnsupportedTreehouseRecolour):
        qualify(profile, fresh(declarations), declarations.root, tmp_path / 'absent')


def test_recolour_helpers_and_images_are_never_executed(profile, declarations, monkeypatch):
    import ast
    original = ast.parse
    forbidden = {'bpy', 'treehouse.trees', 'treehouse.canopy_data'}
    def observing_parse(source, *args, **kwargs):
        assert not any(name in sys.modules for name in forbidden)
        return original(source, *args, **kwargs)
    import sys
    for name in forbidden:
        assert name not in sys.modules
    monkeypatch.setattr(ast, 'parse', observing_parse)
    assert qualify(profile, fresh(declarations), declarations.root).step == 'world.treehouse_trees.recolour'
    assert not any(name in sys.modules for name in forbidden)
