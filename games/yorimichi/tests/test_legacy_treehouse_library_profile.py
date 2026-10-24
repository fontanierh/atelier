"""Actual full-recipe Treehouse library observations; no production helper execution."""
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier import build, build_products, paths


TREES = ('Tree_Canopy_Maple', 'Tree_Canopy_Crimson', 'Tree_Canopy_Amber', 'Tree_Canopy_Ginkgo')
PROPS = tuple('TH_P_' + slug for slug in (
    'backpack', 'barrel', 'basket', 'bell', 'bookshelf', 'crate_desk', 'futon',
    'globe', 'kamado', 'log_table', 'planter', 'stump_kettle', 'telescope'))
SURFACES = ('TH_Structure', 'TH_Frame', 'TH_Trunks', 'TH_Dressing')
ROSTERS = {'trees': TREES, 'props': PROPS, 'surfaces': SURFACES}
STEP_NAMES = {'trees': 'world.treehouse_trees', 'props': 'world.treehouse_props',
              'surfaces': 'world.treehouse'}


@pytest.fixture(scope='module')
def profile():
    source = paths.REPO / 'games/yorimichi/legacy_treehouse_library_profile.py'
    spec = importlib.util.spec_from_file_location('legacy_treehouse_library_test', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def declarations(tmp_path_factory):
    from atelier.build_v2.controller_entry import declaration_context
    root = tmp_path_factory.mktemp('treehouse-library-cold') / 'yorimichi'
    for kind, names in ROSTERS.items():
        region = 'treehouse_surfaces' if kind == 'surfaces' else 'treehouse_' + kind
        for parent in names:
            folder = root / 'planned_exports' / region / parent
            folder.mkdir(parents=True)
            (folder / 'plan.json').write_text(json.dumps(dict(
                schema=1, parent=parent, complete=True, triangle_limit=32768,
                source_triangles=1,
                pieces=[dict(name=parent, payload=parent + '.npz', triangles=1)])))
    ctx = declaration_context('yorimichi')
    ctx.out = root
    steps = build.load_recipe('yorimichi').steps(ctx)
    build.check_declarations(steps)
    graph = build_products.Graph(steps)
    result = {}
    for kind, name in STEP_NAMES.items():
        selected = graph.select([name])
        step = next(step for step in selected if step.name == name)
        region = 'treehouse_surfaces' if kind == 'surfaces' else 'treehouse_' + kind
        exports = [value for value in steps if value.name.startswith(f'world.{region}.export.')]
        assert len(exports) == len(ROSTERS[kind])
        result[kind] = step
    cold_root = tmp_path_factory.mktemp('treehouse-library-plan-free') / 'yorimichi'
    cold_ctx = declaration_context('yorimichi')
    cold_ctx.out = cold_root
    cold_steps = build.load_recipe('yorimichi').steps(cold_ctx)
    build.check_declarations(cold_steps)
    build_products.Graph(cold_steps)
    cold = {kind: next(step for step in cold_steps if step.name == name)
            for kind, name in STEP_NAMES.items()}
    assert not any(step.name.startswith(('world.treehouse_trees.export.',
                                        'world.treehouse_props.export.',
                                        'world.treehouse_surfaces.export.')) for step in cold_steps)
    assert not cold_root.exists()
    return SimpleNamespace(root=root, steps=result, cold_root=cold_root, cold=cold)


def fresh(declarations, kind):
    return deepcopy(declarations.steps[kind])


def qualify(profile, step, root, checkout=paths.REPO):
    return profile.qualify_treehouse_library(step, checkout=checkout, output_root=root)


def rebound(step, root, checkout=None):
    old_root = Path(step.commands[0].args[1])
    old_checkout = step.commands[0].script.parents[5]
    def output(value):
        return root / Path(value).relative_to(old_root)
    command = replace(step.commands[0], args=(step.commands[0].args[0], str(root),
                                              *step.commands[0].args[2:]))
    if checkout is not None:
        command = replace(command, script=checkout / command.script.relative_to(old_checkout))
    inputs = [checkout / value.relative_to(old_checkout) for value in step.inputs] if checkout else list(step.inputs)
    products = [replace(product, paths=tuple(output(value) for value in product.paths))
                for product in step.products]
    return replace(step, commands=[command], inputs=inputs, products=products)


@pytest.mark.parametrize('kind', ['trees', 'props', 'surfaces'])
def test_actual_full_graph_binds_exact_library_roles(profile, declarations, kind):
    step = fresh(declarations, kind)
    observed = qualify(profile, step, declarations.root)
    names = ROSTERS[kind]
    region = 'treehouse_surfaces' if kind == 'surfaces' else 'treehouse_' + kind
    expected_names = () if kind == 'surfaces' else names
    assert observed.step == STEP_NAMES[kind] and observed.kind == kind
    assert observed.script == step.commands[0].script
    assert observed.arguments == ('--out', str(declarations.root), '--kind', kind,
                                 *(item for name in expected_names for item in ('--name', name)))
    assert observed.raw_inputs == () and observed.code_inputs == tuple(step.inputs)
    assert observed.products == tuple((product.name, product.paths) for product in step.products)
    assert step.cache is True and step.audit is False and step.heavy is False
    assert step.toolchain is False and step.verify is None and step.batch is None
    geometry = [declarations.root / 'planned_exports' / region / name for name in names]
    exports = [declarations.root / 'exports' / f'world.{region}.export' / name for name in names]
    assert observed.produced_inputs[-2 * len(names):] == tuple([*geometry, *exports])
    assert len(step.reads) == len(observed.produced_inputs) - (kind == 'surfaces')
    with pytest.raises(FrozenInstanceError):
        observed.kind = 'other'


@pytest.mark.parametrize('kind', ['trees', 'props', 'surfaces'])
def test_cold_plan_free_declaration_is_typed_unsupported(profile, declarations, kind):
    step = deepcopy(declarations.cold[kind])
    with pytest.raises(profile.UnsupportedTreehouseLibrary):
        qualify(profile, step, declarations.cold_root)
    assert not declarations.cold_root.exists()


@pytest.mark.parametrize('kind', ['trees', 'props', 'surfaces'])
def test_warm_generated_bytes_and_stats_are_preserved_without_source_reads(
        profile, declarations, kind, tmp_path, monkeypatch):
    root = tmp_path / kind
    step = rebound(fresh(declarations, kind), root)
    cold_observed = qualify(profile, fresh(declarations, kind), declarations.root)
    generated = [*cold_observed.produced_inputs,
                 *(path for _, paths_ in cold_observed.products for path in paths_)]
    generated = [root / path.relative_to(declarations.root) for path in generated]
    markers = []
    for index, path in enumerate(generated):
        if path.suffix == '.json':
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'foreign generated metadata')
            markers.append(path)
        else:
            path.mkdir(parents=True, exist_ok=True)
            marker = path / 'preserve-me'
            marker.write_bytes(b'foreign generated payload')
            markers.append(marker)
    before = {path: (path.read_bytes(), path.lstat()) for path in markers}
    original_reader = profile._source
    reached = []
    def observing_reader(checkout_arg, path_arg):
        path = Path(path_arg)
        assert path not in generated
        reached.append(path)
        return original_reader(checkout_arg, path_arg)
    monkeypatch.setattr(profile, '_source', observing_reader)
    observed = qualify(profile, step, root)
    assert set(step.inputs) <= set(reached)
    assert all((path.read_bytes(), path.lstat()) == before[path] for path in markers)
    assert all(not callable(value) for value in vars(observed).values())


