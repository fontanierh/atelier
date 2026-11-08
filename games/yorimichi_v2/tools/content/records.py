"""Asset, region and verification records: the one description of what each V2 asset is and who writes it.

An asset record (`assets/<kind>/<name>/asset.toml`) names a stable ID, its owner scope, its sources and, for generated
content, the recipe that turns them into Unreal packages. A verification record (`verified.json` beside it) says which
exact package bytes were produced or saved, from which inputs, by which engine. A region record
(`world/regions/<region>/region.toml`) names a world area, its bounds and neighbours; its `actors.verified.json`
lists the saved One File Per Actor packages that region owns.

Records are portable: repository-relative paths, hashes and versions only. No absolute paths, hostnames or times.
Standard library only, so every check runs from a plain checkout.
"""
from __future__ import annotations

import hashlib
import json
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

SCHEMA = 1
AUTHORITIES = ('generated', 'editor', 'split')
KINDS = ('static-mesh', 'skeletal-mesh', 'skeleton', 'animation', 'material', 'material-instance', 'texture',
         'audio', 'map', 'blueprint', 'data', 'level-instance', 'foliage', 'physics',
         # One ownership unit of donor packages taken once as they are (tools/migrate/adopt.py, nested IDs such as
         # adopted/japan/hidamari), editor-owned from then on.
         'adopted',
         # One saved object of a map (its actor package): an editing unit of its own inside its region, recorded and
         # validated apart from the region's other actors (tools/migrate/objects.py).
         'placement')
VERIFIED_KINDS = ('imported', 'editor-saved')
LFS_POINTER = b'version https://git-lfs.github.com/spec/v1'
ID = re.compile(r'^[a-z0-9][a-z0-9-]*(/[a-z0-9][a-z0-9._-]*)+$')
PACKAGE = re.compile(r'^/Game(/[A-Za-z0-9_.-]+)+$')
HEX64 = re.compile(r'^[0-9a-f]{64}$')
PACKAGE_EXTENSIONS = ('.uasset', '.umap')
# Uncooked companions an editor package may carry; the importer records the ones it actually wrote.
COMPANION_EXTENSIONS = ('.ubulk', '.uexp', '.uptnl')
ACTOR_ROOTS = ('__ExternalActors__', '__ExternalObjects__')   # a World Partition map's One File Per Actor folders


class RecordError(ValueError):
    """A record that does not follow the schema; the message names the file and field."""


@dataclass(frozen=True)
class Source:
    path: str            # relative to the asset folder
    sha256: str


@dataclass(frozen=True)
class Output:
    package: str          # /Game/... long package name
    writer: str           # 'generated' or 'editor': which authority writes this package


@dataclass
class Asset:
    id: str
    kind: str
    authority: str
    owner: str
    folder: Path          # absolute folder holding asset.toml
    sources: list[Source] = field(default_factory=list)
    recipe: dict | None = None
    references: list[str] = field(default_factory=list)          # read but never change our output bytes
    input_dependencies: list[str] = field(default_factory=list)  # their verified state is part of our fingerprint
    outputs: list[Output] = field(default_factory=list)
    license: str | None = None
    provenance: str | None = None
    validation: list[str] = field(default_factory=list)

    @property
    def record(self) -> Path:
        return self.folder / 'asset.toml'

    @property
    def verified(self) -> Path:
        return self.folder / 'verified.json'


@dataclass
class Region:
    id: str
    folder: Path
    bounds_cm: tuple[float, float, float, float]   # min x, min y, max x, max y in Unreal centimetres
    neighbours: list[str]
    maps: list[str]                                 # /Game/... maps whose external actors this region may own
    shared: list[str] = field(default_factory=list)  # shared scopes it reads (sky, sea material, ...)
    patch_m: float | None = None                    # its saved scenery patch size, when not the migration default

    @property
    def actors(self) -> Path:
        return self.folder / 'actors.verified.json'

    @property
    def actor_folders(self) -> list[str]:
        """Game-relative folders its maps' actor packages live in (`unreal/Content/__ExternalActors__/<map>`, and
        `__ExternalObjects__`). Regions on one map share them; save validation's label and bounds rule splits them."""
        return [f'unreal/Content/{root}/{PurePosixPath(m).relative_to("/Game")}'
                for m in self.maps for root in ACTOR_ROOTS]


