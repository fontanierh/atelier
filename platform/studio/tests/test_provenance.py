import subprocess

import pytest

from atelier import provenance


def test_source_revision_names_the_commit_and_any_change(tmp_path):
    git = lambda *args: subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', *args], cwd=tmp_path,
                                       check=True, capture_output=True, text=True).stdout.strip()
    git('init', '-q'); (tmp_path / 'a.txt').write_text('a'); git('add', 'a.txt'); git('commit', '-qm', 'a')
    head = git('rev-parse', 'HEAD')
    assert provenance.source_revision(tmp_path) == dict(head_sha=head, dirty=False)
    assert provenance.head(tmp_path, short=8) == head[:8]
    (tmp_path / 'new.txt').write_text('untracked')
    assert provenance.source_revision(tmp_path)['dirty'] and not provenance.status(tmp_path, untracked=False)
    with pytest.raises(RuntimeError, match='Commit the reviewed source'):
        provenance.require_clean_source('Commit the reviewed source', root=tmp_path)
    (tmp_path / 'a.txt').write_text('changed')
    assert provenance.status(tmp_path, untracked=False).strip() == 'M a.txt'
