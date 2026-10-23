"""Recovery's opt-in default-tool policy; all native discovery is mocked."""
import importlib.util
import io
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier import build_cook_recovery as recovery, paths

# Xcode and the Metal SDK selectors only exist there, so this file runs in the macOS CI group and
# skips anywhere else.
pytestmark = [pytest.mark.macos_only,
              pytest.mark.skipif(sys.platform != 'darwin',
                                 reason='cook recovery pins the default Xcode and Metal SDK selections')]

def cook_tool():
    source = Path(__file__).parents[1] / 'tools/package_cook.py'
    spec = importlib.util.spec_from_file_location('package_cook_tools_fixture', source)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


@pytest.fixture
def selection(tmp_path, monkeypatch):
    cook = cook_tool()
    monkeypatch.setattr(Path, 'home', lambda: tmp_path / 'home')
    monkeypatch.setattr(os, 'environ', {})
    ctx = SimpleNamespace(unreal_root=tmp_path / 'engine', game_dir=tmp_path / 'game',
                          out=tmp_path / 'build', uproject=tmp_path / 'game/Game.uproject', record_cook_recovery=True)
    (ctx.unreal_root / 'Engine').mkdir(parents=True)
    architecture = 'arm64' if os.uname().machine == 'arm64' else 'x64'
    dotnet = ctx.unreal_root / 'Engine/Binaries/ThirdParty/DotNet/10.0' / ('mac-' + architecture) / 'dotnet'
    dotnet.parent.mkdir(parents=True); dotnet.write_bytes(b'bundled dotnet'); dotnet.chmod(0o755)
    developer = tmp_path / 'Xcode.app/Contents/Developer'
    (developer / 'Toolchains').mkdir(parents=True)
    sdks, owners, executables, libraries = {}, {}, {}, {}
    for sdk, platform in [('macosx', 'MacOSX'), ('iphoneos', 'iPhoneOS')]:
        sdks[sdk] = developer / f'Platforms/{platform}.platform/Developer/SDKs/{platform}26.sdk'
        sdks[sdk].mkdir(parents=True)
        (sdks[sdk].parent / f'{platform}.sdk').symlink_to(sdks[sdk].name)
        owners[sdk] = tmp_path / f'downloads/{sdk}/Metal.xctoolchain'
        libraries[sdk] = owners[sdk] / 'usr/metal'
        libraries[sdk].mkdir(parents=True)
        (libraries[sdk] / 'resource').write_bytes(b'original library')
        executables[sdk] = {}
        for name in ('metal', 'metal-ar', 'metallib', 'metal-pack', 'metal-strip'):
            executable = owners[sdk] / 'usr/bin' / name
            executable.parent.mkdir(parents=True, exist_ok=True); executable.write_bytes(b'executable')
            executable.chmod(0o755); executables[sdk][name] = executable
    packaging = developer / 'usr/bin/package-tool'
    packaging.parent.mkdir(parents=True); packaging.write_bytes(b'packaging tool')
    packaging.chmod(0o755)
    calls = []
    def output(argv, **kwargs):
        calls.append(argv)
        assert 0 < kwargs['timeout'] <= 10
        if argv == ['/usr/bin/xcode-select', '-p']: return str(developer)
        if argv[0] == '/usr/bin/xcrun':
            if '--sdk' in argv:
                sdk = argv[2]
                if argv[3:] == ['metal', '--print-search-dirs']:
                    return 'programs: =irrelevant\nlibraries: =' + str(libraries[sdk])
                return str(sdks[sdk] if argv[3] == '--show-sdk-path' else executables[sdk][argv[4]])
            return str(packaging)
        raise AssertionError(argv)
    import subprocess
    monkeypatch.setattr(subprocess, 'check_output', output)
    system = lambda name: ('/bin/' if name in ('realpath', 'chmod', 'bash', 'sh') else '/usr/bin/') + name
    monkeypatch.setattr(cook.shutil, 'which', system)
    monkeypatch.setattr(cook, 'recovery_config_inputs', lambda _: [])
    monkeypatch.setattr(paths, 'ENGINE_PLUGINS', tmp_path / 'platform-plugins')
    return SimpleNamespace(cook=cook, ctx=ctx, developer=developer, sdks=sdks, owners=owners,
                           executables=executables, libraries=libraries, calls=calls, output=output, dotnet=dotnet, system=system)


