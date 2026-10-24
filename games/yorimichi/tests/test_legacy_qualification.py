"""Finite provider and scripted operational checks; real entry evidence is separate."""
from pathlib import Path
import ast
from contextlib import contextmanager
import importlib.util
import signal
import json
from types import SimpleNamespace
import pytest


@pytest.fixture
def scripted_index_provider(tmp_path):
    """Production control-family code with scripted RPCs; not Rust authority proof."""
    from atelier import paths
    from atelier.source_imports import ImportScanner
    from atelier.build_v2.controller_client import capture_named_sources
    from atelier.build_v2.legacy_qualification import CapturedCode, captured_spec
    name = 'games/yorimichi/legacy_qualification.py'
    raw = (paths.REPO / name).read_bytes()
    spec = captured_spec('scripted_index_profile', CapturedCode(str(paths.REPO / name), raw))
    profile = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(profile)
    members = {source.relative_to(paths.REPO).as_posix() for source in
               ImportScanner().local_imports(paths.REPO / 'platform/studio/atelier/build_hashes.py')}
    members.add(name)
    for member in members:
        target = tmp_path / member
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((paths.REPO / member).read_bytes())
    captured = capture_named_sources(tmp_path, sorted(members))
    captured.materialize(tmp_path / 'issuer')
    (tmp_path / 'build/yorimichi').mkdir(parents=True)
    manifest = {'checkout': str(tmp_path), 'issuer_root': str(tmp_path / 'issuer'),
                'issuer_files': list(sorted(members)), 'issuer_digest': captured.digest,
                'source_digest': 'b' * 64, 'nonce': 'c' * 32,
                'scheduler_request': {'digest': 'd' * 64},
                'python_context': {'platform_roots': []}}
    request = {'game': 'yorimichi', 'wanted': ['data.stage'], 'options': {'verify': False}}
    class ScriptedClient:
        record_digest = None
        frame = None
        def __init__(self, deny=False):
            self.calls, self.deny = [], deny
        def request(self, operation):
            self.calls.append(operation)
            if operation['type'] == 'begin_attempt' and self.deny:
                raise RuntimeError('scripted intent refusal')
            if operation['type'] == 'advance':
                self.frame = 1
            return {}
    return SimpleNamespace(root=tmp_path, profile=profile, manifest=manifest, request=request, run=lambda client: profile._control_index(manifest, request, client),
                           client=ScriptedClient)


def test_actual_hash_index_provider_refuses_before_write_when_intent_is_not_granted(scripted_index_provider):
    case = scripted_index_provider
    client = case.client(deny=True)
    with pytest.raises(RuntimeError, match='intent refusal'):
        case.run(client)
    assert [item['type'] for item in client.calls] == ['prepare_selection', 'advance', 'begin_attempt']
    assert not (case.root / 'build/yorimichi/.state').exists()


def test_actual_hash_index_provider_closes_and_validates_complete_scope_before_settlement(scripted_index_provider):
    case = scripted_index_provider
    client = case.client()
    case.run(client)
    assert [item['type'] for item in client.calls] == ['prepare_selection', 'advance', 'begin_attempt', 'settle']
    scope = client.calls[1]['observation']['tasks'][0]['writes']
    outputs = client.calls[-1]['observation']['outputs']
    assert [item['path'] for item in scope] == [item['path'] for item in outputs]
    assert outputs[0]['fact']['kind'] == 'file'
    assert all(item['fact']['kind'] == 'absent' for item in outputs[1:])
    assert (case.root / outputs[0]['path']).read_bytes().startswith(b'SQLite format 3')


def test_actual_hash_index_provider_refuses_link_before_intent_and_preserves_foreign_bytes(scripted_index_provider):
    case = scripted_index_provider
    state = case.root / 'build/yorimichi/.state'
    state.mkdir()
    foreign = case.root / 'foreign'
    foreign.write_bytes(b'preserve foreign bytes')
    (state / 'file-hashes.sqlite3').symlink_to(foreign)
    client = case.client()
    with pytest.raises(OSError):
        case.run(client)
    assert 'begin_attempt' not in [item['type'] for item in client.calls]
    assert foreign.read_bytes() == b'preserve foreign bytes'


