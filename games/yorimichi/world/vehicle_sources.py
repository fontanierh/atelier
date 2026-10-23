"""Publish selected original vehicle constructor code/data before bounded exports."""
import argparse
import ast
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
import yori  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import real_directory  # noqa: E402

FAMILIES={
    'sailboat':dict(material='SailboatPalette',builders={
        'SB_Hull':'hull','SB_Sail':'sail','SB_Boom':'boom','SB_Rudder':'rudder','SB_Wake':'wake'}),
    'kei':dict(material='KeiPalette',builders={
        'SM_Kei_Pickup':'pickup','SM_Kei_Wagon':'wagon','SM_Kei_Retro':'retro','SM_Kei_Microvan':'microvan'}),
}
SOURCE=yori.ASSETS/'vehicles'


def projection(text,family):
    """@cc [owner:fontanierh,label:correctness;performance] selected-vehicle-constructor-source
    Each logical vehicle source MUST contain its unchanged selected constructor, complete
    transitive primitive/constant dependencies and consumed construction data only.
    Compiling a source MUST NOT execute the monolithic entry or construct a sibling part.
    Unrelated part/constant edits MUST stop at unchanged selected products before export.
    """
    if family not in FAMILIES:raise ValueError('Unknown independently declared vehicle family')
    tree=ast.parse(text);nodes={};order=[]
    def bound(target):
        if isinstance(target,ast.Name):return {target.id}
        if isinstance(target,(ast.Tuple,ast.List)):return set().union(*(bound(value) for value in target.elts))
        return set()
    for node in tree.body:
        if isinstance(node,(ast.FunctionDef,ast.ClassDef)):
            nodes[node.name]=node;order.append(node)
        elif isinstance(node,ast.Assign):
            names=set().union(*(bound(target) for target in node.targets))
            for name in names:nodes[name]=node
            order.append(node)
    result={};roster=set(FAMILIES[family]['builders'].values())
    for key,builder in FAMILIES[family]['builders'].items():
        pending=[builder];selected=set()
        while pending:
            name=pending.pop()
            if name in selected or name not in nodes:continue
            selected.add(name)
            pending.extend(n.id for n in ast.walk(nodes[name]) if isinstance(n,ast.Name) and isinstance(n.ctx,ast.Load))
        if selected & roster!={builder}:raise ValueError('Vehicle constructor closure includes a sibling')
        chosen=[];seen=set()
        for node in order:
            if any(nodes[name] is node for name in selected) and id(node) not in seen:
                seen.add(id(node));chosen.append(node)
        if any(isinstance(node,ast.Assign) and any(isinstance(n,ast.Name) and n.id in ('OUT','ROOT') for n in ast.walk(node)) for node in chosen):
            raise ValueError('Selected vehicle source has ambient output dependencies')
        prefix='import math\nfrom mathutils import Matrix, Vector\nfrom village import mesh as v\n'
        program=prefix+'\n\n'.join(ast.unparse(node) for node in chosen)+'\n'
        result[key]=dict(schema=1,family=family,asset=key,builder=builder,program=program,
                         material=FAMILIES[family]['material'])
    return result


def publish(family,output):
    values=projection((SOURCE/family/'build.py').read_text(),family)
    output=real_directory(output,create=True);expected={key+'.json' for key in values}
    if any(path.is_symlink() or not path.is_file() or path.name not in expected for path in output.iterdir()):
        raise ValueError('Foreign vehicle source-data member')
    for key,value in values.items():atomic_json(output/(key+'.json'),value)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--family',choices=FAMILIES,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();publish(args.family,args.output)
