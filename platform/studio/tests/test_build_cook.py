"""Cook flag, identity and log boundaries; all native execution is mocked."""
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier import build, build_cook
from atelier.build_cook import CookMode, Observation, Observer

ENABLED = 'LogCook: Display: INCREMENTAL COOK DEPENDENCIES: Enabled. Incremental Cook Dependencies are enabled in Editor.ini:[CookSettings]:LegacyIterative=false.'
INCREMENTAL = 'LogCook: Display: INCREMENTAL COOK: Global settings are still valid. Keeping previously cooked packages for platform Mac and cooking only packages that have been modified.'
FULL = 'LogCook: Display: FULL COOK: -forcerecook=true (or an equivalent) was specified. Deleting previously cooked packages for platform Mac and recooking all packages discovered in the current cook.'
INVALIDATED = 'LogCook: Display: FULL COOK: -cookincremental was specified, but Global settings have changed and all previously cooked packages are invalidated. Deleting previously cooked packages for platform Mac and recooking all packages discovered in the current cook.'
DISABLED = 'LogCook: Display: INCREMENTAL COOK DEPENDENCIES: Disabled. Incremental Cook Dependencies are disabled because the cooker is not using ZenStore, Falling back to legacy iterative cook mode.'
STATS = 'LogCook: Display: Packages Cooked: 2, Packages Incrementally Skipped: 8, Packages Skipped by Platform: 0, Total Packages: 10'
TAIL = ['LogCook: Display: Cook by the book total time in tick 0.300000s total time 1.200000', STATS,
        'Cook command time: 2.00 s', '********** COOK COMMAND COMPLETED **********',
        'Stage command time: 3.00 s', 'Package command time: 4.00 s', 'Archive command time: 1.00 s',
        'BuildCookRun time: 12.00 s', 'BUILD SUCCESSFUL']


FULL_TAIL = [line.replace('Packages Cooked: 2', 'Packages Cooked: 10').replace('Incrementally Skipped: 8', 'Incrementally Skipped: 0') for line in TAIL]


def observed(lines, mode=CookMode.INCREMENTAL):
    observation = Observation(mode)
    for line in lines:
        observation.line(line)
    return observation.report(success=True)


@pytest.fixture
def context(tmp_path, monkeypatch):
    root = tmp_path / 'engine'
    (root / 'Engine/Build').mkdir(parents=True)
    (root / 'Engine/Build/Build.version').write_text(json.dumps(dict(MajorVersion=5, MinorVersion=8)))
    monkeypatch.setenv('UE_HEADLESS_USER_DIR', str(tmp_path / 'headless'))
    return SimpleNamespace(unreal_root=root, uproject=tmp_path / 'Fixture.uproject', game='fixture',
                           logs=tmp_path / 'logs', env=lambda extra: dict(extra), out=tmp_path / 'out')


def test_default_repr_and_fingerprint_match_preexisting_command():
    command = build.UnrealPackage('Fixture', Path('archive'))
    old = "UnrealPackage(target='Fixture', archive=PosixPath('archive'), config='Development', workers=3, marker='BUILD SUCCESSFUL', timeout=14400, watch=('UnrealEditor-Cmd', 'UnrealEditor', 'ShaderCompileWorker', 'dotnet'), progress=25.0)"
    assert repr(command) == old
    class OldCommand:
        def __repr__(self):
            return old
    assert build.fingerprint(build.Step('cook', [command]), {}) == build.fingerprint(build.Step('cook', [OldCommand()]), {})
    identities = [build.fingerprint(build.Step('cook', [build.UnrealPackage('Fixture', Path('archive'), cook_mode=mode)]), {})
                  for mode in CookMode]
    assert len(set(identities)) == 3


@pytest.mark.parametrize('mode', list(CookMode))
def test_fixed_cooker_only_flags_keep_scope_workers_and_deploy(context, mode):
    argv = build.UnrealPackage('Fixture', Path('archive'), cook_mode=mode).argv(context)
    assert '-cookall' in argv and '-ubtargs=-MaxParallelActions=3' in argv
    assert '-iterate' not in argv and '-cookincremental' not in argv and '-iterativedeploy' not in argv
    extra = [value for value in argv if value.startswith('-AdditionalCookerOptions=')]
    expected = [] if mode is CookMode.DEFAULT else [f'-AdditionalCookerOptions={"-fullcook" if mode is CookMode.FULL else "-cookincremental"} -Cook.DependencyTracking=1']
    assert extra == expected
    assert all(flag in argv for flag in ('-stage', '-pak', '-package', '-archive', '-build'))


