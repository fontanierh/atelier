"""Actual full-recipe canopy data observations; no script or generated-data execution."""
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier import build, build_products, paths


PARENTS = ('Tree_Canopy_Maple', 'Tree_Canopy_Crimson', 'Tree_Canopy_Amber', 'Tree_Canopy_Ginkgo')


@pytest.fixture(scope='module')
def profile():
    source = paths.REPO / 'games/yorimichi/legacy_treehouse_data_profile.py'
    spec = importlib.util.spec_from_file_location('legacy_treehouse_data_test', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def declarations(tmp_path_factory):
    from atelier.build_v2.controller_entry import declaration_context
    root = tmp_path_factory.mktemp('treehouse-data-cold') / 'yorimichi'
    ctx = declaration_context('yorimichi')
    ctx.out = root
    steps = build.load_recipe('yorimichi').steps(ctx)
    build.check_declarations(steps)
    graph = build_products.Graph(steps)
    selected = graph.select(['world.treehouse_trees.data'])
    step = next(step for step in selected if step.name == 'world.treehouse_trees.data')
    return SimpleNamespace(root=root, step=step)


@pytest.fixture(scope='module')
def observation(profile, declarations):
    assert not declarations.root.exists()
    result = profile.qualify_treehouse_data(declarations.step, checkout=paths.REPO, output_root=declarations.root)
    assert not declarations.root.exists()
    return result


def fresh(declarations):
    return deepcopy(declarations.step)


def qualify(profile, step, root, checkout=paths.REPO):
    return profile.qualify_treehouse_data(step, checkout=checkout, output_root=root)


def rebound(step, root, checkout=None):
    old_root = Path(step.commands[0].args[1]).parents[2]
    old_checkout = step.commands[0].script.parents[5]
    def output(value):
        return root / Path(value).relative_to(old_root)
    args = [str(output(value)) if index % 2 else value for index, value in enumerate(step.commands[0].args)]
    command = replace(step.commands[0], args=tuple(args))
    inputs = list(step.inputs)
    if checkout is not None:
        command = replace(command, script=checkout / command.script.relative_to(old_checkout))
        inputs = [checkout / value.relative_to(old_checkout) for value in inputs]
    products = [replace(step.products[0], paths=(output(step.products[0].paths[0]),))]
    return replace(step, commands=[command], inputs=inputs, products=products)


def test_actual_full_graph_binds_exact_data_roles(declarations, observation):
    step = declarations.step
    assert observation.step == step.name
    assert observation.script == step.commands[0].script
    assert observation.arguments == step.commands[0].args
    assert observation.raw_inputs == ()
    assert observation.produced_inputs == tuple(
        declarations.root / f'treehouse-data/canopy/records/{parent}.json' for parent in PARENTS)
    assert observation.code_inputs == tuple(step.inputs)
    assert observation.products == (('treehouse.canopy_dimensions',
                                    (declarations.root / 'treehouse-data/canopy/trees.json',)),)
    assert step.cache is True and step.audit is False and step.heavy is False
    assert step.verify is None and step.batch is None and step.toolchain is False
    assert '--recolour' not in observation.arguments
    assert not any(record in step.inputs for record in observation.produced_inputs)
    with pytest.raises(FrozenInstanceError):
        observation.step = 'other'


def test_warm_records_and_output_bytes_are_preserved(profile, declarations, tmp_path):
    root = tmp_path / 'warm'
    step = rebound(fresh(declarations), root)
    paths_to_make = [root / 'treehouse-data/canopy/trees.json',
                     *(root / f'treehouse-data/canopy/records/{parent}.json' for parent in PARENTS)]
    for path in paths_to_make:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'foreign generated data')
    before = {path: (path.read_bytes(), path.lstat()) for path in paths_to_make}
    observed = qualify(profile, step, root)
    assert observed.produced_inputs == tuple(paths_to_make[1:])
    assert all((path.read_bytes(), path.lstat()) == before[path] for path in paths_to_make)


def test_positive_observation_does_not_execute_script_or_generated_reader(profile, declarations, observation):
    assert observation == qualify(profile, fresh(declarations), declarations.root)
    assert type(observation).__name__ == 'TreehouseData'
    assert all(not callable(value) for value in vars(observation).values())


@pytest.mark.parametrize('name', ['world.treehouse_trees.recolour', 'world.treehouse_trees.geometry', 'other'])
def test_unknown_step_is_refused(profile, declarations, name):
    with pytest.raises(profile.UnsupportedTreehouseData):
        qualify(profile, replace(fresh(declarations), name=name), declarations.root)


@pytest.mark.parametrize('change', ['script', 'blender', 'output', 'record', 'recolour', 'extra', 'order'])
def test_wrong_script_or_arguments_are_refused(profile, declarations, change):
    step = fresh(declarations)
    command = step.commands[0]
    args = list(command.args)
    if change == 'script':
        command = replace(command, script=command.script.with_name('other.py'))
    elif change == 'blender':
        command = build.Blender(command.script, command.args, threads=3, factory_startup=True)
    elif change == 'output':
        args[1] = str(Path(args[1]).with_name('other.json'))
    elif change == 'record':
        args[3] = str(Path(args[3]).with_name('Tree_Canopy_Amber.json'))
    elif change == 'recolour':
        args.extend(['--recolour', str(declarations.root / 'recoloured')])
    elif change == 'extra':
        args.extend(['--record', args[3]])
    else:
        args[2], args[3], args[4], args[5] = args[4], args[5], args[2], args[3]
    with pytest.raises(profile.UnsupportedTreehouseData):
        qualify(profile, replace(step, commands=[replace(command, args=tuple(args))]), declarations.root)