@pytest.mark.parametrize('name', ['DEVELOPER_DIR', 'TOOLCHAINS', 'BASH_ENV', 'ENV', 'UE-CmdLineArgs',
    'UE_DOTNET_DIR', 'UE_USE_SYSTEM_DOTNET', 'UE_SDKS_ROOT', 'UE_AUTOSDK_SPECIFIC_LEVELS', 'DOTNET_ROOT',
    'COREHOST_TRACEFILE', 'CORECLR_ENABLE_PROFILING', 'COMPlus_AltJitName', 'DYLD_INSERT_LIBRARIES',
    'MSBuildSDKsPath', 'MSBuildExtensionsPath', 'MSBUILD_EXE_PATH', 'NUGET_PLUGIN_PATHS',
    'UnrealBuildTool_Mac__Compiler', 'UBT_Mac__Compiler', 'LINUXAutoSDKSetup', 'MacManualSDKSetup',
    'CDPATH', 'IFS', 'BASHOPTS', 'SHELLOPTS', 'POSIXLY_CORRECT', 'BASH_FUNC_realpath%%'])
def test_override_refuses_before_deleting_archive_or_discovering_tools(selection, monkeypatch, name):
    cook, ctx = selection.cook, selection.ctx
    monkeypatch.setenv(name, 'private selector value')
    archive = ctx.out / 'package/archive/old.app'; archive.mkdir(parents=True)
    receipt = ctx.out / 'package/cook.json'; receipt.write_bytes(b'old receipt')
    with pytest.raises(RuntimeError, match='unsupported environment names') as error:
        cook.prepare(ctx, io.StringIO())
    assert name in str(error.value) and 'private selector value' not in str(error.value)
    assert archive.is_dir() and receipt.read_bytes() == b'old receipt' and not selection.calls


@pytest.mark.parametrize('hook', [0, 1, 2])
@pytest.mark.parametrize('kind', ['file', 'dangling-link'])
def test_startup_hooks_refuse_before_deletion(selection, hook, kind):
    cook, ctx = selection.cook, selection.ctx
    path = cook.recovery_shell_hooks(ctx)[hook]; path.parent.mkdir(parents=True, exist_ok=True)
    if kind == 'file': path.write_text('external selector')
    else: path.symlink_to('missing hook')
    archive = ctx.out / 'package/archive/old.app'; archive.mkdir(parents=True)
    with pytest.raises(RuntimeError, match='startup hooks'):
        cook.prepare(ctx, io.StringIO())
    assert archive.is_dir() and not selection.calls


@pytest.mark.parametrize('value', ['', 'macosx', '/missing/SDK.sdk'])
def test_unsupported_sdkroot_refuses_before_deleting_archive(selection, monkeypatch, value):
    monkeypatch.setenv('SDKROOT', value)
    archive = selection.ctx.out / 'package/archive/old.app'; archive.mkdir(parents=True)
    with pytest.raises(RuntimeError, match='SDKROOT.*absolute .sdk directory'):
        selection.cook.prepare(selection.ctx, io.StringIO())
    assert archive.is_dir() and not selection.calls


def test_explicit_sdkroot_is_selected_and_its_complete_bytes_are_inputs(selection, monkeypatch):
    sdk = selection.ctx.out / 'Other.sdk'; sdk.mkdir(parents=True)
    header = sdk / 'usr/include/version.h'; header.parent.mkdir(parents=True); header.write_bytes(b'first')
    alias = selection.ctx.out / 'Current.sdk'; alias.symlink_to(sdk)
    monkeypatch.setenv('SDKROOT', str(alias))
    result = selection.cook.recovery_inputs(selection.ctx)
    assert result.selection['environment_sdkroot'] == str(sdk)
    assert sdk in result.roots and sdk in result.link_owners
    before = recovery.inventory([sdk], hashes=True)
    header.write_bytes(b'second')
    assert recovery.inventory([sdk], hashes=True) != before
    other = selection.ctx.out / 'Third.sdk'; other.mkdir()
    alias.unlink(); alias.symlink_to(other)
    assert selection.cook.recovery_inputs(selection.ctx).selection['environment_sdkroot'] != result.selection['environment_sdkroot']


def test_sdkroot_retains_ancestor_and_chained_link_identity_even_for_same_resolved_sdk(selection, monkeypatch):
    sdk = selection.ctx.out / 'SDKs/Version.sdk'; sdk.mkdir(parents=True)
    link = sdk.parent / 'Current.sdk'; link.symlink_to(sdk.name)
    indirect = sdk.parent / 'Indirect.sdk'; indirect.symlink_to(link.name)
    alias = selection.ctx.out / 'SDK-alias'; alias.symlink_to(sdk.parent)
    monkeypatch.setenv('SDKROOT',str(alias/indirect.name))
    before = selection.cook.recovery_inputs(selection.ctx)
    links = before.selection['environment_sdkroot_links']
    assert links[str(alias)]['link'] == str(sdk.parent)
    assert links[str(alias/indirect.name)]['link'] == link.name
    assert links[str(alias/link.name)]['link'] == sdk.name
    link.unlink(); link.symlink_to(sdk.name)
    after = selection.cook.recovery_inputs(selection.ctx)
    assert after.selection['environment_sdkroot'] == before.selection['environment_sdkroot']
    assert after.selection['environment_sdkroot_links'] != links


