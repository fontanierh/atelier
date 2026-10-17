"""Download selected pinned public weights, verifying every file before reuse."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from pathlib import Path
from urllib.request import urlopen
import argparse
import hashlib
import json
import os
import time

os.environ['HF_XET_NUM_CONCURRENT_RANGE_GETS'] = '4'
os.environ['HF_HUB_DISABLE_PROGRESS_BARS'] = '1'
from huggingface_hub import hf_hub_download

p = argparse.ArgumentParser()
p.add_argument('--root', type=Path, required=True)
p.add_argument('--backend', choices=['native', 'trellis'], required=True)
args = p.parse_args()
root = args.root.resolve()
here = Path(__file__).resolve().parent
records = json.loads((here/(args.backend+'-weights.json')).read_text())
if args.backend == 'trellis':
    records += [r for r in json.loads((here/'native-weights.json').read_text())
                if r['file'] == 'model.safetensors' or r['file'].startswith('ckpts/tex_dec_')]
receipt = root/(('trellis' if args.backend == 'trellis' else 'native')+'-downloads.json')
verified = []
start = time.monotonic()
for record in records:
    dest = root/'models'/record['repo']/record['file']
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        print('Downloading pinned artifact:', record['repo'], record['file'], flush=True)
        if record['repo'] == 'valeoai/NAF':
            # A small pinned release asset; the expected size/hash are in the manifest.
            url = 'https://github.com/valeoai/NAF/releases/download/model/naf_release.pth'
            with urlopen(url, timeout=60) as response:
                data = response.read(record['size_bytes']+1)
            if len(data) != record['size_bytes'] or hashlib.sha256(data).hexdigest() != record['sha256']:
                raise ValueError('NAF release differs from the pinned artifact')
            part = dest.with_name(dest.name+'.verified-part')
            with part.open('xb') as out:
                out.write(data)
            part.replace(dest)
        else:
            with ThreadPoolExecutor(max_workers=1) as pool:
                task = pool.submit(hf_hub_download, repo_id=record['repo'], filename=record['file'],
                                   revision=record['revision'], local_dir=str(root/'models'/record['repo']))
                while True:
                    try:
                        downloaded = task.result(timeout=20)
                        break
                    except FutureTimeout:
                        print(f'Artifact transfer pending: {record["file"]}; elapsed {time.monotonic()-start:.0f}s', flush=True)
            if Path(downloaded).resolve() != dest:
                raise ValueError('Unexpected artifact destination')
    h = hashlib.sha256()
    with dest.open('rb') as source:
        for block in iter(lambda: source.read(4*1024*1024), b''):
            h.update(block)
    if dest.stat().st_size != record['size_bytes'] or h.hexdigest() != record['sha256']:
        raise ValueError('Pinned artifact mismatch: '+record['file'])
    verified.append(record)
    temporary = receipt.with_suffix('.tmp')
    temporary.write_text(json.dumps(verified, indent=2)+'\n')
    temporary.replace(receipt)
    print('Verified:', record['file'], flush=True)
