"""Native QA binds plugin binaries through their declared module manifests."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

SPEC=importlib.util.spec_from_file_location('native_module_identity',Path(__file__).resolve().parents[1]/'tools/network_review_common.py')
MODULE=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(MODULE)
NAME='OwnedModule'
FILE='libUnrealEditor-OwnedModule.dylib'


def project(tmp_path):
    path=tmp_path/'Game.uproject';path.write_text('{}')
    return SimpleNamespace(uproject=path)


def plugin(ctx,folder='OwnedPlugin',build_id='current',filename=FILE):
    root=ctx.uproject.parent/'Plugins'/folder;root.mkdir(parents=True)
    (root/(folder+'.uplugin')).write_text(json.dumps({'Modules':[{'Name':NAME}]}))
    binaries=root/'Binaries/Mac';binaries.mkdir(parents=True)
    (binaries/'UnrealEditor.modules').write_text(json.dumps({'BuildId':build_id,'Modules':{NAME:filename}}))
    path=binaries/filename;path.write_bytes(b'actual plugin module')
    return path


def test_game_and_plugin_module_locations_are_supported(tmp_path):
    ctx=project(tmp_path)
    path=ctx.uproject.parent/'Binaries/Mac'/FILE;path.parent.mkdir(parents=True);path.write_bytes(b'game')
    assert MODULE.native_module_binary(ctx,NAME,FILE,'current','Mac')==path
    path.unlink();path=plugin(ctx)
    assert MODULE.native_module_binary(ctx,NAME,FILE,'current','Mac')==path


@pytest.mark.parametrize('fault',['missing','wrong-build','wrong-name','ambiguous','traversal'])
def test_unbound_or_ambiguous_native_module_refuses(tmp_path,fault):
    ctx=project(tmp_path)
    if fault!='missing':
        plugin(ctx,build_id='old' if fault=='wrong-build' else 'current',filename='other.dylib' if fault=='wrong-name' else FILE)
    if fault=='ambiguous':plugin(ctx,folder='SecondProvider')
    with pytest.raises(RuntimeError):
        MODULE.native_module_binary(ctx,NAME,'../'+FILE if fault=='traversal' else FILE,'current','Mac')
