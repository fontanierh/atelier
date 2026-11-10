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
import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

SCHEMA = 1
AUTHORITIES = ('generated', 'editor', 'split')
KINDS = ('static-mesh', 'skeletal-mesh', 'skeleton', 'animation', 'material', 'material-instance', 'material-master',
         'texture', 'audio', 'map', 'blueprint', 'data', 'level-instance', 'foliage', 'physics',
         # One ownership unit of donor packages taken once as they are (tools/migrate/adopt.py, nested IDs such as
         # adopted/japan/hidamari), editor-owned from then on.
         'adopted',
         # One saved object of a map (its actor package): an editing unit of its own inside its region, recorded and
         # validated apart from the region's other actors (tools/migrate/objects.py).
         'placement',
         # A region generator's pinned code and data, with no package of its own: what its records were generated from,
         # kept recoverable after the packages it once owned moved to their own records (tools/migrate/master_records.py).
         'generator',
         # A material parameter collection its pinned generator writes: only appended to, so its parameter ids stay.
         'parameter-collection')
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
    derive: dict | None = None    # [derive]: the remainder is derived from sources[0] and sources[1] (tools/content/carve.py)

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
              'outputs', 'license', 'provenance', 'validation', 'derive'}
DERIVE_KEYS = {'kind', 'version', 'original', 'selection'}
MATERIAL_RECIPE_KEYS = {'importer', 'version', 'settings'}
MATERIAL_SETTINGS = {'parent', 'textures', 'scalars', 'vectors', 'switches', 'base'}
# A texture recipe's optional settings (unreal/Scripts/import_settings.py reads them; an absent key leaves the texture as
# the importer made it). TEXTURE_GROUPS mirrors import_settings.TEXTURE_GROUPS; tests/test_texture_settings.py pins the match.
TEXTURE_KEYS = {'srgb', 'compression', 'max_texture_size', 'lod_group', 'address', 'mip_gen'}
TEXTURE_GROUPS = frozenset({'TEXTUREGROUP_WORLD', 'TEXTUREGROUP_EFFECTS', 'TEXTUREGROUP_CHARACTER', 'TEXTUREGROUP_UI',
                            'TEXTUREGROUP_WORLD_NORMAL_MAP', 'TEXTUREGROUP_WORLD_SPECULAR'})
TEXTURE_COMPRESSION = re.compile(r'^TC_[A-Z0-9_]+$')
TEXTURE_ADDRESS = frozenset({'wrap', 'mirror'})
TEXTURE_MIP_GEN = frozenset({'TMGS_FROM_TEXTURE_GROUP', 'TMGS_SIMPLE_AVERAGE', 'TMGS_NO_MIPMAPS'})
PARAMETER_NAME = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
REGION_KEYS = {'schema', 'id', 'bounds_cm', 'neighbours', 'maps', 'shared', 'about', 'patch_m'}


def _known(data: dict, keys: set, where: Path, table: str = ''):
    unknown = sorted(set(data) - keys)
    if unknown:
        raise RecordError(f'{where}: unknown key(s) {", ".join(unknown)}{" in " + table if table else ""}')


# The Interchange default instances a generated instance may name as its parent: engine-provided, owned by no record.
ENGINE_PARENTS = frozenset({'/InterchangeAssets/gltf/MaterialInstances/MI_Default_Opaque_DS',
                            '/InterchangeAssets/gltf/MaterialInstances/MI_Default_Opaque',
                            '/InterchangeAssets/gltf/MaterialInstances/MI_Default_Blend_DS',
                            '/InterchangeAssets/gltf/MaterialInstances/MI_ClearCoat_Opaque_DS'})
INSTANCE_KEYS = {'package', 'parent', 'textures', 'scalars', 'vectors', 'switches', 'base'}
# The base-property overrides a material-instance record may state (FMaterialInstanceBasePropertyOverrides), with their
# type: each is written with its override flag set, and every other override flag is cleared (import_asset.py).
BASE_OVERRIDES = {'blend_mode': str, 'opacity_mask_clip_value': float, 'two_sided': bool, 'dithered_lod_transition': bool}
BLEND_MODES = {'BLEND_OPAQUE', 'BLEND_MASKED', 'BLEND_TRANSLUCENT', 'BLEND_ADDITIVE', 'BLEND_MODULATE',
               'BLEND_ALPHA_COMPOSITE', 'BLEND_ALPHA_HOLDOUT'}
