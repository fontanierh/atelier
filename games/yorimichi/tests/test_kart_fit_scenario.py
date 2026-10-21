"""The fit scenario's queued callbacks keep their own rider, so every character gets a summon flag and shots.

The regression builds the real scenario queue with fake live/unreal modules and drains it: a late-bound loop variable
would give every callback the last rider and skip the others' captures.
"""
import importlib.util
import json
import math
import os
import re
import sys
import types
from pathlib import Path

SCENARIO = Path(__file__).resolve().parents[1] / 'scenarios' / 'kart_fit.py'
ROOT = str(Path(__file__).resolve().parents[3])


class Vector:
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.x, self.y, self.z = float(x), float(y), float(z)

    def __add__(self, other):
        return Vector(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other):
        return Vector(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, other):
        return Vector(self.x * other, self.y * other, self.z * other)

    __rmul__ = __mul__


class Transform:
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.translation = Vector(x, y, z)


class Asset:
    def get_path_name(self):
        return '/Game/Test/SK_Test.SK_Test'


class Skeletal:
    def __init__(self):
        self.visible = False

    def get_name(self):
        return 'CharacterMesh0'

    def is_visible(self):
        return self.visible

    def get_skeletal_mesh_asset(self):
        return Asset()

    def get_socket_transform(self, bone, space):
        return Transform(0.0, 0.0, 100.0)


class Pawn:
    def __init__(self):
        self.skeletal = Skeletal()

    def get_class(self):
        return types.SimpleNamespace(get_name=lambda: 'BP_Test_C')

    def get_components_by_class(self, cls):
        return [self.skeletal]


class FakeUnreal(types.ModuleType):
    def __init__(self):
        super().__init__('unreal')
        self.Vector = Vector
        self.SkeletalMeshComponent = Skeletal
        self.RelativeTransformSpace = types.SimpleNamespace(RTS_WORLD=0)
        self.MegaParkValidation = types.SimpleNamespace(
            review_camera=lambda eye, at, fov: True,
            restore_player_camera=lambda: None)
        self.GameplayStatics = types.SimpleNamespace(get_player_pawn=lambda world, index: PAWN)
        self.LiveLibrary = types.SimpleNamespace(game_world=lambda: object())
        self.errors = []

    def log(self, message):
        pass

    def log_error(self, message):
        self.errors.append(message)


class FakeL:
    def __init__(self, live):
        self.live = live

    def input_key(self, key, event, value):
        self.live.keys.append((key, event, value))

    def fixed_step(self, value):
        pass

    def screenshot(self, path):
        self.live.shots.append(path)
        Path(path).write_bytes(b'x')   # the real component writes the frame on the next tick

    def ground_at(self, point):
        return point

    def switch_character(self, name):
        return self.live.switch_character(name)

    def car_state(self):
        return self.live.car_state()

    def car_ride(self):
        return self.live.car_ride()

    def teleport_player(self, at, yaw):
        return True


class FakeLive(types.ModuleType):
    def __init__(self):
        super().__init__('live')
        self.keys = []
        self.shots = []
        self.driving = False
        self.rider = 'cairo'
        self.L = FakeL(self)
        self.ROOT = ROOT

    def car_state(self):
        if self.driving:
            receipt = Path(ROOT) / 'games/yorimichi/assets/characters' / self.rider / 'kart-grip-model.json'
            scale = json.loads(receipt.read_text())['scale']
            return (f'driving=1 speed=0 kph=0.0 scale={scale:.4f} hint=Driving pos=(0,0,0) yaw=0.0 '
                    'car=(0,0,0) carrot=(0.0,0.0,0.0)')
        return 'driving=0 speed=0 kph=0.0 hint=Parked pos=(0,0,0) yaw=0.0 car=(0,0,0) carrot=(0.0,0.0,0.0)'

    def car_ride(self):
        return 'no car'

    def press(self, button):
        if button == 'car':
            self.driving = not self.driving

    def switch_character(self, name):
        self.rider = name.lower()
        return name

    def player(self):
        return Vector(), 0.0

    def drive(self, forward, right):
        pass

    def behave(self, name, fn):
        pass

    def stop(self, name=None):
        pass


