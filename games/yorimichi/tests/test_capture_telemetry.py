"""A capture must reject state text that shifts the numeric telemetry columns."""
import csv
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture
def capture():
    path = Path(__file__).resolve().parents[1] / 'tools' / 'capture.py'
    spec = importlib.util.spec_from_file_location('capture_telemetry_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_comma_and_quote_in_state_preserve_camera_columns(capture, tmp_path):
    path = tmp_path / 'telemetry.csv'
    state = 'mode=Ground,contact="floor",speed=500'
    with path.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['frame', 'clip', 'camera_x', 'action'])
        writer.writerow([0, state, 430.25, 'Wave'])
    rows = capture.read_telemetry(path, 1)
    assert rows[0]['clip'] == state
    assert float(rows[0]['camera_x']) == 430.25
    assert rows[0]['action'] == 'Wave'


@pytest.mark.parametrize('data,expected,message', [
    ('frame,clip,camera_x\n0,mode=Ground,contact=floor,430\n', 1, 'CSV fields'),
    ('frame,clip,camera_x\n0,Ground\n', 1, 'CSV fields'),
    ('frame,clip\n0,Ground\n', 2, 'expected 2'),
    ('frame,clip\n1,Ground\n', 1, 'out of order'),
    ('frame,clip\nno,Ground\n', 1, 'valid frame'),
])
def test_corrupt_or_incomplete_capture_cannot_pass(capture, tmp_path, data, expected, message):
    path = tmp_path / 'telemetry.csv'
    path.write_text(data)
    with pytest.raises(RuntimeError, match=message):
        capture.read_telemetry(path, expected)


def launch_rows(speed, state='PhysicsGround tick=10 backend=Ride'):
    return [{'frame': str(i), 'skating': '1', 'clip': state, 'speed': str(speed if i else 0)}
            for i in range(8)]


def test_launch_is_verified_after_native_command_is_applied(capture):
    result = capture.verify_launches({'events': [{'time': 0, 'action': 'launch', 'speed': 500}]}, launch_rows(498), 60)
    assert result == [{'frame': 0, 'requested_cm_s': 500, 'observed_frame': 1, 'observed_cm_s': 498}]


@pytest.mark.parametrize('speed,state,message', [
    (50, '', 'no ready PhysicsGround'),
    (50, 'PhysicsGround tick=10 backend=Ride', 'never reached 500'),
    (float('nan'), 'PhysicsGround tick=10 backend=Ride', 'never reached 500'),
])
def test_ignored_or_unmeasured_launch_cannot_pass(capture, speed, state, message):
    with pytest.raises(RuntimeError, match=message):
        capture.verify_launches({'events': [{'time': 0, 'action': 'launch', 'speed': 500}]}, launch_rows(speed, state), 60)


@pytest.mark.parametrize('external_build', [False, True])
def test_capture_hashes_generated_and_game_inputs_before_render_admission(capture, tmp_path, monkeypatch, external_build):
    game = tmp_path / 'checkout/games/yorimichi'
    project = game / 'unreal'
    output = tmp_path / ('cache/yorimichi' if external_build else 'checkout/build/yorimichi')
    for path, data in [
        (project / 'Saved/settings.txt', b''),
        (project / 'Binaries/Mac/libUnrealEditor-Yorimichi.dylib', b'native binary'),
        (project / 'Content/Japan/Terrain.uasset', b'terrain'),
        (output / 'world.json', b'world'),
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    monkeypatch.setattr(capture, 'ROOT', game)
    monkeypatch.setattr(capture, 'PROJECT', project)
    monkeypatch.setattr(capture.yori, 'OUT', output)
    monkeypatch.setattr(capture, 'other_render_processes', lambda: [])
    monkeypatch.setattr(capture, 'head', lambda: 'a' * 40)

    class AtAdmission(Exception):
        pass

    def stop_at_admission(purpose):
        raise AtAdmission(purpose)

    monkeypatch.setattr(capture, 'render_lock', stop_at_admission)
    monkeypatch.setattr(capture, 'spawn_game', lambda *args, **kwargs: pytest.fail('Must not launch a real game'))
    with pytest.raises(AtAdmission):
        capture.capture('manifest-test', 'pier', {'seconds': 1})
    manifest = json.loads((output / 'captures/manifest-test/pier/manifest.json').read_text())
    world_key = '../../../cache/yorimichi/world.json' if external_build else '../../build/yorimichi/world.json'
    assert manifest['scene_sha256'] == {
        world_key: hashlib.sha256(b'world').hexdigest(),
        'unreal/Content/Japan/Terrain.uasset': hashlib.sha256(b'terrain').hexdigest(),
    }
