"""The Ride clip decoder (unreal/Scripts/skate_ride/native.py) against the assembled native package and the C++ reader."""
import importlib.util
import math
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import pytest

GAME = Path(__file__).resolve().parents[1]
REPO = GAME.parents[1]
SCRIPTS = GAME / 'unreal' / 'Scripts' / 'skate_ride'
NATIVE_CODE = REPO / 'platform/engine/Plugins/Activities/Skate/Source/AtelierSkate/Private/Native'
PROBE = REPO / 'platform/engine/Plugins/Activities/Skate/Tests/Native/animation_samples_probe.cpp'

_verifier = importlib.util.spec_from_file_location('verify_skate_native', GAME / 'tools' / 'verify_skate_native.py')
V = importlib.util.module_from_spec(_verifier)
_verifier.loader.exec_module(V)
spec = importlib.util.spec_from_file_location('skate_ride_native', SCRIPTS / 'native.py')
N = importlib.util.module_from_spec(spec)
sys.modules['skate_ride_native'] = N
spec.loader.exec_module(N)

BOARD = ('SKATEBOARD_ROOT', 'TRUCK_FRONT', 'TRUCK_BACK', 'LEFT_WHEELFRONT', 'RIGHT_WHEELFRONT', 'LEFT_WHEELBACK',
         'RIGHT_WHEELBACK')


@pytest.fixture(scope='module')
def bundle(tmp_path_factory):
    # The package the skate.runtime build step assembles from the committed motion text.
    return N.Bundle(V.assemble(tmp_path_factory.mktemp('skate-native') / 'package'))


@pytest.fixture(scope='module')
def rig(bundle):
    return bundle.rig()


def test_rig_hierarchy(rig):
    names = [b.name for b in rig.bones]
    assert len(names) == 36 and rig.has_trajectory and names[0] == 'TRAJECTORY' and rig.bones[0].parent == -1
    assert all(name in names for name in BOARD)
    assert rig.bones[rig.index('HIPS')].parent == 0 and rig.bones[rig.index('SKATEBOARD_ROOT')].parent == 0
    assert all(b.parent < i for i, b in enumerate(rig.bones))
    for i, b in enumerate(rig.bones):           # mirror partners are symmetric
        assert b.mirror == -1 or rig.bones[b.mirror].mirror == i
    assert rig.bones[rig.index('LEFTHAND')].mirror == rig.index('RIGHTHAND')
    pose = rig.named_pose(0, 'rig_tpose')
    assert pose is not None and len(pose.samples) == 36
    assert pose is [p for p in rig.poses if p.bank == 0 and p.name == 'RIG_TPOSE'][-1]   # the last record wins


def test_clip_count_and_frames(bundle):
    paths = bundle.clip_paths()
    assert len(paths) == 3324
    assert len(bundle.clip_paths((0,))) == 2672 and len(bundle.clip_paths((1,))) == 652
    frames = 0
    for path in paths:
        clip = N.load_clip(path.read_bytes())
        assert clip.name == path.stem and clip.bank == int(path.parent.name)
        assert clip.bone_count == 36 and clip.fps in (30.0, 60.0)
        frames += clip.frame_count
    assert frames == 131642


def test_sampling_and_constant_tracks(bundle):
    clip = bundle.clip(0, 'PRO_DILL_MANUAL_NOSEIDLE_N_0_CYC')
    assert (clip.frame_count, clip.fps) == (143, 30.0)
    assert math.isclose(clip.duration, 142 / 30.0)
    constant = [i for i, t in enumerate(clip.tracks) if len(t) == 1]
    varying = [i for i, t in enumerate(clip.tracks) if len(t) != 1]
    assert constant and varying and all(len(clip.tracks[i]) == clip.frame_count for i in varying)
    bone, component = divmod(constant[0], 10)
    first = clip.sample_words(0, bone)[component]
    assert all(clip.sample_words(f, bone)[component] == first for f in range(clip.frame_count))
    assert clip.track_floats(bone, component) == [N.as_float(first)] * clip.frame_count
    # the trajectory carries the travel (14 m forward) while the hips stay near it
    start, end = clip.sample(0, 0)[2], clip.sample(clip.frame_count - 1, 0)[2]
    assert end[2] - start[2] > 14
    assert all(abs(clip.sample(f, 1)[2][2]) < 0.5 for f in range(clip.frame_count))