def test_actual_hash_index_provider_keeps_normal_memory_fallback_and_corrupt_hint_bytes(scripted_index_provider):
    case = scripted_index_provider
    state = case.root / 'build/yorimichi/.state'
    state.mkdir()
    hint = state / 'file-hashes.sqlite3'
    hint.write_bytes(b'not a SQLite database; preserve this hint')
    client = case.client()
    case.run(client)
    assert client.calls[-1]['type'] == 'settle'
    assert hint.read_bytes() == b'not a SQLite database; preserve this hint'


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
    assert 'games/yorimichi/world/gen_textures.py' in names
    assert 'games/yorimichi/world/surface_textures.py' in names
    assert 'platform/studio/atelier/build_v2/legacy_action.py' in names
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


def test_texture_guard_uses_the_recorded_queue_deadline_without_reset(tmp_path, monkeypatch):
    from atelier import paths
    from atelier.build_v2 import legacy_client
    from atelier.build_v2.legacy_qualification import CapturedCode, captured_spec
    path = paths.REPO / 'games/yorimichi/legacy_qualification.py'
    spec = captured_spec('finite_texture_deadline_profile', CapturedCode(str(path), path.read_bytes()))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    authority = module.TextureAuthority.__new__(module.TextureAuthority)
    authority.expected_argv, authority.expected_environment = ['python', 'actual-args'], {'closed': 'context'}
    authority.queue_deadline_ns = 20_000_000_000
    authority.custody = {'build': 10, 'content': 11, 'writer': 12}
    authority.launch_context, authority.invocation = object(), 'a' * 32
    authority.checkout, authority.step = tmp_path, SimpleNamespace(name='world.textures.leaf_broad')
    monkeypatch.setattr(legacy_client, 'authority_now_ns', lambda: 15_000_000_000)
    options = authority.guard_options(authority.expected_argv, authority.expected_environment, 'job')
    assert options['queue_seconds'] == 5.
    assert options['custody_fds'] == (10, 11, 12)
    assert options['launch_context'] is authority.launch_context
    monkeypatch.setattr(legacy_client, 'authority_now_ns', lambda: 20_000_000_000)
    with pytest.raises(ValueError, match='deadline expired'):
        authority.guard_options(authority.expected_argv, authority.expected_environment, 'job')


def test_texture_prepared_only_null_frame_preserves_host_qualification_path(scripted_index_provider, monkeypatch):
    # Scripted protocol observations exercise the actual Python cut handling only;
    # the real Rust prepare/Supersede rules remain the permission authority.
    case = scripted_index_provider
    module = case.profile
    authority = module.TextureAuthority.__new__(module.TextureAuthority)
    authority.checkout, authority.manifest, authority.request = case.root, case.manifest, case.request
    authority.client, authority.nonce = case.client(), 'e' * 32
    authority.attempt = 'prepare-' + authority.nonce
    authority.step = SimpleNamespace(name='world.textures.leaf_broad')
    authority.metadata = 'control.textures.scheduler'
    authority.steps = {authority.step.name: authority.step}
    authority.profiles = {authority.step.name: SimpleNamespace(output=case.root / 'build/yorimichi/textures/T_leaf_broad.png')}
    authority.build = SimpleNamespace(fingerprint_state=lambda *a, **k: ('f' * 64, {}), required_inputs=lambda step: [])
    authority.hashlib = __import__('hashlib')
    monkeypatch.setattr(module, '_prior_record', lambda client: {'frame': None, 'binding': {}})
    ctx = SimpleNamespace(out=case.root / 'build/yorimichi')
    authority.texture_steps = dict(authority.steps)
    authority.generated_inputs = set()
    authority.output_paths = {name: (profile.output,) for name, profile in authority.profiles.items()}
    authority.before_prepare(ctx, [], ['data.stage'])
    calls = authority.client.calls
    assert [item['type'] for item in calls] == ['supersede', 'begin_attempt']
    assert [task['id'] for task in calls[0]['initial_frame']['tasks']] == [authority.metadata, authority.step.name]
    assert calls[1]['attempt']['execution'] == {'kind': 'in_process'}
    assert not (ctx.out / '.state').exists()


