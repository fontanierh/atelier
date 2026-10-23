"""Partition one canonical final surface into independent bounded render data."""
import argparse
from pathlib import Path
import sys

sys.path[:0]=[str(Path(__file__).resolve().parents[2]),str(Path(__file__).resolve().parents[1])]
import yori  # noqa: E402,F401
from belmonte.surface_data import read  # noqa: E402
from belmonte.ground_pieces import planned  # noqa: E402
from belmonte.atomic_metadata import metadata  # noqa: E402
from encoded_region_plan import publish  # noqa: E402


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset',required=True)
    parser.add_argument('--surface',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args(argv)
    entry,data=read(args.surface,owner=args.asset)
    _,rows=planned(entry,data)
    result=publish(args.output,parent=args.asset,parts=[
        dict(name=row['name'],data=payload,**metadata(row,slots,collides))
        for row,slots,collides,payload in rows])
    print('BELMONTE GROUND DATA COMPLETE',args.asset,len(rows),entry['triangles'],flush=True)
    return result


if __name__=='__main__':main()
