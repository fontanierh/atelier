from types import SimpleNamespace

import pytest

from atelier.native_packages import save


@pytest.mark.parametrize('result,file_kind', [(False, 'file'), (True, 'missing'), (True, 'directory'), (True, 'link')])
def test_save_refuses_failed_or_missing_regular_primary(tmp_path, result, file_kind):
    path = tmp_path / 'Audio/Wave.uasset'
    path.parent.mkdir()
    if file_kind == 'file':
        path.write_bytes(b'previous bytes')
    elif file_kind == 'directory':
        path.mkdir()
    elif file_kind == 'link':
        path.symlink_to(tmp_path / 'absent')
    editor = SimpleNamespace(save_loaded_asset=lambda *a, **k: result)
    with pytest.raises(RuntimeError):
        save(SimpleNamespace(get_path_name=lambda: '/Game/Audio/Wave.Wave'), editor, tmp_path)


def test_success_requires_current_save_and_returns_disk_primary(tmp_path):
    calls = []
    def saved(asset, **kwargs):
        calls.append(kwargs)
        path = tmp_path / 'Audio/Wave.uasset'
        path.parent.mkdir()
        path.write_bytes(b'current saved package')
        return True
    asset = SimpleNamespace(get_path_name=lambda: '/Game/Audio/Wave.Wave')
    assert save(asset, SimpleNamespace(save_loaded_asset=saved), tmp_path) == tmp_path / 'Audio/Wave.uasset'
    assert calls == [{'only_if_is_dirty': False}]


@pytest.mark.parametrize('name', ['/Engine/Wave.Wave', '/Game/../Wave.Wave', '/Game/Audio/Wave.Other'])
def test_unowned_destination_refuses_before_editor_save(tmp_path, name):
    editor = SimpleNamespace(save_loaded_asset=lambda *a, **k: pytest.fail('must not save unowned paths'))
    with pytest.raises(RuntimeError):
        save(SimpleNamespace(get_path_name=lambda: name), editor, tmp_path)
