"""City source parameters make constructor appearance independent from worker order."""
import hashlib
import importlib
import json
from pathlib import Path
import random
from types import SimpleNamespace

import pytest

GAME = Path(__file__).resolve().parents[1]
ROOT = GAME / 'assets/hidamari/export-parameters'


@pytest.fixture
def context(monkeypatch):
    monkeypatch.syspath_prepend(str(GAME / 'world'))
    import yori  # noqa: F401
    return importlib.import_module('hidamari.source_context')


def test_all_source_contexts_match_their_own_logical_asset_and_initial_provenance(context):
    from hidamari.logical_catalogue import ASSETS
    provenance = json.loads((ROOT / 'source-provenance.json').read_text())
    assert set(provenance['assets']) == set(ASSETS)
    for key in ASSETS:
        path = ROOT / (key + '.json')
        assert context.read(path, key)['asset'] == key
        files = context.inputs(path, key)
        assert files[0] == path and len(files) == 2
        assert hashlib.sha256(path.read_bytes()).hexdigest() == provenance['assets'][key]['parameters_sha256']
        assert hashlib.sha256(files[1].read_bytes()).hexdigest() == provenance['assets'][key]['palette_sha256']


def test_each_constructor_reset_restores_tuple_palette_and_complete_rng_state(context):
    value = context.read(ROOT / 'HD_Temple.json', 'HD_Temple')
    kernel = SimpleNamespace(PALETTE={'foreign': (9, 9, 9)}, R=random.Random(999))
    context.apply(value, kernel)
    state, palette = kernel.R.getstate(), dict(kernel.PALETTE)
    assert palette and 'foreign' not in palette and all(type(rgb) is tuple for rgb in palette.values())
    for _ in range(100): kernel.R.random()
    kernel.PALETTE.clear(); kernel.PALETTE['foreign'] = (1, 0, 0)
    context.apply(value, kernel)
    assert kernel.R.getstate() == state and kernel.PALETTE == palette


def test_foreign_and_nonfinite_contexts_refuse(context, tmp_path):
    value = json.loads((ROOT / 'HD_Temple.json').read_text())
    path = tmp_path / 'context.json'
    value['asset'] = 'Other'
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError): context.read(path, 'HD_Temple')
    value['asset'] = 'HD_Temple'; value['palette_file'] = 'palettes/Bad.json'
    (tmp_path / 'palettes').mkdir()
    (tmp_path / value['palette_file']).write_text(json.dumps({'invalid': [0, float('nan'), 1]}))
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError): context.read(path, 'HD_Temple')