def test_unsupported_engine_refuses_experiment_but_preserves_default(context):
    (context.unreal_root / 'Engine/Build/Build.version').write_text('{"MajorVersion":5,"MinorVersion":7}')
    with pytest.raises(ValueError, match='UE 5.8'):
        build.UnrealPackage('Fixture', Path('archive'), cook_mode=CookMode.INCREMENTAL).argv(context)
    assert '-cookall' in build.UnrealPackage('Fixture', Path('archive')).argv(context)


def test_modern_reuse_is_distinct_from_legitimate_full_invalidation():
    report = observed([ENABLED, INCREMENTAL, *TAIL])
    assert report['validated'] and report['reuse_observed'] is True and report['modern_dependencies'] is True
    assert report['uat_seconds']['cook'] == 2 and report['uat_seconds']['stage'] == 3
    assert report['cooker_seconds'] == 1.2
    full = observed([ENABLED, INVALIDATED, *FULL_TAIL])
    assert full['validated'] and full['decision'] == dict(mode='full', reason='settings-changed')
    assert full['reuse_observed'] is None
    assert observed([ENABLED, FULL, *FULL_TAIL], CookMode.FULL)['validated']
    assert not observed([ENABLED, FULL, *FULL_TAIL])['validated']


@pytest.mark.parametrize('damage', ['disabled', 'missing', 'duplicate', 'truncated', 'malformed', 'legacy', 'tracking-zero'])
def test_incomplete_legacy_ambiguous_or_malformed_evidence_never_validates(damage):
    lines = [ENABLED, INCREMENTAL, *TAIL]
    if damage == 'disabled':
        lines[0] = DISABLED
    elif damage == 'missing':
        lines.pop(0)
    elif damage == 'duplicate':
        lines += ['Cook command time: 2.00 s']
    elif damage == 'truncated':
        lines.remove('********** COOK COMMAND COMPLETED **********')
    elif damage == 'malformed':
        lines[2] = 'LogCook: Display: Cook by the book total time in tick invalid'
    elif damage == 'legacy':
        lines[1] = INCREMENTAL.replace('Global', '-legacyiterative was specified and global')
    else:
        lines[1] = 'LogCook: Display: FULL COOK: -cookincremental was specified, but -Cook.DependencyTracking=0 was present on commandline and so cookincremental is not supported.'
    assert not observed(lines)['validated']


def test_unknown_skip_count_is_not_zero_and_nested_pak_time_is_not_added():
    lines = [ENABLED, INCREMENTAL, *TAIL]
    lines[3] = STATS.replace(' Packages Incrementally Skipped: 8,', '')
    report = observed([*lines, 'Took 2.00s to run UnrealPak, ExitCode=0'])
    assert report['validated'] and report['counts']['incrementally_skipped'] is None
    assert report['reuse_observed'] is None and report['uat_seconds']['stage'] == 3
    zero = observed([ENABLED, INCREMENTAL, *[line.replace('Incrementally Skipped: 8', 'Incrementally Skipped: 0') for line in TAIL]])
    assert zero['counts']['incrementally_skipped'] == 0 and zero['reuse_observed'] is False


@pytest.mark.parametrize('damage', ['replacement', 'truncate', 'rewrite', 'partial-line'])
def test_streaming_observer_refuses_changed_or_truncated_logs(tmp_path, damage):
    path = tmp_path / 'stdout.log'
    original = '\n'.join([ENABLED, INCREMENTAL, *TAIL]) + '\n'
    path.write_text(original)
    observer = Observer(tmp_path, CookMode.INCREMENTAL)
    observer.poll(123)
    if damage == 'replacement':
        path.unlink(); path.write_text(original)
    elif damage == 'truncate':
        path.write_text('short\n')
    elif damage == 'rewrite':
        path.write_text(original.replace('2.00 s', '9.00 s'))
    else:
        with path.open('a') as stream:
            stream.write('partial')
    with pytest.raises(RuntimeError):
        observer.finish(success=True)
    assert not json.loads((tmp_path / 'cook-observation.json').read_text())['validated']


def test_streaming_read_budget_and_early_fallback_refusal(tmp_path, monkeypatch):
    path = tmp_path / 'stdout.log'
    path.write_text('\n'.join([ENABLED, INCREMENTAL, *TAIL]) + '\n')
    monkeypatch.setattr(build_cook, 'POLL_BYTES', 64)
    observer = Observer(tmp_path, CookMode.INCREMENTAL)
    observer.poll(123)
    assert observer.offset == 64
    assert observer.finish(success=True)['validated']
    path.write_text(DISABLED + '\n')
    observer = Observer(tmp_path, CookMode.INCREMENTAL)
    with pytest.raises(RuntimeError, match='refused'):
        while True:
            observer.poll(456)
    observer.finish(success=False)


