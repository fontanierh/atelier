"""Decode the native skating animation data (rig, clip samples, clip metadata) and convert it to Unreal space.

Standard library only, so the same module runs under `uv run`, in the tests and inside Unreal's Python. It ports the
Skate plugin's readers (Private/Native/AnimationSamples.cpp, AnimationMetadata.cpp, DataReader.h) word for word,
including their validation: every float word is kept as its original bit pattern, and floats are only made from them.

Native space is metres with axes left/up/forward. The Skate plugin's Unreal adapter (SkateRuntimeDetail.h, `FromNative`
and `MatrixValue`) maps a native vector v to Unreal (v.z, -v.x, v.y) * 100: a change of handedness. A bone transform
is conjugated by that map, so local transforms convert bone by bone and their products stay consistent:

    translation (x, y, z)        -> (z, -x, y) * 100 cm
    rotation    (x, y, z, w)     -> (-z, x, -y, w)        (a mirror map: the axis maps and the vector part flips)
    scale       (x, y, z)        -> (z, x, y)
"""
from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field
from pathlib import Path

RIG_MAGIC = b'ATSKEL01'
CLIP_MAGIC = b'ATCLIP01'
META_MAGIC = b'ATMETA01'
LOOPING = 0x10000000            # ClipMetadata.flags_word: the clip loops (AnimationPlayback.cpp, PlaybackClip)
PHASE_CONTROLLED = 0x40000000   # the clip's phase is driven by a parameter instead of its clock
ALWAYS = -1.0                   # an attribute whose begin is -1 holds for the whole clip


class FormatError(ValueError):
    pass


def as_float(bits):
    return struct.unpack('<f', struct.pack('<I', bits))[0]


