"""The uneven-ground drive steers on the grass at a controlled speed.

The old run held a full right steer from t = 4.0 s at about 46 kph and crossed the waterfront bank, so the ride
gates measured the bank descent. This drains the real scenario with fake live modules and checks the steering input
happens early, on the uneven patch, at about 18 kph, and that the ride gates still report their unchanged names.
"""
import importlib.util
import json
import sys
import types
from pathlib import Path

SCENARIO = Path(__file__).resolve().parents[1] / 'scenarios' / 'kart_uneven.py'
ROOT = str(Path(__file__).resolve().parents[3])


class Vec:
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.x, self.y, self.z = float(x), float(y), float(z)


class FakeL:
    def __init__(self, live):
        self.live = live

    def car_state(self):
        if not self.live.driving:
            return 'driving=0 speed=0 kph=0.0 yaw=0.0 car=(0,0,0)'
        speed = min(46.0, max(0.0, 15.0 * (self.live.now - 1.3)))
        return 'driving=1 speed=%.2f kph=%.1f yaw=%.3f car=(0,0,0)' % (speed / 3.6, speed, self.live.yaw)

    def car_ride(self):
        return 'y=0.00 vy=0.00 pitch=0.00 roll=0.00 wheels=0/1,1/1,2/1,3/1'

    def input_key(self, key, event, value):
        self.live.keys.append((key, event, value))
        if key == 'A':
            self.live.steering = event == 'press'

    def fixed_step(self, value):
        self.live.steps.append(value)

    def screenshot(self, path):
        self.live.shots.append(path)

    def ground_at(self, point):
        return point

    def teleport_player(self, at, yaw):
        self.live.teleported = True

    def game_world(self):
        return object()


class FakeLive(types.ModuleType):
    def __init__(self):
        super().__init__('live')
        self.ROOT = ROOT
        self.L = FakeL(self)
        self.driving = False
        self.steering = False
        self.yaw = 0.0
        self.now = 0.0
        self.keys, self.steps, self.shots = [], [], []
        self.teleported = False
        self.stopped = False

    def press(self, button):
        if button == 'car':
            self.driving = not self.driving

    def behave(self, name, fn):
        pass

    def stop(self, name=None):
        self.stopped = True

    def drive(self, forward, right):
        pass


def load(tmp_path, monkeypatch):
    monkeypatch.setenv('ATELIER_BUILD_ROOT', str(tmp_path))
    unreal = types.ModuleType('unreal')
    unreal.Vector = Vec
    unreal.MegaParkValidation = types.SimpleNamespace(restore_player_camera=lambda: None)
    unreal.log = lambda message: None
    unreal.log_error = lambda message: None
    live = FakeLive()
    monkeypatch.setitem(sys.modules, 'unreal', unreal)
    monkeypatch.setitem(sys.modules, 'live', live)
    spec = importlib.util.spec_from_file_location('kart_uneven_scenario', SCENARIO)
    module = importlib.util.module_from_spec(spec)
    module.live, module.unreal = live, unreal
    spec.loader.exec_module(module)
    return module, live


def run_to_end(module, live):
    dt = 1.0 / 60.0
    for _ in range(1200):
        live.now = module.st['t']
        if live.steering:
            live.yaw += 60.0 * dt
        module.run(dt)
        if live.stopped:
            break
    assert live.stopped


def test_steers_early_on_the_grass_at_a_controlled_speed(tmp_path, monkeypatch):
    module, live = load(tmp_path, monkeypatch)
    run_to_end(module, live)
    presses = [entry for entry in live.keys if entry[0] == 'A']
    assert presses and presses[0][1] == 'press' and presses[-1][1] == 'release'
    assert not [entry for entry in live.keys if entry[0] == 'D' and entry[1] == 'press']   # the old hard right is gone
    assert module.st['steer_speed'] >= module.STEER_KPH
    assert module.st['steer_speed'] < 25.0
    assert 2.4 <= module.st['steer_t0'] < 2.8
    report = json.loads(Path(module.REPORT).read_text())
    assert report['ok'] and report['status'] == 'passed'
    assert 18.0 <= report['speed_at_steer_kph'] < 25.0
    assert 15.0 < report['steer_rms_deg_s'] < 300.0
    assert {'rms_accel', 'peak_accel', 'contact_lost_percent'} <= set(report)
