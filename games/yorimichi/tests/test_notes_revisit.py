"""The notes revisit scenario maps recorded notes to an exact review-camera pose and numbered captures."""
import importlib.util
import json
import math
import struct
import sys
from pathlib import Path

SCENARIO = Path(__file__).resolve().parents[1] / 'scenarios' / 'notes_revisit.py'
sys.path.insert(0, str(SCENARIO.parent))
spec = importlib.util.spec_from_file_location('notes_revisit', SCENARIO)
notes_revisit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notes_revisit)

PNG = b'\x89PNG\r\n\x1a\n' + struct.pack('>I', 13) + b'IHDR' + struct.pack('>II', 2296, 1440)


def note(index=1, **overrides):
    camera = {'location_cm': [115125.0, -43660.5, 4810.1], 'pitch': -25.42, 'yaw': -178.17, 'roll': 0.0,
              'fov': 70.0, 'forward': [-0.9027, -0.0288, -0.4293]}
    camera.update(overrides.pop('camera', {}))
    data = {'index': index, 'time': '2026-10-21 23:17:13', 'text': 'weird artifacts on the grass here',
            'screenshot': f'note-{index:03d}.png', 'map': 'Slice', 'camera': camera,
            'look_at': [114467.4, -43681.4, 4497.4], 'player_cm': [114745.9, -43672.6, 4587.8]}
    data.update(overrides)
    return data


def write_notes(path, items):
    path.write_text(json.dumps({'units': 'unreal cm', 'notes': items}), encoding='utf-8')
    return path


class FakeBridge:
    def __init__(self, location, rotation):
        self.location = location
        self.rotation = rotation

    def request(self, path):
        assert path == '/state'
        return {'camera': list(self.location), 'camera_rotation': list(self.rotation), 'fps': 60.0}


class FakeQA:
    def __init__(self, location, rotation, fov=70.0):
        self.codes = []
        self.settle_calls = []
        self.fov = fov
        self.bridge = FakeBridge(location, rotation)

    def py(self, code):
        self.codes.append(code)
        if 'get_fov_angle' in code:
            return f'{self.fov}\n'
        if 'unreal.LiveLibrary.screenshot(' in code:
            argument = code.partition('unreal.LiveLibrary.screenshot(')[2].rsplit(')', 1)[0]
            Path(json.loads(argument)).write_bytes(PNG)
        return ''

    def settle(self, **kwargs):
        self.settle_calls.append(kwargs)


def test_pose_uses_the_recorded_pitch_yaw_and_player():
    pose = notes_revisit.pose_from_note(note())
    assert pose.location == (115125.0, -43660.5, 4810.1)
    assert pose.player == (114745.9, -43672.6, 4587.8)
    assert (pose.pitch, pose.yaw, pose.roll, pose.fov) == (-25.42, -178.17, 0.0, 70.0)
    assert pose.player_yaw == -178.17
    direction = tuple((target - origin) / 1000.0 for target, origin in zip(pose.target, pose.location))
    expected = (-0.9027, -0.0288, -0.4293)
    assert max(abs(a - b) for a, b in zip(direction, expected)) < 1e-3


def test_pose_falls_back_to_pitch_and_yaw_without_a_forward_vector_and_to_the_camera_for_the_player():
    item = note()
    del item['camera']['forward']
    del item['player_cm']
    pose = notes_revisit.pose_from_note(item)
    direction = tuple((target - origin) / 1000.0 for target, origin in zip(pose.target, pose.location))
    expected = notes_revisit.forward_from_rotation(-25.42, -178.17)
    assert max(abs(a - b) for a, b in zip(direction, expected)) < 1e-12
    assert pose.player == pose.location


def test_pose_rejects_a_forward_vector_that_disagrees_with_the_rotation():
    item = note(camera={'forward': [1.0, 0.0, 0.0]})
    try:
        notes_revisit.pose_from_note(item)
    except ValueError as error:
        assert 'forward' in str(error)
    else:
        raise AssertionError('a mismatched forward vector must be refused')


