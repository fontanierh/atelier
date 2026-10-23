"""Diagnostic scene placement from the current assembled independent railway GLBs."""
import json
import math
from pathlib import Path

from atelier.export_manifest import name, real_directory, sha
from atelier.encoded_glb import geometry
from atelier.model_files import regular_files


def read(source):
    source = Path(source); real_directory(source.parent)
    if source.is_symlink() or not source.is_file() or source.parent.name != 'atomic':
        raise ValueError('Track review requires its explicit assembled atomic track.json')
    doc = json.loads(source.read_text()); root = source.parent.parent
    path = source.parent / 'meshes/manifest.json'; real_directory(path.parent)
    if path.is_symlink() or not path.is_file(): raise ValueError('Missing current railway assembly inventory')
    manifest = json.loads(path.read_text())
    if manifest.get('schema') != 1 or manifest.get('complete') is not True: raise ValueError('Incomplete railway assembly')
    receipts = {row['asset']: row for row in manifest['exports']}
    if len(receipts) != len(manifest['exports']): raise ValueError('Aliased railway review exports')
    expected = set()
    for parent, spec in doc['meshes'].items():
        name(parent)
        if not spec['lods']: raise ValueError('Missing authored railway LODs')
        for level, relative in enumerate(spec['lods']):
            key = f'{parent}_LOD{level}'; primary = key + '.glb'
            if relative != 'atomic/meshes/' + primary: raise ValueError('Escaping railway review source')
            row = receipts[key]; mesh = root / relative
            if row.get('schema') != 1 or row['asset'] != key or row['primary'] != primary or row['sha256'] != sha(mesh):
                raise ValueError('Changed railway review export')
            if geometry(mesh.read_bytes())['triangles'] != row['triangles']:
                raise ValueError('Railway diagnostic primary differs from its bounded source')
            expected.add(primary)
    if set(receipts) != {Path(primary).stem for primary in expected} or regular_files(path.parent) != expected | {'manifest.json'}:
        raise ValueError('Foreign or incomplete railway review library')
    return root, doc


def origins(doc):
    rows = [*doc['chunks'], *doc.get('banks', []),
            *(row for tunnel in doc['tunnels'] for row in tunnel['lining']),
            *(row for viaduct in doc['viaducts'] for row in viaduct['pieces']),
            *doc.get('station', {}).get('pieces', [])]
    if doc.get('overbridge'): rows.append(doc['overbridge'])
    result = {}
    for row in rows:
        if row['name'] in result: raise ValueError('Repeated diagnostic railway origin')
        result[row['name']] = row['origin']
    return result


def instances(doc, parent):
    rows = doc['instances'][parent]
    return [row for group in rows.values() for row in group] if isinstance(rows, dict) else rows


class Library:
    """@cc [owner:fontanierh,label:correctness] diagnostic-track-uses-assembled-geometry
    Diagnostic views MUST import the current assembled separate GLBs and preserve their
    authored mesh/material state and published placement frames. Instances MUST share
    the imported mesh data; never call a legacy constructor/exporter or join geometry.
    """
    def __init__(self, source):
        self.root, self.doc = read(source)
        self.templates = {}

    def place(self, parent, rows):
        import bpy
        from mathutils import Matrix
        if parent not in self.templates:
            path = self.root / self.doc['meshes'][parent]['lods'][0]
            identity = sha(path); before = set(bpy.data.objects)
            bpy.ops.import_scene.gltf(filepath=str(path))
            if sha(path) != identity: raise ValueError('Railway review source changed during import')
            objects = [obj for obj in bpy.data.objects if obj not in before]
            if not objects or any(obj.type not in ('MESH', 'EMPTY') for obj in objects):
                raise ValueError('Unsupported assembled railway diagnostic objects')
            self.templates[parent] = objects
            for obj in objects: obj.hide_render = True; obj.hide_set(True)
        templates = self.templates[parent]; made = []
        for index, (x, y, z, yaw, scale) in enumerate(rows):
            anchor = bpy.data.objects.new(f'{parent}_placement_{index}', None)
            bpy.context.scene.collection.objects.link(anchor)
            anchor.matrix_world = (Matrix.Translation((x, y, z)) @ Matrix.Rotation(math.radians(yaw), 4, 'Z')
                                   @ Matrix.Diagonal((1., scale, 1., 1.)))
            copies = {obj: obj.copy() for obj in templates}
            for original, obj in copies.items():
                bpy.context.scene.collection.objects.link(obj)
                obj.parent = copies.get(original.parent, anchor)
                obj.hide_render = False; obj.hide_set(False)
                made.append(obj)
        return made