@pytest.mark.parametrize('fallback', [False, True])
def test_existing_guard_lifecycle_validates_before_following_certification(context, monkeypatch, fallback):
    command = build.UnrealPackage('Fixture', Path('archive'), cook_mode=CookMode.INCREMENTAL)
    step = build.Step('unreal.cook', [command], heavy=True)
    calls = []
    def guard(argv, folder, **kwargs):
        calls.append(kwargs)
        folder.mkdir(parents=True)
        (folder / 'stdout.log').write_text('\n'.join([DISABLED if fallback else ENABLED, INCREMENTAL, *TAIL]) + '\n')
        kwargs['on_slot']('big', '')
        kwargs['on_poll'](123)
        return 0
    monkeypatch.setattr(build.guarded, 'run', guard)
    if fallback:
        with pytest.raises(RuntimeError, match='refused'):
            build.run_command(context, step, command, io.StringIO())
    else:
        phases = build.run_command(context, step, command, io.StringIO())
        assert phases['cook']['validated']
    assert len(calls) == 1 and calls[0]['kind'] == 'compile'
    assert calls[0]['watch'] == command.watch and calls[0]['timeout'] == command.timeout


def test_mode_survives_every_recipe_reload_without_affecting_other_commands(tmp_path, monkeypatch):
    recipe = tmp_path / 'build.py'
    recipe.write_text("from pathlib import Path\nfrom atelier.build import Step, Python, UnrealPackage\ndef steps(ctx):\n return [Step('source', [Python(Path('source.py'))]), Step('unreal.cook', [UnrealPackage('Fixture', Path('archive'))], heavy=True)]\n")
    monkeypatch.setattr(build.paths, 'game_dir', lambda _: tmp_path)
    ctx = SimpleNamespace(cook_mode=CookMode.INCREMENTAL)
    first = build.load_recipe('fixture').steps(ctx)
    fresh = build.load_recipe('fixture').steps(ctx)
    assert first[1].commands[0].cook_mode is CookMode.INCREMENTAL
    assert build.fingerprint(first[1], {}) == build.fingerprint(fresh[1], {})
    assert repr(first[0].commands) == repr(build.load_recipe('fixture').steps(SimpleNamespace())[0].commands)
    with pytest.raises(SystemExit, match='selected package'):
        build_cook.validate_selection(ctx, [first[0]])


def test_experimental_force_keeps_current_prerequisites_and_reason_out_of_key(context, tmp_path, monkeypatch):
    from atelier.build_hashes import HashIndex
    context.out.mkdir()
    context.stamps = context.out / 'stamps'
    context.cook_mode = CookMode.INCREMENTAL
    context.cook_reason = 'unchanged warm-state control'
    generated, receipt = context.out / 'generated', context.out / 'cook.json'
    counts = dict(generate=0, cook=0)
    def generate(ctx, log):
        counts['generate'] += 1
        generated.write_text('same')
    def certify(ctx, log):
        receipt.write_text('completed')
    def declarations():
        return [build.Step('generate', [build.Call('generate', generate)], outputs=[generated]),
                build.Step('unreal.cook', [build.UnrealPackage('Fixture', Path('archive'), cook_mode=context.cook_mode),
                                           build.Call('certify', certify)], needs=['generate'], outputs=[receipt], heavy=True)]
    def run(ctx, step, command, log, *args, **kwargs):
        if isinstance(command, build.Call):
            command.fn(ctx, log)
        else:
            counts['cook'] += 1
    monkeypatch.setattr(build, 'run_command', run)
    monkeypatch.setattr(build, 'slot_count', lambda: 1)
    with HashIndex(context.out / 'hash.sqlite3') as index:
        for force in (False, True):
            if force:
                from atelier import build_plan
                report = build_plan.inspect(context, declarations(), ['unreal.cook'], force=True)
                assert report['cook_reason'] == context.cook_reason
                assert report['steps'][0]['status'] == 'current' and 'forced' not in report['steps'][0]['reasons']
                assert report['steps'][1]['status'] == 'run' and 'forced' in report['steps'][1]['reasons']
            assert build._build(context, ['unreal.cook'], force=force, touch=False, echo=lambda *_: None,
                                index=index, steps=declarations()) == 0
        assert counts == dict(generate=1, cook=2)
        before = build.fingerprint(declarations()[1], {'generate': 'key'})
        context.cook_reason = 'different label, identical inputs'
        assert before == build.fingerprint(declarations()[1], {'generate': 'key'})
        context.cook_mode = CookMode.DEFAULT
        assert build._build(context, ['unreal.cook'], force=True, touch=False, echo=lambda *_: None,
                            index=index, steps=declarations()) == 0
        assert counts == dict(generate=2, cook=3)


