"""Dependency lowering must preserve producer authority before any runtime exists."""
from copy import deepcopy

import pytest

from atelier.build_v2.recipe_compiler import Unsupported, compile_rows


def row(name, *, inputs=(), products=(), reads=(), outputs=()):
    return {'id': name, 'commands': [{'kind': 'python', 'script': {'path': 'ops/main.py'},
                                    'args': [], 'env': []}],
            'code': ['ops/main.py'], 'inputs': list(inputs), 'reads': list(reads),
            'needs': [], 'after': [], 'products': list(products), 'outputs': list(outputs),
            'verify': None, 'replan': False}


def test_generated_file_is_a_product_edge_without_reading_existing_output(tmp_path):
    producer = row('producer', products=[{'id': 'terrain', 'paths': ['build/game/terrain'],
                                        'optional_paths': []}])
    consumer = row('consumer', inputs=[{'path': 'build/game/terrain/final.npz', 'optional': False}],
                   outputs=['build/game/height.json'])
    marker = compile_rows([producer, consumer], project='game', targets=['consumer'])
    request = marker.request(tmp_path)
    unit = request['declaration']['units'][1]
    assert unit['inputs'] == [{'role': 'content', 'name': 'item0',
                              'source': {'kind': 'item', 'unit': 'producer', 'item': 'product0'},
                              'whole': 'The recipe consumes declared ROOT archives from this complete producer Item.'}]
    assert unit['params']['recipe']['paths'] == {
        'build/game/terrain': 'inputs/item0/products/0-0.tree.tar'}
    assert not list(tmp_path.iterdir())


def test_named_product_bytes_are_explicit_content_even_without_needs(tmp_path):
    producer = row('producer', products=[{'id': 'terrain', 'paths': ['build/game/terrain'],
                                        'optional_paths': []}])
    consumer = row('consumer', reads=[{'producer': 'producer', 'product': 'terrain',
                                     'paths': ['build/game/terrain']}], outputs=['build/game/result.json'])
    result = compile_rows([producer, consumer], project='game', targets=['consumer']).request(tmp_path)
    assert result['declaration']['units'][1]['inputs'][0]['source']['kind'] == 'item'
    altered = deepcopy(consumer)
    altered['reads'][0]['producer'] = 'foreign'
    with pytest.raises(Unsupported, match='owning declaration'):
        compile_rows([producer, altered], project='game', targets=['consumer'])


def test_optional_source_remains_explicit_absence_and_never_disappears_from_key(tmp_path):
    unit = row('source', inputs=[{'path': 'assets/settings.json', 'optional': True}],
               outputs=['build/game/data.json'])
    request = compile_rows([unit], project='game', targets=['source']).request(tmp_path)
    assert request['declaration']['units'][0]['inputs'][0]['source'] == {
        'kind': 'file', 'path': 'assets/settings.json', 'optional': True}


def test_unimplemented_native_command_cannot_be_relabelled_python():
    unit = row('native', outputs=['build/game/native.json'])
    unit['commands'] = [{'kind': 'UnrealScript', 'script': {'path': 'ops/main.py'}}]
    with pytest.raises(Unsupported, match='native typed execution adapter'):
        compile_rows([unit], project='game', targets=['native'])


def test_duplicate_or_escaping_ownership_refuses():
    unit = row('source', outputs=['../foreign'])
    with pytest.raises(Unsupported, match='noncanonical'):
        compile_rows([unit], project='game', targets=['source'])
    unit = row('source', outputs=['build/game/data.json'])
    with pytest.raises(Unsupported, match='duplicate recipe unit'):
        compile_rows([unit, unit], project='game', targets=['source'])
