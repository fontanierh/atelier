"""Finite metadata observations only: no native tools or producer bodies."""
from copy import deepcopy
from dataclasses import FrozenInstanceError, fields, replace
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier import build, build_products, paths


@pytest.fixture(scope='module')
def profile():
    source = paths.REPO / 'games/yorimichi/legacy_world_layout_profile.py'
    spec = importlib.util.spec_from_file_location('world_layout_profile_test', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def default_selection(craterpark_generator_by_choice, monkeypatch):
    for name in ('ATELIER_CRATERPARK_V4_DESIGN', 'ATELIER_CRATERPARK_EDITOR_PARK', 'ATELIER_CRATERPARK_EDITOR_LINES'):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(scope='module')
def declarations(tmp_path_factory):
    from atelier.build_v2.controller_entry import declaration_context
    with pytest.MonkeyPatch.context() as patch:
        for name in ('ATELIER_CRATERPARK_V4_DESIGN', 'ATELIER_CRATERPARK_EDITOR_PARK', 'ATELIER_CRATERPARK_EDITOR_LINES'):
            patch.delenv(name, raising=False)
        recipe = build.load_recipe('yorimichi')
        root = tmp_path_factory.mktemp('layout-profile').resolve() / 'cold'
        context = declaration_context('yorimichi')
        context.out = root
        raw = next(s for s in recipe.world_steps(context) if s.name == 'world.layout')
        context = declaration_context('yorimichi')
        context.out = root
        steps = recipe.steps(context)
        build.check_declarations(steps)
        graph = build_products.Graph(steps)
        enriched = next(s for s in graph.select([raw.name]) if s.name == raw.name)
        owner = graph.by_name[graph.owners['treehouse.canopy_dimensions']]
        canopy = next(p for p in owner.products if p.name == 'treehouse.canopy_dimensions')
        assert tuple(canopy.paths) == (root / 'treehouse-data/canopy/trees.json',)
    assert not root.exists()
    return SimpleNamespace(root=root, raw=raw, enriched=enriched, recipe=recipe)


@pytest.fixture(params=('raw', 'enriched'))
def stage(request):
    return request.param


def fresh(declarations, stage='raw'):
    return deepcopy(getattr(declarations, stage))


def qualify(profile, step, root, checkout=paths.REPO):
    return profile.qualify_world_layout(step, checkout=checkout, output_root=root)


def rebound(step, root, checkout=None):
    old = step.outputs[0].parent
    def path(value):
        if value.is_relative_to(old):
            return root / value.relative_to(old)
        return checkout / value.relative_to(paths.REPO) if checkout is not None else value
    return replace(step, commands=[replace(step.commands[0], script=path(step.commands[0].script))],
                   inputs=[path(p) for p in step.inputs], outputs=[path(p) for p in step.outputs])


@pytest.mark.parametrize('field,value', [('cutoff', False), ('heavy', True), ('cache', True), ('audit', True),
    ('batch', build.Batch('other')), ('verify', lambda: True), ('replan', True), ('reads', ['other']),
    ('products', [build_products.Product('fake', (Path('/tmp/fake'),))]), ('cutoff', 1), ('heavy', 1)])
def test_exact_controls_refuse(profile, declarations, stage, field, value):
    with pytest.raises(profile.UnsupportedWorldLayout, match='Step controls'):
        qualify(profile, replace(fresh(declarations, stage), **{field: value}), declarations.root)


def test_private_metadata_refuses(profile, declarations, stage):
    step = fresh(declarations, stage)
    step.private_authority = True
    try:
        with pytest.raises(profile.UnsupportedWorldLayout, match='Step controls'):
            qualify(profile, step, declarations.root)
    finally:
        del step.private_authority


@pytest.mark.parametrize('change', ['partial', 'extra', 'order', 'duplicate', 'missing-raw'])
def test_only_two_exact_input_stages(profile, declarations, change):
    step = fresh(declarations, 'enriched')
    inputs = list(step.inputs)
    if change == 'partial':
        inputs.pop()
    elif change == 'extra':
        inputs.append(step.commands[0].script)
    elif change == 'order':
        inputs[-1], inputs[-2] = inputs[-2], inputs[-1]
    elif change == 'duplicate':
        inputs.insert(0, inputs[0])
    else:
        inputs.pop(3)
    with pytest.raises(profile.UnsupportedWorldLayout, match='input order'):
        qualify(profile, replace(step, inputs=inputs), declarations.root)


def test_actual_factory_full_graph_and_abi(profile, declarations, stage):
    step = fresh(declarations, stage)
    observed = qualify(profile, step, declarations.root)
    assert tuple(f.name for f in fields(observed)) == (
        'step', 'script', 'arguments', 'raw_inputs', 'produced_inputs', 'code_inputs', 'output_paths', 'products')
    assert observed.script == step.commands[0].script
    assert observed.arguments == () and observed.products == ()
    assert len(observed.raw_inputs) == 46 and len(observed.code_inputs) == 82
    scanner = build._FastImportScanner.__bases__[0]()
    world = paths.REPO / 'games/yorimichi/world'
    assert observed.code_inputs == tuple(scanner.local_imports(observed.script, (world, world / 'regions', paths.STUDIO)))
    assert observed.produced_inputs == (declarations.root / 'craterpark/v2/geometry.npz',
                                         declarations.root / 'treehouse-data/canopy/trees.json')
    factory = [*observed.raw_inputs, observed.produced_inputs[0]]
    assert step.inputs == (factory if stage == 'raw' else
        [*factory, *(p for p in observed.code_inputs if p not in factory
                    and p != paths.REPO / 'games/yorimichi/world/regions/megapark/plants.py')])
    assert observed.output_paths == tuple(step.outputs)
    from atelier.build_v2.controller_entry import declaration_context
    context = declaration_context('yorimichi')
    context.out = declarations.root
    later = next(s for s in declarations.recipe.world_steps(context) if s.name == step.name)
    assert later.inputs == factory  # fixture restoration must not select legacy mode
    assert not declarations.root.exists()
    with pytest.raises(FrozenInstanceError):
        observed.step = 'other'


def test_warm_produced_excluded_before_read(profile, declarations, stage, tmp_path, monkeypatch):
    root = tmp_path.resolve() / 'warm'
    files = {root / 'craterpark/v2/geometry.npz': b'finite generated fixture',
             root / 'treehouse-data/canopy/trees.json': b'finite canopy fixture',
             **{root / name: b'finite output fixture' for name in (
                 'world.json', 'heightmap.npy', 'heightmap.bin', 'farhills.npy',
                 'treehouse/layout.json', 'megapark/trail.json', 'map_preview.png')}}
    for p, data in files.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    before = {p: (p.read_bytes(), p.stat()) for p in files}
    reads = []
    reader = profile._read
    def observe(checkout, path):
        reads.append(path)
        assert not path.is_relative_to(root) and path.suffix not in ('.npz', '.bin')
        return reader(checkout, path)
    monkeypatch.setattr(profile, '_read', observe)
    qualify(profile, rebound(fresh(declarations, stage), root), root)
    assert reads
    assert all((p.read_bytes(), p.stat()) == value for p, value in before.items())


def finite_checkout(profile, step, tmp_path):
    import shutil
    observed = qualify(profile, step, step.outputs[0].parent)
    checkout = tmp_path.resolve() / 'checkout'
    files = [*observed.code_inputs, paths.REPO / 'games/yorimichi/build.py',
             *(p for p in observed.raw_inputs if p.suffix in ('.py', '.json'))]
    for source in dict.fromkeys(files):
        dest = checkout / source.relative_to(paths.REPO)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
    for source in observed.raw_inputs:
        dest = checkout / source.relative_to(paths.REPO)
        if source.suffix == '.bin':
            dest.write_bytes(b'finite raw terrain fixture')
        elif source.name == 'geometry':
            dest.mkdir(parents=True)
    root = tmp_path.resolve() / 'output'
    return checkout, rebound(step, root, checkout), root


@pytest.mark.parametrize('relative', [
    '', 'games', 'games/yorimichi', 'games/yorimichi/world', 'platform', 'platform/studio',
    'games/yorimichi/world/gen_world.py',
    'games/yorimichi/tools/craterpark_editor/shipped.json',
    'games/yorimichi/tools/craterpark_editor/data/outer.bin',
    'games/yorimichi/assets/vehicles/belmonte-train/line.json',
    'games/yorimichi/world/regions/craterpark/v2/curves.py',
    'games/yorimichi/tools/craterpark_editor/data',
    'games/yorimichi/assets/craterpark/geometry'])
def test_rebound_alias_checks_reached(profile, declarations, tmp_path, monkeypatch, relative):
    checkout, step, root = finite_checkout(profile, fresh(declarations), tmp_path)
    qualify(profile, step, root, checkout)
    target = checkout / relative
    foreign = tmp_path.resolve() / 'foreign'
    target.rename(foreign)
    target.symlink_to(foreign, target_is_directory=foreign.is_dir())
    reached = []
    checker = profile._role
    def observe(anchor, path, **kwargs):
        reached.append(path)
        return checker(anchor, path, **kwargs)
    monkeypatch.setattr(profile, '_role', observe)
    with pytest.raises(profile.UnsupportedWorldLayout, match='input role'):
        qualify(profile, step, root, checkout)
    assert any(p == target or target in p.parents for p in reached)
    assert not root.exists()


@pytest.mark.parametrize('relative', ['', 'world.json', 'heightmap.npy', 'heightmap.bin', 'farhills.npy',
    'treehouse', 'treehouse/layout.json', 'megapark/trail.json', 'map_preview.png',
    'craterpark/v2', 'craterpark/v2/geometry.npz', 'treehouse-data/canopy/trees.json'])
def test_output_aliases_reached(profile, declarations, tmp_path, relative):
    root = tmp_path.resolve() / 'output'
    foreign = tmp_path.resolve() / 'foreign'
    foreign.mkdir()
    marker = foreign / 'marker'
    marker.write_bytes(b'untouched')
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to(marker if target.suffix else foreign, target_is_directory=not target.suffix)
    before = marker.read_bytes(), marker.stat()
    with pytest.raises(profile.UnsupportedWorldLayout, match='output'):
        qualify(profile, rebound(fresh(declarations), root), root)
    assert (marker.read_bytes(), marker.stat()) == before


@pytest.mark.parametrize('kind', ['missing', 'changed', 'extra-import', 'enrichment', 'factory', 'raw-role'])
def test_source_structure_and_closure_refuse(profile, declarations, tmp_path, kind):
    checkout, step, root = finite_checkout(profile, fresh(declarations), tmp_path)
    source = checkout / ('games/yorimichi/build.py' if kind in ('factory', 'enrichment', 'raw-role')
                         else 'games/yorimichi/world/regions/craterpark/v2/curves.py')
    original = source.read_text()
    if kind == 'missing':
        source.unlink()
    elif kind == 'changed':
        source.write_text(original + '\nCHANGED = True\n')
    elif kind == 'extra-import':
        source.write_text(original + '\nfrom craterpark.v2 import unknown_helper\n')
        source.with_name('unknown_helper.py').write_text('raise AssertionError("never execute")\n')
    else:
        before, after = {'factory': ('cutoff=True', 'cutoff=False'),
            'enrichment': ('if f not in step.inputs', 'if f in step.inputs'),
            'raw-role': ("ASSETS / 'craterpark' / 'scene.json'", "ASSETS / 'craterpark' / 'other.json'")}[kind]
        assert before in original
        source.write_text(original.replace(before, after))
    with pytest.raises(profile.UnsupportedWorldLayout):
        qualify(profile, step, root, checkout)


@pytest.mark.parametrize('change', ['args', 'script', 'commands', 'needs', 'outputs', 'unknown'])
def test_exact_command_roles_refuse(profile, declarations, change):
    step = fresh(declarations)
    if change in ('args', 'script'):
        step.commands = [replace(step.commands[0], **({'args': ('--other',)} if change == 'args'
                        else {'script': step.commands[0].script.with_name('other.py')}))]
    elif change == 'commands':
        step.commands.append(build.Call('foreign', lambda: None))
    elif change == 'needs':
        step.needs = []
    elif change == 'outputs':
        step.outputs.append(step.outputs[0].with_name('other.json'))
    else:
        step.unknown = True
    with pytest.raises(profile.UnsupportedWorldLayout):
        qualify(profile, step, declarations.root)


def test_no_producer_selector_provenance_or_probe(profile, declarations, stage, monkeypatch):
    import shutil
    import subprocess
    import sys
    calls = []
    def forbidden(*args, **kwargs):
        calls.append('forbidden')
        raise AssertionError('executed a provider or probe')
    for name in ('editor_path', 'input_paths', 'editor_lines', 'selected', 'provenance', 'load_document'):
        monkeypatch.setattr(declarations.recipe.craterpark_v4, name, forbidden)
    monkeypatch.setattr(shutil, 'which', forbidden)
    monkeypatch.setattr(subprocess, 'run', forbidden)
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    import numpy as np
    from PIL import Image
    monkeypatch.setattr(np, 'save', forbidden)
    monkeypatch.setattr(Image, 'fromarray', forbidden)
    def trace(frame, event, arg):
        if event == 'call' and '/games/yorimichi/world/' in frame.f_code.co_filename:
            calls.append(frame.f_code.co_name)
        return trace
    previous = sys.gettrace()
    sys.settrace(trace)
    try:
        qualify(profile, fresh(declarations, stage), declarations.root)
    finally:
        sys.settrace(previous)
    assert calls == []


@pytest.mark.parametrize('name,value', [
    ('ATELIER_CRATERPARK_EDITOR_PARK', 'off'),
    ('ATELIER_CRATERPARK_EDITOR_PARK', '/foreign/park.json'),
    ('ATELIER_CRATERPARK_V4_DESIGN', '/foreign/design.json'),
    ('ATELIER_CRATERPARK_EDITOR_LINES', 'L1')])
def test_current_default_context_required(profile, declarations, monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(profile.UnsupportedWorldLayout, match='context'):
        qualify(profile, fresh(declarations), declarations.root)


@pytest.mark.parametrize('field,value', [
    ('deferred_inputs', [Path('other')]), ('after', ['other']), ('pool_roots', [Path('other')]),
    ('explicit', True), ('references', ['other']), ('optional_inputs', [Path('other')]),
    ('queries', ['other']), ('toolchain', True), ('cook_recovery', 'other'),
    ('checkpoint_previous_needs', []), ('checkpoint_restore', lambda: None),
    ('checkpoint_outputs', (Path('other'),)), ('candidate_scope', 'other'),
    ('controller', 'other'), ('about', 'changed'), ('name', 'world.other'),
    ('inputs', ()), ('outputs', ())])
def test_remaining_exact_fields(profile, declarations, field, value):
    with pytest.raises(profile.UnsupportedWorldLayout):
        qualify(profile, replace(fresh(declarations), **{field: value}), declarations.root)


def test_raw_metadata_is_data_not_pinned_code(profile, declarations, tmp_path):
    import json
    checkout, step, root = finite_checkout(profile, fresh(declarations), tmp_path)
    original = qualify(profile, step, root, checkout)
    for p in original.raw_inputs:
        if p.name in ('shipped.json', 'terrain.json', 'scene.json'):
            value = json.loads(p.read_bytes())
            value['observation_test_note'] = 'raw data changes remain data identity'
            p.write_text(json.dumps(value))
    assert qualify(profile, step, root, checkout) == original
    assert not root.exists()


@pytest.mark.parametrize('kind', ['step-subclass', 'command-subclass', 'missing-name', 'missing-command-field'])
def test_malformed_exact_types(profile, declarations, kind):
    step = fresh(declarations)
    if kind == 'step-subclass':
        class Foreign(type(step)):
            pass
        step = Foreign(**vars(step))
    elif kind == 'command-subclass':
        class Foreign(type(step.commands[0])):
            pass
        step.commands = [Foreign(**vars(step.commands[0]))]
    elif kind == 'missing-name':
        del step.name
    else:
        object.__delattr__(step.commands[0], 'script')
    with pytest.raises(profile.UnsupportedWorldLayout):
        qualify(profile, step, declarations.root)


@pytest.mark.parametrize('index', range(7))
def test_all_seven_output_members_required(profile, declarations, index):
    step = fresh(declarations)
    step.outputs.pop(index)
    with pytest.raises(profile.UnsupportedWorldLayout, match='output roles'):
        qualify(profile, step, declarations.root)


@pytest.mark.parametrize('change', ['missing-npz', 'extra-trees', 'needs-order', 'reads-missing', 'reads-extra'])
def test_produced_and_named_read_declarations_exact(profile, declarations, change):
    step = fresh(declarations)
    if change == 'missing-npz':
        step.inputs.pop()
    elif change == 'extra-trees':
        step.inputs.append(declarations.root / 'treehouse-data/canopy/trees.json')
    elif change == 'needs-order':
        step.needs.reverse()
    elif change == 'reads-missing':
        step.reads = []
    else:
        step.reads.append('other')
    with pytest.raises(profile.UnsupportedWorldLayout):
        qualify(profile, step, declarations.root)


def test_unknown_import_candidate_refuses_before_content(profile, declarations, tmp_path, monkeypatch):
    checkout, step, root = finite_checkout(profile, fresh(declarations), tmp_path)
    extra = checkout / 'games/yorimichi/world/numpy.py'
    extra.write_text('raise AssertionError("unknown module must never execute")\n')
    reader = profile._read
    def read(anchor, source):
        assert source != extra
        return reader(anchor, source)
    monkeypatch.setattr(profile, '_read', read)
    with pytest.raises(profile.UnsupportedWorldLayout, match='unknown source import target'):
        qualify(profile, step, root, checkout)
    assert not root.exists()


def test_full_returned_closure_checked(profile, declarations, monkeypatch):
    original = qualify(profile, fresh(declarations), declarations.root)
    scanner = build._FastImportScanner.__bases__[0]
    monkeypatch.setattr(scanner, 'local_imports', lambda self, *args: list(original.code_inputs[:-1]))
    with pytest.raises(profile.UnsupportedWorldLayout, match='sorted source closure differs'):
        qualify(profile, fresh(declarations), declarations.root)


def test_enriched_extra_plants_role_refuses(profile, declarations):
    step = fresh(declarations, 'enriched')
    step.inputs.append(paths.REPO / 'games/yorimichi/world/regions/megapark/plants.py')
    with pytest.raises(profile.UnsupportedWorldLayout, match='input order'):
        qualify(profile, step, declarations.root)


@pytest.mark.parametrize('relative,before,after', [
    ('games/yorimichi/build.py', 'if f.resolve() not in drop', 'if f.resolve() in drop'),
    ('games/yorimichi/build.py', "ASSETS / 'vehicles' / 'belmonte-train' / 'line.json'", "ASSETS / 'vehicles' / 'belmonte-train' / 'other.json'"),
    ('games/yorimichi/world/gen_world.py', '"map_preview.png"', '"other-preview.png"'),
    ('games/yorimichi/world/regions/craterpark/v2/v4_placement.py', "'geometry.npz'", "'other.npz'")])
def test_relevant_source_role_counter_mutations(profile, declarations, tmp_path, relative, before, after):
    checkout, step, root = finite_checkout(profile, fresh(declarations), tmp_path)
    source = checkout / relative
    original = source.read_text()
    assert before in original
    source.write_text(original.replace(before, after))
    with pytest.raises(profile.UnsupportedWorldLayout, match='source structure differs'):
        qualify(profile, step, root, checkout)
