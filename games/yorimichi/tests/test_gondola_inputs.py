"""Only final terrain groups in the declared corridor enter ground identities."""
import json
from pathlib import Path
import sys

import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'world'))
from gondola import inputs


@pytest.fixture
def exports(tmp_path,monkeypatch):
    manifest=tmp_path/'source.json'
    manifest.write_text(json.dumps({'meshes':[
        {'name':'SM_BM_BT_Terrain_near','bounds_m':[[400,4000,0],[500,4650,1]]},
        {'name':'SM_BM_BT_Terrain_far','bounds_m':[[1000,4000,0],[1100,4650,1]]}]}))
    monkeypatch.setattr(inputs,'MANIFEST',manifest)
    transform={'translation_cm':[0.,0.,0.],'rotation_xyzw':[0.,0.,0.,1.],'scale':[1.,1.,1.]}
    names=['SM_BM_BT_Terrain_near','SM_BM_BT_Terrain_far','SM_BM_NorthApron','SM_BM_House']
    groups=[{'asset':f'/Game/{n}.{n}','transforms':[transform], 'materials':['material']} for n in names]
    runtime={'origin_cm':[0,0,0],'groups':groups}
    path=tmp_path/'belmonte/runtime.json';path.parent.mkdir();path.write_text(json.dumps(runtime))
    return tmp_path,path,runtime


def test_ground_identity_ignores_distant_tiles_props_and_materials(exports):
    folder,path,runtime=exports
    first=inputs.selected_ground(folder)
    assert len(first['groups'])==2
    runtime['groups'][0]['materials']=['changed material']
    runtime['groups'][-1]['asset']='/Game/ChangedProp.ChangedProp'
    path.write_text(json.dumps(runtime))
    assert inputs.selected_ground(folder)==first
    assert all('far' not in str(p) and 'House' not in str(p) for p in inputs.paths(folder))


def test_unsupported_ground_placement_is_explicitly_refused(exports):
    folder,path,runtime=exports
    runtime['groups'][0]['transforms'][0]['translation_cm'][0]=100
    path.write_text(json.dumps(runtime))
    with pytest.raises(ValueError,match='identity Belmonte placement'):
        inputs.selected_ground(folder)


def test_ground_snapshot_changes_when_extraction_or_decoding_code_changes(exports,monkeypatch):
    folder,path,runtime=exports
    asset=folder/'ground.npz';asset.write_bytes(b'unchanged final geometry')
    extractor=folder/'probe.py';extractor.write_text('old decoding')
    monkeypatch.setattr(inputs,'CODE',{'probe.py':extractor})
    monkeypatch.setattr(inputs,'paths',lambda build:[asset])
    old=inputs.snapshot(folder)
    product=folder/'gondola/world';product.mkdir(parents=True)
    (product/'ground.npz').write_bytes(asset.read_bytes())
    import hashlib
    (product/'ground.json').write_text(json.dumps({'inputs':old,'output_sha256':hashlib.sha256(asset.read_bytes()).hexdigest()}))
    extractor.write_text('corrected decoding')
    new=inputs.snapshot(folder)
    assert old['files']==new['files'] and old['belmonte_ground']==new['belmonte_ground']
    assert old['code']!=new['code']
    from gondola.products import ground
    with pytest.raises(ValueError,match='ground exports changed'):
        ground(folder)


def test_ground_extractor_bootstraps_studio_in_an_isolated_blender_environment():
    """Blender supplies NumPy/bpy but does not install the Atelier package."""
    import subprocess
    import numpy as np
    probe=Path(__file__).resolve().parents[1]/'world/gondola/probe.py'
    code='\n'.join((
        'import runpy,sys,types',
        f'sys.path.append({str(Path(np.__file__).resolve().parents[1])!r})',
        "sys.modules['bpy']=types.ModuleType('bpy')",
        f"runpy.run_path({str(probe)!r},run_name='ground_extractor_import')",
        "assert 'atelier.gltf' in sys.modules",
    ))
    result=subprocess.run([sys.executable,'-I','-S','-c',code],capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stderr
