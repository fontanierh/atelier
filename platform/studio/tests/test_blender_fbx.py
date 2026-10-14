"""Metadata adapter checks without launching Blender; native equivalence is a separate proof."""
import datetime
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from atelier.blender.fbx import stable_export, stable_id


def test_ids_ignore_process_hash_seed_and_keep_connection_sentinels():
    script = "from atelier.blender.fbx import stable_id; print(stable_id(('Tree', 'Mesh')))"
    values = [subprocess.check_output([sys.executable, '-c', script],
                                     env=dict(os.environ, PYTHONHASHSEED=seed)) for seed in ('0', '91')]
    assert values[0] == values[1]
    assert stable_id(0) == 0
    assert 0 < stable_id(('Tree', 'Mesh')) < 2 ** 63
    assert stable_id(('Tree', 'Mesh')) != stable_id(('Tree', 'Collision'))
    with pytest.raises(ValueError, match='Unsupported'):
        stable_id(object())


def test_adapter_is_scoped_and_clears_history_even_after_failure(monkeypatch):
    times = []
    exporter = SimpleNamespace(fbx_header_elements=lambda root, scene, time=None: times.append(time))
    utils = SimpleNamespace(_key_to_uuid=lambda used, key: 42, UUID=int,
                            _keys_to_uuids={'old': 42}, _uuids_to_keys={42: 'old'})
    before = (exporter.fbx_header_elements, utils._key_to_uuid, utils._keys_to_uuids, utils._uuids_to_keys)
    monkeypatch.setitem(sys.modules, 'io_scene_fbx', SimpleNamespace(export_fbx_bin=exporter, fbx_utils=utils))
    with pytest.raises(RuntimeError, match='export failed'):
        with stable_export():
            exporter.fbx_header_elements(None, None)
            assert utils._keys_to_uuids == utils._uuids_to_keys == {}
            uid = utils._key_to_uuid({}, 'Tree')
            with pytest.raises(ValueError, match='collision'):
                utils._key_to_uuid({uid: 'other key'}, 'Tree')
            utils._keys_to_uuids['new'] = uid
            raise RuntimeError('export failed')
    assert times == [datetime.datetime(1970, 1, 1)]
    after = (exporter.fbx_header_elements, utils._key_to_uuid, utils._keys_to_uuids, utils._uuids_to_keys)
    assert all(a is b for a, b in zip(before, after))
    with stable_export():
        assert utils._keys_to_uuids == {}
        assert utils._key_to_uuid({}, 'Tree') == uid
