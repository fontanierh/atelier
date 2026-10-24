"""Original CraterPark factory/Graph metadata only; never run editor or native tools."""
from copy import deepcopy
from dataclasses import FrozenInstanceError, fields, replace
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier import build, build_inputs, build_products, paths


@pytest.fixture(scope='module')
def profile():
    source = paths.REPO / 'games/yorimichi/legacy_craterpark_geometry_profile.py'
    spec = importlib.util.spec_from_file_location('craterpark_geometry_profile_test', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def declarations(tmp_path_factory):
    from atelier.build_v2.controller_entry import declaration_context
    with pytest.MonkeyPatch.context() as patch:
        for name in ('ATELIER_CRATERPARK_V4_DESIGN', 'ATELIER_CRATERPARK_EDITOR_PARK', 'ATELIER_CRATERPARK_EDITOR_LINES'):
            patch.delenv(name, raising=False)
        recipe = build.load_recipe('yorimichi')
        root = tmp_path_factory.mktemp('craterpark-profile') / 'cold'
        raw = recipe.craterpark_v2_steps(root)[0]
        build_products.Graph([raw])
        context = declaration_context('yorimichi')
        context.out = root
        steps = recipe.steps(context)
        build.check_declarations(steps)
        graph = build_products.Graph(steps)
        enriched = next(step for step in graph.select(['world.craterpark_geometry'])
                        if step.name == 'world.craterpark_geometry')
    assert not root.exists()
    return SimpleNamespace(root=root, raw=raw, enriched=enriched, recipe=recipe, steps=steps)


@pytest.fixture(params=('raw', 'enriched'))
def stage(request):
    return request.param


def fresh(declarations, stage='raw'):
    return deepcopy(getattr(declarations, stage))


def qualify(profile, step, root, checkout=paths.REPO):
    return profile.qualify_craterpark_geometry(step, checkout=checkout, output_root=root)


def rebound(step, root, checkout=None):
    old = step.outputs[0].parents[2]
    def path(value):
        value = Path(value)
        if value.is_relative_to(old):
            return root / value.relative_to(old)
        return checkout / value.relative_to(paths.REPO) if checkout is not None else value
    command = step.commands[0]
    return replace(step, commands=[replace(command, script=path(command.script), args=(command.args[0], str(path(command.args[1]))))],
                   inputs=[path(value) for value in step.inputs], outputs=[path(value) for value in step.outputs])


def test_actual_factory_and_full_graph_roles(profile, declarations, stage):
    step = fresh(declarations, stage)
    observed = qualify(profile, step, declarations.root)
    game = paths.REPO / 'games/yorimichi'
    world = game / 'world'
    regions = world / 'regions'
    v2 = regions / 'craterpark/v2'
    data = game / 'tools/craterpark_editor/data'
    assert observed.raw_inputs == (v2, regions / 'craterpark/__init__.py', regions / 'craterpark/placement.py',
        game / 'assets/craterpark', regions / 'megapark/placement.py', world / 'yori.py',
        regions / 'hidamari/__init__.py', regions / 'hidamari/natural_terrain.py',
        game / 'tools/craterpark_editor/shipped.json', data / 'terrain.json',
        data / 'inner_natural.bin', data / 'inner_dug.bin', data / 'outer.bin')
    assert observed.script == step.commands[0].script == v2 / 'editor_generate.py'
    assert observed.arguments == step.commands[0].args
    assert observed.produced_inputs == ()
    assert observed.output_paths == tuple(step.outputs)
    assert step.products == [] and step.cutoff is True and step.cache is False and step.heavy is True
    assert observed.code_inputs == tuple(build_inputs.local_imports(observed.script, (world, regions, paths.STUDIO)))
    assert len(observed.code_inputs) == 43
    assert observed.tool_sources == tuple(v2 / 'editor' / name for name in ('bridge.cjs', 'pieces.cjs', 'terrain.cjs', 'pin.json'))
    expected = list(observed.raw_inputs)
    if stage == 'enriched':
        expected.extend(source for source in observed.code_inputs if source not in observed.raw_inputs)
    assert step.inputs == expected
    assert not declarations.root.exists()
    with pytest.raises(FrozenInstanceError):
        observed.step = 'other'


def test_exact_abi(profile):
    assert tuple(field.name for field in fields(profile.CraterparkGeometry)) == (
        'step', 'script', 'arguments', 'raw_inputs', 'produced_inputs', 'code_inputs', 'output_paths', 'tool_sources')


def test_warm_output_bytes_preserved(profile, declarations, stage, tmp_path, monkeypatch):
    root = tmp_path / 'warm'
    files = {root / 'craterpark/v2/geometry.npz': b'foreign geometry',
             root / 'craterpark/v2/geometry-report.json': b'foreign report',
             root / 'craterpark/v2/lines/L1.npz': b'foreign line'}
    for file, content in files.items():
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(content)
    before = {file: (file.read_bytes(), file.lstat()) for file in files}
    reader = profile._read
    def sources_only(checkout, path):
        assert not path.is_relative_to(root)
        assert path.suffix not in ('.npz', '.bin')
        return reader(checkout, path)
    monkeypatch.setattr(profile, '_read', sources_only)
    qualify(profile, rebound(fresh(declarations, stage), root), root)
    assert all((file.read_bytes(), file.lstat()) == value for file, value in before.items())


@pytest.mark.parametrize('change', ['v4', 'legacy', 'document', 'extra', 'order', 'environment', 'alias'])
def test_wrong_command_refuses(profile, declarations, stage, change):
    step = fresh(declarations, stage)
    command = step.commands[0]
    if change in ('v4', 'legacy'):
        command = replace(command, script=command.script.with_name('v4_generate.py' if change == 'v4' else 'generate.py'))
    elif change == 'document':
        command = replace(command, args=('--park', str(Path(command.args[1]).with_name('park.json'))))
    elif change == 'extra':
        command = replace(command, args=(*command.args, '--lines', 'L1'))
    elif change == 'order':
        command = replace(command, args=tuple(reversed(command.args)))
    elif change == 'environment':
        object.__setattr__(command, 'env', (('PATH', 'other'),))
    else:
        class Alias(type(command)):
            pass
        command = Alias(**vars(command))
    try:
        with pytest.raises(profile.UnsupportedCraterparkGeometry, match='command|document'):
            qualify(profile, replace(step, commands=[command]), declarations.root)
    finally:
        if change == 'environment':
            object.__delattr__(command, 'env')


@pytest.mark.parametrize('field,value', [('cutoff', False), ('heavy', False), ('cache', True), ('audit', True),
    ('batch', build.Batch('other')), ('verify', lambda: True), ('replan', True), ('reads', ['other']),
    ('products', [build_products.Product('fake', (Path('/tmp/fake'),))]), ('cutoff', 1), ('heavy', 1)])
def test_exact_controls_refuse(profile, declarations, stage, field, value):
    with pytest.raises(profile.UnsupportedCraterparkGeometry, match='Step controls'):
        qualify(profile, replace(fresh(declarations, stage), **{field: value}), declarations.root)


def test_private_metadata_refuses(profile, declarations, stage):
    step = fresh(declarations, stage)
    step.private_authority = True
    try:
        with pytest.raises(profile.UnsupportedCraterparkGeometry, match='Step controls'):
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
    with pytest.raises(profile.UnsupportedCraterparkGeometry, match='input order'):
        qualify(profile, replace(step, inputs=inputs), declarations.root)


def finite_checkout(profile, step, tmp_path):
    """Exact finite source/tool/JSON copies; tiny layer sentinels are role fixtures only."""
    import shutil
    checkout = tmp_path / 'checkout'
    original = qualify(profile, step, Path(step.outputs[0]).parents[2])
    files = [*original.code_inputs, *original.tool_sources, paths.REPO / 'games/yorimichi/build.py',
             *(path for path in original.raw_inputs if path.suffix in ('.py', '.json'))]
    for source in dict.fromkeys(files):
        destination = checkout / source.relative_to(paths.REPO)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    for path in original.raw_inputs:
        destination = checkout / path.relative_to(paths.REPO)
        if path.suffix == '.bin':
            destination.write_bytes(b'raw layer role sentinel, not terrain geometry')
        elif path.suffix == '':
            destination.mkdir(parents=True, exist_ok=True)
    return checkout, rebound(step, tmp_path / 'output', checkout), tmp_path / 'output'


def test_finite_source_fixture_and_raw_json_identity(profile, declarations, tmp_path):
    import json
    checkout, step, root = finite_checkout(profile, fresh(declarations), tmp_path)
    observed = qualify(profile, step, root, checkout)
    park, terrain = observed.raw_inputs[8:10]
    original = {path: path.read_bytes() for path in (park, terrain)}
    try:
        for path in (park, terrain):
            value = json.loads(original[path])
            value['note'] = 'raw metadata edit remains data identity'
            path.write_text(json.dumps(value))
        assert qualify(profile, step, root, checkout) == observed
    finally:
        for path, content in original.items():
            path.write_bytes(content)
    assert not root.exists()


@pytest.mark.parametrize('relative', [
    'games/yorimichi/build.py',
    'games/yorimichi/world/regions/craterpark/v2/editor_generate.py',
    'games/yorimichi/world/regions/craterpark/v2/curves.py',
    'games/yorimichi/world/regions/craterpark/v2/editor/frontend.py',
    *(f'games/yorimichi/world/regions/craterpark/v2/editor/{name}' for name in
      ('bridge.cjs', 'pieces.cjs', 'terrain.cjs', 'pin.json')),
    'games/yorimichi/tools/craterpark_editor/shipped.json',
    'games/yorimichi/tools/craterpark_editor/data/terrain.json'])
def test_source_tool_json_links_reach_nofollow_check(profile, declarations, tmp_path, monkeypatch, relative):
    checkout, step, root = finite_checkout(profile, fresh(declarations), tmp_path)
    source = checkout / relative
    content = source.read_bytes()
    foreign = tmp_path / 'foreign'
    foreign.write_bytes(content)
    source.unlink()
    source.symlink_to(foreign)
    reached = []
    reader = profile._read
    def observe(anchor, path):
        reached.append(path)
        return reader(anchor, path)
    monkeypatch.setattr(profile, '_read', observe)
    try:
        with pytest.raises(profile.UnsupportedCraterparkGeometry):
            qualify(profile, step, root, checkout)
        assert source in reached
    finally:
        source.unlink()
        source.write_bytes(content)
    assert foreign.read_bytes() == content


@pytest.mark.parametrize('kind', ['checkout', 'v2', 'assets', 'raw-layer', 'raw-parent'])
def test_input_parent_and_final_aliases_reach_role_checks(profile, declarations, tmp_path, monkeypatch, kind):
    checkout, step, root = finite_checkout(profile, fresh(declarations), tmp_path)
    targets = {'checkout': checkout, 'v2': checkout / 'games/yorimichi/world/regions/craterpark/v2',
        'assets': checkout / 'games/yorimichi/assets/craterpark',
        'raw-layer': checkout / 'games/yorimichi/tools/craterpark_editor/data/outer.bin',
        'raw-parent': checkout / 'games/yorimichi/tools/craterpark_editor/data'}
    target = targets[kind]
    foreign = tmp_path / 'foreign'
    target.rename(foreign)
    target.symlink_to(foreign, target_is_directory=kind != 'raw-layer')
    reached = []
    checker = profile._role
    def observe(anchor, path, **kwargs):
        reached.append(path)
        return checker(anchor, path, **kwargs)
    monkeypatch.setattr(profile, '_role', observe)
    try:
        with pytest.raises(profile.UnsupportedCraterparkGeometry, match='input role'):
            qualify(profile, step, root, checkout)
        assert target in reached
    finally:
        target.unlink()
        foreign.rename(target)
    assert not root.exists()


@pytest.mark.parametrize('kind', ['root', 'parent', 'geometry', 'report', 'lines'])
def test_output_aliases_never_change_foreign_bytes(profile, declarations, stage, tmp_path, kind):
    root = tmp_path / 'output'
    targets = {'root': root, 'parent': root / 'craterpark/v2',
               'geometry': root / 'craterpark/v2/geometry.npz',
               'report': root / 'craterpark/v2/geometry-report.json', 'lines': root / 'craterpark/v2/lines'}
    foreign = tmp_path / 'foreign'
    foreign.mkdir()
    marker = foreign / 'marker'
    marker.write_bytes(b'preserve foreign output')
    target = targets[kind]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to(marker if kind in ('geometry', 'report') else foreign,
                      target_is_directory=kind not in ('geometry', 'report'))
    before = marker.read_bytes(), marker.lstat()
    try:
        with pytest.raises(profile.UnsupportedCraterparkGeometry, match='output'):
            qualify(profile, rebound(fresh(declarations, stage), root), root)
    finally:
        target.unlink()
    assert (marker.read_bytes(), marker.lstat()) == before


@pytest.mark.parametrize('relative,before,after', [
    ('games/yorimichi/build.py', "runner, arguments = 'editor_generate.py'", "runner, arguments = 'other.py'"),
    ('games/yorimichi/build.py', 'if f not in step.inputs', 'if f in step.inputs'),
    ('games/yorimichi/world/regions/craterpark/v2/editor/frontend.py', '--max-old-space-size=1024', '--max-old-space-size=2048'),
    ('games/yorimichi/world/regions/craterpark/v2/editor_generate.py', "parser.add_argument('--park', required=True", "parser.add_argument('--park', required=False"),
    ('games/yorimichi/world/regions/craterpark/v2/v4_config.py', "SHIPPED_LINES = 'L1,L2,p5'", "SHIPPED_LINES = 'L1'")])
def test_constructor_enrichment_frontend_structure_is_bound(profile, declarations, tmp_path, relative, before, after):
    checkout, step, root = finite_checkout(profile, fresh(declarations), tmp_path)
    source = checkout / relative
    original = source.read_bytes()
    assert before.encode() in original
    source.write_bytes(original.replace(before.encode(), after.encode()))
    try:
        with pytest.raises(profile.UnsupportedCraterparkGeometry, match='structure differs'):
            qualify(profile, step, root, checkout)
    finally:
        source.write_bytes(original)


@pytest.mark.parametrize('kind', ['missing-code', 'missing-tool', 'changed-tool', 'unknown-import'])
def test_finite_source_and_tool_membership_refuses(profile, declarations, tmp_path, kind):
    checkout, step, root = finite_checkout(profile, fresh(declarations), tmp_path)
    v2 = checkout / 'games/yorimichi/world/regions/craterpark/v2'
    source = v2 / ('curves.py' if kind in ('missing-code', 'unknown-import') else 'editor/bridge.cjs')
    original = source.read_bytes()
    extra = v2 / 'unknown_helper.py'
    if kind in ('missing-code', 'missing-tool'):
        source.unlink()
    elif kind == 'changed-tool':
        source.write_bytes(original + b'\nrequire("unknown-tool");\n')
    else:
        source.write_bytes(original + b'\nfrom craterpark.v2 import unknown_helper\n')
        extra.write_bytes(b'raise AssertionError("helper body must not execute")\n')
    try:
        with pytest.raises(profile.UnsupportedCraterparkGeometry, match={
            'missing-code': 'source/data file', 'missing-tool': 'source/data file',
            'changed-tool': 'tool sources differ', 'unknown-import': 'unknown source import target'}[kind]):
            qualify(profile, step, root, checkout)
    finally:
        source.write_bytes(original)
        extra.unlink(missing_ok=True)


def test_no_producer_selector_frontend_or_node_probe_execution(profile, declarations, stage, monkeypatch):
    import shutil
    import subprocess
    import sys
    calls = []
    def forbidden(*args, **kwargs):
        calls.append('probe/provider')
        raise AssertionError('qualification executed a provider or process probe')
    for name in ('editor_path', 'input_paths', 'editor_lines'):
        monkeypatch.setattr(declarations.recipe.craterpark_v4, name, forbidden)
    monkeypatch.setattr(shutil, 'which', forbidden)
    monkeypatch.setattr(subprocess, 'run', forbidden)
    traced = []
    def trace(frame, event, arg):
        if event == 'call' and '/regions/craterpark/' in frame.f_code.co_filename:
            traced.append(frame.f_code.co_name)
        return trace
    previous = sys.gettrace()
    sys.settrace(trace)
    try:
        qualify(profile, fresh(declarations, stage), declarations.root)
    finally:
        sys.settrace(previous)
    assert calls == traced == []


def test_actual_layout_declares_generated_geometry_and_tracks_its_bytes(declarations, tmp_path, monkeypatch):
    for name in ('ATELIER_CRATERPARK_V4_DESIGN', 'ATELIER_CRATERPARK_EDITOR_PARK', 'ATELIER_CRATERPARK_EDITOR_LINES'):
        monkeypatch.delenv(name, raising=False)
    steps = declarations.recipe.craterpark_v2_steps(tmp_path)
    layout = next(step for step in steps if step.name == 'world.craterpark_layout')
    geometry = tmp_path / 'craterpark/v2/geometry.npz'
    assert layout.needs == ['world.craterpark_geometry']
    assert layout.inputs.count(geometry) == 1
    assert layout.outputs == [tmp_path / 'craterpark/layout-identity.json']
    graph = build_products.Graph(steps)
    assert [step.name for step in graph.select([layout.name])] == ['world.craterpark_geometry', layout.name]
    # Finite bytes exercise the ORIGINAL fingerprint, not geometry validity or
    # a completion/authority certificate. No native producer runs in this test.
    geometry.parent.mkdir(parents=True)
    geometry.write_bytes(b'first generated geometry fixture')
    before = build.fingerprint(layout, {'world.craterpark_geometry': 'producer-identity'})
    geometry.write_bytes(b'changed generated geometry fixture')
    assert build.fingerprint(layout, {'world.craterpark_geometry': 'producer-identity'}) != before


def test_actual_world_layout_declares_selected_raw_generated_reads_and_preview(declarations, tmp_path, monkeypatch):
    for name in ('ATELIER_CRATERPARK_V4_DESIGN', 'ATELIER_CRATERPARK_EDITOR_PARK', 'ATELIER_CRATERPARK_EDITOR_LINES'):
        monkeypatch.delenv(name, raising=False)
    world = next(step for step in declarations.steps if step.name == 'world.layout')
    geometry = declarations.root / 'craterpark/v2/geometry.npz'
    assert world.inputs.count(geometry) == 1
    for path in declarations.recipe.craterpark_v4.input_paths():
        assert world.inputs.count(path) == 1
    assert world.reads == ['treehouse.canopy_dimensions']
    assert 'world.craterpark_layout' in world.needs and 'world.craterpark_geometry' in world.needs
    preview = declarations.root / 'map_preview.png'
    assert world.outputs[-1] == preview and world.outputs.count(preview) == 1
    # Cross the ACTUAL producer's unconditional save with the ACTUAL declaration.
    import ast
    tree = ast.parse((paths.REPO / 'games/yorimichi/world/gen_world.py').read_bytes())
    writes = [call for call in ast.walk(tree) if isinstance(call, ast.Call)
              and isinstance(call.func, ast.Attribute) and call.func.attr == 'save'
              and call.args and any(isinstance(node, ast.Constant) and node.value == 'map_preview.png'
                                    for node in ast.walk(call.args[0]))]
    assert len(writes) == 1
    # Existing required-output policy refuses six former representative outputs
    # without the mandatory preview. These bytes assert presence only, not validity.
    mapped = [tmp_path / path.relative_to(declarations.root) for path in world.outputs]
    observed = replace(world, outputs=mapped)
    for path in mapped[:-1]:
        path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'presence-only fixture')
    assert not build.outputs_present(observed)
    mapped[-1].write_bytes(b'presence-only preview fixture')
    assert build.outputs_present(observed)