SWITCH_NAME = re.compile(r'^bHas[A-Za-z]+$')   # the static switches the record may state: the Interchange bHas* booleans


def _parent(values: dict, where: Path) -> str:
    parent = _need(values, 'parent', where)
    if not PACKAGE.match(parent) and parent not in ENGINE_PARENTS:
        raise RecordError(f'{where}: parent {parent!r} must be a /Game package or an Interchange default instance')
    return parent


def _base(values: dict, where: Path) -> None:
    base = values.get('base', {})
    if not isinstance(base, dict):
        raise RecordError(f'{where}: base must be a table of base-property overrides')
    for name, value in base.items():
        kind = BASE_OVERRIDES.get(name)
        if kind is None:
            raise RecordError(f'{where}: base override {name!r} is not one of {sorted(BASE_OVERRIDES)}')
        if kind is bool and not isinstance(value, bool):
            raise RecordError(f'{where}: base override {name} must be true or false')
        if kind is float and (isinstance(value, bool) or not isinstance(value, (int, float))):
            raise RecordError(f'{where}: base override {name} must be a number')
        if kind is str and value not in BLEND_MODES:
            raise RecordError(f'{where}: base override {name} must be one of {sorted(BLEND_MODES)}')


def _parameters(values: dict, where: Path) -> None:
    _base(values, where)
    switches = values.get('switches', {})
    if not isinstance(switches, dict):
        raise RecordError(f'{where}: switches must be a table of bHas... = true or false')
    for name, value in switches.items():
        if not SWITCH_NAME.match(name) or not isinstance(value, bool):
            raise RecordError(f'{where}: switch {name!r} must be a bHas... name with true or false')
    textures = values.get('textures', {})
    if not isinstance(textures, dict):
        raise RecordError(f'{where}: textures must be a table of parameter = /Game package')
    for name, package in textures.items():
        if not PARAMETER_NAME.match(name) or not isinstance(package, str) or not PACKAGE.match(package):
            raise RecordError(f'{where}: texture {name!r} = {package!r} must be a parameter name and a /Game package')
    scalars = values.get('scalars', {})
    if not isinstance(scalars, dict):
        raise RecordError(f'{where}: scalars must be a table of parameter = number')
    for name, value in scalars.items():
        if not PARAMETER_NAME.match(name) or isinstance(value, bool) or not isinstance(value, (int, float)):
            raise RecordError(f'{where}: scalar {name!r} must be a number')
    vectors = values.get('vectors', {})
    if not isinstance(vectors, dict):
        raise RecordError(f'{where}: vectors must be a table of parameter = [r, g, b, a]')
    for name, value in vectors.items():
        if not PARAMETER_NAME.match(name) or not isinstance(value, list) or len(value) != 4 \
                or any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in value):
            raise RecordError(f'{where}: vector {name!r} must be four numbers [r, g, b, a]')


def texture_settings(recipe: dict, where: Path) -> dict:
    """Validate a texture [recipe]: `importer = "texture"`, version 1 (unchanged by the optional settings), and
    [recipe.settings] with any of: srgb (bool), compression (a TC_* name), max_texture_size (a power of two), lod_group
    (a TEXTUREGROUP_* name), address ("wrap" or "mirror"). A key the record does not state leaves the texture as imported."""
    if recipe.get('importer') != 'texture' or recipe.get('version') != 1:
        raise RecordError(f'{where}: a texture recipe is importer "texture" version 1')
    settings = recipe.get('settings', {})
    if not isinstance(settings, dict):
        raise RecordError(f'{where}: [recipe.settings] must be a table')
    _known(settings, TEXTURE_KEYS, where, '[recipe.settings]')
    if 'srgb' in settings and not isinstance(settings['srgb'], bool):
        raise RecordError(f'{where}: srgb must be true or false')
    if 'compression' in settings and not (isinstance(settings['compression'], str)
                                          and TEXTURE_COMPRESSION.match(settings['compression'])):
        raise RecordError(f'{where}: compression {settings["compression"]!r} is not a TC_* name')
    if 'max_texture_size' in settings:
        size = settings['max_texture_size']
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0 or size & (size - 1):
            raise RecordError(f'{where}: max_texture_size must be a positive power of two, not {size!r}')
    if 'lod_group' in settings and settings['lod_group'] not in TEXTURE_GROUPS:
        raise RecordError(f'{where}: unknown lod_group {settings["lod_group"]!r}')
    if 'address' in settings and settings['address'] not in TEXTURE_ADDRESS:
        raise RecordError(f'{where}: unknown address {settings["address"]!r}')
    if 'mip_gen' in settings and settings['mip_gen'] not in TEXTURE_MIP_GEN:
        raise RecordError(f'{where}: unknown mip_gen {settings["mip_gen"]!r}')
    return settings


