"""Only explicit final source/query products in the corridor enter ground identities."""
import json
from pathlib import Path
import sys

import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'world'))
from gondola import inputs,source_inputs


@pytest.fixture
def exports(tmp_path):
    models={name:dict(source=dict(bounds_m=bounds)) for name,bounds in (
        ('SM_BM_BT_Terrain_near',[[400,4000,0],[500,4650,1]]),
        ('SM_BM_BT_Terrain_far',[[1000,4000,0],[1100,4650,1]]))}
    product=source_inputs.ground_projection(tmp_path,models=models,origin=[0,0,0])
    path=tmp_path/'gondola/world/ground-sources.json';path.parent.mkdir(parents=True);path.write_text(json.dumps(product))
    return tmp_path,path,product,models


def test_ground_identity_ignores_distant_tiles_props_and_materials(exports):
    folder,path,product,models=exports
    first=inputs.selected_ground(folder)
    assert len(first['groups'])==2
    models['SM_BM_BT_Terrain_near']['source']['materials']=['changed material']
    models['SM_BM_BT_Terrain_far']['source']['bounds_m']=[[1200,4000,0],[1300,4650,1]]
    assert source_inputs.ground_projection(folder,models=models,origin=[0,0,0])==product
    assert inputs.selected_ground(folder)==first
    assert all('far' not in str(p) and 'Country' not in str(p) for p in inputs.paths(folder))
    assert not any(p.suffix in ('.fbx','.glb') for p in inputs.paths(folder))
    assert any(p.name=='HD_NorthTrail.npz' for p in inputs.paths(folder))


def test_unsupported_ground_placement_is_explicitly_refused(exports):
    folder,path,product,_=exports
    product['groups'][0]['transforms']=[{'translation_cm':[100,0,0]}]
    path.write_text(json.dumps(product))
    with pytest.raises(ValueError,match='ground source member'):inputs.selected_ground(folder)


def test_ground_snapshot_changes_when_extraction_or_decoding_code_changes(exports,monkeypatch):
    folder,path,runtime,_=exports
    asset=folder/'ground.npz';asset.write_bytes(b'unchanged final geometry')
    extractor=folder/'probe.py';extractor.write_text('old decoding')
    monkeypatch.setattr(inputs,'CODE',{'probe.py':extractor})
    monkeypatch.setattr(inputs,'geometry_paths',lambda build,ground:[asset])
    old=inputs.snapshot(folder)
    product=folder/'gondola/world';product.mkdir(parents=True,exist_ok=True)
    (product/'ground.npz').write_bytes(asset.read_bytes())
    import hashlib
    (product/'ground.json').write_text(json.dumps({'inputs':old,'output_sha256':hashlib.sha256(asset.read_bytes()).hexdigest()}))
    extractor.write_text('corrected decoding')
    new=inputs.snapshot(folder)
    assert old['files']==new['files'] and old['belmonte_ground']==new['belmonte_ground']
    assert old['code']!=new['code']
    from gondola.products import ground
    with pytest.raises(ValueError,match='ground exports changed'):ground(folder)


def test_ground_extractor_bootstraps_studio_without_bpy():
    import subprocess
    import numpy as np
    probe=Path(__file__).resolve().parents[1]/'world/gondola/probe.py'
    code='\n'.join(('import runpy,sys',f'sys.path.append({str(Path(np.__file__).resolve().parents[1])!r})',
        f"runpy.run_path({str(probe)!r},run_name='ground_extractor_import')",
        "assert 'atelier.gltf' in sys.modules and 'bpy' not in sys.modules"))
    result=subprocess.run([sys.executable,'-I','-S','-c',code],capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stderr
