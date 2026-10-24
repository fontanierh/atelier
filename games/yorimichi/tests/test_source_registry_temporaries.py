"""The original compact source snapshot keeps bytes and scoped temporary ownership."""
import importlib.util
import json
from pathlib import Path
import pytest
from atelier import paths
from atelier.atomic_files import managed_temporaries


@pytest.fixture
def registry():
    spec=importlib.util.spec_from_file_location('owned_source_registry',paths.REPO/'games/yorimichi/world/source_registry.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_default_and_managed_snapshot_bytes_and_scope_reset(registry,tmp_path,monkeypatch):
    library=tmp_path/'library.json';library.write_text(json.dumps({'files':{
        'brinecove/models/model.glb':{'sha256':'a'*64},'unrelated.glb':{'sha256':'b'*64}}}))
    normal=tmp_path/'normal/snapshot.json';managed=tmp_path/'managed/snapshot.json';scratch=tmp_path/'scratch'
    original=registry.tempfile.NamedTemporaryFile;observed=[]
    def temporary(*args,**kwargs):
        observed.append(Path(kwargs['dir']));return original(*args,**kwargs)
    monkeypatch.setattr(registry.tempfile,'NamedTemporaryFile',temporary)
    registry.publish(library,normal,'brinecove/models/')
    with managed_temporaries(scratch):registry.publish(library,managed,'brinecove/models/')
    assert normal.read_bytes()==managed.read_bytes()==b'{"files":{"brinecove/models/model.glb":{"sha256":"'+b'a'*64+b'"}}}\n'
    assert normal.stat().st_mode==managed.stat().st_mode and observed==[normal.parent,scratch]
    assert list(scratch.iterdir())==[]
    again=tmp_path/'after/snapshot.json';registry.publish(library,again,'brinecove/models/')
    assert observed[-1]==again.parent
