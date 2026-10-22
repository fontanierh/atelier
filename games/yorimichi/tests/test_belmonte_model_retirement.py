"""Real ordinary producer removal/rename, with expensive terrain generation stubbed."""
import ast
from dataclasses import replace
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import struct
from types import SimpleNamespace

import numpy as np
import pytest

from atelier import build, build_checkpoints, model_files
from atelier.gltf import glb_pack, glb_parts
from test_region_products import products, RECIPE


@pytest.mark.parametrize('change', ['remove', 'rename', 'remove_hull'])
def test_normal_belmonte_producer_retires_superseded_glbs_without_touching_sources(tmp_path, monkeypatch, change):
    out, library = tmp_path / 'out', tmp_path / 'sources'
    library.mkdir()
    settings = tmp_path / 'selection.json'
    selected = {'models': ['House', 'Prop'], 'hull': True}
    payload = struct.pack('<9f3H', 0., 0., 0., 1., 0., 0., 0., 1., 0., 0, 1, 2)
    raw = glb_pack(dict(asset={'version': '2.0'}, buffers=[{'byteLength': len(payload)}],
        bufferViews=[dict(buffer=0, byteOffset=0, byteLength=36), dict(buffer=0, byteOffset=36, byteLength=6)],
        accessors=[dict(bufferView=0, componentType=5126, type='VEC3', count=3),
                   dict(bufferView=1, componentType=5123, type='SCALAR', count=3)],
        scenes=[{'nodes': [0]}], scene=0, nodes=[{'mesh': 0}], materials=[{'name': 'M_0'}],
        meshes=[{'primitives': [dict(attributes={'POSITION': 0}, indices=1, material=0)]}]), payload)
    for name in ('House', 'Prop', 'Renamed', 'House_Collision'):
        (library / (name + '.glb')).write_bytes(raw)
    def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    def entry(name):
        return dict(name=name, path=name + '.glb', sha256=sha(library / (name + '.glb')),
                    source_asset=name, triangles=1, bounds_m=[[0, 0, 0], [1, 2, 3]], slots=['M_0'])
    def manifest():
        current = json.loads(settings.read_text())
        meshes = [entry(name) for name in current['models']]
        if current['hull']:
            next(mesh for mesh in meshes if mesh['name'] == 'House')['collision'] = {
                'path': 'House_Collision.glb', 'sha256': sha(library / 'House_Collision.glb')}
        return dict(meshes=meshes, placements=[dict(asset=name, materials=['paint'], transform={
            'translation_cm': [0, 0, 0], 'rotation_xyzw': [0, 0, 0, 1], 'scale': [1, 1, 1]})
            for name in current['models']], signs=[])
    def surroundings():
        extra = []
        for name in ('SM_BM_NorthApron', 'SM_BM_NorthCountry'):
            for folder in ('glb', 'natural'):
                path = out / 'belmonte' / folder / (name + '.glb')
                path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
            extra.append(dict(name=name, path='glb/' + name + '.glb', sha256=hashlib.sha256(raw).hexdigest(),
                              triangles=1, bounds_m=[[0, 0, 0], [1, 2, 3]], slots=['M_0']))
        return extra, {}
    script = RECIPE.REGIONS / 'belmonte/build.py'
    spec = importlib.util.spec_from_file_location('retired_model_pieces', script.with_name('model_pieces.py'))
    pieces = importlib.util.module_from_spec(spec); spec.loader.exec_module(pieces)
    main = next(node for node in ast.parse(script.read_text()).body if isinstance(node, ast.FunctionDef) and node.name == 'main')
    scope = dict(OUT=out / 'belmonte', json=json, shutil=shutil, source=SimpleNamespace(
        LIBRARY=library, manifest=manifest, sha=sha, triangles=lambda _: [], Surface=lambda _: None,
        terrain=lambda: SimpleNamespace(height=lambda *a: 0)), terrain=SimpleNamespace(VALLEY_CARVED_TILES=set(), OUTER=[0, 0, 10, 10]),
        finish_surfaces=lambda _: {'paint': {'name': 'Paint', 'texture': None}}, glb_parts=glb_parts,
        surroundings=surroundings, np=np, planting=SimpleNamespace(replacements=lambda *a: ({}, {}), woodland=lambda _: {}),
        clear_railway=lambda _: {}, L=SimpleNamespace(ORIGIN=[0, 0, 0], native_origin=lambda: [0, 0, 0],
            BOUNDS=[0, 0, 10, 10], RAILWAY={}), map_zones=lambda _: [], tv_spots=lambda _: [],
        source_records=model_files.source_records, retain_files=model_files.retain_files, model_pieces=pieces, Path=Path, foliage=SimpleNamespace(AUTHORED=frozenset()))
    exec(compile(ast.Module(body=[main], type_ignores=[]), str(script), 'exec'), scope)
    producer = replace(RECIPE.belmonte_steps(out)[0], commands=[build.Call('real producer', lambda ctx, log: scope['main']())],
                       inputs=[settings, library, script], needs=[], heavy=False)
    projection = RECIPE.belmonte_steps(out)[1]
    selector = replace(RECIPE.region_texture_step(out, 'belmonte'), needs=[producer.name])
    projection = replace(projection, needs=[producer.name, selector.name], commands=[build.Call('real projection',
        lambda ctx, log: products.publish_library(out / 'belmonte', out / 'products/belmonte'))], cache=False, audit=False)
    ctx = SimpleNamespace(game='fixture', out=out, logs=out / 'logs', stamps=out / 'stamps', uproject=None)
    monkeypatch.setattr(build, 'Context', lambda *a, **kw: ctx)
    monkeypatch.setattr(build, 'load_recipe', lambda _: SimpleNamespace(steps=lambda _: [producer, selector, projection]))
    monkeypatch.setattr(build_checkpoints, 'configured', lambda _: None)
    def run():
        settings.write_text(json.dumps(selected))
        messages = []
        status = build.build('fixture', [projection.name], echo=messages.append)
        assert status == 0, '\n'.join(messages)
    run()
    sources = {p: p.read_bytes() for p in library.iterdir()}
    if change == 'remove': selected.update(models=['Prop'], hull=False)
    elif change == 'rename': selected['models'] = ['House', 'Renamed']
    else: selected['hull'] = False
    run()
    assert all(path.read_bytes() == data for path, data in sources.items())
    expected = {*selected['models'], 'SM_BM_NorthApron', 'SM_BM_NorthCountry'}
    if selected['hull']: expected.add('House_Collision')
    assert {p.stem for p in (out / 'belmonte/glb').iterdir()} == expected
    run()  # The ordinary next build remains current, without a cleanup command.


@pytest.mark.parametrize('fault', ['missing', 'file_link', 'directory_link', 'parent_link', 'escaping', 'root_file'])
def test_model_retirement_refuses_incomplete_or_linked_trees_before_deletion(tmp_path, fault):
    root = tmp_path / 'generated'
    root.mkdir()
    old, keep = root / 'old.glb', root / 'keep.glb'
    old.write_bytes(b'old'); keep.write_bytes(b'current')
    outside = tmp_path / 'source.glb'; outside.write_bytes(b'committed source')
    expected = ['keep.glb']
    if fault == 'missing': keep.unlink()
    elif fault == 'file_link': keep.unlink(); keep.symlink_to(outside)
    elif fault == 'directory_link': (root / 'linked').symlink_to(tmp_path, target_is_directory=True)
    elif fault == 'parent_link':
        (tmp_path / 'alias').symlink_to(tmp_path, target_is_directory=True)
        root = tmp_path / 'alias/generated'
    elif fault == 'escaping': expected = ['../source.glb']
    else: root = old
    with pytest.raises((OSError, ValueError)): model_files.retain_files(root, expected)
    assert old.read_bytes() == b'old' and outside.read_bytes() == b'committed source'
