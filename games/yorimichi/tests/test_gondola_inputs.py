"""Only final terrain groups in the declared corridor enter ground identities."""
import json
from pathlib import Path
import sys

import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'world'))
from gondola import inputs


@pytest.fixture
def exports(tmp_path,monkeypatch):
    surfaces=[{'name':name,'path':'ground/glb/'+name+'.glb','bounds_m':bounds}
              for name,bounds in [('SM_BM_BT_Terrain_near',[[400,4000,0],[500,4650,1]]),
                                 ('SM_BM_BT_Terrain_far',[[1000,4000,0],[1100,4650,1]]),
                                 ('SM_BM_NorthApron',[[0,0,0],[100,100,1]]),
                                 ('SM_BM_NorthCountry',[[0,0,0],[100,100,1]])]]
    product={'schema':1,'origin_cm':[0,0,0],'surfaces':surfaces}
    path=tmp_path/'products/belmonte/ground.json';path.parent.mkdir(parents=True);path.write_text(json.dumps(product))
    return tmp_path,path,product


def test_ground_identity_ignores_distant_tiles_props_and_materials(exports):
    folder,path,product=exports
    first=inputs.selected_ground(folder)
    assert len(first['groups'])==2
    product['surfaces'][0]['materials']=['changed material']
    product['surfaces'][1]['bounds_m']=[[1200,4000,0],[1300,4650,1]]
    product['unrelated_props']=['changed']
    path.write_text(json.dumps(product))
    assert inputs.selected_ground(folder)==first
    assert all('far' not in str(p) and 'Country' not in str(p) for p in inputs.paths(folder))
    assert all('/ground/glb/' in str(p) for p in inputs.paths(folder) if p.suffix=='.glb')


def test_unsupported_ground_placement_is_explicitly_refused(exports):
    folder,path,product=exports
    product['surfaces'][0]['transforms']=[{'translation_cm':[100,0,0]}]
    path.write_text(json.dumps(product))
    with pytest.raises(ValueError,match='identity Belmonte placement'):
        inputs.selected_ground(folder)


def test_ground_snapshot_changes_when_extraction_or_decoding_code_changes(exports,monkeypatch):
    folder,path,runtime=exports
    asset=folder/'ground.npz';asset.write_bytes(b'unchanged final geometry')
    extractor=folder/'probe.py';extractor.write_text('old decoding')
    monkeypatch.setattr(inputs,'CODE',{'probe.py':extractor})
    monkeypatch.setattr(inputs,'geometry_paths',lambda build,ground:[asset])
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