def test_selected_runtime_key_and_roster_bind_used_helpers_but_not_unrelated_issuer(tmp_path, monkeypatch):
    import ast
    from atelier.build_v2.legacy_qualification import CapturedCode
    import importlib.util
    from types import SimpleNamespace
    from atelier import build, build_audit, paths
    from atelier.build_v2.legacy_qualification import captured_spec
    root = paths.REPO
    catalogue_path = root / 'games/yorimichi/world/texture_catalog.py'
    def load(name, path):
        spec = captured_spec(name, CapturedCode(str(path), path.read_bytes()))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    tree = ast.parse((root / 'games/yorimichi/build.py').read_bytes())
    factory = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'texture_steps')
    namespace = {'Step': build.Step, 'Python': build.Python, 'Product': build.Product,
                 'WORLD': catalogue_path.parent, 'ASSETS': root / 'games/yorimichi/assets',
                 '_load_helper_module': load}
    exec(compile(ast.Module(body=[factory], type_ignores=[]), str(root / 'games/yorimichi/build.py'), 'exec'), namespace)
    step = namespace['texture_steps'](SimpleNamespace(out=tmp_path / 'out'))[0]
    monkeypatch.setattr(build_audit.build_cache if hasattr(build_audit, 'build_cache') else __import__('atelier.build_cache', fromlist=['tool_context']),
                        'tool_context', lambda *a, **k: {'normal': 'unchanged'})
    original = build_audit.tool_context(step, lambda path: 'original')
    assert original == {'normal': 'unchanged'}
    profile = load('actual_game_profile_runtime_test', root / 'games/yorimichi/legacy_qualification.py')
    issuer = profile.source_names(root)
    runtime = build_audit._bind_captured_runtime(step, checkout=root, issuer_files=issuer)
    assert 'games/yorimichi/world/gen_textures.py' in runtime.files
    assert set(build_audit._CAPTURED_WORKER) <= set(runtime.files)
    assert 'games/yorimichi/village_atomic_build.py' in issuer
    assert 'games/yorimichi/village_atomic_build.py' not in runtime.files
    assert len(runtime.files) < len(issuer)
    before = build_audit.tool_context(step, lambda path: 'original')
    after = build_audit.tool_context(step, lambda path: 'changed' if Path(path).name == 'legacy_qualification.py' else 'original')
    assert before != after
    assert before['captured_python_runtime']['flags'] == ['-I', '-S', '-B']
    assert str(root) not in str(before['captured_python_runtime'])
    assert build_audit.NATIVE not in build_audit.captured_runtime_inputs(step)


def test_texture_group_frame_separates_shared_metadata_and_products_and_settles_after_close(scripted_index_provider, monkeypatch):
    case = scripted_index_provider
    module = case.profile
    authority = module.TextureAuthority.__new__(module.TextureAuthority)
    authority.checkout, authority.manifest, authority.request = case.root, case.manifest, case.request
    authority.client, authority.nonce = case.client(), 'a' * 32
    authority.metadata = 'control.textures.scheduler'
    authority.attempt = authority.preparation_attempt = 'prepare-' + authority.nonce
    authority.hashlib = __import__('hashlib')
    authority.steps = {name: SimpleNamespace(name=name) for name in
                       ('world.textures.leaf_broad', 'world.textures.leaf_cedar')}
    authority.profiles = {name: SimpleNamespace(output=case.root / 'build/yorimichi/textures' / (name + '.png'))
                          for name in authority.steps}
    authority.runtimes = {name: object() for name in authority.steps}
    authority.completed = {}
    authority.aggregate, authority.aggregate_done = None, None
    authority.native_steps, authority.native_launch, authority.dones = {}, None, {}
    authority.build = SimpleNamespace(fingerprint_state=lambda *a, **k: ('f' * 64, {}), required_inputs=lambda step: [])
    monkeypatch.setattr(module, '_prior_record', lambda client: None)
    ctx = SimpleNamespace(out=case.root / 'build/yorimichi')
    authority.texture_steps = dict(authority.steps)
    authority.generated_inputs = set()
    authority.output_paths = {name: (profile.output,) for name, profile in authority.profiles.items()}
    authority.before_prepare(ctx, [], ['data.stage'])
    frame = authority.client.calls[1]['observation']
    assert len(frame['tasks']) == 3
    shared, *products = frame['tasks']
    assert shared['id'] == authority.metadata
    assert all('/textures/' not in claim['path'] for claim in shared['writes'])
    assert [len(task['writes']) for task in products] == [1, 1]
    assert authority.client.calls[-1]['attempt']['members'] == [authority.metadata, *authority.steps]
    monkeypatch.setattr(authority, '_check_certificate', lambda ctx, step: 'f' * 64)
    invocations = []
    for step in authority.steps.values():
        authority.before_task(ctx, step)
        invocations.append((authority.invocation, authority.guard_relative))
        authority.after_task(ctx, step, None)
    assert len(set(invocations)) == 2
    assert not any(call['type'] == 'settle' for call in authority.client.calls)
    authority.checkpoint_complete(ctx, [])
    assert not any(call['type'] == 'settle' for call in authority.client.calls)
    authority.after_index(ctx)
    settled = [call['observation']['task'] for call in authority.client.calls if call['type'] == 'settle']
    assert settled == [*authority.steps, authority.metadata]
    assert all(call['observation']['attempt'] == authority.preparation_attempt
               for call in authority.client.calls if call['type'] == 'settle')
    with pytest.raises(ValueError, match='invalidated'):
        authority.after_checkpoint(ctx, ['changed'])


