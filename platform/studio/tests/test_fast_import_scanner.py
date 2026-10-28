"""The plan-scoped scanner lists each directory once, yet rediscovers added/removed modules and keeps precedence."""
from atelier import build


def write(root, files):
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)


def test_a_module_added_after_a_cached_closure_is_found_by_the_next_scanner(tmp_path):
    write(tmp_path, {'entry.py': 'import helper\nfrom pkg import later\n', 'pkg/__init__.py': ''})
    first = build._FastImportScanner().local_imports(tmp_path / 'entry.py', (tmp_path,))
    assert set(first) == {tmp_path / 'entry.py', tmp_path / 'pkg/__init__.py'}
    write(tmp_path, {'helper.py': '', 'pkg/later.py': ''})
    second = build._FastImportScanner().local_imports(tmp_path / 'entry.py', (tmp_path,))
    assert set(second) == {tmp_path / n for n in ('entry.py', 'helper.py', 'pkg/__init__.py', 'pkg/later.py')}


def test_a_package_created_under_an_absent_directory_is_found(tmp_path):
    write(tmp_path, {'entry.py': 'from deep.inner import leaf\n'})
    assert build._FastImportScanner().local_imports(tmp_path / 'entry.py', (tmp_path,)) == [tmp_path / 'entry.py']
    write(tmp_path, {'deep/inner/leaf.py': ''})
    assert set(build._FastImportScanner().local_imports(tmp_path / 'entry.py', (tmp_path,))) == {
        tmp_path / 'entry.py', tmp_path / 'deep/inner/leaf.py'}


def test_a_removed_module_leaves_the_next_closure(tmp_path):
    write(tmp_path, {'entry.py': 'import helper\n', 'helper.py': 'import leaf\n', 'leaf.py': ''})
    assert len(build._FastImportScanner().local_imports(tmp_path / 'entry.py', (tmp_path,))) == 3
    (tmp_path / 'leaf.py').unlink()
    (tmp_path / 'helper.py').write_text('X = 1\n')  # a changed source re-reads its imports
    assert set(build._FastImportScanner().local_imports(tmp_path / 'entry.py', (tmp_path,))) == {
        tmp_path / 'entry.py', tmp_path / 'helper.py'}


def test_one_scanner_keeps_precedence_per_search(tmp_path):
    # One shared helper resolves `common` by each call's own search order, never by a previous call's answer.
    write(tmp_path, {'entry.py': 'import shared\n', 'lib/shared.py': 'import common\n', 'a/common.py': '', 'b/common.py': ''})
    scanner = build._FastImportScanner()
    a = scanner.local_imports(tmp_path / 'entry.py', (tmp_path / 'lib', tmp_path / 'a'))
    b = scanner.local_imports(tmp_path / 'entry.py', (tmp_path / 'lib', tmp_path / 'b'))
    assert tmp_path / 'a/common.py' in a and tmp_path / 'b/common.py' not in a
    assert tmp_path / 'b/common.py' in b and tmp_path / 'a/common.py' not in b
    write(tmp_path, {'lib/common.py': ''})  # the helper's own directory now wins, in the next plan
    fresh = build._FastImportScanner().local_imports(tmp_path / 'entry.py', (tmp_path / 'lib', tmp_path / 'a'))
    assert tmp_path / 'lib/common.py' in fresh and tmp_path / 'a/common.py' not in fresh


def test_a_directory_named_like_a_module_is_not_a_module(tmp_path):
    write(tmp_path, {'entry.py': 'import odd\n', 'odd.py/keep.txt': ''})
    assert build._FastImportScanner().local_imports(tmp_path / 'entry.py', (tmp_path,)) == [tmp_path / 'entry.py']
