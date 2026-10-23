"""Unreal imports sharing a Content folder own exactly the files they wrote; no Unreal launches."""
import json
import os
from pathlib import Path
import shutil
import time
from types import SimpleNamespace

import pytest

from atelier import build, build_cache, build_checkpoints, checkpoint_actions as actions, checkpoint_store as cp, paths
from atelier import package_ownership


def save_line(content, relative):
    destination = f'../../../../{content.parent.parent.name}/{content.parent.name}/Content/{relative}'
    return f"[0]LogSavePackage: Moving '../../Saved/tmp1.tmp' to '{destination}'\n"


KEI = ['Japan/Assets/SM_Kei.uasset', 'Japan/Assets/SM_Kei_Pickup.uasset', 'Japan/Materials/MI_Kei.uasset']
LAKE = ['Japan/Assets/SM_Lake.uasset', 'Japan/Materials/MI_Water.uasset']


@pytest.fixture
def shared(tmp_path, monkeypatch):
    repo = tmp_path.resolve(); (repo / 'uv.lock').write_text('lock')
    monkeypatch.setattr(paths, 'REPO', repo)
    monkeypatch.setattr(paths, 'ENGINE_PLUGINS', repo / 'plugins')
    monkeypatch.setattr(paths, 'build_root', lambda: repo / 'build')
    monkeypatch.setenv('ATELIER_CACHE', str(repo / 'cache'))
    project = repo / 'game/unreal'; project.mkdir(parents=True)
    content = project / 'Content'
    ctx = SimpleNamespace(game='fixture', out=repo / 'build/fixture', logs=repo / 'build/fixture/logs',
                          stamps=repo / 'build/fixture/stamps', cook_mode=build.CookMode.DEFAULT,
                          uproject=project / 'Game.uproject', unreal_root=None,
                          checkpoint_observed_context='fixture context')
    ctx.uproject.write_text('{}')
    saves = {'unreal.kei': list(KEI), 'unreal.lake': list(LAKE)}
    steps = []
    for name in saves:
        script = repo / (name + '.py'); script.write_text('# import ' + name)
        steps.append(build.Step(name, [build.UnrealScript(script, 'IMPORT COMPLETE')], inputs=[script]))
    monkeypatch.setattr(build, 'Context', lambda *a, **kw: ctx)
    monkeypatch.setattr(build, 'load_recipe', lambda _: SimpleNamespace(steps=lambda ctx: steps))
    monkeypatch.setattr(build_checkpoints, 'configured', lambda ctx: {})
    monkeypatch.setattr(build_checkpoints, 'prepare', lambda *a, **kw: None)
    monkeypatch.setattr(build_cache, 'tool_context', lambda *a, **kw: dict(tool='fixed'))
    launches = []

    def run(ctx, step, command, log, *args, **kw):  # Stands in for the Unreal editor, Python and calls.
        launches.append(step.name)
        for relative in saves[step.name]:
            if callable(relative):  # Any other effect, such as removing a replaced file.
                relative()
                continue
            if isinstance(relative, Path):  # A generated file a script writes.
                relative.parent.mkdir(parents=True, exist_ok=True)
                relative.write_bytes(b'generated ' + relative.name.encode())
                continue
            (content / relative).parent.mkdir(parents=True, exist_ok=True)
            (content / relative).write_bytes(b'package ' + relative.encode())
            log.write(save_line(content, relative))
    monkeypatch.setattr(build, 'run_command', run)
    messages = []
    def add(step, writes):
        steps.append(step)
        saves[step.name] = list(writes)
    return SimpleNamespace(ctx=ctx, content=content, launches=launches, saves=saves, messages=messages, add=add,
                           stamp=lambda name: json.loads((ctx.stamps / (name + '.json')).read_text()),
                           run=lambda **kw: build.build('fixture', echo=messages.append, **kw))


def entries():
    return sorted((cp.Store('fixture').directory / 'actions').glob('*.json'))


def test_deleting_one_steps_files_from_a_shared_folder_restores_only_them(shared):
    p = shared
    assert p.run() == 0 and p.launches == ['unreal.kei', 'unreal.lake']
    kei, lake = p.stamp('unreal.kei'), p.stamp('unreal.lake')
    assert kei['checkpoint_packages'] == ['content/' + n for n in sorted(KEI)]
    assert 'checkpoint_local' not in kei and 'checkpoint_local' not in lake
    entry = json.loads(actions.entry_path(cp.Store('fixture'), kei['checkpoint_key']).read_text())
    assert [r['path'] for r in entry['roots']] == kei['checkpoint_packages']  # Files, never folders.
    assert all(r['kind'] == 'file' for r in entry['roots'])
    neighbours = {n: os.stat(p.content / n) for n in LAKE}
    for name in KEI:
        (p.content / name).unlink()
    started = time.monotonic()
    assert p.run() == 0
    assert time.monotonic() - started < 5
    assert p.launches == ['unreal.kei', 'unreal.lake']  # Restored, not relaunched.
    assert any(m.startswith('unreal.kei') and 'restored in' in m and 'checkpoint action' in m for m in p.messages)
    for name in KEI:
        assert (p.content / name).read_bytes() == b'package ' + name.encode()
    for name, before in neighbours.items():  # The other step's files in the same folders are untouched.
        after = os.stat(p.content / name)
        assert (after.st_ino, after.st_mtime_ns, after.st_size) == (before.st_ino, before.st_mtime_ns, before.st_size)
    assert sorted(p.content.rglob('*.uasset')) == sorted(p.content / n for n in KEI + LAKE)