def as_bits(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


def finite(bits):
    return (bits & 0x7f800000) != 0x7f800000


class Reader:
    """DataReader.h: little-endian u32 words, u64 as two words, strings with a u32 byte count; starts after the magic."""

    def __init__(self, data: bytes):
        self.data, self.at, self.ok = data, 8, True

    def need(self, count):
        if not self.ok or self.at > len(self.data) or count > len(self.data) - self.at:
            self.ok = False
        return self.ok

    def remaining(self):
        return len(self.data) - self.at if self.at <= len(self.data) else 0

    def word(self):
        if not self.need(4):
            return 0
        value = struct.unpack_from('<I', self.data, self.at)[0]
        self.at += 4
        return value

    def words(self, count):
        if not self.need(4 * count):
            return ()
        values = struct.unpack_from(f'<{count}I', self.data, self.at)
        self.at += 4 * count
        return values

    def wide(self):
        low, high = self.word(), self.word()
        return low | (high << 32)

    def string(self):
        count = self.word()
        if not self.need(count):
            return ''
        value = self.data[self.at:self.at + count].decode('latin-1')
        self.at += count
        return value

    def signed(self):
        value = self.word()
        return value - (1 << 32) if value & 0x80000000 else value


# ---------------------------------------------------------------- rig
@dataclass
class Bone:
    name: str
    parent: int
    mirror: int


@dataclass
class ReferencePose:
    bank: int
    name: str
    record: int
    samples: list            # one 10-word tuple per bone: scale XYZ, rotation XYZW, translation XYZ


@dataclass
class Rig:
    bones: list
    has_trajectory: bool
    poses: list

    def named_pose(self, bank, name):
        """AnimationRig::NamedPose: same-name records in one bank are replaced in file order (the last one wins)."""
        found = None
        for pose in self.poses:
            if pose.bank == bank and pose.name.upper() == name.upper():
                found = pose
        return found

    def pose(self, bank, record):
        return next((p for p in self.poses if p.bank == bank and p.record == record), None)

    def index(self, name):
        return next(i for i, b in enumerate(self.bones) if b.name == name)


def load_rig(data: bytes) -> Rig:
    """AnimationRig::Load."""
    def fail():
        raise FormatError('Invalid native animation rig')
    if len(data) < 20 or data[:8] != RIG_MAGIC:
        fail()
    r = Reader(data)
    count, trajectory = r.word(), r.word()
    if count == 0 or count > 255 or trajectory > 1 or count > r.remaining() // 12:
        fail()
    bones, names = [], set()
    for i in range(count):
        name = r.string()
        parent, mirror = r.signed(), r.signed()
        if not r.ok or parent < -1 or parent >= i or mirror < -1 or mirror >= count or not name or name in names:
            fail()
        names.add(name)
        bones.append(Bone(name, parent, mirror))
    for i, bone in enumerate(bones):
        if bone.mirror >= 0 and bones[bone.mirror].mirror != i:
            fail()
    pose_count = r.word()
    if not r.ok or pose_count > r.remaining() // 20:
        fail()
    poses, records = [], set()
    for _ in range(pose_count):
        bank = r.word()
        name = r.string()
        record = r.wide()
        samples = r.word()
        if not r.ok or not name or samples != count or samples > r.remaining() // 40:
            fail()
        flat = r.words(10 * samples)
        if not all(finite(w) for w in flat):
            fail()
        if (bank, record) in records:
            fail()
        records.add((bank, record))
        poses.append(ReferencePose(bank, name, record, [tuple(flat[10 * b:10 * b + 10]) for b in range(samples)]))
    if not r.ok or r.remaining() != 0:
        fail()
    return Rig(bones, trajectory != 0, poses)


# ---------------------------------------------------------------- clips
@dataclass
class Clip:
    name: str
    bank: int
    record: int
    fps_bits: int
    loop_translation: tuple      # 3 words
    loop_rotation: tuple         # 4 words
    channel_animation: bool
    channel_weights: tuple       # one word per bone
    frame_count: int
    bone_count: int
    tracks: list = field(repr=False)   # bone*10 + component -> tuple of words (1 for a constant track, else one per frame)

    @property
    def fps(self):
        return as_float(self.fps_bits)

    @property
    def duration(self):
        """Seconds from the first to the last frame: SelectAnimationFrames clamps at frame_count - 1."""
        return (self.frame_count - 1) / self.fps

    def sample_words(self, frame, bone):
        """AnimationClipSamples::Sample."""
        out = []
        for i in range(10):
            track = self.tracks[bone * 10 + i]
            out.append(track[0] if len(track) == 1 else track[frame])
        return tuple(out)

    def sample(self, frame, bone):
        """(scale xyz, rotation xyzw, translation xyz) as floats, native space (DecodeSampleWords)."""
        return split_sample(self.sample_words(frame, bone))

    def constant(self, bone, component):
        return len(self.tracks[bone * 10 + component]) == 1

    def track_floats(self, bone, component):
        """The track as floats, expanded to one per frame."""
        track = self.tracks[bone * 10 + component]
        values = struct.unpack(f'<{len(track)}f', struct.pack(f'<{len(track)}I', *track))
        return list(values) * self.frame_count if len(values) == 1 else list(values)


def load_clip(data: bytes) -> Clip:
    """AnimationClipSamples::Load."""
    def fail():
        raise FormatError('Invalid native animation samples')
    if len(data) < 8 or data[:8] != CLIP_MAGIC:
        fail()
    r = Reader(data)
    name = r.string()
    bank = r.word()
    record = r.wide()
    fps_bits = r.word()
    loop_translation = r.words(3)
    loop_rotation = r.words(4)
    if not r.ok or not all(finite(w) for w in loop_translation + loop_rotation):
        fail()
    channel, weights = r.word(), r.word()
    fps = as_float(fps_bits)
    if not r.ok or not name or not finite(fps_bits) or not fps > 0 or channel > 1 or weights == 0 or weights > 255 \
            or weights > r.remaining() // 4:
        fail()
    channel_weights = r.words(weights)
    if not all(finite(w) for w in channel_weights):
        fail()
    frame_count, bone_count = r.word(), r.word()
    if not r.ok or frame_count == 0 or bone_count != weights or weights * 10 > r.remaining() // 8:
        fail()
    tracks = []
    for _ in range(weights * 10):
        count = r.word()
        if not r.ok or (count != 1 and count != frame_count) or count > r.remaining() // 4:
            fail()
        track = r.words(count)
        if not all(finite(w) for w in track):
            fail()
        tracks.append(track)
    if not r.ok or r.remaining() != 0:
        fail()
    return Clip(name, bank, record, fps_bits, loop_translation, loop_rotation, channel != 0, channel_weights,
                frame_count, bone_count, tracks)


def split_sample(words):
    f = struct.unpack('<10f', struct.pack('<10I', *words))
    return f[0:3], f[3:7], f[7:10]


def normalised(q):
    """The stored rotations are near-unit (their norms differ from 1 by up to about 1.2%, from the original
    quantisation). The runtime's sampler normalises them: SelectAnimationFrames always pairs a frame with the next one
    and BlendPoseSample renormalises, even at a zero blend weight (only a clip's very last frame is used raw)."""
    n = math.sqrt(sum(v * v for v in q))
    return tuple(v / n for v in q)


def runtime_sample(sample):
    """A decoded sample with its rotation normalised, as the native runtime poses it."""
    scale, rotation, translation = sample
    return scale, normalised(rotation), translation


def quaternion_multiply(a, b):
    """NativeMath.cpp QuaternionMultiply (xyzw): the Hamilton product a * b."""
    cx, cy, cz = a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]
    return (a[0] * b[3] + b[0] * a[3] + cx, a[1] * b[3] + b[1] * a[3] + cy, a[2] * b[3] + b[2] * a[3] + cz,
            a[3] * b[3] - (a[0] * b[0] + a[1] * b[1] + a[2] * b[2]))


