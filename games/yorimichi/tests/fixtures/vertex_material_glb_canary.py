"""Actual immutable material graph and GLB serializer versus schema3 atomic reconstruction."""
import argparse
import ast
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

import bpy

GAME = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(GAME / 'world'))
import yori  # noqa: E402,F401
from atelier import mesh_ir, mesh_materials  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import real_directory, sha  # noqa: E402
from region_mesh_parts import plan  # noqa: E402
import export_region_piece  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--counter', type=Path, required=True)
    parser.add_argument('--counter-sha', required=True)
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    output = real_directory(args.output)
    if output.exists(): raise ValueError('Fresh finite-material GLB evidence required')
    fixture = Path(__file__).with_name('stable-predecessor-283329c07.txt')
    if sha(fixture) != args.source_sha or sha(args.counter) != args.counter_sha:
        raise ValueError('Frozen original material or independent counter differs')
    tree = ast.parse(fixture.read_text())
    tree.body = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ('material', 'export_glb')]
    if {n.name for n in tree.body} != {'material', 'export_glb'}: raise ValueError('Missing original material/export functions')
    old = dict(bpy=bpy, MATERIAL='M_HS_Stable')
    exec(compile(tree, str(fixture), 'exec'), old)
    # Only the independently maintained pure numeric GLB parser is executed here.
    # Git authority is checked by the outer host, never inside a guarded child.
    functions = {'canonical', 'finite', 'require', '_digest', 'glb_counter'}
    parsed = ast.parse(args.counter.read_text())
    parsed.body = [node for node in parsed.body if (isinstance(node, ast.FunctionDef) and node.name in functions)
                   or (isinstance(node, ast.ClassDef) and node.name == 'EvidenceError')]
    if {node.name for node in parsed.body} != functions | {'EvidenceError'}:
        raise ValueError('Independent GLB counter layout changed')
    counter = dict(json=json, hashlib=hashlib, math=math, struct=struct, Counter=Counter)
    exec(compile(parsed, str(args.counter), 'exec'), counter)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    material = old['material']()
    data = bpy.data.meshes.new('Control')
    data.from_pydata([(0,0,0),(2,0,0),(2,1,0),(0,1,0)], [], [(0,1,2,3)]); data.update()
    data.materials.append(material)
    unused = bpy.data.materials.new('Unused'); data.materials.append(unused)
    uv = data.uv_layers.new(name='UVMap')
    for value, xy in zip(uv.data, ((0,0),(2,0),(2,1),(0,1))): value.uv = xy
    colour = data.color_attributes.new(name='Color', type='FLOAT_COLOR', domain='POINT')
    for value, rgba in zip(colour.data, ((.1,.2,.3,1),(.2,.4,.6,1),(.8,.3,.2,1),(.1,.7,.4,1))): value.color = rgba
    obj = bpy.data.objects.new('Control', data); bpy.context.collection.objects.link(obj)
    output.mkdir()
    control = output / 'original.glb'; old['export_glb'](control, [obj])
    specs = mesh_materials.capture_slots(obj)
    assert specs[1] is None
    value = plan(obj, output / 'plan', partition='whole', options=dict(export_apply=True), material_specs=specs)
    payload = output / 'plan' / value['pieces'][0]['payload']; original_payload = payload.read_bytes()
    unused.use_nodes = True; unused.node_tree.nodes.new('ShaderNodeValue')
    plan(obj, output / 'plan', partition='whole', options=dict(export_apply=True), material_specs=mesh_materials.capture_slots(obj))
    assert payload.read_bytes() == original_payload, 'Unused material graph changed the consumed leaf'
    metadata, _ = mesh_ir.decode(original_payload)
    assert metadata['schema'] == 3 and metadata['slots'] == ['M_HS_Stable'] and metadata['material_specs'] == [specs[0]]
    export_region_piece.main(['--input', str(payload), '--output', str(output / 'atomic'), '--format', '.glb'])
    current = output / 'atomic/Control.glb'
    before, triangles = counter['glb_counter'](control.read_bytes())
    after, actual_triangles = counter['glb_counter'](current.read_bytes())
    assert before == after and triangles == actual_triangles == 2, 'Complete GLB corners/material JSON differ'
    bad = old['material']('Unsupported')
    bad.node_tree.nodes.new('ShaderNodeValue')
    try: mesh_materials.capture(bad)
    except ValueError: pass
    else: raise ValueError('Unsupported shader graph was silently approximated')
    assert sha(fixture) == args.source_sha and sha(args.counter) == args.counter_sha
    atomic_json(output / 'result.json', dict(complete=True, numeric_glb_corner_material_union=True,
        triangles=triangles, material_spec=specs[0],
        original_glb_sha256=sha(control), actual_glb_sha256=sha(current), independent_counter_sha256=args.counter_sha))
    print('FINITE MATERIAL EXACT GLB EQUIVALENCE COMPLETE', flush=True)


if __name__ == '__main__': main()