PAWN = Pawn()


def load(tmp_path, monkeypatch):
    monkeypatch.setenv('ATELIER_BUILD_ROOT', str(tmp_path))
    unreal = FakeUnreal()
    live = FakeLive()
    monkeypatch.setitem(sys.modules, 'unreal', unreal)
    monkeypatch.setitem(sys.modules, 'live', live)
    spec = importlib.util.spec_from_file_location('kart_fit_scenario', SCENARIO)
    module = importlib.util.module_from_spec(spec)
    module.live = live   # the bridge injects this name into the shared namespace
    module.unreal = unreal
    spec.loader.exec_module(module)
    return module, live, unreal


def drain(module):
    for _ in range(400):
        module.tick(10.0)
        if not module.queue:
            module.tick(10.0)   # the empty-queue tick writes the receipt
            break


def test_every_rider_gets_a_summon_flag_and_captures(tmp_path, monkeypatch):
    module, live, unreal = load(tmp_path, monkeypatch)
    drain(module)
    assert not unreal.errors
    assert module.flags == {'Cairo': True, 'Modori': True, 'Nox': True, 'Paul': True}
    for rider in ('cairo', 'modori', 'nox', 'paul'):
        assert any(Path(shot).name.startswith(rider + '_') for shot in live.shots), rider
        assert any(Path(shot).name == rider + '_grip_left_neutral.png' for shot in live.shots), rider
        assert any(Path(shot).name == rider + '_grip_right_steer.png' for shot in live.shots), rider
    assert len(module.results) == 4
    assert all(item['summon_ok'] for item in module.results)
    assert all(abs(item['live_scale'] / item['prepared_scale'] - 1) < .001 for item in module.results)
    assert all(item['prepared_scale'] for item in module.results)
    receipt = json.loads(Path(module.json_path).read_text())
    assert receipt['ok'] is True and receipt['status'] == 'passed'
    assert [item['rider'] for item in receipt['riders']] == ['Cairo', 'Modori', 'Nox', 'Paul']


def test_a_failed_run_invalidates_a_previous_success(tmp_path, monkeypatch):
    module, live, unreal = load(tmp_path, monkeypatch)
    receipt = Path(module.json_path)
    receipt.write_text(json.dumps({'ok': True, 'status': 'passed', 'riders': [{'rider': 'Cairo'}]}))

    def fail(name):
        raise RuntimeError('boom')

    live.switch_character = fail
    drain(module)
    data = json.loads(receipt.read_text())
    assert data['ok'] is False and data['status'] == 'failed'
    assert any('boom' in error for error in data['errors'])


def test_refused_summons_do_not_pass_the_receipt(tmp_path, monkeypatch):
    module, live, unreal = load(tmp_path, monkeypatch)
    live.press = lambda button: None   # every car toggle refused
    drain(module)
    data = json.loads(Path(module.json_path).read_text())
    assert data['ok'] is False and data['status'] == 'failed'
    assert all(not item['summon_ok'] for item in data['riders'])
    assert any('did not mount' in error for error in data['errors'])
    assert any('missing' in error for error in data['errors'])



def test_fit_receipt_refuses_live_scale_mismatch(tmp_path, monkeypatch):
    module, live, _ = load(tmp_path, monkeypatch)
    original = live.car_state
    monkeypatch.setattr(live, 'car_state', lambda: re.sub(r'scale=[0-9.]+', 'scale=0.5', original()))
    drain(module)
    receipt = json.loads(Path(module.json_path).read_text())
    assert not receipt['ok'] and receipt['status'] == 'failed'
    assert len([error for error in receipt['errors'] if 'scale mismatch' in error]) == 4
