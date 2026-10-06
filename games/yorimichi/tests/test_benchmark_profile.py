"""A fullscreen capture must exercise its requested session profile, not just the viewport."""
import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def benchmark():
    path = Path(__file__).resolve().parents[1] / 'tools' / 'benchmark.py'
    spec = importlib.util.spec_from_file_location('benchmark_profile_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_missing_session_key_enables_desktop_without_changing_other_settings(benchmark):
    assert benchmark.desktop_settings('') == 'desktop=1'
    assert benchmark.desktop_settings('performance=0;render_scale=85') == 'performance=0;render_scale=85;desktop=1'


def test_explicit_baseline_and_duplicate_last_value_remain_authoritative(benchmark):
    baseline = 'desktop=1;performance=0;desktop=0'
    assert benchmark.desktop_settings(baseline) == baseline
    benchmark.verify_desktop_profile({'desktop': 0}, baseline)
    with pytest.raises(RuntimeError):
        benchmark.verify_desktop_profile({'desktop': 1}, baseline)


@pytest.mark.parametrize('profile', [None, {}, {'desktop': 0}])
def test_missing_or_ineffective_profile_cannot_pass_desktop_capture(benchmark, profile):
    with pytest.raises(RuntimeError):
        benchmark.verify_desktop_profile(profile, 'desktop=1')


def test_logged_effective_desktop_profile_passes(benchmark):
    benchmark.verify_desktop_profile({'desktop': 1}, 'performance=1;desktop=1')


@pytest.mark.parametrize('value', ['', 'invalid', 'nan', 'inf'])
def test_invalid_override_fails_before_capture(benchmark, value):
    with pytest.raises(ValueError, match='desktop must be a finite number'):
        benchmark.desktop_settings('desktop=' + value)