def quaternion_rotate(q, v):
    """NativeMath.cpp QuaternionRotate: v + 2 q x (q x v + w v) (not normalised, as the native one)."""
    fx, fy, fz = q[1] * v[2] - q[2] * v[1], q[2] * v[0] - q[0] * v[2], q[0] * v[1] - q[1] * v[0]
    ux, uy, uz = q[3] * v[0] + fx, q[3] * v[1] + fy, q[3] * v[2] + fz
    sx, sy, sz = q[1] * uz - q[2] * uy, q[2] * ux - q[0] * uz, q[0] * uy - q[1] * ux
    return (v[0] + 2 * sx, v[1] + 2 * sy, v[2] + 2 * sz)


def add_pose(motion, reference):
    """AnimationPose.cpp AddAnimationPose(motion, reference, motion_is_a=true): the clip sample layered on a
    reference pose sample. scale = ref.s * s; rotation = ref.q * q; translation = ref.q(t) + ref.t."""
    (ms, mq, mt), (rs, rq, rt) = motion, reference
    r = quaternion_rotate(rq, mt)
    return (tuple(a * b for a, b in zip(rs, ms)), quaternion_multiply(rq, mq),
            (r[0] + rt[0], r[1] + rt[1], r[2] + rt[2]))


def local_pose(clip, frame, bone, reference):
    """The native local pose of a bone at a frame: the runtime sample (rotation normalised) added onto the reference
    pose sample, as AnimationTrees.cpp's BindPose tree evaluates every clip (Pose RIG_TPOSE, Add motion_is_a). The
    clips are deltas on the rig's reference pose: their translations are zero apart from the hips, the board root and
    the hand and toe targets reparented to the board (and the spine in a couple of clips), so the bone lengths come
    from the reference pose. The rotation is returned normalised: the native matrix is built
    from the product as is, whose norm is the reference rotation's (within 0.5% of 1); an Unreal transform holds the
    rotation it stands for. `reference` is a ReferencePose (RIG_TPOSE); its TRAJECTORY sample is the identity, so the
    trajectory passes through unchanged."""
    scale, rotation, translation = add_pose(runtime_sample(clip.sample(frame, bone)),
                                            split_sample(reference.samples[bone]))
    return scale, normalised(rotation), translation


