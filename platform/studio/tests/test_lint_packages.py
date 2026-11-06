"""Lint finds personal paths inside committed Unreal package bytes, in either string encoding."""
from atelier import cli

HOME = '/' + 'Users/somebody/donor/bench.glb'   # built at runtime so lint never sees a literal home path


def test_latin1_and_utf16_home_paths_are_found():
    plain = b'\x00\x01SourceFile=' + HOME.encode() + b'\x00'
    wide = HOME.encode('utf-16-le')
    for data in (plain, b'\x07' + wide, wide):
        assert cli.package_problems('x.uasset', data) == ['x.uasset: a home-directory path inside the package bytes']


def test_engine_paths_and_clean_packages_pass():
    assert cli.package_problems('x.uasset', b'/Users/Shared/Epic Games/UE_5.8/Engine/Content\x00/Game/Japan/SM_Bench') == []


def test_tailnet_hostname_is_found():
    assert cli.package_problems('x.umap', ('http://box.tail1234ab.ts' + '.net/x').encode()) == [
        'x.umap: a tailnet hostname inside the package bytes']


def test_an_lfs_pointer_without_local_content_is_skipped():
    pointer = b'version https://git-lfs.github.com/spec/v1\noid sha256:' + b'0' * 64 + b'\nsize 12\n'
    assert cli.package_problems('x.uasset', pointer) == []
