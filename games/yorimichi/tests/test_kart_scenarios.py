"""The kart scenarios' shared cleanup: a failing run must not leave keys, camera or timestep owned."""
import importlib.util
from pathlib import Path

SCENARIOS = Path(__file__).resolve().parents[1] / 'scenarios'
spec = importlib.util.spec_from_file_location('kart_cleanup', SCENARIOS / 'kart_cleanup.py')
cleanup_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cleanup_module)


class FakeL:
    def __init__(self, calls):
        self.calls = calls

    def input_key(self, key, event, value):
        self.calls.append(('key', key, event, value))

    def fixed_step(self, value):
        self.calls.append(('step', value))


class FakeLive:
    def __init__(self):
        self.calls = []
        self.L = FakeL(self.calls)

    def drive(self, forward, right):
        self.calls.append(('drive', forward, right))


def test_cleanup_releases_every_owned_control():
    live = FakeLive()
    cleanup_module.cleanup(live, lambda: live.calls.append(('camera',)))
    released = {call[1] for call in live.calls if call[0] == 'key' and call[2] == 'release'}
    assert released == set(cleanup_module.KEYS)
    assert ('drive', 0.0, 0.0) in live.calls
    assert ('camera',) in live.calls
    assert ('step', 0) in live.calls


def test_cleanup_is_idempotent():
    live = FakeLive()
    cleanup_module.cleanup(live, lambda: live.calls.append(('camera',)))
    cleanup_module.cleanup(live, lambda: live.calls.append(('camera',)))
    assert live.calls.count(('step', 0)) == 2


def test_failed_scenario_still_releases_throttle():
    live = FakeLive()

    def scenario():
        live.L.input_key('W', 'press', 1.0)
        raise RuntimeError('boom')

    try:
        scenario()
    except RuntimeError:
        cleanup_module.cleanup(live, lambda: live.calls.append(('camera',)))
    assert ('key', 'W', 'release', 0.0) in live.calls
    assert ('step', 0) in live.calls


def test_every_kart_scenario_cleans_up_on_both_paths():
    for name in ('kart_equipment.py', 'kart_uneven.py', 'kart_fit.py', 'kart_film.py'):
        source = (SCENARIOS / name).read_text()
        assert source.count('CLEAN.cleanup') >= 2, name

