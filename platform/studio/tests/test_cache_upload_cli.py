"""Explicit upload CLI wiring without network, credential access or cache writes."""
import json

from atelier import artifact_upload, cache_admin, cli


def test_upload_cli_forwards_only_explicit_configuration(tmp_path, monkeypatch, capsys):
    calls = []
    def upload(directory, trust, **kwargs):
        calls.append((directory, trust, kwargs))
        return {'uploaded': False, 'dry_run': True}
    monkeypatch.setattr(artifact_upload, 'upload_bundle', upload)
    args = cli.make_parser().parse_args(['cache', 'upload-bundle', str(tmp_path / 'bundle'),
                                       '--trust', str(tmp_path / 'trust.json'),
                                       '--profile', str(tmp_path / 'upload.json'), '--dry-run', '--timeout', '2'])
    assert cache_admin.main(args) == 0
    assert json.loads(capsys.readouterr().out) == {'uploaded': False, 'dry_run': True}
    directory, trust, options = calls[0]
    assert directory == tmp_path / 'bundle' and trust == tmp_path / 'trust.json'
    assert options['profile'] == tmp_path / 'upload.json' and options['dry_run'] is True and options['timeout'] == 2.


def test_upload_cli_reports_safe_failure(tmp_path, monkeypatch, capsys):
    def refuse(*args, **kwargs):
        raise artifact_upload.UploadError('Every uploaded product requires an explicit public redistribution grant')
    monkeypatch.setattr(artifact_upload, 'upload_bundle', refuse)
    args = cli.make_parser().parse_args(['cache', 'upload-bundle', str(tmp_path),
                                       '--trust', 'trust.json', '--profile', 'upload.json'])
    assert cache_admin.main(args) == 1
    assert capsys.readouterr().out.strip() == 'cache: Every uploaded product requires an explicit public redistribution grant'
