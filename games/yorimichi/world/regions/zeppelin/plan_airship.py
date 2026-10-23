"""Selected Zeppelin logical owner."""
import sys
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parents[2]),str(Path(__file__).resolve().parents[1])]
import yori  # noqa: E402,F401
from zeppelin.parts import ship
from zeppelin.plan_asset import main

if __name__=="__main__":main('ship','ZP_Airship')
