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
    helper = tmp_path / 'selected_helper.py'
    helper.write_text('selected = 1\n')
    names = {'producer.py', 'selected_helper.py', *native._WORKER}
    for name in native._WORKER:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('pass\n')
    step = build.Step('fixed-native-member', [build.Blender(script, threads=3, factory_startup=True)],
                      products=[build.Product('result', (tmp_path / 'result',))], cache=True, heavy=True)
    assert native.captured_native_inputs(step) == ()
    monkeypatch.setattr(build_cache, 'tool_context', lambda *a, **k: {'checked': 'fixture-tool-context'})
    runtime = native._bind_native_runtime(step, checkout=tmp_path, issuer_files=sorted(names), code_inputs=(helper,))
    assert set(runtime.files) == names - {'platform/studio/atelier/build_batch_worker.py'}
    assert not any(name.endswith(('build_audit_worker.py', 'legacy_bootstrap.py')) for name in runtime.files)
    assert set(native.captured_native_inputs(step)) <= set(build.required_inputs(step))
    first = build.fingerprint(step, {})
    helper.write_text('selected = 2\n')
    assert build.fingerprint(step, {}) != first
    first = build.fingerprint(step, {})
    (tmp_path / 'platform/studio/atelier/build_v2/legacy_native_action.py').write_text('value = 2\n')
    assert build.fingerprint(step, {}) != first
    step._captured_native_runtime = SimpleNamespace(files=runtime.files)
    with pytest.raises(ValueError, match='unqualified'):
        build.required_inputs(step)


@pytest.mark.parametrize('standalone', [False, True])
@pytest.mark.parametrize('original,expected', [(0., 600.), (300., 300.), (900., 600.)])
def test_native_shared_intent_precedes_files_and_uses_one_recorded_bound(tmp_path, monkeypatch, original, expected, standalone):
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
                        metadata_scopes={'control.scheduler': ['state'], 'control.scheduler.logs': ['logs'],
                                         'control.scheduler.stamps': ['stamps'], 'control.scheduler.journal': ['journal']},
                        custody={'build': 10, 'content': 11, 'writer': 12}, client=Client(),
                        manifest={'distribution': str(tmp_path / 'distribution'), 'source_digest': 'b' * 64,
                                  'issuer_digest': 'c' * 64, 'scheduler_request': {'digest': 'd' * 64},
                                  'work_deadline_ns': 5000 * 1_000_000_000},
                        files=[('platform/studio/atelier/build_v2/controller_client.py', b'pinned')])
    step = build.Step('actual-qualified-member', [])
    session = SimpleNamespace(candidates=[(step, 'e' * 64, {})], nonce='f' * 32,
                              guard=tmp_path / 'original-stable-batch.guard',
                              folder=tmp_path / '.state/batches'/('f' * 32))
    runtime = native._NativeRuntime(tmp_path, native._WORKER, native._ORIGIN)
    from atelier.build_v2.legacy_native_launch import NativeBatchLaunch
    launch = NativeBatchLaunch(a, session, {step.name: runtime})
    command = build.Blender(paths.STUDIO / 'atelier/build_batch_worker.py', threads=3,
                            factory_startup=True, env=(('ATELIER_BATCH', str(tmp_path / '.state/batches/f')),
                                                      ('PYTHONHASHSEED', '0')))
    command.timeout = original
    ctx = SimpleNamespace(blender=str(bundle / 'MacOS/Blender'))
    if standalone:
        from atelier.build_v2.legacy_native_launch import NativeSingleLaunch
        command = build.Blender(tmp_path / 'producer.py', args=('--recolour', '/owned/output'),
                                threads=3, factory_startup=True)
        command.timeout = original
        step.commands = [command]
        runtime = native._NativeRuntime(tmp_path, ('producer.py', *native._ACTION_WORKER), native._ORIGIN)
        ctx.out, ctx.logs = tmp_path / 'output', tmp_path / 'output/logs'
        launch = NativeSingleLaunch(a, ctx, step, command, runtime)
        assert not hasattr(launch, 'session')
    with launch.prepared(ctx, command) as (argv, environment, descriptors):
        assert descriptors == ()  # Checkout locks go to monitor custody, NEVER worker pass_fds.
        assert len(calls) == 1 and calls[0]['attempt']['members'] == [*a.metadata_scopes, step.name]
        intent = calls[0]['attempt']['execution']['launch']
        assert intent['execution_ns'] == int(expected * 1e9) and launch.work_seconds == expected
        assert intent['threads'] == 3 and intent['memory_bytes'] == 10 * 1024**3
        assert (intent['program'], intent['args']) == (argv[0], argv[1:])
        assert os.stat(launch.context).st_mode & 0o777 == 0o600
        assert hashlib.sha256(launch.context.read_bytes()).hexdigest() in argv[8]
        assert standalone or session.guard == launch.directory
        options = launch.guard_options(argv, dict(environment), 'job')
        assert options['logical_folder'] == (ctx.logs / (step.name + '.guard') if standalone
                                              else tmp_path / 'original-stable-batch.guard')
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


