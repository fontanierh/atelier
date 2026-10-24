"""Finite provider capture; real fresh-process Graph proof lives in the Rust T1a case."""
from pathlib import Path
import ast
from contextlib import contextmanager
import importlib.util
import signal
import json
from types import SimpleNamespace
import pytest


@pytest.fixture
def finite_recipe_steps(monkeypatch):
    """Execute only the actual steps AST with finite constructors, never a recipe import/job."""
    from atelier import paths
    from atelier.build_v2 import legacy_qualification as phases
    source = paths.REPO / 'games/yorimichi/build.py'
    node = next(n for n in ast.parse(source.read_bytes()).body
                if isinstance(n, ast.FunctionDef) and n.name == 'steps')

    def prepare(fail=None):
        trace, stack, snapshots = [], [], {}
        original = RuntimeError('original-constructor-sentinel')
        ctx = SimpleNamespace(out=Path('/virtual/out'), uproject=Path('/virtual/game.uproject'))
        @contextmanager
        def phase(label):
            assert label in phases._DIAGNOSTIC_PHASES
            trace.append(('begin', label))
            stack.append(label)
            try:
                yield
            except BaseException:
                trace.append(('raised', label))
                raise
            else:
                trace.append(('returned', label))
            finally:
                assert stack.pop() == label
        monkeypatch.setattr(phases, 'diagnostic_phase', phase)
        class Name(str):
            def startswith(self, prefix):
                trace.append(('filter', str(self), prefix, stack[-1]))
                return super().startswith(prefix)
        class Sequence(list):
            def __add__(self, other):
                trace.append(('add', tuple(str(s.name) for s in self), tuple(str(s.name) for s in other)))
                return Sequence(list.__add__(self, other))
        def step(name, commands=(), **kwargs):
            fields = dict(name=Name(name), commands=list(commands), inputs=[], outputs=[],
                          reads=[], needs=[], after=[], explicit=False, candidate_scope=None)
            fields.update(kwargs)
            return SimpleNamespace(**fields)
        world, regions, game, assets = map(Path, ('/virtual/world', '/virtual/world/regions',
                                                  '/virtual/game', '/virtual/assets'))
        studio, scripts, treehouse = map(Path, ('/virtual/platform/studio', '/virtual/scripts',
                                                '/virtual/world/regions/treehouse'))
        class Python:
            def __init__(self, script):
                self.script = script
        class Blender(Python):
            pass
        # Keep the fake Unreal descriptor distinct from Python, as in the real recipe.
        class UnrealScript:
            def __init__(self, script):
                self.script = script
        fbx = studio / 'atelier/blender/fbx.py'
        imported = world / 'helper.py'
        class Scanner:
            def __init__(self):
                trace.append(('scanner',))
            def local_imports(self, *args):
                trace.append(('scan', str(args[0])))
                return [fbx]
        values = {
            'ferry': [step('ferry.data'), step('unreal.ferry')],
            'gondola': [step('gondola.data'), step('unreal.gondola')],
            'world': [step('world.entry', [Blender(world / 'shape.py'), UnrealScript(scripts / 'native.py')],
                           needs=['unreal.world'], inputs=[world / 'shorelines.py', treehouse / 'layout.py'])],
            'character': [step('character.entry')], 'sound': [step('sound.entry')],
            'unreal': [step('unreal.entry')], 'staging': [step('data.stage')],
            'adventure': [step('adventure.entry')], 'hippodrome': [step('hippodrome.entry')],
            'belmonte': [step('belmonte.skip0'), step('belmonte.skip1'), step('belmonte.skip2'), step('belmonte.keep')],
            'brinecove': [step('brinecove.skip0'), step('brinecove.skip1'), step('brinecove.keep')],
            'fit': [step('fit.entry')], 'pawn': [step('pawn.entry')],
            'cook': [step('cook')], 'package': [step('package')],
        }
        def constructor(name):
            def call(*args):
                trace.append(('call', name))
                if name in ('adventure', 'belmonte', 'brinecove'):
                    assert args == (ctx.out,)
                elif name == 'fit':
                    assert len(args) == 2 and args[0] is ctx.out
                elif name == 'pawn':
                    assert len(args) == 1
                elif name in ('cook', 'package'):
                    assert len(args) == 2 and args[0] is ctx
                else:
                    assert args == (ctx,)
                if fail == name:
                    raise original
                if name in ('fit', 'pawn', 'cook', 'package'):
                    snapshots[name] = (args[-1], tuple(str(s.name) for s in args[-1]))
                return values[name][0] if name in ('cook', 'package') else Sequence(values[name])
            return call
        def helper(name, path):
            trace.append(('helper', name))
            if name == 'yorimichi_network_identity':
                assert path == game / 'network_identity.py'
                return SimpleNamespace(stage=object(), content_files=object())
            assert name == 'yorimichi_content_policy' and path == game / 'content_policy.py'
            return SimpleNamespace(archive=object(), retired=object(), music_enabled=lambda: False)
        def own(result):
            trace.append(('ownership', tuple(str(s.name) for s in result)))
        namespace = dict(Path=Path, SimpleNamespace=SimpleNamespace, Step=step,
                         Call=lambda *args: args, DeferredInputs=lambda *args, **kwargs: (args, kwargs),
                         WORLD=world, REGIONS=regions, GAME=game, ASSETS=assets, SCRIPTS=scripts,
                         TREEHOUSE=treehouse, paths=SimpleNamespace(STUDIO=studio),
                         build_inputs=SimpleNamespace(ImportScanner=Scanner), Python=Python,
                         Blender=Blender, UnrealScript=UnrealScript, CandidateScope=lambda **kwargs: kwargs,
                         craterpark_v4=SimpleNamespace(selected=lambda: False),
                         local_imports=lambda *args: [imported], _mentions_import_village=lambda path: False,
                         _load_helper_module=helper, declare_owned_content=own,
                         music_selector_members=object(), os=SimpleNamespace(environ={}),
                         native_source_inputs=lambda: object())
        for name, function in (('ferry', 'ferry_steps'), ('gondola', 'gondola_steps'),
                               ('world', 'world_steps'), ('character', 'character_steps'),
                               ('sound', 'sound_effect_steps'), ('unreal', 'unreal_steps'),
                               ('staging', 'staging_steps'), ('adventure', 'adventure_steps'),
                               ('hippodrome', 'hippodrome_steps'), ('belmonte', 'belmonte_steps'),
                               ('brinecove', 'brinecove_steps'), ('fit', 'fit_steps'),
                               ('pawn', 'pawn_steps'), ('cook', 'cook_step'), ('package', 'package_step')):
            namespace[function] = constructor(name)
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), 'exec'), namespace)
        return SimpleNamespace(run=namespace['steps'], trace=trace, snapshots=snapshots, values=values,
                               original=original, ctx=ctx,
                               expected_inputs=[world / 'shorelines.py', treehouse / 'layout.py',
                                                fbx.parent / '__init__.py', fbx, imported,
                                                assets / 'vehicles/belmonte-train/line.json'])
    return prepare


