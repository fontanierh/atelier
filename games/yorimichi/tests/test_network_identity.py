"""A mixed executable, stale imported asset or modified runtime file changes session identity."""
import importlib.util
import io
from pathlib import Path
import shutil

import pytest

spec = importlib.util.spec_from_file_location('network_identity', Path(__file__).resolve().parents[1] / 'network_identity.py')
identity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(identity)


def write(root, relative, data):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


@pytest.fixture
def project(tmp_path):
    write(tmp_path, 'games/yorimichi/unreal/Source/Yorimichi/Player.cpp', b'game logic')
    write(tmp_path, 'platform/engine/Plugins/Skate/Source/Ride.cpp', b'skate physics')
    content = tmp_path / 'games/yorimichi/unreal/Content'
    write(content, 'Data/world.json', b'{"start": [1,2,3]}')
    write(content, 'Data/moves.json', b'{"jump": 1}')
    write(content, 'Japan/Maps/Slice.umap', b'imported level')
    write(content, 'Japan/Collision.uasset', b'actual imported collision')
    return tmp_path, content


def test_identity_survives_checkout_path_and_ignores_its_own_output(project, tmp_path):
    repo, content = project
    first = identity.create(repo, content, io.StringIO())
    write(repo, 'platform/engine/Plugins/Skate/Intermediate/junk.cpp', b'generated output')
    write(content, '.DS_Store', b'finder metadata')
    assert identity.create(repo, content, io.StringIO()) == first
    clone = tmp_path.parent / (tmp_path.name + '-clone')
    shutil.copytree(repo, clone)
    assert identity.create(clone, clone / content.relative_to(repo), io.StringIO()) == first


@pytest.mark.parametrize('relative', ['Data/moves.json', 'Japan/Collision.uasset', 'Data/new-rail.json'])
def test_actual_content_bytes_change_compatibility(project, relative):
    repo, content = project
    first = identity.create(repo, content, io.StringIO())
    write(content, relative, b'different or extra gameplay data')
    assert identity.create(repo, content, io.StringIO())['signature'] != first['signature']


def test_plugin_gameplay_code_is_part_of_the_executable_identity(project):
    repo, content = project
    first = identity.create(repo, content, io.StringIO())
    write(repo, 'platform/engine/Plugins/Skate/Source/Ride.cpp', b'changed skate physics')
    second = identity.create(repo, content, io.StringIO())
    assert second['code'] != first['code']
    assert second['signature'] != first['signature']


def test_missing_world_cannot_be_certified(project):
    repo, content = project
    (content / 'Data/world.json').unlink()
    with pytest.raises(ValueError, match='before world data'):
        identity.create(repo, content, io.StringIO())
    assert not (content / 'Data/Network/session.json').exists()