def import_step(asset_id: str) -> str:
    """The build step that imports a generated asset: `import.` and its ID with "/" as "." (step names allow no "/")."""
    return 'import.' + asset_id.replace('/', '.')


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def is_lfs_pointer(path: Path) -> bool:
    """True when the working file is still a Git LFS pointer, not the real bytes."""
    try:
        if path.stat().st_size > 1024:
            return False
        with path.open('rb') as handle:
            return handle.read(len(LFS_POINTER)) == LFS_POINTER
    except OSError:
        return False


def package_files(game: Path, package: str) -> list[Path]:
    """Candidate files of one long package name: `/Game/A/B` -> `unreal/Content/A/B.uasset` or `.umap`."""
    if not PACKAGE.match(package):
        raise RecordError(f'not a /Game package path: {package}')
    stem = game / 'unreal' / 'Content' / PurePosixPath(package).relative_to('/Game')
    return [stem.with_suffix(ext) for ext in PACKAGE_EXTENSIONS]


def content_relative(game: Path, path: Path) -> str:
    return path.resolve().relative_to(game.resolve()).as_posix()


def _need(data: dict, key: str, where: Path, kind=str):
    if key not in data:
        raise RecordError(f'{where}: missing `{key}`')
    value = data[key]
    if not isinstance(value, kind):
        raise RecordError(f'{where}: `{key}` must be {kind.__name__}')
    return value


def _portable(value: str, where: Path, key: str) -> str:
    if value.startswith('/') and not value.startswith('/Game/') or value.startswith('~') or '..' in PurePosixPath(value).parts \
            or re.match(r'^[A-Za-z]:[\\/]', value) or '/Users/' in value or '/home/' in value:
        raise RecordError(f'{where}: `{key}` must be a portable relative path or /Game package, not {value!r}')
    return value


ASSET_KEYS = {'schema', 'id', 'kind', 'authority', 'owner', 'sources', 'recipe', 'references', 'input_dependencies',
              'outputs', 'license', 'provenance', 'validation'}
REGION_KEYS = {'schema', 'id', 'bounds_cm', 'neighbours', 'maps', 'shared', 'about', 'patch_m'}


def _known(data: dict, keys: set, where: Path, table: str = ''):
    unknown = sorted(set(data) - keys)
    if unknown:
        raise RecordError(f'{where}: unknown key(s) {", ".join(unknown)}{" in " + table if table else ""}')


