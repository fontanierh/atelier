"""Cook view mappings come from exact staged Native Items, including expanded followers."""
from copy import deepcopy
from pathlib import Path
import os

import pytest
from atelier.build_v2.recipe_native_paths import bind


def staged(tmp_path):
    root = tmp_path / 'inputs/mesh/content/Game/Scene'
    root.mkdir(parents=True)
    (root / 'Mesh.uasset').write_bytes(b'native package')
    (root / 'Mesh.ubulk').write_bytes(b'payload')
    return {'op': {'kind': 'unreal.cook.produce', 'version': '1'},
            'inputs': [{'name': 'mesh', 'path': 'inputs/mesh'}],
            'params': {'project': 'games/test/unreal/Test.uproject', 'recipe': {
                'paths': {}, 'native_inputs': {'slots': ['mesh'], 'derived': []}}}}


def test_resolved_item_paths_preserve_bytes_and_the_original_declaration(tmp_path):
    job = staged(tmp_path)
    before = deepcopy(job)
    result = bind(job, tmp_path)
    assert result['params']['recipe']['paths'] == {
        'games/test/unreal/Content/Scene/Mesh.uasset': 'inputs/mesh/content/Game/Scene/Mesh.uasset',
        'games/test/unreal/Content/Scene/Mesh.ubulk': 'inputs/mesh/content/Game/Scene/Mesh.ubulk'}
    assert job == before
    assert (tmp_path / 'inputs/mesh/content/Game/Scene/Mesh.uasset').read_bytes() == b'native package'


def test_dynamic_members_use_only_their_actual_staged_slots(tmp_path):
    job = staged(tmp_path)
    job['params']['recipe']['native_inputs'] = {'slots': [], 'derived': [
        {'derived_items': {'root': 'derived/meshes', 'members': [{'piece': 'Mesh', 'slot': 'mesh'}]}}]}
    assert len(bind(job, tmp_path)['params']['recipe']['paths']) == 2


@pytest.mark.parametrize('damage', ['unknown', 'unresolved', 'outside', 'link', 'hardlink', 'foreign', 'collision', 'empty'])
def test_invalid_membership_refuses_before_it_can_create_a_cook_view(tmp_path, damage):
    job = staged(tmp_path)
    recipe = job['params']['recipe']
    member = tmp_path / 'inputs/mesh/content/Game/Scene/Mesh.uasset'
    if damage == 'unknown':
        recipe['native_inputs']['slots'] = ['missing']
    elif damage == 'unresolved':
        recipe['native_inputs']['derived'] = [{'derived_items': {'root': 'r', 'templates': []}}]
    elif damage == 'outside':
        job['inputs'][0]['path'] = '../foreign'
    elif damage == 'link':
        member.unlink(); member.symlink_to(tmp_path / 'foreign')
    elif damage == 'hardlink':
        os.link(member, tmp_path / 'alias')
    elif damage == 'foreign':
        (member.parent / 'shader.py').write_text('not a package')
    elif damage == 'collision':
        recipe['paths']['games/test/unreal/Content/Scene/Mesh.uasset'] = 'inputs/other'
    elif damage == 'empty':
        for path in member.parent.iterdir(): path.unlink()
    with pytest.raises(ValueError):
        bind(job, tmp_path)
    assert not (tmp_path / '.recipe-runtime').exists()


def test_ordinary_recipe_without_native_bindings_is_unchanged(tmp_path):
    job = staged(tmp_path)
    del job['params']['recipe']['native_inputs']
    assert bind(job, tmp_path) == job