@pytest.mark.parametrize('name', ['world.treehouse_trees.assembled', 'world.treehouse', 'other'])
def test_unknown_variant_is_refused(profile, declarations, name):
    with pytest.raises(profile.UnsupportedTreehouseLibrary):
        qualify(profile, replace(fresh(declarations, 'trees'), name=name), declarations.root)


@pytest.mark.parametrize('change', ['script', 'blender', 'out', 'kind', 'name', 'extra', 'order', 'missing'])
def test_wrong_script_or_arguments_are_refused(profile, declarations, change):
    step = fresh(declarations, 'trees')
    command = step.commands[0]
    args = list(command.args)
    if change == 'script':
        command = replace(command, script=command.script.with_name('other.py'))
    elif change == 'blender':
        command = build.Blender(command.script, command.args, threads=3, factory_startup=True)
    elif change == 'out':
        args[1] = str(Path(args[1]).with_name('other'))
    elif change == 'kind':
        args[3] = 'props'
    elif change == 'name':
        args[5] = 'Tree_Canopy_Ginkgo'
    elif change == 'extra':
        args.extend(['--name', 'Future'])
    elif change == 'order':
        args[4], args[5], args[6], args[7] = args[6], args[7], args[4], args[5]
    else:
        args = args[:-2]
    with pytest.raises(profile.UnsupportedTreehouseLibrary):
        qualify(profile, replace(step, commands=[replace(command, args=tuple(args))]), declarations.root)