def test_native_core_registration_rejects_spelling_only_replacement(tmp_path):
    from types import ModuleType
    bpy = ModuleType('bpy'); bpy.__file__ = str(tmp_path / 'bpy/__init__.py')
    binding = ModuleType('_bpy')
    for key in ('app', 'props', 'types', 'data', 'context', 'msgbus'):
        value = ModuleType('bpy.' + key)
        setattr(bpy, key, value); setattr(binding, key, value)
    modules = {'bpy':bpy, '_bpy':binding}
    tool = lambda value: bool(value) and Path(value).is_relative_to(tmp_path)
    assert native._registered_tool_provider('bpy.app', bpy.app, modules, (), tool, {})
    forged = ModuleType('bpy.app'); forged.callback = lambda: None
    assert not native._registered_tool_provider('bpy.app', forged, modules, (), tool, {})
    modules['_bpy'] = ModuleType('_bpy')
    assert not native._registered_tool_provider('_bpy', modules['_bpy'], modules, (), tool, {})


def test_unknown_tool_local_namespace_with_callback_is_not_native_provider(tmp_path):
    from types import ModuleType
    from importlib.machinery import ModuleSpec
    module = ModuleType('unknown_namespace')
    module.__spec__ = ModuleSpec(module.__name__, loader=None, is_package=True)
    module.__spec__.submodule_search_locations = [str(tmp_path)]
    module.callback = lambda: None
    assert not native._registered_tool_provider(module.__name__, module, {}, (), lambda value: True, {})


def test_actual_preload_gate_refuses_forged_namespace_code(tmp_path, monkeypatch, capsys):
    import json
    import sys
    from types import ModuleType
    from importlib.machinery import ModuleSpec
    module = ModuleType('forged_namespace')
    module.__spec__ = ModuleSpec(module.__name__, loader=None, is_package=True)
    module.__spec__.submodule_search_locations = [str(tmp_path / 'Contents')]
    module.callback = lambda: None
    monkeypatch.setattr(sys, 'modules', {module.__name__:module, **sys.modules})
    monkeypatch.setattr(sys, 'argv', ['blender', '--python-expr', 'pass'])
    caller = SimpleNamespace(f_code=compile('pass', '<string>', 'exec'), f_globals=vars(sys.modules['__main__']))
    with pytest.raises(ValueError, match='unclassified preloaded providers'):
        native._preloaded({'distribution': str(tmp_path / 'distribution')}, [tmp_path / 'Contents'], caller)
    record = json.loads(capsys.readouterr().err.split('native_preload_unclassified ', 1)[1].splitlines()[0])
    assert any(row['name'] == 'forged_namespace' for row in record['modules'])