def test_actual_recipe_steps_preserve_constructor_filter_result_and_enrichment_order(finite_recipe_steps):
    case = finite_recipe_steps()
    result = case.run(case.ctx)
    expected = ['world.entry', 'character.entry', 'sound.entry', 'ferry.data', 'gondola.data',
                'unreal.entry', 'data.stage', 'adventure.entry', 'hippodrome.entry',
                'belmonte.keep', 'brinecove.keep', 'unreal.ferry', 'unreal.gondola',
                'fit.entry', 'pawn.entry', 'data.content', 'data.network', 'cook', 'package']
    assert [str(s.name) for s in result] == expected
    assert [event[1] for event in case.trace if event[0] == 'call'] == [
        'ferry', 'gondola', 'world', 'character', 'sound', 'unreal', 'staging', 'adventure',
        'hippodrome', 'belmonte', 'brinecove', 'fit', 'pawn', 'cook', 'package']
    filters = [event[1] for event in case.trace if event[0] == 'filter' and event[-1] == 'recipe.steps']
    assert filters == ['ferry.data', 'unreal.ferry', 'gondola.data', 'unreal.gondola'] * 2
    ordered = [event[:2] for event in case.trace if event[0] == 'call'
               or (event[0] == 'filter' and event[-1] == 'recipe.steps')]
    assert ordered.index(('call', 'sound')) < ordered.index(('filter', 'ferry.data')) < ordered.index(('call', 'unreal'))
    assert ordered.index(('call', 'brinecove')) < len(ordered) - 1 - ordered[::-1].index(('filter', 'ferry.data')) < ordered.index(('call', 'fit'))
    assert case.snapshots['fit'][1] == tuple(expected[:13])
    assert case.snapshots['pawn'][1] == tuple(expected[:14])
    assert case.snapshots['fit'][0] is case.snapshots['pawn'][0]
    world = case.values['world'][0]
    assert world.after == ['unreal.north'] and world.inputs == case.expected_inputs
    assert world.reads == ['treehouse.canopy_dimensions']
    assert result[-4].needs == ['unreal.entry', 'unreal.ferry', 'unreal.gondola', 'data.stage']
    assert result[-3].needs == ['unreal.entry', 'unreal.ferry', 'unreal.gondola', 'data.stage', 'data.content']
    assert case.trace[-2:] == [('returned', 'recipe.return'), ('returned', 'recipe.steps')]