@pytest.mark.parametrize('change', ['cache', 'heavy', 'audit', 'toolchain', 'verify', 'batch', 'replan',
                                    'controller', 'needs', 'after', 'references', 'outputs', 'queries', 'alias'])
def test_wrong_controls_are_refused(profile, declarations, change):
    step = fresh(declarations, 'props')
    values = {'cache': {'cache': False}, 'heavy': {'heavy': True}, 'audit': {'audit': True},
              'toolchain': {'toolchain': True}, 'verify': {'verify': lambda: True},
              'batch': {'batch': build.Batch('other')}, 'replan': {'replan': True},
              'controller': {'controller': object()}, 'needs': {'needs': ['world.textures']},
              'after': {'after': ['other']}, 'references': {'references': ['other']},
              'outputs': {'outputs': [step.products[0].paths[0]]}, 'queries': {'queries': [object()]}}
    if change == 'alias':
        class AliasStep(type(step)):
            pass
        step = AliasStep(**vars(step))
    else:
        step = replace(step, **values[change])
    with pytest.raises(profile.UnsupportedTreehouseLibrary):
        qualify(profile, step, declarations.root)


def test_unknown_step_attribute_is_refused(profile, declarations):
    step = fresh(declarations, 'trees')
    step.extra_authority = True
    with pytest.raises(profile.UnsupportedTreehouseLibrary):
        qualify(profile, step, declarations.root)


@pytest.mark.parametrize('change', ['missing', 'extra', 'duplicate', 'order', 'aggregate-only', 'future'])
def test_wrong_read_roster_is_refused(profile, declarations, change):
    step = fresh(declarations, 'trees')
    reads = list(step.reads)
    if change == 'missing':
        reads.pop()
    elif change == 'extra':
        reads.append('world.treehouse_trees.export.Future')
    elif change == 'duplicate':
        reads.append(reads[-1])
    elif change == 'order':
        reads[-1], reads[-2] = reads[-2], reads[-1]
    elif change == 'aggregate-only':
        reads = reads[:3]
    else:
        reads[-1] = 'world.treehouse_trees.export.Future'
    with pytest.raises(profile.UnsupportedTreehouseLibrary):
        qualify(profile, replace(step, reads=reads), declarations.root)


@pytest.mark.parametrize('change', ['name', 'path', 'extra', 'optional', 'collection', 'alias'])
def test_wrong_product_is_refused(profile, declarations, change):
    step = fresh(declarations, 'surfaces')
    products = list(step.products)
    if change == 'name':
        products[0] = replace(products[0], name='other')
    elif change == 'path':
        products[0] = replace(products[0], paths=(products[0].paths[0].with_name('other'), *products[0].paths[1:]))
    elif change == 'extra':
        products.append(build_products.Product('other', (products[0].paths[0].with_name('other'),)))
    elif change == 'optional':
        products[0] = replace(products[0], optional_paths=(products[0].paths[0] / 'extra',))
    elif change == 'collection':
        products[0] = replace(products[0], collection='x', bounds=(0., 0., 0., 1., 1., 1.))
    else:
        class AliasProduct(type(products[0])):
            pass
        products[0] = AliasProduct(**vars(products[0]))
    with pytest.raises(profile.UnsupportedTreehouseLibrary):
        qualify(profile, replace(step, products=products), declarations.root)


