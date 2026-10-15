"""world.crater_cloud: write craterpark/cloud.json, Crater Park's lenticular cap cloud (cloud.py), for ACraterCloud."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import yori  # noqa: E402
from craterpark import cloud  # noqa: E402

if __name__ == '__main__':
    path = cloud.write(yori.OUT / 'craterpark' / 'cloud.json')
    record = cloud.record()
    print(f"CRATER CLOUD {len(record['layers'])} shells, "
          f"{sum(len(layer['triangles']) // 3 for layer in record['layers'])} triangles -> {path}", flush=True)
