"""Complete-root codec and producer-view boundary regressions."""
import io
import json
from pathlib import Path
import tarfile

import pytest

from atelier.build_v2 import recipe_job as job


def test_complete_root_roundtrip_file_directory_empty_and_absent(tmp_path):
    for kind in ('file', 'directory', 'empty', 'absent'):
        source = tmp_path / kind
        if kind == 'file':
            source.write_bytes(b'raw\0payload')
        elif kind in ('directory', 'empty'):
            source.mkdir()
            if kind == 'directory':
                (source / 'nested').mkdir()
                (source / 'nested/data').write_bytes(b'content')
                (source / 'nested/executable').write_bytes(b'executable')
                (source / 'nested/executable').chmod(0o755)
        archive = tmp_path / (kind + '.tar')
        manifest = job.pack_root(source, archive, required=kind != 'absent')
        duplicate = tmp_path / (kind + '.again.tar')
        job.pack_root(source, duplicate, required=kind != 'absent')
        assert archive.read_bytes() == duplicate.read_bytes()
        result = tmp_path / (kind + '.restored')
        assert job.unpack_root(archive, result) == manifest
        assert job.inventory(result) == job.inventory(source)


def test_missing_required_link_and_existing_destination_refuse(tmp_path):
    with pytest.raises(ValueError, match='required'):
        job.pack_root(tmp_path / 'missing', tmp_path / 'required.tar')
    target = tmp_path / 'target'
    target.write_text('data')
    alias = tmp_path / 'alias'
    alias.symlink_to(target)
    with pytest.raises(ValueError, match='link'):
        job.pack_root(alias, tmp_path / 'link.tar')
    archive = tmp_path / 'valid.tar'
    job.pack_root(target, archive)
    with pytest.raises(ValueError, match='exists'):
        job.unpack_root(archive, target)
    assert target.read_text() == 'data'


@pytest.mark.parametrize('name,kind', [('../escape', 'file'), ('root', 'symlink'), ('root', 'hardlink')])
def test_archive_unknown_paths_and_links_refuse_before_root_write(tmp_path, name, kind):
    archive = tmp_path / 'bad.tar'
    manifest = json.dumps({'version': 1, 'kind': 'file', 'entries': [['', 'file', 1, 0o644, '0' * 64]]}).encode()
    with tarfile.open(archive, 'w', format=tarfile.USTAR_FORMAT) as output:
        row = tarfile.TarInfo(job.MANIFEST)
        row.size = len(manifest)
        output.addfile(row, io.BytesIO(manifest))
        row = tarfile.TarInfo(name)
        row.size = 1
        row.mode = 0o644
        if kind != 'file':
            row.type = tarfile.SYMTYPE if kind == 'symlink' else tarfile.LNKTYPE
            row.linkname = '/outside'
        output.addfile(row, io.BytesIO(b'x') if kind == 'file' else None)
    destination = tmp_path / 'restored'
    with pytest.raises(ValueError):
        job.unpack_root(archive, destination)
    assert not destination.exists()


def test_view_uses_declared_mapping_and_refuses_output_input_overlap(tmp_path):
    (tmp_path / job.RUNTIME).mkdir(mode=0o700)
    (tmp_path / 'source.py').write_text('def run(): pass\n')
    (tmp_path / 'inputs').mkdir()
    (tmp_path / 'inputs/raw').write_text('input')
    request = {'code': ['source.py'], 'inputs': [{'path': 'inputs/raw'}],
               'params': {'recipe': {'paths': {'data/raw': 'inputs/raw'},
                                     'outputs': [{'path': 'build/result'}]}}}
    view, protected, writes = job.prepare_view(request, tmp_path)
    assert (view / 'data/raw').read_text() == 'input'
    assert str(view / 'source.py') in protected
    assert writes == [str(view / 'build/result')]
    assert (tmp_path / 'inputs/raw').read_text() == 'input'


def test_existing_parent_mkdir_is_noop_only_and_other_writes_remain_refused(tmp_path):
    from atelier.build_v2.python_job import PathGuard
    output = tmp_path / 'build' / 'product'
    output.parent.mkdir()
    guard = PathGuard(str(tmp_path), [], [], lambda report: None,
                      [str(output)], mkdir_existing=[str(output.parent)])
    calls = []
    def mkdir(path, **kwargs):
        calls.append(path)
        raise FileExistsError(path)
    wrapped = guard.wrap('mkdir', mkdir, 'write')
    with pytest.raises(FileExistsError):
        wrapped(str(output.parent))
    assert calls == [str(output.parent)]
    assert not guard.allowed('write', str(output.parent))
    assert not guard.allowed('write', str(output.parent / 'other'))
    assert guard.allowed('write', str(output))


def test_nested_callback_binds_actual_freevars_without_evaluating_artificial_defaults(tmp_path):
    source = tmp_path / 'callback.py'
    source.write_text('def factory(path):\n    def action(value=3):\n        return path.name, value\n    return action\n')
    fn = job.bind({'source': 'callback.py', 'qualname': 'factory.<locals>.action', 'line': 2,
                   'captures': [{'path': 'data/expected'}], 'defaults': [7], 'kwdefaults': {}}, tmp_path)
    assert fn() == ('expected', 7)
    with pytest.raises(ValueError, match='closure'):
        job.bind({'source': 'callback.py', 'qualname': 'factory.<locals>.action', 'line': 2,
                  'captures': [], 'defaults': [], 'kwdefaults': {}}, tmp_path)


def test_derived_roster_requires_actual_resolved_member_list(tmp_path):
    descriptor = {'derived_items': {'root': 'build/exports', 'members': [
        {'piece': 'PieceA', 'root': 'build/exports/PieceA', 'slot': 'derived_0'}]}}
    result = job._value(descriptor, tmp_path)
    assert result[0][1] == 'PieceA'
    assert result[0][0].products[0].paths == (tmp_path / 'build/exports/PieceA',)
    with pytest.raises(ValueError, match='unresolved'):
        job._value({'derived_items': {'root': 'build/exports', 'templates': []}}, tmp_path)
