"""Metadata adapter checks without launching Blender; native equivalence is a separate proof."""
import datetime
import os
import subprocess
import sys
import struct
from types import SimpleNamespace

import pytest

from atelier.blender.fbx import export_fbx, stable_export, stable_id


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
    exporter = SimpleNamespace(fbx_header_elements=lambda root, scene, time=None: times.append(time),
                               _gen_vid_path=lambda image, scene: ('/checkout/texture.png', 'texture.png'))
    utils = SimpleNamespace(_key_to_uuid=lambda used, key: 42, UUID=int,
                            _keys_to_uuids={'old': 42}, _uuids_to_keys={42: 'old'})
    before = (exporter.fbx_header_elements, utils._key_to_uuid, utils._keys_to_uuids, utils._uuids_to_keys)
    monkeypatch.setitem(sys.modules, 'io_scene_fbx', SimpleNamespace(export_fbx_bin=exporter, fbx_utils=utils))
    with pytest.raises(RuntimeError, match='export failed'):
        with stable_export():
            exporter.fbx_header_elements(node(b'', [node(b'FBXHeaderExtension', [node(b'SceneInfo', [node(b'Properties70', [node(b'P', props=[string('Original|ApplicationNativeFile'), string('author.blend')])])])])]), None)
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


def node(name, children=(), props=()):
    return SimpleNamespace(id=name, elems=list(children), props=list(props), props_type=b'S'*len(props))


def string(value):
    value = value.encode()
    return struct.pack('<I', len(value)) + value


@pytest.mark.parametrize('kind', ['static', 'skeletal', 'animation'])
def test_export_preserves_options_and_scopes_all_volatile_metadata(monkeypatch, kind):
    entry = node(b'P', props=[string('Original|ApplicationNativeFile'), string('/checkout/author.blend')])
    root = node(b'', [node(b'FBXHeaderExtension', [node(b'SceneInfo', [node(b'Properties70', [entry])])])])
    times, copies, seen = [], [], []
    def media(image, scene):
        copies.append(image)
        return '/checkout/textures/albedo.png', 'textures/albedo.png'
    exporter = SimpleNamespace(fbx_header_elements=lambda r, s, time=None: times.append(time), _gen_vid_path=media)
    utils = SimpleNamespace(_key_to_uuid=lambda used, key: 9, UUID=int,
                            _keys_to_uuids={}, _uuids_to_keys={})
    monkeypatch.setitem(sys.modules, 'io_scene_fbx', SimpleNamespace(export_fbx_bin=exporter, fbx_utils=utils))
    def operation(**options):
        seen.append(options)
        exporter.fbx_header_elements(root, None)
        assert exporter._gen_vid_path('image', None) == ('textures/albedo.png', 'textures/albedo.png')
        return {'FINISHED'}
    monkeypatch.setitem(sys.modules, 'bpy', SimpleNamespace(ops=SimpleNamespace(export_scene=SimpleNamespace(fbx=operation))))
    options = dict(filepath='mesh.fbx', object_types={'MESH'} if kind == 'static' else {'ARMATURE'},
                   bake_anim=kind == 'animation', axis_forward='-Y', colors_type='SRGB', use_tspace=False)
    with stable_export():  # Existing callers may temporarily nest the metadata adapter.
        export_fbx(**options)
    assert seen == [dict(options, path_mode='RELATIVE')]
    assert all(time == datetime.datetime(1970, 1, 1) for time in times)
    assert entry.props[-1] == struct.pack('<I', 0)
    assert copies == ['image'] and exporter._gen_vid_path is media


def test_media_absolute_paths_and_cancelled_exports_refuse(monkeypatch):
    exporter = SimpleNamespace(fbx_header_elements=lambda *a, **k: None,
                               _gen_vid_path=lambda *a: ('absolute', 'C:\\checkout\\texture.png'))
    utils = SimpleNamespace(_key_to_uuid=None, UUID=int, _keys_to_uuids={}, _uuids_to_keys={})
    monkeypatch.setitem(sys.modules, 'io_scene_fbx', SimpleNamespace(export_fbx_bin=exporter, fbx_utils=utils))
    monkeypatch.setitem(sys.modules, 'bpy', SimpleNamespace(ops=SimpleNamespace(
        export_scene=SimpleNamespace(fbx=lambda **kw: {'CANCELLED'}))))
    with stable_export(), pytest.raises(ValueError, match='relative'):
        exporter._gen_vid_path(None, None)
    with pytest.raises(RuntimeError, match='did not finish'):
        export_fbx(filepath='mesh.fbx')
    with pytest.raises(ValueError, match='relative'):
        export_fbx(filepath='mesh.fbx', path_mode='ABSOLUTE')


def test_unknown_exporter_header_layout_refuses(monkeypatch):
    exporter = SimpleNamespace(fbx_header_elements=lambda *a, **kw: None, _gen_vid_path=lambda *a: ('', ''))
    utils = SimpleNamespace(_key_to_uuid=None, UUID=int, _keys_to_uuids={}, _uuids_to_keys={})
    monkeypatch.setitem(sys.modules, 'io_scene_fbx', SimpleNamespace(export_fbx_bin=exporter, fbx_utils=utils))
    with stable_export(), pytest.raises(ValueError, match='metadata layout'):
        exporter.fbx_header_elements(node(b''), None)


def test_changed_metadata_property_type_refuses(monkeypatch):
    entry = node(b'P', props=[string('Original|ApplicationNativeFile'), string('author.blend')])
    entry.props_type = b'SI'
    root = node(b'', [node(b'FBXHeaderExtension', [node(b'SceneInfo', [node(b'Properties70', [entry])])])])
    exporter = SimpleNamespace(fbx_header_elements=lambda *a, **kw: None, _gen_vid_path=lambda *a: ('', ''))
    utils = SimpleNamespace(_key_to_uuid=None, UUID=int, _keys_to_uuids={}, _uuids_to_keys={})
    monkeypatch.setitem(sys.modules, 'io_scene_fbx', SimpleNamespace(export_fbx_bin=exporter, fbx_utils=utils))
    with stable_export(), pytest.raises(ValueError, match='metadata layout'):
        exporter.fbx_header_elements(root, None)