def test_quaternions_normalised(bundle):
    """Stored rotations are near-unit (original quantisation); runtime_sample normalises them as the sampler does."""
    worst, normalised = 0.0, 0.0
    for path in bundle.clip_paths()[::37]:
        clip = N.load_clip(path.read_bytes())
        for frame in range(0, clip.frame_count, 3):
            for bone in range(clip.bone_count):
                q = clip.sample(frame, bone)[1]
                worst = max(worst, abs(math.sqrt(sum(v * v for v in q)) - 1.0))
                r = N.runtime_sample(clip.sample(frame, bone))[1]
                normalised = max(normalised, abs(math.sqrt(sum(v * v for v in r)) - 1.0))
    assert 1e-4 < worst < 0.02 and normalised < 1e-12


def test_clips_add_onto_reference_pose(bundle, rig):
    """Clips are deltas on RIG_TPOSE (AddAnimationPose, motion_is_a): apart from the hips, the board root and the
    hand and toe targets reparented to the board, their translations are zero, so the bone lengths are the reference
    pose's; the trajectory passes through unchanged."""
    ref = rig.named_pose(0, 'RIG_TPOSE')
    clip = bundle.clip(0, 'G_5050_FS_HI_0_CYC')
    roots = {0, rig.index('HIPS'), rig.index('SKATEBOARD_ROOT')} | {i for i, b in enumerate(rig.bones) if 'REPARENTED' in b.name}
    for frame in (0, clip.frame_count // 2, clip.frame_count - 1):
        for bone in range(36):
            raw = clip.sample(frame, bone)
            scale, rotation, translation = N.local_pose(clip, frame, bone, ref)
            ref_t = N.split_sample(ref.samples[bone])[2]
            if bone not in roots:
                assert raw[2] == (0.0, 0.0, 0.0)
                assert all(math.isclose(a, b, abs_tol=1e-7) for a, b in zip(translation, ref_t))
            assert math.isclose(math.sqrt(sum(v * v for v in rotation)), 1.0, abs_tol=1e-12)
        trajectory = N.local_pose(clip, frame, 0, ref)
        assert all(math.isclose(a, b, abs_tol=1e-7) for a, b in zip(trajectory[2], clip.sample(frame, 0)[2]))
    # the composition: identity motion gives the reference; the product order is reference * motion
    identity = ((1.0, 1.0, 1.0), (0.0, 0.0, 0.0, 1.0), (0.0, 0.0, 0.0))
    spine = N.split_sample(ref.samples[rig.index('SPINE')])
    assert N.add_pose(identity, spine) == (spine[0], spine[1], spine[2])
    turn = ((1.0, 1.0, 1.0), (0.0, math.sin(0.4), 0.0, math.cos(0.4)), (0.1, 0.0, 0.0))
    _, q, t = N.add_pose(turn, ((1.0, 1.0, 1.0), (math.sin(0.3), 0.0, 0.0, math.cos(0.3)), (0.0, 1.0, 0.0)))
    assert math.isclose(q[0], math.sin(0.3) * math.cos(0.4)) and math.isclose(q[2], math.sin(0.3) * math.sin(0.4))
    assert math.isclose(t[1], 1.0) and math.isclose(t[0], 0.1)
    # a 50-50 on the board: hips well above the board root, the feet near the deck
    def height(name):
        g = []
        for i, bone in enumerate(rig.bones):
            m = N.native_matrix(N.local_pose(clip, 0, i, ref))
            g.append(m if bone.parent <= 0 else N.multiply(m, g[bone.parent]))
        return g[rig.index(name)][3][1]
    assert 0.6 < height('HIPS') - height('SKATEBOARD_ROOT') < 0.9
    assert 0.05 < height('LEFTFOOT') - height('SKATEBOARD_ROOT') < 0.2


def test_quaternion_angle_is_stable():
    """The verification metric: exact for tiny and large angles, sign-insensitive (2 acos(|a.b|) reads float32
    rounding as about 5e-4 rad)."""
    import array
    for angle in (1e-7, 3e-5, 1e-4, 0.5, 3.0):
        a = (0.0, 0.0, 0.0, 1.0)
        b = (0.0, math.sin(angle / 2), 0.0, math.cos(angle / 2))
        assert N.quaternion_angle(a, b) == pytest.approx(angle, rel=1e-6)
        assert N.quaternion_angle(a, tuple(-v for v in b)) == pytest.approx(angle, rel=1e-6)
    q = N.normalised((0.3, -0.5, 0.2, 0.75))
    single = tuple(array.array('f', q))      # the same rotation rounded to single precision
    assert N.quaternion_angle(q, single) < 1e-6


def test_euler_storage_model(bundle, rig):
    """native.euler_stored reproduces UE's single-precision Euler key storage: the 0.000837 rad Unreal returned for
    PRO_DYRDEK_MONGO_HSPD_LSTR_CYC2 frame 51 LEFTHAND (pitch near -90), and a few 1e-6 rad elsewhere."""
    reference = rig.named_pose(0, 'RIG_TPOSE')
    names = [b.name for b in rig.bones]
    clip = bundle.clip(0, 'PRO_DYRDEK_MONGO_HSPD_LSTR_CYC2')
    q = N.sample_to_unreal(N.local_pose(clip, 51, names.index('LEFTHAND'), reference))[1]
    assert N.quaternion_angle(q, N.euler_stored(q)) == pytest.approx(8.368283e-4, rel=2e-3)
    q = N.sample_to_unreal(N.local_pose(clip, 10, names.index('SPINE'), reference))[1]
    assert N.quaternion_angle(q, N.euler_stored(q)) < 1e-5
    assert N.quaternion_angle((0, 0, 0, 1), N.euler_stored((0, 0, 0, 1))) == 0.0


def test_snap_guard(bundle, rig):
    """native.snap_guard moves a key that the control rig's 1e-4 equality test would read as the reference pose, so
    the sequence keeps it, and leaves the reference itself and keys clear of the test alone: OFB_FOOTPLANT_BSR_0_CYC
    holds LEFTTOEBASE 2.24e-4 rad from its reference, which Unreal returned as the reference."""
    reference = rig.named_pose(0, 'RIG_TPOSE')
    b = [x.name for x in rig.bones].index('LEFTTOEBASE')
    rest = N.sample_to_unreal(N.runtime_sample(N.split_sample(reference.samples[b])))
    assert N.snap_guard(rest, rest) == (rest, False)
    key = N.sample_to_unreal(N.local_pose(bundle.clip(0, 'OFB_FOOTPLANT_BSR_0_CYC'), 0, b, reference))
    assert N.quaternion_angle(key[1], rest[1]) == pytest.approx(2.245e-4, rel=1e-3)
    assert N.rig_equal(key, rest)
    moved, guarded = N.snap_guard(key, rest)
    assert guarded and not N.rig_equal(moved, rest)
    assert moved[1] == key[1] and moved[2] == key[2]
    assert math.dist(moved[0], key[0]) == pytest.approx(N.SNAP_GUARD_CM)
    far = N.sample_to_unreal(N.local_pose(bundle.clip(0, 'PRO_DYRDEK_MONGO_HSPD_LSTR_CYC2'), 10, b, reference))
    assert N.snap_guard(far, rest) == (far, False)


def test_malformed_clip_rejected(bundle):
    data = bundle.clip_paths()[0].read_bytes()
    for bad in (b'', data[:11], data[:-1], data + b'\0', b'ATCLIP02' + data[8:]):
        with pytest.raises(N.FormatError):
            N.load_clip(bad)


def test_metadata(bundle):
    banks = bundle.metadata()
    clips = {c.name: c for bank in banks for c in bank.clips}
    assert len(clips) == 3324
    meta = clips['PRO_DILL_MANUAL_NOSEIDLE_N_0_CYC']
    sample = bundle.clip(0, 'PRO_DILL_MANUAL_NOSEIDLE_N_0_CYC')
    assert meta.fps_bits == sample.fps_bits and N.as_float(meta.frames_bits) == sample.frame_count and meta.looping
    kinds = {a.type_id for c in clips.values() for a in c.attributes}
    assert kinds == {0, 3}
    pushes = [c for c in clips.values() if any(a.name == 'PUSH_CONTACT' for a in c.attributes)]
    assert pushes
    for c in clips.values():
        for a in c.attributes:
            assert a.begin == N.ALWAYS or 0.0 <= a.begin <= a.end <= 1.0 + 1e-6
            assert 'value' in N.attribute_payload(a)


def test_unreal_conversion_matches_adapter(bundle):
    """Converting a sample bone by bone equals SkateRuntimeDetail.h's MatrixValue of the native matrix, and products of
    converted locals equal the converted product (the map is a conjugation)."""
    clip = bundle.clip(0, 'PRO_DILL_MANUAL_NOSEIDLE_N_0_CYC')
    for frame in (0, 40, 142):
        for bone in range(36):
            sample = clip.sample(frame, bone)
            expected = N.adapter_matrix(N.native_matrix(sample))
            actual = N.unreal_matrix(*N.sample_to_unreal(sample))
            for row in range(4):
                for lane in range(4):
                    assert math.isclose(actual[row][lane], expected[row][lane], abs_tol=1e-5)
        child, parent = clip.sample(frame, 2), clip.sample(frame, 1)
        native_global = N.adapter_matrix(N.multiply(N.native_matrix(child), N.native_matrix(parent)))
        unreal_global = N.multiply(N.unreal_matrix(*N.sample_to_unreal(child)), N.unreal_matrix(*N.sample_to_unreal(parent)))
        for row in range(4):
            for lane in range(4):
                assert math.isclose(unreal_global[row][lane], native_global[row][lane], abs_tol=1e-4)


def raw_dump(clip):
    """animation_samples_probe.cpp Dump(): the C++ reader's view of a clip."""
    out = bytearray(b'ATCLRAW1')
    out += struct.pack('<I', len(clip.name)) + clip.name.encode()
    out += struct.pack('<IIII', clip.bank, clip.record & 0xffffffff, clip.record >> 32, clip.fps_bits)
    out += struct.pack('<7I', *clip.loop_translation, *clip.loop_rotation)
    out += struct.pack('<II', int(clip.channel_animation), len(clip.channel_weights))
    out += struct.pack(f'<{len(clip.channel_weights)}I', *clip.channel_weights)
    out += struct.pack('<II', clip.frame_count, clip.bone_count)
    for frame in range(clip.frame_count):
        for bone in range(clip.bone_count):
            out += struct.pack('<10I', *clip.sample_words(frame, bone))
    return bytes(out)


def rig_dump(rig):
    out = bytearray(b'ATSKEL01') + struct.pack('<II', len(rig.bones), int(rig.has_trajectory))
    for b in rig.bones:
        out += struct.pack('<I', len(b.name)) + b.name.encode() + struct.pack('<ii', b.parent, b.mirror)
    out += struct.pack('<I', len(rig.poses))
    for p in rig.poses:
        out += struct.pack('<I', p.bank) + struct.pack('<I', len(p.name)) + p.name.encode()
        out += struct.pack('<III', p.record & 0xffffffff, p.record >> 32, len(p.samples))
        for s in p.samples:
            out += struct.pack('<10I', *s)
    return bytes(out)


@pytest.fixture(scope='module')
def probe(tmp_path_factory):
    compiler = shutil.which('clang++')
    if not compiler:
        pytest.skip('clang++ is needed to build the C++ reader probe')
    binary = tmp_path_factory.mktemp('probe') / 'animation-samples-probe'
    subprocess.run([compiler, '-std=c++17', '-O1', '-I', str(NATIVE_CODE), str(NATIVE_CODE / 'AnimationSamples.cpp'),
                    str(PROBE), '-o', str(binary)], check=True)
    return binary


def test_agrees_with_cpp_reader(bundle, rig, probe, tmp_path):
    """The C++ reader (AnimationSamples.cpp, through its parity probe) and this decoder give the same words for every
    frame and bone of a spread of clips, and the same rig."""
    dump = subprocess.run([str(probe), 'rig', str(bundle.root / 'animation' / 'rig.skate'), str(tmp_path)],
                          capture_output=True, check=True).stdout
    assert dump == rig_dump(rig)
    for path in bundle.clip_paths()[::97] + [bundle.clip_paths()[-1]]:
        dump = subprocess.run([str(probe), 'clip', str(path), str(tmp_path)], capture_output=True, check=True).stdout
        assert dump == raw_dump(N.load_clip(path.read_bytes())), path.name


def test_source_digest_ignores_comments_docstrings_and_layout(tmp_path):
    """The clip importer's fingerprint hashes code, so an edit to the words alone does not rebuild /Game/SkateRide."""
    base = tmp_path / 'base.py'
    base.write_text('"""Module."""\nX = 1\n\n\nclass A:\n    """A."""\n    def f(self):\n        """F."""\n        return X\n')
    edited = tmp_path / 'edited.py'
    edited.write_text('"""The module, reworded."""\n# a comment\nX = 1  # one\n\nclass A:\n    """Another A."""\n\n'
                      '    def f(self):\n        """Another F."""\n        return X\n')
    assert N.source_digest(base) == N.source_digest(edited)


def test_source_digest_follows_code(tmp_path):
    """A change to the code, a string that is not a docstring included, changes the digest."""
    variants = ['X = 1\n', 'X = 2\n', 'X = 1\nY = "words"\n', 'X = 1\nY = "other words"\n', 'def f():\n    """F."""\n',
                'def f():\n    """F."""\n    return 1\n']
    digests = []
    for i, text in enumerate(variants):
        path = tmp_path / f'v{i}.py'
        path.write_text(text)
        digests.append(N.source_digest(path))
    assert len(set(digests)) == len(variants)
