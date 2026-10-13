"""The operator's independent pose-lab snapshot is the idle author's reference."""
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from atelier.character.names import mixamo_aliases, slug
from atelier.gltf import glb_parts

CHARS = Path(__file__).resolve().parents[1] / 'assets/characters'
SOURCE = CHARS / 'nox'
spec = importlib.util.spec_from_file_location('idle_stance', CHARS / 'adventure/stance.py')
stance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stance)


def trs(node):
    if 'matrix' in node:
        return np.array(node['matrix']).reshape(4, 4).T
    x, y, z, w = node.get('rotation', [0, 0, 0, 1])
    rotation = np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                         [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                         [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])
    result = np.eye(4)
    result[:3, :3] = rotation @ np.diag(node.get('scale', [1, 1, 1]))
    result[:3, 3] = node.get('translation', [0, 0, 0])
    return result


def rig():
    doc, _ = glb_parts((SOURCE / 'Nox.glb').read_bytes())
    reference = json.loads((SOURCE / 'provenance/idle-pose-reference.json').read_text())
    choice = json.loads((SOURCE / 'provenance/idle-pose-choice.json').read_text())
    basis = np.array(choice['reference']['glb_to_prepared_column_major']).reshape(4, 4).T
    parent_node = {child: i for i, node in enumerate(doc['nodes']) for child in node.get('children', [])}
    aliases = mixamo_aliases()
    joints = doc['skins'][0]['joints']
    names = {i: aliases.get(doc['nodes'][i]['name'], slug(doc['nodes'][i]['name'])) for i in joints}
    parent = {name: names.get(parent_node.get(i), 'root') for i, name in names.items()}
    parent['root'] = None
    def worlds(overrides):
        result = {}
        def world(i):
            if i not in result:
                node = doc['nodes'][i]
                value = overrides.get(str(i))
                local = value if value is not None else trs(node)
                result[i] = (world(parent_node[i]) if i in parent_node else np.eye(4)) @ local
            return result[i]
        return {name: basis @ world(i) for i, name in names.items()}
    rest = worlds({})
    idle = worlds({i: np.array(v).reshape(4, 4).T for i, v in reference['local_matrices'].items()})
    final = worlds({i: trs({'translation': b['position'], 'rotation': b['rotation_xyzw'], 'scale': b['scale']})
                    for i, b in choice['resolved_pose']['bone_local'].items()})
    for value in (rest, idle, final):
        value['root'] = np.eye(4)
    def rotation(m):
        u, _, vt = np.linalg.svd(m[:3, :3])
        return u @ vt
    depth = lambda name: 0 if not parent[name] else 1 + depth(parent[name])
    order = sorted(parent, key=depth)
    rr = {name: rotation(value) for name, value in rest.items()}
    rp = {name: value[:3, 3].copy() for name, value in rest.items()}
    rotations = {name: np.repeat(rotation(value)[None], 2, axis=0) for name, value in idle.items()}
    positions = {name: np.repeat(value[None, :3, 3], 2, axis=0) for name, value in idle.items()}
    return order, parent, rr, rp, rotations, positions, final, choice


def profile():
    return stance.load(SOURCE / 'provenance/idle-pose-choice.json', hashlib.sha256((SOURCE / 'Nox.glb').read_bytes()).hexdigest())


def test_selected_idle_matches_independent_downloaded_pose():
    order, parent, rr, rp, rotations, positions, final, choice = rig()
    original = {name: value.copy() for name, value in positions.items()}
    receipt = stance.apply(order, parent, rr, rp, rotations, positions, profile())
    errors = []
    for name in order:
        errors.append(np.linalg.norm(positions[name][1] - final[name][:3, 3]))
        expected = final[name][:3, :3]
        u, _, vt = np.linalg.svd(expected)
        delta = rotations[name][1] @ (u @ vt).T
        angle = np.arccos(np.clip((np.trace(delta)-1)/2, -1, 1))
        assert np.rad2deg(angle) < .01, (name, np.rad2deg(angle))
    assert max(errors) < 5e-5, max(errors)
    assert receipt['pelvis_lowering_cm'] == 0
    for side in 'LR':
        hip, knee, ankle = (positions[f'{key}_{side}'][1] for key in ('thigh', 'shin', 'foot'))
        for a, b in (('thigh', 'shin'), ('shin', 'foot')):
            np.testing.assert_allclose(np.linalg.norm(positions[f'{a}_{side}'][1] - positions[f'{b}_{side}'][1]),
                                       np.linalg.norm(rp[f'{a}_{side}'] - rp[f'{b}_{side}']), atol=1e-8)
        # The chosen stance bends the knee forward; it never hyperextends behind.
        assert knee[0] - (hip[0] + ankle[0])/2 > .05
        np.testing.assert_allclose(positions[f'toe_{side}'][1, 2], original[f'toe_{side}'][1, 2], atol=5e-6)
    assert choice['settings']['hips'] == -9 and choice['settings']['L']['swing'] == -20


def test_zero_stance_is_bitwise_identity():
    order, parent, rr, rp, rotations, positions, _, _ = rig()
    expected_rot = {name: value.copy() for name, value in rotations.items()}
    expected_pos = {name: value.copy() for name, value in positions.items()}
    zero = {key: (dict(L=0., R=0.) if key == 'arm_swing_deg' else 0.) for key in profile()}
    zero['reference_frame'] = 1
    stance.apply(order, parent, rr, rp, rotations, positions, zero)
    for name in order:
        np.testing.assert_array_equal(rotations[name], expected_rot[name])
        np.testing.assert_array_equal(positions[name], expected_pos[name])


def test_choice_is_bound_to_model_and_units():
    with pytest.raises(ValueError, match='different model'):
        stance.load(SOURCE / 'provenance/idle-pose-choice.json', '0'*64)
    choice = json.loads((SOURCE / 'provenance/idle-pose-choice.json').read_text())
    factor = choice['reference']['display_to_game_distance_scale']
    np.testing.assert_allclose(profile()['pelvis_forward_m'], -9 * factor / 100, atol=1e-12)
    np.testing.assert_allclose(profile()['foot_spacing_m'], -8 * factor / 100, atol=1e-12)


def test_only_nox_opts_in_and_only_idle_has_the_stance():
    import tomllib
    for path in CHARS.glob('*/adventure.toml'):
        table = tomllib.loads(path.read_text()).get('stance', {})
        assert set(table) == ({'Nml_Wait'} if path.parent.name == 'nox' else set())
