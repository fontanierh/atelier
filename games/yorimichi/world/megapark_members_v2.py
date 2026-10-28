"""Project actual MegaPark generated membership and consume declared native audits."""
import ast
from collections import defaultdict
import hashlib
from itertools import product
import json
from pathlib import Path
import re
import shutil

import numpy as np

ROLES={'diffuse','decal','macrooverlay','lightmap','normal','detail','specular','transparent'}


def _json(path):
    def pairs(rows):
        value={}
        for key,item in rows:
            if key in value:raise ValueError('Duplicate MegaPark membership field')
            value[key]=item
        return value
    return json.loads(Path(path).read_bytes(),object_pairs_hook=pairs,parse_constant=lambda value:(_ for _ in ()).throw(ValueError('Nonfinite MegaPark metadata')))


def project(build=None,restyle=None,source=None,output=None,kind=None,expected_restyle=()):
    """@cc [owner:fontanierh,label:correctness] actual-megapark-generated-members
    Membership MUST come from the complete declared build/restyle ROOTs and
    committed map. Original source/restyled PNG checksums MUST validate before
    any output. Emit only actual per-MI specs/lightmap value or per-tid roles;
    no speculative member, generated scan, original main or native work MAY run.
    """
    report=_json(build);paint=_json(restyle/'textures.json');catalogue=_json(source)
    if hashlib.sha256(source.read_bytes()).hexdigest()!=report['source_sha256'] or report['textures']!=catalogue['textures']:
        raise ValueError('MegaPark generated texture catalogue differs from committed source')
    if set(paint['textures'])!=set(expected_restyle) or set(paint['textures'])-set(catalogue['textures']):raise ValueError('MegaPark restyle membership differs from committed finish declarations')
    for tid,info in catalogue['textures'].items():
        path=source.parent/info['png']
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=info['sha256']:raise ValueError('Changed committed MegaPark texture: '+tid)
    for tid,info in paint['textures'].items():
        path=restyle/info['png']
        if path.resolve()!=path or not path.is_relative_to(restyle) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=info['sha256']:raise ValueError('Changed restyled MegaPark texture: '+tid)
    roles={tid:set() for tid in catalogue['textures']};members={}
    if not isinstance(report['materials'],dict) or not report['materials']:raise ValueError('MegaPark generated material roster is empty')
    for key,p in report['materials'].items():
        channels=p.get('retail_texture_ids',{});alpha=p.get('alpha_mode',0)
        if (not isinstance(key,str) or not re.fullmatch('0x[A-Za-z0-9_]+',key) or type(alpha) is not int or alpha not in (0,1,2)
                or not isinstance(channels,dict) or set(channels)-ROLES or set(channels.values())-set(roles)):
            raise ValueError('Invalid actual MegaPark material member: '+str(key))
        norm=paint['lightmaps'].get(channels.get('lightmap'),3.)
        if type(norm) not in (int,float) or not np.isfinite(norm):raise ValueError('Invalid actual MegaPark lightmap level')
        members['MI_'+key[2:]]={'key':key,'material':p,'lightmap_norm':norm}
        for role,tid in channels.items():roles[tid].add(role)
    values=members if kind=='materials' else {'T_'+tid[2:]:{'tid':tid,'roles':sorted(value)} for tid,value in roles.items()} if kind=='roles' else None
    if values is None:raise ValueError('Unknown MegaPark projection kind')
    encoded={name:json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n' for name,value in values.items()}
    if len({name.casefold() for name in encoded})!=len(encoded):raise ValueError('Aliased MegaPark generated member names')
    if output.exists():raise ValueError('MegaPark member output must be fresh')
    output.mkdir(parents=True)
    for name,raw in encoded.items():(output/(name+'.json')).write_text(raw)


def copy_member(source=None,destination=None):
    """Package exactly the engine-selected spec for its independent native author follower."""
    if source.is_symlink() or not source.is_file() or destination.exists():raise ValueError('MegaPark selected spec must be fresh and regular')
    value=_json(source)
    if source.name!='MI_'+value['key'][2:]+'.json':raise ValueError('MegaPark selected spec name differs')
    destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,destination)


