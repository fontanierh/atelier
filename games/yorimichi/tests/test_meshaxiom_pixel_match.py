"""Exercise real projection on occluded geometry, without model weights or Blender."""
import importlib.util
import gzip
import json
import os
from pathlib import Path
import sys
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


def test_preparation_guard_failure_never_starts_native_work(monkeypatch, tmp_path):
    from atelier.harness.safety import guarded
    script = SCRIPT.with_name('meshaxiom_prepare.py')
    spec = importlib.util.spec_from_file_location('meshaxiom_prepare_test', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    def unavailable(*args, **kwargs):
        raise RuntimeError('guard unavailable')
    def forbidden(*args):
        pytest.fail('Native preparation started without a live guard')
    monkeypatch.setattr(guarded, 'run', unavailable)
    monkeypatch.setattr(module, 'prepare', forbidden)
    output = tmp_path/'output'
    with pytest.raises(RuntimeError, match='guard unavailable'):
        module.main(['--mesh', 'unused.json', '--image', 'unused.png', '--output', str(output),
                     '--report', str(tmp_path/'guard')])
    assert not output.exists()


@pytest.mark.skipif(sys.platform != 'darwin' or os.environ.get('CI') != 'true',
                    reason='Real unmanaged guard needs the isolated macOS CI host, without a live local build')
def test_standalone_preparation_has_real_aggregate_cleanup(monkeypatch, tmp_path):
    from atelier.harness import capacity_runtime
    spec = importlib.util.spec_from_file_location('meshaxiom_prepare_unmanaged_test', SCRIPT.with_name('meshaxiom_prepare.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(capacity_runtime, 'configured_session', lambda **kwargs: None)
    report = tmp_path/'guard'
    # A tiny failure control exercises the real wrapper/worker/owned-child lifecycle.
    # No Blender, weights or source geometry are needed; failed UV export must stop calibration.
    result = module.main(['--mesh', 'unused.json', '--image', 'unused.png', '--output', str(tmp_path/'output'),
                          '--blender', '/usr/bin/false', '--report', str(report), '--timeout', '30'])
    assert result == 1
    assert 'UV preparation: Blender exited 1' in (report/'stdout.log').read_text()
    receipt = json.loads((report/'memory-health-tree.json').read_text())
    assert receipt['state'] == 'child_exited' and receipt['cleanup_complete']
    assert receipt['peak_bytes'] > 0 and receipt['processes'] == []


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


@pytest.mark.parametrize('blend', ['weighted', 'best-angle', 'front-first'])
def test_multiview_reaches_occluded_rear_without_changing_front_geometry(adapter, tmp_path, blend):
    vendor = REPO/'games/yorimichi/tools/pixel_match/photo_paint.py'
    pm = adapter.load_module(vendor)
    model = tmp_path/'clay.glb'
    fixture_glb(pm, model)
    front = tmp_path/'front.png'
    rear = tmp_path/'rear.png'
    Image.new('RGBA', (64, 64), (210, 40, 20, 255)).save(front)
    Image.new('RGBA', (64, 64), (20, 40, 210, 255)).save(rear)
    Image.open(front).save(tmp_path/'reference-matted.png')
    camera = np.eye(4)
    camera[2, 3] = 3
    back_camera = np.diag([-1., 1., -1., 1.])
    back_camera[2, 3] = -3
    fov = float(np.deg2rad(45))
    (tmp_path/'calibration.json').write_text(json.dumps(dict(
        mesh_sha256=adapter.digest(model), reference_sha256=adapter.digest(front),
        matted_sha256=adapter.digest(tmp_path/'reference-matted.png'),
        transform_matrix=camera.tolist(), camera_angle_x=fov)))
    manifest = tmp_path/'views.json'
    views = [dict(name=name, image=path.name, image_sha256=adapter.digest(path),
                  transform_matrix=matrix.tolist(), camera_angle_x=fov)
             for name, path, matrix in [('front', front, camera), ('rear', rear, back_camera)]]
    manifest.write_text(json.dumps(dict(mesh_sha256=adapter.digest(model), views=views)))
    args = SimpleNamespace(module=vendor, mesh=model, image=front, output=tmp_path, views=manifest, blend=blend)
    adapter.paint(args, pm)
    report = json.loads((tmp_path/'pixel-match-report.json').read_text())
    assert report['view_count'] == 2 and report['covered_surface_fraction_painted'] > .9
    assert report['non_texture_buffers_identical'] and report['geometry_and_uvs_identical']
    after = pm.read_glb(tmp_path/'head-pixel-match.glb')[3]
    assert after[32, 16, 0] > after[32, 16, 2]  # front stays red
    assert after[32, 48, 2] > after[32, 48, 0]  # formerly unseen rear becomes blue
    views[0]['transform_matrix'][0][0] = 2
    manifest.write_text(json.dumps(dict(mesh_sha256=adapter.digest(model), views=views)))
    with pytest.raises(ValueError, match='Invalid multiview camera'):
        adapter.paint(args, pm)
    views[0]['transform_matrix'] = camera.tolist()
    manifest.write_text(json.dumps(dict(mesh_sha256=adapter.digest(model), views=views)))
    rear.write_bytes(b'changed reference')
    with pytest.raises(ValueError, match='reference no longer matches'):
        adapter.paint(args, pm)


@pytest.mark.parametrize('mutation', ['position', 'winding'])
@pytest.mark.parametrize('compressed', [False, True])
def test_uv_verifier_detects_geometry_edits_even_with_identical_counts(adapter, tmp_path, monkeypatch, mutation, compressed):
    monkeypatch.syspath_prepend(str(SCRIPT.parent))
    spec = importlib.util.spec_from_file_location('meshaxiom_quality_test', SCRIPT.with_name('meshaxiom_quality.py'))
    quality = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(quality)
    pm = adapter.load_module(REPO/'games/yorimichi/tools/pixel_match/photo_paint.py')
    model = tmp_path/'clay.glb'
    fixture_glb(pm, model)
    native = tmp_path/'mesh.json'
    native.write_text(json.dumps(dict(vertices=[[-1,-1,0],[1,-1,0],[1,-1,2],[-1,-1,2],
                                               [-1,1,0],[1,1,0],[1,1,2],[-1,1,2]],
                                      faces=[[0,1,2],[0,2,3],[4,6,5],[4,7,6]])))
    if compressed:
        packed = tmp_path/'mesh.json.gz'
        packed.write_bytes(gzip.compress(native.read_bytes()))
        native = packed
    positions = np.array([[-.175,0,.175],[.175,0,.175],[.175,.35,.175],[-.175,.35,.175],
                          [-.175,0,-.175],[.175,0,-.175],[.175,.35,-.175],[-.175,.35,-.175]], dtype='<f4')
    doc, binary = pm._split_glb(model.read_bytes())
    binary = bytearray(binary)
    binary[:positions.nbytes] = positions.tobytes()
    model.write_bytes(pm._join_glb(doc, bytes(binary)))
    assert quality.verify_geometry(native, model, pm)['all_triangles_and_winding_preserved']
    if mutation == 'position':
        positions[0, 0] += .001
        binary[:positions.nbytes] = positions.tobytes()
    else:
        view = doc['bufferViews'][2]
        offset = view['byteOffset']
        indices = np.frombuffer(binary, dtype='<u2', count=12, offset=offset).copy()
        indices[0], indices[1] = indices[1], indices[0]
        binary[offset:offset+indices.nbytes] = indices.tobytes()
    model.write_bytes(pm._join_glb(doc, bytes(binary)))
    with pytest.raises(ValueError, match='coordinates or winding changed'):
        quality.verify_geometry(native, model, pm)


def test_front_first_avoids_blending_disagreeing_features_and_fills_unseen_regions(adapter, tmp_path):
    pm = adapter.load_module(REPO/'games/yorimichi/tools/pixel_match/photo_paint.py')
    model = tmp_path/'clay.glb'
    fixture_glb(pm, model)
    positions, uvs, faces, base = pm.read_glb(model)
    camera = np.eye(4)
    camera[2, 3] = 3
    first = np.full((64,64,4), [210,40,20,255], dtype='uint8')
    second = np.full((64,64,4), [20,40,210,255], dtype='uint8')
    views = [pm.View(image, camera, np.deg2rad(45), name)
             for image, name in [(first, 'face'), (second, 'other')]]
    settings = pm.Settings(facing_low=.08, facing_high=.35, edge_px=2, match_colour=False)
    selected, _ = adapter.select_view(base, positions, uvs, faces, views,
                                     frame=adapter.IDENTITY_FRAME, settings=settings, pm=pm, mode='front-first')
    weighted, _ = pm.paint_texture(base, positions, uvs, faces, views,
                                   frame=adapter.IDENTITY_FRAME, settings=settings)
    assert selected[32,16,0] > selected[32,16,2]+100
    assert abs(int(weighted[32,16,0])-int(weighted[32,16,2])) < 10
    transparent = first.copy()
    transparent[...,3] = 0
    views[0] = pm.View(transparent, camera, np.deg2rad(45), 'face')
    fallback, _ = adapter.select_view(base, positions, uvs, faces, views,
                                     frame=adapter.IDENTITY_FRAME, settings=settings, pm=pm, mode='front-first')
    assert fallback[32,16,2] > fallback[32,16,0]+100


def test_coherent_reference_gets_new_receipt_and_preserves_prior_paid_inputs(tmp_path, monkeypatch):
    from atelier.ai import images
    monkeypatch.syspath_prepend(str(SCRIPT.parent))
    spec = importlib.util.spec_from_file_location('meshaxiom_coherent_reference_test', SCRIPT.with_name('meshaxiom_quality.py'))
    quality = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(quality)
    (tmp_path/'guides').mkdir()
    (tmp_path/'references').mkdir()
    image = tmp_path/'identity.png'
    image.write_bytes(b'identity input')
    guide = tmp_path/'guides/coherent.png'
    guide.write_bytes(b'completed projected guide')
    view = dict(name='view', reference_stem='view-coherent', guide=guide.name,
                guide_sha256=quality.digest(guide), guide_mode='fill-unpainted', yaw=120, pitch=-5)
    (tmp_path/'guides/cameras.json').write_text(json.dumps(dict(
        reference_sha256=quality.digest(image), views=[view])))
    old = tmp_path/'references/view.provenance.json'
    old.write_bytes(b'prior paid operation')
    calls = []
    def submit(target, prompt, size, context=None, **kwargs):
        calls.append((target, prompt))
        kwargs['record'].write_text('uncertain receipt')
    monkeypatch.setattr(images, 'paint', submit)
    args = SimpleNamespace(output=tmp_path, image=image, views='view')
    quality.references(args)
    assert calls[0][0].name == 'view-coherent.png'
    assert 'Fill only its blank neutral-gray' in calls[0][1]
    assert old.read_bytes() == b'prior paid operation'
    with pytest.raises(FileExistsError, match='receipt already exists'):
        quality.references(args)
    with pytest.raises(FileExistsError, match='paid receipt'):
        quality.coherent_guide(SimpleNamespace(output=tmp_path, from_model=tmp_path/'unused.glb',
                                             from_contact=tmp_path/'unused.png', reference_stem='view-coherent'))
    assert len(calls) == 1


def test_uniform_registration_preserves_paid_pixels_and_records_actual_alignment(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPT.parent))
    spec = importlib.util.spec_from_file_location('meshaxiom_registration_test', SCRIPT.with_name('meshaxiom_quality.py'))
    quality = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(quality)
    (tmp_path/'guides').mkdir()
    (tmp_path/'references').mkdir()
    source = tmp_path/'references/view.png'
    pixels = np.zeros((128,128,3), dtype='uint8')
    pixels[22:110,28:104] = [200,130,90]
    Image.fromarray(pixels).save(source)
    original = source.read_bytes()
    guide = tmp_path/'guides/view.png'
    target = np.zeros_like(pixels)
    target[16:112,20:104] = 160
    Image.fromarray(target).save(guide)
    identity = tmp_path/'identity.png'
    identity.write_bytes(b'identity')
    view = dict(name='view', guide=guide.name, guide_sha256=quality.digest(guide))
    (tmp_path/'guides/cameras.json').write_text(json.dumps(dict(views=[view])))
    source.with_suffix('.provenance.json').write_text(json.dumps(dict(status='done', camera=view,
        output_sha256=quality.digest(source), reference_sha256=quality.digest(identity))))
    quality.register_reference(SimpleNamespace(output=tmp_path, image=identity, guide_view='view'))
    record = json.loads(source.with_suffix('.registration.json').read_text())
    assert source.read_bytes() == original
    assert record['silhouette_iou_after'] >= .95
    assert record['silhouette_iou_after'] > record['silhouette_iou_before']
    assert record['raw_sha256'] == quality.digest(source)
    assert record['output_sha256'] == quality.digest(source.with_name(record['output']))


def test_transferred_photos_keep_original_mesh_identity_and_reject_new_silhouette_drift(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPT.parent))
    spec = importlib.util.spec_from_file_location('meshaxiom_transfer_test', SCRIPT.with_name('meshaxiom_quality.py'))
    quality = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(quality)
    (tmp_path/'guides').mkdir()
    (tmp_path/'uv').mkdir()
    model = tmp_path/'uv/clay-uv.glb'
    model.write_bytes(b'original native geometry UV export')
    identity = tmp_path/'identity.png'
    identity.write_bytes(b'original identity')
    (tmp_path/'uv-comparison.json').write_text(json.dumps([dict(name='uv')]))
    camera_path = tmp_path/'guides/cameras.json'
    camera_path.write_text(json.dumps(dict(mesh_sha256=quality.digest(model),
                                         reference_sha256=quality.digest(identity), views=[])))
    assert quality.camera_set(tmp_path, identity)[0] == model
    model.write_bytes(b'a different density output cannot masquerade as the generation mesh')
    with pytest.raises(ValueError, match='Guide inputs no longer match'):
        quality.camera_set(tmp_path, identity)
    guide = tmp_path/'guides/target.png'
    pixels = np.zeros((64,64,3), dtype='uint8')
    pixels[12:52,12:52] = 160
    Image.fromarray(pixels).save(guide)
    camera = dict(name='target', guide=guide.name, guide_sha256=quality.digest(guide))
    photo = quality.matte(Image.fromarray(pixels))
    assert quality.projection_fit(tmp_path, camera, photo)['target_silhouette_iou'] == 1
    # A source photograph can pass its own guide while failing the new mesh's silhouette.
    changed = pixels.copy()
    changed[:24] = 0
    with pytest.raises(ValueError, match='reject transfer'):
        quality.projection_fit(tmp_path, camera, quality.matte(Image.fromarray(changed)))
    guide.write_bytes(b'target guide changed after calibration')
    with pytest.raises(ValueError, match='Target projection guide changed'):
        quality.projection_fit(tmp_path, camera, photo)
