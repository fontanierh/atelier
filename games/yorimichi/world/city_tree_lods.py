"""Isolated city-tree LODs: retain every leaf and simplify only its fan outline.

Run in guarded Blender. LOD0 is duplicated from the production Unreal asset by
the importer; this exporter writes only LOD1/2, never production FBXs.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parent)); import yori  # noqa: E402,F401
import argparse
import hashlib
import json
import sys
from pathlib import Path

import bpy
import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from hidamari import arcade, plaza
from village import build as village

BUILDERS = {'HD_ArcadeTree': arcade.tree, 'HD_PlazaTreeGold': plaza.tree,
            'HD_PlazaTreeOrange': lambda: plaza.tree(orange=True)}
# Preserve root, full left/right span and the highest arc corner. No leaf thinning.
CORNERS = {1: (0, 1, 3, 6, 8, 10), 2: (0, 1, 6, 10)}


def simplified(source, level):
    target = village.Mesh(source.name + f'_LOD{level}')
    leaf_faces = 0
    for face in source.faces:
        selected = face
        if len(face) == 11:
            # The generator emits front then reversed back faces. Select matching
            # physical corners on both sides, so the two outlines remain closed.
            corners = CORNERS[level]
            if leaf_faces % 2:
                corners = tuple(10-i for i in reversed(corners))
            selected = tuple(face[i] for i in corners)
            leaf_faces += 1
        first = len(target.vertices)
        target.vertices.extend(source.vertices[i] for i in selected)
        target.colors.extend(source.colors[i] for i in selected)
        target.faces.append(tuple(range(first, len(target.vertices))))
    expected = 15 * (310 if source.name == 'HD_ArcadeTree' else 210) * 2
    assert leaf_faces == expected, (source.name, 'unexpected leaf topology', leaf_faces)
    assert len(target.faces) == len(source.faces)
    # Front/back pairs must share exactly the same positions in reverse order.
    # Other scene polygons can have this corner count; select source leaf slots.
    leaves = [target.faces[i] for i, f in enumerate(source.faces) if len(f) == 11]
    for a, b in zip(leaves[::2], leaves[1::2]):
        assert [target.vertices[i] for i in a] == [target.vertices[i] for i in reversed(b)]
    return target, leaf_faces // 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    assert args.tag.replace('_', '').isalnum()
    folder = yori.OUT/'city_tree_lods'/args.tag
    if folder.exists():   # a rebuild replaces this tag's previous output
        __import__('shutil').rmtree(folder)
    folder.mkdir(parents=True, exist_ok=False)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    material = bpy.data.materials.new('HidamariPalette')
    receipt = json.loads((yori.OUT/'hidamari/manifest.json').read_text())
    report = dict(tag=args.tag, sources={}, screen_sizes=[1., .18, .07])
    for name, build in BUILDERS.items():
        source = build()
        original_triangles = sum(len(f)-2 for f in source.faces)
        assert original_triangles == receipt[name]['triangles'], (name, 'generator differs from production')
        positions = np.array(source.vertices)
        for actual, key in [(positions.min(axis=0), 'min'), (positions.max(axis=0), 'max')]:
            assert np.allclose(actual, receipt[name][key], atol=.001, rtol=0), (name, key)
        entry = dict(original_triangles=original_triangles,
                     source_fbx_sha256=hashlib.sha256((yori.OUT/'hidamari/assets'/f'{name}.fbx').read_bytes()).hexdigest(),
                     lods=[])
        for level in CORNERS:
            mesh, leaves = simplified(source, level)
            obj = mesh.object(material)
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj
            path = folder/f'{mesh.name}.fbx'
            bpy.ops.export_scene.fbx(filepath=str(path), use_selection=True,
                apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL', axis_forward='-Y', axis_up='Z',
                object_types={'MESH'}, mesh_smooth_type='FACE', bake_anim=False, use_custom_props=False)
            entry['lods'].append(dict(level=level, file=path.name, leaves=leaves,
                triangles=sum(len(f)-2 for f in mesh.faces), sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
            bpy.data.objects.remove(obj, do_unlink=True)
        report['sources'][name] = entry
    report['complete'] = True
    (folder/'manifest.json').write_text(json.dumps(report, indent=2)+'\n')
    print('CITY TREE LODS COMPLETE', json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