def audit(build=None,letters=None,source=None,output=None,dumps=(),reports=(),materials=(),verifier=None,level=None):
    """@cc [owner:fontanierh,label:correctness] consumed-megapark-native-audit
    The exact complete declared native dump/report/material roster MUST precede
    the original triangle verifier. Reports MUST derive from actual dump bytes
    and actual native per-piece reports. Original keyed
    verifier functions and committed source/letters MUST run in a bounded namespace;
    no ambient receiving report, generated scan or fabricated native dump MAY pass.
    """
    from megapark import cars,placement,plants,sign
    primary=level/'content/Game/MegaPark/Maps/SuperUltraMegaPark.umap'
    if primary.resolve()!=primary or not primary.is_file():raise ValueError('MegaPark audit requires the actual completed native level Item')
    report=_json(build);catalogue=_json(source);entries=report['render']+report['collision']+report['seam']
    names={entry['name'] for entry in entries}
    if len(names)!=len(entries) or hashlib.sha256(source.read_bytes()).hexdigest()!=report['source_sha256']:raise ValueError('MegaPark audit source/membership differs')
    def roster(values):
        result={piece:child.products[0].paths[0] for child,piece in values}
        if len(result)!=len(values):raise ValueError('Duplicate MegaPark audit member')
        return result
    geometry=roster(dumps);receipts=roster(reports);mis=roster(materials)
    if set(geometry)!=names or set(receipts)!=names or set(mis)!={'MI_'+key[2:] for key in report['materials']}:raise ValueError('Incomplete actual MegaPark native audit roster')
    target=output/'imported-geometry';target.mkdir(parents=True,exist_ok=False);results=[];seams={e['name'] for e in report['seam']}
    for entry in entries:
        key=entry['name'];path=geometry[key]/'data/imported-geometry'/(key+'.bin')
        if path.resolve()!=path or not path.is_file() or path.stat().st_size!=entry['triangles']*9*8:raise ValueError('Missing actual MegaPark triangle dump: '+key)
        data=np.fromfile(path,dtype='<f8').reshape(-1,3,3)
        if not np.isfinite(data).all():raise ValueError('Nonfinite actual MegaPark triangle dump')
        shutil.copyfile(path,target/(key+'.bin'));observed=_json(receipts[key]/'data/imported-reports'/(key+'.json'))
        if (set(observed)!={'name','triangles','bounds_error_cm','uv_channels','collision','placed'} or observed['name']!=key
                or observed['triangles']!=entry['triangles'] or not 0<=observed['bounds_error_cm']<.05
                or type(observed['uv_channels']) is not int or observed['uv_channels']<0
                or observed['collision']!=key.startswith('UC_') or observed['placed']!=(key not in seams)):
            raise ValueError('MegaPark actual native report differs from current source')
        results.append(observed)
    scope={'np':np,'json':json,'defaultdict':defaultdict,'product':product,'Path':Path,'SOURCE':source.parent,'OUT':output,
        'cars':cars,'placement':placement,'plants':plants,'sign':sign}
    tree=ast.parse(verifier.read_bytes(),str(verifier));wanted={'whole_expected_triangles','expected_triangles','letters','compare','main'}
    nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in wanted or isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='TOLERANCE' for t in n.targets)]
    if {n.name for n in nodes if isinstance(n,ast.FunctionDef)}!=wanted:raise ValueError('Original MegaPark verifier definitions differ')
    # These two inputs already reside at output/build.json and output/letters.npz in
    # the protected recipe view; only the three declared audit siblings are writable.
    if build!=output/'build.json' or letters!=output/'letters.npz':raise ValueError('MegaPark verifier source inputs must bind to its declared view paths')
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(verifier),'exec'),scope);scope['main']()
    result={'retired':[],'level':'/Game/MegaPark/Maps/SuperUltraMegaPark','source_sha256':report['source_sha256'],'meshes':results,
        'textures':len(report['textures']),'materials':len(mis),'rails':len(report['rails']),
        'render_triangles':sum(e['triangles'] for e in results if not e['collision']),'collision_triangles':sum(e['triangles'] for e in results if e['collision'])}
    (output/'import-report.json').write_text(json.dumps(result,indent=2)+'\n')
