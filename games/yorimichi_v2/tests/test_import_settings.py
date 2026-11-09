"""The optional import settings default to the importer's earlier behaviour and reject malformed values."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'unreal' / 'Scripts'))
import import_settings as s  # noqa: E402


def test_absent_settings_change_nothing():
    for settings in ({}, {'collision': 'complex', 'triangles': 3, 'full_precision_uvs': True}):
        assert s.allow_cpu_access(settings) is None and s.double_sided(settings) is True
        assert s.max_texture_size(settings) is None and s.lod_group(settings) is None
        assert s.legacy_fbx(settings) is False


def test_present_settings_are_read():
    assert s.allow_cpu_access({'allow_cpu_access': True}) is True and s.allow_cpu_access({'allow_cpu_access': False}) is False
    assert s.double_sided({'double_sided': False}) is False
    assert s.max_texture_size({'max_texture_size': 2048}) == 2048
    assert s.lod_group({'lod_group': 'TEXTUREGROUP_EFFECTS'}) == 'TEXTUREGROUP_EFFECTS'


@pytest.mark.parametrize('call,settings', [(s.allow_cpu_access, {'allow_cpu_access': 1}), (s.double_sided, {'double_sided': 'no'}),
                                           (s.max_texture_size, {'max_texture_size': 1000}), (s.max_texture_size, {'max_texture_size': True}),
                                           (s.lod_group, {'lod_group': 'World'})])
def test_malformed_values_are_refused(call, settings):
    with pytest.raises(s.SettingError):
        call(settings)


def test_legacy_fbx_is_read():
    assert s.legacy_fbx({'legacy_fbx': True}) is True
    with pytest.raises(s.SettingError):
        s.legacy_fbx({'legacy_fbx': 'yes'})


def test_collision_trace_is_absent_by_default_and_checked():
    assert s.collision_trace({}) is None
    assert s.collision_trace({'collision_trace': 'CTF_USE_DEFAULT'}) == 'CTF_USE_DEFAULT'
    with pytest.raises(s.SettingError):
        s.collision_trace({'collision_trace': 'DEFAULT'})
