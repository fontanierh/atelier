"""Unsupported cutover launchers refuse before side effects; no native programs or models run."""
import importlib.util
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from atelier import capacity_compat as compat, setup, stream
from atelier.capacity_protocol import CapacityError

GAME = Path(__file__).resolve().parents[1]


def load(relative):
    path = GAME / relative
    spec = importlib.util.spec_from_file_location('unmanaged_' + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def forbidden(*args, **kwargs):
    pytest.fail('Refusal must precede process/model allocation or file mutation')


@pytest.fixture(params=['preparing', 'sealed', 'active'])
def cutover(request, monkeypatch):
    monkeypatch.setattr(compat, 'read', lambda: {'state': request.param})
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    monkeypatch.setattr(subprocess, 'run', forbidden)


def test_stream_start_refuses_before_output_or_process_state(cutover, monkeypatch):
    monkeypatch.setattr(stream, 'Game', forbidden)
    with pytest.raises(CapacityError, match='Browser streaming.*no full-capacity lifecycle'):
        stream.main('fixture', 'start')
    with pytest.raises(CapacityError, match='Browser streaming'):
        stream.start(object())


def test_engine_setup_refuses_before_checks_or_outer_lock(cutover, monkeypatch, tmp_path):
    monkeypatch.setattr(setup, 'mac_checks', forbidden)
    monkeypatch.setattr(setup, 'render_lock', forbidden)
    with pytest.raises(CapacityError, match='Headless toolchain setup'):
        setup.main(headless=True)
    with pytest.raises(CapacityError, match='Headless toolchain setup'):
        setup.prepare_headless(tmp_path / 'missing-engine')
    assert list(tmp_path.iterdir()) == []


def test_animation_setup_refuses_before_install_or_export(cutover, monkeypatch, tmp_path):
    module = load('animation_lab/setup.py')
    for generator in ('kimodo', 'unimate'):
        monkeypatch.setitem(sys.modules, f'atelier.ai.{generator}.install', SimpleNamespace(install=forbidden))
        with pytest.raises(CapacityError, match='Animation lab setup'):
            module.prepare(generator, tmp_path / generator)
    monkeypatch.setattr(sys, 'argv', ['setup.py'])
    with pytest.raises(CapacityError, match='Animation lab setup'):
        module.main()
    with pytest.raises(CapacityError, match='Animation lab setup'):
        module.command('npm', 'ci')
    assert list(tmp_path.iterdir()) == []


@pytest.fixture
def models(monkeypatch):
    server = load('animation_lab/server.py')
    monkeypatch.setitem(sys.modules, 'server', server)
    monkeypatch.syspath_prepend(str(GAME / 'animation_lab'))
    return server, load('animation_lab/unified.py')


def test_model_start_load_and_generation_refuse_before_allocation(cutover, models, tmp_path, monkeypatch):
    server, unified = models
    monkeypatch.setattr(server.threading, 'Thread', forbidden)
    monkeypatch.setitem(sys.modules, 'engine', SimpleNamespace(Engine=forbidden))
    monkeypatch.setitem(sys.modules, 'kimodo_engine', SimpleNamespace(Engine=forbidden))
    for generator in ('kimodo', 'unimate'):
        root = tmp_path / generator
        with pytest.raises(CapacityError, match='Animation model loading'):
            server.Lab(root, generator=generator)
        assert not root.exists()
        # Reading saved libraries remains available, but manually requesting a later load does not.
        lab = server.Lab(root, warm=False, generator=generator)
        with pytest.raises(CapacityError, match='Animation model loading'):
            lab.load('cpu')
        with pytest.raises(CapacityError, match='Animation generation'):
            lab.create({'prompt': 'A person jumps'})
        job = {'id': 'not-started'}
        with pytest.raises(CapacityError, match='Animation generation'):
            lab.run(job)
        assert lab.jobs == {} and lab.active is None and lab.engine is None
        assert not (root / 'results/not-started').exists()
    with pytest.raises(CapacityError, match='Animation model worker'):
        unified.Backend('unimate', tmp_path / 'backend', tmp_path / 'runtime')
    assert not (tmp_path / 'runtime').exists()
    with pytest.raises(CapacityError, match='Animation model workers'):
        unified.UnifiedLab(tmp_path / 'combined', {})
    assert not (tmp_path / 'combined').exists()
    browser = unified.UnifiedLab(tmp_path / 'browser', {}, start=False)
    with pytest.raises(CapacityError, match='Animation generation'):
        browser.create({})
    assert browser.backends == {} and browser.active is None
    with pytest.raises(CapacityError, match='Animation generation'):
        unified.Backend.__new__(unified.Backend).request('/api/generate', {})
    monkeypatch.setattr(sys, 'argv', ['server.py'])
    with pytest.raises(CapacityError, match='Animation lab server'):
        server.main()


def test_building_kit_refuses_before_local_locks_or_output(cutover, monkeypatch, tmp_path):
    module = load('world/regions/hidamari/kit/lab.py')
    monkeypatch.setattr(module, 'lock', forbidden)
    monkeypatch.setattr(module, 'DOCS', tmp_path / 'docs')
    for function, args in [(module.blender_build, (['asset'],)), (module.unreal_import, (['asset'],)),
                           (module.capture_views, ('fixture', ['asset']))]:
        with pytest.raises(CapacityError, match='Building kit'):
            function(*args)
    assert not (tmp_path / 'docs').exists()


def test_character_authoring_refuses_before_log_creation_or_render(cutover, monkeypatch, tmp_path):
    module = load('assets/characters/tools/cairo_outfit.py')
    log = tmp_path / 'logs/native.log'
    with pytest.raises(CapacityError, match='Character outfit authoring'):
        module.run(['blender'], log, {})
    assert not log.parent.exists()
    monkeypatch.setattr(sys, 'argv', ['cairo_outfit.py', str(tmp_path / 'missing-spec.toml')])
    with pytest.raises(CapacityError, match='Character outfit authoring'):
        module.main()
    with pytest.raises(CapacityError, match='Character sprint comparison'):
        load('assets/characters/tools/compare_cairo_sprint.py')


def test_absent_cutover_preserves_legacy_dispatch_and_authoring(monkeypatch, tmp_path):
    monkeypatch.setattr(compat, 'read', lambda: None)
    output = tmp_path / 'stream'
    game = SimpleNamespace(out=output)
    calls = []
    monkeypatch.setattr(stream, 'Game', lambda name: game)
    monkeypatch.setattr(stream, 'start', lambda selected, local: calls.append((selected, local)) or 17)
    assert stream.main('fixture', 'start', local=True) == 17
    assert calls == [(game, True)] and output.is_dir()
    module = load('assets/characters/tools/cairo_outfit.py')
    monkeypatch.setattr(subprocess, 'run', lambda argv, **options: calls.append(argv) or SimpleNamespace(returncode=3))
    log = tmp_path / 'logs/native.log'
    assert module.run(['legacy-tool', 'argument'], log, {}) == 3
    assert calls[-1] == ['legacy-tool', 'argument'] and log.is_file()


def test_absent_cutover_preserves_model_warmup_and_single_worker(monkeypatch, models, tmp_path):
    monkeypatch.setattr(compat, 'read', lambda: None)
    server, unified = models
    warmed = []
    monkeypatch.setattr(server.threading, 'Thread', lambda **options: SimpleNamespace(start=lambda: warmed.append(options)))
    lab = server.Lab(tmp_path / 'lab')
    assert warmed[0]['target'] == lab.load and warmed[0]['args'] == ('mps',)
    root = tmp_path / 'backend'
    python = root / 'venv/bin/python'
    python.parent.mkdir(parents=True)
    python.touch()
    child = SimpleNamespace(pid=123)
    monkeypatch.setattr(subprocess, 'Popen', lambda argv, **options: warmed.append(argv) or child)
    from atelier.safety import guard
    from contextlib import nullcontext
    monkeypatch.setattr(guard, 'attach', lambda *args, **options: nullcontext('monitor'))
    monkeypatch.setattr(guard, 'reap', lambda process: None)
    backend = unified.Backend('unimate', root, tmp_path / 'runtime')
    assert backend.process is child and backend.monitor == 'monitor'
    assert warmed[-1][0] == str(python)
    backend.close()
