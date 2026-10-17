#!/usr/bin/env python3
"""Copy a validated Kiyo build into the committed character source and write its manifest."""
import hashlib
import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
BUILD = REPO / 'build' / 'yorimichi' / 'tide-reader'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    report = json.loads((BUILD / 'build.json').read_text())
    assert report['missing_core_bones'] == [], 'build is missing core humanoid bones'
    assert report['unweighted_count'] == 0, 'build contains unweighted vertices'
    assert not report['over_four_influences'], 'build exceeds four weights per vertex'
    source = BUILD / 'Kiyo-r01.blend'
    glb = BUILD / 'Kiyo-r01.glb'
    assert source.exists() and glb.exists(), 'run the headless Blender build with --export first'
    target_source = HERE / source.name
    target_glb = HERE / glb.name
    shutil.copy2(source, target_source)
    shutil.copy2(glb, target_glb)
    references = ['references/sheet.jpg', 'references/details.jpg', 'references/poses.jpg']
    manifest = {
        'native': target_source.name,
        'native_sha256': sha(target_source),
        'render_glb': target_glb.name,
        'render_glb_sha256': sha(target_glb),
        'height_cm': round(report['height_m'] * 100, 1),
        'floor_m': report['floor_m'],
        'axes': 'Z up, facing -Y, soles on the shared 6.5 mm game floor',
        'revision': 'r01',
        'rig': {
            'contract': 'humanoid',
            'core_bones': 23,
            'extras': ['hat', 'hair_bun', 'cape_L', 'cape_R', 'staff', 'tide_board', 'satchel'],
        },
        'geometry': {
            'vertices': report['vertices'],
            'polygons': report['polygons'],
            'triangles': report['triangles'],
        },
        'material': 'M_Kiyo_Palette: one opaque vertex-colour material',
        'weighting': {
            'unweighted_vertices': report['unweighted_count'],
            'max_influences': 4,
            'weight_sum_min': report['weight_sum_min'],
            'weight_sum_max': report['weight_sum_max'],
        },
        'references': references,
        'reference_sha256': {name: sha(HERE / name) for name in references},
        'reference_provenance': {
            'sheet': 'references/sheet.provenance.json',
            'details': 'references/details.provenance.json',
            'poses': 'references/poses.provenance.json',
        },
        'build_sources': {
            'kiyo_mesh.py': sha(HERE / 'kiyo_mesh.py'),
            'kiyo_rig.py': sha(HERE / 'kiyo_rig.py'),
            'build.py': sha(HERE / 'build.py'),
        },
        'build_report': 'build/yorimichi/tide-reader/build.json',
        'history': 'Kiyo r01: Sunburst turnaround, construction and attitude sheets, then procedural low-poly Blender geometry.',
    }
    (HERE / 'source-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({key: manifest[key] for key in ('native', 'native_sha256', 'render_glb', 'render_glb_sha256',
                                                     'height_cm', 'geometry')}, indent=2), flush=True)


if __name__ == '__main__':
    main()
