"""A capture must reject state text that shifts the numeric telemetry columns."""
import csv
import importlib.util
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
