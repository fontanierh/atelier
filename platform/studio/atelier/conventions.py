"""The house rules in code: unit conversion, the humanoid contract, clip roles, sound cues (platform/conventions).

Standard library only: imported from the command line, Blender and Unreal.
"""
import tomllib
from functools import lru_cache

from .paths import CONVENTIONS


def to_unreal(point):
    """Source metres (Z up) to Unreal centimetres: (x, y, z) -> (100x, -100y, 100z)."""
    x, y, z = point
    return (x * 100.0, -y * 100.0, z * 100.0)


def yaw_to_unreal(yaw_degrees):
    return -yaw_degrees


@lru_cache(maxsize=None)
def _toml(name):
    with open(CONVENTIONS / name, 'rb') as handle:
        return tomllib.load(handle)


def humanoid():
    return _toml('rigs/humanoid.toml')


def required_bones():
    return [bone for chain in humanoid()['required'].values() for bone in chain]


def clip_roles():
    """{role: {'loop': bool, 'root_motion': bool}} for the platform's roles (skate roles also exist as <role>Goofy)."""
    return dict(_toml('clip-roles.toml'))


def sound_cues():
    return dict(_toml('sound-cues.toml'))


def versions():
    return dict(_toml('versions.toml'))
