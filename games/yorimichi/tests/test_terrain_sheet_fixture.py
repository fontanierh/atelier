"""Preserve sheet topology and authored attributes through regional extraction."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

GAME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GAME/'world'))
import yori  # noqa: E402,F401
from terrain_sheet_fixture import evaluate, inputs  # noqa: E402

BASELINE = Path(__file__).with_name('fixtures')/'terrain-sheet-r8.json'


@pytest.mark.parametrize('carved', [False, True])
def test_shipped_sheet_arrays_attributes_and_order(carved):
    baseline = json.loads(BASELINE.read_text())
    assert baseline['source_revision'] == '4ff62dabbc1a20350a3a849e58f00196db8a3dff'
    assert baseline['earthworks_sha256'] == 'df83a60f4ea86dff9413d9972a9129fcbf21b7d9f74a9f605618515c8eaeeecf'
    expected = baseline['cases']['carved' if carved else 'no_line']
    result, behavior = evaluate(carved)
    assert behavior == expected['behavior']
    assert behavior['input_arrays_unchanged']
    assert behavior['returns_original'] is (not carved)
    assert set(result) == set(expected['arrays']) | {'source_name'}
    assert result['source_name'] == expected['source_name']
    for key, old in expected['arrays'].items():
        current = result[key]
        assert current.dtype.str == old['dtype'], key
        assert list(current.shape) == old['shape'], key
        if key == 'faces':
            np.testing.assert_array_equal(current, old['values'])
        else:
            np.testing.assert_allclose(current, old['values'], rtol=0., atol=1.e-9, err_msg=key)
    if carved:
        assert len(result['vertices']) > len(inputs()['vertices'])
        assert len(result['faces']) > len(inputs()['faces'])
        assert result['colours'][:, 3].min() == 0.