def material_settings(recipe: dict, where: Path, inputs: list[str], outputs: list[str]) -> dict:
    """Validate a material-instance [recipe]: `importer = "material-instance"`, version 2, and one of two forms.

    Single form: [recipe.settings] with `parent`, `textures` ({parameter: /Game texture package}), `scalars` ({parameter:
    number}) and `vectors` ({parameter: [r, g, b, a]}), written to every output. Instances form: [[recipe.settings.instances]]
    with one row per output, `package` and the same keys (each row's `parent` as well). Either form may add `base`, the
    base-property overrides (blend_mode, opacity_mask_clip_value, two_sided, dithered_lod_transition). The instance is written as exactly
    the values the record states; none is an override the record does not state. Every /Game package it reads must be an
    output of one of its input_dependencies (an Interchange default parent is engine-provided, not read from a record)."""
    _known(recipe, MATERIAL_RECIPE_KEYS, where, '[recipe]')
    if recipe.get('importer') != 'material-instance' or recipe.get('version') != 2:
        raise RecordError(f'{where}: a material-instance recipe is importer "material-instance" version 2')
    settings = recipe.get('settings')
    if not isinstance(settings, dict):
        raise RecordError(f'{where}: a material-instance needs [recipe.settings]')
    if 'instances' in settings:
        _known(settings, {'instances'}, where, '[recipe.settings]')
        rows = settings['instances']
        if not isinstance(rows, list) or not rows:
            raise RecordError(f'{where}: instances must be a non-empty list of [[recipe.settings.instances]] tables')
        packages = []
        for row in rows:
            if not isinstance(row, dict):
                raise RecordError(f'{where}: each instance is a table')
            _known(row, INSTANCE_KEYS, where, '[[recipe.settings.instances]]')
            package = _need(row, 'package', where)
            if not PACKAGE.match(package) or package in packages:
                raise RecordError(f'{where}: instance package {package!r} must be a /Game package named once')
            packages.append(package)
            _parent(row, where)
            _parameters(row, where)
        if sorted(packages) != sorted(outputs):
            raise RecordError(f'{where}: the instances name {sorted(packages)} but the outputs are {sorted(outputs)}')
        return settings
    _known(settings, MATERIAL_SETTINGS, where, '[recipe.settings]')
    _parent(settings, where)
    _parameters(settings, where)
    if not inputs:
        raise RecordError(f'{where}: a material-instance names the owners of its parent and textures as '
                          f'input_dependencies')
    return settings


MASTER_IMPORTER = ('material-master', 1)
MASTER_SETTINGS = {'builder', 'reads', 'arguments'}
MASTER_BUILDER = re.compile(r'^[a-z][a-z0-9_]*$')
# An engine asset a master may read (a default texture such as WhiteSquareTexture): owned by no record, like ENGINE_PARENTS.
ENGINE_PACKAGE = re.compile(r'^/Engine(/[A-Za-z0-9_.-]+)+$')