def test_selected_callback_helpers_use_existing_key_without_native_or_python_worker(tmp_path, monkeypatch):
    from atelier.build_v2.legacy_call import bind_captured_call
    from atelier.build_v2.legacy_qualification import UnsupportedOrigin
    owner = tmp_path / 'callback.py'; helper = tmp_path / 'helper.py'
    owner.write_text('def run(ctx, log): return None\n'); helper.write_text('setting = 1\n')
    step = build.Step('exact-callback', [build.Call('discover fixed', lambda ctx, log: None)], inputs=[owner])
    original = build.fingerprint(step, {})
    bind_captured_call(step, checkout=tmp_path, issuer_files=['callback.py','helper.py'], code_inputs=[owner,helper])
    assert set(build.required_inputs(step)) == {owner,helper}
    first = build.fingerprint(step, {})
    assert first != original
    helper.write_text('setting = 2\n')
    assert build.fingerprint(step, {}) != first
    step._captured_call_runtime = SimpleNamespace(files=(helper,))
    with pytest.raises(UnsupportedOrigin, match='fixed issuer'):
        build.required_inputs(step)


def test_native_future_executable_scope_rejects_external_and_forged_tool_code_stickily(tmp_path):
    from atelier.build_v2.legacy_qualification import CapturedCode, UnsupportedOrigin
    root = tmp_path / 'checkout'; tool = tmp_path / 'Contents'; root.mkdir(); tool.mkdir()
    source = CapturedCode(str(root / 'owner.py'), b'value = 1\n')
    provider = tool / 'provider.py'; provider.write_text('value = 2\n')
    check = native._native_execution_check([source], checkout=root, installation=[tool])
    check('exec', (source.compiled(),))
    check('exec', (compile(provider.read_bytes(), str(provider), 'exec', dont_inherit=True),))
    for code in (compile('value = 3', '/external/extension.py', 'exec'),
                 compile('value = 3', str(provider), 'exec'), compile('value = 3', '<string>', 'exec')):
        with pytest.raises(UnsupportedOrigin):
            check('exec', (code,))
    with pytest.raises(UnsupportedOrigin, match='sticky'):
        check.require_clean()
    with pytest.raises(UnsupportedOrigin):
        check('import', ('external_native', '/external/provider.so'))


def test_native_anonymous_templates_require_actual_installed_caller_code(tmp_path):
    from atelier.build_v2.legacy_qualification import UnsupportedOrigin
    tool = tmp_path / 'Contents'; tool.mkdir()
    path = tool / 'provider.py'
    raw = b'def call(check, code):\n    check("exec", (code,))\n'
    path.write_bytes(raw)
    namespace = {}; exec(compile(raw, str(path), 'exec', dont_inherit=True), namespace)
    check = native._native_execution_check([], checkout=tmp_path / 'checkout', installation=[tool])
    with pytest.raises(UnsupportedOrigin):
        namespace['call'](check, compile('value = 1', '<string>', 'exec'))
    # A producer cannot gain the same permission by using an installed filename.
    forged = {}; exec(compile('def call(check, code):\n check("exec", (code,))\n', str(path), 'exec'), forged)
    with pytest.raises(UnsupportedOrigin):
        forged['call'](check, compile('value = 2', '<string>', 'exec'))


def test_exact_installed_namespace_is_inert_and_parent_bound(tmp_path, monkeypatch):
    from types import ModuleType
    from importlib.machinery import NamespaceLoader, ModuleSpec
    scripts = tmp_path / 'Contents/Resources/5.2/scripts'
    bpy = ModuleType('bpy'); bpy.__file__ = str(scripts / 'modules/bpy/__init__.py')
    name = 'bl_operators.node_editor'; path = scripts / 'startup/bl_operators/node_editor'
    import sys
    parent = ModuleType('bl_operators'); parent.__path__ = [str(path.parent)]
    monkeypatch.setitem(sys.modules, 'bl_operators', parent)
    module = ModuleType(name); loader = NamespaceLoader(name, [str(path)], lambda *a: None)
    module.__loader__ = loader; module.__package__ = name; module.__file__ = None; module.__path__ = [str(path)]
    module.__spec__ = ModuleSpec(name, loader, is_package=True); module.__spec__.submodule_search_locations = module.__path__
    parent.node_editor = module
    modules = {'bpy':bpy, 'bl_operators':parent, name:module}
    tool = lambda value: bool(value) and Path(value).is_relative_to(tmp_path / 'Contents')
    assert native._registered_tool_provider(name, module, modules, (), tool, {})
    module.callback = lambda: None
    assert not native._registered_tool_provider(name, module, modules, (), tool, {})
    del module.callback
    module.__path__ = [str(tmp_path / 'external')]
    assert not native._registered_tool_provider(name, module, modules, (), tool, {})


