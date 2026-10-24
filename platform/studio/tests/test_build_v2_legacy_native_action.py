"""Used native code/argv observations only; no Blender or launch authority fabricated."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier import build, build_cache, paths
from atelier.build_v2 import legacy_native_action as native


def test_original_native_worker_argv_preserves_flags_and_binds_exact_bootstrap():
    command = build.Blender(paths.STUDIO / 'atelier/build_batch_worker.py', threads=3,
                            factory_startup=True, env=(('PYTHONHASHSEED', '0'),))
    ctx = SimpleNamespace(blender='original-pinned-blender')
    argv = native.worker_argv(command, ctx, startup=Path('/owned/startup.json'),
                             specification=Path('/owned/spec.json'), specification_digest='a' * 64,
                             capture_file=Path('/owned/controller_client.py'), capture_digest='b' * 64)
    assert argv[:8] == ['original-pinned-blender', '--factory-startup', '-b', '--threads', '3',
                        '--python-exit-code', '1', '--python-expr']
    assert len(argv) == 9 and 'a' * 64 in argv[-1] and 'b' * 64 in argv[-1]
    assert '/owned/spec.json' in argv[-1]
    assert command.script == paths.STUDIO / 'atelier/build_batch_worker.py'
    assert command.env == (('PYTHONHASHSEED', '0'),) and command.args == ()
    for changed in (build.Blender(Path('unknown.py'), threads=3),
                    build.Blender(command.script, args=('unexpected',), threads=3)):
        with pytest.raises(ValueError, match='worker role'):
            native.worker_argv(changed, ctx, startup=Path('/s'), specification=Path('/r'),
                               specification_digest='a' * 64, capture_file=Path('/c'), capture_digest='b' * 64)


def test_native_runtime_uses_selected_code_in_original_input_encoder_without_python_worker(tmp_path, monkeypatch):
    script = tmp_path / 'producer.py'
    script.write_text('value = 1\n')
    names = {'producer.py', *native._WORKER}
    for name in native._WORKER:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('pass\n')
    step = build.Step('fixed-native-member', [build.Blender(script, threads=3, factory_startup=True)],
                      products=[build.Product('result', (tmp_path / 'result',))], cache=True, heavy=True)
    assert native.captured_native_inputs(step) == ()
    monkeypatch.setattr(build_cache, 'tool_context', lambda *a, **k: {'checked': 'fixture-tool-context'})
    runtime = native._bind_native_runtime(step, checkout=tmp_path, issuer_files=sorted(names))
    assert set(runtime.files) == names
    assert not any(name.endswith(('build_audit_worker.py', 'legacy_bootstrap.py')) for name in runtime.files)
    assert set(native.captured_native_inputs(step)) <= set(build.required_inputs(step))
    first = build.fingerprint(step, {})
    (tmp_path / 'platform/studio/atelier/build_v2/legacy_native_action.py').write_text('value = 2\n')
    assert build.fingerprint(step, {}) != first
    step._captured_native_runtime = SimpleNamespace(files=runtime.files)
    with pytest.raises(ValueError, match='unqualified'):
        build.required_inputs(step)


@pytest.mark.parametrize('original,expected', [(0., 600.), (300., 300.), (900., 600.)])
def test_native_shared_intent_precedes_files_and_uses_one_recorded_bound(tmp_path, monkeypatch, original, expected):
    import hashlib
    import os
    from atelier.build_v2 import legacy_client
    from atelier.harness import capacity_runtime, capacity_protocol
    monkeypatch.delenv('ATELIER_CAPACITY_CLIENT', raising=False)
    monkeypatch.setattr(capacity_runtime, 'read_configuration', lambda path: {'schema': 2})
    monkeypatch.setattr(capacity_protocol, 'boot_id', lambda: 'same-boot')
    monkeypatch.setattr(capacity_protocol, 'process_start', lambda pid: 123)
    monkeypatch.setattr(legacy_client, 'authority_now_ns', lambda: 1_000_000_000)
    from atelier import build_audit
    bundle = tmp_path / 'Blender.app/Contents'
    monkeypatch.setattr(build_audit, 'installation', lambda command: [bundle])
    calls = []
    class Client:
        def request(self, record):
            # Permission must be accepted before ANY fresh worker/control files.
            assert not launch.directory.exists()
            calls.append(record)
    a = SimpleNamespace(checkout=tmp_path, nonce='a' * 32, metadata='control.scheduler',
                        custody={'build': 10, 'content': 11, 'writer': 12}, client=Client(),
                        manifest={'distribution': str(tmp_path / 'distribution'), 'source_digest': 'b' * 64,
                                  'issuer_digest': 'c' * 64, 'scheduler_request': {'digest': 'd' * 64},
                                  'work_deadline_ns': 5000 * 1_000_000_000},
                        files=[('platform/studio/atelier/build_v2/controller_client.py', b'pinned')])
    step = build.Step('actual-qualified-member', [])
    session = SimpleNamespace(candidates=[(step, 'e' * 64, {})], nonce='f' * 32,
                              guard=tmp_path / 'original-stable-batch.guard')
    runtime = native._NativeRuntime(tmp_path, native._WORKER, native._ORIGIN)
    from atelier.build_v2.legacy_native_launch import NativeBatchLaunch
    launch = NativeBatchLaunch(a, session, {step.name: runtime})
    command = build.Blender(paths.STUDIO / 'atelier/build_batch_worker.py', threads=3,
                            factory_startup=True, env=(('ATELIER_BATCH', str(tmp_path / '.state/batches/f')),
                                                      ('PYTHONHASHSEED', '0')))
    command.timeout = original
    ctx = SimpleNamespace(blender=str(bundle / 'MacOS/Blender'))
    with launch.prepared(ctx, command) as (argv, environment, descriptors):
        assert descriptors == ()  # Checkout locks go to monitor custody, NEVER worker pass_fds.
        assert len(calls) == 1 and calls[0]['attempt']['members'] == [a.metadata, step.name]
        intent = calls[0]['attempt']['execution']['launch']
        assert intent['execution_ns'] == int(expected * 1e9) and launch.work_seconds == expected
        assert intent['threads'] == 3 and intent['memory_bytes'] == 10 * 1024**3
        assert (intent['program'], intent['args']) == (argv[0], argv[1:])
        assert os.stat(launch.context).st_mode & 0o777 == 0o600
        assert hashlib.sha256(launch.context.read_bytes()).hexdigest() in argv[-1]
        assert session.guard == launch.directory
        options = launch.guard_options(argv, dict(environment), 'job')
        assert options['logical_folder'] == tmp_path / 'original-stable-batch.guard'
        assert options['custody_fds'] == (10, 11, 12) and options['queue_seconds'] == 1800.
        monkeypatch.setattr(legacy_client, 'authority_now_ns', lambda: 11_000_000_000)
        assert launch.guard_options(argv, dict(environment), 'job')['queue_seconds'] == 1790.
        with pytest.raises(ValueError, match='differs'):
            launch.guard_options([*argv, 'extra'], dict(environment), 'job')


def test_native_bootstrap_rejects_preloaded_project_before_open_or_import(monkeypatch):
    import os
    command = build.Blender(paths.STUDIO / 'atelier/build_batch_worker.py', threads=3, factory_startup=True)
    argv = native.worker_argv(command, SimpleNamespace(blender='pinned-blender'),
                             startup=Path('/absent/startup'), specification=Path('/absent/spec'),
                             specification_digest='a' * 64, capture_file=Path('/absent/capture'), capture_digest='b' * 64)
    monkeypatch.setattr(os, 'open', lambda *a, **k: pytest.fail('bootstrap touched files before preload refusal'))
    with pytest.raises(RuntimeError, match='preloaded project helpers'):
        exec(compile(argv[-1], '<string>', 'exec'), {'__name__': '__main__'})


def test_caught_sticky_origin_failure_cannot_reach_original_batch_receipt(tmp_path, monkeypatch):
    import json
    import runpy
    import sys
    from atelier import build_batch_worker as worker
    from atelier.build_v2.legacy_action import captured_execution_check
    from atelier.build_v2.legacy_qualification import CapturedCode, UnsupportedOrigin
    script = tmp_path / 'producer.py'
    script.write_text('value = 1\n')
    gate = captured_execution_check([CapturedCode(str(script), script.read_bytes())], checkout=tmp_path, platform_roots=[])
    folder = tmp_path / 'batch'
    folder.mkdir()
    (folder / 'plan.json').write_text(json.dumps({'nonce': 'original-plan', 'kind': 'Blender',
        'actions': [{'name': 'original-member', 'script': str(script), 'args': [], 'env': {}}]}))
    monkeypatch.setenv('ATELIER_BATCH', str(folder))
    monkeypatch.setattr(sys, 'path', list(sys.path))
    monkeypatch.setattr(sys, 'argv', list(sys.argv))
    caught = []
    def producer(*args, **kwargs):
        try:
            gate('exec', (compile('value = 2', str(tmp_path / 'uncaptured.py'), 'exec'),))
        except UnsupportedOrigin:
            caught.append('producer-caught-refusal')
        return {}
    monkeypatch.setattr(runpy, 'run_path', producer)
    original_write = worker.write
    def guarded_write(path, value):
        assert not path.name.endswith('.receipt.json'), 'caught refusal reached an original success receipt'
        original_write(path, value)
    monkeypatch.setattr(worker, 'write', guarded_write)
    with pytest.raises(UnsupportedOrigin, match='sticky'):
        with native.checked_actions(gate):
            worker.main()
    assert caught == ['producer-caught-refusal']
    assert not (folder / 'original-member.receipt.json').exists()
    assert not (folder / 'result.json').exists()
    assert runpy.run_path is producer  # The original binding restores even on refusal.


def test_parent_validator_bytes_enter_existing_keys_without_worker_code_permission(tmp_path, monkeypatch):
    import hashlib
    from atelier.build_v2.legacy_qualification import CallableObservation
    script = tmp_path / 'producer.py'
    script.write_text('value = 1\n')
    validator = tmp_path / 'validator.py'
    validator.write_text('def valid(): return True\n')
    names = {'producer.py', 'validator.py', *native._WORKER}
    for name in native._WORKER:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('pass\n')
    step = build.Step('fixed-native-member', [build.Blender(script, threads=3, factory_startup=True)],
                      products=[build.Product('result', (tmp_path / 'result',))], cache=True, heavy=True)
    checked = CallableObservation(str(validator), 'valid', 1, hashlib.sha256(validator.read_bytes()).hexdigest(), ())
    monkeypatch.setattr(build_cache, 'tool_context', lambda *a, **k: {'checked': 'fixture-tool'})
    runtime = native._bind_native_runtime(step, checkout=tmp_path, issuer_files=sorted(names), verifier=checked)
    assert runtime.validators == ('validator.py',) and 'validator.py' not in runtime.files
    assert validator in build.required_inputs(step)
    first = build.fingerprint(step, {})
    validator.write_text('def valid(): return False\n')
    assert build.fingerprint(step, {}) != first
    del step._captured_native_runtime
    with pytest.raises(ValueError, match='validator source changed'):
        native._bind_native_runtime(step, checkout=tmp_path, issuer_files=sorted(names), verifier=checked)


def test_preload_diagnostic_collects_multiple_unknowns_bounded_without_private_values(tmp_path, monkeypatch, capsys):
    import json
    import sys
    from types import ModuleType
    first = ModuleType('closed_unknown_one')
    second = ModuleType('closed_unknown_two')
    secret = 'private-value-never-print'
    second.__file__ = '/outside/' + secret + '/module.py'
    second.__spec__ = SimpleNamespace(origin=second.__file__, loader=object())
    observed = {'closed_unknown_one': first, 'closed_unknown_two': second, **sys.modules}
    monkeypatch.setattr(sys, 'modules', observed)
    monkeypatch.setattr(sys, 'argv', ['blender', '--python-expr', 'pass'])
    caller = SimpleNamespace(f_code=compile('pass', '<string>', 'exec'),
                             f_globals=vars(sys.modules['__main__']))
    with pytest.raises(ValueError, match='unclassified preloaded providers'):
        native._preloaded({'distribution': str(tmp_path / 'distribution')}, [tmp_path / 'Contents'], caller)
    stderr = capsys.readouterr().err
    line = next(line for line in stderr.splitlines() if line.startswith('native_preload_unclassified '))
    raw = line.removeprefix('native_preload_unclassified ')
    record = json.loads(raw)
    assert record['count'] >= 2 and len(raw.encode()) <= 8192
    table = {row['name']: row for row in record['modules']}
    assert {'closed_unknown_one', 'closed_unknown_two'} <= set(table)
    assert table['closed_unknown_two']['file_role'] == 'outside-checked-roots'
    assert secret not in stderr and '/outside/' not in stderr


def test_registered_native_providers_require_exact_parent_and_factory_identity(tmp_path):
    from types import ModuleType
    import types
    root = tmp_path / 'pinned'
    tool = lambda value: bool(value) and Path(value).is_relative_to(root)
    main = ModuleType('__main__')
    mp = ModuleType('multiprocessing'); mp.__file__ = str(root / 'multiprocessing/__init__.py')
    modules = {'__main__': main, 'multiprocessing': mp}
    assert native._registered_tool_provider('__mp_main__', main, modules, (), tool, vars(main))
    assert not native._registered_tool_provider('__mp_main__', ModuleType('__main__'), modules, (), tool, vars(main))
    math = ModuleType('mathutils'); child = ModuleType('mathutils.geometry'); math.geometry = child
    modules['mathutils'] = math
    assert native._registered_tool_provider('mathutils.geometry', child, modules, ('mathutils',), tool, {})
    assert not native._registered_tool_provider('mathutils.geometry', ModuleType('mathutils.geometry'), modules, ('mathutils',), tool, {})
    assert not native._registered_tool_provider('mathutils.unknown', child, modules, ('mathutils',), tool, {})
    binding = ModuleType('_bpy'); binding._utils_units = child; modules['_bpy'] = binding
    assert native._registered_tool_provider('bpy.utils.units', child, modules, (), tool, {})
    binding._utils_units = ModuleType('other')
    assert not native._registered_tool_provider('bpy.utils.units', child, modules, (), tool, {})
    fre = ModuleType('_freestyle')
    assert not native._registered_tool_provider('_freestyle', fre, modules, ('_freestyle',), tool, {})
    assert not native._registered_tool_provider('_freestyle', fre, modules, (), tool, {})
    class Handle:
        def submodule_items(self): return tuple(self.items.items())
    handle = Handle(); base = ModuleType('bl_ext'); base.__file__ = '[bl_ext]'
    namespace = ModuleType('bl_ext.user_default'); namespace.__file__ = '[bl_ext.user_default]'
    namespace.__path__ = ['/untrusted/namespace/search']
    base.user_default = namespace; handle._module = base; handle.items = {'user_default': namespace}
    addon = ModuleType('addon_utils'); addon.__file__ = str(root / 'addon_utils.py')
    addon._ext_global = types.SimpleNamespace(module_handle=handle)
    junction = ModuleType('junction'); junction.__file__ = str(root / 'junction_module.py'); junction.JunctionModuleHandle = Handle
    modules.update({'addon_utils':addon, '_bpy_internal.extensions.junction_module':junction, 'bl_ext':base})
    assert native._registered_tool_provider('bl_ext', base, modules, (), tool, {})
    assert native._registered_tool_provider('bl_ext.user_default', namespace, modules, (), tool, {})
    assert not native._registered_tool_provider('bl_ext.user_default.arbitrary', namespace, modules, (), tool, {})
    handle.items['user_default'] = ModuleType('replaced')
    assert not native._registered_tool_provider('bl_ext.user_default', namespace, modules, (), tool, {})


def test_multiprocessing_prior_blender_namespace_must_be_exact_inert_default(tmp_path):
    import builtins
    from types import ModuleType
    parent = ModuleType('multiprocessing'); parent.__file__ = str(tmp_path / 'multiprocessing/__init__.py')
    bpy = ModuleType('bpy')
    prior = ModuleType('__main__'); prior.__file__ = '<blender string>'
    prior.__builtins__ = vars(builtins); prior.bpy = bpy
    modules = {'multiprocessing': parent, 'bpy': bpy, '__main__': ModuleType('__main__')}
    tool = lambda value: bool(value) and Path(value).is_relative_to(tmp_path)
    assert native._registered_tool_provider('__mp_main__', prior, modules, (), tool, {})
    prior.extra = lambda: None
    assert not native._registered_tool_provider('__mp_main__', prior, modules, (), tool, {})
    del prior.extra
    prior.bpy = ModuleType('bpy')
    assert not native._registered_tool_provider('__mp_main__', prior, modules, (), tool, {})
    prior.bpy = bpy; prior.__builtins__ = dict(vars(builtins))
    assert not native._registered_tool_provider('__mp_main__', prior, modules, (), tool, {})
