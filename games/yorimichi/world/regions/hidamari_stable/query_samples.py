"""Exact selected height queries; render constructors cannot rebuild the north surface."""
import base64
import hashlib
import json
import math

import numpy as np


def request(x, y, carved=True):
    x, y = np.broadcast_arrays(np.asarray(x, dtype='<f8'), np.asarray(y, dtype='<f8'))
    if type(carved) is not bool or not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError('Invalid Stable canonical query')
    return dict(shape=list(x.shape), x=base64.b64encode(x.tobytes()).decode(),
                y=base64.b64encode(y.tobytes()).decode(), carved=carved)


def identity(row):
    return hashlib.sha256(json.dumps(row, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class Recorder:
    def __init__(self, sample): self.sample, self.rows = sample, {}

    def __call__(self, x, y, *, carved=True):
        query = request(x, y, carved)
        result = self.sample(x, y, carved=carved)
        values = np.asarray(result, dtype='<f8')
        if list(values.shape) != query['shape'] or not np.isfinite(values).all():
            raise ValueError('Canonical Stable height result differs from requested frame')
        row = dict(query, values=base64.b64encode(values.tobytes()).decode())
        key = identity(query)
        if key in self.rows and self.rows[key] != row: raise ValueError('Same Stable query returned different source bits')
        self.rows[key] = row
        return result

    def value(self): return dict(schema=1, complete=True, queries=self.rows)


class Lookup:
    def __init__(self, table):
        if (table.get('schema') != 1 or table.get('complete') is not True
                or not isinstance(table.get('queries'), dict) or not table['queries']):
            raise ValueError('Incomplete selected Stable canonical height data')
        self.rows, self.used = {}, set()
        for key, row in table['queries'].items():
            if set(row) != {'shape', 'x', 'y', 'carved', 'values'}: raise ValueError('Unknown canonical query field')
            query = {name: row[name] for name in ('shape', 'x', 'y', 'carved')}
            if identity(query) != key or not isinstance(row['shape'], list): raise ValueError('Canonical query identity differs')
            if any(type(size) is not int or size <= 0 for size in row['shape']): raise ValueError('Invalid query dimensions')
            count = math.prod(row['shape'])
            if not 0 < count <= 1000000: raise ValueError('Unbounded selected canonical query')
            arrays = {}
            for name in ('x', 'y', 'values'):
                data = base64.b64decode(row[name], validate=True)
                if len(data) != count * 8: raise ValueError('Canonical query array width differs')
                arrays[name] = np.frombuffer(data, dtype='<f8').reshape(row['shape'])
                if not np.isfinite(arrays[name]).all(): raise ValueError('Nonfinite canonical height query')
            if request(arrays['x'], arrays['y'], row['carved']) != query: raise ValueError('Noncanonical query fields')
            self.rows[key] = arrays['values']

    def __call__(self, x, y, *, carved=True):
        key = identity(request(x, y, carved))
        if key not in self.rows: raise ValueError('Stable source requested undeclared canonical height data')
        self.used.add(key)
        return self.rows[key].copy()

    def complete(self):
        if self.used != set(self.rows): raise ValueError('Stale or unused Stable selected height queries')
