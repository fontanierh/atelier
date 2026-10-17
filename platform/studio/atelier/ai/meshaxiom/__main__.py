"""Run sequential Apple Silicon stages; invoke this command through atelier.safety.guarded."""
import argparse
import json
from pathlib import Path
import subprocess
import sys


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--image',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--face-budget',type=int,default=2000)
    parser.add_argument('--steps',type=int,default=20)
    parser.add_argument('--max-nodes',type=int,default=8192)
    parser.add_argument('--stage',choices=['all','vertex','topology'],default='all')
    args=parser.parse_args()
    if not 1<=args.face_budget<=16000 or not 1<=args.steps<=40 or not 1<=args.max_nodes<=26000:
        parser.error('face budget must be 1–16000, steps 1–40, max nodes 1–26000')
    args.output.mkdir(parents=True,exist_ok=True)
    for stage in (['vertex','topology'] if args.stage=='all' else [args.stage]):
        subprocess.run([sys.executable,'-u','-m','atelier.ai.meshaxiom.worker','--stage',stage,
            '--root',str(args.root.resolve()),'--image',str(args.image.resolve()),'--output',str(args.output.resolve()),
            '--face-budget',str(args.face_budget),'--steps',str(args.steps),'--max-nodes',str(args.max_nodes)],check=True)
    if args.stage in ('all','topology'):
        if not (args.output/'mesh.glb').is_file():raise RuntimeError('Generation did not produce a GLB')
        print(json.dumps({'status':'complete','mesh':str(args.output/'mesh.glb')}),flush=True)

if __name__=='__main__':main()
