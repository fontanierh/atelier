"""Prepare one complete material/texture library without any geometry constructor."""
import argparse
import json
from pathlib import Path
import re
import sys
import tempfile

sys.path[:0]=[str(Path(__file__).resolve().parents[2]),str(Path(__file__).resolve().parents[1])]
import yori  # noqa: E402,F401
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import real_directory,sha  # noqa: E402
from atelier.model_files import regular_files  # noqa: E402
from atelier.file_copy import copy_file  # noqa: E402
from belmonte.scene_inputs import read  # noqa: E402
from belmonte.material_preparation import finish  # noqa: E402

JOURNAL='.material-transaction.json'


def filenames(value):
    if not isinstance(value,list) or len(set(value))!=len(value) or any(
            not isinstance(key,str) or not re.fullmatch(r'T_BM_[0-9a-f]{12}\.png',key) for key in value):
        raise ValueError('Foreign prepared texture names')
    return set(value)


def preflight(root):
    root=real_directory(root);old=set()
    if root.exists():
        for path in root.iterdir():
            if path.name=='textures':
                real_directory(path)
                if not path.is_dir():raise ValueError('Texture product root must be a directory')
            elif path.is_symlink() or not path.is_file() or path.name not in ('materials.json','inventory.json',JOURNAL):
                raise ValueError('Foreign prepared material output')
        if (root/'inventory.json').exists():
            prior=json.loads((root/'inventory.json').read_text())
            if (set(prior)!={'schema','owner','files','materials_sha256'} or type(prior['schema']) is not int or prior['schema']!=1
                    or prior['owner']!='BelmonteMaterials' or not isinstance(prior['files'],dict)):
                raise ValueError('Foreign prepared material ownership')
            old.update(filenames(list(prior['files'])))
        if (root/JOURNAL).exists():
            prior=json.loads((root/JOURNAL).read_text())
            if set(prior)!={'schema','owner','files'} or type(prior['schema']) is not int or prior['schema']!=1 or prior['owner']!='BelmonteMaterials':
                raise ValueError('Foreign material transaction')
            old.update(filenames(prior['files']))
        current=regular_files(root/'textures') if (root/'textures').exists() else set()
        if current-old or (root/'textures').exists() and any(p.is_dir() for p in (root/'textures').iterdir()):
            raise ValueError('Foreign generated textures')
        if (root/'materials.json').exists() and not (root/'inventory.json').exists() and not (root/JOURNAL).exists():
            raise ValueError('Unrecorded material output')
    return root,old


def prepare(inputs,root,*,assets,library):
    """@cc [owner:fontanierh,label:correctness] materials-before-file-assembly
    Material preparation MUST consume only its complete scene/material/image
    inputs and MUST NOT invoke geometry construction or mesh export. Preserve
    the existing palette, atlas/detail image processing and texture names.
    Preflight owned outputs before writes, stage complete images privately, and
    retire only known superseded files after complete current publication.
    """
    root,old=preflight(root);assets=real_directory(assets);library=real_directory(library)
    data=read(inputs,view='materials');root.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.belmonte-materials-',dir=root.parent) as temporary:
        work=Path(temporary);(work/'textures').mkdir()
        materials=finish(data,work,assets,library)
        expected={value['texture'] for value in materials.values() if value['texture']}
        filenames(list(expected))
        if regular_files(work/'textures')!=expected:raise ValueError('Prepared material texture inventory differs')
        identities={key:sha(work/'textures'/key) for key in expected}
        root.mkdir(parents=True,exist_ok=True);(root/'textures').mkdir(exist_ok=True)
        atomic_json(root/JOURNAL,dict(schema=1,owner='BelmonteMaterials',files=sorted(old|expected)))
        for key in sorted(expected):
            target=root/'textures'/key
            if not target.exists() or sha(target)!=identities[key]:
                pending=work/('.publish-'+key)
                if pending.exists() or pending.is_symlink():raise ValueError('Unresolved material staging file')
                try:
                    copy_file(work/'textures'/key,pending)
                    if sha(pending)!=identities[key]:raise ValueError('Prepared image changed while staging')
                    pending.replace(target)
                finally:pending.unlink(missing_ok=True)
        atomic_json(root/'materials.json',materials)
        atomic_json(root/'inventory.json',dict(schema=1,owner='BelmonteMaterials',files=identities,
                                              materials_sha256=sha(root/'materials.json')))
        for key in old-expected:(root/'textures'/key).unlink(missing_ok=True)
        (root/JOURNAL).unlink()
    validate(root)
    print('BELMONTE MATERIAL LIBRARY COMPLETE',len(materials),len(expected),flush=True)
    return materials


def validate(root):
    root,old=preflight(root)
    if (root/JOURNAL).exists():raise ValueError('Incomplete prepared material transaction')
    value=json.loads((root/'inventory.json').read_text());materials=json.loads((root/'materials.json').read_text())
    if (sha(root/'materials.json')!=value['materials_sha256'] or regular_files(root/'textures')!=old
            or {v['texture'] for v in materials.values() if v['texture']}!=old
            or any(sha(root/'textures'/key)!=wanted for key,wanted in value['files'].items())):
        raise ValueError('Prepared material bytes changed')
    return materials


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('input','output','assets','library'):parser.add_argument('--'+key,type=Path,required=True)
    args=parser.parse_args();prepare(args.input,args.output,assets=args.assets,library=args.library)