def test_native_factory_templates_require_exact_embedded_literal_and_captured_caller(tmp_path):
    from atelier.build_v2.legacy_qualification import CapturedCode, UnsupportedOrigin
    tool = tmp_path / 'Contents'; (tool/'MacOS').mkdir(parents=True)
    texts = (('addon_utils.disable_all()', 'eval'), ('bl_app_template_utils.reset()', 'eval'),
             ('bpy.utils.refresh_script_paths()\naddon_utils.reset_all()', 'exec'))
    (tool/'MacOS/Blender').write_bytes(b'fixture-binary\0' + b'\0'.join(text.encode() for text, _ in texts) + b'\0')
    owner = CapturedCode(str(tmp_path/'checkout/owner.py'), b'def call(check, code):\n    check("exec", (code,))\n')
    namespace = {}; exec(owner.compiled(), namespace)
    check = native._native_execution_check([owner], checkout=tmp_path/'checkout', installation=[tool])
    for text, mode in texts:
        namespace['call'](check, compile(text, '<string>', mode, dont_inherit=True))
    check.require_clean()
    with pytest.raises(UnsupportedOrigin):
        namespace['call'](check, compile('addon_utils.unknown()', '<string>', 'eval'))
    (tool/'MacOS/Blender').write_bytes(b'unrelated fixed image')
    refused = native._native_execution_check([owner], checkout=tmp_path/'checkout', installation=[tool])
    with pytest.raises(UnsupportedOrigin):
        namespace['call'](refused, compile(texts[0][0], '<string>', 'eval'))


def test_embedded_native_audit_refusal_cannot_be_swallowed_as_normal_exit(monkeypatch, capsys):
    import os
    class OwnedExit(BaseException): pass
    exits = []
    def exit_(code):
        exits.append(code)
        raise OwnedExit()
    monkeypatch.setattr(os, '_exit', exit_)
    def check(event, args): raise ValueError('refused provider')
    observed = native._fatal_native_audit(check)
    with pytest.raises(OwnedExit):
        observed('exec', ())
    assert exits == [1]
    assert capsys.readouterr().err == 'native source-origin refusal: ValueError\n'


def test_installed_namedtuple_template_checks_full_caller_fields_and_tuple_namespace():
    import collections
    source = Path(collections.__file__).read_bytes()
    compilation = compile(source, collections.namedtuple.__code__.co_filename, 'exec', dont_inherit=True)
    fields = ('module_finder', 'name', 'ispkg')
    namespace = {'_tuple_new':tuple.__new__, '__builtins__':{}, '__name__':'namedtuple_ModuleInfo'}
    caller = SimpleNamespace(f_code=collections.namedtuple.__code__,
                             f_locals={'typename':'ModuleInfo','field_names':fields,'namespace':namespace})
    code = compile('lambda _cls, module_finder, name, ispkg: _tuple_new(_cls, (module_finder, name, ispkg))', '<string>', 'eval')
    assert native._checked_namedtuple(code, caller, compilation)
    namespace['_tuple_new'] = lambda *a: None
    assert not native._checked_namedtuple(code, caller, compilation)
    namespace['_tuple_new'] = tuple.__new__
    caller.f_locals['field_names'] = ('name', 'name')
    assert not native._checked_namedtuple(code, caller, compilation)
    caller.f_locals['field_names'] = ('name;import_os',)
    assert not native._checked_namedtuple(code, caller, compilation)
    caller.f_locals['field_names'] = fields
    assert not native._checked_namedtuple(compile('lambda: __import__("os")','<string>','eval'), caller, compilation)