def material_master_settings(recipe: dict, where: Path, authority: str, sources: list, outputs: list[str]) -> dict:
    """@cc [owner:fontanierh,label:correctness] material-master-generator-pinned
    Validate a material-master [recipe]: `importer = "material-master"`, version 1, and [recipe.settings] with `builder`
    (the lower-case name of the generator function that builds the graph), `reads` (optional: packages the graph samples;
    each /Game package is an output of an input dependency, while /Engine packages are supplied by the engine and need
    no game owner; see material_master_input_problems) and `arguments` (optional: one plain
    scalar or string per builder argument; lists and tables are refused). A master is generator-built, so its authority is
    generated and its generator is one or more pinned .py [[sources]]: the recipe names a builder, it does not restate the
    graph. Each output is a /Game package named M_<name>."""
    _known(recipe, MATERIAL_RECIPE_KEYS, where, '[recipe]')
    if (recipe.get('importer'), recipe.get('version')) != MASTER_IMPORTER:
        raise RecordError(f'{where}: a material-master recipe is importer "material-master" version 1')
    if authority != 'generated':
        raise RecordError(f'{where}: a material-master is generator-built, so its authority is generated, not {authority!r}')
    if not sources or any(not source.path.endswith('.py') for source in sources):
        raise RecordError(f'{where}: a material-master names its generator as [[sources]] .py files, each pinned by sha256')
    settings = recipe.get('settings')
    if not isinstance(settings, dict):
        raise RecordError(f'{where}: a material-master needs [recipe.settings]')
    _known(settings, MASTER_SETTINGS, where, '[recipe.settings]')
    builder = _need(settings, 'builder', where)
    if not MASTER_BUILDER.match(builder):
        raise RecordError(f'{where}: builder {builder!r} must be a lower-case function name')
    reads = settings.get('reads', [])
    if not isinstance(reads, list) or len(set(reads)) != len(reads) \
            or any(not isinstance(package, str) or not (PACKAGE.match(package) or ENGINE_PACKAGE.match(package))
                   for package in reads):
        raise RecordError(f'{where}: reads must be a list of distinct /Game or /Engine packages')
    arguments = settings.get('arguments', {})
    if not isinstance(arguments, dict):
        raise RecordError(f'{where}: arguments must be a table of name = value')
    for name, value in arguments.items():
        if not PARAMETER_NAME.match(name) or isinstance(value, (list, dict)):
            raise RecordError(f'{where}: argument {name!r} must be a name with a plain scalar or string value')
    for package in outputs:
        if not package.rsplit('/', 1)[-1].startswith('M_'):
            raise RecordError(f'{where}: output {package!r} is a material master and must be named M_<name>')
    return settings


SKATE_RUNTIME_IMPORTER = ('skate-runtime', 1)
SKATE_RUNTIME_SOURCES = ['src/simulation_package.py', 'src/motion_text.py', 'src/runtime_text.py',
                         'src/skate_runtime_inputs.sha256']


def skate_runtime_settings(recipe: dict, where: Path, sources: list, outputs: list[str]) -> dict:
    """@cc [owner:fontanierh,label:correctness] skate-runtime-record-pins
    Validate a skate-runtime data [recipe]: `importer = "skate-runtime"`, version 1, and [recipe.settings] with only
    `manifest_sha256` (the simulation package manifest the assembled package must hash to). Its [[sources]] are exactly the
    pinned assembler code and the Skate/Data input list (SKATE_RUNTIME_SOURCES, in that order), so the import fingerprint
    covers every byte the package is assembled from. It is one output, a /Game package named RuntimeData."""
    _known(recipe, MATERIAL_RECIPE_KEYS, where, '[recipe]')
    if (recipe.get('importer'), recipe.get('version')) != SKATE_RUNTIME_IMPORTER:
        raise RecordError(f'{where}: a skate-runtime recipe is importer "skate-runtime" version 1')
    if [source.path for source in sources] != SKATE_RUNTIME_SOURCES:
        raise RecordError(f'{where}: a skate-runtime record pins exactly {SKATE_RUNTIME_SOURCES}')
    settings = recipe.get('settings')
    if not isinstance(settings, dict) or set(settings) != {'manifest_sha256'} \
            or not HEX64.match(str(settings['manifest_sha256'])):
        raise RecordError(f'{where}: [recipe.settings] holds only manifest_sha256, 64 lower-case hex digits')
    if len(outputs) != 1 or outputs[0].rsplit('/', 1)[-1] != 'RuntimeData':
        raise RecordError(f'{where}: a skate-runtime record is one output package named RuntimeData')
    return settings


COLLECTION_IMPORTER = ('parameter-collection', 1)
COLLECTION_SETTINGS = {'builder', 'arguments'}


