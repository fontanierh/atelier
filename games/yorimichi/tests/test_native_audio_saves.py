"""Execute production audio imports: failed saves must not publish a partial native result."""
import ast
import json
from pathlib import Path
import runpy
import sys
from types import SimpleNamespace

import pytest

from atelier import build, build_products
from atelier.native_packages import save


SCRIPTS = Path(__file__).resolve().parents[1] / 'unreal/Scripts'


class Object:
    def __init__(self, **values): self.values = values
    def set_editor_property(self, name, value): self.values[name] = value
    def get_editor_property(self, name): return self.values[name]


class Wave(Object):
    def get_name(self): return self.values['path'].rsplit('.', 1)[-1]
    def get_path_name(self): return self.values['path']


def environment(tmp_path, monkeypatch, mode):
    content = tmp_path / 'game/unreal/Content'
    assets, saved, logs = {}, [], []
    def imported(tasks):
        for task in tasks:
            path = task.values['destination_path']+'/'+task.values['destination_name']
            asset = Wave(path=path+'.'+task.values['destination_name'], duration=.25)
            assets[asset.get_path_name()] = asset
            task.values['imported_object_paths'] = [asset.get_path_name()]
    def write(asset, **kwargs):
        saved.append(asset)
        if len(saved) == 2 and mode == 'refused': return False
        if len(saved) == 2 and mode == 'missing': return True
        path = content / (asset.get_path_name().split('.')[0].removeprefix('/Game/')+'.uasset')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'saved wave')
        return True
    editor = SimpleNamespace(make_directory=lambda *a: None, load_asset=assets.__getitem__,
                             does_asset_exist=lambda *a: False, save_loaded_asset=write)
    tools = SimpleNamespace(import_asset_tasks=imported)
    unreal = SimpleNamespace(EditorAssetLibrary=editor, AssetToolsHelpers=SimpleNamespace(get_asset_tools=lambda: tools),
                             AssetImportTask=Object, SoundFactory=Object, SoundWave=Wave, log=logs.append)
    yori = SimpleNamespace(OUT=tmp_path / 'build', GAME=tmp_path / 'game')
    monkeypatch.setitem(sys.modules, 'unreal', unreal)
    monkeypatch.setitem(sys.modules, 'yori', yori)
    monkeypatch.setattr(sys, 'path', list(sys.path))
    return yori, unreal, saved, logs


@pytest.mark.parametrize('kind', ['combat', 'skate', 'bike', 'transport', 'driving', 'footsteps'])
@pytest.mark.parametrize('mode', ['refused', 'missing', 'success'])
def test_actual_import_cannot_certify_partially_saved_wave_directory(tmp_path, monkeypatch, kind, mode):
    yori, unreal, saved, logs = environment(tmp_path, monkeypatch, mode)
    folder = yori.OUT / 'audio' / ('kart' if kind == 'driving' else kind)
    (folder / 'stone').mkdir(parents=True)
    (folder / 'manifest.json').write_text(json.dumps({'loops': []}))
    files = [folder / 'stone' / f'cue_{i:02d}.wav' for i in (1, 2)]
    for path in files: path.write_bytes(b'input wave')
    script = SCRIPTS / ('import_footsteps.py' if kind == 'footsteps' else f'import_{kind}_audio.py')
    if kind == 'footsteps':
        # Exercise the same production wave loop without unrelated data-asset factory setup.
        body = [node for node in ast.parse(script.read_text()).body
                if isinstance(node, ast.FunctionDef) and node.name == 'import_surface']
        namespace = {'U': unreal, 'E': unreal.EditorAssetLibrary, 'AT': unreal.AssetToolsHelpers.get_asset_tools(),
                     'DEST': '/Game/Japan/Audio', 'save_native_package': save, 'yori': yori}
        exec(compile(ast.Module(body=body, type_ignores=[]), str(script), 'exec'), namespace)
        run = lambda: namespace['import_surface']('stone', files)
    else:
        run = lambda: runpy.run_path(str(script), run_name='__main__')
    if mode == 'success':
        run()
        assert len(saved) == 2
        if kind != 'footsteps': assert any('IMPORT COMPLETE' in line for line in logs)
    else:
        with pytest.raises(RuntimeError): run()
        assert len(saved) == 2
        assert len(list((yori.GAME / 'unreal/Content').rglob('*.uasset'))) == 1
        assert not any('IMPORT COMPLETE' in line for line in logs)
        assert not list(yori.OUT.glob('*_import.json'))


@pytest.mark.parametrize('kind', ['footsteps', 'combat', 'skate', 'kart', 'bike', 'transport'])
def test_every_source_wave_byte_is_a_sound_input(tmp_path, kind):
    recipe = build.load_recipe('yorimichi')
    ctx = SimpleNamespace(out=tmp_path, game='yorimichi', uproject=None)
    graph = build_products.Graph(recipe.steps(ctx))
    product, = graph.by_name['audio.' + kind].products
    folder, = product.paths
    folder.mkdir(parents=True)
    wave = folder / 'cue.wav'; wave.write_bytes(b'first')
    original = build_products.identity(build_products.inventory(product))
    wave.write_bytes(b'changed')
    changed = build_products.identity(build_products.inventory(product))
    wave.unlink()
    missing = build_products.identity(build_products.inventory(product))
    assert len({original, changed, missing}) == 3
    assert 'audio.' + kind in graph.by_name['unreal.sounds'].reads