def test_texture_same_frame_continuation_requeues_only_settled_members_before_new_intent(scripted_index_provider, monkeypatch):
    case = scripted_index_provider
    module = case.profile
    authority = module.TextureAuthority.__new__(module.TextureAuthority)
    authority.checkout, authority.manifest, authority.request = case.root, case.manifest, case.request
    authority.client, authority.nonce = case.client(), 'b' * 32
    authority.metadata = 'control.textures.scheduler'
    authority.attempt = authority.preparation_attempt = 'prepare-' + authority.nonce
    authority.hashlib = __import__('hashlib')
    step = SimpleNamespace(name='world.textures.leaf_broad')
    authority.steps = {step.name: step}
    authority.profiles = {step.name: SimpleNamespace(output=case.root / 'build/yorimichi/textures/T_leaf_broad.png')}
    authority.build = SimpleNamespace(fingerprint_state=lambda *a, **k: ('f' * 64, {}), required_inputs=lambda step: [])
    monkeypatch.setattr(module, '_prior_record', lambda client: None)
    ctx = SimpleNamespace(out=case.root / 'build/yorimichi')
    authority.texture_steps = dict(authority.steps)
    authority.generated_inputs = set()
    authority.output_paths = {name: (profile.output,) for name, profile in authority.profiles.items()}
    authority.before_prepare(ctx, [], ['data.stage'])
    frame = authority.client.calls[1]['observation']
    binding = authority.client.calls[0]['observation']
    authority.client.calls.clear()
    old = {'binding': binding, 'frame': {'scope': frame, 'pending': [step.name],
                                       'settled': [{'task': authority.metadata}]}}
    monkeypatch.setattr(module, '_prior_record', lambda client: old)
    authority.texture_steps = dict(authority.steps)
    authority.generated_inputs = set()
    authority.output_paths = {name: (profile.output,) for name, profile in authority.profiles.items()}
    authority.before_prepare(ctx, [], ['data.stage'])
    assert [call['type'] for call in authority.client.calls] == ['prepare_selection', 'requeue', 'begin_attempt']
    assert authority.client.calls[1]['members'] == [authority.metadata]
    assert authority.client.calls[2]['attempt']['members'] == [authority.metadata, step.name]
    assert not (ctx.out / '.state').exists()


