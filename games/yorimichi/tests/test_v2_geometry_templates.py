from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import v2_geometry_templates as gt  # noqa: E402

CHECKOUT = Path(__file__).resolve().parents[3]


def _rows(encoding='encoded_glb'):
    logical = [['HD_A', {'path': 'build/y/planned_exports/r/HD_A'}, 'world.r.geometry.HD_A', 'r.geometry.HD_A', encoding],
               ['HD_B', {'path': 'build/y/planned_exports/r/HD_B'}, 'world.r.geometry.HD_B', 'r.geometry.HD_B', encoding]]
    planners = [{'id': f'world.r.geometry.{key}', 'products': [{'id': f'r.geometry.{key}',
                 'paths': [f'build/y/planned_exports/r/{key}'], 'optional_paths': []}], 'commands': [], 'replan': False}
                for key in ('HD_A', 'HD_B')]
    discover = {'id': 'world.r.geometry', 'replan': True, 'products': [], 'commands': [{'kind': 'call', 'fn': {
        'source': gt.REGION_EXPORTS, 'qualname': 'steps.<locals>.discover', 'closure': [{'path': 'x'}, logical]}}]}
    assemble = {'id': 'world.r.assembled', 'replan': False, 'products': [], 'commands': [{'kind': 'call', 'fn': {
        'source': gt.REGION_EXPORTS, 'qualname': 'steps.<locals>.assemble',
        'closure': [[], {'path': 'build/y/atomic_regions/r'}, logical, 'r']}}]}
    return [*planners, discover, assemble]


def test_encoded_templates_use_the_lossless_body_with_core_injected_params():
    out = gt.geometry_templates(_rows(), checkout=CHECKOUT)
    assert len(out['templates']) == 2
    template = out['templates'][0]
    assert template['op'] == {'kind': 'encoded_export_piece', 'version': '1'}
    assert template['script'] == gt.ENCODED_SCRIPT and template['params'] == {}
    assert template['files'] == [{'path': '$piece.glb'}, {'path': 'export.json'}]
    assert gt.ENCODED_SCRIPT in template['code'] and 'platform/studio/atelier/encoded_glb.py' in template['code']
    assert set(out['groups']) == {'world.r.geometry.HD_A', 'world.r.geometry.HD_B'}


def test_mesh_ir_templates_keep_the_fbx_body():
    template = gt.geometry_templates(_rows('mesh_ir'), checkout=CHECKOUT)['templates'][0]
    assert template['op'] == {'kind': 'blender_export_piece', 'version': '1'} and template['script'] == gt.EXPORT_SCRIPT


def test_assembly_children_become_one_ordered_derived_token():
    rows = _rows()
    out = gt.geometry_templates(rows, checkout=CHECKOUT)
    assert out['derived'] == [{'unit': 'world.r.assembled', 'command': 0, 'capture': 0, 'value': {'derived_items': {
        'root': 'build/v2-derived/r', 'templates': [
            {'producer': 'world.r.geometry.HD_A', 'group': 'geometry', 'unit_prefix': 'world.r.export.HD_A'},
            {'producer': 'world.r.geometry.HD_B', 'group': 'geometry', 'unit_prefix': 'world.r.export.HD_B'}]}}}]
    applied = gt.apply_derived(rows, out['derived'])
    assert applied[-1]['commands'][0]['fn']['closure'][0] == out['derived'][0]['value']
    assert rows[-1]['commands'][0]['fn']['closure'][0] == []  # the input rows are unchanged


@pytest.mark.parametrize('change', ['region', 'parents', 'extra'])
def test_assembly_capture_mismatches_refuse(change):
    rows = _rows()
    closure = rows[-1]['commands'][0]['fn']['closure']
    if change == 'region':
        closure[3] = 'other'
    if change == 'parents':
        closure[2] = closure[2][:1]
    if change == 'extra':
        closure.append([])
    with pytest.raises(gt.Unsupported, match='world.r.assembled'):
        gt.geometry_templates(rows, checkout=CHECKOUT)
