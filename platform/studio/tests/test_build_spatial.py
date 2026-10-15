"""Spatial reads follow complete declared membership, independently of unrelated products."""
from dataclasses import replace
from types import SimpleNamespace

import pytest

from atelier import build, build_cache, build_products, build_spatial
from atelier.build import BBoxQuery, Product, Python, Step
from atelier.build_products import Graph


NEAR = (0, 0, 0, 10, 10, 10)
FAR = (100, 100, 100, 110, 110, 110)


@pytest.fixture
def recipe(tmp_path, monkeypatch):
    script = tmp_path / 'generate.py'
    script.write_text('pass\n')
    # Installed tools are independent of the selector behavior exercised here.
    monkeypatch.setattr(build_cache, 'tool_context', lambda *args, **kwargs: {'schema': 1, 'tool': 'fixture'})

    def product(name, bounds=NEAR, collection='terrain', paths=None):
        return Product(name, tuple(paths or (tmp_path / 'outputs' / name,)),
                       collection=collection, bounds=bounds)

    def producer(name, *products, **kwargs):
        return Step(name, [Python(script)], products=list(products), **kwargs)

    def consumer(queries=None, **kwargs):
        return Step('consume', [Python(script)], audit=True,
                    products=[Product('result', (tmp_path / 'result',))],
                    queries=[BBoxQuery('near', 'terrain', NEAR)] if queries is None else queries, **kwargs)

    def fingerprint(steps, done=None):
        effective = Graph(steps).by_name['consume']
        return build.fingerprint_state(effective, {} if done is None else done)

    return SimpleNamespace(product=product, producer=producer, consumer=consumer,
                           fingerprint=fingerprint, root=tmp_path)


def test_query_selects_all_intersecting_owners_but_not_other_collections(recipe):
    r = recipe
    producers = [r.producer('tiles', r.product('z'), r.product('a'), r.product('far', FAR)),
                 r.producer('objects', r.product('object', collection='objects')),
                 r.producer('other_tile', r.product('m'))]
    consumer = r.consumer(reads=['a'])
    graph = Graph([consumer, *reversed(producers)])
    effective = graph.by_name['consume']
    assert effective.reads == ['a', 'm', 'z']
    assert [step.name for step in graph.select(['consume'])] == ['tiles', 'other_tile', 'consume']
    assert consumer.reads == ['a']
    assert build_spatial.manifest(effective)['queries']['near']['matches'] == [
        {'name': name, 'owner': owner, 'bounds': tuple(map(float, NEAR)),
         'paths': [str(r.root / 'outputs' / name)]}
        for name, owner in [('a', 'tiles'), ('m', 'other_tile'), ('z', 'tiles')]]


@pytest.mark.parametrize('bounds', [
    (10, 2, 2, 11, 3, 3), (2, 10, 2, 3, 11, 3), (2, 2, 10, 3, 3, 11),
    (-1, 2, 2, 0, 3, 3), (2, -1, 2, 3, 0, 3), (2, 2, -1, 3, 3, 0),
    (10, 10, 10, 10, 10, 10),
])
def test_touching_faces_and_flat_corner_are_inclusive(recipe, bounds):
    r = recipe
    graph = Graph([r.producer('tile', r.product('touch', bounds)), r.consumer()])
    assert graph.by_name['consume'].reads == ['touch']


def test_a_separated_axis_excludes_an_otherwise_overlapping_product(recipe):
    r = recipe
    graph = Graph([r.producer('tile', r.product('outside', (10.001, 0, 0, 11, 10, 10))), r.consumer()])
    assert graph.by_name['consume'].reads == []


def test_empty_query_is_recorded_and_new_membership_invalidates(recipe):
    r = recipe
    consumer = r.consumer()
    empty_key, state = r.fingerprint([consumer])
    assert state['queries']['near']['matches'] == []
    assert state['queries']['near']['collection'] == 'terrain'
    far = r.producer('tile', r.product('tile', FAR))
    assert r.fingerprint([far, consumer])[0] == empty_key
    touching = r.producer('tile', r.product('tile', (10, 0, 0, 11, 1, 1)))
    assert r.fingerprint([touching, consumer])[0] != empty_key
    assert r.fingerprint([replace(consumer, queries=[BBoxQuery('near', 'terrain', FAR)])])[0] != empty_key


def test_graphs_do_not_accumulate_reads_or_change_an_existing_snapshot(recipe):
    r = recipe
    tile = r.producer('tiles', r.product('near'), r.product('far', FAR))
    consumer = r.consumer()
    first = Graph([tile, consumer]).by_name['consume']
    snapshot = build_spatial.manifest(first)
    assert Graph([tile, consumer]).by_name['consume'].reads == ['near']
    assert consumer.reads == []
    with pytest.raises(ValueError, match='resolved'):
        build_spatial.manifest(consumer)
    tile.products = [r.product('far')]
    assert Graph([tile, consumer]).by_name['consume'].reads == ['far']
    assert first.reads == ['near']
    assert build_spatial.manifest(first) == snapshot
    snapshot['queries']['near']['matches'].clear()
    assert len(build_spatial.manifest(first)['queries']['near']['matches']) == 1


