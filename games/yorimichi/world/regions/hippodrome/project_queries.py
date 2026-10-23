"""Publish exact consumed final heights before selected Hippodrome construction."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import argparse
from atelier.atomic_files import atomic_json
from hippodrome import layout as L
from hidamari import layout as H
from hippodrome import skirt_data,lane_skirt_data
import numpy as np


def project(destination):
    """@cc [owner:fontanierh,label:correctness] hippodrome-projected-query-parity
    Publish precisely the original scalar final-surface calls and platform height. Query
    discovery MUST preserve each call's float coordinates; no interpolation or batching
    may alter the original sample evaluation. Missing projected reads MUST fail closed.
    """
    z=L.platform_height(H.north_height);points={}
    def record(x,y):
        key=float(x).hex()+','+float(y).hex()
        points[key]=float(H.north_height(np.array([x]),np.array([y]))[0])
        return points[key]
    for module in (skirt_data,lane_skirt_data):
        previous=module.ground;module.ground=record
        try:module.construct(z)
        finally:module.ground=previous
    atomic_json(destination,dict(schema=1,platform_z=z,ground=points))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);project(parser.parse_args().output)
