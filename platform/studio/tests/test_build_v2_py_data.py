"""Focused Python tests for build-v2 D1 (py_data) job-body helpers."""
from pathlib import Path
import pytest

from atelier.build_v2 import py_data
from atelier.build_v2.python_job import JobContext


def _ctx(tmp_path: Path, monkeypatch, inputs=None, outputs=('out.json', 'route.json', 'runtime.bin', 'tool.sh'), params=None):
    monkeypatch.chdir(tmp_path)
    in_map = {}
    for k, (rel, content) in (inputs or {}).items():
        if content is None:
            in_map[k] = None
        else:
            p = tmp_path / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(content)
            in_map[k] = str(p)
    ctx = JobContext(in_map, outputs, params or {'seed': 7}, 7)
    return ctx


def test_canonical_json_and_read_write_helpers(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path, monkeypatch, inputs={
        'config': ('in/config.json', b'{"b":2,"a":[1,3]}'),
        'optional': ('in/optional.json', None),
    })
    assert py_data.read_json(ctx, 'config') == {'a': [1, 3], 'b': 2}
    assert py_data.read_json(ctx, 'optional', default={'fallback': True}) == {'fallback': True}
    with pytest.raises(LookupError):
        py_data.read_json(ctx, 'optional')
    with pytest.raises(LookupError):
        py_data.read_json(ctx, 'undeclared')

    out = py_data.write_json(ctx, 'out.json', {'z': 1, 'a': {'d': 4, 'c': 3}})
    assert out.read_bytes() == b'{"a":{"c":3,"d":4},"z":1}'

    extreme = py_data.canonical_json_bytes({
        'floats': [
            1e-06,
            1e-05,
            0.0001,
            1e-300,
            5e-324,
            1234567890123456.0,
            1e16,
            1.7976931348623157e+308,
            -0.0,
            0.0,
        ],
        'ints': [9007199254740993, 18446744073709551615],
        'unicode': {'漢': 3, 'é': 1, 'Ω': 2, 'a': 0},
    }).decode('utf-8')
    assert '"floats":[1e-06,1e-05,0.0001,1e-300,5e-324,1234567890123456.0,1e+16,1.7976931348623157e+308,-0.0,0.0]' in extreme
    assert '"ints":[9007199254740993,18446744073709551615]' in extreme
    assert '"unicode":{"a":0,"é":1,"Ω":2,"漢":3}' in extreme

    for invalid in (None, 42, 'scalar', {'nan': float('nan')}, {'inf': float('inf')}):
        with pytest.raises(ValueError):
            py_data.canonical_json_bytes(invalid)


def test_write_route_and_runtime_binary_helpers(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path, monkeypatch)
    route_path = py_data.write_route(
        ctx,
        'route.json',
        route_id='brinecove_ferry',
        waypoints=[[0.0, 0.0, 0.0], [3.0, 4.0, 0.0], [3.0, 16.0, 0.0]],
        metadata={'harbour': 'brinecove'},
    )
    assert route_path.read_bytes() == (
        b'{"distances_m":[0.0,5.0,17.0],"metadata":{"harbour":"brinecove"},'
        b'"route_id":"brinecove_ferry","waypoints":[[0.0,0.0,0.0],[3.0,4.0,0.0],[3.0,16.0,0.0]]}'
    )

    with pytest.raises(ValueError, match='at least two waypoints'):
        py_data.write_route(ctx, 'route.json', 'r', [[0.0, 0.0, 0.0]])
    with pytest.raises(ValueError, match='monotone'):
        py_data.write_route(
            ctx,
            'route.json',
            'r',
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0]],
            distances_m=[0.0, 5.0, 3.0],
        )

    bin_path = py_data.write_runtime_binary(ctx, 'runtime.bin', [b'rec1', b'rec2'])
    assert bin_path.read_bytes() == b'ATD1\x01\x00\x00\x00\x02\x00\x00\x00\x04rec1\x00\x00\x00\x04rec2'
    assert (bin_path.stat().st_mode & 0o777) == 0o644

    tool_path = py_data.write_bytes(ctx, 'tool.sh', b'#!/bin/sh\necho ok\n', executable=True)
    assert (tool_path.stat().st_mode & 0o777) == 0o755

    with pytest.raises(ValueError):
        py_data.pack_runtime_binary([])
    with pytest.raises(ValueError):
        py_data.pack_runtime_binary([b''])
