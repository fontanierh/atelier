"""Copy the exact independent skate export roster and original logical riding data."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
sys.path[:0]=[str(Path(__file__).resolve().parents[2]),str(Path(__file__).resolve().parents[1])]
import yori  # noqa: E402,F401
from atelier import export_manifest,mesh_ir  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.file_copy import copy_file  # noqa: E402
from atelier.export_manifest import real_directory,sha  # noqa: E402
from atelier.model_files import regular_files  # noqa: E402
from region_mesh_parts import validate  # noqa: E402
from skatepark import atomic_source as source,pieces  # noqa: E402


def copy_current(path,target,digest):
    real_directory(target.parent,create=True)
    if target.is_symlink() or (target.exists() and not target.is_file()):raise ValueError('Invalid current skate assembly member')
    if target.is_file() and sha(target)==digest:return
    with tempfile.NamedTemporaryFile(dir=target.parent,prefix='.copy-',delete=False) as stream:temporary=Path(stream.name)
    try:
        temporary.unlink();copy_file(path,temporary)
        if sha(path)!=digest or sha(temporary)!=digest:raise ValueError('Skate atomic product changed during copy')
        temporary.replace(target)
    finally:temporary.unlink(missing_ok=True)


def main(argv=None):
    """@cc [owner:fontanierh,label:correctness;performance] complete-atomic-skate-file-assembly
    Every original logical parent MUST have its complete bounded independent export
    roster and actual current FBX roundtrip evidence. Validate all receipts, source
    geometry bindings and exclusive destinations before copying. Assembly MUST NOT
    export or join geometry. Preserve exact riding triangle bytes and logical park
    semantics. Complete current membership MUST precede owned old-source retirement.
    """
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args(argv);out=args.out;root=out/'skatepark';data=out/'skatepark-data'
    real_directory(root);current=[];membership={};records={};meshes={};slots={};roundtrip={}
    for name in source.PARK+source.BOARD:
        region='skatepark_board' if name in source.BOARD else 'skatepark'
        plan_root=out/'planned_exports'/region/name;plan=validate(plan_root)
        record=json.loads((data/'records'/(name+'.json')).read_text())
        if record.get('name')!=name or record.get('triangles')!=plan['source_triangles'] or record['pieces']!=[row['name'] for row in plan['pieces']]:
            raise ValueError('Skate metadata differs from complete selected source membership')
        records[name]=record;meshes[name]={key:record[key] for key in ('triangles','vertices','min','max')}
        if name in source.PARK:membership[name]=record['pieces']
        for row in plan['pieces']:
            key=row['name'];folder=out/('exports/world.'+region+'.export')/key
            receipt=export_manifest.validate(folder,key=key)
            proof=json.loads((data/'roundtrip'/(key+'.json')).read_text())
            if (proof.get('schema')!=1 or proof.get('complete') is not True or proof.get('name')!=key
                    or proof.get('fbx_sha256')!=receipt['sha256'] or proof.get('input_sha256')!=row['sha256']
                    or proof.get('triangles')!=row['triangles'] or type(proof.get('bounds_error_mm')) not in (int,float)
                    or not 0<=proof['bounds_error_mm']<1):
                raise ValueError('Missing/stale actual per-piece skate FBX roundtrip')
            if receipt['metadata'].get('geometry_sha256')!=row['sha256']:raise ValueError('Atomic skate payload changed after export')
            meta,piece=mesh_ir.decode((plan_root/row['payload']).read_bytes())
            if proof.get('imported_triangles')!=source.imported_triangle_count(piece):
                raise ValueError('Skate actual imported polygon census differs from exact source validation')
            material_slots=[slot for i,slot in enumerate(meta['slots']) if i in set(piece['materials'])]
            item=dict(name=key,parent=name,triangles=row['triangles'],vertices=len(piece['positions']),
                min=row['min'],max=row['max'],material_slots=material_slots,source_material_slots=meta['slots'],sha256=receipt['sha256'])
            current.append((item,folder/receipt['primary'],'board' if name in source.BOARD else 'assets'))
            meshes[key]={key_:item[key_] for key_ in ('triangles','vertices','min','max')};slots[key]=material_slots
            roundtrip[key]=proof['bounds_error_mm']
        if name in source.PARK:slots[name]=record['material_slots']
    expected={kind:{item['name']+'.fbx' for item,_,family in current if family==kind} for kind in ('assets','board')}
    for kind in ('assets','board'):
        folder=real_directory(root/kind)
        if folder.exists():
            actual=regular_files(folder)
            if any('/' in name or not name.endswith('.fbx') or
                (not pieces.owned_name(Path(name).stem) if kind=='assets' else name not in expected[kind]) for name in actual):
                raise ValueError('Foreign previous skate source owner')
    for file in ('build-report.json','runtime-park.json','collision.json'):
        path=root/file
        if path.is_symlink() or (path.exists() and not path.is_file()):raise ValueError('Invalid skate metadata destination')
    logical=json.loads((data/'queries/logical.json').read_text())
    pieces.validate_logical_contract(Path(__file__).with_name('park.json'),logical)
    report=json.loads((data/'queries/report.json').read_text())
    report['ao']=json.loads((data/'ao/report.json').read_text())
    report['meshes']=meshes;report['material_slots']=slots
    report['fbx_roundtrip']=dict(max_bounds_error_mm=roundtrip)
    runtime=pieces.runtime_park(logical,membership)
    for item,path,kind in current:copy_current(path,root/kind/(item['name']+'.fbx'),item['sha256'])
    emitted=[item for item,_,kind in current if kind=='assets']
    report['pieces']=dict(triangle_limit=pieces.TRIANGLE_LIMIT,cell_metres=pieces.CELL_METRES,members=membership,
        exports=emitted,retired_exports=pieces.retire_exports(root/'assets',emitted))
    for kind in ('assets','board'):
        if regular_files(root/kind)!=expected[kind]:raise ValueError('Current skate source membership differs after retirement')
    collision=data/'queries/collision.json'
    copy_current(collision,root/'collision.json',sha(collision))
    atomic_json(root/'runtime-park.json',runtime)
    source_root=Path(__file__).parent
    report['identity']=dict(sources={str(path.relative_to(yori.REGIONS)):sha(path) for path in sorted(source_root.glob('*.py'))},
        exports={kind+'/'+item['name']+'.fbx':item['sha256'] for item,_,kind in current},
        park_json_sha256=sha(source_root/'park.json'),runtime_park_sha256=sha(root/'runtime-park.json'))
    atomic_json(root/'build-report.json',report)
    print('SKATE ATOMIC ASSEMBLY COMPLETE',len(emitted),len(source.BOARD),flush=True)


if __name__=='__main__':main()