# ---------------------------------------------------------------- metadata
@dataclass
class Attribute:
    name: str
    type_id: int
    begin_bits: int
    end_bits: int
    source_offset: int
    payload_words: tuple

    @property
    def begin(self):
        return as_float(self.begin_bits)

    @property
    def end(self):
        return as_float(self.end_bits)


@dataclass
class ClipMetadata:
    name: str
    source_offset: int
    fps_bits: int
    frames_bits: int
    base_speed_bits: int
    flags_word: int
    attributes: list

    @property
    def looping(self):
        return bool(self.flags_word & LOOPING)

    @property
    def phase_controlled(self):
        return bool(self.flags_word & PHASE_CONTROLLED)

    @property
    def length(self):
        """PlaybackClip clock length in seconds at speed 1: (frames - 1) / (base_speed * fps)."""
        return (as_float(self.frames_bits) - 1.0) / (as_float(self.base_speed_bits) * as_float(self.fps_bits))


@dataclass
class Metadata:
    source_bank: str
    source_sha256: str
    source_bytes: int
    clips: list
    phase_blends: list
    blend_spaces: list
    selectors: list
    selection_spaces: list
    unsupported_trees: list

    def clip(self, name):
        """AnimationMetadata::Clip: among same-name records the one with the greatest source offset (last on ties)."""
        name, found = name.upper(), None
        for c in self.clips:
            if c.name == name and (found is None or c.source_offset >= found.source_offset):
                found = c
        return found


def _name_ok(text, length):
    return bool(text) and len(text) <= length and all(c.isascii() and (c.isupper() or c.isdigit() or c == '_') for c in text)


def load_metadata(data: bytes) -> Metadata:
    """AnimationMetadata::Load (every section is read so the trailing-byte check holds; trees keep their raw fields)."""
    def fail():
        raise FormatError('Invalid native animation metadata')
    if len(data) < 8 or data[:8] != META_MAGIC:
        fail()
    r = Reader(data)

    def count(minimum):
        value = r.word()
        if not r.ok or value > r.remaining() // minimum:
            fail()
        return value

    def word_list():
        return list(r.words(count(4)))

    def name_list():
        return [r.string() for _ in range(count(4))]

    source_bank, source_sha256, source_bytes = r.string(), r.string(), r.wide()
    if not r.ok or not source_bank or len(source_sha256) != 64 or source_bytes < 48 or \
            any(c not in '0123456789abcdefABCDEF' for c in source_sha256):
        fail()

    def identity(name, offset):
        return _name_ok(name, 36) and offset < source_bytes

    clips = []
    for _ in range(count(32)):
        name, offset = r.string(), r.wide()
        fps_bits, frames_bits, speed_bits, flags = r.word(), r.word(), r.word(), r.word()
        if not identity(name, offset) or not finite(fps_bits) or not as_float(fps_bits) > 0 or not finite(frames_bits) \
                or not as_float(frames_bits) >= 1 or not finite(speed_bits) or not as_float(speed_bits) > 0:
            fail()
        attributes, previous = [], offset
        for _ in range(count(28)):
            a_name = r.string()
            kind = r.word()
            begin, end, a_offset = r.word(), r.word(), r.wide()
            payload = tuple(word_list())
            minimum = {0: 1, 1: 4, 3: 6}.get(kind, 0)
            if not r.ok or kind > 255 or not _name_ok(a_name, 30) or not finite(begin) or not finite(end) or \
                    a_offset <= previous or a_offset >= source_bytes or len(payload) < minimum:
                fail()
            previous = a_offset
            attributes.append(Attribute(a_name, kind, begin, end, a_offset, payload))
        clips.append(ClipMetadata(name, offset, fps_bits, frames_bits, speed_bits, flags, attributes))
    phase_blends = []
    for _ in range(count(20)):
        tree = dict(name=r.string(), source_offset=r.wide(), parameter=r.string(), children=name_list())
        if not r.ok or not identity(tree['name'], tree['source_offset']) or len(tree['children']) < 2:
            fail()
        phase_blends.append(tree)
    blend_spaces = []
    for _ in range(count(24)):
        tree = dict(name=r.string(), source_offset=r.wide(), parameters=name_list(), children=name_list(), simplexes=[])
        d = len(tree['parameters'])
        if not r.ok or not identity(tree['name'], tree['source_offset']) or d == 0 or d > 4:
            fail()
        simplexes = count(16)
        if simplexes == 0:
            fail()
        for _ in range(simplexes):
            simplex = dict(children=word_list(), vertex_bits=[word_list() for _ in range(count(4))],
                           normal_bits=[word_list() for _ in range(count(4))], scale_bits=word_list())
            if not r.ok or len(simplex['children']) != d + 1:
                fail()
            tree['simplexes'].append(simplex)
        blend_spaces.append(tree)
    selectors = []
    for _ in range(count(28)):
        tree = dict(name=r.string(), source_offset=r.wide(), parameter=r.string(), default_child=r.string(),
                    children=name_list(), values=name_list())
        if not r.ok or not identity(tree['name'], tree['source_offset']) or len(tree['children']) != len(tree['values']):
            fail()
        selectors.append(tree)
    selection_spaces = []
    for _ in range(count(20)):
        tree = dict(name=r.string(), source_offset=r.wide(), parameters=[], candidates=[])
        parameters = count(20)
        if parameters > 10:
            fail()
        for _ in range(parameters):
            tree['parameters'].append(dict(name=r.string(), mode=r.word(), weight_bits=r.word(), minimum_bits=r.word(),
                                           maximum_bits=r.word()))
        candidates = count(8)
        if candidates == 0:
            fail()
        for _ in range(candidates):
            tree['candidates'].append(dict(child=r.string(), value_bits=word_list()))
        if not r.ok or not identity(tree['name'], tree['source_offset']):
            fail()
        selection_spaces.append(tree)
    unsupported = []
    for _ in range(count(16)):
        tree = dict(name=r.string(), source_offset=r.wide(), type_id=r.word())
        if not r.ok or not identity(tree['name'], tree['source_offset']):
            fail()
        unsupported.append(tree)
    if not r.ok or r.remaining() != 0:
        fail()
    return Metadata(source_bank, source_sha256, source_bytes, clips, phase_blends, blend_spaces, selectors,
                    selection_spaces, unsupported)