def test_typing_eval_is_backed_by_installed_cycles_annotation_and_checked_callbacks(tmp_path, monkeypatch):
    import builtins, sys, types, typing
    from atelier.build_v2.legacy_qualification import UnsupportedOrigin
    path = tmp_path/'Contents/Resources/5.2/scripts/addons_core/cycles/properties.py'
    path.parent.mkdir(parents=True)
    raw = b"from __future__ import annotations\ndef update_render_passes(): pass\nclass Settings:\n    value: EnumProperty(name='Mode', translation_context=i18n_contexts.id_light, update=update_render_passes)\n"
    path.write_bytes(raw)
    module = types.ModuleType('cycles.properties'); module.__file__ = str(path); module.EnumProperty = len
    module.i18n_contexts = types.SimpleNamespace(id_light='Light')
    exec(compile(raw, str(path), 'exec', dont_inherit=True), vars(module))
    monkeypatch.setitem(sys.modules, 'cycles.properties', module)
    props = types.SimpleNamespace(EnumProperty=len)
    app = types.SimpleNamespace(translations=types.SimpleNamespace(contexts=module.i18n_contexts))
    core = types.SimpleNamespace(bpy_struct=object)
    bpy = types.SimpleNamespace(props=props, app=app, types=core, __file__=str(tmp_path/'Contents/Resources/5.2/scripts/modules/bpy/__init__.py'))
    monkeypatch.setitem(sys.modules, 'bpy', bpy)
    monkeypatch.setitem(sys.modules, '_bpy', types.SimpleNamespace(props=props, app=app, types=core))
    original = builtins.eval
    def hints():
        check = native._native_execution_check([], checkout=tmp_path/'checkout',
                    installation=[tmp_path/'Contents', Path(typing.__file__).resolve().parent])
        observed = []
        def evaluated(code, globalns=None, localns=None):
            if type(code) is types.CodeType and code.co_filename == '<string>':
                check('exec', (code,)); observed.append(True)
                return int  # Observation fixture never calls the fake property/callback.
            return original(code, globalns, localns)
        check.wrapper_code = evaluated.__code__  # Same exact-code skip as production audit wrapper.
        with monkeypatch.context() as patch:
            patch.setattr(builtins, 'eval', evaluated)
            result = typing.get_type_hints(module.Settings)
        check.require_clean()
        assert observed == [True]
        return result
    assert hints() == {'value':int}
    module.i18n_contexts.id_light = 'Foreign'
    with pytest.raises(UnsupportedOrigin): hints()
    module.i18n_contexts.id_light = 'Light'
    module.Settings.__annotations__['value'] = "EnumProperty(name='Foreign', translation_context=i18n_contexts.id_light, update=update_render_passes)"
    with pytest.raises(UnsupportedOrigin): hints()
    module.Settings.__annotations__['value'] = "EnumProperty(name='Mode', translation_context=i18n_contexts.id_light, update=update_render_passes)"
    module.update_render_passes = lambda: None
    with pytest.raises(UnsupportedOrigin): hints()


