"""The slice budget runner (tools/test/budgets.py): a verdict times the operation itself, not the resource queue, and
a failed run fails the budget."""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('v2_budgets', ROOT / 'tools/test/budgets.py')
budgets = importlib.util.module_from_spec(spec)
sys.modules['v2_budgets'] = budgets
spec.loader.exec_module(budgets)


def run(seconds, queue=0., ok=True):
    return {'ok': ok, 'wall_s': seconds + queue, 'queue_s': queue, 'operation_s': seconds}


def test_median_and_slowest_hold_within_the_targets():
    measured = budgets.summarize('place', [run(s) for s in (28, 29, 31, 30, 55)])
    assert measured['median_s'] == 30 and measured['slowest_s'] == 55 and measured['passed']


def test_queue_wait_is_reported_but_not_counted():
    measured = budgets.summarize('open', [run(60, queue=300) for _ in range(5)])
    assert measured['median_s'] == 60 and measured['queue_s'] == 1500 and measured['passed']


def test_a_slow_outlier_fails_the_slowest_target():
    assert not budgets.summarize('place', [run(s) for s in (28, 29, 30, 30, 61)])['passed']


def test_a_failed_run_fails_the_budget():
    measured = budgets.summarize('check', [run(3), run(3), run(3, ok=False)])
    assert measured['failed'] == 1 and not measured['passed']


def test_only_a_compile_of_the_edited_file_counts():
    built = '[2/4] Compile [Apple] YorimichiLive.cpp\n[3/4] Link [Apple] UnrealEditor-Yorimichi.dylib\n'
    assert budgets.compiled(built, 'YorimichiLive.cpp')
    assert not budgets.compiled('unreal.compile                     up to date\n', 'YorimichiLive.cpp')
    assert not budgets.compiled('[1/2] Compile [Apple] JapanWorld.cpp\n', 'YorimichiLive.cpp')


def test_a_game_that_does_not_quit_stops_the_series_and_restores_the_edit(tmp_path, monkeypatch):
    source = tmp_path / 'Edited.cpp'
    source.write_bytes(b'int x;\n')
    calls = []

    def run_once(operation, index, args, log):
        calls.append(index)
        args.edit.write_bytes(args.original + b'// budget run\n')
        if index == 1:
            raise budgets.CleanupError('the game did not quit')
        return {'run': index, 'ok': True, 'wall_s': 1., 'queue_s': 0., 'operation_s': 1.}

    monkeypatch.setattr(budgets, 'run_once', run_once)
    monkeypatch.setattr(budgets, 'git', lambda *a: 'abc\n')
    assert budgets.main(['cpp', '--edit', str(source), '--out', str(tmp_path / 'out')]) == 2
    assert calls == [0, 1]                                              # no run after the failed cleanup
    assert source.read_bytes() == b'int x;\n'
    receipt = (tmp_path / 'out/cpp.json').read_text()
    assert '"stopped"' in receipt and '"passed": false' in receipt
