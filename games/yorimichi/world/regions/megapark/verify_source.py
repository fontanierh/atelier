"""Verify the converted park against the independently decoded original cache.

Geometry/UV/normal words and PNG pixels must be unchanged. Collision is checked
against the existing runtime's corrected reader, including every float word,
surface, group, feature edge, and one-sided flag. All evidence stays in build.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct
import subprocess
import sys

import numpy as np
from PIL import Image


def verify(cache, upstream, source, output, oracle_source):
    output.mkdir(parents=True, exist_ok=True)
    original = json.loads((cache / 'manifest.json').read_text())
    native = json.loads((source / 'map.json').read_text())
    by_id = {entry['asset_id']: entry for entry in original['models']}
    words = 0
    for model in native['models']:
        with np.load(source / model['npz'], allow_pickle=False) as converted, np.load(cache / by_id[model['asset_id']]['npz'], allow_pickle=False) as reference:
            assert set(converted.files) == set(reference.files), model['asset_id']
            for key in reference.files:
                a, b = converted[key], reference[key]
                assert a.dtype == b.dtype and a.shape == b.shape and a.tobytes() == b.tobytes(), (model['asset_id'], key)
                words += a.size
    # Every source model using an authored Mega Park material must be present,
    # including adjoining source chunks extending beyond the nominal rectangle.
    authored = {model['asset_id'] for model in original['models']
                if any('_MP' in part['name'] or '_MP' in (part.get('material_name') or '') for part in model['meshes'])}
    assert authored <= {model['asset_id'] for model in native['models']}
    for tid, entry in native['textures'].items():
        reference = original['textures'][tid]
        image = Image.open(source / entry['png']).convert('RGBA')
        assert image.size == (reference['width'], reference['height'])
        assert image.tobytes() == (cache / reference['rgba']).read_bytes(), tid
    sys.path.insert(0, str(upstream / 'tools/vendor/university/tools/vanilla_map_extraction/tools'))
    from build_retail_collision_archive import collision_sections
    assets = {entry['asset_id']: entry for entry in original['simulation_assets']}
    archive = bytearray(b'RWCMSET1' + struct.pack('<I', len(native['collision'])))
    expected = bytearray()
    for entry in native['collision']:
        sections = collision_sections((cache / assets[entry['asset_id']]['rx2']).read_bytes())
        raw = sections[entry['section_index']]
        name = entry['id'].encode()
        archive.extend(struct.pack('<I', len(name)) + name + struct.pack('<I', len(raw)) + raw)
        with np.load(source / entry['npz'], allow_pickle=False) as data:
            for i, points in enumerate(data['triangles']):
                edge = data['edge_codes'][i]
                present = int(edge[0] >= 0)
                codes = edge if present else (0,0,0)
                expected.extend(struct.pack('<9fHH3BBB', *points.ravel(), int(data['surface'][i]), int(data['group'][i]),
                    *codes, present, int(data['one_sided'])))
    (output / 'original-collision.rwcmset').write_bytes(archive)
    # The oracle uses unmodified reader source; it never reads native arrays.
    rust = '''#[path = ORACLE] mod retail;
use std::{env,fs,io::{BufWriter,Write}};
fn main() {
 let args: Vec<_> = env::args().collect();
 let bytes = fs::read(&args[1]).unwrap();
 let mut out = BufWriter::new(fs::File::create(&args[2]).unwrap());
 let count = retail::visit_clusters(&bytes, |_, triangles| {
  for t in triangles {
   for p in t.points { for v in p { out.write_all(&v.to_bits().to_le_bytes()).unwrap(); } }
   out.write_all(&t.surface.to_le_bytes()).unwrap(); out.write_all(&t.group.to_le_bytes()).unwrap();
   out.write_all(&t.edges.unwrap_or([0;3])).unwrap();
   out.write_all(&[u8::from(t.edges.is_some()),u8::from(t.one_sided)]).unwrap();
  }
  Ok(())
 }).unwrap();
 out.flush().unwrap(); println!("{} original triangles decoded", count);
}'''.replace('ORACLE', json.dumps(str(oracle_source.resolve())))
    (output / 'collision_oracle.rs').write_text(rust)
    binary = output / 'collision-oracle'
    subprocess.run(['rustc', '+1.97.1', '--edition=2024', '-O', str(output / 'collision_oracle.rs'), '-o', str(binary)], check=True)
    actual = output / 'oracle-collision.bin'
    subprocess.run([str(binary.resolve()), str((output / 'original-collision.rwcmset').resolve()), str(actual.resolve())], check=True)
    assert actual.read_bytes() == expected, 'Original collision and native geometry differ'
    report = {'status': 'passed', 'source_array_elements': words, 'authored_park_models_covered': len(authored),
        'textures': len(native['textures']), 'collision_triangles': len(expected)//45,
        'collision_sha256': hashlib.sha256(expected).hexdigest(), 'oracle_source_sha256': hashlib.sha256(oracle_source.read_bytes()).hexdigest()}
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('cache', 'upstream', 'source', 'output', 'oracle-source'):
        parser.add_argument('--'+key, type=Path, required=True)
    args = parser.parse_args()
    verify(args.cache, args.upstream, args.source, args.output, args.oracle_source)
