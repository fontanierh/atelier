"""Compile only the supplied-mesh CPU voxelizer; no unused octree/CUDA symbols."""
from pathlib import Path
import os
import subprocess
import sys
import argparse
from torch.utils.cpp_extension import load
p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
root=p.parse_args().root.resolve()
src=root/'pixal3d-mac/extern/o_voxel/src/convert'
build=root/'voxelizer-build'
build.mkdir(exist_ok=True)
os.environ['MAX_JOBS']='2'
os.environ['PATH']=str(Path(sys.executable).parent)+os.pathsep+os.environ['PATH']
eigen=Path(subprocess.check_output(['brew','--prefix','eigen'],text=True).strip())/'include/eigen3'
module=load(name='atelier_mesh_voxelizer',sources=[str(src/'flexible_dual_grid.cpp'),str(Path(__file__).with_name('voxelizer_entry.cpp'))],
    extra_include_paths=[str(src),str(eigen)],extra_cflags=['-O3','-std=c++17'],build_directory=str(build),verbose=True)
print('Real supplied-mesh voxelizer loaded:',module.__file__,flush=True)
