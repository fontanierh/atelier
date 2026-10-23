"""Bound a complete selected encoded mesh; no sibling construction."""
import argparse
import math
from atelier.gltf_partition import split
from encoded_region_plan import publish

def plan(key, output, construct):
    """@cc [owner:fontanierh,label:correctness] hippodrome-exact-selected-plan
    A selected asset MUST preserve its original encoded bytes when bounded; an oversized
    source MUST preserve all primitive data and placement while partitioning below 32768
    triangles. Construction MUST NOT read or write a sibling rendered export.
    """
    data,info=construct()
    if info['triangles']<=32768:parts=[dict(name=key,data=data,metadata=info)]
    else:
        lo,hi=info['min'],info['max']
        bounds=[math.floor(lo[i]/128)*128 for i in (0,1)]
        bounds += [max(bounds[i]+128,math.ceil(hi[i]/128)*128) for i in (0,1)]
        parts=[dict(name=key+'_Piece'+row['suffix'],data=row['data'],metadata=dict(
                   info,triangles=row['triangles'],min=list(row['bounds'][0]),max=list(row['bounds'][1]),
                   parent=key),assembly_metadata=dict(parent_bounds=[lo,hi])) for row in split(data,bounds)]
    return publish(output,parent=key,parts=parts)



def main(key, construct):
    parser=argparse.ArgumentParser();parser.add_argument("--output",required=True);parser.add_argument("--query")
    args=parser.parse_args()
    if args.query:
        from hippodrome.query_context import load
        load(args.query)
    plan(key,args.output,construct)
