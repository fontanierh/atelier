"""Selected Zeppelin logical owner."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from zeppelin.parts import trail
from zeppelin.plan_asset import main

if __name__=="__main__":main('trail','ZP_Trail')
