"""V2 commits its editable Unreal content through lockable Git LFS, and only temporary outputs stay ignored."""
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
V2 = 'games/yorimichi_v2'

pytestmark = pytest.mark.skipif(shutil.which('git') is None or not (REPO / '.git').exists(), reason='needs a git checkout')


def ignored(path: str) -> bool:
    return subprocess.run(['git', 'check-ignore', '-q', '--no-index', path], cwd=REPO).returncode == 0


def attrs(path: str) -> dict:
    out = subprocess.run(['git', 'check-attr', 'filter', 'lockable', 'diff', '--', path], cwd=REPO,
                         capture_output=True, text=True, check=True).stdout
    return {line.split(': ')[1]: line.split(': ')[2] for line in out.splitlines()}


@pytest.mark.parametrize('path', [
    f'{V2}/unreal/Content/Japan/Maps/Island.umap',
    f'{V2}/unreal/Content/__ExternalActors__/Japan/Maps/Island/0/AB/C5UDZYKFL5M0YW62JXMPIZ.uasset',
    f'{V2}/unreal/Content/Japan/Props/SM_Bench.uasset',
    f'{V2}/unreal/Content/Japan/Props/SM_Bench.ubulk',
    f'{V2}/unreal/Config/DefaultEngine.ini',
    f'{V2}/assets/props/bench/asset.toml',
])
def test_editable_content_and_records_are_tracked(path):
    assert not ignored(path)


@pytest.mark.parametrize('path', [
    f'{V2}/unreal/Saved/Logs/YorimichiV2.log',
    f'{V2}/unreal/Intermediate/Build/x.o',
    f'{V2}/unreal/Binaries/Mac/YorimichiV2Editor.dylib',
    f'{V2}/unreal/DerivedDataCache/a.ddp',
    'games/yorimichi/unreal/Content/Japan/Maps/Island.umap',   # the original game keeps generated content
])
def test_temporary_outputs_stay_ignored(path):
    assert ignored(path)


@pytest.mark.parametrize('suffix', ['uasset', 'umap', 'ubulk', 'uexp', 'glb', 'png', 'wav', 'blend'])
def test_binaries_are_lockable_lfs(suffix):
    found = attrs(f'{V2}/unreal/Content/X/Y.{suffix}')
    assert found['filter'] == 'lfs' and found['lockable'] == 'set'


@pytest.mark.parametrize('name', ['unreal/Config/DefaultEngine.ini', 'assets/props/bench/asset.toml',
                                  'assets/props/bench/verified.json', 'unreal/YorimichiV2.uproject'])
def test_text_stays_mergeable_text(name):
    found = attrs(f'{V2}/{name}')
    assert found['filter'] == 'unspecified' and found['lockable'] == 'unspecified'