def test_installed_dataclass_wrapper_binds_static_class_and_whole_generator(tmp_path, monkeypatch):
    import sys
    from types import ModuleType
    from atelier.build_v2.legacy_qualification import UnsupportedOrigin
    tool = tmp_path / 'tool'; tool.mkdir()
    dc_path = tool / 'dataclasses.py'
    dc_raw = '''class _FuncBuilder:
 def __init__(self, globals):
  self.names=['__init__']; self.src=[' def __init__(self):\\n  pass']; self.globals=globals
  self.locals={}; self.overwrite_errors={}; self.unconditional_adds={}
 def add_fns_to_class(self, cls):
  txt='def __create_fn__():\\n'+'\\n'.join(self.src)+'\\n return ('+','.join(self.names)+',)'
  code=compile(txt,'<string>','exec',dont_inherit=True)
  check('exec',(code,))
def _process_class(cls):
 func_builder=_FuncBuilder(vars(sys.modules[cls.__module__]))
 func_builder.add_fns_to_class(cls)
 return cls
def dataclass(cls):
 def wrap(cls): return _process_class(cls)
 return wrap(cls)
'''
    dc_path.write_text(dc_raw)
    dc = ModuleType('dataclasses'); dc.__dict__['sys'] = sys
    monkeypatch.setitem(sys.modules, 'dataclasses', dc)
    exec(compile(dc_raw, str(dc_path), 'exec', dont_inherit=True), vars(dc))
    sdk_path = tool / 'sdk.py'
    sdk_raw = 'from dataclasses import dataclass\n@dataclass\nclass Actual:\n value: str\n'
    sdk_path.write_text(sdk_raw)
    sdk = ModuleType('sdk'); monkeypatch.setitem(sys.modules, 'sdk', sdk)
    check = native._native_execution_check([], checkout=tmp_path/'checkout', installation=[tool])
    dc.check = check
    exec(compile(sdk_raw, str(sdk_path), 'exec', dont_inherit=True), vars(sdk))
    check.require_clean()
    # A genuine builder and matching anonymous wrapper outside the live source
    # decoration stack still cannot mint execution permission.
    with pytest.raises(UnsupportedOrigin):
        dc._FuncBuilder(vars(sdk)).add_fns_to_class(sdk.Actual)
    forged = ModuleType('sdk'); monkeypatch.setitem(sys.modules, 'sdk', forged)
    with pytest.raises(UnsupportedOrigin):
        exec(compile(sdk_raw+'\npoison=True\n', str(sdk_path), 'exec', dont_inherit=True), vars(forged))


def test_standalone_original_argv_preserves_arguments_without_batch_worker(tmp_path):
    script = tmp_path / 'producer.py'
    command = build.Blender(script, args=('--recolour', '/owned/output'), threads=3, factory_startup=True)
    runtime = native._NativeRuntime(tmp_path, ('producer.py', *native._ACTION_WORKER), native._ORIGIN)
    argv = native.action_argv(command, SimpleNamespace(blender='pinned-blender'), runtime=runtime,
        startup=Path('/owned/startup'), specification=Path('/owned/spec'),
        specification_digest='a' * 64, capture_file=Path('/owned/capture'), capture_digest='b' * 64)
    assert argv[:7] == command.argv(SimpleNamespace(blender='pinned-blender'))[:7]
    assert argv[7] == '--python-expr' and argv[-3:] == ['--', '--recolour', '/owned/output']
    assert not any(name.endswith('/build_batch_worker.py') for name in runtime.files)
    with pytest.raises(ValueError, match='selected captured runtime'):
        native.action_argv(build.Blender(tmp_path / 'unknown.py'), SimpleNamespace(blender='pinned'),
            runtime=runtime, startup=Path('/s'), specification=Path('/r'),
            specification_digest='a' * 64, capture_file=Path('/c'), capture_digest='b' * 64)


@pytest.mark.parametrize('fault', ['foreign', 'link', 'duplicate', 'relative', 'not-python'])
def test_native_extra_selected_code_refuses_unknown_or_aliased_roles(tmp_path, fault):
    script = tmp_path / 'producer.py'; script.write_text('pass\n')
    helper = tmp_path / 'selected.py'; helper.write_text('selected = 1\n')
    names = {'producer.py', 'selected.py', *native._WORKER}
    for name in native._WORKER:
        path = tmp_path / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text('pass\n')
    step = build.Step('fixed-native', [build.Blender(script, threads=3, factory_startup=True)])
    roles = (helper,)
    if fault == 'foreign':
        names.remove('selected.py')
    elif fault == 'link':
        helper.unlink(); helper.symlink_to(script)
    elif fault == 'duplicate':
        roles = (helper, helper)
    elif fault == 'relative':
        roles = (Path('selected.py'),)
    else:
        roles = (tmp_path / 'selected.json',)
    with pytest.raises((OSError, ValueError)):
        native._bind_native_runtime(step, checkout=tmp_path, issuer_files=sorted(names), code_inputs=roles)
    assert native.captured_native_inputs(step) == ()
