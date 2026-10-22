"""Exporter metadata migration preserves independently bound art and prepared grip geometry."""
import ast
import hashlib
import inspect
import json
from pathlib import Path

GAME = Path(__file__).resolve().parents[1]
ROOT = GAME.parents[1]
PROOF = json.loads((GAME / 'assets/fbx-boundary-revalidation.json').read_text())


def sha(data):
    return hashlib.sha256(data).hexdigest()


def geometry_ast(text, resource_path_only=False):
    class Boundary(ast.NodeTransformer):
        def visit_ImportFrom(self, node):
            if node.module == 'atelier.blender.fbx':
                assert [(a.name, a.asname) for a in node.names] == [('export_fbx', 'export_scene_fbx')]
                return None
            return node

        def visit_Call(self, node):
            self.generic_visit(node)
            if isinstance(node.func, ast.Name) and node.func.id == 'export_scene_fbx':
                node.func = ast.parse('bpy.ops.export_scene.fbx', mode='eval').body
            return node

        def visit_Assign(self, node):
            if (resource_path_only and any(isinstance(t, ast.Name) and t.id == 'FBX' for t in node.targets)
                    and isinstance(node.value, ast.Call)):
                assert isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name) and node.value.func.id == 'dict'
                option, = [k for k in node.value.keywords if k.arg == 'path_mode']
                assert isinstance(option.value, ast.Constant) and option.value.value in ('RELATIVE', 'ABSOLUTE')
                option.value.value = 'ABSOLUTE'
            return self.generic_visit(node)
    # Python 3.12 added empty type_params fields; absence and an empty list
    # represent the same non-generic declaration on supported interpreters.
    options = {'show_empty': True} if 'show_empty' in inspect.signature(ast.dump).parameters else {}
    return sha(ast.dump(Boundary().visit(ast.parse(text)), include_attributes=False, **options)
               .replace(', type_params=[]', '').encode())


def test_source_only_export_migration_and_negative_geometry_controls():
    assert sha((ROOT / 'platform/studio/atelier/blender/fbx.py').read_bytes()) == PROOF['exporter_sha256']
    for rel, row in PROOF['files'].items():
        text = (ROOT / rel).read_text()
        assert sha(text.encode()) == row['current_sha256']
        assert geometry_ast(text, row['resource_path_only']) == row['geometry_ast_sha256']
        assert geometry_ast(text + '\ngeometry_changed = 1\n', row['resource_path_only']) != row['geometry_ast_sha256']
        if row['resource_path_only']:
            assert geometry_ast(text.replace('add_leaf_bones=False', 'add_leaf_bones=True'), True) != row['geometry_ast_sha256']


def test_only_current_source_bindings_changed_in_art_and_grip_records():
    # Reconstruct each exact original record; all images, original paid generation
    # inputs, model/bind/pose/scale data and historical witnesses remain significant.
    by_new = {v['current_sha256']:v['previous_sha256'] for v in PROOF['files'].values()}
    def previous_geography(value):
        return {k:by_new.get(v, v) for k,v in value.items()}
    for rel, evidence in PROOF['atlas'].items():
        data = (ROOT / rel).read_bytes()
        assert sha(data) == evidence['current_record_sha256']
        record = json.loads(data)
        if 'geography' in record:
            record['geography'] = previous_geography(record['geography'])
        for name in ('generation_witness', 'verified_geography'):
            if isinstance(record.get(name), dict):
                record[name]['geography'] = previous_geography(record[name]['geography'])
        assert sha((json.dumps(record, indent=2)+'\n').encode()) == evidence['previous_record_sha256']
    for rel, evidence in PROOF['grips'].items():
        data = (ROOT / rel).read_bytes()
        assert sha(data) == evidence['current_record_sha256']
        record = json.loads(data)
        assert record['source_sha256'] == evidence['current_source_sha256']
        assert record['model_sha256'] == evidence['unchanged_model_sha256']
        record['source_sha256'] = evidence['previous_source_sha256']
        assert sha((json.dumps(record, indent=2)+'\n').encode()) == evidence['previous_record_sha256']
