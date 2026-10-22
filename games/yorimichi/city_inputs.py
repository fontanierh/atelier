"""The city LOD/tile generators consume six meshes, not every Hidamari export."""
import hashlib
import json
from pathlib import Path

TILES = ('HD_Terrain', 'HD_Streets', 'HD_Square')
TREES = ('HD_ArcadeTree', 'HD_PlazaTreeGold', 'HD_PlazaTreeOrange')


def paths(out, names):
    """Explicit membership for the selected city generator's real file reads."""
    root = Path(out) / 'hidamari'
    return [root / 'manifest.json', *(root / 'assets' / (name + '.fbx') for name in names)]


def snapshot(out, names):
    """@cc [owner:fontanierh,label:correctness] city-generator-consumed-inputs
    The cutoff MUST cover each selected mesh's triangles/min/max, consumed collision count and exact FBX bytes, including raw
    hashes emitted by the generators. Missing selected data MUST refuse, never preserve a cache hit.
    Unselected manifest entries and unused fields MUST NOT invalidate the selected generator.
    Generator code and transitive helpers MUST remain separate recipe inputs.
    """
    manifest_path, *meshes = paths(out, names)
    manifest = json.loads(manifest_path.read_text())
    result = {}
    for name, mesh in zip(names, meshes):
        entry = manifest[name]
        fields = ('triangles', 'min', 'max', 'collision_boxes') if name in TILES else ('triangles', 'min', 'max')
        result[name] = {'receipt': {key: entry[key] for key in fields},
                        'fbx': hashlib.sha256(mesh.read_bytes()).hexdigest()}
    return result