@pytest.mark.parametrize('replacement', ['Packages Cooked: nope', 'Packages Cooked: 20, Packages Incrementally Skipped: 8, Packages Skipped by Platform: 0, Total Packages: 10'])
def test_malformed_or_inconsistent_counts_remain_unknown(replacement):
    lines = [ENABLED, INCREMENTAL, *TAIL]
    lines[3] = 'LogCook: Display: ' + replacement
    report = observed(lines)
    assert not report['validated'] and report['counts']['cooked'] is None


def test_experiment_cli_is_deliberate_and_reason_never_changes_command_identity():
    from atelier.cli import parse_args
    default = parse_args(['build', 'sandbox', 'unreal.cook'])
    assert default.cook_mode is None and default.cook_reason is None
    experiment = parse_args(['build', 'sandbox', 'unreal.cook', '--cook-mode', 'modern-incremental',
                             '--force', '--cook-reason', 'unchanged control'])
    assert experiment.cook_mode == 'modern-incremental' and experiment.cook_reason == 'unchanged control'
    with pytest.raises(SystemExit):
        parse_args(['build', 'sandbox', '--cook-mode', 'legacy-iterate'])


@pytest.mark.parametrize('planning', [False, True])
@pytest.mark.parametrize('reason', [None, '', '   ', 'multiple\nlines'])
def test_forced_experiment_requires_reason_before_plan_or_execution(context, planning, reason):
    from atelier import build_plan
    context.cook_mode, context.cook_reason = CookMode.INCREMENTAL, reason
    step = build.Step('unreal.cook', [build.UnrealPackage('Fixture', Path('archive'))], heavy=True)
    with pytest.raises(SystemExit, match='--cook-reason'):
        if planning:
            build_plan._inspect(context, [step], ['unreal.cook'], force=True, index=None)
        else:
            build._build(context, ['unreal.cook'], force=True, touch=False, echo=lambda *_: None,
                         index=None, steps=[step])
    assert not context.out.exists()


@pytest.mark.parametrize('fallback', [False, True])
def test_build_never_runs_certifier_or_writes_stamp_after_invalid_modern_cook(context, monkeypatch, fallback):
    from atelier.build_hashes import HashIndex
    context.out.mkdir()
    context.stamps = context.out / 'stamps'
    context.cook_mode, context.cook_reason = CookMode.INCREMENTAL, None
    receipt = context.out / 'cook.json'
    def certify(ctx, log):
        receipt.write_text('certified')
    step = build.Step('unreal.cook', [build.UnrealPackage('Fixture', Path('archive'), cook_mode=CookMode.INCREMENTAL),
                                     build.Call('certify', certify)], heavy=True, outputs=[receipt])
    def guard(argv, folder, **kwargs):
        folder.mkdir(parents=True)
        (folder / 'stdout.log').write_text('\n'.join([DISABLED if fallback else ENABLED, INCREMENTAL, *TAIL]) + '\n')
        kwargs['on_slot']('big', '')
        kwargs['on_poll'](123)
        return 0
    monkeypatch.setattr(build.guarded, 'run', guard)
    monkeypatch.setattr(build, 'slot_count', lambda: 1)
    with HashIndex(context.out / 'hash.sqlite3') as index:
        code = build._build(context, ['unreal.cook'], force=False, touch=False, echo=lambda *_: None,
                            index=index, steps=[step])
    assert code == int(fallback)
    assert receipt.exists() is not fallback
    assert (context.stamps / 'unreal.cook.json').exists() is not fallback


def test_late_previous_registry_failure_is_full_invalidation_not_reuse():
    line = 'LogCook: Error: Could not load PreviousAssetRegistry, which is unexpected when cooking incrementally. Abandoning incremental cook and executing a full cook.'
    report = observed([ENABLED, INCREMENTAL, line, *FULL_TAIL])
    assert report['validated'] and report['decision'] == dict(mode='full', reason='missing-previous-registry')
    assert report['reuse_observed'] is None
    warning = 'LogCook: Warning: Previous cook results returned a record for generator package example, but that package can no longer be found; its generated packages will not be removed from cook results. Run a full cook to remove them.'
    assert not observed([ENABLED, INCREMENTAL, warning, *TAIL])['validated']
