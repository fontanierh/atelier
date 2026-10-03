"""Authored test geometry and animation; contains no retail data."""
import struct


def synthetic_m2() -> bytes:
    """A triangle, one pivot bone, a one-second translation clip and one skinned section."""
    data = bytearray(0x144)
    data[:4] = b"MD20"
    struct.pack_into("<I", data, 4, 256)

    def append(payload):
        offset = len(data)
        data.extend(payload)
        return offset

    def array(position, count, offset):
        struct.pack_into("<II", data, position, count, offset)

    seq = bytearray(68)
    struct.pack_into("<H", seq, 0, 51)
    struct.pack_into("<II", seq, 4, 0, 1000)
    array(0x1C, 1, append(seq))
    bone = bytearray(108)
    struct.pack_into("<i", bone, 0, -1)
    struct.pack_into("<h", bone, 8, -1)
    struct.pack_into("<3f", bone, 96, 1, 2, 3)
    for offset in (12, 40, 68):
        struct.pack_into("<HH", bone, offset, 1, 0xFFFF)
    bone_at = append(bone)
    array(0x34, 1, bone_at)
    times = append(struct.pack("<II", 0, 1000))
    values = append(struct.pack("<6f", 0, 0, 0, 0, 0, 1))
    ranges = append(struct.pack("<II", 0, 1))
    struct.pack_into("<6I", data, bone_at + 16, 1, ranges, 2, times, 2, values)
    vertices = bytearray()
    for point in ((0, 0, 0), (1, 0, 0), (0, 1, 0)):
        vertex = bytearray(48)
        struct.pack_into("<3f", vertex, 0, *point)
        vertex[12] = 255
        struct.pack_into("<3f", vertex, 20, 0, 0, 1)
        vertices.extend(vertex)
    array(0x44, 3, append(vertices))
    skin = bytearray(44)
    skin_at = append(skin)
    array(0x4C, 1, skin_at)
    indices = append(struct.pack("<3H", 0, 1, 2))
    triangles = append(struct.pack("<3H", 0, 1, 2))
    section = bytearray(32)
    struct.pack_into("<H", section, 10, 3)
    section_at = append(section)
    array(skin_at, 3, indices)
    array(skin_at + 8, 3, triangles)
    array(skin_at + 24, 1, section_at)
    return bytes(data)
