"""Observed read closure: native recording remains explicitly best effort."""
from pathlib import Path
import pytest
from atelier.build_v2.unreal_worker import JobRefused, validate_read_report


def report(*files):
    return {'version': 1, 'best_effort': True, 'files': [str(p) for p in files]}


def test_declared_files_generated_outputs_and_installed_platform_are_accepted(tmp_path):
    source = tmp_path / 'in' / 'mesh.fbx'
    code = tmp_path / 'op.py'
    output = tmp_path / 'Content' / 'mesh.uasset'
    engine = tmp_path / 'installed-engine'
    validate_read_report(report(source, code, output, engine / 'Data' / 'table'),
                         [source, code], [engine], [output])


@pytest.mark.parametrize('unknown', ['in/other.fbx', 'other.py', 'Content/ambient.uasset', 'ddc-sibling/data'])
def test_unknown_data_code_and_upstream_reads_fail(tmp_path, unknown):
    with pytest.raises(JobRefused, match='undeclared') as error:
        validate_read_report(report(tmp_path / unknown), [tmp_path / 'in/mesh.fbx'], [tmp_path / 'ddc'])
    assert error.value.kind == 'dependency'


def test_declared_symlink_cannot_authorize_another_file(tmp_path):
    declared = tmp_path / 'declared'
    declared.write_text('known')
    alias = tmp_path / 'alias'
    alias.symlink_to(tmp_path / 'unknown')
    with pytest.raises(JobRefused, match='undeclared'):
        validate_read_report(report(alias), [declared])


@pytest.mark.parametrize('value', [None, {}, {'version': True, 'best_effort': True, 'files': []},
                                  report(Path('relative')), {'version': 1, 'best_effort': False, 'files': []}])
def test_missing_malformed_or_relative_reports_fail(value):
    with pytest.raises(JobRefused):
        validate_read_report(value, [])
