"""Portable D2 decoder/ownership/failure checks; no Blender export fidelity claim."""
import hashlib
import io
import json
import os
import runpy
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from atelier import mesh_ir, mesh_collision
from atelier.build_v2 import blender_ops as ops
from atelier.build_v2.blender_validate import mesh_facts, validate_export_receipt, FBX_HEADER, decode_mesh_payload
from test_mesh_ir import payload


LIMITS = dict(max_pieces=8, max_manifest_bytes=1024 * 1024,
              max_member_bytes=mesh_ir.MAX_BYTES, max_total_bytes=2 * mesh_ir.MAX_BYTES)


def emit_plan(root, *, whole_collision=False):
    meta, original = mesh_ir.decode(payload())  # independent existing source fixture/decoder
    rows = []
    for index, asset in enumerate(['Whole_A', 'Whole_B']):
        piece = dict(original)
        piece['positions'] = original['positions'] + [index * 2, 0, 0]
        collision_piece = dict(original, positions=np.vstack([original['positions'], [0, 0, 1]]).astype('<f4'))
        collision_piece['colours'] = [(label, domain, kind, np.vstack([values, values[0]]) if domain == 'POINT' else values) for label, domain, kind, values in original['colours']]
        collisions = [mesh_collision.encode(collision_piece, slots=['Material'], matrix=meta['matrix'])] if whole_collision and index == 0 else []
        raw = mesh_ir.encode(piece, key=asset, slots=meta['slots'], matrix=meta['matrix'], options={}, collisions=collisions)
        (root / (asset + '.npz')).write_bytes(raw)
        rows.append(dict(name=asset, payload=asset + '.npz', sha256=hashlib.sha256(raw).hexdigest(),
                         triangles=1, polygons=1, source_faces=[index],
                         min=[index * 2, 0, 0], max=[index * 2 + 1, 1, 0], collision_hulls=len(collisions),
                         slots=['Material'], source_material_indices=[0]))
    value = dict(schema=1, parent='Whole', complete=True, triangle_limit=32768, partition='logical',
                 collision_owner='Whole_A' if whole_collision else None, source_triangles=2, source_polygons=2,
                 source_collision_hulls=int(whole_collision),
                 slots=['Material'], matrix=np.eye(4).tolist(), pieces=rows)
    (root / 'plan.json').write_text(json.dumps(value, sort_keys=True))
    return value


def planned(tmp_path):
    root = tmp_path / 'plan'
    root.mkdir()
    return root, emit_plan(root)


def test_existing_decoder_and_in_job_plan_preserve_complete_corner_and_owner_data(tmp_path):
    root, value = planned(tmp_path)
    assert ops.verify_plan(root, parent='Whole', limits=LIMITS) == value
    raw = (root / 'Whole_A.npz').read_bytes()
    meta, piece = mesh_ir.decode(raw)
    facts = mesh_facts(raw, expected_asset='Whole_A')
    assert facts['uv_channels'] == ['UVMap', 'Piece1']
    assert facts['colour_channels'] == [['Color', 'POINT', 'BYTE_COLOR']]
    assert piece['normals'].tobytes() == np.asarray([[0, -0.0, 1]] * 3, dtype='<f4').tobytes()
    assert facts['slots'] == meta['slots'] == ['Material']
    assert facts['min'] == [0, 0, 0] and facts['max'] == [1, 1, 0]


@pytest.mark.parametrize('material_graph', [False, True])
def test_producer_checks_original_glb_settings_without_authorizing_fbx(tmp_path, material_graph):
    from test_mesh_materials import spec
    root, value = planned(tmp_path)
    options = dict(export_apply=True, export_image_format='AUTO' if material_graph else 'NONE')
    for row in value['pieces']:
        path = root / row['payload']
        meta, piece = mesh_ir.decode(path.read_bytes())
        raw = mesh_ir.encode(piece, key=meta['asset'], slots=meta['slots'], matrix=meta['matrix'],
                             options=options, material_specs=[spec()] if material_graph else None)
        path.write_bytes(raw)
        row['sha256'] = hashlib.sha256(raw).hexdigest()
        assert mesh_facts(raw, output_format=None)['options'] == options
        with pytest.raises(ValueError):
            mesh_facts(raw)  # The FBX consumer still refuses GLB settings/materials.
    (root / 'plan.json').write_text(json.dumps(value))
    assert ops.verify_plan(root, parent='Whole', limits=LIMITS, output_format='glb') == value


