"""Launch preferences, manifest readiness and clean renderer relaunches; no engine process is started."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def desktop(monkeypatch, tmp_path):
    path = Path(__file__).resolve().parents[1] / 'tools' / 'desktop_preview.py'
    spec = importlib.util.spec_from_file_location('desktop_preview_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    project = tmp_path / 'unreal'
    (project / 'Saved').mkdir(parents=True)
    monkeypatch.setattr(module, 'PROJECT', project)
    monkeypatch.delenv('YORIMICHI_EXTRA_ARGS', raising=False)
    return module


def manifest(desktop, count=183):
    from regions.hidamari.logical_catalogue import ASSETS
    path = desktop.PROJECT / 'Content' / 'Data' / 'city_surface_tiles' / 'v1_128m' / 'manifest.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    sources = {name: {'tiles': [{'name': name + str(i)} for i in range(n)]}
               for name, n in zip(ASSETS,(count-len(ASSETS)+1,*([1]*(len(ASSETS)-1))))}
    path.write_text(json.dumps({'version':3,'complete': True, 'tag': 'v1_128m', 'sources': sources}))
    return path


def ready_log(lumen=False, trees=True, tiles=183, forced=2, groups=3):
    return (f'DESKTOP PREVIEW viewport=2228x1440 fullscreen=1 window_aspect=1.547\n'
            f'r.ForwardShading = "{int(not lumen)}"\n'
            f'CITY PIECES production parents=86 pieces={tiles} hidden_parents=0\n'
            f'CITY TREE LODS tag=v4 enabled={int(trees)} forced={forced} groups={groups} instances=900 distance_scale=1.50\n'
            'FORWARD FILL nominal_lux=3.000 lights=1\n')


def test_region_tree_groups_preserve_city_readiness(desktop):
    manifest(desktop)
    assert desktop.parse_ready(ready_log().replace('groups=3', 'groups=4'))
    with pytest.raises(ValueError, match='CITY TREE LODS'):
        desktop.parse_ready(ready_log().replace('groups=3', 'groups=2'))


def test_default_forward_and_saved_lumen_keep_distinct_mesh_generation(desktop, tmp_path):
    ctx = SimpleNamespace(unreal_app=Path('Editor'), uproject=Path('Game.uproject'))
    forward = desktop.command(ctx, tmp_path, shared_settings=True)
    assert any('r.ForwardShading=True' in arg for arg in forward)
    assert '-ForceDPCVars=r.GenerateMeshDistanceFields=0,r.MeshCardRepresentation=0' in forward
    assert '-renderrestart' in forward
    assert 'japan.CityTreeLODs' not in ' '.join(forward)
    (desktop.PROJECT / 'Saved' / 'settings.txt').write_text('renderer=1\ntree_optimization=0\nperformance=0\nrender_scale=85\nexposure=1.2\n')
    lumen = desktop.command(ctx, tmp_path, shared_settings=True, extra=['-liveport=8844'])
    assert any('r.ForwardShading=False' in arg for arg in lumen)
    assert not any(arg.startswith('-ForceDPCVars=') for arg in lumen)
    assert '-liveport=8844' in lumen
    settings = next(arg for arg in lumen if arg.startswith('-set='))
    assert 'performance=1' not in settings and 'render_scale=100' not in settings
    assert 'tree_optimization=' not in settings and 'exposure=' not in settings
    assert 'r.ScreenPercentage 100' not in ' '.join(lumen)


def test_probe_renderer_flags_preserve_lumen_and_default_viewport(desktop):
    for lumen in (False, True):
        flags = desktop.renderer_arguments(lumen)
        assert '-noshaderworker' in flags
        assert ('r.ForwardShading=' + ('False' if lumen else 'True')) in ' '.join(flags)
        assert any(arg.startswith('-ForceDPCVars=') for arg in flags) == (not lumen)
        assert 'GameViewportClientClassName' not in ' '.join(flags)
        assert 'DesktopPreviewViewportClient' in ' '.join(desktop.renderer_arguments(lumen, desktop_viewport=True))


def test_bridge_binding_failure_wins_over_misleading_listening_announcement(desktop):
    failure = 'LogHttpListener: Error: HttpListener unable to bind to 127.0.0.1:8857'
    log = failure + '\nLIVE bridge listening on 8857\n'
    assert desktop.bridge_bind_error(log, 8857) == failure
    assert desktop.bridge_bind_error(log, 8858) is None
    assert desktop.bridge_bind_error(log.replace(':8857', ':88570'), 8857) is None
    assert desktop.bridge_bind_error('LIVE bridge listening on 8857\n', 8857) is None


def test_isolated_shared_preferences_use_normal_profile_without_overwriting_saved_choices(desktop, tmp_path):
    primary = desktop.PROJECT / 'Saved' / 'settings.txt'
    primary.write_text('renderer=1\nexposure=1.5\n')
    isolated = tmp_path / 'isolated.txt'
    isolated.write_text('renderer=0\nperformance=0\nrender_scale=85\nexposure=1.2\n')
    ctx = SimpleNamespace(unreal_app=Path('Editor'), uproject=Path('Game.uproject'))
    command = desktop.command(ctx, tmp_path, windowed=True, shared_settings=True, preferences=isolated)
    assert '-preferencesfile=' + str(isolated) in command
    assert any('r.ForwardShading=True' in arg for arg in command)
    profile = next(arg for arg in command if arg.startswith('-set='))
    assert 'desktop=1' in profile and 'renderer=0' in profile
    assert 'performance=1' not in profile and 'render_scale=100' not in profile and 'exposure=' not in profile
    assert 'japan.CitySurfaceTiles' not in ' '.join(command)
    assert primary.read_text() == 'renderer=1\nexposure=1.5\n'


def test_readiness_matches_current_manifest_and_rejects_partial_import(desktop):
    manifest(desktop)
    assert desktop.parse_ready(ready_log())['height'] == 1440
    assert desktop.parse_ready(ready_log(lumen=True, trees=False), True, tree_optimization=False)
    with pytest.raises(ValueError, match='pieces=183'):
        desktop.parse_ready(ready_log(tiles=85))
    with pytest.raises(ValueError, match='pieces=183'):
        desktop.parse_ready(ready_log(tiles=830))
    with pytest.raises(ValueError, match='CITY TREE LODS'):
        desktop.parse_ready(ready_log().replace('CITY TREE LODS', 'missing trees'))
    path = manifest(desktop)
    data = json.loads(path.read_text())
    data['complete'] = False
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='manifest'):
        desktop.parse_ready(ready_log())


def test_fractional_graphics_choices_match_the_native_threshold(desktop, tmp_path):
    ctx = SimpleNamespace(unreal_app=Path('Editor'), uproject=Path('Game.uproject'))
    (desktop.PROJECT / 'Saved' / 'settings.txt').write_text('renderer=0.5\ntree_optimization=0.5\n')
    command = desktop.command(ctx, tmp_path, shared_settings=True)
    assert any('r.ForwardShading=True' in arg for arg in command)
    manifest(desktop)
    trees = desktop.toggle(desktop.read_preferences(desktop.PROJECT / 'Saved' / 'settings.txt'), 'tree_optimization', 1)
    assert desktop.parse_ready(ready_log(trees=False), tree_optimization=trees)


@pytest.mark.parametrize('memory_gib', [10., 18., 24.])
def test_menu_renderer_restart_reads_saved_choice_and_releases_each_guard(desktop, monkeypatch, tmp_path, memory_gib):
    manifest(desktop)
    preferences = desktop.PROJECT / 'Saved' / 'settings.txt'
    preferences.write_text('renderer=0\ntree_optimization=0\n')
    ctx = SimpleNamespace(unreal_app=Path('Editor'), uproject=Path('Game.uproject'), out=tmp_path / 'build', env=lambda: {})
    monkeypatch.setattr(desktop, 'Context', lambda game: ctx)
    monkeypatch.setattr(desktop, 'wait_for_bridge_port', lambda command: None)
    runs = []

    def run(command, folder, **kwargs):
        runs.append((command, folder, kwargs))
        if len(runs) == 1:
            preferences.write_text('renderer=1\ntree_optimization=0\n')
            request = Path(next(arg for arg in command if arg.startswith('-renderrestartrequest=')).partition('=')[2])
            request.write_text('renderer=1\n')
            return 0
        (folder / 'game.log').write_text(ready_log(lumen=True, trees=False))
        return 0

    monkeypatch.setattr(desktop.guarded, 'run', run)
    assert desktop.launch(shared_settings=True, settings='renderer=0;show_fps=1', memory_gib=memory_gib) == 0
    assert len(runs) == 2
    assert any('r.ForwardShading=True' in arg for arg in runs[0][0])
    assert any('r.ForwardShading=False' in arg for arg in runs[1][0])
    assert runs[0][1] != runs[1][1]
    assert all(run[2]['kind'] == 'game' and run[2]['limit_gib'] == memory_gib for run in runs)
    assert 'show_fps=1' in next(arg for arg in runs[1][0] if arg.startswith('-set='))


def test_restart_requires_a_changed_saved_choice(desktop, monkeypatch, tmp_path):
    ctx = SimpleNamespace(unreal_app=Path('Editor'), uproject=Path('Game.uproject'), out=tmp_path, env=lambda: {})
    monkeypatch.setattr(desktop, 'Context', lambda game: ctx)
    def run(command, folder, **kwargs):
        (folder / 'renderer-restart.txt').write_text('renderer=0\n')
        return 0
    monkeypatch.setattr(desktop.guarded, 'run', run)
    assert desktop.launch(shared_settings=True) == 1


def test_forced_tree_comparison_readiness_and_invalid_saved_modes(desktop):
    manifest(desktop)
    forced=ready_log(forced=3)
    assert desktop.parse_ready(forced,tree_lod_mode=3)['height']==1440
    with pytest.raises(ValueError,match='CITY TREE LODS'):
        desktop.parse_ready(forced,tree_lod_mode=0)
    assert desktop.tree_lod_choice({'tree_lod_mode':'1.5'})==2
    assert desktop.tree_lod_choice({'tree_lod_mode':'0.4'})==0
    # Like the game, an unreadable or missing saved mode starts at the release default.
    assert desktop.tree_lod_choice({'tree_lod_mode':'nan'})==2
    assert desktop.tree_lod_choice({'tree_lod_mode':'bad'})==2
    assert desktop.tree_lod_choice({})==2


def test_launcher_defaults_are_the_game_release_defaults(desktop):
    from test_release_defaults import release_defaults
    game = release_defaults()
    assert desktop.RELEASE_DEFAULTS == {key: int(game[key]) for key in desktop.RELEASE_DEFAULTS}


@pytest.mark.parametrize('saved, settings, forced', [
    ('', '', 2),                                   # a fresh install: the release preset's forced tree detail
    ('exposure=1.2\n', '', 2),                     # saved choices that leave the tree mode at its default
    ('tree_lod_mode=0\n', '', 0),                  # a saved automatic mode
    ('tree_lod_mode=1\n', '', 1),
    ('tree_lod_mode=2\n', 'tree_lod_mode=3', 3),    # an explicitly requested mode wins over the saved one
    ('tree_lod_mode=3\n', 'tree_lod_mode=0', 0),
])
def test_play_verifies_the_tree_mode_the_game_starts_in(desktop, monkeypatch, tmp_path, saved, settings, forced):
    manifest(desktop)
    (desktop.PROJECT / 'Saved' / 'settings.txt').write_text(saved)
    ctx = SimpleNamespace(unreal_app=Path('Editor'), uproject=Path('Game.uproject'), out=tmp_path / 'build', env=lambda: {})
    monkeypatch.setattr(desktop, 'Context', lambda game: ctx)
    logs = []

    def run(command, folder, **kwargs):
        (folder / 'game.log').write_text(logs[-1])
        return 0

    monkeypatch.setattr(desktop.guarded, 'run', run)
    for shared in (True, False):
        logs.append(ready_log(forced=forced))
        assert desktop.launch(shared_settings=shared, settings=settings) == 0
        # The tree detail the game did not start in is not verified.
        logs.append(ready_log(forced=(forced + 1) % 4))
        assert desktop.launch(shared_settings=shared, settings=settings) == 1


@pytest.mark.parametrize('log', [
    ready_log().replace('CITY TREE LODS', 'missing trees'),   # never reported
    ready_log(trees=False),                                   # optimization expected on but disabled
    ready_log(groups=2),                                      # fewer than the three city tree groups
    ready_log(groups=0),
])
def test_preset_readiness_still_rejects_missing_disabled_or_partial_trees(desktop, log):
    manifest(desktop)
    with pytest.raises(ValueError, match='CITY TREE LODS'):
        desktop.parse_ready(log)


def test_renderer_restart_waits_for_an_occupied_loopback_port(desktop):
    import socket
    import pytest
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as owner:
        owner.bind(('127.0.0.1', 0))
        owner.listen()
        port = owner.getsockname()[1]
        with pytest.raises(TimeoutError, match='stayed occupied'):
            desktop.wait_for_bridge_port(['-liveport='+str(port)], timeout=.03)
        # The check must not take over, close or share the owner's listener.
        assert owner.getsockname() == ('127.0.0.1', port)
        owner.listen()
    desktop.wait_for_bridge_port(['-liveport='+str(port)], timeout=.03)


def test_renderer_restart_rejects_an_invalid_port(desktop):
    import pytest
    with pytest.raises(ValueError, match='live bridge port'):
        desktop.wait_for_bridge_port(['-liveport=65536'], timeout=.03)


@pytest.mark.parametrize('memory_gib', [9.999, 24.001, float('nan'), float('inf'), float('-inf')])
def test_desktop_refuses_invalid_memory_before_context_or_launch(desktop, monkeypatch, memory_gib):
    monkeypatch.setattr(desktop, 'Context', lambda *a: pytest.fail('invalid ceiling reached context'))
    with pytest.raises(ValueError, match='10 to 24 GiB'):
        desktop.launch(memory_gib=memory_gib)