@pytest.mark.parametrize('change', ['script', 'order', 'extra', 'duplicate', 'generated', 'alias'])
def test_wrong_inputs_are_refused(profile, declarations, change):
    step = fresh(declarations, 'trees')
    inputs = list(step.inputs)
    if change == 'script':
        inputs[5] = inputs[5].with_name('other.py')
    elif change == 'order':
        inputs[0], inputs[1] = inputs[1], inputs[0]
    elif change == 'extra':
        inputs.append(paths.REPO / 'games/yorimichi/region_exports.py')
    elif change == 'duplicate':
        inputs.append(inputs[-1])
    elif change == 'generated':
        inputs.append(declarations.root / 'treehouse-data/canopy/trees.json')
    else:
        class AliasPath(type(inputs[0])):
            pass
        inputs[0] = AliasPath(str(inputs[0]))
    with pytest.raises(profile.UnsupportedTreehouseLibrary):
        qualify(profile, replace(step, inputs=inputs), declarations.root)


def finite_checkout(step, tmp_path):
    import shutil
    checkout = tmp_path / 'checkout'
    original = step.commands[0].script.parents[5]
    for source in step.inputs:
        target = checkout / source.relative_to(original)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    for relative in ('treehouse_atomic_build.py', 'treehouse_pieces.py'):
        source = original / 'games/yorimichi' / relative
        target = checkout / 'games/yorimichi' / relative
        shutil.copy2(source, target)
    return checkout


@pytest.mark.parametrize('relative', ['games/yorimichi/world/regions/treehouse/assemble_atomic.py',
                                      'games/yorimichi/treehouse_pieces.py',
                                      'platform/studio/atelier/export_assembly.py'])
def test_linked_source_reaches_nofollow_refusal(profile, declarations, tmp_path, relative):
    checkout = finite_checkout(fresh(declarations, 'trees'), tmp_path)
    step = rebound(fresh(declarations, 'trees'), declarations.root, checkout)
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
        with pytest.raises(profile.UnsupportedTreehouseLibrary):
            qualify(profile, step, declarations.root, checkout)
    finally:
        profile._source = original_reader
    assert source in reached
    assert foreign.read_bytes() == original_bytes


@pytest.mark.parametrize('kind', ['output', 'output-parent', 'planner', 'export', 'metadata'])
def test_linked_or_invalid_generated_path_is_refused_without_changes(profile, declarations, tmp_path, kind):
    root = tmp_path / 'output'
    step = rebound(fresh(declarations, 'trees'), root)
    foreign = tmp_path / 'foreign'
    foreign.mkdir()
    marker = foreign / 'marker'
    marker.write_bytes(b'preserve generated data')
    output = root / 'treehouse/trees'
    produced = root / 'planned_exports/treehouse_trees/Tree_Canopy_Maple'
    if kind == 'output':
        output.parent.mkdir(parents=True)
        output.symlink_to(foreign, target_is_directory=True)
    elif kind == 'output-parent':
        output.parent.parent.mkdir(parents=True)
        output.parent.symlink_to(foreign, target_is_directory=True)
    elif kind == 'planner':
        produced.parent.mkdir(parents=True)
        produced.symlink_to(foreign, target_is_directory=True)
    elif kind == 'export':
        produced = root / 'exports/world.treehouse_trees.export/Tree_Canopy_Maple'
        produced.parent.mkdir(parents=True)
        produced.symlink_to(foreign, target_is_directory=True)
    else:
        produced = root / 'treehouse-data/canopy/trees.json'
        produced.parent.mkdir(parents=True)
        produced.symlink_to(marker)
    with pytest.raises(profile.UnsupportedTreehouseLibrary):
        qualify(profile, step, root)
    assert marker.read_bytes() == b'preserve generated data'


def test_missing_source_is_honest_refusal(profile, declarations, tmp_path):
    with pytest.raises(profile.UnsupportedTreehouseLibrary):
        qualify(profile, fresh(declarations, 'trees'), declarations.root, tmp_path / 'absent')