@pytest.mark.parametrize('options', [dict(export_apply=1), dict(export_image_format='JPEG'),
                                     dict(export_apply=True, global_scale=1), dict(filepath='foreign.glb')])
def test_glb_options_remain_finite_and_do_not_mix_fbx_ownership(options):
    from atelier.build_v2.blender_validate import validate_mesh_options
    with pytest.raises(ValueError):
        validate_mesh_options(options, output_format='glb')


@pytest.mark.parametrize('fault', ['truncated', 'extra', 'missing', 'alias', 'overlap', 'bound', 'hash'])
def test_producer_refuses_bad_emitted_inventory_and_bindings(tmp_path, fault):
    root, value = planned(tmp_path)
    if fault == 'truncated':
        path = root / 'Whole_A.npz'
        path.write_bytes(path.read_bytes()[:20])
        value['pieces'][0]['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    elif fault == 'extra':
        (root / 'unowned.bin').write_bytes(b'foreign')
    elif fault == 'missing':
        (root / 'Whole_A.npz').unlink()
    elif fault == 'alias':
        value['pieces'][1]['name'] = 'whole_a'
    elif fault == 'overlap':
        value['pieces'][1]['source_faces'] = [0]
    elif fault == 'bound':
        value['pieces'][0]['max'] = [99, 1, 0]
    else:
        value['pieces'][0]['sha256'] = '0' * 64
    (root / 'plan.json').write_text(json.dumps(value))
    with pytest.raises((ValueError, OSError)):
        ops.verify_plan(root, parent='Whole', limits=LIMITS)


def test_plan_links_limits_and_whole_collision_misownership_refuse(tmp_path):
    root, value = planned(tmp_path)
    path = root / 'Whole_A.npz'
    outside = tmp_path / 'outside'
    outside.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(outside)
    with pytest.raises(ValueError, match='link'):
        ops.verify_plan(root, parent='Whole', limits=LIMITS)
    path.unlink()
    path.write_bytes(outside.read_bytes())
    with pytest.raises(ValueError, match='count'):
        ops.verify_plan(root, parent='Whole', limits={**LIMITS, 'max_pieces': 1})
    value['collision_owner'] = 'Whole_B'
    value['source_collision_hulls'] = 1
    (root / 'plan.json').write_text(json.dumps(value))
    with pytest.raises(ValueError, match='collision'):
        ops.verify_plan(root, parent='Whole', limits=LIMITS)
    assert outside.read_bytes() == path.read_bytes()


def test_whole_collision_corner_payload_belongs_to_one_explicit_piece(tmp_path):
    root = tmp_path / 'plan'
    root.mkdir()
    emit_plan(root, whole_collision=True)
    value = ops.verify_plan(root, parent='Whole', limits=LIMITS)
    assert [row['collision_hulls'] for row in value['pieces']] == [1, 0]
    meta, _piece = mesh_ir.decode((root / 'Whole_A.npz').read_bytes())
    collision = mesh_collision.decode(meta['collisions'][0])
    assert collision['normals'].tobytes() == np.asarray([[0, -0.0, 1]] * 3, dtype='<f4').tobytes()


def test_run_plan_uses_only_keyed_owned_output_root_and_checks_before_return(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path('output').mkdir()
    context = SimpleNamespace(params=dict(output_root='output/pieces', parent='Whole', plan_limits=LIMITS))
    value = ops.run_plan(context, emit_plan)
    assert [r['name'] for r in value['pieces']] == ['Whole_A', 'Whole_B']
    with pytest.raises(FileExistsError):
        ops.run_plan(context, emit_plan)
    context.params['output_root'] = '../foreign'
    with pytest.raises(ValueError, match='root'):
        ops.run_plan(context, emit_plan)
    assert not (tmp_path.parent / 'foreign').exists()


def test_selected_payload_consumer_refuses_wrong_role_and_malformed_bytes_before_blender(tmp_path, monkeypatch):
    def unexpected(*_args, **_kwargs):
        pytest.fail('invalid selected payload reached Blender export')
    monkeypatch.setattr(ops, '_export_mesh', unexpected)
    root, _value = planned(tmp_path)
    (root / 'Whole_B.npz').unlink()
    (root / 'plan.json').unlink()
    context = SimpleNamespace(params=dict(format='fbx', payload_encoding='mesh_ir', payload_role='collision',
                                          payload_member='Whole_A.npz'), inputs={'payload': root},
                              outputs=['Whole_A.fbx', 'export.json'])
    with pytest.raises(ValueError, match='selected'):
        ops.run_export_piece(context)
    context.params['payload_role'] = 'geometry'
    (root / 'Whole_A.npz').write_bytes(b'truncated mesh')
    with pytest.raises((ValueError, OSError)):
        ops.run_export_piece(context)
    assert not (tmp_path / 'export.json').exists()


def test_real_serializer_parse_refusal_prevents_receipt_success(tmp_path, monkeypatch):
    root, _value = planned(tmp_path)
    (root / 'Whole_B.npz').unlink()
    (root / 'plan.json').unlink()
    out = tmp_path / 'output'
    out.mkdir()
    context = SimpleNamespace(params=dict(format='fbx', payload_encoding='mesh_ir', payload_role='geometry',
                                          payload_member='Whole_A.npz'), inputs={'payload': root},
                              outputs=['asset.fbx', 'export.json'], output=lambda name: out / name)
    # Failure injection only: no stand-in serializer success or native-fidelity claim.
    selected = []
    def failed_serializer(asset, _meta, _piece, path, _options):
        selected.append((asset, path.name))
        path.write_bytes(b'truncated')
    monkeypatch.setattr(ops, '_export_mesh', failed_serializer)
    def refused(_path, **_kwargs):
        raise ValueError('existing FBX parser refused serialization')
    monkeypatch.setattr(ops, 'verify_emitted_fbx', refused)
    with pytest.raises(ValueError, match='parser refused'):
        ops.run_export_piece(context)
    assert selected == [('Whole_A', 'asset.fbx')]
    assert not (out / 'export.json').exists()


def test_receipt_and_binary_framing_check_never_claims_native_fidelity():
    facts = mesh_facts(payload(), expected_asset='Part')
    primary = FBX_HEADER + b'bounded-framing-fixture'
    digest = hashlib.sha256(primary).hexdigest()
    source_digest = hashlib.sha256(payload()).hexdigest()
    receipt = dict(schema=1, asset='Part', primary='Part.fbx', triangles=1, bounds=[[0, 0, 0], [1, 1, 0]],
                   sha256=digest, metadata=dict(geometry_sha256=source_digest, slots=['Material'], polygons=1,
                                               collision_hulls=0, uv_channels=['UVMap', 'Piece1']))
    raw = json.dumps(receipt).encode()
    generic = dict(receipt, primary='asset.fbx')
    assert validate_export_receipt(json.dumps(generic).encode(), primary, asset='Part', primary_name='asset.fbx',
                                   primary_digest=digest, payload_digest=source_digest, facts=facts) == generic
    assert validate_export_receipt(raw, primary, asset='Part', primary_digest=digest,
                                    payload_digest=source_digest, facts=facts) == receipt
    for broken in [b'{}', raw[:-1], raw.replace(b'"Part.fbx"', b'"Other.fbx"')]:
        with pytest.raises(ValueError):
            validate_export_receipt(broken, primary, asset='Part', primary_digest=digest,
                                    payload_digest=source_digest, facts=facts)
    with pytest.raises(ValueError, match='FBX'):
        validate_export_receipt(raw, b'truncated', asset='Part', primary_digest=digest,
                                payload_digest=source_digest, facts=facts)


@pytest.mark.parametrize('material_graph', [False, True])
def test_glb_consumer_preserves_exact_options_and_refuses_truncated_serializer(tmp_path, monkeypatch, material_graph):
    from test_mesh_materials import spec
    root = tmp_path / 'selected'
    root.mkdir()
    out = tmp_path / 'output'
    out.mkdir()
    meta, piece = mesh_ir.decode(payload())
    options = dict(export_apply=True, export_image_format='AUTO' if material_graph else 'NONE')
    raw = mesh_ir.encode(piece, key='Part', slots=meta['slots'], matrix=meta['matrix'], options=options,
                         material_specs=[spec()] if material_graph else None)
    (root / 'Part.npz').write_bytes(raw)
    context = SimpleNamespace(params=dict(format='glb', payload_encoding='mesh_ir', payload_role='geometry',
                                          payload_member='Part.npz'), inputs={'payload': root},
                              outputs=['Part.glb', 'export.json'], output=lambda name: out / name)
    called = []
    def truncated(asset, metadata, _piece, path, actual):
        called.append((asset, metadata['schema'], path.name, actual))
        path.write_bytes(b'truncated')
    monkeypatch.setattr(ops, '_export_mesh', truncated)
    with pytest.raises((ValueError, __import__('struct').error)):
        ops.run_export_piece(context)
    assert called == [('Part', 3 if material_graph else 2, 'Part.glb', options)]
    assert not (out / 'export.json').exists()
    assert (root / 'Part.npz').read_bytes() == raw


def test_per_piece_options_cannot_widen_owned_outputs_or_silently_override_selection():
    assert ops.export_options({'axis_forward': '-Y'}, {'axis_up': 'Z'}) == {'axis_forward': '-Y', 'axis_up': 'Z'}
    for options in [{'filepath': 'foreign.fbx'}, {'use_selection': False}, {'bake_anim': True},
                    {'object_types': ['LIGHT']}, {'batch_mode': 'SCENE'}, {'path_mode': 'COPY'}]:
        with pytest.raises(ValueError):
            ops.export_options(options, {})


def test_retained_village_schema2_sample_decodes_complete_mesh_and_owned_collision(tmp_path, monkeypatch):
    """Old source sample coverage only; no reconstructed execution or native fidelity claim."""
    root = Path(__file__).resolve().parents[2] / 'build-v2/tests/fixtures/blender'
    raw = (root / 'Village_Edges.npz').read_bytes()
    provenance = json.loads((root / 'Village_Edges.provenance.json').read_bytes())
    assert hashlib.sha256(raw).hexdigest() == provenance['sha256']
    assert len(raw) == provenance['bytes'] == 138217
    meta, piece, facts = decode_mesh_payload(raw)
    assert meta['schema'] == 2
    assert facts['asset'] == 'Village_Edges'
    assert facts['triangles'] == 7860 and facts['polygons'] == 3574
    assert facts['collision_hulls'] == len(meta['collisions']) == 89
    assert facts['slots'] == ['VillagePalette'] and facts['used_material_indices'] == [0]
    assert facts['matrix'] == np.eye(4).tolist()
    assert facts['uv_channels'] == ['UVMap']
    assert facts['colour_channels'] == [['Color', 'POINT', 'FLOAT_COLOR']]
    assert len(piece['normals']) == sum(map(len, piece['faces']))
    assert all(len(hull['vertices']) >= 4 for hull in meta['collisions'])

    output = tmp_path / 'current-whole-group'
    output.mkdir()
    manifest = ops.emit_whole_payload(output, raw, parent='Village_Edges')
    assert ops.verify_plan(output, parent='Village_Edges', limits=LIMITS) == manifest
    assert (output / 'Village_Edges.npz').read_bytes() == raw
    assert manifest['collision_owner'] == 'Village_Edges'
    script = Path(__file__).resolve().parents[1] / 'build_v2_blender_plan.py'
    entry = runpy.run_path(str(script))['run']
    context = SimpleNamespace(inputs={'source': root / 'Village_Edges.npz'},
                              input=lambda _slot: root / 'Village_Edges.npz',
                              params=dict(output_root='output/geometry', parent='Village_Edges', plan_limits=LIMITS))
    monkeypatch.chdir(tmp_path)
    entry(context)
    assert ops.verify_plan(tmp_path / 'output/geometry', parent='Village_Edges', limits=LIMITS) == manifest

    with pytest.raises(ValueError):
        ops.emit_whole_payload(output, raw, parent='Village_Edges')


def test_plan_refuses_hardlinked_owned_names(tmp_path):
    root, _manifest = planned(tmp_path)
    outside = tmp_path / 'unowned-alias.npz'
    os.link(root / 'Whole_A.npz', outside)
    with pytest.raises(ValueError, match='link'):
        ops.verify_plan(root, parent='Whole', limits=LIMITS)
    assert outside.read_bytes() == (root / 'Whole_A.npz').read_bytes()


@pytest.mark.parametrize('fault', ['unknown_envelope', 'unknown_member', 'role', 'duplicate_envelope', 'duplicate_member', 'mistyped_member', 'mistyped_frame'])
def test_producer_closes_metadata_schema_and_refuses_duplicate_keys(tmp_path, fault):
    root, manifest = planned(tmp_path)
    if fault == 'unknown_envelope':
        manifest['new_policy'] = True
    elif fault in ('unknown_member', 'role'):
        manifest['pieces'][0]['role' if fault == 'role' else 'new_policy'] = 'collision'
    elif fault == 'mistyped_member':
        manifest['pieces'][0]['triangles'] = True
    elif fault == 'mistyped_frame':
        manifest['matrix'][0][0] = True
    raw = json.dumps(manifest, separators=(',', ':'))
    if fault == 'duplicate_envelope':
        raw = raw.replace('"schema":1', '"schema":1,"schema":1', 1)
    elif fault == 'duplicate_member':
        raw = raw.replace('"name":"Whole_A"', '"name":"Whole_A","name":"Whole_A"', 1)
    (root / 'plan.json').write_text(raw)
    with pytest.raises(ValueError):
        ops.verify_plan(root, parent='Whole', limits=LIMITS)


@pytest.mark.parametrize('literal', ['NaN', 'Infinity', '-Infinity', '1e999', '{}', '[]', 'true', '"bad"'])
def test_payload_options_refuse_before_producer_completion_or_consumer_export(tmp_path, monkeypatch, literal):
    root, manifest = planned(tmp_path)
    with np.load(io.BytesIO((root / 'Whole_A.npz').read_bytes()), allow_pickle=False) as saved:
        arrays = {key: saved[key] for key in saved.files}
    meta = json.loads(arrays['metadata'].tobytes())
    meta['options'] = dict(global_scale=0)
    raw_meta = json.dumps(meta).replace('"global_scale": 0', '"global_scale": ' + literal)
    arrays['metadata'] = np.frombuffer(raw_meta.encode(), dtype=np.uint8)
    stream = io.BytesIO()
    np.savez_compressed(stream, **arrays)
    raw = stream.getvalue()
    (root / 'Whole_A.npz').write_bytes(raw)
    manifest['pieces'][0]['sha256'] = hashlib.sha256(raw).hexdigest()
    (root / 'plan.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='option'):
        ops.verify_plan(root, parent='Whole', limits=LIMITS)
    (root / 'Whole_B.npz').unlink()
    (root / 'plan.json').unlink()
    calls = []
    monkeypatch.setattr(ops, '_export_mesh', lambda *_args, **_kwargs: calls.append('export'))
    context = SimpleNamespace(params=dict(format='fbx', payload_encoding='mesh_ir', payload_role='geometry',
                                          payload_member='Whole_A.npz'), inputs={'payload': root},
                              outputs=['Whole_A.fbx', 'export.json'], output=lambda name: tmp_path / name)
    with pytest.raises(ValueError, match='option'):
        ops.run_export_piece(context)
    assert calls == [] and not (tmp_path / 'export.json').exists()


def test_declared_piece_options_refuse_before_exporter_and_have_finite_typed_bounds(tmp_path, monkeypatch):
    root, _manifest = planned(tmp_path)
    (root / 'Whole_B.npz').unlink()
    (root / 'plan.json').unlink()
    calls = []
    monkeypatch.setattr(ops, '_export_mesh', lambda *_args, **_kwargs: calls.append('export'))
    context = SimpleNamespace(params=dict(format='fbx', payload_encoding='mesh_ir', payload_role='geometry',
                                          payload_member='Whole_A.npz'), inputs={'payload': root},
                              outputs=['Whole_A.fbx', 'export.json'], output=lambda name: tmp_path / name)
    for options in [dict(global_scale=float('nan')), dict(global_scale=float('inf')), dict(global_scale=1e300),
                    dict(global_scale=10**1000), dict(apply_unit_scale=1), dict(global_scale=True),
                    dict(new_export_policy={}), dict(scene_world_color=[0, 0, float('inf')])]:
        context.params['options'] = options
        with pytest.raises(ValueError, match='option'):
            ops.run_export_piece(context)
    assert calls == []
    assert ops.export_options(dict(global_scale=1), dict(global_scale=0.001))['global_scale'] == 0.001


def test_frozen_job_world_color_reaches_the_real_shared_validator_as_a_list():
    from atelier.build_v2.python_job import JobContext
    from atelier.blender.fbx import validate_world_color

    context = JobContext({}, (), {'options': {'scene_world_color': [0, 0.25, 1]}}, 0)
    frozen = context.params['options']['scene_world_color']
    assert isinstance(frozen, tuple)
    with pytest.raises(ValueError):
        validate_world_color(frozen)
    actual = ops.export_options({}, context.params['options'])
    assert actual['scene_world_color'] == [0, 0.25, 1]
    assert type(actual['scene_world_color']) is list
    assert validate_world_color(actual['scene_world_color']) == [0, 0.25, 1]
    assert context.params['options']['scene_world_color'] == frozen


@pytest.mark.parametrize('mode', ['RELATIVE', 'STRIP'])
def test_declared_fbx_media_policy_survives_payload_decode_and_export_options(mode):
    meta, piece = mesh_ir.decode(payload())
    options = {'path_mode': mode, 'apply_scale_options': 'FBX_SCALE_ALL',
               'apply_unit_scale': True, 'axis_forward': '-Y', 'axis_up': 'Z',
               'colors_type': 'SRGB', 'mesh_smooth_type': 'FACE',
               'scene_world_color': [.05, .05, .05], 'use_custom_props': False}
    raw = mesh_ir.encode(piece, key=meta['asset'], slots=meta['slots'], matrix=meta['matrix'],
                         options=options, collisions=meta['collisions'])
    decoded, _, facts = decode_mesh_payload(raw, output_format='fbx')
    assert decoded['options'] == facts['options'] == options
    assert ops.export_options(decoded['options'], {}, output_format='fbx') == options


@pytest.mark.parametrize('mode', ['COPY', 'ABSOLUTE', 'AUTO', 'strip'])
def test_unknown_or_resource_copying_fbx_media_policies_refuse(mode):
    with pytest.raises(ValueError, match='path_mode'):
        ops.export_options({'path_mode': mode}, {}, output_format='fbx')


@pytest.mark.parametrize('declared', ['fbx', 'glb'])
def test_recipe_geometry_checks_declared_format_against_actual_payload_before_completion(tmp_path, monkeypatch, declared):
    from atelier.build_v2 import recipe_job
    root, manifest = planned(tmp_path)
    for row in manifest['pieces']:
        path = root / row['payload']
        meta, piece = mesh_ir.decode(path.read_bytes())
        raw = mesh_ir.encode(piece, key=meta['asset'], slots=meta['slots'], matrix=meta['matrix'],
                             options={'export_apply': True, 'export_image_format': 'NONE'})
        path.write_bytes(raw)
        row['sha256'] = hashlib.sha256(raw).hexdigest()
    (root / 'plan.json').write_text(json.dumps(manifest))
    output = tmp_path / 'output'
    output.mkdir()
    monkeypatch.chdir(tmp_path)
    context = SimpleNamespace(output_dir=output, params={'plan_limits': LIMITS,
        'recipe': {'paths': {}, 'outputs': [], 'commands': [], 'verify': None,
                   'geometry': {'source': 'plan', 'encoding': 'mesh_ir', 'format': declared, 'parent': 'Whole'}}})
    if declared == 'glb':
        recipe_job.run(context)
        assert (output / 'geometry/plan.json').read_bytes() == (root / 'plan.json').read_bytes()
    else:
        with pytest.raises(ValueError, match='export_apply'):
            recipe_job.run(context)
        assert not (output / 'geometry').exists()


@pytest.mark.parametrize('geometry', [{'encoding': 'mesh_ir'}, {'encoding': 'mesh_ir', 'format': 'GLB'},
                                      {'encoding': 'encoded_glb', 'format': 'fbx'}])
def test_recipe_geometry_refuses_missing_or_incompatible_format_before_body(geometry):
    from atelier.build_v2 import recipe_job
    with pytest.raises(ValueError, match='exact export format'):
        recipe_job.run(SimpleNamespace(params={'recipe': {'geometry': geometry}}))
