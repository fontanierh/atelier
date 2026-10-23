"""Complete atomic Stable receiver; production enable policy stays explicit."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from import_stable_atomic import main

if __name__ == '__main__': main()