def test_nonrecording_prepare_uses_no_new_policy_or_tool_discovery(selection, monkeypatch):
    cook, ctx = selection.cook, selection.ctx
    ctx.record_cook_recovery = False
    monkeypatch.setenv('UE_DOTNET_DIR', 'unsupported custom runtime')
    monkeypatch.setattr(cook, 'source_snapshot', lambda _: {'revision': 'a'*40})
    cook.prepare(ctx, io.StringIO())
    assert not selection.calls


@pytest.mark.parametrize('name', ['xcode-select', 'xcrun', 'uname', 'which', 'dirname', 'env', 'realpath', 'chmod', 'bash', 'sh'])
def test_path_shadowing_refuses_even_with_valid_absolute_discovery(selection, monkeypatch, name):
    shim = selection.ctx.out / 'shim'; shim.parent.mkdir(); shim.write_text('mutable shim')
    monkeypatch.setattr(selection.cook.shutil, 'which', lambda item: str(shim) if item == name else selection.system(item))
    with pytest.raises(RuntimeError, match='PATH-shadowed'):
        selection.cook.recovery_tool_selection()
    assert not selection.calls


def test_selection_covers_both_sdk_and_full_resources_once(selection, monkeypatch):
    result = selection.cook.recovery_inputs(selection.ctx)
    assert isinstance(result, recovery.NativeCookInputs)
    assert set(result.selection['sdks']) == {'macosx', 'iphoneos'}
    assert selection.developer.parent in result.roots and selection.developer.parent in result.link_owners
    assert set(selection.owners.values()) <= set(result.roots) & set(result.link_owners)
    assert selection.calls.count(['/usr/bin/xcode-select', '-p']) == 1
    for sdk in ('macosx', 'iphoneos'):
        assert ['/usr/bin/xcrun', '--sdk', sdk, 'metal', '--print-search-dirs'] in selection.calls
    for sdk, tools in result.selection['sdks'].items():
        assert tools['path'] == str(selection.sdks[sdk])
        assert set(tools['metal']) == {'metal', 'metal-ar', 'metallib', 'metal-pack', 'metal-strip', 'library'}
    # Resource-only changes must invalidate, even with unchanged compiler bytes.
    roots = [selection.developer.parent, *selection.owners.values()]
    before = recovery.inventory(roots, hashes=True)
    (selection.libraries['iphoneos'] / 'resource').write_bytes(b'changed library')
    assert recovery.inventory(roots, hashes=True) != before


def test_metal_library_probe_uses_the_same_sdk_context_as_unreal(selection, monkeypatch):
    import subprocess
    def output(argv, **kwargs):
        if argv[0] in {str(tools['metal']) for tools in selection.executables.values()}:
            return 'libraries: =' + str(selection.developer)  # No SDK context gives a different resource path.
        return selection.output(argv, **kwargs)
    monkeypatch.setattr(subprocess, 'check_output', output)
    selected = selection.cook.recovery_tool_selection()
    for sdk in ('macosx', 'iphoneos'):
        assert selected['sdks'][sdk]['metal']['library'] == str(selection.libraries[sdk])


def test_platform_swift_plugin_resources_are_part_of_the_input_inventory(selection):
    roots = [selection.developer.parent, *selection.owners.values()]
    plugin = selection.developer / 'Platforms/MacOSX.platform/Developer/usr/lib/swift/host/plugins/plugin'
    plugin.parent.mkdir(parents=True); plugin.write_bytes(b'Swift plugin')
    before = recovery.inventory(roots, hashes=True)
    plugin.write_bytes(b'changed Swift plugin')
    assert recovery.inventory(roots, hashes=True) != before


def test_sdk_alias_disagreement_and_retarget_refuse(selection):
    alias = selection.sdks['macosx'].parent / 'MacOSX.sdk'
    alias.unlink(); alias.symlink_to(selection.sdks['iphoneos'])
    with pytest.raises(RuntimeError, match='reconcile'):
        selection.cook.recovery_tool_selection()