def attribute_payload(attribute):
    """The attribute's payload as the runtime reads it (AnimationPlayback.cpp ActiveLanes / NumericLanes):
    kind 0 one float, kind 1 four floats, kind 2 a curve of (frame, value) points, kind 3 six words of which word 5
    is a float, other kinds no payload lanes."""
    words, kind = attribute.payload_words, attribute.type_id
    if kind == 0:
        return dict(value=as_float(words[0]))
    if kind == 1:
        return dict(values=[as_float(w) for w in words[:4]])
    if kind == 2 and len(words) >= 2:
        n = words[1]
        if 0 < n <= (len(words) - 2) // 2:
            return dict(curve=[[as_float(words[2 + 2 * i]), as_float(words[3 + 2 * i])] for i in range(n)])
        return dict(curve=[])
    if kind == 3:
        return dict(words=list(words[:5]), value=as_float(words[5]))
    return {}


# ---------------------------------------------------------------- bundle
class Bundle:
    """The native animation files of a SkateNative folder."""

    def __init__(self, root):
        self.root = Path(root)

    def rig(self):
        return load_rig((self.root / 'animation' / 'rig.skate').read_bytes())

    def clip_paths(self, banks=(0, 1)):
        return [p for bank in banks for p in sorted((self.root / 'animation' / 'clips' / str(bank)).glob('*.skate'))]

    def clip(self, bank, name):
        return load_clip((self.root / 'animation' / 'clips' / str(bank) / f'{name}.skate').read_bytes())

    def metadata(self):
        return [load_metadata((self.root / 'metadata' / f'bank-{b}.skate').read_bytes()) for b in (0, 1)]


# ---------------------------------------------------------------- Unreal space
def translation_to_unreal(t):
    return (t[2] * 100.0, -t[0] * 100.0, t[1] * 100.0)