def load_asset(path: Path) -> Asset:
    """Read and validate one asset.toml."""
    try:
        data = tomllib.loads(path.read_text())
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise RecordError(f'{path}: {error}') from None
    _known(data, ASSET_KEYS, path)
    if data.get('schema') != SCHEMA:
        raise RecordError(f'{path}: `schema` must be {SCHEMA}')
    asset_id = _need(data, 'id', path)
    if not ID.match(asset_id):
        raise RecordError(f'{path}: id {asset_id!r} must look like kind/name in lower-case kebab segments')
    kind = _need(data, 'kind', path)
    if kind not in KINDS:
        raise RecordError(f'{path}: kind {kind!r} is not one of {", ".join(KINDS)}')
    authority = _need(data, 'authority', path)
    if authority not in AUTHORITIES:
        raise RecordError(f'{path}: authority {authority!r} is not one of {", ".join(AUTHORITIES)}')
    owner = _need(data, 'owner', path)
    if not ID.match(owner):
        raise RecordError(f'{path}: owner {owner!r} must be a claim scope such as region/w04-skatepark')
    sources = []
    for entry in data.get('sources', []):
        _known(entry, {'path', 'sha256'}, path, '[[sources]]')
        rel = _portable(_need(entry, 'path', path), path, 'sources.path')
        digest = _need(entry, 'sha256', path)
        if not HEX64.match(digest):
            raise RecordError(f'{path}: source {rel} sha256 must be 64 lower-case hex digits')
        sources.append(Source(rel, digest))
    recipe = data.get('recipe')
    if authority in ('generated', 'split'):
        if not isinstance(recipe, dict) or not isinstance(recipe.get('importer'), str) \
                or not isinstance(recipe.get('version'), int):
            raise RecordError(f'{path}: generated content needs [recipe] with importer (str) and version (int)')
        if not sources:
            raise RecordError(f'{path}: generated content needs at least one source')
    elif recipe is not None:
        raise RecordError(f'{path}: editor-owned content has no [recipe]; its saved packages are its source')
    outputs = []
    for entry in data.get('outputs', []):
        _known(entry, {'package', 'writer'}, path, '[[outputs]]')
        package = _portable(_need(entry, 'package', path), path, 'outputs.package')
        if not PACKAGE.match(package):
            raise RecordError(f'{path}: output {package!r} must be a /Game package path')
        writer = entry.get('writer', 'generated' if authority == 'generated' else 'editor')
        if authority != 'split' and writer != ('generated' if authority == 'generated' else 'editor'):
            raise RecordError(f'{path}: output {package} writer {writer!r} contradicts authority {authority!r}')
        if writer not in ('generated', 'editor'):
            raise RecordError(f'{path}: output {package} writer must be generated or editor')
        outputs.append(Output(package, writer))
    if not outputs:
        raise RecordError(f'{path}: an asset needs at least one output package')
    if len({o.package for o in outputs}) != len(outputs):
        raise RecordError(f'{path}: duplicate output package')
    if authority == 'split' and {o.writer for o in outputs} != {'generated', 'editor'}:
        raise RecordError(f'{path}: split authority needs generated and editor-written outputs; otherwise pick one')
    for key in ('references', 'input_dependencies'):
        for dep in data.get(key, []):
            if not isinstance(dep, str) or not ID.match(dep):
                raise RecordError(f'{path}: {key} entry {dep!r} is not an asset ID')
    return Asset(asset_id, kind, authority, owner, path.parent.resolve(), sources, recipe,
                 list(data.get('references', [])), list(data.get('input_dependencies', [])), outputs,
                 data.get('license'), data.get('provenance'), list(data.get('validation', [])))


def load_region(path: Path) -> Region:
    try:
        data = tomllib.loads(path.read_text())
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise RecordError(f'{path}: {error}') from None
    _known(data, REGION_KEYS, path)
    if data.get('schema') != SCHEMA:
        raise RecordError(f'{path}: `schema` must be {SCHEMA}')
    region_id = _need(data, 'id', path)
    if not region_id.startswith('region/') or not ID.match(region_id):
        raise RecordError(f'{path}: region id must look like region/<name>')
    bounds = _need(data, 'bounds_cm', path, list)
    if len(bounds) != 4 or not all(isinstance(v, (int, float)) for v in bounds) \
            or bounds[0] >= bounds[2] or bounds[1] >= bounds[3]:
        raise RecordError(f'{path}: bounds_cm must be [min_x, min_y, max_x, max_y] with min < max')
    maps = _need(data, 'maps', path, list)
    for package in maps:
        if not PACKAGE.match(package):
            raise RecordError(f'{path}: map {package!r} must be a /Game package path')
    patch_m = data.get('patch_m')
    if patch_m is not None and (isinstance(patch_m, bool) or not isinstance(patch_m, (int, float)) or patch_m < 1):
        raise RecordError(f'{path}: patch_m must be a size of 1 m or more')
    return Region(region_id, path.parent.resolve(), tuple(float(v) for v in bounds),
                  list(data.get('neighbours', [])), maps, list(data.get('shared', [])),
                  None if patch_m is None else float(patch_m))


def load_verified(path: Path) -> dict:
    data = json.loads(path.read_text())
    if data.get('schema') != SCHEMA or data.get('kind') not in VERIFIED_KINDS:
        raise RecordError(f'{path}: verification schema must be {SCHEMA} and kind one of {VERIFIED_KINDS}')
    files = data.get('files')
    if not isinstance(files, dict) or (not files and not path.name.startswith('actors.')):
        raise RecordError(f'{path}: `files` must map content-relative paths to sha256')
    for rel, digest in files.items():
        _portable(rel, path, 'files')
        if not HEX64.match(str(digest)):
            raise RecordError(f'{path}: file {rel} sha256 must be 64 hex digits')
    if not isinstance(data.get('engine'), str) or not data['engine']:
        raise RecordError(f'{path}: `engine` must name the engine build that wrote these bytes')
    if data['kind'] == 'imported' and not HEX64.match(str(data.get('input_fingerprint', ''))):
        raise RecordError(f'{path}: an import record needs the input_fingerprint it was made from')
    return data


