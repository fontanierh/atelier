"""Construct only the authored northern country, independent of apron interiors."""
from pathlib import Path
import sys

sys.path[:0]=[str(Path(__file__).resolve().parents[2]),str(Path(__file__).resolve().parents[1])]
import yori  # noqa: E402,F401
from belmonte.north_pipeline import raw  # noqa: E402
from belmonte.terrain import country  # noqa: E402

if __name__=='__main__':raw('SM_BM_NorthCountry',country)