@pytest.mark.parametrize('change', ['audit', 'cache', 'heavy', 'toolchain', 'verify', 'batch', 'replan',
                                    'controller', 'needs', 'after', 'references', 'outputs', 'queries', 'alias'])
def test_wrong_controls_are_refused(profile, declarations, change):
    step = fresh(declarations)
    values = {'audit': {'audit': True}, 'cache': {'cache': False}, 'heavy': {'heavy': True},
              'toolchain': {'toolchain': True}, 'verify': {'verify': lambda: True},
              'batch': {'batch': build.Batch('other')}, 'replan': {'replan': True},
              'controller': {'controller': object()}, 'needs': {'needs': ['world.textures']},
              'after': {'after': ['world.other']}, 'references': {'references': ['other']},
              'outputs': {'outputs': [step.products[0].paths[0]]}, 'queries': {'queries': [object()]}}
    if change == 'alias':
        class AliasStep(type(step)):
            pass
        step = AliasStep(**vars(step))
    else:
        step = replace(step, **values[change])
    with pytest.raises(profile.UnsupportedTreehouseData):
        qualify(profile, step, declarations.root)


def test_unknown_step_attribute_is_refused(profile, declarations):
    step = fresh(declarations)
    step.extra_authority = True
    with pytest.raises(profile.UnsupportedTreehouseData):
        qualify(profile, step, declarations.root)


@pytest.mark.parametrize('change', ['missing', 'order', 'extra', 'duplicate'])
def test_wrong_record_reads_are_refused(profile, declarations, change):
    step = fresh(declarations)
    reads = list(step.reads)
    if change == 'missing':
        reads.pop()
    elif change == 'order':
        reads[0], reads[1] = reads[1], reads[0]
    elif change == 'extra':
        reads.append('treehouse.canopy_record.Future')
    else:
        reads.append(reads[-1])
    with pytest.raises(profile.UnsupportedTreehouseData):
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
        products.append(build_products.Product('other', (products[0].paths[0].with_name('other.json'),)))
    elif change == 'optional':
        products[0] = replace(products[0], optional_paths=(products[0].paths[0].with_suffix('.tmp'),))
    elif change == 'collection':
        products[0] = replace(products[0], collection='x', bounds=(0., 0., 0., 1., 1., 1.))
    else:
        class AliasProduct(type(products[0])):
            pass
        products[0] = AliasProduct(**vars(products[0]))
    with pytest.raises(profile.UnsupportedTreehouseData):
        qualify(profile, replace(step, products=products), declarations.root)


@pytest.mark.parametrize('change', ['script', 'order', 'extra', 'duplicate', 'record', 'alias'])
def test_wrong_source_inputs_are_refused(profile, declarations, change):
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
    elif change == 'record':
        inputs.append(declarations.root / 'treehouse-data/canopy/records/Tree_Canopy_Maple.json')
    else:
        class AliasPath(type(inputs[0])):
            pass
        inputs[0] = AliasPath(str(inputs[0]))
    with pytest.raises(profile.UnsupportedTreehouseData):
        qualify(profile, replace(step, inputs=inputs), declarations.root)


def finite_checkout(step, tmp_path):
    import shutil
    checkout = tmp_path / 'checkout'
    original = step.commands[0].script.parents[5]
    for source in step.inputs:
        target = checkout / source.relative_to(original)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return checkout


@pytest.mark.parametrize('relative', ['games/yorimichi/world/regions/treehouse/canopy_data.py',
                                      'games/yorimichi/world/regions/treehouse/canopy.py',
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
        with pytest.raises(profile.UnsupportedTreehouseData):
            qualify(profile, step, declarations.root, checkout)
    finally:
        profile._source = original_reader
    assert source in reached
    assert foreign.read_bytes() == original_bytes


@pytest.mark.parametrize('kind', ['output', 'output-parent', 'record', 'record-parent'])
def test_linked_or_invalid_generated_path_is_refused_without_changes(profile, declarations, tmp_path, kind):
    root = tmp_path / 'output'
    step = rebound(fresh(declarations), root)
    foreign = tmp_path / 'foreign'
    foreign.mkdir()
    marker = foreign / 'marker'
    marker.write_bytes(b'preserve generated data')
    output = root / 'treehouse-data/canopy/trees.json'
    record = root / 'treehouse-data/canopy/records/Tree_Canopy_Maple.json'
    if kind == 'output':
        output.parent.mkdir(parents=True)
        output.symlink_to(marker)
    elif kind == 'output-parent':
        output.parent.parent.mkdir(parents=True)
        output.parent.symlink_to(foreign, target_is_directory=True)
    elif kind == 'record':
        record.parent.mkdir(parents=True)
        record.symlink_to(marker)
    else:
        record.parent.parent.mkdir(parents=True)
        record.parent.symlink_to(foreign, target_is_directory=True)
    with pytest.raises(profile.UnsupportedTreehouseData):
        qualify(profile, step, root)
    assert marker.read_bytes() == b'preserve generated data'


def test_missing_source_is_honest_refusal(profile, declarations, tmp_path):
    with pytest.raises(profile.UnsupportedTreehouseData):
        qualify(profile, fresh(declarations), declarations.root, tmp_path / 'absent')
