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


@pytest.mark.parametrize('relative', [
    'games/yorimichi/unreal/Source/Yorimichi/Player.cpp',
    'games/yorimichi/unreal/Config/DefaultEngine.ini',
    'platform/engine/Plugins/Skate/Source/Ride.cpp',
])
def test_source_line_endings_preserve_identity_but_code_edits_do_not(project, relative):
    repo, content = project
    source = b'first line\nsecond line\n'
    write(repo, relative, source)
    expected = identity.create(repo, content, io.StringIO())
    write(repo, relative, source.replace(b'\n', b'\r\n'))
    assert identity.create(repo, content, io.StringIO()) == expected
    write(repo, relative, source.replace(b'first', b'changed'))
    assert identity.create(repo, content, io.StringIO())['code'] != expected['code']


def test_lone_carriage_return_in_source_is_not_normalized(project):
    repo, content = project
    path = 'games/yorimichi/unreal/Source/Yorimichi/Player.cpp'
    write(repo, path, b'first\rsecond\n')
    first = identity.create(repo, content, io.StringIO())
    write(repo, path, b'first\nsecond\n')
    assert identity.create(repo, content, io.StringIO())['code'] != first['code']


@pytest.mark.parametrize('relative', ['Data/moves.json', 'Japan/Collision.uasset'])
def test_runtime_content_line_endings_are_still_byte_exact(project, relative):
    repo, content = project
    write(content, relative, b'first\nsecond\n')
    first = identity.create(repo, content, io.StringIO())
    write(content, relative, b'first\r\nsecond\r\n')
    assert identity.create(repo, content, io.StringIO())['signature'] != first['signature']


@pytest.mark.parametrize('name', ['Thumbs.db', 'THUMBS.DB', '.DS_Store'])
def test_desktop_metadata_does_not_join_the_gameplay_manifest(project, name):
    repo, content = project
    first = identity.create(repo, content, io.StringIO())
    write(content, 'Data/nested/' + name, b'desktop cache')
    assert identity.create(repo, content, io.StringIO()) == first
    write(content, 'Data/nested/' + name + '.json', b'gameplay data')
    assert identity.create(repo, content, io.StringIO())['signature'] != first['signature']


@pytest.mark.parametrize('relative', [
    'games/yorimichi/unreal/Config/DefaultEngine.ini',
    'games/yorimichi/unreal/Yorimichi.uproject',
    'platform/engine/Plugins/Skate/Config/DefaultSkate.ini',
])
def test_gameplay_configuration_changes_executable_identity(project, relative):
    repo, content = project
    write(repo, relative, b'original settings')
    first = identity.create(repo, content, io.StringIO())
    write(repo, relative, b'changed physics or plugin settings')
    second = identity.create(repo, content, io.StringIO())
    assert second['code'] != first['code']
    assert second['signature'] != first['signature']
