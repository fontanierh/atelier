"""One explicit switch selects the design-driven park throughout the build."""
import hashlib
from functools import lru_cache
import json
import math
import os
from pathlib import Path

SWITCH = 'ATELIER_CRATERPARK_V4_DESIGN'
# The owner's editor document (craterpark-editor/1 park.json) selects the editor park instead: the same downstream
# contract (geometry.npz, placement, terrain stamp), compiled by editor_generate.py from the editor's own geometry.
EDITOR_SWITCH = 'ATELIER_CRATERPARK_EDITOR_PARK'
EDITOR_SCHEMA = 'craterpark-editor/1'
# With neither switch set the build ships the editor park the owner last approved (its terrain in data/ beside it);
# EDITOR_SWITCH=off builds the old park instead
SHIPPED = Path(__file__).resolve().parents[4] / 'tools' / 'craterpark_editor' / 'shipped.json'
SHIPPED_LINES = 'L1,L2,p5'


def editor_path():
    value = os.environ.get(EDITOR_SWITCH, '').strip()
    if value.lower() == 'off':
        return None
    if value:
        return Path(value).expanduser().resolve()
    return None if os.environ.get(SWITCH, '').strip() else SHIPPED


def editor_lines():
    """The lines (and single pieces) the editor park ships: ATELIER_CRATERPARK_EDITOR_LINES, or the shipped park's."""
    return os.environ.get('ATELIER_CRATERPARK_EDITOR_LINES', '').strip() or SHIPPED_LINES


def editor():
    return editor_path() is not None


def design_path():
    if editor():
        return editor_path()
    value = os.environ.get(SWITCH, '').strip()
    return Path(value).expanduser().resolve() if value else None


def editor_document(doc):
    """What v4 placement reads, for an editor park: the shared 680 m frame, no caldera dig override, and the
    editor's terrain grid as the site (the park may use the whole grid)."""
    return {'frame': {'lift': 680.}, 'ground': {}, 'editor': True, 'site': {}}


def selected():
    return design_path() is not None


def load_document(path=None):
    """Read the selected JSON object, without executing referenced Python helpers."""
    path = Path(path) if path is not None else design_path()
    if path is None:
        raise ValueError(f'{SWITCH} must select a design')
    document = json.loads(path.read_text())
    if not isinstance(document, dict):
        raise ValueError('v4 design must be a JSON object')
    if document.get('schema') == EDITOR_SCHEMA:
        return editor_document(document)
    return document


def placement_document():
    """The selected document in the established placement frame, without geometry imports."""
    doc = load_document()
    if float(doc.get('frame', {}).get('lift', 680.)) != 680.:
        raise ValueError('v4 frame.lift must match the established 680 m coordinate frame')
    return doc


def caldera_depth(default=45., *, document=None):
    """The natural ground's selected depth, independent of placement mesh loading."""
    doc = placement_document() if document is None else document
    dig = doc.get('ground', {}).get('dig')
    if not dig:
        return default
    if dig.get('kind') != 'depth':
        raise ValueError('v4 world terrain currently requires ground.dig.kind=depth')
    value = float(dig['DEPTH'])
    if not math.isfinite(value) or value <= 0:
        raise ValueError('v4 caldera DEPTH must be finite and positive')
    return value


def input_paths(path=None):
    """@cc [owner:fontanierh] v4-design-inputs
    All data files the design loader may read MUST be recipe fingerprints.
    Selected design and referenced data MUST exist; missing data never selects the old park.
    """
    path = Path(path).resolve() if path is not None else design_path()
    if path is None:
        return []
    document = json.loads(path.read_text())
    if not isinstance(document, dict):
        raise ValueError(f'{path}: a Crater Park design must be a JSON object')
    if document.get('schema') == EDITOR_SCHEMA:
        # the editor park and the terrain it was drawn on (data/ beside it)
        data = path.parent / 'data'
        meta = json.loads((data / 'terrain.json').read_text())
        files = [data / 'terrain.json'] + [data / name for name in (*meta['inner']['layers'].values(), meta['outer']['file'])]
        for file in files:
            if not file.is_file():
                raise ValueError(f'editor park input missing: {file.name}')
        return [path, *files]
    document = load_document(path)
    paths = [path]
    refs = [document.get('elements_file'), document.get('ground', {}).get('heightmap')]
    site = document.get('site', {})
    site_ref = site.get('file')
    for preferred in site.get('prefer', []):
        candidate = Path(preferred).expanduser()
        candidate = candidate if candidate.is_absolute() else path.parent / candidate
        if candidate.is_file():
            site_ref = preferred
            break
    refs += [site_ref, site.get('block_file')]
    for ref in refs:
        if not ref:
            continue
        candidate = Path(ref).expanduser()
        candidate = candidate if candidate.is_absolute() else path.parent / candidate
        candidate = candidate.resolve()
        if not candidate.is_file():
            raise ValueError(f'v4 design input missing: {candidate.name}')
        paths.append(candidate)
    return list(dict.fromkeys(paths))


@lru_cache(maxsize=256)
def _file_sha(path, mtime_ns, size, ctime_ns):
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    after = Path(path).stat()
    if (after.st_mtime_ns, after.st_size, after.st_ctime_ns) != (mtime_ns, size, ctime_ns):
        raise ValueError('v4 input changed while hashing; retry with stable inputs')
    return digest


def file_sha(path):
    path = Path(path).resolve()
    stat = path.stat()
    return _file_sha(str(path), stat.st_mtime_ns, stat.st_size, stat.st_ctime_ns)


def provenance(path=None):
    """Portable names plus byte hashes; no machine paths in generated reports."""
    paths = input_paths(path)
    if not paths:
        raise ValueError('no v4 design selected')
    entries = [{'name': os.path.relpath(p, paths[0].parent),
                'sha256': file_sha(p)} for p in paths]
    digest = hashlib.sha256(json.dumps(entries, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {'schema': 4, 'design_sha256': entries[0]['sha256'], 'source_sha256': digest, 'inputs': entries,
            'depth': load_document(paths[0]).get('ground', {}).get('dig', {}).get('DEPTH')}
