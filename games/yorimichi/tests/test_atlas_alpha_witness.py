"""World alpha provenance and restored-ground checks."""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

GAME = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('yorimichi_atlas', GAME / 'world/map/atlas.py')
atlas = importlib.util.module_from_spec(spec)
spec.loader.exec_module(atlas)


def test_world_overview_is_island_shaped_without_changing_its_rgb_geography():
    with Image.open(atlas.ASSETS / 'world.png') as image, Image.open(atlas.ASSETS / 'coasts/world.png') as mask:
        assert 'A' in image.getbands()
        alpha = np.asarray(image.getchannel('A'))
        land = np.asarray(mask) > 127
        assert int(alpha[land].min()) >= 250
        for x, y in [(0, 0), (image.width - 1, 0), (0, image.height - 1),
                     (image.width - 1, image.height - 1), (image.width - 1, image.height // 2)]:
            assert int(alpha[y, x]) == 0
        assert atlas.verify_coast(image, mask, 'world') < .0035


def test_alpha_requires_bound_generation_provenance(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, 'atlas', atlas)
    spec = importlib.util.spec_from_file_location('yorimichi_alpha', GAME / 'world/map/mask_atlas_island.py')
    alpha = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(alpha)
    assets = tmp_path / 'assets'
    (assets / 'coasts').mkdir(parents=True)
    source = tmp_path / 'source.png'
    Image.new('RGB', (1024, 1024)).save(source)
    mask = assets / 'coasts' / 'world.png'
    Image.new('L', (1024, 1024), 0).save(mask)
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    mask_sha = hashlib.sha256(mask.read_bytes()).hexdigest()
    receipt = dict(output_sha256=source_sha, labels_baked=False, bounds=atlas.WORLD_BOUNDS,
                   inputs=[dict(role='exact geography', sha256='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'),
                           dict(role='exact coast mask', sha256=mask_sha)])
    (assets / 'coasts/source.json').write_text(json.dumps(dict(
        geography=atlas.geography_signature(),
        frames=dict(world=dict(bounds=atlas.WORLD_BOUNDS, sha256=mask_sha, reference_sha256='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa')))))
    with pytest.raises(ValueError, match='no current geography'):
        alpha.validate_source(receipt, source_sha, mask, None, assets=assets)
    witness = dict(kind='terrain-reference-revalidation', geography=atlas.geography_signature(),
                   painting_sha256=source_sha, coast_sha256=mask_sha, reference_sha256='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa')
    witness_path = tmp_path / 'witness.json'
    witness_path.write_text(json.dumps(witness))
    assert alpha.validate_source(receipt, source_sha, mask, witness_path, assets=assets) == witness
    witness['coast_sha256'] = 'not the signed mask'
    witness_path.write_text(json.dumps(witness))
    with pytest.raises(ValueError, match='does not bind'):
        alpha.validate_source(receipt, source_sha, mask, witness_path, assets=assets)
    bad = dict(receipt, inputs=[dict(role='exact geography', sha256='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'),
                                dict(role='exact coast mask', sha256='wrong')])
    with pytest.raises(ValueError, match='did not use'):
        alpha.validate_source(bad, source_sha, mask, None, assets=assets)
    duplicate = dict(receipt, inputs=[dict(role='exact geography', sha256='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'),
                                      dict(role='exact geography', sha256='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'),
                                      dict(role='exact coast mask', sha256=mask_sha)])
    with pytest.raises(ValueError, match='duplicate'):
        alpha.validate_source(duplicate, source_sha, mask, None, assets=assets)
    wrong_ref = dict(receipt, inputs=[dict(role='exact geography', sha256='wrong'),
                                      dict(role='exact coast mask', sha256=mask_sha)])
    with pytest.raises(ValueError, match='signed World reference'):
        alpha.validate_source(wrong_ref, source_sha, mask, None, assets=assets)
    missing_ref = dict(receipt, inputs=[dict(role='exact coast mask', sha256=mask_sha)])
    with pytest.raises(ValueError, match='did not record its exact geography'):
        alpha.validate_source(missing_ref, source_sha, mask, None, assets=assets)
    other = assets / 'coasts/other.png'
    Image.new('L', (1024, 1024), 0).save(other)
    with pytest.raises(ValueError, match='authoritative'):
        alpha.validate_source(receipt, source_sha, other, None, assets=assets)
    original_mask = tmp_path / 'original-mask.png'
    Image.new('L', (1024, 1024), 255).save(original_mask)
    original_sha = hashlib.sha256(original_mask.read_bytes()).hexdigest()
    changed_receipt = dict(receipt, inputs=[dict(role='exact geography', sha256='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'),
                                            dict(role='exact coast mask', sha256=original_sha)])
    with pytest.raises(ValueError, match='did not use'):
        alpha.validate_source(changed_receipt, source_sha, mask, None, assets=assets)
    changed = dict(kind='terrain-reference-revalidation', geography=atlas.geography_signature(),
                   painting_sha256=source_sha, original_coast_sha256=original_sha,
                   current_coast_sha256=mask_sha, original_reference_sha256='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                   reference_sha256='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa')
    changed_path = tmp_path / 'changed-witness.json'
    changed_path.write_text(json.dumps(changed))
    assert alpha.validate_source(changed_receipt, source_sha, mask, changed_path, assets=assets) == changed
    assert changed_receipt['inputs'][1]['sha256'] == original_sha
    old_witness = dict(kind='terrain-reference-revalidation', geography=atlas.geography_signature(),
                       painting_sha256=source_sha, coast_sha256=mask_sha, reference_sha256='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa')
    changed_path.write_text(json.dumps(old_witness))
    with pytest.raises(ValueError, match='does not bind'):
        alpha.validate_source(changed_receipt, source_sha, mask, changed_path, assets=assets)
    for field in ('original_coast_sha256', 'current_coast_sha256', 'original_reference_sha256',
                  'reference_sha256', 'painting_sha256'):
        broken = dict(changed, **{field: 'not the bound value'})
        changed_path.write_text(json.dumps(broken))
        with pytest.raises(ValueError, match='does not bind'):
            alpha.validate_source(changed_receipt, source_sha, mask, changed_path, assets=assets)


def test_committed_world_alpha_binds_the_paid_generation_and_signed_mask():
    record = json.loads((atlas.ASSETS / 'world.json').read_text())
    mask_sha = hashlib.sha256((atlas.ASSETS / 'coasts/world.png').read_bytes()).hexdigest()
    witness = record['generation_witness']
    original_mask_sha = next(item['sha256'] for item in record['generation']['inputs']
                             if item.get('role') == 'exact coast mask')
    original_reference_sha = next(item['sha256'] for item in record['generation']['inputs']
                                  if item.get('role') == 'exact geography')
    assert witness['kind'] == 'terrain-reference-revalidation'
    assert witness['geography'] == atlas.geography_signature() == record['geography']
    assert witness['painting_sha256'] == record['generation']['output_sha256']
    if 'current_coast_sha256' in witness:
        assert witness['original_coast_sha256'] == original_mask_sha
        assert witness['current_coast_sha256'] == mask_sha
        assert witness['original_reference_sha256'] == original_reference_sha
    else:
        assert witness['coast_sha256'] == mask_sha
        assert original_mask_sha == mask_sha
    assert any(item.get('role') == 'exact coast mask' and item.get('sha256') == original_mask_sha
               for item in record['generation']['inputs'])


def test_alpha_input_drift_fails_before_publishing(tmp_path, monkeypatch):
    from PIL import ImageDraw
    monkeypatch.setitem(sys.modules, 'atlas', atlas)
    spec = importlib.util.spec_from_file_location('yorimichi_alpha_drift', GAME / 'world/map/mask_atlas_island.py')
    alpha = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(alpha)
    assets = tmp_path / 'assets'
    (assets / 'coasts').mkdir(parents=True)
    source = tmp_path / 'source.png'
    mask = assets / 'coasts' / 'world.png'
    painting = Image.new('RGB', (256, 256), (30, 100, 160))
    ImageDraw.Draw(painting).ellipse((60, 60, 196, 196), fill=(120, 150, 65))
    painting.save(source)
    coast = Image.new('L', (256, 256), 0)
    ImageDraw.Draw(coast).ellipse((60, 60, 196, 196), fill=255)
    coast.save(mask)
    mask_sha = hashlib.sha256(mask.read_bytes()).hexdigest()
    reference = 'a' * 64
    geography = {'test': 'current'}
    monkeypatch.setattr(atlas, 'ASSETS', assets)
    monkeypatch.setattr(atlas, 'geography_signature', lambda: geography)
    receipt = dict(output_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), labels_baked=False,
                   bounds=atlas.WORLD_BOUNDS, geography=geography,
                   inputs=[dict(role='exact geography', sha256=reference),
                           dict(role='exact coast mask', sha256=mask_sha)],
                   prompt='test', bounds_ok=True)
    (tmp_path / 'receipt.json').write_text(json.dumps(receipt))
    (assets / 'coasts/source.json').write_text(json.dumps(dict(
        geography=geography,
        frames=dict(world=dict(bounds=atlas.WORLD_BOUNDS, sha256=mask_sha, reference_sha256=reference)))))
    real_read_bytes = Path.read_bytes
    calls = {'source': 0}
    def drifting_read(self):
        data = real_read_bytes(self)
        if self.resolve() == source.resolve():
            calls['source'] += 1
            if calls['source'] == 2:
                return data + b'changed'
        return data
    monkeypatch.setattr(Path, 'read_bytes', drifting_read)
    out, out_record = tmp_path / 'out.png', tmp_path / 'out.json'
    monkeypatch.setattr(sys, 'argv', ['mask_atlas_island.py', '--source', str(source),
                                      '--record', str(tmp_path / 'receipt.json'),
                                      '--mask', str(mask), '--out', str(out),
                                      '--out-record', str(out_record)])
    with pytest.raises(ValueError, match='changed during alpha generation'):
        alpha.main()
    assert not out.exists() and not out_record.exists()
    monkeypatch.setattr(Path, 'read_bytes', real_read_bytes)
    witness = dict(kind='terrain-reference-revalidation', geography=geography,
                   painting_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                   coast_sha256=mask_sha, reference_sha256=reference)
    witness_path = tmp_path / 'witness.json'
    witness_path.write_text(json.dumps(witness))
    receipt['geography'] = {}
    (tmp_path / 'receipt.json').write_text(json.dumps(receipt))
    witness_calls = {'count': 0}
    def drifting_witness(self):
        data = real_read_bytes(self)
        if self.resolve() == witness_path.resolve():
            witness_calls['count'] += 1
            if witness_calls['count'] == 2:
                return data + b'changed'
        return data
    monkeypatch.setattr(Path, 'read_bytes', drifting_witness)
    out2, out_record2 = tmp_path / 'out2.png', tmp_path / 'out2.json'
    monkeypatch.setattr(sys, 'argv', ['mask_atlas_island.py', '--source', str(source),
                                      '--record', str(tmp_path / 'receipt.json'),
                                      '--mask', str(mask), '--witness', str(witness_path),
                                      '--out', str(out2), '--out-record', str(out_record2)])
    with pytest.raises(ValueError, match='changed during alpha generation'):
        alpha.main()
    assert not out2.exists() and not out_record2.exists()
    monkeypatch.setattr(Path, 'read_bytes', real_read_bytes)
    receipt['geography'] = geography
    (tmp_path / 'receipt.json').write_text(json.dumps(receipt))
    out3, out_record3 = tmp_path / 'out3.png', tmp_path / 'out3.json'
    out3.write_bytes(b'existing')
    real_exists = Path.exists
    def racing_exists(self):
        if self.resolve() in (out3.resolve(), out_record3.resolve()):
            return False
        return real_exists(self)
    monkeypatch.setattr(Path, 'exists', racing_exists)
    monkeypatch.setattr(sys, 'argv', ['mask_atlas_island.py', '--source', str(source),
                                      '--record', str(tmp_path / 'receipt.json'),
                                      '--mask', str(mask), '--out', str(out3),
                                      '--out-record', str(out_record3)])
    with pytest.raises(FileExistsError):
        alpha.main()
    assert out3.read_bytes() == b'existing'
    assert not out_record3.exists()
