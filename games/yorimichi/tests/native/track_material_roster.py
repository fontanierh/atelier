"""Finite Track fixture material ownership, independent of Unreal and host geometry."""
import json
from pathlib import Path
import re
import struct

from atomic_equivalence_io import require

STATION_MATERIALS=frozenset(('MI_ST_Clock','MI_ST_Coach','MI_ST_Glass','MI_ST_Green'))


def glb_material_names(path):
    """Read only the actual owner's GLB JSON material table, without decoding geometry."""
    with Path(path).open('rb') as stream:
        header=stream.read(20)
        require(len(header)==20,'Truncated Track material source')
        magic,version,total,size,kind=struct.unpack('<5I',header)
        require(magic==0x46546c67 and version==2 and kind==0x4e4f534a and 0<size<=16*1024*1024
                and total==Path(path).stat().st_size,'Invalid Track material GLB header')
        value=json.loads(stream.read(size))
    materials=value.get('materials',[])
    indices={primitive['material'] for node in value.get('nodes',[]) if 'mesh' in node
             for primitive in value['meshes'][node['mesh']]['primitives'] if 'material' in primitive}
    require(all(type(index) is int and 0<=index<len(materials) for index in indices),'Invalid source primitive material')
    return {materials[index].get('name') for index in indices}


def library_membership(runtime,report,root,source_materials):
    """@cc [owner:fontanierh,label:correctness] finite-track-station-material-roster
    Owned materials MUST be genuinely reported at their exact owner paths and witnessed
    by both runtime material keys and the owner's actual LOD0 source GLB table.
    Only the four explicit station names MAY extend the existing MI_TK schema;
    an MI_ST prefix, unused runtime declaration or fabricated alias MUST NOT suffice.
    """
    require(re.fullmatch(r'/Game/AtelierValidation/Track_[0-9a-f]{12}/Library',root),'Foreign Track library')
    require(set(report['meshes'])==set(runtime['meshes'])==set(source_materials),'Incomplete source/report mesh roster')
    required={key for key in STATION_MATERIALS if any(key in row['materials'] and key in source_materials[name]['names']
                for name,row in runtime['meshes'].items())}
    require(required<=set(report['materials']),'Missing source-consumed station material report')
    for name,row in source_materials.items():
        path=Path(row['path'])
        require(path.name==name+'_LOD0.glb' and path.parent.name=='meshes' and '..' not in path.parts,
                'Wrong Track source material witness path')
    owned=set();witnesses={}
    for key,path in report['materials'].items():
        require(isinstance(key,str) and isinstance(path,str),'Invalid material ownership record')
        if key.startswith('MI_B_'):continue  # Existing environment-owned binding; not a Library package.
        require(re.fullmatch(r'MI_TK_[A-Za-z0-9_]+',key) or key in STATION_MATERIALS,
                'Unknown owned Track material')
        package=root+'/Materials/'+key
        require(path==package+'.'+key,'Wrong Track material owner path')
        users=[name for name,row in runtime['meshes'].items()
               if key in row['materials'] and key in source_materials[name]['names']]
        require(users,'Reported material lacks a runtime/source GLB witness')
        owned.add(package)
        witnesses[key]=dict(path=path,owner_function='import_belmonte_track.track_material',
            sources=[dict(mesh=name,path=source_materials[name]['path']) for name in sorted(users)])
    return ({root+'/'+name for name in runtime['meshes']} | {root+'/Materials/M_TK_Glow'} | owned),witnesses


def source_tables(runtime,track):
    """Same exact LOD0 paths read by the unchanged production importer's glb_materials."""
    result={}
    for name,row in runtime['meshes'].items():
        relative=Path(row['lods'][0])
        require(not relative.is_absolute() and '..' not in relative.parts
                and relative.as_posix()=='meshes/'+name+'_LOD0.glb','Foreign Track source material path')
        path=Path(track)/relative
        result[name]=dict(path=str(path),names=glb_material_names(path))
    return result
