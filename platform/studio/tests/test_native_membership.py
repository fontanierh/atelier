"""Current package membership is complete before superseded native assets can retire."""
from types import SimpleNamespace

import pytest

from atelier import native_membership as M

ROOT = '/Game/Region/Meshes'
PREFIX = 'SM_Region_'
OLD = ROOT+'/'+PREFIX+'Old'
CURRENT = ROOT+'/'+PREFIX+'Piece0'


class NativeArray:
    def __init__(self, values): self.values = values
    def __iter__(self): return iter(self.values)


def editor(paths, references=None):
    paths, deleted = set(paths), []
    def remove(path):
        deleted.append(path)
        paths.remove(path)
        return True
    return SimpleNamespace(list_assets=lambda root, **k: NativeArray(sorted(paths)),
        does_asset_exist=lambda path: path in paths, delete_asset=remove,
        find_package_referencers_for_asset=lambda path, **k: NativeArray((references or {}).get(path, []))), paths, deleted


def test_native_array_inventory_and_superseded_parent_retire_keep_current_and_foreign():
    e, paths, deleted = editor([OLD, CURRENT, ROOT+'/HandAuthored'])
    previous = M.inventory(e, ROOT, PREFIX)
    assert previous == {OLD, CURRENT}
    assert M.retire(e, previous, [PREFIX+'Piece0'], ROOT, PREFIX) == [OLD]
    assert paths == {CURRENT, ROOT+'/HandAuthored'} and deleted == [OLD]


@pytest.mark.parametrize('bad', ['empty', 'missing', 'duplicate', 'escape', 'foreign', 'object', 'unicode'])
def test_incomplete_or_invalid_current_membership_cannot_delete(bad):
    e, paths, deleted = editor([OLD, CURRENT])
    names = {'empty': [], 'missing': [PREFIX+'Missing'], 'duplicate': [PREFIX+'Piece0']*2,
             'escape': [PREFIX+'../Old'], 'foreign': ['Foreign'], 'object': [PREFIX+'Piece0.Other'],
             'unicode': [PREFIX+'Pièce0']}[bad]
    with pytest.raises(ValueError): M.retire(e, {OLD}, names, ROOT, PREFIX)
    assert paths == {OLD, CURRENT} and deleted == []


@pytest.mark.parametrize('previous', [{'/Game/Other/SM_Region_Old'}, {ROOT+'/Foreign'}, {'../old'}])
def test_invalid_prior_ownership_refuses_before_deletion(previous):
    e, paths, deleted = editor([OLD, CURRENT])
    with pytest.raises(ValueError): M.retire(e, previous, [PREFIX+'Piece0'], ROOT, PREFIX)
    assert paths == {OLD, CURRENT} and deleted == []


def test_all_external_reference_checks_finish_before_first_delete():
    extra = ROOT+'/'+PREFIX+'ZOld'
    e, paths, deleted = editor([OLD, extra, CURRENT], {extra: ['/Game/Other/StillUsingOld']})
    with pytest.raises(ValueError, match='external references'):
        M.retire(e, {OLD, extra}, [PREFIX+'Piece0'], ROOT, PREFIX)
    assert paths == {OLD, extra, CURRENT} and deleted == []


def test_all_retiring_packages_exist_before_first_delete():
    e, paths, deleted = editor([OLD, CURRENT])
    with pytest.raises(ValueError, match='Prior native membership changed'):
        M.retire(e, {OLD, ROOT+'/'+PREFIX+'ZMissing'}, [PREFIX+'Piece0'], ROOT, PREFIX)
    assert paths == {OLD, CURRENT} and deleted == []


def test_retiring_primary_and_collision_references_are_allowed():
    hull = OLD+'_Collision'
    e, paths, deleted = editor([OLD, hull, CURRENT], {hull: [OLD]})
    assert M.retire(e, {OLD, hull}, [PREFIX+'Piece0'], ROOT, PREFIX) == [OLD, hull]
    assert paths == {CURRENT} and deleted == [OLD, hull]


@pytest.mark.parametrize('bad', [None, False, 'a package', {'package': True}, [None], [CURRENT]])
def test_invalid_or_current_package_references_cannot_be_deleted(bad):
    e, paths, deleted = editor([OLD, CURRENT])
    e.find_package_referencers_for_asset = lambda *a, **k: bad
    with pytest.raises(ValueError): M.retire(e, {OLD}, [PREFIX+'Piece0'], ROOT, PREFIX)
    assert paths == {OLD, CURRENT} and deleted == []


@pytest.mark.parametrize('bad', ['/Game/Other/SM_Region_Old', ROOT+'/SM_Region_Old.Wrong',
                                 ROOT+'/SM_Region_Sub/Child.Child', ROOT+'/SM_Region_É.É'])
def test_invalid_native_inventory_refuses(bad):
    e, _, deleted = editor([])
    e.list_assets = lambda *a, **k: [bad]
    with pytest.raises(ValueError): M.inventory(e, ROOT, PREFIX)
    assert deleted == []


def test_delete_failure_is_not_success():
    e, paths, deleted = editor([OLD, CURRENT])
    e.delete_asset = lambda path: False
    with pytest.raises(ValueError, match='Could not retire'):
        M.retire(e, {OLD}, [PREFIX+'Piece0'], ROOT, PREFIX)
    assert paths == {OLD, CURRENT} and deleted == []


def test_replacements_validate_all_sources_before_retiring_any_parent():
    other = ROOT+'/'+PREFIX+'Other'
    missing = ROOT+'/'+PREFIX+'Missing'
    e, paths, deleted = editor([OLD, other, CURRENT])
    with pytest.raises(ValueError, match='incomplete'):
        M.retire_replaced(e, {OLD: [CURRENT], other: [missing]})
    assert not deleted and OLD in paths and other in paths


def test_replacements_keep_current_pieces_and_preflight_all_external_refs():
    other = ROOT+'/'+PREFIX+'Other'
    e, paths, deleted = editor([OLD, other, CURRENT], {other: ['/Game/Foreign/Reader']})
    with pytest.raises(ValueError, match='external references'):
        M.retire_replaced(e, {OLD: [CURRENT], other: [CURRENT]})
    assert not deleted
    e, paths, deleted = editor([OLD, CURRENT])
    assert M.retire_replaced(e, {OLD: [CURRENT]}) == [OLD]
    assert paths == {CURRENT}
    assert M.retire_replaced(e, {OLD: [CURRENT]}) == []  # fresh receiver has no parent


@pytest.mark.parametrize('replacements', [{}, {OLD: []}, {OLD: [OLD]},
    {OLD: [CURRENT], CURRENT: [OLD]}, {OLD: [CURRENT, CURRENT]},
    {'/Game/../Parent': [CURRENT]}, {OLD: [CURRENT+'.Wrong']}])
def test_invalid_replacement_ownership_never_deletes(replacements):
    e, paths, deleted = editor([OLD, CURRENT])
    with pytest.raises(ValueError):
        M.retire_replaced(e, replacements)
    assert not deleted and paths == {OLD, CURRENT}


def test_replacement_paths_allow_actual_negative_city_cells():
    current = ROOT+'/HD_Streets_cell_-1_2_Piece03'
    e, paths, deleted = editor([OLD, current])
    assert M.retire_replaced(e, {OLD: [current]}) == [OLD]
    assert paths == {current}