def parameter_collection_settings(recipe: dict, where: Path, authority: str, sources: list, outputs: list[str]) -> dict:
    """@cc [owner:fontanierh,label:correctness] parameter-collection-generator-pinned
    Validate a parameter-collection [recipe]: `importer = "parameter-collection"`, version 1, and [recipe.settings] with
    `builder` (the lower-case name of the generator function that creates or completes the collection) and `arguments`
    (optional: one plain scalar or string per builder argument). Like a master, a collection is generator-built: its
    authority is generated and its generator is one or more pinned .py [[sources]], the first holding the builder and the
    parameters it makes. It is one output, a /Game package named MPC_<name>."""
    _known(recipe, MATERIAL_RECIPE_KEYS, where, '[recipe]')
    if (recipe.get('importer'), recipe.get('version')) != COLLECTION_IMPORTER:
        raise RecordError(f'{where}: a parameter-collection recipe is importer "parameter-collection" version 1')
    if authority != 'generated':
        raise RecordError(f'{where}: a parameter-collection is generator-built, so its authority is generated, not {authority!r}')
    if not sources or any(not source.path.endswith('.py') for source in sources):
        raise RecordError(f'{where}: a parameter-collection names its generator as [[sources]] .py files, each pinned by sha256')
    settings = recipe.get('settings')
    if not isinstance(settings, dict):
        raise RecordError(f'{where}: a parameter-collection needs [recipe.settings]')
    _known(settings, COLLECTION_SETTINGS, where, '[recipe.settings]')
    builder = _need(settings, 'builder', where)
    if not MASTER_BUILDER.match(builder):
        raise RecordError(f'{where}: builder {builder!r} must be a lower-case function name')
    arguments = settings.get('arguments', {})
    if not isinstance(arguments, dict):
        raise RecordError(f'{where}: arguments must be a table of name = value')
    for name, value in arguments.items():
        if not PARAMETER_NAME.match(name) or isinstance(value, (list, dict)):
            raise RecordError(f'{where}: argument {name!r} must be a name with a plain scalar or string value')
    if len(outputs) != 1 or not outputs[0].rsplit('/', 1)[-1].startswith('MPC_'):
        raise RecordError(f'{where}: a parameter-collection is one output package named MPC_<name>')
    return settings


def material_master_reads(asset: 'Asset') -> list[str]:
    """The /Game and /Engine packages a material master's graph samples, in the order its record states them."""
    return list((asset.recipe or {}).get('settings', {}).get('reads', []))


def material_rows(asset: 'Asset') -> list[dict]:
    """One row per instance the record writes: {package, parent, textures, scalars, vectors}."""
    settings = (asset.recipe or {}).get('settings', {})
    if 'instances' in settings:
        return [dict(row) for row in settings['instances']]
    return [dict(settings, package=o.package) for o in asset.outputs]


def material_inputs(asset: 'Asset') -> list[str]:
    """The /Game packages a material instance reads: each row's parent (unless it is an engine default), then its
    textures in parameter order, without repeats."""
    out = []
    for row in material_rows(asset):
        for package in [row['parent'], *(row.get('textures', {})[k] for k in sorted(row.get('textures', {})))]:
            if package not in ENGINE_PARENTS and package not in out:
                out.append(package)
    return out


def material_input_problems(asset: 'Asset', outputs_of: dict[str, set[str]]) -> list[str]:
    """Each package a material instance or master reads must be an output of one of its input_dependencies; [] when all
    are. `outputs_of` maps every record ID to the set of its /Game output packages."""
    if asset.kind == 'material-master':
        wanted = [package for package in material_master_reads(asset) if not ENGINE_PACKAGE.match(package)]
    elif asset.kind == 'material-instance':
        wanted = material_inputs(asset)
    else:
        return []
    covered = set().union(*(outputs_of.get(dep, set()) for dep in asset.input_dependencies))
    return [f'{package} is read by {asset.id} but no input dependency owns it'
            for package in wanted if package not in covered]


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
    derive = data.get('derive')
    if derive is not None:
        # A carved tile: sources are [original, selection], and the importer's source is the derived remainder.
        _known(derive, DERIVE_KEYS, path, '[derive]')
        if derive.get('kind') != 'carve' or derive.get('version') != 1:
            raise RecordError(f'{path}: [derive] must be kind "carve" version 1')
        names = [_need(derive, 'original', path), _need(derive, 'selection', path)]
        if authority != 'generated' or [s.path for s in sources] != names:
            raise RecordError(f'{path}: [derive] needs generated authority and sources exactly {names}')
        derive = dict(derive)
    if kind in ('material-master', 'parameter-collection') and authority != 'generated':
        # A master or collection stays generator-built until its generator is recoverable; it is never converted by omission.
        raise RecordError(f'{path}: a {kind} is generator-built, so its authority is generated, not {authority!r}')
    recipe = data.get('recipe')
    inputs = list(data.get('input_dependencies', []))
    if authority in ('generated', 'split'):
        if not isinstance(recipe, dict) or not isinstance(recipe.get('importer'), str) \
                or not isinstance(recipe.get('version'), int):
            raise RecordError(f'{path}: generated content needs [recipe] with importer (str) and version (int)')
        # A material instance pins no file of its own: its parent and textures are the packages of its
        # input_dependencies (material_settings), so it needs those instead of a source.
        if kind == 'material-instance':
            material_settings(recipe, path, inputs, [entry.get('package', '') for entry in data.get('outputs', [])])
        elif kind == 'material-master':
            # A master's generator is its pinned .py source; its reads are checked against input_dependencies later
            # (material_input_problems), once every record's outputs are known.
            material_master_settings(recipe, path, authority, sources, [entry.get('package', '') for entry in data.get('outputs', [])])
        elif kind == 'parameter-collection':
            parameter_collection_settings(recipe, path, authority, sources,
                                          [entry.get('package', '') for entry in data.get('outputs', [])])
        else:
            if not sources:
                raise RecordError(f'{path}: generated content needs at least one source')
            if kind == 'data' and recipe.get('importer') == 'skate-runtime':
                skate_runtime_settings(recipe, path, sources, [entry.get('package', '') for entry in data.get('outputs', [])])
            if kind == 'texture':
                texture_settings(recipe, path)   # a texture's settings are checked after its original is required
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
    if kind == 'generator':
        if outputs or recipe is not None or not sources:
            raise RecordError(f'{path}: a generator record names pinned [[sources]] and no outputs or recipe')
    elif not outputs:
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
                 data.get('license'), data.get('provenance'), list(data.get('validation', [])), derive)


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
DATA_GENERATED = 'Data/Network'        # the multiplayer manifest unreal.package writes (tools/package/network_identity.py)
DATA_LOCK = 'runtime-data.lock.json'  # every runtime data file with its sha256


