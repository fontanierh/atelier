"""Copy independent forest levels and impostors; assemble only their authored LOD metadata."""
import argparse
import json
from pathlib import Path
import sys
sys.path[:0]=[str(Path(__file__).resolve().parent),str(Path(__file__).resolve().parent/'regions')]
import yori  # noqa: E402,F401
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier import export_assembly  # noqa: E402
from atelier.file_copy import copy_file  # noqa: E402
from atelier.export_manifest import real_directory,sha  # noqa: E402
from atelier.model_files import regular_files,retain_files,member  # noqa: E402
from region_mesh_parts import validate  # noqa: E402
from forest_parameters import load  # noqa: E402


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--parameters',type=Path,action='append',required=True)
    args=parser.parse_args(argv)
    output=real_directory(args.out/'forest/assembled')
    source_items=[];trees={};images=[]
    for parameters in args.parameters:
        name,spec=load(parameters)
        records=[]
        for level in range(5):
            key=name if level==0 else name+f'_LOD{level}'
            plan=validate(args.out/'planned_exports/forest'/key)
            if len(plan['pieces'])!=1 or plan['pieces'][0]['name']!=key:
                raise ValueError('Authored forest LOD membership changed')
            row=plan['pieces'][0]
            if row['collision_hulls']!=(1 if level==0 else 0):
                raise ValueError('Forest whole trunk ownership differs')
            record=json.loads((args.out/'forest-data/records'/(key+'.json')).read_text())
            if record.get('name')!=name or record.get('level')!=level or record['triangles']!=row['triangles']:
                raise ValueError('Forest metadata differs from current logical geometry')
            records.append(record)
            source_items.append(export_assembly.Item(key,args.out/'exports/world.forest.export'/key))
        counts=[record['triangles'] for record in records]
        if not counts[0]>counts[1]>counts[2] or not all(0<n<=32768 for n in counts):
            raise ValueError('Forest authored LOD counts differ')
        bake=args.out/'forest-bakes'/name
        proxy=json.loads((bake/'record.json').read_text())
        if proxy['name']!=name:
            raise ValueError('Foreign forest impostor metadata')
        record=proxy['record']
        expected={name+'_'+mode+'.png' for mode in ('colour','normal')}|{'record.json'}
        expected.update(name+'-'+mode+f'-{view}.png' for mode in ('colour','normal') for view in range(4))
        if regular_files(bake)!=expected:
            raise ValueError('Incomplete forest image membership')
        images.extend((bake/file,file,sha(bake/file)) for file in sorted(expected-{'record.json'}))
        bark='BarkOlive' if spec[0]=='olive' else 'BarkTuscan' if name.startswith('Tree_Tuscan_') else 'Bark'
        trees[name]=dict(height=records[0]['height'],spread=records[0]['spread'],leaf=spec[-1],triangles=counts,
            screen_sizes=[1.,.24,.075,.018,.0054],impostor=record,impostor_slot=name+'_Impostor',
            impostor_bark=bark,crown=records[4]['crown'],trunk_hulls=records[0]['trunk_hulls'])
    # The mesh copier owns its own exclusive flat subdirectory. The final library
    # has a separate complete inventory for these files plus generated images.
    copied=args.out/'forest/mesh-files'
    manifest=export_assembly.assemble(source_items,copied)
    wanted={'trees.json','library.json',*(row['primary'] for row in manifest['exports']),*(file for _,file,_ in images)}
    current=regular_files(output) if output.exists() else set()
    previous=json.loads((output/'library.json').read_text()) if 'library.json' in current else {}
    journal=output/'.library-transaction.json'
    recorded=set()
    if previous:
        if previous.get('schema')!=1 or previous.get('complete') is not True:
            raise ValueError('Invalid previous forest library')
        recorded.update(member(file) for file in previous['files'])
    if journal.name in current:
        interrupted=json.loads(journal.read_text())
        if interrupted.get('schema')!=1 or interrupted.get('owner')!='forest':
            raise ValueError('Foreign forest assembly transaction')
        recorded.update(member(file) for file in interrupted['files'])
    if current-recorded-{'library.json',journal.name}:
        raise ValueError('Foreign previous assembled forest library')
    output.mkdir(parents=True,exist_ok=True)
    atomic_json(journal,dict(schema=1,owner='forest',files=sorted(recorded|wanted)))
    transfers=[(copied/row['primary'],row['primary'],row['sha256']) for row in manifest['exports']]+images
    for source,file,digest in transfers:
        target=output/file
        if not target.is_file() or sha(target)!=digest:
            staging=output/(file+'.tmp')
            if staging.exists() or staging.is_symlink():
                raise ValueError('Unowned forest copy staging')
            try:
                copy_file(source,staging)
                if sha(source)!=digest or sha(staging)!=digest:
                    raise ValueError('Forest source changed during assembly')
                staging.replace(target)
            finally:
                staging.unlink(missing_ok=True)
    atomic_json(output/'trees.json',trees)
    atomic_json(output/'library.json',dict(schema=1,complete=True,files=sorted(wanted-{'library.json'})))
    journal.unlink()
    retain_files(output,wanted)
    atomic_json(args.out/'forest/trees.json',trees)
    print('FOREST ASSEMBLY COMPLETE',len(trees),len(source_items),flush=True)


if __name__=='__main__':main()
