"""The Ski plugin's native simulation (Source/AtelierSki/Private/Native) outside Unreal: its own checks, and a scripted
park run that must match the browser lab's sim.js step for step."""
import shutil
import subprocess

import pytest

from atelier import paths

SKI = paths.PLATFORM / 'engine' / 'Plugins' / 'Activities' / 'Ski'
NATIVE = SKI / 'Source' / 'AtelierSki' / 'Private' / 'Native'


@pytest.fixture(scope='module')
def binary(tmp_path_factory):
    if not shutil.which('clang++'):
        pytest.skip('clang++ is not installed')
    out = tmp_path_factory.mktemp('ski') / 'ski_sim_test'
    sources = sorted(str(p) for p in NATIVE.glob('*.cpp')) + [str(SKI / 'Tests' / 'ski_sim_test.cpp')]
    subprocess.run(['clang++', '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror', '-fno-exceptions', '-fno-rtti',
                    f'-I{NATIVE}', *sources, '-o', str(out)], check=True, timeout=300)
    return out


def test_native_ski_checks(binary):
    result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr


def test_native_ski_matches_the_lab(binary):
    if not shutil.which('node'):
        pytest.skip('node is not installed')
    native = subprocess.run([str(binary), 'trace'], capture_output=True, text=True, check=True, timeout=120).stdout
    lab = subprocess.run(['node', str(SKI / 'Tests' / 'trace_sim.mjs')], capture_output=True, text=True, check=True,
                         timeout=120).stdout
    native_rows, lab_rows = native.split('\n'), lab.split('\n')
    assert len(native_rows) == len(lab_rows) > 50
    for a, b in zip(native_rows, lab_rows):
        for x, y in zip(a.split(), b.split()):
            assert abs(float(x) - float(y)) < 1e-6, f'native\n{a}\nlab\n{b}'
