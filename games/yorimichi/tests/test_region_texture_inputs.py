"""Actual selected-byte action and audited projections ignore unused texture files."""
from dataclasses import replace
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier import build, build_checkpoints
from test_region_products import RECIPE, products, export as brinecove
from test_belmonte_products import export as belmonte


@pytest.mark.parametrize('region,export', [('brinecove', brinecove), ('belmonte', belmonte)])
def test_real_projection_tracks_only_selected_texture_bytes(tmp_path, monkeypatch, region, export):
    out = tmp_path / 'out'; folder = out / region
    export(folder, {})
    ctx = SimpleNamespace(game='fixture', out=out, logs=out / 'logs', stamps=out / 'stamps', uproject=None)
    selector = replace(RECIPE.region_texture_step(out, region), needs=[])
    factory = RECIPE.brinecove_steps if region == 'brinecove' else RECIPE.belmonte_steps
    projection = replace(factory(out)[1], needs=[selector.name])
    monkeypatch.setattr(build, 'Context', lambda *a, **k: ctx)
    monkeypatch.setattr(build, 'load_recipe', lambda _: SimpleNamespace(steps=lambda _: [selector, projection]))
    monkeypatch.setattr(build_checkpoints, 'configured', lambda _: None)
    monkeypatch.setenv('ATELIER_CACHE', str(tmp_path / 'cache'))
    def run():
        logs = []
        assert build.build('fixture', [projection.name], echo=logs.append) == 0, '\n'.join(logs)
        return {name: (ctx.stamps / (name + '.json')).read_bytes() for name in (selector.name, projection.name)}
    before = run()
    # Add, modify and remove an unconsumed file: neither action executes or republishes its stamp.
    unused = folder / 'textures/unused.png'
    unused.write_bytes(b'unused'); assert run() == before
    unused.write_bytes(b'changed'); assert run() == before
    unused.unlink(); assert run() == before
    material_path = out / f'products/{region}/materials.json'
    original_materials = material_path.read_bytes()
    direct = products.library_views(folder, collision_basename=region == 'belmonte',
                                    bindings=region == 'belmonte', preserve_mesh_order=region == 'belmonte')
    assert json.loads(original_materials) == direct['materials']
    selected = next(iter(json.loads(original_materials)['files']))
    (folder / selected).write_bytes(b'new selected texture')
    after = run()
    assert all(after[name] != before[name] for name in before)
    assert material_path.read_bytes() != original_materials
    assert folder / 'textures' not in projection.inputs


def test_selection_covers_layer_normal_and_arbitrary_file_formats(tmp_path):
    folder = tmp_path / 'region'; brinecove(folder, {})
    report_path = folder / 'build-report.json'; report = json.loads(report_path.read_text())
    entry = next(iter(report['materials'].values()))
    entry['layers'] = {'Sand': 'layer.exr', 'Tint': [1., .5, 0.]}
    entry['normals'] = {'Rock': 'normal.weird'}
    report_path.write_text(json.dumps(report))
    (folder / 'textures/layer.exr').write_bytes(b'layer')
    (folder / 'textures/normal.weird').write_bytes(b'normal')
    selector = RECIPE.region_texture_step(tmp_path, 'region')
    provider, = selector.deferred_inputs
    assert {path.relative_to(folder).as_posix() for path in provider.collect(*provider.settings)} == {
        'build-report.json', 'textures/paint.png', 'textures/layer.exr', 'textures/normal.weird'}
    subprocess.run([sys.executable, str(RECIPE.GAME / 'region_texture_inputs.py'), str(folder),
                    str(selector.outputs[0])], check=True)
    del entry['layers']['Sand']; del entry['normals']
    report_path.write_text(json.dumps(report))
    assert {path.relative_to(folder).as_posix() for path in provider.collect(*provider.settings)} == {
        'build-report.json', 'textures/paint.png'}


@pytest.mark.parametrize('bad', ['missing', 'linked', 'root_linked', 'escape'])
def test_selected_invalid_source_cannot_publish_snapshot(tmp_path, bad):
    folder = tmp_path / 'region'; brinecove(folder, {})
    selected = folder / 'textures/paint.png'
    if bad == 'missing': selected.unlink()
    elif bad == 'linked':
        selected.unlink(); target = tmp_path / 'outside.png'; target.write_bytes(b'outside'); selected.symlink_to(target)
    elif bad == 'root_linked':
        target = tmp_path / 'backing'; folder.rename(target); folder.symlink_to(target, target_is_directory=True)
    else:
        report_path = folder / 'build-report.json'; report = json.loads(report_path.read_text())
        next(iter(report['materials'].values()))['texture'] = '../outside.png'; report_path.write_text(json.dumps(report))
    selector = RECIPE.region_texture_step(tmp_path, 'region')
    result = subprocess.run([sys.executable, str(RECIPE.GAME / 'region_texture_inputs.py'),
                             str(folder), str(selector.outputs[0])], capture_output=True, text=True)
    assert result.returncode != 0
    assert not selector.outputs[0].exists()


def test_snapshot_cannot_hide_missing_or_extra_selected_members(tmp_path):
    folder = tmp_path / 'region'; brinecove(folder, {})
    report = json.loads((folder / 'build-report.json').read_text())
    inventory = tmp_path / 'textures.json'
    inventory.write_text(json.dumps({'schema': 1, 'files': {}}))
    with pytest.raises(ValueError, match='membership'):
        products.texture_files(folder, report, inventory)
    inventory.write_text(json.dumps({'schema': 1, 'files': {'textures/paint.png': {'sha256': 'a' * 64, 'size': -1}}}))
    with pytest.raises(ValueError, match='byte inventory'):
        products.texture_files(folder, report, inventory)