@dataclass(frozen=True)
class Restricted:
    """Package roots whose bytes never go to public Git LFS (`restricted.toml`, DECISIONS D05 group 2): ignored by Git,
    pinned by Content-relative path in the lock, and fetched from the directory `$<source_env>` names."""
    roots: tuple[str, ...]      # /Game/... roots; empty when the game declares none
    lock: Path                  # absolute path of the pinned manifest
    source_env: str

    @property
    def folders(self) -> tuple[str, ...]:
        """The roots as Content-relative folders: `/Game/Japan/Audio` -> `Japan/Audio`."""
        return tuple(root[len('/Game/'):] for root in self.roots)

    def covers(self, rel: str) -> bool:
        """True for a Content-relative file (`Audio/Skate/A_Roll.uasset`) under a restricted root."""
        return any(rel.startswith(folder + '/') for folder in self.folders)

    def covers_package(self, package: str) -> bool:
        return package.startswith('/Game/') and self.covers(package[len('/Game/'):])

    def content_rel(self, game_rel: str) -> str | None:
        """`unreal/Content/Audio/X.uasset` -> `Audio/X.uasset` when restricted, else None."""
        prefix = 'unreal/Content/'
        rel = game_rel[len(prefix):] if game_rel.startswith(prefix) else None
        return rel if rel is not None and self.covers(rel) else None


def load_restricted(game: Path) -> Restricted:
    """The game's restricted roots; none when it has no `restricted.toml`."""
    path = game / 'restricted.toml'
    if not path.is_file():
        return Restricted((), game / 'restricted.lock.json', 'V2_RESTRICTED_SOURCE')
    try:
        data = tomllib.loads(path.read_text())
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise RecordError(f'{path}: {error}') from None
    _known(data, {'schema', 'roots', 'lock', 'source'}, path)
    if data.get('schema') != SCHEMA:
        raise RecordError(f'{path}: `schema` must be {SCHEMA}')
    roots = _need(data, 'roots', path, list)
    for root in roots:
        if not isinstance(root, str) or not PACKAGE.match(root):
            raise RecordError(f'{path}: root {root!r} must be a /Game package path')
    lock = _portable(_need(data, 'lock', path), path, 'lock')
    source = _need(data, 'source', path, dict)
    _known(source, {'env', 'about'}, path, '[source]')
    return Restricted(tuple(roots), game / lock, _need(source, 'env', path))


DATA_ROOT = 'Data'                    # unreal/Content/Data: files the game reads at run time (AtelierDataPath)
DATA_LOCK = 'runtime-data.lock.json'  # every runtime data file with its sha256


def data_files(game: Path) -> list[str]:
    """Content-relative paths of every file under unreal/Content/Data."""
    root = game / 'unreal' / 'Content' / DATA_ROOT
    if not root.is_dir():
        return []
    return sorted(p.relative_to(root.parent).as_posix() for p in root.rglob('*') if p.is_file() or p.is_symlink())


def load_data_lock(game: Path) -> dict[str, str] | None:
    """Content-relative path -> sha256 of every pinned runtime data file; None when there is no lock."""
    path = game / DATA_LOCK
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as error:
        raise RecordError(f'{path}: {error}') from None
    files = data.get('files') if isinstance(data, dict) else None
    if not isinstance(data, dict) or data.get('schema') != SCHEMA or not isinstance(files, dict):
        raise RecordError(f'{path}: a data lock is {{"schema": {SCHEMA}, "files": {{PATH: SHA256}}}}')
    for rel, digest in files.items():
        _portable(rel, path, 'files')
        if not rel.startswith(DATA_ROOT + '/') or not isinstance(digest, str) or not HEX64.match(digest):
            raise RecordError(f'{path}: {rel} must be a file under {DATA_ROOT}/ with a sha256')
    return dict(files)


