"""Rebuild only the two water materials in place, without reimporting any mesh.

    UnrealEditor-Cmd Yorimichi.uproject -run=pythonscript \
        -script=Scripts/refresh_water_materials.py -unattended -nop4 -nosplash -stdout

Both builders create-or-load their asset by path, so every mesh that already references
M_ForestLakeWater or M_HarborWater picks up the new graph with no reassignment.
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
print('WATER MATERIALS OK', flush=True)
