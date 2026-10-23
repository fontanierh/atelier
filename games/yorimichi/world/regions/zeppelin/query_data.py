"""Complete selected final terrain values, keyed by original float coordinates."""
import json
from pathlib import Path


def key(x,y):return float(x).hex()+','+float(y).hex()

class Queries:
    def __init__(self,path):
        self.value=json.loads(Path(path).read_text())
        if self.value.get('schema')!=1:raise ValueError('Invalid Zeppelin queries')
    def ground(self,x,y):
        name=key(x,y)
        if name not in self.value['ground']:raise ValueError('Unprojected Zeppelin ground sample')
        return self.value['ground'][name]