def write_data_lock(game: Path) -> int:
    """Pin every runtime data file as it is now; returns how many."""
    files = {rel: sha256_file(game / 'unreal' / 'Content' / rel) for rel in data_files(game)}
    (game / DATA_LOCK).write_text(json.dumps({
        'schema': SCHEMA,
        'about': 'Runtime data under unreal/Content/Data (tools/migrate/adopt.py --data or --pin-data); '
                 'tools/content/check.py requires every file here, hydrated and with these bytes, and nothing else.',
        'files': files}, indent=2, sort_keys=True) + '\n')
    return len(files)


def load_lock(restricted: Restricted) -> dict[str, dict]:
    """Content-relative path -> {sha256, size} for every pinned restricted file; empty when there is no lock yet."""
    path = restricted.lock
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as error:
        raise RecordError(f'{path}: {error}') from None
    files = data.get('files') if isinstance(data, dict) else None
    if not isinstance(data, dict) or data.get('schema') != SCHEMA or not isinstance(files, dict):
        raise RecordError(f'{path}: a lock is {{"schema": {SCHEMA}, "files": {{PATH: {{sha256, size}}}}}}')
    for rel, entry in files.items():
        _portable(rel, path, 'files')
        if not restricted.covers(rel) or not rel.endswith(PACKAGE_EXTENSIONS + COMPANION_EXTENSIONS):
            raise RecordError(f'{path}: {rel} is not a package file under a restricted root')
        if not isinstance(entry, dict) or set(entry) != {'sha256', 'size'} or not HEX64.match(str(entry['sha256'])) \
                or not isinstance(entry['size'], int):
            raise RecordError(f'{path}: {rel} must pin {{"sha256": 64 hex digits, "size": bytes}}')
    return files


def restricted_tracked(game: Path, restricted: Restricted) -> list[str]:
    """Game-relative files under the restricted roots that Git tracks or has staged; none outside a Git checkout."""
    import subprocess
    if not restricted.roots:
        return []
    try:
        listing = subprocess.run(['git', 'ls-files', '-z', '--cached', '--', *(f'unreal/Content/{f}' for f in restricted.folders)],
                                 cwd=game, capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return []
    return sorted(n for n in listing.stdout.decode().split('\0') if n) if listing.returncode == 0 else []


def write_json(path: Path, data: dict) -> bool:
    """Write canonical JSON only when the content changes; a no-op leaves the file and its time untouched."""
    text = json.dumps(data, indent=2, sort_keys=True) + '\n'
    if path.is_file() and path.read_text() == text:
        return False
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(text)
    tmp.replace(path)
    return True


def input_fingerprint(asset: Asset, dependency_fingerprints: dict[str, str]) -> str:
    """What a generated asset's packages are made from: sources, recipe and input dependencies' verified states.

    Paths are relative and sorted (the source-to-package pairing keeps record order), so the same inputs give the
    same fingerprint on every machine and checkout.
    """
    body = {
        'id': asset.id, 'kind': asset.kind, 'schema': SCHEMA,
        'sources': sorted([s.path, s.sha256] for s in asset.sources),
        'recipe': asset.recipe,
        'outputs': sorted([o.package, o.writer] for o in asset.outputs if o.writer == 'generated'),
        # The importer pairs sources with generated packages in record order, so the pairing is an input too.
        'mapping': [[s.path, o.package] for s, o in
                    zip(asset.sources, [o for o in asset.outputs if o.writer == 'generated'])],
        'input_dependencies': {dep: dependency_fingerprints.get(dep, 'missing')
                               for dep in sorted(asset.input_dependencies)},
    }
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def state_fingerprint(verified: dict) -> str:
    """One asset's verified state, as consumed by dependents: its package hashes and engine."""
    body = {'files': dict(sorted(verified['files'].items())), 'engine': verified['engine']}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def discover(game: Path) -> tuple[list[Asset], list[Region]]:
    assets = [load_asset(p) for p in sorted((game / 'assets').glob('**/asset.toml'))]
    regions = [load_region(p) for p in sorted((game / 'world' / 'regions').glob('*/region.toml'))]
    return assets, regions
