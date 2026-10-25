import pytest

from atelier.build_v2 import recipe_inputs as ri


def _row(name, **fields):
    row = {'id': name, 'commands': [], 'code': [], 'inputs': [], 'deferred': [], 'reads': [], 'references': [],
           'needs': [], 'after': [], 'products': [], 'outputs': [], 'verify': None, 'replan': False}
    row.update(fields)
    return row


def _graph():
    producer = _row('a.make', products=[{'id': 'a.data', 'paths': ['build/g/a'], 'optional_paths': []}],
                    outputs=['build/g/log.txt'])
    rows = {'a.make': producer}
    roots = [('build/g/a', 'a.make', 'product0'), ('build/g/log.txt', 'a.make', 'output0')]
    products = {'a.data': ('a.make', 'product0', ['build/g/a'])}
    return rows, roots, products


def _lower(row, tmp_path):
    rows, roots, products = _graph()
    rows[row['id']] = row
    return ri.lower_inputs(row, rows=rows, roots=roots, products=products, checkout=tmp_path)


def test_source_directory_lists_every_member_and_generated_paths_bind_items(tmp_path):
    (tmp_path / 'assets' / 'sub').mkdir(parents=True)
    (tmp_path / 'assets' / 'one.json').write_text('1')
    (tmp_path / 'assets' / 'sub' / 'two.bin').write_bytes(b'2')
    row = _row('b.use', code=['tools/b.py', '<blender>/5.2/addon.py'],
               inputs=[{'path': 'assets', 'root': 'checkout', 'optional': False},
                       {'path': 'build/g/a/x.json', 'root': 'checkout', 'optional': False},
                       {'path': '5.2/scripts/x.py', 'root': 'blender', 'optional': False}])
    result = _lower(row, tmp_path)
    files = [i['source']['path'] for i in result['inputs'] if i['source']['kind'] == 'file']
    assert files == ['assets/one.json', 'assets/sub/two.bin']
    items = [i['source'] for i in result['inputs'] if i['source']['kind'] == 'item']
    assert items == [{'kind': 'item', 'unit': 'a.make', 'item': 'product0'}]
    assert result['paths']['build/g/a'] == 'inputs/item0/products/0-0.tree.tar'
    assert result['code'] == ['tools/b.py']
    assert result['tools'] == ['<blender>/5.2/addon.py', '<blender>/5.2/scripts/x.py']
    assert set(result['slots']) == {i['name'] for i in result['inputs']}


def test_references_are_conservative_content_edges(tmp_path):
    ref = {'producer': 'a.make', 'product': 'a.data', 'paths': ['build/g/a']}
    result = _lower(_row('b.use', references=[ref]), tmp_path)
    assert [i['source'] for i in result['inputs']] == [{'kind': 'item', 'unit': 'a.make', 'item': 'product0'}]


def test_deferred_binds_all_owning_roots_and_keys_support(tmp_path):
    provider = {'name': 'pieces', 'collect': {'source': 'tools/collect.py', 'qualname': 'collect', 'line': 1},
                'settings': [{'path': 'build/g'}], 'support': ['tools/collect.py', 'tools/helper.py'],
                'owners': [{'root': 'build/g/a', 'producer': 'a.make'}, {'root': 'build/g/log.txt', 'producer': 'a.make'}]}
    result = _lower(_row('b.use', deferred=[provider], needs=['a.make']), tmp_path)
    assert {(i['source']['unit'], i['source']['item']) for i in result['inputs']} == {
        ('a.make', 'product0'), ('a.make', 'output0')}
    assert {'tools/collect.py', 'tools/helper.py'} <= set(result['code'])
    assert result['deferred'][0]['bound_generated_roots'] == ['build/g/a', 'build/g/log.txt']
    assert result['deferred'][0]['observed_source_roots'] == []
    # Without an ancestor edge nothing generated is bound (no cycle through a downstream producer).
    unrelated = _lower(_row('c.use', deferred=[provider]), tmp_path)
    assert unrelated['inputs'] == [] and unrelated['deferred'][0]['bound_generated_roots'] == []


def test_unknown_external_data_and_missing_source_refuse_by_name(tmp_path):
    row = _row('audio.combat', inputs=[{'path': 'sonniss/combat', 'root': 'atelier-cache', 'optional': False}])
    with pytest.raises(ri.Unsupported, match='audio.combat: external atelier-cache data sonniss/combat'):
        _lower(row, tmp_path)
    with pytest.raises(ri.Unsupported, match='b.use: missing source input nope.json'):
        _lower(_row('b.use', inputs=[{'path': 'nope.json', 'root': 'checkout', 'optional': False}]), tmp_path)


def test_absent_optional_source_keeps_identity_and_links_refuse(tmp_path):
    result = _lower(_row('b.use', inputs=[{'path': 'maybe.json', 'root': 'checkout', 'optional': True}]), tmp_path)
    assert result['inputs'][0]['source'] == {'kind': 'file', 'path': 'maybe.json', 'optional': True}
    (tmp_path / 'real').mkdir()
    (tmp_path / 'link').symlink_to(tmp_path / 'real')
    with pytest.raises(ri.Unsupported, match='linked source input link'):
        _lower(_row('b.use', inputs=[{'path': 'link', 'root': 'checkout', 'optional': False}]), tmp_path)


def test_needs_bind_every_prerequisite_root(tmp_path):
    result = _lower(_row('b.use', needs=['a.make']), tmp_path)
    assert {i['source']['item'] for i in result['inputs']} == {'product0', 'output0'}


@pytest.mark.parametrize('field,value', [
    ('needs', ['a.make']),
    ('reads', [{'producer': 'a.make', 'product': 'a.data', 'paths': ['build/g/a']}]),
    ('references', [{'producer': 'a.make', 'product': 'a.data', 'paths': ['build/g/a']}]),
    ('inputs', [{'path': 'build/g/a/x.json', 'root': 'checkout', 'optional': False}]),
])
def test_broad_recipe_item_edges_explain_complete_producer_scope(tmp_path, field, value):
    result = _lower(_row('b.use', **{field: value}), tmp_path)
    assert result['inputs']
    assert all(input['source']['kind'] == 'item' and input['role'] == 'content'
               and 'complete producer Item' in input['whole']
               for input in result['inputs'])


def test_deferred_folder_holding_own_output_is_not_a_self_edge(tmp_path):
    provider = {'name': 'proof', 'collect': None, 'settings': [{'path': 'build/g'}, {'path': '.'}], 'support': [],
                'owners': [{'root': 'build/g/self.json', 'producer': 'b.use'}]}
    rows, roots, products = _graph()
    row = _row('b.use', deferred=[provider], outputs=['build/g/self.json'])
    rows['b.use'] = row
    roots = [*roots, ('build/g/self.json', 'b.use', 'output0')]
    result = ri.lower_inputs(row, rows=rows, roots=roots, products=products, checkout=tmp_path)
    assert result['inputs'] == []
    assert result['deferred'][0]['observed_source_roots'] == ['.']
