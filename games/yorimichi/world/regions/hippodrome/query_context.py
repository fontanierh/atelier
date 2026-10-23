"""Strict projected final terrain reads; never open a sibling mesh export."""
import json
from pathlib import Path

_VALUE=None

def load(path):
    global _VALUE
    value=json.loads(Path(path).read_text())
    if value.get('schema')!=1:raise ValueError('Invalid Hippodrome terrain projection')
    _VALUE=value

def height():
    if _VALUE is None:raise ValueError('Hippodrome height projection required')
    return _VALUE['platform_z']

def ground(x,y):
    if _VALUE is None:raise ValueError('Hippodrome ground projection required')
    key=float(x).hex()+','+float(y).hex()
    if key not in _VALUE['ground']:raise ValueError('Unprojected Hippodrome ground sample')
    return _VALUE['ground'][key]