def test_a_path_two_steps_save_stays_unpublished_for_both_and_is_listed(shared):
    p = shared
    p.saves['unreal.lake'].append('Japan/Assets/Sea.uasset')
    p.saves['unreal.kei'].append('Japan/Assets/Sea.uasset')
    assert p.run() == 0
    assert p.stamp('unreal.lake')['checkpoint_local'][0].startswith('content/Japan/Assets/Sea.uasset also written by unreal.kei')
    assert any('kept local, not published' in m and 'Sea.uasset' in m for m in p.messages)
    listed = package_ownership.report(cp.Store('fixture'))
    assert listed['contested'] == {'content/Japan/Assets/Sea.uasset': ['unreal.kei', 'unreal.lake']}
    # kei published before the second writer appeared; its entry is never restored now.
    for name in KEI:
        (p.content / name).unlink()
    p.messages.clear()
    assert p.run() == 0
    assert p.launches == ['unreal.kei', 'unreal.lake', 'unreal.kei']
    assert any('saved result not restored' in m and 'Sea.uasset also written by unreal.lake' in m for m in p.messages)
    assert p.stamp('unreal.kei')['checkpoint_local']


def test_a_changed_written_set_for_identical_inputs_stays_local_and_is_listed(shared):
    p = shared
    assert p.run() == 0 and len(entries()) == 2
    p.saves['unreal.kei'].pop()
    assert p.run(wanted=('unreal.kei',), force=True, rebuild_reason='unreal.kei=test') == 0
    stamp = p.stamp('unreal.kei')
    assert stamp['checkpoint_local'][0].startswith('written set changed for identical inputs')
    assert package_ownership.report(cp.Store('fixture'))['nondeterministic'] == ['unreal.kei']
    # The step stays local: its saved result is no longer restored either.
    for name in p.saves['unreal.kei']:
        (p.content / name).unlink()
    assert p.run() == 0 and p.launches.count('unreal.kei') == 3


def test_an_unclaimed_file_beside_the_written_packages_keeps_the_run_local(shared):
    p = shared
    (p.content / 'Japan/Assets').mkdir(parents=True)
    (p.content / 'Japan/Assets/SM_Unchanged.uasset').write_bytes(b'skipped as not dirty')
    assert p.run() == 0
    assert p.stamp('unreal.kei')['checkpoint_local'] == ['content/Japan/Assets/SM_Unchanged.uasset present but not rewritten']
    assert not any(json.loads(e.read_text())['task'] == 'unreal.kei' for e in entries())


def test_a_file_written_in_an_earlier_run_but_not_now_keeps_the_run_local(shared):
    p = shared
    assert p.run() == 0
    p.saves['unreal.kei'].remove('Japan/Materials/MI_Kei.uasset')
    (paths.REPO / 'unreal.kei.py').write_text('# import unreal.kei, revised')  # New inputs, new key.
    assert p.run() == 0 and p.launches == ['unreal.kei', 'unreal.lake', 'unreal.kei']
    assert p.stamp('unreal.kei')['checkpoint_local'] == ['content/Japan/Materials/MI_Kei.uasset present but not rewritten']


def test_a_script_without_declared_outputs_owns_its_generated_files(shared):
    p = shared
    layout = paths.REPO / 'layout.py'; layout.write_text('# layout')
    files = [p.ctx.out / 'layout/world.json', p.ctx.out / 'layout/roads/streets.json']
    p.add(build.Step('world.layout', [build.Python(layout, ())], inputs=[layout]), files)
    assert p.run() == 0
    stamp = p.stamp('world.layout')
    assert stamp['checkpoint_packages'] == ['generated/layout/roads/streets.json', 'generated/layout/world.json']
    assert 'checkpoint_local' not in stamp
    shutil.rmtree(p.ctx.out / 'layout')
    assert p.run() == 0 and p.launches.count('world.layout') == 1  # Restored from its own entry.
    assert all(f.read_bytes() == b'generated ' + f.name.encode() for f in files)