def data_files(game: Path) -> list[str]:
    """Content-relative paths of every file under unreal/Content/Data, except the generated Data/Network manifest."""
    root = game / 'unreal' / 'Content' / DATA_ROOT
    if not root.is_dir():
        return []
    return sorted(p.relative_to(root.parent).as_posix() for p in root.rglob('*')
                  if (p.is_file() or p.is_symlink()) and not p.relative_to(root.parent).is_relative_to(DATA_GENERATED))


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
        # Only a carved record carries it, so every other record's fingerprint is unchanged.
        **({'derive': asset.derive} if asset.derive else {}),
    }
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def state_fingerprint(verified: dict) -> str:
    """One asset's verified state, as consumed by dependents: its package hashes and engine."""
    body = {'files': dict(sorted(verified['files'].items())), 'engine': verified['engine']}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def record_paths(game: Path) -> list[Path]:
    """Every asset record (assets/**/asset.toml) that is not inside another record's folder: a record's copied
    sources keep their donor names, and a donor's own asset.toml among them is a source file, not a V2 record."""
    paths = sorted((game / 'assets').glob('**/asset.toml'))
    folders = {p.parent for p in paths}
    return [p for p in paths if not any(parent in folders for parent in p.parent.parents)]


def record_files(game: Path) -> list[tuple]:
    """(game-relative path, size, mtime_ns, ctime_ns, inode) of every file discover() and region ownership read: each
    asset.toml under assets/ (a nested one too, which record_paths filters), each region.toml and actors.verified.json.
    A cheap stamp of the records (stat only, no parsing): writing, creating, deleting or moving any of them changes it."""
    root = str(game) + os.sep
    found = []
    stack = [str(game / 'assets')]
    while stack:
        try:
            entries = list(os.scandir(stack.pop()))
        except FileNotFoundError:
            continue
        for entry in entries:
            if entry.is_dir(follow_symlinks=False):   # as glob('**') walks: symlinked folders are not entered
                stack.append(entry.path)
            elif entry.name == 'asset.toml':
                found.append(entry.path)
    regions = game / 'world' / 'regions'
    if regions.is_dir():
        found += [str(folder / name) for folder in regions.iterdir() for name in ('region.toml', 'actors.verified.json')]
    stamps = []
    for path in found:
        try:
            st = os.stat(path)
        except (FileNotFoundError, NotADirectoryError):   # absent (or deleted since the listing), as discover() finds it
            continue
        stamps.append((path.removeprefix(root).replace(os.sep, '/'), st.st_size, st.st_mtime_ns, st.st_ctime_ns,
                       st.st_ino))
    return sorted(stamps)


def discover(game: Path) -> tuple[list[Asset], list[Region]]:
    assets = [load_asset(p) for p in record_paths(game)]
    regions = [load_region(p) for p in sorted((game / 'world' / 'regions').glob('*/region.toml'))]
    return assets, regions