def rotation_to_unreal(q):
    return (-q[2], q[0], -q[1], q[3])


def scale_to_unreal(s):
    return (s[2], s[0], s[1])


def sample_to_unreal(sample):
    """(scale, rotation, translation) native -> (translation cm, rotation xyzw, scale) in Unreal space."""
    scale, rotation, translation = sample
    return translation_to_unreal(translation), rotation_to_unreal(rotation), scale_to_unreal(scale)


def native_matrix(sample):
    """NativeMath.cpp SqtToMatrix (row vectors: rows are the scaled basis, then the translation)."""
    (sx, sy, sz), (x, y, z, w), t = sample
    xx, yy, zz, xy, wz, xz, wy, yz, wx = x * x, y * y, z * z, x * y, w * z, x * z, w * y, y * z, w * x
    return [[(1 - 2 * (yy + zz)) * sx, 2 * (xy + wz) * sx, 2 * (xz - wy) * sx, 0.0],
            [2 * (xy - wz) * sy, (1 - 2 * (xx + zz)) * sy, 2 * (yz + wx) * sy, 0.0],
            [2 * (xz + wy) * sz, 2 * (yz - wx) * sz, (1 - 2 * (xx + yy)) * sz, 0.0],
            [t[0], t[1], t[2], 1.0]]


def adapter_matrix(m):
    """SkateRuntimeDetail.h MatrixValue: the Unreal FMatrix rows the adapter builds from a native matrix."""
    def axis(i):
        return [m[i][2], -m[i][0], m[i][1]]
    return [axis(2) + [0.0], [-v for v in axis(0)] + [0.0], axis(1) + [0.0], [v * 100.0 for v in axis(3)] + [1.0]]


def unreal_matrix(translation, rotation, scale):
    """FTransform::ToMatrixWithScale (row vectors, same quaternion formula as the native one)."""
    x, y, z, w = rotation
    m = native_matrix(((scale[0], scale[1], scale[2]), (x, y, z, w), translation))
    return m


def multiply(local, parent):
    """Row-vector affine product local * parent (ConcatenateAffine without the fused rounding)."""
    out = [[0.0] * 4 for _ in range(4)]
    for row in range(4):
        for lane in range(4):
            out[row][lane] = sum(local[row][k] * parent[k][lane] for k in range(4))
    return out


def quaternion_angle(a, b):
    """The rotation angle in radians between two unit quaternions (sign-insensitive), as 4 atan2(|a - b|, |a + b|)
    with b's sign matched to a. The usual 2 acos(|a.b|) is ill-conditioned near zero: single-precision quaternions
    that agree to 1e-7 read as about 5e-4 rad apart through it."""
    if sum(x * y for x, y in zip(a, b)) < 0:
        b = [-v for v in b]
    return 4.0 * math.atan2(math.dist(a, b), math.sqrt(sum((x + y) ** 2 for x, y in zip(a, b))))


def _f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def _fast_asin(value):
    """FMath::FastAsin(float), operation for operation in single precision."""
    half_pi = _f32(1.5707963050)
    x = abs(value)
    root = _f32(math.sqrt(max(_f32(1.0 - x), 0.0)))
    result = _f32(-0.0012624911)
    for c in (0.0066700901, -0.0170881256, 0.0308918810, -0.0501743046, 0.0889789874, -0.2145988016, half_pi):
        result = _f32(_f32(result * x) + _f32(c))
    result = _f32(result * root)
    return _f32(half_pi - result) if value >= 0.0 else _f32(result - half_pi)