@pytest.mark.parametrize('old,new', [
    ("choices=('surfaces','props','trees')", "choices=('surfaces','trees')"),
    ("'--name',action='append'", "'--name',action='store'"),
    ("tuple(names)!=tuple(PROPS", "tuple(names)==tuple(PROPS"),
    ("region='treehouse_'+kind", "region='other_'+kind"),
    ("if args.kind=='surfaces'", "if args.kind=='trees'"),
    ("PARENTS=('TH_Structure'", "PARENTS=('Other'"),
])
def test_changed_source_role_reaches_exact_check(profile, declarations, tmp_path, monkeypatch, old, new):
    checkout = finite_checkout(fresh(declarations, 'trees'), tmp_path)
    step = rebound(fresh(declarations, 'trees'), declarations.root, checkout)
    script = step.commands[0].script
    original = script.read_text()
    assert old in original
    script.write_text(original.replace(old, new, 1))
    def no_scan(*args, **kwargs):
        pytest.fail('changed source roles must refuse before import discovery')
    monkeypatch.setattr(profile._scanner_type(), 'local_imports', no_scan)
    with pytest.raises(profile.UnsupportedTreehouseLibrary):
        qualify(profile, step, declarations.root, checkout)


@pytest.mark.parametrize('kind', ['trees', 'props', 'surfaces'])
def test_cold_observation_prechecks_sources_and_never_executes_helpers(
        profile, declarations, tmp_path, monkeypatch, kind):
    from atelier import export_assembly, export_manifest, file_copy, model_files
    root = tmp_path / 'absent-output'
    step = rebound(fresh(declarations, kind), root)
    reached = []
    source_reader = profile._source
    scanner = profile._scanner_type().local_imports
    def source(checkout, path):
        assert Path(path).is_relative_to(paths.REPO)
        assert not Path(path).is_relative_to(root)
        reached.append(Path(path))
        return source_reader(checkout, path)
    def scan(*args, **kwargs):
        assert set(step.inputs) <= set(reached)
        return scanner(*args, **kwargs)
    def forbidden(*args, **kwargs):
        pytest.fail('qualification executed a production helper')
    monkeypatch.setattr(profile, '_source', source)
    monkeypatch.setattr(profile._scanner_type(), 'local_imports', scan)
    for module, names in ((export_assembly, ('assemble', 'copy_verified', 'destination_members')),
                          (export_manifest, ('validate',)), (file_copy, ('copy_file',)),
                          (model_files, ('regular_files', 'retain_files'))):
        for name in names:
            monkeypatch.setattr(module, name, forbidden)
    observed = qualify(profile, step, root)
    assert observed.code_inputs == tuple(step.inputs)
    assert not root.exists()


def test_generated_input_never_reaches_source_reader(profile, declarations, monkeypatch):
    step = fresh(declarations, 'trees')
    generated = declarations.root / 'planned_exports/treehouse_trees/Tree_Canopy_Maple/plan.json'
    def forbidden(*args, **kwargs):
        pytest.fail('an invalid input roster reached a source reader')
    monkeypatch.setattr(profile, '_source', forbidden)
    with pytest.raises(profile.UnsupportedTreehouseLibrary):
        qualify(profile, replace(step, inputs=[*step.inputs, generated]), declarations.root)


@pytest.mark.parametrize('change', ['checkout-alias', 'output-alias', 'checkout-parent', 'output-parent',
                                    'boolean-alias'])
def test_anchor_and_control_aliases_are_refused(profile, declarations, change):
    class AliasPath(type(paths.REPO)):
        pass
    checkout, root = paths.REPO, declarations.root
    step = fresh(declarations, 'trees')
    if change == 'checkout-alias':
        checkout = AliasPath(checkout)
    elif change == 'output-alias':
        root = AliasPath(root)
    elif change == 'checkout-parent':
        checkout = checkout / 'games/..'
    elif change == 'output-parent':
        root = root / 'child/..'
    else:
        step = replace(step, heavy=0)
    with pytest.raises(profile.UnsupportedTreehouseLibrary):
        qualify(profile, step, root, checkout)


def test_unexpected_import_candidate_is_refused_before_source_read(profile, declarations, monkeypatch):
    generated = declarations.root / 'planned_exports/treehouse_trees/Tree_Canopy_Maple/plan.json'
    original = profile._source
    def source(checkout, path):
        assert path != generated
        return original(checkout, path)
    monkeypatch.setattr(profile, '_source', source)
    monkeypatch.setattr(profile._scanner_type(), 'resolve', lambda *args: [generated])
    with pytest.raises(profile.UnsupportedTreehouseLibrary, match='import escapes'):
        qualify(profile, fresh(declarations, 'trees'), declarations.root)
