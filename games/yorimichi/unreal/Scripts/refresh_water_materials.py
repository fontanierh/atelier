"""Rebuild only the water materials (the forest lake, the harbour and the open sea) in place, without reimporting any
mesh.

    UnrealEditor-Cmd Yorimichi.uproject -run=pythonscript \
        -script=Scripts/refresh_water_materials.py -unattended -nop4 -nosplash -stdout

Every builder creates or loads its asset by path, so every mesh that already references
M_ForestLakeWater, M_HarborWater or M_Sea picks up the new graph with no reassignment. M_HarborWater and M_Sea share
sea_look.py, so they are rebuilt together.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402  (build/yorimichi = yori.OUT)
import runpy, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

runpy.run_path(str(HERE/'forest_lake_material.py'))['create']()
print('REFRESHED M_ForestLakeWater', flush=True)

from harbor_material import material as harbor_material
harbor_material(water=True)
print('REFRESHED M_HarborWater', flush=True)

from import_southwest import sea_material
sea_material()
print('REFRESHED M_Sea', flush=True)
print('WATER MATERIALS OK', flush=True)
