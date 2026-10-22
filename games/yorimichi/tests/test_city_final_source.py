"""Final-source selection must refuse before Blender or output mutation."""
import ast
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_volcano_layers import RECIPE


@pytest.fixture
def selected_source(tmp_path, monkeypatch):
    import argparse
    source = tmp_path/'hidamari/ferry/HD_Harbor.fbx'
    source.parent.mkdir(parents=True)
    source.write_bytes(b'final cut')
    metadata = tmp_path/'digests/harbor-source.json'
    metadata.parent.mkdir()
    row = dict(source='HD_Harbor', source_path='hidamari/ferry/HD_Harbor.fbx',
               source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
               triangles=190896, min=[0, 0, 0], max=[1, 1, 1], collision_boxes=0)
    metadata.write_text(json.dumps(row))
    touched = []

    def partition(name, folder, size, expected, **kwargs):
        touched.append((name, expected, kwargs))
        return dict(tiles=[])

    script = RECIPE.WORLD/'city_surface_tiles.py'
    main = next(n for n in ast.parse(script.read_text()).body if isinstance(n, ast.FunctionDef) and n.name == 'main')
    namespace = dict(argparse=argparse, hashlib=hashlib, json=json, math=math, re=re, sys=sys,
        Path=Path, TRIANGLE_LIMIT=32768, yori=SimpleNamespace(OUT=tmp_path), partition=partition,
        bpy=SimpleNamespace(ops=SimpleNamespace(wm=SimpleNamespace(read_factory_settings=lambda **kw:touched.append('reset')))),
        atomic_json=lambda *args: None, retain_files=lambda *args: None)
    exec(compile(ast.Module(body=[main], type_ignores=[]), str(script), 'exec'), namespace)

    def run(source_path='hidamari/ferry/HD_Harbor.fbx', metadata_path='digests/harbor-source.json', names=('HD_Harbor',)):
        argv = ['splitter', '--', '--tag', 'v1_128m', '--sources', *names]
        if source_path is not None: argv += ['--source-path', source_path]
        if metadata_path is not None: argv += ['--metadata-path', metadata_path]
        monkeypatch.setattr(sys, 'argv', argv)
        namespace['main']()

    return SimpleNamespace(root=tmp_path, source=source, metadata=metadata, row=row, touched=touched, run=run)


def test_final_source_uses_exact_selected_path_and_post_cut_metadata(selected_source):
    p = selected_source
    p.run()
    assert p.touched == ['reset', ('HD_Harbor', p.row, {'source_path': p.source})]


@pytest.mark.parametrize('bad', ['missing_path', 'missing_metadata', 'multiple', 'absolute', 'parent',
    'dot', 'double_slash', 'backslash', 'source_link', 'ancestor_link', 'basename', 'wrong_source',
    'triangles', 'collision', 'nonfinite', 'reversed', 'extra', 'changed_bytes', 'wrong_path'])
def test_invalid_final_source_never_touches_blender_or_outputs(selected_source, bad):
    p = selected_source
    args = {}
    if bad == 'missing_path': args['source_path'] = None
    elif bad == 'missing_metadata': args['metadata_path'] = None
    elif bad == 'multiple': args['names'] = ('HD_Harbor', 'HD_Park')
    elif bad == 'absolute': args['source_path'] = str(p.source)
    elif bad == 'parent': args['source_path'] = 'hidamari/ferry/../ferry/HD_Harbor.fbx'
    elif bad == 'dot': args['source_path'] = './hidamari/ferry/HD_Harbor.fbx'
    elif bad == 'double_slash': args['source_path'] = 'hidamari//ferry/HD_Harbor.fbx'
    elif bad == 'backslash': args['source_path'] = r'hidamari\ferry\HD_Harbor.fbx'
    elif bad == 'source_link':
        p.source.rename(p.source.with_suffix('.original'))
        p.source.symlink_to(p.source.with_suffix('.original'))
    elif bad == 'ancestor_link':
        p.source.parent.rename(p.source.parent.with_name('original'))
        p.source.parent.symlink_to(p.source.parent.with_name('original'), target_is_directory=True)
    elif bad == 'basename':
        other = p.source.with_name('HD_Park.fbx'); other.write_bytes(b'other')
        args['source_path'] = str(other.relative_to(p.root))
    else:
        if bad == 'wrong_source': p.row['source'] = 'HD_Park'
        elif bad == 'changed_bytes': p.source.write_bytes(b'changed cut')
        elif bad == 'wrong_path': p.row['source_path'] = 'hidamari/assets/HD_Harbor.fbx'
        elif bad == 'triangles': p.row['triangles'] = True
        elif bad == 'collision': p.row['collision_boxes'] = -1
        elif bad == 'nonfinite': p.row['min'][0] = float('nan')
        elif bad == 'reversed': p.row['min'][0] = 2
        elif bad == 'extra': p.row['other'] = 'unknown'
        p.metadata.write_text(json.dumps(p.row))
    with pytest.raises((AssertionError, ValueError)):
        p.run(**args)
    assert p.touched == []
    assert not (p.root/'city_surface_tiles').exists()