@pytest.mark.parametrize('failure', ['unknown-tool-owner', 'external-metal-library'])
def test_unowned_resources_refuse_instead_of_expanding_owners(selection, monkeypatch, failure):
    import subprocess
    def output(argv, **kwargs):
        if failure == 'unknown-tool-owner' and argv[-1] == 'metal':
            return str(selection.developer / 'usr/bin/package-tool')
        if failure == 'external-metal-library' and argv[-1] == '--print-search-dirs':
            return 'libraries: =' + str(selection.developer)
        return selection.output(argv, **kwargs)
    monkeypatch.setattr(subprocess, 'check_output', output)
    with pytest.raises(RuntimeError, match='resource owner'):
        selection.cook.recovery_tool_selection()


def test_hook_appearing_after_capture_refuses_rediscovery(selection):
    result = selection.cook.recovery_inputs(selection.ctx)
    hook = selection.cook.recovery_shell_hooks(selection.ctx)[0]
    assert hook in result.roots
    hook.parent.mkdir(); hook.write_text('changed tool selection')
    with pytest.raises(RuntimeError, match='startup hooks'):
        selection.cook.recovery_inputs(selection.ctx)


def test_selection_deadline_refuses_instead_of_starting_native_work(selection, monkeypatch):
    ticks = iter([0, 31])
    monkeypatch.setattr(selection.cook.time, 'monotonic', lambda: next(ticks))
    with pytest.raises(RuntimeError, match='exceeded 30 seconds'):
        selection.cook.recovery_tool_selection()
    assert not selection.calls


def test_repeat_chmod_accepts_only_ctime_of_declared_bundled_runtime(selection):
    path = selection.dotnet
    before = recovery.inventory([path.parent], hashes=True, repeat_chmod_files=[path])
    path.chmod(0o755)
    after = recovery.inventory([path.parent], hashes=True, repeat_chmod_files=[path])
    assert before == after
    assert selection.cook.recovery_dotnet_input(selection.ctx) == path
    result = selection.cook.recovery_inputs(selection.ctx)
    assert result.repeat_chmod_files == [path] and result.selection['dotnet'] == str(path)


@pytest.mark.parametrize('change', ['bytes-restored-mtime', 'mode', 'inode', 'mtime'])
def test_repeat_chmod_keeps_content_and_other_file_identity_exact(selection, change):
    from atelier.build_hashes import HashIndex
    path = selection.dotnet
    with HashIndex(selection.ctx.out / 'hashes.sqlite3') as index:
        before = recovery.inventory([path], hashes=True, hasher=index.digest, repeat_chmod_files=[path])
        info = path.stat()
        if change == 'bytes-restored-mtime':
            path.write_bytes(b'changed dotnet')
            os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns))
        elif change == 'mode': path.chmod(0o700)
        elif change == 'inode':
            other = path.with_name('replacement'); other.write_bytes(path.read_bytes())
            other.chmod(0o755); os.utime(other, ns=(info.st_atime_ns, info.st_mtime_ns)); other.replace(path)
        else: os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + 1_000_000))
        assert recovery.inventory([path], hashes=True, hasher=index.digest, repeat_chmod_files=[path]) != before


def test_repeat_chmod_never_hides_mutation_during_inventory(selection):
    path = selection.dotnet
    def changing_hasher(item):
        item.chmod(0o755)
        return 'not trusted merely because a hasher returned'
    with pytest.raises(RuntimeError, match='changed during inventory'):
        recovery.inventory([path], hashes=True, hasher=changing_hasher, repeat_chmod_files=[path])


def test_other_tools_still_pin_ctime(selection):
    path = selection.executables['macosx']['metal']
    before = recovery.inventory([path, selection.dotnet], hashes=True, repeat_chmod_files=[selection.dotnet])
    path.chmod(0o755)
    assert recovery.inventory([path, selection.dotnet], hashes=True, repeat_chmod_files=[selection.dotnet]) != before


@pytest.mark.parametrize('damage', ['missing', 'symlink', 'not-executable'])
def test_nondefault_or_unprimed_dotnet_refuses_before_deletion(selection, damage):
    path = selection.dotnet
    if damage == 'not-executable': path.chmod(0o644)
    else:
        path.unlink()
        if damage == 'symlink': path.symlink_to(selection.executables['macosx']['metal'])
    archive = selection.ctx.out / 'package/archive/old.app'; archive.mkdir(parents=True)
    with pytest.raises(RuntimeError, match='bundled default dotnet'):
        selection.cook.prepare(selection.ctx, io.StringIO())
    assert archive.is_dir() and not selection.calls