def test_texture_failed_final_certificate_never_settles_earlier_members_or_metadata(scripted_index_provider, monkeypatch):
    case = scripted_index_provider
    authority = case.profile.TextureAuthority.__new__(case.profile.TextureAuthority)
    authority.client = case.client()
    authority.aggregate, authority.aggregate_done = None, None
    authority.native_steps, authority.native_launch, authority.dones = {}, None, {}
    authority.completed = {'world.textures.leaf_broad': 'attempt-one', 'world.textures.leaf_cedar': 'attempt-two'}
    authority.steps = {name: SimpleNamespace(name=name) for name in authority.completed}
    def check(ctx, step):
        if step.name.endswith('leaf_cedar'):
            raise ValueError('changed original certificate')
        return 'f' * 64
    monkeypatch.setattr(authority, '_check_certificate', check)
    with pytest.raises(ValueError, match='changed original certificate'):
        authority.after_checkpoint(SimpleNamespace(), [])
    assert authority.client.calls == []


def test_actual_texture_read_aggregate_has_no_commands_outputs_or_extra_controls():
    from dataclasses import replace
    from atelier import build, build_products, paths
    from atelier.build_v2.legacy_client import AuthorityRefused
    from atelier.build_v2.legacy_qualification import CapturedCode, captured_spec
    path = paths.REPO / 'games/yorimichi/legacy_qualification.py'
    spec = captured_spec('texture_aggregate_constraints', CapturedCode(str(path), path.read_bytes()))
    profile = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(profile)
    recipe = build.load_recipe('yorimichi')
    steps = recipe.texture_steps(SimpleNamespace(out=paths.REPO / 'build/yorimichi'))
    graph = build_products.Graph(steps)
    aggregate = graph.by_name['world.textures']
    products = [step.products[0].name for step in steps if step.products]
    assert profile.qualify_texture_aggregate(aggregate, build=build, graph=graph, products=products) is aggregate
    for mutation in ({'commands': [build.Python(recipe.WORLD / 'gen_textures.py')]},
                     {'outputs': [paths.REPO / 'build/yorimichi/textures']},
                     {'reads': list(reversed(products))}, {'cache': True}, {'replan': True}):
        with pytest.raises(AuthorityRefused):
            profile.qualify_texture_aggregate(replace(aggregate, **mutation), build=build, graph=graph, products=products)


def test_actual_aggregate_reuses_original_product_keys_and_detects_changed_reads(tmp_path):
    from atelier import build, build_products, paths
    from atelier.build_hashes import HashIndex
    from atelier.build_v2.legacy_qualification import CapturedCode, captured_spec
    source = paths.REPO / 'games/yorimichi/legacy_qualification.py'
    spec = captured_spec('actual_aggregate_metadata_flow', CapturedCode(str(source), source.read_bytes()))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    factory = build.load_recipe('yorimichi')
    steps = factory.texture_steps(SimpleNamespace(out=tmp_path))
    textures = {step.name: step for step in steps if step.products}
    aggregate = next(step for step in steps if step.name == 'world.textures')
    done = {}
    for step in textures.values():
        step.outputs[0].parent.mkdir(parents=True, exist_ok=True)
        step.outputs[0].write_bytes(step.name.encode())
        build_products.feed_results(done, build_products.records(step))
    index = HashIndex()
    ctx = SimpleNamespace(build_hash_index=index, build_tool_cache={}, stamps=tmp_path / 'stamps')
    ctx.stamps.mkdir()
    key = build.fingerprint(aggregate, done, index=index, tool_cache={})
    (ctx.stamps / (aggregate.name + '.json')).write_text(json.dumps({'fingerprint': key}))
    authority = module.TextureAuthority.__new__(module.TextureAuthority)
    authority.build, authority.steps, authority.aggregate = build, textures, aggregate
    authority.texture_steps = textures
    authority.native_steps, authority.dones = {}, {}
    authority.aggregate_done = None
    authority.completed = {name: 'original-attempt' for name in textures}
    authority.preparation_attempt = 'original-preparation'
    authority.before_task(ctx, aggregate)
    authority.after_task(ctx, aggregate, None, done=done)
    assert authority.runtime is None and authority.attempt == authority.preparation_attempt
    assert authority.aggregate_key == key and set(authority.completed) == set(textures)
    assert aggregate.commands == [] and aggregate.outputs == []
    index.close()
    authority._check_aggregate(ctx)
    next(iter(textures.values())).outputs[0].write_bytes(b'changed product after aggregate')
    with pytest.raises(ValueError, match='aggregate read identity'):
        authority._check_aggregate(ctx)
