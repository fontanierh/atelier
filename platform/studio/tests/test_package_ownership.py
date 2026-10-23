"""Unreal imports sharing a Content folder own exactly the files they wrote; no Unreal launches."""
import json
import os
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

    def run(ctx, step, command, log, *args, **kw):  # Stands in for the Unreal editor.
        launches.append(step.name)
        for relative in saves[step.name]:
            (content / relative).parent.mkdir(parents=True, exist_ok=True)
            (content / relative).write_bytes(b'package ' + relative.encode())
            log.write(save_line(content, relative))
    monkeypatch.setattr(build, 'run_command', run)
    messages = []
    return SimpleNamespace(ctx=ctx, content=content, launches=launches, saves=saves, messages=messages,
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
