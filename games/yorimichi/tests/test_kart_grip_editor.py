"""Authored grips mirror anatomically, stay wheel-local, and save without losing a newer edit."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import numpy as np
import pytest

EDITOR = Path(__file__).resolve().parents[1] / 'tools/kart_grip_editor'
sys.path.insert(0, str(EDITOR))
from grip_data import bone_names, mirror_left, pack, unpack, wheel_frame  # noqa: E402

spec = importlib.util.spec_from_file_location('kart_grip_server', EDITOR / 'server.py')
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


@pytest.fixture
def meta():
    bind, parents = {}, {}
    for side, sign in (('L', 1), ('R', -1)):
        for i, name in enumerate(bone_names(side)):
            value = np.eye(4)
            if side == 'R':
                value[:3, :3] = np.diag([1., -1., -1.])
            value[:3, 3] = [.03 * ((i-1) % 3+1) if i else 0, sign*.2, .6 + (.015*((i-1)//3) if i else 0)]
            bind[name] = pack(value)
            parents[name] = None if i == 0 else (f'hand_{side}' if (i-1) % 3 == 0 else bone_names(side)[i-1])
    seated = copy.deepcopy(bind)
    pelvis = np.eye(4); pelvis[:3, 3] = [-.3, 0, .3]; seated['pelvis'] = pack(pelvis)
    for side, sign in (('L', 1), ('R', -1)):
        for name, x in ((f'upperarm_{side}', -.8), (f'forearm_{side}', -.4)):
            value = np.eye(4); value[:3, 3] = [x, sign*.2, .6]
            bind[name] = pack(value); seated[name] = pack(value)
    return {'seated_world': seated, 'id': 'cairo', 'model_sha256': 'fixture', 'scale': .85, 'bind_world': bind, 'parents': parents,
            'layout': {'steering': [.12, 0, .58], 'steering_tilt_degrees': 50}}


def payload(meta):
    inverse = np.linalg.inv(wheel_frame(meta))
    left = {name: pack(inverse @ unpack(meta['bind_world'][name])) for name in bone_names('L')}
    return {'schema': 1, 'character': 'cairo', 'model_sha256': 'fixture', 'authored_side': 'L',
            'mirror': 'anatomical-bind', 'hands': {'L': left, 'R': mirror_left(left, meta)}, 'revision': ''}


def test_mirror_uses_bind_frames_and_preserves_right_bone_lengths(meta):
    pose = payload(meta)
    wheel = wheel_frame(meta)
    for name, values in pose['hands']['R'].items():
        assert wheel @ unpack(values) == pytest.approx(unpack(meta['bind_world'][name]))
    # Object key order is not part of the file format.
    assert mirror_left(dict(reversed(list(pose['hands']['L'].items()))), meta) == pose['hands']['R']


def test_steering_keeps_all_32_frames_exactly_wheel_local(meta):
    pose = payload(meta)
    for angle in (-.8, 0, .8):
        from math import sin, cos
        steer = np.array([[1, 0, 0, 0], [0, cos(angle), -sin(angle), 0], [0, sin(angle), cos(angle), 0], [0, 0, 0, 1]])
        current = wheel_frame(meta) @ steer
        for hand in pose['hands'].values():
            for values in hand.values():
                local = unpack(values)
                assert np.linalg.inv(current) @ (current @ local) == pytest.approx(local, abs=1e-10)


def test_independent_right_edit_and_stale_model_are_rejected(meta):
    pose = payload(meta)
    server.validate(pose, meta)
    changed = copy.deepcopy(pose)
    changed['hands']['R']['finger_0_R'][12] += .01
    with pytest.raises(ValueError, match='mirrored'):
        server.validate(changed, meta)
    changed = copy.deepcopy(pose); changed['model_sha256'] = 'old'
    with pytest.raises(ValueError, match='model changed'):
        server.validate(changed, meta)


def test_save_round_trip_and_conflict_preserve_operator_work(tmp_path, meta):
    models, saves = tmp_path / 'models', tmp_path / 'saves'
    models.mkdir(); (models / 'cairo.json').write_text(json.dumps(meta))
    httpd = server.ThreadingHTTPServer(('127.0.0.1', 0), server.handler(models, saves))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True); thread.start()
    url = f'http://127.0.0.1:{httpd.server_address[1]}'
    try:
        with urlopen(url + '/config.json') as response:
            token = json.load(response)['token']
        data = payload(meta)
        data.update(arm_poles={'L': [-.1, .33, .42], 'R': [-.1, -.33, .42]},
                    shoulder_lean_degrees=25, wheel_height_offset=-.05, wheel_tilt_offset_degrees=10)
        request = lambda: Request(url + '/save', json.dumps(data).encode(),
                                  {'Content-Type': 'application/json', 'X-Grip-Token': token}, method='POST')
        with urlopen(request()) as response:
            first = json.load(response)
        raw = (saves / 'cairo/kart-grip.json').read_bytes()
        with pytest.raises(HTTPError) as conflict:
            urlopen(request())
        assert conflict.value.code == 409
        assert (saves / 'cairo/kart-grip.json').read_bytes() == raw
        data['revision'] = first['revision']
        with urlopen(request()) as response:
            assert json.load(response)['ok']
        assert len(list((models / 'history/cairo').glob('*.json'))) == 1
        saved = json.loads((saves / 'cairo/kart-grip.json').read_text())
        assert saved['hands'] == data['hands'] and saved['bind_world'] == meta['bind_world']
        for key in ('arm_poles', 'shoulder_lean_degrees', 'wheel_height_offset', 'wheel_tilt_offset_degrees'):
            assert saved[key] == data[key]
    finally:
        httpd.shutdown(); httpd.server_close(); thread.join(timeout=2)


@pytest.mark.parametrize('change', [
    {'shoulder_lean_degrees': float('nan')}, {'shoulder_lean_degrees': 90},
    {'wheel_tilt_offset_degrees': 40}, {'wheel_height_offset': .3}, {'arm_poles': {'L': [-.1, -.3, .5]}},
    {'arm_poles': {'L': [-.1, .3, .5], 'R': [-.1, -.4, .5]}},
])
def test_invalid_arm_and_wheel_fit_are_rejected(meta, change):
    data = payload(meta); data.update(change)
    with pytest.raises(ValueError):
        server.validate(data, meta)


def test_fitted_column_stays_axial_as_height_and_angle_change(meta):
    meta['layout']['steering_column_base'] = [.455639852470912, 0, .18]
    for height in (-.1, 0, .1):
        for tilt in (-20, 0, 20):
            fitted = dict(meta, wheel_height_offset=height, wheel_tilt_offset_degrees=tilt)
            wheel = wheel_frame(fitted)
            shaft = wheel[:3, 3] - np.array(meta['layout']['steering_column_base'])*meta['scale']
            normal = wheel[:3, 0]
            assert abs(np.dot(shaft, normal)/np.linalg.norm(shaft)/np.linalg.norm(normal)) == pytest.approx(1)


def test_production_preflight_rejects_unmirrored_and_stale_profiles(meta):
    from validate_profiles import validate_profile
    meta = copy.deepcopy(meta)
    meta['model_sha256'] = 'a'*64
    meta['layout']['scale_range'] = [.82, 1.16]
    pose = payload(meta)
    pose.update(scale=meta['scale'], layout=meta['layout'], bind_world=meta['bind_world'],
                model_sha256=meta['model_sha256'])
    validate_profile(pose, meta['layout'])
    changed = copy.deepcopy(pose); changed['hands']['R']['thumb_R'][12] += .02
    with pytest.raises(ValueError, match='mirrored'):
        validate_profile(changed, meta['layout'])
    with pytest.raises(ValueError, match='stale'):
        validate_profile(pose, dict(meta['layout'], steering=[.2, 0, .6]))


def test_preflight_keeps_the_full_saved_grip_contract(meta):
    from validate_profiles import validate_profile
    meta = copy.deepcopy(meta)
    meta['model_sha256'] = 'a'*64
    meta['layout']['scale_range'] = [.82, 1.16]
    pose = payload(meta)
    pose.update(scale=meta['scale'], layout=meta['layout'], bind_world=meta['bind_world'],
                model_sha256=meta['model_sha256'])
    validate_profile(pose, meta['layout'])
    nan = copy.deepcopy(pose); nan['hands']['R']['finger_0_R'][0] = float('nan')
    with pytest.raises(ValueError, match='Invalid finger transform'):
        validate_profile(nan, meta['layout'])
    wrong = copy.deepcopy(pose); wrong['schema'] = 99
    with pytest.raises(ValueError, match='Wrong character or grip format'):
        validate_profile(wrong, meta['layout'])
    elbow = copy.deepcopy(pose); elbow['arm_poles'] = {'L': [-.1, -.3, .5]}
    with pytest.raises(ValueError, match='left elbow'):
        validate_profile(elbow, meta['layout'])


def test_cairo_transfer_preserves_target_lengths_and_normalized_knuckle_contact(meta):
    from retarget import retarget
    source = payload(meta)
    source.update(arm_poles={'L': [-.1, .33, .4]}, shoulder_lean_degrees=2,
                  wheel_height_offset=.027, wheel_tilt_offset_degrees=-3)
    original = copy.deepcopy(source)
    for side in 'LR':
        for part in ('upperarm', 'forearm'): meta['bind_world'].pop(f'{part}_{side}')
    target = copy.deepcopy(meta); target.update(id='nox', scale=1.1)
    # Different hand size and imported bone rolls must not copy Cairo's bone lengths/axes.
    roll = np.array([[0., -1., 0.], [1., 0., 0.], [0., 0., 1.]])
    for name, values in target['bind_world'].items():
        bone = unpack(values); bone[:3, 3] *= 1.25; bone[:3, :3] = bone[:3, :3] @ roll
        target['bind_world'][name] = pack(bone)
    result = retarget(source, meta, target)
    fitted = dict(target, **{k: source[k] for k in ('shoulder_lean_degrees', 'wheel_height_offset', 'wheel_tilt_offset_degrees')})
    wheel = wheel_frame(fitted)
    for name in bone_names('L')[1:]:
        parent = target['parents'][name]
        actual = np.linalg.norm((wheel @ unpack(result['hands']['L'][name]))[:3, 3] -
                                (wheel @ unpack(result['hands']['L'][parent]))[:3, 3])
        bind_length = np.linalg.norm(unpack(target['bind_world'][name])[:3, 3] - unpack(target['bind_world'][parent])[:3, 3])
        assert actual == pytest.approx(bind_length)
    def anchor(hand):
        return np.mean([unpack(hand[f'finger_{i}_L'])[:3, 3] for i in range(4)], axis=0)
    assert anchor(result['hands']['L']) == pytest.approx(anchor(source['hands']['L']))
    assert source == original
    server.validate(result, target)


def test_extra_hand_sides_are_rejected(meta):
    pose = payload(meta); pose['hands']['extra'] = pose['hands']['L']
    with pytest.raises(ValueError, match='Only'):
        server.validate(pose, meta)


@pytest.mark.parametrize('base', [45, 50, 60])
@pytest.mark.parametrize('angle', [15, 75])
def test_wheel_range_is_total_angle_not_a_fixed_offset(meta, base, angle):
    meta['layout']['steering_tilt_degrees'] = base
    pose = payload(meta); pose['wheel_tilt_offset_degrees'] = angle-base
    assert server.validate(pose, meta)['wheel_tilt_offset_degrees'] == angle-base


def test_registered_model_receipt_is_independent_of_save_claims(meta):
    from source_identity import digest
    from validate_profiles import validate_profile
    meta['layout']['scale_range'] = [.82, 1.16]; meta['model_sha256'] = 'a'*64
    pose = payload(meta); pose.update(scale=meta['scale'], layout=meta['layout'], bind_world=meta['bind_world'], model_sha256=meta['model_sha256'])
    receipt = {'model_sha256': 'a'*64, 'bind_sha256': digest(meta['bind_world']),
               'scale': meta['scale'], 'seated_world': meta['seated_world']}
    validate_profile(pose, meta['layout'], receipt)
    pose['model_sha256'] = 'b'*64
    # Only registration may carry a pose across a verified re-export. A save claim
    # alone cannot change the independently recorded model identity.
    with pytest.raises(ValueError, match='registered prepared model checksum'):
        validate_profile(pose, meta['layout'], receipt)
    receipt['model_sha256'] = 'b'*64
    validate_profile(pose, meta['layout'], receipt)
    changed = copy.deepcopy(pose)
    changed['bind_world']['finger_0_L'][12] += .01
    with pytest.raises(ValueError, match='registered prepared bind'):
        validate_profile(changed, meta['layout'], receipt)


def test_grip_source_identity_excludes_animation_builds():
    from source_identity import source_paths
    names = {p.name for p in source_paths('cairo')}
    assert 'combat-build.json' not in names and 'locomotion-build.json' not in names
    assert 'fit.py' not in names
    assert {'character.toml', 'source-manifest.json', 'outfit_correctives.py',
            'humanoid.toml', 'names.py', 'rig.py', 'export.py', 'definition.py'} <= names


def test_register_carries_a_pose_across_a_rebuilt_model(monkeypatch, tmp_path, meta):
    import source_identity as identity
    import hashlib
    models, profiles = tmp_path / 'models', tmp_path / 'profiles'
    models.mkdir(); (profiles / 'cairo').mkdir(parents=True)
    # A consistent re-export updates the GLB and the export metadata together.
    new_model = b'new-model-bytes'
    meta['model_sha256'] = hashlib.sha256(new_model).hexdigest()
    meta.update(source_sha256='a'*64, scale=.85)
    (models / 'cairo.json').write_text(json.dumps(meta))
    (models / 'cairo.glb').write_bytes(new_model)
    pose = payload(meta)
    pose.update(scale=meta['scale'], bind_world=meta['bind_world'], model_sha256='b'*64)
    (profiles / 'cairo/kart-grip.json').write_text(json.dumps(pose))
    monkeypatch.setattr(identity, 'source_identity', lambda name: 'a'*64)
    receipt = identity.register(models, profiles)
    registered = json.loads((profiles / 'cairo/kart-grip-model.json').read_text())
    assert registered == {'schema': 1, 'character': 'cairo', **receipt['cairo']}
    current = meta['model_sha256']
    assert receipt['cairo']['model_sha256'] == current
    assert json.loads((profiles / 'cairo/kart-grip.json').read_text())['model_sha256'] == current
    changed = json.loads((profiles / 'cairo/kart-grip.json').read_text())
    changed['bind_world']['finger_0_L'][12] += .01
    (profiles / 'cairo/kart-grip.json').write_text(json.dumps(changed))
    with pytest.raises(ValueError, match='re-author the grip'):
        identity.register(models, profiles)


def test_register_rejects_a_changed_model_with_unchanged_metadata(monkeypatch, tmp_path, meta):
    import source_identity as identity
    models, profiles = tmp_path / 'models', tmp_path / 'profiles'
    models.mkdir(); (profiles / 'cairo').mkdir(parents=True)
    meta.update(source_sha256='a'*64, scale=.85, model_sha256='a'*64)
    (models / 'cairo.json').write_text(json.dumps(meta))
    (models / 'cairo.glb').write_bytes(b'not-the-prepared-model')
    pose = payload(meta)
    pose.update(scale=meta['scale'], bind_world=meta['bind_world'], model_sha256=meta['model_sha256'])
    (profiles / 'cairo/kart-grip.json').write_text(json.dumps(pose))
    monkeypatch.setattr(identity, 'source_identity', lambda name: 'a'*64)
    with pytest.raises(ValueError, match='does not match its export metadata'):
        identity.register(models, profiles)


def test_neutral_replay_detects_a_detached_wrist(meta):
    from grip_data import neutral_reach
    pose = payload(meta)
    assert max(neutral_reach(pose, meta).values()) < .001
    pose['hands']['L']['hand_L'][12] += 2
    assert neutral_reach(pose, meta)['L'] > .01


def test_character_owned_grips_form_the_complete_runtime_table(monkeypatch, tmp_path):
    import source_identity as identity
    from validate_profiles import validate_profile
    receipt = identity.prepared_models()
    assert set(receipt['models']) == set(identity.playable_ids())
    for name, prepared in receipt['models'].items():
        path = identity.profile_path(name)
        assert (path.parent / 'character.toml').is_file()
        pose = json.loads(path.read_text())
        assert pose['character'] == name
        assert prepared['source_sha256'] == identity.source_identity(name)
        validate_profile(pose, pose['layout'], prepared)
    monkeypatch.setattr(identity, 'playable_ids', lambda: ('fixture',))
    folder = tmp_path / 'fixture'
    folder.mkdir()
    with pytest.raises(FileNotFoundError):
        identity.prepared_models(tmp_path)
    identity.model_path('fixture', tmp_path).write_text(json.dumps({'schema': 1, 'character': 'another'}))
    with pytest.raises(ValueError, match='invalid prepared-model receipt'):
        identity.prepared_models(tmp_path)


def test_production_preflight_uses_the_independent_model_checksum():
    import source_identity as identity
    from validate_profiles import validate_profile
    prepared = identity.prepared_models()['models']['cairo']
    pose = json.loads(identity.profile_path('cairo').read_text())
    pose['model_sha256'] = 'f' * 64
    assert pose['model_sha256'] != prepared['model_sha256']
    with pytest.raises(ValueError, match='registered prepared model checksum'):
        validate_profile(pose, pose['layout'], prepared)