def test_pose_keeps_a_recorded_player_yaw():
    assert notes_revisit.pose_from_note(note(player_yaw=-88.0)).player_yaw == -88.0


def test_load_notes_orders_by_index_and_refuses_duplicates():
    import tempfile
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / 'notes.json'
        write_notes(path, [note(3), note(1), note(2)])
        _, items = notes_revisit.load_notes(path)
        assert [item['index'] for item in items] == [1, 2, 3]
        write_notes(path, [note(1), note(1)])
        try:
            notes_revisit.load_notes(path)
        except ValueError as error:
            assert 'duplicate' in str(error)
        else:
            raise AssertionError('duplicate note indexes must be refused')


def test_capture_writes_one_numbered_still_and_a_measured_index(tmp_path):
    notes = write_notes(tmp_path / 'notes.json', [note()])
    out = tmp_path / 'out'
    pose = notes_revisit.pose_from_note(note())
    fake = FakeQA(pose.location, (pose.pitch, pose.yaw, pose.roll))
    assert notes_revisit.capture(notes, out, qa_module=fake, monotonic=lambda: 0.0, sleep=lambda _: None) == 0

    assert (out / 'note-001-after.png').read_bytes() == PNG
    index = json.loads((out / 'index.json').read_text(encoding='utf-8'))
    assert index['ok'] is True
    assert index['settle'] == {'minimum_fps': 30.0, 'seconds': 1.0}
    capture = index['captures'][0]
    assert capture['after'] == 'note-001-after.png'
    assert capture['before'] == 'note-001.png'
    assert capture['size'] == [2296, 1440]
    assert capture['ok'] is True and capture['errors'] == []
    assert capture['error'] == {'location_cm': 0.0, 'pitch_deg': 0.0, 'yaw_deg': 0.0, 'fov_deg': 0.0}
    assert capture['camera']['fov'] == 70.0
    assert fake.settle_calls == [{'minimum': 30.0, 'seconds': 1.0, 'limit': 90.0}]
    assert 'teleport_player' in fake.codes[0] and 'review_camera' in fake.codes[0]
    assert any('screenshot' in code for code in fake.codes)
    assert 'restore_player_camera' in fake.codes[-1]


def test_capture_reports_a_camera_that_is_not_at_the_recorded_pose(tmp_path):
    notes = write_notes(tmp_path / 'notes.json', [note()])
    out = tmp_path / 'out'
    pose = notes_revisit.pose_from_note(note())
    fake = FakeQA((pose.location[0] + 5.0, pose.location[1], pose.location[2]),
                  (pose.pitch, pose.yaw + 1.0, pose.roll), fov=69.0)
    assert notes_revisit.capture(notes, out, qa_module=fake, monotonic=lambda: 0.0, sleep=lambda _: None) == 1
    index = json.loads((out / 'index.json').read_text(encoding='utf-8'))
    assert index['ok'] is False
    assert index['captures'][0]['ok'] is False
    assert 'camera is 5.00 cm' in index['captures'][0]['errors'][0]
    assert 'camera yaw is 1.00 degrees off' in index['captures'][0]['errors'][1]
    assert 'camera fov is 1.00 degrees off' in index['captures'][0]['errors'][2]
    assert (out / 'note-001-after.png').exists()


def test_png_size_and_shot_name():
    import tempfile
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / 'shot.png'
        path.write_bytes(PNG)
        assert notes_revisit.png_size(path) == (2296, 1440)
        path.write_bytes(b'not a png')
        assert notes_revisit.png_size(path) is None
    assert notes_revisit.shot_name(7) == 'note-007-after.png'
    assert math.isclose(sum(a * b for a, b in zip(notes_revisit.forward_from_rotation(0.0, 0.0),
                                                  (1.0, 0.0, 0.0))), 1.0)
