"""Publish exact consumed final heights before selected Hippodrome construction."""
import sys
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parents[i]) for i in (2,1)]
import argparse
from atelier.atomic_files import atomic_json
from hippodrome import layout as L
from hidamari import layout as H
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
    x0,y0,x1,y1=L.PLATFORM
    ring=[(x,y0) for x in np.arange(x0,x1,1.)]+[(x1,y) for y in np.arange(y0,y1,1.)]+[(x,y1) for x in np.arange(x1,x0,-1.)]+[(x0,y) for y in np.arange(y1,y0,-1.)]
    def out(x,y):
        dx=L.SKIRT if x>=x1-1e-6 else -L.SKIRT if x<=x0+1e-6 else 0.
        dy=L.SKIRT if y>=y1-1e-6 else -L.SKIRT if y<=y0+1e-6 else 0.
        return x+dx,y+dy
    for (ax,ay),(bx,by) in zip(ring,ring[1:]+ring[:1]):
        if ay<=y0+1e-6 and by<=y0+1e-6 and abs((ax+bx)/2-L.LANE[0][0])<L.LANE_WIDTH/2:continue
        record(*out(ax,ay));record(*out(bx,by))
    (lx,ya),(_,yb)=L.LANE;ys=np.linspace(ya,yb,int(yb-ya)+1)
    for k in range(int(yb-ya)):
        for side in (-1,1):
            x=lx+side*(L.LANE_WIDTH/2)
            record(x+side*1.5,ys[k]);record(x+side*1.5,ys[k+1])
    atomic_json(Path(destination),dict(schema=1,platform_z=z,ground=points))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);project(parser.parse_args().output)
