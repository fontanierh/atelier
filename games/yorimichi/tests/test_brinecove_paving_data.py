"""Ground refuses incomplete/foreign paving inventories without reading mesh exports."""
import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def data(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'world'))
    import yori  # noqa: F401
    return importlib.import_module('brinecove.paving_data')


def files(root, data):
    result = []
    for owner in data.OWNERS:
        path = root / (owner + '.json')
        path.write_text(json.dumps(dict(schema=1, owner=owner, rectangles=[[0, 1, 0, 1, len(result)]])))
        result.append(path)
    return result


def test_complete_paving_is_ordered_by_original_component_ownership(tmp_path, data):
    paths = files(tmp_path, data)
    expected = [[0, 1, 0, 1, i] for i in range(9)]
    assert data.read_all(paths[::-1]) == expected


@pytest.mark.parametrize('kind', ['missing', 'duplicate', 'foreign', 'nonfinite', 'link'])
def test_invalid_complete_ground_inputs_refuse(tmp_path, data, kind):
    paths = files(tmp_path, data)
    if kind == 'missing': paths.pop()
    elif kind == 'duplicate': paths.append(paths[0])
    elif kind == 'link':
        copy = tmp_path / 'copy'; copy.write_bytes(paths[0].read_bytes())
        paths[0].unlink(); paths[0].symlink_to(copy)
    else:
        value = json.loads(paths[0].read_text())
        if kind == 'foreign': value['owner'] = 'Foreign'
        else: value['rectangles'][0][-1] = float('nan')
        paths[0].write_text(json.dumps(value))
    with pytest.raises(ValueError): data.read_all(paths)
