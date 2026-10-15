"""Small action-side API for frozen, graph-resolved spatial inputs. No engine or build imports."""
from dataclasses import dataclass
import json
import os
from pathlib import Path


@dataclass(frozen=True)
class SpatialInput:
    name: str
    bounds: tuple[float, ...]
    paths: tuple[Path, ...]


def query(name: str) -> tuple[SpatialInput, ...]:
    """Return this action's declared query results. Arbitrary runtime queries are not supported."""
    manifest = json.loads(Path(os.environ['ATELIER_ACTION_INPUTS']).read_text())
    if manifest['schema'] != 1 or manifest['intersection'] != 'inclusive':
        raise ValueError('Unsupported action input manifest')
    return tuple(SpatialInput(p['name'], tuple(p['bounds']), tuple(map(Path, p['paths'])))
                 for p in manifest['queries'][name]['matches'])