@pytest.mark.parametrize('failed', ['gondola', 'world', 'staging', 'fit', 'pawn', 'cook', 'package'])
def test_actual_recipe_steps_keep_original_raised_constructor_and_stop_later_calls(finite_recipe_steps, failed):
    case = finite_recipe_steps(failed)
    with pytest.raises(RuntimeError) as caught:
        case.run(case.ctx)
    assert caught.value is case.original
    calls = [event[1] for event in case.trace if event[0] == 'call']
    assert calls[-1] == failed
    assert case.trace[-1] == ('raised', 'recipe.steps')
    assert ('returned', 'recipe.steps') not in case.trace


def test_current_discovery_provider_roster_uses_static_imports_within_capture_bound(monkeypatch):
    from atelier import paths
    from atelier.build_v2.controller_client import capture_named_sources, MAX_NAMED_ISSUER_FILES
    from atelier.build_v2.legacy_qualification import CapturedCode, captured_spec
    writes = []
    def refuse_write(path, *args, **kwargs):
        writes.append(str(path))
        raise AssertionError('captured declaration preflight attempted mkdir')
    monkeypatch.setattr(Path, 'mkdir', refuse_write)
    name = 'games/yorimichi/legacy_qualification.py'
    initial = capture_named_sources(paths.REPO, (name,))
    spec = captured_spec('existing_discovery_profile',
                         CapturedCode(str(paths.REPO / name), dict(initial.files)[name]))
    profile = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(profile)
    source = capture_named_sources(paths.REPO, profile.source_names(paths.REPO))
    names = dict(source.files)
    assert 'games/yorimichi/build.py' in names
    assert 'games/yorimichi/legacy_qualification.py' in names
    assert 'platform/studio/atelier/build.py' in names
    assert 'platform/studio/atelier/build_products.py' in names
    assert 'games/yorimichi/world/regions/belmonte/source.py' in names
    assert 'games/yorimichi/world/regions/belmonte/query_surface.py' in names
    assert 'games/yorimichi/world/regions/belmonte/terrain.py' in names
    assert 'games/yorimichi/world/regions/village/atomic_sources.py' in names
    assert 'games/yorimichi/world/regions/village/catalogue.py' in names
    for package in ('train', 'regions/brinecove', 'regions/ferry',
                    'regions/hidamari_stable', 'regions/swordcamp'):
        assert f'games/yorimichi/world/{package}/__init__.py' in names
    for name in names:
        boundary = (paths.REPO / 'games/yorimichi' if name.startswith('games/') else
                    paths.REPO / ('platform/studio' if name.startswith('platform/studio/')
                                  else 'platform/harness'))
        parent = (paths.REPO / name).parent
        while parent != boundary:
            assert parent.is_relative_to(boundary)
            initializer = parent / '__init__.py'
            if initializer.is_file():
                assert initializer.relative_to(paths.REPO).as_posix() in names
            parent = parent.parent
    assert all((paths.REPO / name).is_file() for name in names)
    assert len(names) <= MAX_NAMED_ISSUER_FILES == 512
    assert not writes