def euler_stored(q):
    """The rotation an Unreal Engine 5 animation sequence actually holds for the key q (Unreal space, x y z w).

    UE 5's sequence data model keeps bone keys as single-precision Euler angles: the controller converts each key with
    FQuat4f::Euler (FQuat4f::Rotator), and evaluation rebuilds the quaternion with FQuat::MakeFromEuler. Within 0.081
    degrees of pitch +-90 (|Z X - W Y| > 0.4999995) Rotator snaps the pitch to +-90 and the roll to 0, so a key there
    comes back up to about 2e-3 rad away; elsewhere the round trip is within a few 1e-5 rad. This reproduces the round
    trip in single precision, to explain those keys in the verification."""
    x, y, z, w = (_f32(v) for v in q)
    test = _f32(_f32(z * x) - _f32(w * y))
    yaw_y = _f32(2.0 * _f32(_f32(w * z) + _f32(x * y)))
    yaw_x = _f32(1.0 - _f32(2.0 * _f32(_f32(y * y) + _f32(z * z))))
    to_deg = _f32(180.0 / math.pi)
    threshold = _f32(0.4999995)

    def axis(angle):
        angle = math.fmod(angle, 360.0)
        angle = angle + 360.0 if angle < 0.0 else angle
        return _f32(angle - 360.0 if angle > 180.0 else angle)

    if abs(test) > threshold:
        sign = 1.0 if test > 0.0 else -1.0
        pitch, roll = 90.0 * sign, 0.0
        yaw = axis(sign * _f32(_f32(2.0 * _f32(math.atan2(x, w))) * to_deg))
    else:
        pitch = _f32(_fast_asin(_f32(2.0 * test)) * to_deg)
        yaw = _f32(_f32(math.atan2(yaw_y, yaw_x)) * to_deg)
        roll = _f32(_f32(math.atan2(_f32(-2.0 * _f32(_f32(w * x) + _f32(y * z))),
                                    _f32(1.0 - _f32(2.0 * _f32(_f32(x * x) + _f32(y * y)))))) * to_deg)
    half = math.pi / 360.0
    sp, cp = math.sin(pitch * half), math.cos(pitch * half)
    sy, cy = math.sin(yaw * half), math.cos(yaw * half)
    sr, cr = math.sin(roll * half), math.cos(roll * half)
    return (cr * sp * sy - sr * cp * cy, -cr * sp * cy - sr * cp * sy, cr * cp * sy - sr * sp * cy,
            cr * cp * cy + sr * sp * sy)


RIG_EQUAL = 1e-4        # FRigComputedTransform::Equals' default tolerance
SNAP_GUARD_CM = 3e-4    # the translation offset that keeps a key apart from the reference pose (see snap_guard)


def rig_equal(a, b, tolerance=RIG_EQUAL):
    """FRigComputedTransform::Equals for two (translation, rotation xyzw, scale) keys: translation and scale within the
    tolerance per component, rotation FQuat::Equals (every component within it, with either sign)."""
    (ta, qa, sa), (tb, qb, sb) = a, b
    close = lambda u, v: all(abs(x - y) <= tolerance for x, y in zip(u, v))  # noqa: E731
    return close(ta, tb) and close(sa, sb) and (close(qa, qb) or close(qa, [-v for v in qb]))


def snap_guard(key, reference):
    """The key to give an Unreal Engine 5 sequence so that it holds that key: (key, guarded).

    Evaluating a sequence's data model (compression samples it this way) runs its FK control rig, which writes each
    bone's local transform through URigHierarchy::SetTransform; that skips a transform FRigComputedTransform::Equals
    the bone's current one, and the current one is the reference pose. A key within 1e-4 per component of the reference
    but not on it therefore comes back as the reference: up to about 2.9e-4 rad away for a toe resting near its
    reference rotation. Such a key gets SNAP_GUARD_CM added to its X translation, which the equality test sees (it is
    checked with a margin for the Unreal reference pose's own rounding); the rotation is then kept exactly. A key on
    the reference (within 2e-6) is left alone: the reference is what it stands for."""
    if not rig_equal(key, reference, 1.5 * RIG_EQUAL):
        return key, False
    (t, q, s), (rt, rq, rs) = key, reference
    if quaternion_angle(q, rq) <= 2e-6 and math.dist(t, rt) <= 2e-6 and max(abs(x - y) for x, y in zip(s, rs)) <= 2e-6:
        return key, False
    return ((t[0] + SNAP_GUARD_CM, t[1], t[2]), q, s), True
