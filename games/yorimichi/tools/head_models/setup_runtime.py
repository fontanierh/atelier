"""Install pinned isolated runtimes inside an outer aggregate guard."""
from pathlib import Path
import argparse
import os
import subprocess
import sys
import time

from support import SOURCES, verify_source

p = argparse.ArgumentParser()
p.add_argument('--root', type=Path, required=True)
p.add_argument('--backend', choices=['native', 'trellis'], required=True)
args = p.parse_args()
root = args.root.resolve()
root.mkdir(parents=True, exist_ok=True)
here = Path(__file__).resolve().parent
os.environ['MAX_JOBS'] = '2'
os.environ['CMAKE_BUILD_PARALLEL_LEVEL'] = '2'


def run(command):
    command = list(map(str, command))
    print('Setup:', ' '.join(command), flush=True)
    child = subprocess.Popen(command)
    start = time.monotonic()
    while True:
        try:
            code = child.wait(timeout=20)
            break
        except subprocess.TimeoutExpired:
            print(f'Setup command still active after {time.monotonic()-start:.0f}s', flush=True)
    if code:
        raise SystemExit(code)


names = ('pixal3d-mac', 'naf') if args.backend == 'native' else ('trellis2mlx',)
for name in names:
    url, commit = SOURCES[name]
    repo = root/name
    if not repo.exists():
        run(['git', 'init', repo])
        run(['git', '-C', repo, 'fetch', '--depth', '1', url, commit])
        run(['git', '-C', repo, 'checkout', '--detach', 'FETCH_HEAD'])
    if name == 'pixal3d-mac':
        diff = subprocess.check_output(['git', '-C', str(repo), 'diff', '--unified=0', 'HEAD'], text=True)
        if not diff:
            run(['git', '-C', repo, 'apply', '--unidiff-zero', '--check', here/'pixal-mps.patch'])
            run(['git', '-C', repo, 'apply', '--unidiff-zero', here/'pixal-mps.patch'])
verify_source(root, args.backend)
if args.backend == 'native':
    py = root/'pixal-venv/bin/python'
    eigen = subprocess.check_output(['brew', '--prefix', 'eigen'], text=True).strip()
    os.environ['CPLUS_INCLUDE_PATH'] = str(Path(eigen)/'include/eigen3')
    if not py.exists():
        run(['uv', 'venv', '--python', '3.10', py.parents[1]])
    packages = ['setuptools==80.9.0', 'wheel==0.45.1', 'ninja==1.13.2',
                'torch==2.12.0', 'torchvision==0.27.0', 'numpy==2.2.6', 'pillow==12.2.0',
                'transformers==5.9.0', 'timm==1.0.27', 'huggingface-hub==1.16.4',
                'safetensors==0.7.0', 'einops==0.8.2', 'easydict==1.13', 'scipy==1.15.3',
                'trimesh==4.10.1', 'opencv-python-headless==4.13.0.92', 'tqdm==4.67.3',
                'xatlas==0.0.11', 'plyfile==1.1.3', 'imageio==2.37.3', 'psutil==7.2.2',
                'matplotlib==3.10.9', 'kornia==0.8.2']
    run(['uv', 'pip', 'install', '--python', py, *packages])
    run(['uv', 'pip', 'install', '--python', py, '--no-build-isolation', 'natten==0.21.0'])
    for package in ['mtlmesh', 'mtlgemm', 'mtlbvh', 'mtldiffrast', 'o_voxel', 'natten-mps']:
        run(['uv', 'pip', 'install', '--python', py, '--no-deps', '--no-build-isolation',
             '-e', root/'pixal3d-mac/extern'/package])
    run([py, here/'build_voxelizer.py', '--root', root])
else:
    py = root/'mlx-venv/bin/python'
    if not py.exists():
        run(['uv', 'venv', '--python', '3.12', py.parents[1]])
    run(['uv', 'pip', 'install', '--python', py, '-r', here/'mlx-requirements.txt'])
    run(['uv', 'pip', 'install', '--python', py, '--no-deps', '-e', root/'trellis2mlx'])
    run([py, '-c', 'import mlx.core as mx; assert mx.metal.is_available(); print(mx.device_info())'])
with (root/(args.backend+'-packages.txt')).open('w') as out:
    subprocess.run(['uv', 'pip', 'freeze', '--python', str(py)], stdout=out, check=True)