@pytest.mark.parametrize('commands', [[build.Call('textures', lambda ctx, log: None)], []], ids=['call', 'group'])
def test_a_step_that_writes_nothing_publishes_an_empty_result(shared, commands):
    p = shared
    p.add(build.Step('world.textures', commands), [])
    assert p.run() == 0
    stamp = p.stamp('world.textures')
    assert stamp['checkpoint_packages'] == [] and 'checkpoint_local' not in stamp
    entry = json.loads(actions.entry_path(cp.Store('fixture'), stamp['checkpoint_key']).read_text())
    assert entry['roots'] == [] and entry['files'] == {}
    for stamp_file in p.ctx.stamps.glob('*.json'):  # A fresh checkout: nothing local.
        stamp_file.unlink()
    p.messages.clear()
    assert p.run() == 0 and p.launches.count('world.textures') == len(commands)  # Not run again.
    assert any(m.startswith('world.textures') and 'restored in' in m for m in p.messages)


def test_a_moved_package_clears_the_old_claim_and_the_kept_result_publishes(shared):
    p = shared
    # kei once wrote the sea too; lake is its single owner now (as slice C made world the owner).
    p.saves['unreal.lake'].append('Japan/Assets/Sea.uasset')
    p.saves['unreal.kei'].append('Japan/Assets/Sea.uasset')
    assert p.run() == 0
    lake = p.stamp('unreal.lake')
    assert lake['checkpoint_local'][0].startswith('content/Japan/Assets/Sea.uasset also written by unreal.kei')
    assert lake['checkpoint_retry']
    p.saves['unreal.kei'].remove('Japan/Assets/Sea.uasset')
    (paths.REPO / 'unreal.kei.py').write_text('# import unreal.kei, reads the sea')  # Its recipe changed.
    p.messages.clear()
    assert p.run() == 0
    assert p.launches == ['unreal.kei', 'unreal.lake', 'unreal.kei']  # lake did not rerun.
    assert 'checkpoint_local' not in p.stamp('unreal.kei')  # Its latest run no longer claims the sea.
    assert package_ownership.report(cp.Store('fixture'))['contested'] == {}
    lake = p.stamp('unreal.lake')
    assert 'checkpoint_local' not in lake and actions.entry_path(cp.Store('fixture'), lake['checkpoint_key']).is_file()
    assert any(m.startswith('unreal.lake') and 'published its kept result' in m for m in p.messages)
    for name in [*LAKE, 'Japan/Assets/Sea.uasset']:  # And it now restores like any other result.
        (p.content / name).unlink()
    assert p.run() == 0 and p.launches.count('unreal.lake') == 1
    assert (p.content / 'Japan/Assets/Sea.uasset').read_bytes() == b'package Japan/Assets/Sea.uasset'


def test_a_step_replacing_its_own_release_file_publishes_and_restores_exactly(shared):
    p = shared
    script = paths.REPO / 'package.py'; script.write_text('# package r1')
    package = p.ctx.out / 'package'
    def release(n):
        return [lambda: [old.unlink() for old in package.glob('Release-*.zip')],
                package / f'Release-{n}.zip', package / 'Download/Game.app/Contents/Info.plist', package / 'SHA256SUMS']
    p.add(build.Step('unreal.package', [build.Python(script, ())], inputs=[script]), release('r1'))
    assert p.run() == 0 and 'checkpoint_local' not in p.stamp('unreal.package')
    p.saves['unreal.package'] = release('r2')
    script.write_text('# package r2')  # A new revision: the old zip is deleted, as package_archive does.
    assert p.run() == 0
    stamp = p.stamp('unreal.package')
    assert 'checkpoint_local' not in stamp and not (package / 'Release-r1.zip').exists()
    assert stamp['checkpoint_packages'] == ['generated/package/Download/Game.app/Contents/Info.plist',
                                            'generated/package/Release-r2.zip', 'generated/package/SHA256SUMS']
    shutil.rmtree(package)
    assert p.run() == 0 and p.launches.count('unreal.package') == 2  # Restored, exact bytes.
    assert (package / 'Release-r2.zip').read_bytes() == b'generated Release-r2.zip'
    assert sorted(f.name for f in package.rglob('*') if f.is_file()) == ['Info.plist', 'Release-r2.zip', 'SHA256SUMS']


def test_deleting_another_steps_file_keeps_the_run_local(shared):
    p = shared
    script = paths.REPO / 'clean.py'; script.write_text('# clean')
    p.add(build.Step('world.clean', [build.Python(script, ())], inputs=[script], needs=['unreal.kei']),
          [lambda: (shared.content / KEI[0]).unlink(), p.ctx.out / 'clean.json'])
    assert p.run() == 0
    assert p.stamp('world.clean')['checkpoint_local'][0] == 'deleted content/' + KEI[0]
