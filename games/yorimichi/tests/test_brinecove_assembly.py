"""Coastal assembly preserves source bytes and refuses foreign destination ownership."""
import ast
import hashlib
import json
from pathlib import Path

import pytest

GAME = Path(__file__).resolve().parents[1]
REGION = GAME / 'world/regions/brinecove'


@pytest.fixture
def files(monkeypatch):
    monkeypatch.syspath_prepend(str(GAME / 'world'))
    import yori  # noqa: F401
    from brinecove import assembly_files
    return assembly_files


@pytest.mark.parametrize('kind', ['foreign', 'directory', 'linked', 'broken'])
def test_coastal_staging_refuses_before_changing_foreign_bytes(tmp_path, files, kind):
    source = tmp_path / 'Current.glb'; source.write_bytes(b'current model')
    target = tmp_path / 'models'; target.mkdir()
    foreign = target / 'foreign'
    outside = tmp_path / 'outside'; outside.write_bytes(b'not ours')
    if kind == 'foreign': foreign.write_bytes(b'untouched')
    elif kind == 'directory': foreign.mkdir()
    else: foreign.symlink_to(outside if kind == 'linked' else tmp_path / 'missing')
    with pytest.raises(ValueError): files.preflight(target, {'Current.glb': source}, ['Previous.glb'])
    assert outside.read_bytes() == b'not ours'
    assert not (target / 'Current.glb').exists()
    assert foreign.is_symlink() or foreign.exists()


def test_coastal_staging_keeps_unchanged_mtime_and_retires_only_after_complete_publication(tmp_path, files):
    from atelier.export_manifest import sha
    source = tmp_path / 'Current.glb'; source.write_bytes(b'current model')
    target = tmp_path / 'models'; target.mkdir()
    stale = target / 'Previous.glb'; stale.write_bytes(b'old owned model')
    sources = {'Current.glb': source}; identities = {'Current.glb': sha(source)}
    files.preflight(target, sources, ['Previous.glb'])
    files.stage(target, sources, identities)
    assert stale.exists()  # staging cannot retire the previous published library
    previous = (target / 'Current.glb').stat().st_mtime_ns
    files.stage(target, sources, identities)
    assert (target / 'Current.glb').stat().st_mtime_ns == previous
    source.write_bytes(b'changed source')
    with pytest.raises(ValueError): files.stage(target, sources, identities)
    assert stale.exists() and (target / 'Current.glb').read_bytes() == b'current model'
    files.retire(target, sources)
    assert not stale.exists()


def test_extracted_hero_and_foliage_definitions_match_recorded_original_source():
    """Independent immutable Git source, rather than a duplicate of the new implementation."""
    baseline = json.loads((GAME / 'tests/fixtures/brinecove-placement-source.json').read_text())
    assert baseline['revision'].startswith('099b747ed')
    for original, current, selected in (
        ('hero_assets.py', 'hero_model.py', {'_import'}),
        ('hero_assets.py', 'hero_placements.py', {'placements'}),
        ('flora.py', 'foliage_placements.py', {'Poisson', '_ridge', 'scatter', 'groundcover', 'bloom_spots'}),
    ):
        expected = {key: value for key, value in baseline['files'][original]['definitions'].items() if key in selected}
        actual = {node.name: hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()
                  for node in ast.parse((REGION / current).read_text()).body
                  if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in selected}
        assert expected.keys() == selected
        assert actual == expected
