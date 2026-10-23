"""The opt-in finite graph cannot alter old mesh packets or accept unsupported shader state."""
import hashlib
import io
import json

import numpy as np
import pytest

from atelier import mesh_ir
from test_mesh_ir import payload


def spec():
    return dict(kind='vertex_color_principled_v1', attribute='Color', roughness=float(np.float32(.85)),
        metallic=0.0, base_color_default=[float(np.float32(.8))]*3+[1.0],
        viewport_color=[float(np.float32(.8))]*3+[1.0], viewport_roughness=0.5,
        viewport_metallic=0.0, viewport_specular=0.5, backface_culling=False, default_profile_sha256='a'*64)


def with_materials(specs):
    meta, piece = mesh_ir.decode(payload())
    return mesh_ir.encode(piece, key=meta['asset'], slots=meta['slots'], matrix=meta['matrix'],
                          options=meta['options'], material_specs=specs)


def test_optional_materials_preserve_the_exact_preexisting_schema2_bytes():
    assert hashlib.sha256(payload()).hexdigest() == '99e6d8f3a331cfd3815df66f8ba4a64f13874e87aa0a1c7303a1d966c5d4480d'
    meta, piece = mesh_ir.decode(payload())
    assert mesh_ir.encode(piece, key=meta['asset'], slots=meta['slots'], matrix=meta['matrix'],
                          options=meta['options'], material_specs=None) == payload()
    assert meta['schema'] == 2 and 'material_specs' not in meta


def test_schema3_retains_exact_float32_graph_values_and_the_used_slot_order():
    value = spec(); data = with_materials([value]); meta, _ = mesh_ir.decode(data)
    assert meta['schema'] == 3 and meta['material_specs'] == [value]
    assert meta['material_specs'][0]['roughness'] == float(np.float32(.85))
    assert data == with_materials([value]) and data != payload()


@pytest.mark.parametrize('change', [lambda v:v.update(kind='arbitrary_nodes'), lambda v:v.update(attribute='Other'),
    lambda v:v.update(roughness=.85), lambda v:v.update(metallic=True), lambda v:v.update(backface_culling=1),
    lambda v:v.update(roughness=float('nan')), lambda v:v.update(default_profile_sha256='z'*64),
    lambda v:v.update(base_color_default=[1.0]), lambda v:v.update(texture='missing.png')])
def test_unsupported_or_inexact_material_fields_refuse_before_export(change):
    value = spec(); change(value)
    with pytest.raises(ValueError): with_materials([value])


def test_complete_per_slot_descriptors_and_actual_colour_channel_are_required():
    for values in ([], [spec(), spec()], [None]):
        with pytest.raises(ValueError): with_materials(values)
    meta, piece = mesh_ir.decode(payload()); piece['colours'] = []
    piece['selection'].update(colour_active=None, colour_render=None)
    with pytest.raises(ValueError, match='missing source channel'):
        mesh_ir.encode(piece, key='Part', slots=meta['slots'], matrix=meta['matrix'], options={}, material_specs=[spec()])


def test_schema2_cannot_silently_carry_unclaimed_schema3_materials():
    arrays = dict(np.load(io.BytesIO(with_materials([spec()])), allow_pickle=False))
    metadata = json.loads(arrays['metadata'].tobytes()); metadata['schema'] = 2
    arrays['metadata'] = np.frombuffer(json.dumps(metadata).encode(), dtype=np.uint8)
    stream = io.BytesIO(); np.savez_compressed(stream, **arrays)
    with pytest.raises(ValueError, match='metadata'): mesh_ir.decode(stream.getvalue())
