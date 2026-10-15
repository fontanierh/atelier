"""A mixed executable, stale imported asset or modified runtime file changes session identity."""
import importlib.util
import io
from pathlib import Path, PureWindowsPath
import shutil
from types import SimpleNamespace

from atelier import build, paths
from atelier.build import DeferredInputs, Step
from atelier.build_deferred import observe
from atelier.build_products import Graph

import pytest

spec = importlib.util.spec_from_file_location('network_identity', Path(__file__).resolve().parents[1] / 'network_identity.py')
identity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(identity)


def write(root, relative, data):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def legacy_content_files(content):
    """The previous enumeration, retained as an exact membership/order reference."""
    return sorted((p for p in content.rglob('*') if p.is_file()
                   and not (set(p.relative_to(content).parts) & identity.IGNORED)
                   and p.name.casefold() not in identity.DESKTOP_METADATA
                   and not p.is_relative_to(content / 'Data/Network')),
                  key=lambda p: p.relative_to(content).as_posix())


@pytest.mark.parametrize('root', ['Content', 'deep/OtherName', 'Data/Network', 'Intermediate/Content'])
def test_content_enumeration_preserves_lexical_membership_and_order(tmp_path, root):
    content = tmp_path / root
    included = [
        '.git/config', 'a.txt', 'a/deep.uasset', 'Data/world.json',
        'Data/Networked/session.json', 'Data/Network.uasset',
        'Other/Data/Network/session.json', 'Network/session.json', 'Content/mesh.uasset',
        'BinariesData/mesh.uasset', 'intermediate/mesh.uasset', 'Data/Thumbs.db.json',
    ]
    excluded = [
        'Data/Network/session.json', 'Data/Network/deep/asset.uasset',
        'Data/.DS_Store', 'Data/THUMBS.DB', 'nested/thumbs.db',
        *[f'nested/{name}/deep/asset.uasset' for name in identity.IGNORED],
        'Saved',
    ]
    for name in included + excluded:
        write(content, name, b'content')
    actual = identity.content_files(content)
    assert actual == legacy_content_files(content)
    assert [p.relative_to(content).as_posix() for p in actual] == sorted(included)
    write(content, 'new/deep/mesh.uasset', b'new')
    (content / 'a.txt').unlink()
    assert identity.content_files(content) == legacy_content_files(content)
    assert content / 'new/deep/mesh.uasset' in identity.content_files(content)
    assert content / 'a.txt' not in identity.content_files(content)


def test_content_enumeration_preserves_file_and_directory_symlink_behavior(tmp_path):
    content = tmp_path / 'OtherRoot'
    target = write(tmp_path, 'external/asset.uasset', b'linked content')
    write(content, 'Data/world.json', b'world')
    (content / 'file.uasset').symlink_to(target)
    (content / 'directory').symlink_to(target.parent, target_is_directory=True)
    (content / 'broken.uasset').symlink_to(tmp_path / 'missing')
    (content / 'Saved').symlink_to(target)
    (content / 'Data/Network').mkdir()
    (content / 'Data/Network/linked.uasset').symlink_to(target)
    root_link = tmp_path / 'LinkedRoot'
    root_link.symlink_to(content, target_is_directory=True)
    for root in (content, root_link):
        actual = identity.content_files(root)
        assert actual == legacy_content_files(root)
        assert [p.relative_to(root).as_posix() for p in actual] == ['Data/world.json', 'file.uasset']


def test_content_enumeration_excludes_network_when_it_is_a_file(tmp_path):
    content = tmp_path / 'Content'
    write(content, 'Data/Network', b'identity output')
    other = write(content, 'Data/NetworkSibling', b'gameplay data')
    assert identity.content_files(content) == legacy_content_files(content) == [other]


def test_content_enumeration_keeps_differently_cased_network_directory(tmp_path):
    # Keep this separate from Data/Network for case-insensitive filesystems.
    content = tmp_path / 'Content'
    lower = write(content, 'Data/network/session.json', b'gameplay data')
    expected = [] if Path('a') == Path('A') else [lower]
    assert identity.content_files(content) == legacy_content_files(content) == expected


def test_content_enumeration_preserves_windows_lexical_path_rules():
    names = ['Data/network/a', 'data/Network/b', 'DATA/NETWORK/c',
             'Data/Networked/d', 'Other/Data/Network/e', 'saved/f', 'Saved/g']

    class WindowsFiles(PureWindowsPath):
        """Exercise Windows lexical rules without a Windows filesystem."""
        def rglob(self, pattern):
            return iter(self / name for name in names)

        def is_file(self):
            return True

    content = WindowsFiles('C:/different/root')
    actual = identity.content_files(content)
    assert actual == legacy_content_files(content)
    assert [p.relative_to(content).as_posix() for p in actual] == [
        'Data/Networked/d', 'Other/Data/Network/e', 'saved/f']


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


def test_network_provider_preserves_existing_selection_and_links(tmp_path):
    source = Path(identity.__file__)
    root = tmp_path / 'Content'; root.mkdir()
    for name in ('Data/Network/session.json', 'Other/Data/Network/keep', 'Data/Networked/keep', 'Mesh.uasset',
                 'Saved/no', 'nested/.DS_Store'):
        file = root / name; file.parent.mkdir(parents=True, exist_ok=True); file.write_text(name)
    (root / 'link.uasset').symlink_to(root / 'Mesh.uasset')
    (root / 'dir-link').symlink_to(root / 'Other', target_is_directory=True)
    step = Step('network', [], deferred_inputs=[DeferredInputs('content', identity.content_files, (root,), support=(source,))])
    assert observe(step).members == tuple(identity.content_files(root))
    assert [p.relative_to(root).as_posix() for p in observe(step).members] == [
        'Data/Networked/keep', 'Mesh.uasset', 'Other/Data/Network/keep', 'link.uasset']


def test_shipped_network_declaration_does_not_scan_content(monkeypatch):
    recipe = build.load_recipe('yorimichi')
    # Isolate only composition, without assembling unrelated world/character declarations.
    for name in ('world_steps', 'character_steps', 'sound_effect_steps', 'unreal_steps', 'staging_steps',
                 'adventure_steps', 'hippodrome_steps', 'belmonte_steps', 'fit_steps', 'pawn_steps'):
        monkeypatch.setattr(recipe, name, lambda *args: [])
    monkeypatch.setattr(recipe, 'staging_steps', lambda *args: [Step('data.stage', [])])
    monkeypatch.setattr(recipe, 'cook_step', lambda *args: Step('cook', []))
    monkeypatch.setattr(recipe, 'package_step', lambda *args: Step('package', []))
    def forbidden(*args):
        pytest.fail('recipe composition scanned generated content')
    monkeypatch.setattr(Path, 'rglob', forbidden)
    ctx = SimpleNamespace(out=paths.REPO / 'build/standin', uproject=recipe.GAME / 'unreal/Standin.uproject')
    declarations = recipe.steps(ctx)
    network = next(s for s in declarations if s.name == 'data.network')
    assert network.deferred_inputs[0].settings == (recipe.GAME / 'unreal/Content',)
    assert network.deferred_inputs[0].collect.__name__ == 'content_files'
    assert network.inputs[-1] == paths.ENGINE_PLUGINS
    Graph(declarations)
