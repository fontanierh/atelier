"""Tiny receiving-native codec check before the diagnostic preparation retry."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'world'))
import yori

import struct
import unreal as U
from atelier import mesh_geometry as G
from foliage_variant_validation import matches, settings_reader

E=U.EditorAssetLibrary
source_path='/Game/Belmonte/Meshes/SM_BM_BP_BarrelPlanter'
source=E.load_asset(source_path)
assert source,source_path
before=G.package_inventory(yori.GAME/'unreal/Content',[source_path])
channels=max(1,source.get_num_tex_coords(0))
levels=[]
for z in (0.,2.):
    vertices=[dict(p=p,n=[0.,0.,1.],c=[.25,.5,.75,1.],uv=[.125,.875],
                   uvs=[[channel+.125,channel+.875] for channel in range(channels)])
              for p in ([0.,0.,z],[3.,0.,z],[0.,4.,z])]
    levels.append(dict(vertices=vertices,faces=[dict(v=[0,1,2],s=0)]))
folder=yori.OUT/'foliage_transport_probe'
folder.mkdir(exist_ok=True)
path=folder/'fixture.mesh'
expected=G.write_geometry(levels,channels,path)
assert expected==G.expected_digest(levels,channels)
material=E.load_asset('/Engine/EngineMaterials/DefaultMaterial')
assert material
destination='/Game/FoliageSystem/TransportProbe'
mesh=None
try:
    mesh=U.YorimichiFoliageGeometryReader.build_variant(source,str(path),[1.,.24],destination,material,material)
    assert mesh,'Binary mesh construction failed'
    assert matches(mesh,source,[source.get_material(i) for i in range(len(source.get_editor_property('static_materials')))],
        (material,material),[1,1],[1.,.24],expected,folder/'fixture.snapshot',editor=settings_reader(U),
        snapshot=U.YorimichiFoliageBuilder.export_geometry_snapshot,digest=G.file_digest,
        refusal=lambda reason:U.log_error('FOLIAGE TRANSPORT FIXTURE: '+reason))
    data=path.read_bytes()
    malformed=[b'BAD'+data[3:],data[:-1],data+b'x',
               data[:len(G.MAGIC)]+struct.pack('<I',3)+data[len(G.MAGIC)+4:]]
    for index,value in enumerate(malformed):
        bad=folder/f'bad-{index}.mesh'
        bad.write_bytes(value)
        assert not U.YorimichiFoliageGeometryReader.build_variant(source,str(bad),[1.,.24],destination,material,material),index
finally:
    if mesh:assert E.delete_loaded_asset(mesh),'Temporary native fixture cleanup failed'
    assert G.package_inventory(yori.GAME/'unreal/Content',[source_path])==before,'Fixture changed source packages'
U.log('FOLIAGE BINARY TRANSPORT PASS')
