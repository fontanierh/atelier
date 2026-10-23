"""@cc [owner:fontanierh,label:correctness] embedded-evidence-io-boundary
Embedded emitters MUST use the same exact artifact/hash/finite-value gates as host
verification without importing host geometry or Git authority code. Geometry
comparison and immutable Git authority MUST remain host-only.
"""
import hashlib
import json
import math
from pathlib import Path
import re

from atelier.export_manifest import real_directory

HEX = re.compile(r'[0-9a-f]{64}')
MAX_ARTIFACT_BYTES = 512 * 1024 * 1024


class EvidenceError(ValueError):
    pass

def require(condition, message):
    if not condition: raise EvidenceError(message)

def finite(value):
    if isinstance(value, bool): return True
    if isinstance(value, (int,float)): return math.isfinite(value)
    if isinstance(value, str) or value is None: return True
    if isinstance(value,(list,tuple)): return all(finite(v) for v in value)
    if isinstance(value,dict): return all(isinstance(k,str) and finite(v) for k,v in value.items())
    return False

def canonical(value):
    require(finite(value), 'Nonfinite or unsupported canonical evidence value')
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()

def artifact(row):
    require(isinstance(row,dict) and set(row)=={'path','sha256'} and isinstance(row['path'],str)
            and isinstance(row['sha256'],str) and HEX.fullmatch(row['sha256']), 'Invalid artifact identity')
    path=Path(row['path'])
    require(path.is_absolute(), 'Artifact paths must be absolute')
    real_directory(path.parent)
    require(not path.is_symlink() and path.is_file() and 0<path.stat().st_size<=MAX_ARTIFACT_BYTES,
            'Missing, linked, empty or oversized artifact: '+str(path))
    payload=path.read_bytes()
    require(hashlib.sha256(payload).hexdigest()==row['sha256'], 'Artifact bytes differ: '+str(path))
    return payload
