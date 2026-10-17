"""Exercise real projection on occluded geometry, without model weights or Blender."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image
import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO/'games/yorimichi/tools/meshaxiom_pixel_match.py'


@pytest.fixture
def adapter():
    spec = importlib.util.spec_from_file_location('pixel_match_adapter_test', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_border_matte_keeps_enclosed_black_features(adapter):
    pixels = np.zeros((32, 32, 3), dtype='uint8')
    pixels[4:28, 4:28] = 120
    pixels[12:16, 12:16] = 0
    result = adapter.matte(Image.fromarray(pixels))
    assert np.all(result[:4, :, 3] == 0)
    assert np.all(result[12:16, 12:16, 3] == 255)
    assert np.array_equal(result[..., :3], pixels)


def fixture_glb(pm, path):
    positions = np.array([[-.5,-.5,.2],[.5,-.5,.2],[.5,.5,.2],[-.5,.5,.2],
                          [-.5,-.5,-.2],[.5,-.5,-.2],[.5,.5,-.2],[-.5,.5,-.2]], dtype='<f4')
    uvs = np.array([[.05,.05],[.45,.05],[.45,.95],[.05,.95],
                    [.55,.05],[.95,.05],[.95,.95],[.55,.95]], dtype='<f4')
    faces = np.array([[0,1,2],[0,2,3],[4,6,5],[4,7,6]], dtype='<u2')
    neutral = np.full((64,64,4), 128, dtype='uint8')
    neutral[...,3] = 255
    chunks = [positions.tobytes(), uvs.tobytes(), faces.tobytes(), pm.encode_png(neutral)]
    binary, views = b'', []
    for chunk in chunks:
        binary += b'\0'*(-len(binary)%4)
        views.append(dict(buffer=0, byteOffset=len(binary), byteLength=len(chunk)))
        binary += chunk
    doc = dict(asset=dict(version='2.0'), nodes=[dict(mesh=0)], scenes=[dict(nodes=[0])], scene=0,
               buffers=[dict(byteLength=len(binary))], bufferViews=views,
               accessors=[dict(bufferView=0,componentType=5126,count=8,type='VEC3'),
                          dict(bufferView=1,componentType=5126,count=8,type='VEC2'),
                          dict(bufferView=2,componentType=5123,count=12,type='SCALAR')],
               meshes=[dict(primitives=[dict(attributes=dict(POSITION=0,TEXCOORD_0=1),indices=2,material=0)])],
               materials=[dict(pbrMetallicRoughness=dict(baseColorTexture=dict(index=0)))],
               textures=[dict(source=0)], images=[dict(bufferView=3,mimeType='image/png')])
    path.write_bytes(pm._join_glb(doc,binary))


def test_projection_preserves_geometry_and_occluded_texels(adapter, tmp_path):
    vendor = REPO/'games/yorimichi/tools/pixel_match/photo_paint.py'
    pm = adapter.load_module(vendor)
    model = tmp_path/'clay.glb'
    fixture_glb(pm, model)
    reference = tmp_path/'reference.png'
    image = np.full((64,64,4), [210,40,20,255], dtype='uint8')
    Image.fromarray(image).save(reference)
    matted = tmp_path/'reference-matted.png'
    Image.fromarray(image).save(matted)
    camera = np.eye(4)
    camera[2,3] = 3
    calibration = dict(mesh_sha256=adapter.digest(model), reference_sha256=adapter.digest(reference),
                       matted_sha256=adapter.digest(matted), transform_matrix=camera.tolist(),
                       camera_angle_x=float(np.deg2rad(45)))
    (tmp_path/'calibration.json').write_text(json.dumps(calibration))
    args = SimpleNamespace(module=vendor,mesh=model,image=reference,output=tmp_path)
    adapter.paint(args,pm)
    report = json.loads((tmp_path/'pixel-match-report.json').read_text())
    assert report['geometry_and_uvs_identical'] and report['non_texture_buffers_identical']
    assert report['changed_protected_texels'] == 0 and report['protected_texels'] > 500
    assert 0 < report['covered_surface_fraction_painted'] < .6
    before = pm.read_glb(model)[3]
    after = pm.read_glb(tmp_path/'head-pixel-match.glb')[3]
    assert np.array_equal(before[:,36:60],after[:,36:60])  # occluded rear island
    assert np.any(before[:,4:28] != after[:,4:28])  # visible front actually receives paint
    reference.write_bytes(b'changed reference')
    with pytest.raises(ValueError,match='no longer match'):
        adapter.paint(args,pm)
