import json
import os

import pytest

from atelier.build_v2 import recipe_external_inputs as rx


def _cache(tmp_path):
    cache = tmp_path / 'cache'
    (cache / 'sonniss' / 'combat' / 'sub').mkdir(parents=True)
    (cache / 'sonniss' / 'combat' / 'hit.wav').write_bytes(b'hit')
    (cache / 'sonniss' / 'combat' / 'sub' / 'clash.wav').write_bytes(b'clash')
    (cache / 'game' / 'music').mkdir(parents=True)
    (cache / 'game' / 'music' / 'catalog.json').write_text('{}')
    (cache / 'unrelated.bin').write_bytes(b'never read')
    return cache


def _row(name, inputs=(), settings=None):
    row = {'id': name, 'inputs': [dict(entry) for entry in inputs], 'deferred': []}
    if settings is not None:
        row['deferred'] = [{'name': 'music', 'settings': settings}]
    return row


def _snapshot(root):
    return {p.relative_to(root).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in sorted(root.rglob('*')) if p.is_file()}


def test_imports_inputs_and_deferred_settings_as_frozen_checkout_sources(tmp_path):
    cache, checkout = _cache(tmp_path), tmp_path / 'checkout'
    checkout.mkdir()
    before = _snapshot(cache)
    rows = [
        # The inner file first, then its folder: the folder import completes the identical subset.
        _row('audio.transport', [{'path': 'sonniss/combat/hit.wav', 'root': 'atelier-cache', 'optional': False}]),
        _row('audio.combat', [{'path': 'sonniss/combat', 'root': 'atelier-cache', 'optional': False},
                              {'path': 'games/x.py', 'root': 'checkout', 'optional': False}]),
        _row('audio.music', [{'path': 'game/music/catalog.json', 'root': 'atelier-cache', 'optional': False}],
             settings=[{'path': 'game/music', 'root': 'atelier-cache'}, 3]),
    ]
    original = json.dumps(rows, sort_keys=True)
    out, receipt = rx.import_external_inputs(rows, checkout=checkout, source_cache=cache)
    assert json.dumps(rows, sort_keys=True) == original  # inputs are not mutated
    assert out[1]['inputs'] == [
        {'path': 'build/v2-source-inputs/atelier-cache/sonniss/combat', 'root': 'checkout', 'optional': False},
        {'path': 'games/x.py', 'root': 'checkout', 'optional': False}]
    assert out[2]['deferred'][0]['settings'] == [{'path': 'build/v2-source-inputs/atelier-cache/game/music'}, 3]
    imported = checkout / 'build/v2-source-inputs/atelier-cache'
    assert (imported / 'sonniss/combat/sub/clash.wav').read_bytes() == b'clash'
    assert not (imported / 'sonniss/combat/sub/clash.wav').is_symlink()
    assert not (imported / 'unrelated.bin').exists()
    combat = next(entry for entry in receipt['imports'] if entry['path'] == 'sonniss/combat')
    assert [f['path'] for f in combat['files']] == ['hit.wav', 'sub/clash.wav']
    assert json.loads((checkout / 'build/v2-source-inputs/receipt.json').read_text()) == receipt
    assert _snapshot(cache) == before  # the cache is never modified
    again, second = rx.import_external_inputs(rows, checkout=checkout, source_cache=cache)
    assert again == out and second == receipt  # identical existing imports are kept


def test_conflicting_destination_refuses(tmp_path):
    cache, checkout = _cache(tmp_path), tmp_path / 'checkout'
    target = checkout / 'build/v2-source-inputs/atelier-cache/sonniss/combat'
    target.mkdir(parents=True)
    (target / 'hit.wav').write_bytes(b'different')
    with pytest.raises(rx.Unsupported, match='conflicts'):
        rx.import_external_inputs([_row('audio.combat', [{'path': 'sonniss/combat', 'root': 'atelier-cache',
                                                          'optional': False}])], checkout=checkout, source_cache=cache)


def test_links_missing_and_unknown_roots_refuse(tmp_path):
    cache, checkout = _cache(tmp_path), tmp_path / 'checkout'
    os.symlink(cache / 'unrelated.bin', cache / 'sonniss' / 'combat' / 'link.wav')
    entry = {'path': 'sonniss/combat', 'root': 'atelier-cache', 'optional': False}
    with pytest.raises(rx.Unsupported, match='linked'):
        rx.import_external_inputs([_row('a', [entry])], checkout=checkout, source_cache=cache)
    with pytest.raises(rx.Unsupported, match='missing external input'):
        rx.import_external_inputs([_row('a', [{**entry, 'path': 'nope'}])], checkout=checkout, source_cache=cache)
    with pytest.raises(rx.Unsupported, match='unknown external root'):
        rx.import_external_inputs([_row('a', [{**entry, 'root': 'elsewhere'}])], checkout=checkout, source_cache=cache)
    with pytest.raises(rx.Unsupported, match='noncanonical'):
        rx.import_external_inputs([_row('a', [{**entry, 'path': '../x'}])], checkout=checkout, source_cache=cache)


def test_absent_optional_external_keeps_its_checkout_identity(tmp_path):
    cache, checkout = _cache(tmp_path), tmp_path / 'checkout'
    out, receipt = rx.import_external_inputs([_row('a', [{'path': 'maybe.wav', 'root': 'atelier-cache', 'optional': True}])],
                                             checkout=checkout, source_cache=cache)
    assert out[0]['inputs'][0] == {'path': 'build/v2-source-inputs/atelier-cache/maybe.wav', 'root': 'checkout', 'optional': True}
    assert receipt['imports'][0]['absent'] is True


def test_blender_tool_entries_stay_untouched(tmp_path):
    cache, checkout = _cache(tmp_path), tmp_path / 'checkout'
    entry = {'path': '5.2/scripts/x.py', 'root': 'blender', 'optional': False}
    out, receipt = rx.import_external_inputs([_row('a', [entry])], checkout=checkout, source_cache=cache)
    assert out[0]['inputs'] == [entry] and receipt['imports'] == []