def test_query_and_catalogue_order_do_not_change_frozen_results_or_keys(recipe):
    r = recipe
    products = [r.product('z'), r.product('a')]
    queries = [BBoxQuery('second', 'terrain', NEAR), BBoxQuery('first', 'terrain', NEAR)]
    first = Graph([r.producer('tiles', *products), r.consumer(queries)])
    second = Graph([r.consumer(list(reversed(queries))), r.producer('tiles', *reversed(products))])
    a, b = first.by_name['consume'], second.by_name['consume']
    assert a.reads == b.reads == ['a', 'z']
    assert build_spatial.manifest(a) == build_spatial.manifest(b)
    assert build.fingerprint_state(a, {})[0] == build.fingerprint_state(b, {})[0]


@pytest.mark.parametrize('changed', ['query_name', 'criteria', 'collection', 'name', 'bounds', 'owner', 'paths'])
def test_selected_metadata_changes_key_even_when_consumed_bytes_are_identical(recipe, changed):
    r = recipe
    product = r.product('tile')
    query = BBoxQuery('near', 'terrain', NEAR)
    owner = 'tiles'
    before = r.fingerprint([r.producer(owner, product), r.consumer([query])], {'product:tile': 'same-bytes'})[0]
    if changed == 'query_name':
        query = BBoxQuery('renamed', 'terrain', NEAR)
    elif changed == 'criteria':
        query = BBoxQuery('near', 'terrain', (-1, -1, -1, 10, 10, 10))
    elif changed == 'collection':
        query = BBoxQuery('near', 'renamed_collection', NEAR)
        product = replace(product, collection='renamed_collection')
    elif changed == 'name':
        product = replace(product, name='renamed')
    elif changed == 'bounds':
        product = replace(product, bounds=(1, 1, 1, 9, 9, 9))
    elif changed == 'owner':
        owner = 'renamed_owner'
    else:
        product = replace(product, paths=(r.root / 'moved',))
    after = r.fingerprint([r.producer(owner, product), r.consumer([query])],
                          {f'product:{product.name}': 'same-bytes'})[0]
    assert after != before


def test_unread_sibling_and_far_changes_do_not_invalidate_but_selected_bytes_do(recipe):
    r = recipe
    near, sibling, far = r.product('near'), r.product('sibling', collection='other'), r.product('far', FAR)
    for product in (near, sibling, far):
        product.paths[0].parent.mkdir(parents=True, exist_ok=True)
        product.paths[0].write_text(product.name)

    def state(products):
        done = {f'product:{p.name}': build_products.identity(build_products.inventory(p)) for p in products}
        return r.fingerprint([r.producer('tiles', *products), r.consumer()], done)

    before, details = state([near, sibling, far])
    assert set(details['reads']) == {'near'}
    sibling.paths[0].write_text('changed unread bytes')
    far.paths[0].write_text('changed far bytes')
    far = replace(far, bounds=(200, 200, 200, 210, 210, 210))
    assert state([near, sibling, far])[0] == before
    near.paths[0].write_text('changed consumed bytes')
    assert state([near, sibling, far])[0] != before


@pytest.mark.parametrize('bounds', [
    (), (0, 0, 0, 1, 1), (0, 0, 0, 1, 1, float('nan')),
    (0, 0, 0, 1, float('inf'), 1), (False, 0, 0, 1, 1, 1),
    ('0', 0, 0, 1, 1, 1), (2, 0, 0, 1, 1, 1), (0, 2, 0, 1, 1, 1), (0, 0, 2, 1, 1, 1),
])
def test_invalid_bounds_are_refused_for_selectors_and_products(recipe, bounds):
    with pytest.raises(ValueError):
        BBoxQuery('near', 'terrain', bounds)
    with pytest.raises(ValueError):
        recipe.product('tile', bounds)


@pytest.mark.parametrize('name,collection', [('', 'terrain'), (None, 'terrain'), (4, 'terrain'), ('near', ''), ('near', None)])
def test_query_requires_nonempty_string_names(name, collection):
    with pytest.raises(ValueError):
        BBoxQuery(name, collection, NEAR)


def test_spatial_product_requires_both_collection_and_bounds(recipe):
    with pytest.raises(ValueError):
        recipe.product('tile', NEAR, collection=None)
    with pytest.raises(ValueError):
        recipe.product('tile', None)


def test_duplicate_queries_and_queries_without_audit_are_refused(recipe):
    r = recipe
    query = BBoxQuery('near', 'terrain', NEAR)
    with pytest.raises(ValueError, match='duplicate spatial query'):
        Graph([r.consumer([query, BBoxQuery('near', 'other', FAR)])])
    with pytest.raises(ValueError, match='audited Python'):
        Graph([replace(r.consumer(), audit=False)])
    with pytest.raises(ValueError, match='invalid spatial query'):
        Graph([r.consumer(['terrain'])])


def test_queries_cannot_bypass_the_single_python_named_output_audit_contract(recipe):
    consumer = recipe.consumer()
    for invalid in (replace(consumer, products=[]), replace(consumer, commands=consumer.commands * 2)):
        with pytest.raises(ValueError, match='audit requires'):
            Graph([invalid])


def test_spatial_edges_participate_in_cycle_detection(recipe):
    r = recipe
    a = r.producer('a', r.product('a', collection='a'), audit=True,
                   queries=[BBoxQuery('b', 'b', NEAR)])
    b = r.producer('b', r.product('b', collection='b'), audit=True,
                   queries=[BBoxQuery('a', 'a', NEAR)])
    with pytest.raises(ValueError, match='Build dependency cycle'):
        Graph([a, b])
    with pytest.raises(ValueError, match='Build dependency cycle'):
        Graph([r.producer('self', r.product('self'), audit=True,
                          queries=[BBoxQuery('self', 'terrain', NEAR)])])
