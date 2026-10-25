import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from atelier import encoded_glb
from test_encoded_region_plan import model

SCRIPT = Path(__file__).resolve().parents[1] / 'world/stage_encoded_export_v2.py'


def _stage():
    spec = importlib.util.spec_from_file_location('stage_encoded_export_v2_test', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Context:
    def __init__(self, root, params, outputs):
        self.inputs, self.params, self.outputs = {'payload': root}, params, outputs
        self.output_dir = root.parent / 'output'

    def input(self, name):
        return self.inputs[name]

    def output(self, name):
        assert name in self.outputs
        self.output_dir.mkdir(parents=True, exist_ok=True)
        return self.output_dir / name


def _job(tmp_path, *, role='render', key='Part', extra=None):
    root = tmp_path / 'inputs' / 'payload'
    root.mkdir(parents=True)
    packet = encoded_glb.encode(model(), key=key)
    (root / f'{key}.mesh').write_bytes(packet)
    if extra:
        (root / extra).write_bytes(b'x')
    params = {'payload_member': f'{key}.mesh', 'payload_encoding': 'encoded_glb', 'payload_role': role}
    return Context(root, params, [f'{key}.glb', 'export.json']), packet


def test_exports_original_bytes_and_receipt_with_payload_digest(tmp_path):
    context, packet = _job(tmp_path)
    _stage().run(context)
    identity, data = encoded_glb.decode(packet, key='Part')
    out = context.output_dir
    assert sorted(p.name for p in out.iterdir()) == ['Part.glb', 'export.json']
    assert (out / 'Part.glb').read_bytes() == data
    receipt = json.loads((out / 'export.json').read_text())
    assert receipt['sha256'] == hashlib.sha256(data).hexdigest()
    assert receipt['metadata']['payload_sha256'] == hashlib.sha256(packet).hexdigest()
    assert receipt['metadata']['geometry_sha256'] == identity['sha256']
    assert (receipt['asset'], receipt['primary'], receipt['triangles']) == ('Part', 'Part.glb', identity['triangles'])
    assert (out / 'export.json').read_text().endswith('\n')


@pytest.mark.parametrize('change', ['role', 'encoding', 'outputs', 'foreign', 'member'])
def test_declaration_mismatches_refuse_before_writing(tmp_path, change):
    context, _ = _job(tmp_path, extra='Other.mesh' if change == 'foreign' else None)
    if change == 'role':
        context.params['payload_role'] = 'collision'
    if change == 'encoding':
        context.params['payload_encoding'] = 'mesh_ir'
    if change == 'outputs':
        context.outputs = ['Part.glb']
    if change == 'member':
        context.params['payload_member'] = '../Part.mesh'
    with pytest.raises(ValueError):
        _stage().run(context)
    assert not (context.output_dir / 'export.json').exists()


def test_linked_payload_refuses(tmp_path):
    context, packet = _job(tmp_path)
    payload = context.inputs['payload'] / 'Part.mesh'
    real = tmp_path / 'real.mesh'
    real.write_bytes(packet)
    payload.unlink()
    payload.symlink_to(real)
    with pytest.raises(ValueError, match='linked'):
        _stage().run(context)