def test_owned_fixture_cleanup_excludes_shared_descendants_and_exec_transitions():
    from atelier import paths
    from atelier.harness.safety.tree_guard import OwnedTree
    spec = importlib.util.spec_from_file_location(
        'owned_entry_fixture', paths.REPO / 'games/yorimichi/tests/legacy_host_entry_case.py')
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)

    class Table:
        def __init__(self):
            self.names = {pid: 'python' for pid in range(1, 7)}
            self.edges = {1: [2, 3, 5], 3: [4], 5: [6]}
            self.unknown = set()
        def started(self, pid):
            return pid * 10 if pid in self.names else None
        def name(self, pid):
            if pid in self.unknown:
                raise OSError('unknown executable observation')
            return self.names[pid]
        def owned_children(self, pid, start):
            return [(child, child * 10) for child in self.edges.get(pid, [])]

    api = Table()
    tree = OwnedTree(api, 1, 10)
    tree.discover()  # All ordinary actors were independently observed before exec.
    api.names[3] = 'zenserver'
    api.names[5] = 'UnrealTraceServer'
    sent = []
    fixture.signal_readonly_owned(tree, signal.SIGTERM, send=lambda pid, number: sent.append((pid, number)))
    assert {pid for pid, _ in sent} == {1, 2}
    assert all(number == signal.SIGTERM for _, number in sent)
    sent.clear()
    fixture.signal_readonly_owned(tree, signal.SIGKILL, send=lambda pid, number: sent.append((pid, number)))
    assert {pid for pid, _ in sent} == {1, 2}
    assert all(number == signal.SIGKILL for _, number in sent)
    api.unknown.add(2)
    sent.clear()
    with pytest.raises(OSError, match='unknown executable'):
        fixture.signal_readonly_owned(tree, signal.SIGTERM, send=lambda pid, number: sent.append((pid, number)))
    assert not sent


def _entry_fixture():
    from atelier import paths
    spec = importlib.util.spec_from_file_location(
        'retained_entry_fixture', paths.REPO / 'games/yorimichi/tests/legacy_host_entry_case.py')
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    return fixture


def test_fixture_retains_only_exact_bounded_control_diagnostics_without_env_or_request_values(tmp_path):
    fixture = _entry_fixture()
    control = tmp_path / 'build/build-v2/legacy-host' / ('a' * 32)
    evidence = tmp_path / 'evidence'
    control.mkdir(parents=True, mode=0o700)
    evidence.mkdir(mode=0o700)
    def private(path, raw):
        path.write_bytes(raw)
        path.chmod(0o600)
    private(evidence / 'stdout.log', f'Managed legacy authority control: {control}\n'.encode())
    private(control / 'startup.json', json.dumps({
        'version': 2, 'nonce': 'a' * 32, 'host': {'pid': 7, 'boot': 'boot', 'started': '9'},
        'operational_environment': {'agent': 'DO_NOT_COPY_PRIVATE_VALUE'},
    }).encode())
    private(control / 'request.json', b'{"private":"DO_NOT_COPY_PRIVATE_VALUE"}')
    raw_log = b'legacy_phase v1 fixed retained diagnostic\n'
    private(control / 'scheduler.log', raw_log)
    result = fixture.retain_control_diagnostics(tmp_path, evidence)
    assert result == {'locator': 'bound', 'retained': ['startup.json', 'request.json', 'scheduler.log']}
    binding = (evidence / 'failed-control-binding.json').read_bytes()
    request = (evidence / 'failed-request-binding.json').read_bytes()
    assert b'DO_NOT_COPY_PRIVATE_VALUE' not in binding + request
    assert (evidence / 'failed-scheduler.log').read_bytes() == raw_log
    assert (evidence / 'failed-scheduler.log').stat().st_mode & 0o777 == 0o600
    assert 'cleanup' not in result and 'complete' not in result


@pytest.mark.parametrize('fault', ['missing-locator', 'multiple-locators', 'linked-log', 'oversized-log'])
def test_fixture_unknown_control_diagnostics_do_not_follow_links_search_or_invent_cleanup(tmp_path, fault):
    fixture = _entry_fixture()
    control = tmp_path / 'build/build-v2/legacy-host' / ('b' * 32)
    evidence = tmp_path / 'evidence'
    control.mkdir(parents=True, mode=0o700)
    evidence.mkdir(mode=0o700)
    line = f'Managed legacy authority control: {control}\n'
    (evidence / 'stdout.log').write_text('' if fault == 'missing-locator' else
                                       line * (2 if fault == 'multiple-locators' else 1))
    (evidence / 'stdout.log').chmod(0o600)
    outside = tmp_path / 'outside'
    outside.write_bytes(b'private-unrelated-original')
    outside.chmod(0o600)
    if fault == 'linked-log':
        (control / 'scheduler.log').symlink_to(outside)
    elif fault == 'oversized-log':
        (control / 'scheduler.log').write_bytes(b'x' * (256 * 1024 + 1))
        (control / 'scheduler.log').chmod(0o600)
    result = fixture.retain_control_diagnostics(tmp_path, evidence)
    assert result['retained'] == []
    assert result['locator'] == ('unknown' if 'locator' in fault else 'bound')
    assert not (evidence / 'failed-scheduler.log').exists()
    assert outside.read_bytes() == b'private-unrelated-original'
    assert 'cleanup' not in result and 'complete' not in result
