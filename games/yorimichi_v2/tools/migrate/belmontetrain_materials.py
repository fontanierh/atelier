"""Source recovery for the 459 residual Belmonte train packages: their texture and material-instance records (plan first).

    uv run python games/yorimichi_v2/tools/migrate/belmontetrain_materials.py [--donor DIR]            # plan; writes nothing
    uv run python games/yorimichi_v2/tools/migrate/belmontetrain_materials.py [--donor DIR] --table    # the doc table (markdown)
    uv run python games/yorimichi_v2/tools/migrate/belmontetrain_materials.py [--donor DIR] --paths    # claim paths and scopes
    uv run python games/yorimichi_v2/tools/migrate/belmontetrain_materials.py [--donor DIR] --claim TASK  # the one journaled write

DIR is the donor's `belmonte-train` folder (default: $YV2_DONOR_BUILD/belmonte-train). It is read only.

The seven adopted records (assets/adopted/belmontetrain/<unit>) hold 321 `M_BT_*` material instances and 138 `T_BT_*`
textures in Source/SM_BT_<V>/LOD0..2. Each of the 21 unit LOD GLBs (`<unit>/SM_BT_<V>_LOD<n>.glb`, pinned by the donor's
import-report.json) names its glTF materials and images, and every residual package binds to one of them by name:

- one texture record per texture package. Its source is the donor image the GLB embeds (byte-identical to
  `textures/<image>.png|jpg`, checked here), pinned by sha256. The importer writes one package from one source, so a
  record owns one package. Interchange names the second glTF texture of one image `<image>1` (T_BT_Walnut1).
- one material-instance record per (unit, LOD) group. It has no source file and no GLB copy: its recipe is the
  `instances` form of the Japan leaf records (one [[recipe.settings.instances]] table per package, keyed by package), with
  each instance's Interchange parent, BaseColorTexture, BaseColorFactor, RoughnessFactor, MetallicFactor, and for the
  clear-coat and emissive ones ClearCoatFactor, EmissiveFactor and EmissiveStrength, all from the GLB. Its
  input_dependencies are the texture records it binds. The donor's static switches are not in the form.

Facts are checked against the committed package bytes when they are hydrated (not LFS pointers): a float32 colour or
roughness must appear in the instance, its parent path and its texture paths must appear, and a texture's
compression and LOD-group names must appear. A texture's sRGB flag is not in the bytes, so it always needs the native read.
Nothing here imports, runs Unreal or writes a file in plan mode.

--claim writes the texture and material records, their src/ copies, and moves the 459 [[outputs]] out of the seven adopted
records (deleting a record that is left with none, with its verified entries and units.json keys). The packages' files
stay where they are until a verified import rewrites them. The prop records that reference an adopted unit point at
the unit's new records. It is one journaled write (brinecove_split_apply.execute) under the seven unit scopes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import struct
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = HERE.parents[1]
REPO = GAME.parents[1]
sys.path.insert(0, str(GAME / 'tools' / 'content'))
import authority  # noqa: E402
import records  # noqa: E402
sys.path.insert(0, str(HERE))
import brinecove_split_apply as apply  # noqa: E402  (Journal and execute: the journaled write every migrate step uses)
import recover  # noqa: E402  (_drop_outputs, _toml, slug)

GAME_REL = 'games/yorimichi_v2'
RECORDS = 'assets/adopted/belmontetrain'
UNITS_REL = f'{RECORDS}/units.json'
UNITS = {'baggage-van': 'BaggageVan', 'brake-van': 'BrakeVan', 'first-class': 'FirstClass', 'locomotive': 'Locomotive',
         'restaurant': 'Restaurant', 'second-class': 'SecondClass', 'tender': 'Tender'}
SCOPES = sorted(f'shared/belmontetrain/{unit}' for unit in UNITS)
LODS = (0, 1, 2)
FOLDER = '/Game/BelmonteTrain/Source/SM_BT_{v}/LOD{n}/'
# The Interchange default material instance the donor's import made each instance from, by glTF alphaMode, by the
# KHR_materials_clearcoat extension and by doubleSided (the committed bytes name them: M_BT_Brass opaque double-sided,
# M_BT_Glass blend, M_BT_LiveryIvory clear-coat, M_BT_WindowInterior* single-sided with no `_DS`). Any other mode or
# extension is refused.
PARENT_NAMES = {'OPAQUE': 'Opaque', 'BLEND': 'Blend'}
EXTENSIONS_OK = {'KHR_materials_clearcoat', 'KHR_materials_emissive_strength'}
ENUM_NAMES = {'TC_DEFAULT': 'TC_Default', 'TC_NORMALMAP': 'TC_Normalmap', 'TC_MASKS': 'TC_Masks'}


def parent_of(mode: str, clearcoat: bool, two_sided: bool) -> str:
    return '/InterchangeAssets/gltf/MaterialInstances/MI_{}_{}{}'.format(
        'ClearCoat' if clearcoat else 'Default', PARENT_NAMES[mode], '_DS' if two_sided else '')
LOD_GROUP = 'TEXTUREGROUP_WORLD'
ADDRESS = 'wrap'
# glTF texture role -> (sRGB, compression); the compression names are the importer's TextureCompressionSettings names
ROLE_TEXTURE = {'base': (True, 'TC_DEFAULT'), 'emissive': (True, 'TC_DEFAULT'), 'normal': (False, 'TC_NORMALMAP'),
                'metallic_roughness': (False, 'TC_MASKS'), 'occlusion': (False, 'TC_MASKS')}
# (parent object, field, role) of each glTF texture slot a material can name
TEXTURE_SLOTS = (('pbrMetallicRoughness', 'baseColorTexture', 'base'),
                 ('pbrMetallicRoughness', 'metallicRoughnessTexture', 'metallic_roughness'),
                 (None, 'normalTexture', 'normal'), (None, 'occlusionTexture', 'occlusion'),
                 (None, 'emissiveTexture', 'emissive'))
PACKAGE_PREFIX = '/Game/BelmonteTrain/Source/SM_BT_'
DONOR_ENV = 'YV2_DONOR_BUILD'


class PlanError(RuntimeError):
    pass


def donor_default() -> Path | None:
    root = os.environ.get(DONOR_ENV)
    return Path(root).expanduser() / 'belmonte-train' if root else None


# --- the donor's GLBs -------------------------------------------------------------------------------------------------------

def read_glb(path: Path) -> tuple[dict, bytes]:
    """(glTF JSON, binary chunk) of a binary glTF file."""
    data = path.read_bytes()
    if data[:4] != b'glTF':
        raise PlanError(f'{path.name}: not a binary glTF')
    size = struct.unpack_from('<I', data, 12)[0]
    doc = json.loads(data[20:20 + size])
    body = data[20 + size + 8:]
    return doc, body


def image_bytes(doc: dict, body: bytes, index: int) -> bytes:
    view = doc['bufferViews'][doc['images'][index]['bufferView']]
    start = view.get('byteOffset', 0)
    return body[start:start + view['byteLength']]


def texture_packages(doc: dict) -> list[tuple[str, int]]:
    """Per glTF texture: (its Interchange package name, its image index). A repeated image is named <image><k>."""
    seen, out = {}, []
    for texture in doc.get('textures', []):
        image = texture['source']
        name = doc['images'][image]['name']
        k = seen.get(image, 0)
        seen[image] = k + 1
        out.append((name if k == 0 else f'{name}{k}', image))
    return out


def texture_roles(doc: dict) -> dict[int, set[str]]:
    """glTF texture index -> the roles the materials give it."""
    roles: dict[int, set[str]] = {}
    for material in doc.get('materials', []):
        for group, field_, role in TEXTURE_SLOTS:
            holder = material.get(group, {}) if group else material
            if field_ in holder:
                roles.setdefault(holder[field_]['index'], set()).add(role)
    return roles


@dataclass
class Donor:
    """One unit LOD's GLB, read: the file, its pin, and its images and textures by name."""
    unit: str
    lod: int
    name: str                 # SM_BT_<V>_LOD<n>.glb
    path: Path                # the donor file (read only)
    sha: str
    doc: dict
    body: bytes
    textures: list            # [(package name, image index, glTF texture index)]


def pinned_shas(donor: Path) -> dict[str, str]:
    """GLB file name -> the sha256 the donor's import-report.json pins (every vehicle source)."""
    report = json.loads((donor / 'service' / 'import-report.json').read_text())
    out = {}
    for vehicle in report['vehicles'].values():
        out.update(vehicle.get('sources', {}))
    return out


def read_donor(donor: Path) -> dict[tuple[str, int], Donor]:
    pins = pinned_shas(donor)
    glbs = {}
    for unit, mesh in UNITS.items():
        for lod in LODS:
            name = f'SM_BT_{mesh}_LOD{lod}.glb'
            path = donor / unit / name
            if not path.is_file():
                raise PlanError(f'{unit}: {name} is missing from the donor')
            sha = hashlib.sha256(path.read_bytes()).hexdigest()
            if pins.get(name) != sha:
                raise PlanError(f'{unit}/{name}: its sha256 is not the donor report\'s pin')
            doc, body = read_glb(path)
            names = texture_packages(doc)
            glbs[(unit, lod)] = Donor(unit, lod, name, path, sha, doc, body, [(n, img, i) for i, (n, img) in enumerate(names)])
    return glbs


# --- the planned records ----------------------------------------------------------------------------------------------------

@dataclass
class TextureRec:
    id: str
    unit: str
    lod: int
    package: str
    name: str                 # the texture's package name, e.g. T_BT_Walnut1
    donor_file: Path          # textures/<image>.png|jpg (read only)
    sha: str
    srgb: bool
    compression: str
    roles: list
    owner: str = ''

    @property
    def source_name(self) -> str:
        return self.donor_file.name


@dataclass
class MaterialRec:
    id: str
    unit: str
    lod: int
    owner: str
    glb: str                  # SM_BT_<V>_LOD<n>.glb: the donor GLB the facts were read from (not committed)
    instances: list           # [{package, parent, base, metallic, roughness, clearcoat, emissive, two_sided, textures}]
    inputs: list              # texture record IDs the instances bind (input_dependencies: their verified state is an input)
    outputs: list = field(default_factory=list)


@dataclass
class Plan:
    textures: list
    materials: list
    unmapped: list
    donor: Path
    packages: dict            # package -> record ID (every planned package)

    def record_ids(self, unit: str) -> list[str]:
        return sorted({r.id for r in self.textures + self.materials if r.unit == unit})


def donor_texture_file(donor: Path, image: str) -> Path:
    found = [p for p in (donor / 'textures').glob(f'{image}.*') if p.suffix in ('.png', '.jpg')]
    if len(found) != 1:
        raise PlanError(f'{image}: {len(found)} donor image files, not one')
    return found[0]


def texture_settings(roles: set[str]) -> tuple[bool, str] | None:
    """(sRGB, compression) of a texture whose roles are one class; None when the roles mix classes or are empty."""
    if not roles:
        return None
    settings = {ROLE_TEXTURE[r] for r in roles}
    return settings.pop() if len(settings) == 1 else None


def residual_outputs(game: Path, unit: str) -> list[str]:
    path = game / RECORDS / unit / 'asset.toml'
    if not path.is_file():
        raise PlanError(f'{RECORDS}/{unit} is gone: the move is done (state), so the donor plan no longer applies')
    asset = records.load_asset(path)
    return [o.package for o in asset.outputs]


def record_id_for_texture(unit: str, lod: int, name: str) -> str:
    return f'texture/belmontetrain/{unit}-lod{lod}-{recover.slug(name[len("T_BT_"):])}'


def record_id_for_material(unit: str, lod: int) -> str:
    return f'material/belmontetrain/{unit}-lod{lod}'


def plan(game: Path, donor: Path) -> Plan:
    """The planned records of the 459 packages, read from the donor only. Packages that do not bind are reported."""
    glbs = read_donor(donor)
    textures, materials, unmapped, packages = [], [], [], {}
    for unit in UNITS:
        owned = residual_outputs(game, unit)
        for lod in LODS:
            glb = glbs[(unit, lod)]
            folder = FOLDER.format(v=UNITS[unit], n=lod)
            mine = [p for p in owned if p.startswith(folder)]
            roles = texture_roles(glb.doc)
            names_by_index = {i: n for n, _, i in glb.textures}
            # textures
            for name, image, index in glb.textures:
                package = folder + name
                if package not in mine:
                    unmapped.append(f'{package}: no residual record owns it (the GLB texture has no output)')
                    continue
                image_name = glb.doc['images'][image]['name']
                donor_file = donor_texture_file(donor, image_name)
                if hashlib.sha256(image_bytes(glb.doc, glb.body, image)).hexdigest() != hashlib.sha256(
                        donor_file.read_bytes()).hexdigest():
                    unmapped.append(f'{package}: the GLB image is not the donor file {donor_file.name}')
                    continue
                settings = texture_settings(roles.get(index, set()))
                if settings is None:
                    unmapped.append(f'{package}: its roles {sorted(roles.get(index, set()))} are unset or mixed')
                    continue
                rid = record_id_for_texture(unit, lod, name)
                textures.append(TextureRec(rid, unit, lod, package, name, donor_file,
                                           hashlib.sha256(donor_file.read_bytes()).hexdigest(), settings[0], settings[1],
                                           sorted(roles.get(index, set())), f'shared/belmontetrain/{unit}'))
                packages[package] = rid
            # material instances
            bound = []
            refs = set()
            glb_materials = {m['name']: m for m in glb.doc.get('materials', [])}
            for mat_name, mat in glb_materials.items():
                package = folder + mat_name
                if package not in mine:
                    unmapped.append(f'{package}: the GLB material has no residual output')
                    continue
                mode = mat.get('alphaMode', 'OPAQUE')
                extensions = mat.get('extensions', {})
                if mode not in PARENT_NAMES or set(extensions) - EXTENSIONS_OK:
                    unmapped.append(f'{package}: alphaMode {mode} or extensions {sorted(extensions)} have no known parent')
                    continue
                pbr = mat.get('pbrMetallicRoughness', {})
                textures_of = {}
                for group, field_, role in TEXTURE_SLOTS:
                    holder = mat.get(group, {}) if group else mat
                    if field_ in holder:
                        textures_of[role] = folder + names_by_index[holder[field_]['index']]
                if set(textures_of) - {'base'}:
                    unmapped.append(f'{package}: its {sorted(set(textures_of) - {"base"})} texture parameters are not confirmed')
                    continue
                refs.update(record_id_for_texture(unit, lod, t.rsplit('/', 1)[1]) for t in textures_of.values())
                clearcoat = 'KHR_materials_clearcoat' in extensions
                emissive = mat.get('emissiveFactor', [0.0, 0.0, 0.0])
                strength = extensions.get('KHR_materials_emissive_strength', {}).get('emissiveStrength', 1.0)
                bound.append({'package': package, 'parent': parent_of(mode, clearcoat, bool(mat.get('doubleSided', False))),
                              'base': list(pbr.get('baseColorFactor', [1, 1, 1, 1])),
                              'metallic': float(pbr.get('metallicFactor', 1.0)),
                              'roughness': float(pbr.get('roughnessFactor', 1.0)),
                              'clearcoat': float(extensions['KHR_materials_clearcoat'].get('clearcoatFactor', 0.0))
                              if clearcoat else None,
                              'emissive': list(emissive), 'emissive_strength': float(strength),
                              'two_sided': bool(mat.get('doubleSided', False)), 'textures': textures_of})
            for package in mine:
                if package.rsplit('/', 1)[1].startswith('M_BT_') and package not in {b['package'] for b in bound}:
                    unmapped.append(f'{package}: no GLB material binds it')
            if bound:
                rid = record_id_for_material(unit, lod)
                materials.append(MaterialRec(rid, unit, lod, f'shared/belmontetrain/{unit}', glb.name,
                                             bound, sorted(refs), [b['package'] for b in bound]))
                for b in bound:
                    packages[b['package']] = rid
    return Plan(textures, materials, unmapped, donor, packages)


# --- the record text ---------------------------------------------------------------------------------------------------------

def texture_text(rec: TextureRec) -> str:
    lines = [f'# Planned from the donor Belmonte train (tools/migrate/belmontetrain_materials.py): {rec.name} in '
             f'{rec.unit} LOD{rec.lod}, the donor image {rec.source_name}.',
             '# The donor file is committed in src/ and pinned by sha256; the record is imported by the V2 editor and',
             '# verified by tools/import/run.py, never edited by hand.',
             'schema = 1', f'id = "{rec.id}"', 'kind = "texture"', 'authority = "generated"', f'owner = "{rec.owner}"',
             '', '[[sources]]', f'path = "src/{rec.source_name}"', f'sha256 = "{rec.sha}"',
             '', '[recipe]', 'importer = "texture"', 'version = 1', '', '[recipe.settings]',
             f'srgb = {"true" if rec.srgb else "false"}', f'compression = "{rec.compression}"',
             f'lod_group = "{LOD_GROUP}"', f'address = "{ADDRESS}"',
             '', '[[outputs]]', f'package = "{rec.package}"', '']
    return '\n'.join(lines)


# The parameter names the committed bytes carry (BaseColorTexture, BaseColorFactor, RoughnessFactor, MetallicFactor,
# ClearCoatFactor, EmissiveFactor, EmissiveStrength). The static switches are not written: the bytes do not show their values.
# The switches every instance's parent has, all on in the parent and all off in the read (the read's effective values).
# bHasSpecularColorTexture is in neither parent, so it is never stated. The anisotropy switch is named by the non-clear-coat
# parents and bHasClearCoatTexture by the clear-coat parent; each row states only the one its parent has.
SWITCHES_OFF = ('bHasNormalTexture', 'bHasEmissiveTexture', 'bHasOcclusionTexture', 'bHasMetallicRoughnessTexture',
                'bHasSpecularTexture', 'bHasIridescence')


def instance_row(inst: dict) -> dict:
    """One instance's record row: {package, parent, textures, scalars, vectors}, its values exactly as the GLB states them."""
    scalars = {'MetallicFactor': inst['metallic'], 'RoughnessFactor': inst['roughness']}
    vectors = {'BaseColorFactor': list(inst['base'])}
    textures = {'BaseColorTexture': inst['textures']['base']} if 'base' in inst['textures'] else {}
    if inst['clearcoat'] is not None:
        scalars['ClearCoatFactor'] = inst['clearcoat']
    if any(inst['emissive']):
        vectors['EmissiveFactor'] = [*inst['emissive'], 1.0]
        scalars['EmissiveStrength'] = inst['emissive_strength']
    # The static switches the GLB's textures decide: BaseColorTexture on when the base texture is set, the others off
    # (ClearCoatTexture only on a clear-coat instance). The read confirms them; the bytes do not show their values.
    switches = {'bHasBaseColorTexture': 'base' in inst['textures']}
    switches.update({name: False for name in SWITCHES_OFF})
    if inst['clearcoat'] is not None:
        switches['bHasClearCoatTexture'] = False
    else:
        switches['bHasAnisotropyTextureAndOrRotation'] = False
    return {'package': inst['package'], 'parent': inst['parent'], 'textures': textures, 'scalars': scalars,
            'vectors': vectors, 'switches': switches}


def material_text(rec: MaterialRec) -> str:
    lines = [f'# Planned from the donor Belmonte train (tools/migrate/belmontetrain_materials.py): the {len(rec.instances)} '
             f'material instances of {rec.unit} LOD{rec.lod}, read from the donor {rec.glb} (not committed).',
             "# The instances' parameters are the GLB facts, confirmed by the committed bytes; the import writes each",
             '# instance from its row and reads every value back. Built by the V2 editor, never edited by hand.',
             'schema = 1', f'id = "{rec.id}"', 'kind = "material-instance"', 'authority = "generated"',
             f'owner = "{rec.owner}"', 'input_dependencies = [' + ', '.join(f'"{r}"' for r in rec.inputs) + ']',
             '', '[recipe]', 'importer = "material-instance"', 'version = 2', '', '[recipe.settings]']
    for inst in rec.instances:
        row = instance_row(inst)
        lines += ['', '[[recipe.settings.instances]]', f'package = "{row["package"]}"', f'parent = "{row["parent"]}"']
        for key in ('textures', 'scalars', 'vectors', 'switches'):
            if row[key]:
                lines.append(f'{key} = {recover._toml(row[key])}')
    lines += ['']
    for package in rec.outputs:
        lines += ['[[outputs]]', f'package = "{package}"', '']
    return '\n'.join(lines)


def record_folder(rid: str) -> str:
    """assets/<first ID segment>/<rest> for a record ID."""
    return 'assets/' + rid


# --- the byte checks ----------------------------------------------------------------------------------------------------

def package_path(game: Path, package: str) -> Path:
    return game / 'unreal' / 'Content' / (package[len('/Game/'):] + '.uasset')


def _float32(value: float) -> bytes:
    return struct.pack('<f', value)


def byte_check(game: Path, plan: Plan) -> dict[str, tuple[str, list[str]]]:
    """package -> (status, notes). `determined`: every checked fact is in the committed bytes (and nothing failed).
    `read`: a fact is missing or not checkable from the bytes and needs the native read. `no bytes`: an LFS pointer."""
    out = {}
    for rec in plan.textures:
        path = package_path(game, rec.package)
        if not path.is_file() or records.is_lfs_pointer(path):
            out[rec.package] = ('no bytes', ['the committed package is an LFS pointer or missing'])
            continue
        data = path.read_bytes()
        notes = []
        if ENUM_NAMES[rec.compression].encode() not in data:
            notes.append(f'compression {ENUM_NAMES[rec.compression]} is not in the bytes')
        if b'TEXTUREGROUP_World' not in data:
            notes.append('TEXTUREGROUP_World is not in the bytes')
        if b'TA_Wrap' not in data:
            notes.append('TA_Wrap is not in the bytes')
        notes.append('sRGB flag not in the bytes: native read')
        out[rec.package] = ('read', notes)
    for rec in plan.materials:
        for inst in rec.instances:
            path = package_path(game, inst['package'])
            if not path.is_file() or records.is_lfs_pointer(path):
                out[inst['package']] = ('no bytes', ['the committed package is an LFS pointer or missing'])
                continue
            data = path.read_bytes()
            notes = []
            if inst['parent'].encode() not in data:
                notes.append('parent path is not in the bytes')
            # A default value (white, metallic 1, no emission, clear-coat 0) is not stored, so it is not checked.
            if inst['base'] != [1, 1, 1, 1] and struct.pack('<4f', *inst['base']) not in data:
                notes.append('base colour is not in the bytes')
            if inst['metallic'] != 1.0 and _float32(inst['metallic']) not in data:
                notes.append('metallic is not in the bytes')
            if _float32(inst['roughness']) not in data:
                notes.append('roughness is not in the bytes')
            if inst['clearcoat'] is not None and inst['clearcoat'] != 0.0 and _float32(inst['clearcoat']) not in data:
                notes.append('clear-coat factor is not in the bytes')
            if any(inst['emissive']) and struct.pack('<3f', *inst['emissive']) not in data:
                notes.append('emissive colour is not in the bytes')
            if inst['emissive_strength'] != 1.0 and _float32(inst['emissive_strength']) not in data:
                notes.append('emissive strength is not in the bytes')
            if inst['two_sided'] and b'TwoSided' not in data:
                notes.append('two-sided is not in the bytes')
            for role, package in sorted(inst['textures'].items()):
                if package.encode() not in data:
                    notes.append(f'{role} texture {package.rsplit("/", 1)[1]} is not referenced by the bytes')
            out[inst['package']] = ('determined' if not notes else 'read', notes or ['all checked facts are in the bytes'])
    return out


# --- the claim ------------------------------------------------------------------------------------------------------------------

def adopted_state(game: Path) -> str:
    """`pending` (the seven records hold the 459 outputs), `moved` (none are left, the new records exist)."""
    listed = 0
    for unit in UNITS:
        path = game / RECORDS / unit / 'asset.toml'
        if path.is_file():
            listed += len(residual_outputs(game, unit))
    if listed == 459:
        return 'pending'
    if listed == 0:
        return 'moved'
    raise PlanError(f'the seven records list {listed} of the 459 outputs; resolve by hand, nothing changed')


def build_writes(game: Path, plan: Plan) -> dict:
    """The one write: {'writes': {game-relative path: bytes}, 'deletes': [game-relative path]} for the claimed move."""
    writes, deletes = {}, []
    for rec in plan.textures:
        rel = record_folder(rec.id) + '/asset.toml'
        writes[rel] = texture_text(rec).encode()
        writes[record_folder(rec.id) + '/src/' + rec.source_name] = rec.donor_file.read_bytes()
    for rec in plan.materials:
        writes[record_folder(rec.id) + '/asset.toml'] = material_text(rec).encode()
    moved = set(plan.packages)
    adopted_ids = {f'adopted/belmontetrain/{unit}' for unit in UNITS}
    for unit in UNITS:
        rel = f'{RECORDS}/{unit}/asset.toml'
        text = (game / rel).read_text()
        packages = set(residual_outputs(game, unit))
        if not packages <= moved:
            raise PlanError(f'{unit}: {sorted(packages - moved)[:3]} have no planned record')
        new = recover._drop_outputs(text, packages)
        if tomllib.loads(new).get('outputs'):
            raise PlanError(f'{rel}: outputs remain after the move; refused')
        deletes.append(rel)
        verified = game / RECORDS / unit / 'verified.json'
        if verified.is_file():
            stems = {'unreal/Content/' + p[len('/Game/'):] for p in packages}
            strays = [k for k in json.loads(verified.read_text()).get('files', {}) if k.rsplit('.', 1)[0] not in stems]
            if strays:
                raise PlanError(f'{RECORDS}/{unit}/verified.json lists {strays[0]}, not a moved package; refused')
            deletes.append(f'{RECORDS}/{unit}/verified.json')
    units_text = (game / UNITS_REL).read_text()
    units = json.loads(units_text)
    if json.dumps(units, indent=1, ensure_ascii=False) + '\n' != units_text:
        raise PlanError(f'{UNITS_REL} is not in the form adoption writes; edit it by hand')
    for package in moved:
        units.get('packages', {}).pop(package, None)
    new_units = (json.dumps(units, indent=1, ensure_ascii=False) + '\n').encode()
    if new_units != units_text.encode():
        writes[UNITS_REL] = new_units
    # records that point at an adopted unit now point at that unit's new records
    for path in records.record_paths(game):
        rel = path.relative_to(game).as_posix()
        if path.parent.name in UNITS and rel.startswith(RECORDS + '/'):
            continue
        text = path.read_text()
        match = re.search(r'(?m)^references = \[(.*)\]$', text)
        if not match:
            continue
        refs = re.findall(r'"([^"]+)"', match.group(1))
        hit = [r for r in refs if r in adopted_ids]
        if not hit:
            continue
        units_hit = [r.rsplit('/', 1)[1] for r in hit]
        new_refs = [r for r in refs if r not in adopted_ids]
        for unit in units_hit:
            new_refs += plan.record_ids(unit)
        new_refs = sorted(set(new_refs))
        line = 'references = [' + ', '.join(f'"{r}"' for r in new_refs) + ']'
        writes[rel] = text[:match.start()].encode() + line.encode() + text[match.end():].encode()
    return {'writes': writes, 'deletes': sorted(set(deletes))}


def claimed_paths(ops: dict) -> list[str]:
    return sorted(set(ops['writes']) | set(ops['deletes']))


def materialize(game: Path, plan: Plan, claim: str, *, lockable=apply.lockable_present, echo=print) -> str:
    """The claimed move. Recovers an interrupted journal first; a second run after the move changes nothing."""
    apply.Journal(game).recover(claim)
    if adopted_state(game) == 'moved':
        echo('materialize: already moved; nothing written')
        return 'moved'
    ops = build_writes(game, plan)
    try:
        authority.authorize([f'{GAME_REL}/{rel}' for rel in claimed_paths(ops)], claim, 'Belmonte train material records',
                            scopes=SCOPES)
    except authority.Unauthorized as error:
        raise PlanError(str(error)) from None
    apply.execute(game, ops, scopes=SCOPES, lockable=lockable)
    if adopted_state(game) != 'moved':
        raise PlanError('the move did not leave the records empty; restore from the journal and report')
    echo(f'materialize: {len(plan.textures)} texture and {len(plan.materials)} material-instance record(s) written; '
         f'{len(plan.packages)} packages moved')
    return 'moved'


# --- reporting ---------------------------------------------------------------------------------------------------------------

def summary(plan: Plan, checks: dict) -> str:
    counts = {}
    for status, _ in checks.values():
        counts[status] = counts.get(status, 0) + 1
    lines = [f'textures: {len(plan.textures)} record(s); material-instance groups: {len(plan.materials)} record(s); '
             f'packages planned: {len(plan.packages)}; unmapped: {len(plan.unmapped)}',
             'byte checks: ' + ', '.join(f'{k} {v}' for k, v in sorted(counts.items()))]
    lines += [f'  unmapped: {u}' for u in plan.unmapped[:10]]
    return '\n'.join(lines)


def table(plan: Plan, checks: dict) -> str:
    rows = ['| Package | Planned record | Donor evidence | Committed bytes | Status and read job |',
            '|---|---|---|---|---|']
    for rec in plan.textures:
        status, notes = checks.get(rec.package, ('no bytes', []))
        rows.append(f'| `{rec.package}` | `{rec.id}` (texture) | {rec.source_name} pinned, sha256 `{rec.sha[:10]}…` | '
                    f'{"; ".join(notes) or "checked"} | settled by the read: sRGB true, TC_DEFAULT, TEXTUREGROUP_WORLD, TA_WRAP (belmontetrain-read.json) |')
    for rec in plan.materials:
        for inst in rec.instances:
            status, notes = checks.get(inst['package'], ('no bytes', []))
            rows.append(f'| `{inst["package"]}` | `{rec.id}` (material-instance) | {rec.glb}, parent `{inst["parent"].rsplit("/", 1)[1]}` | '
                        f'{"; ".join(notes)} | settled by the read: parent, textures, values, alpha and bHas* switches agree (belmontetrain-read.json) |')
    return '\n'.join(rows)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Plan the residual Belmonte train texture and material records (see the docstring).')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--table', action='store_true', help='print the markdown table of the 459 packages')
    mode.add_argument('--paths', action='store_true', help='print every path and scope a claim needs, and exit')
    mode.add_argument('--claim', metavar='TASK', help='write the records and move the outputs under this claim')
    parser.add_argument('--donor', metavar='DIR', help='the donor belmonte-train folder (default: $YV2_DONOR_BUILD/belmonte-train)')
    args = parser.parse_args(argv)
    donor = Path(args.donor).expanduser() if args.donor else donor_default()
    if donor is None or not donor.is_dir():
        print('belmontetrain_materials: no donor folder (pass --donor or set YV2_DONOR_BUILD)', file=sys.stderr)
        return 1
    try:
        current, detail = state(GAME)
        if current == 'done':
            print(f'belmontetrain_materials: {detail}; nothing to claim (plan mode reads the records with records_plan)')
            return 0
        plan_ = plan(GAME, donor)
        if args.claim:
            materialize(GAME, plan_, args.claim)
            return 0
        if args.paths:
            ops = build_writes(GAME, plan_)
            print('\n'.join(f'{GAME_REL}/{rel}' for rel in claimed_paths(ops)))
            print('scopes: ' + ' '.join(SCOPES))
            return 0
        checks = byte_check(GAME, plan_)
        print(table(plan_, checks) if args.table else summary(plan_, checks))
        return 0
    except (PlanError, records.RecordError, apply.SplitError) as error:
        print(f'belmontetrain_materials: {error}', file=sys.stderr)
        return 1



# --- the evidence: the two native reads, compacted to what the records assert -------------------------------------------

TEXTURE_KEYS = ('srgb', 'compression', 'lod_group', 'address_x', 'address_y')
TOLERANCE = 1e-4


def _enum(value):
    """A read enum's bare name: the read's text may keep its index ("TC_DEFAULT: 0>"), which is dropped."""
    return value.split(':')[0].split('.')[-1].strip('<> ') if value else value


def _path(value):
    """A read object path without its ".Name" suffix: "<package>.<name>" -> "<package>"."""
    return value.split('.')[0] if value else None


def planned_rows(plan: Plan) -> dict:
    """package -> the row each material instance states. A planned instance computes its row from the GLB facts; a written
    record (records_plan) carries the row it states."""
    out = {}
    for rec in plan.materials:
        for inst in rec.instances:
            out[inst['package']] = inst['row'] if 'row' in inst else instance_row(inst)
    return out


def evidence(plan: Plan, materials_read: dict, textures_read: dict) -> dict:
    """The compact evidence of the two reads (the report_materials.py and report_textures.py rows), per package, with
    only what the records assert: a material's parent, its stated texture, scalar and vector values, and each switch the
    row states or whose effective value differs from its parent; a texture's five settings."""
    materials = {}
    for package, row in planned_rows(plan).items():
        read = materials_read[package]
        names = set(read['switches']) | set(row['switches'])
        switches = {}
        for name in sorted(names):
            got = read['switches'].get(name)
            if got is None:
                switches[name] = {'effective': None, 'parent': None}
            elif name in row['switches'] or got['effective'] != got['parent']:
                switches[name] = {'effective': got['effective'], 'parent': got['parent']}
        materials[package] = {
            'parent': _path(read['parent']),
            'textures': {k: _path(read['effective']['texture'].get(k)) for k in row['textures']},
            'scalars': {k: read['effective']['scalar'].get(k) for k in row['scalars']},
            'vectors': {k: read['effective']['vector'].get(k) for k in row['vectors']},
            'switches': switches}
    textures = {rec.package: {k: (_enum(v) if isinstance(v, str) else v)
                             for k, v in ((k, textures_read[rec.package][k]) for k in TEXTURE_KEYS)}
                for rec in plan.textures}
    return {'materials': materials, 'textures': textures}


def disagreements(plan: Plan, ev: dict) -> list:
    """Every way the plan disagrees with the evidence (empty when it agrees): a parent, texture, scalar or vector value
    (its alpha too), a switch the row states that the read does not confirm, and a switch whose read value differs from
    its parent that the row does not state."""
    out = []
    for package, row in planned_rows(plan).items():
        got = ev['materials'].get(package)
        if got is None:
            out.append(f'{package}: no evidence')
            continue
        if got['parent'] != row['parent']:
            out.append(f'{package}: parent {got["parent"]} is not {row["parent"]}')
        for k, v in row['textures'].items():
            if got['textures'].get(k) != v:
                out.append(f'{package}: {k} {got["textures"].get(k)} is not {v}')
        for k, v in row['scalars'].items():
            if got['scalars'].get(k) is None or abs(got['scalars'][k] - v) > TOLERANCE:
                out.append(f'{package}: {k} {got["scalars"].get(k)} is not {v}')
        for k, v in row['vectors'].items():
            value = got['vectors'].get(k)
            if value is None or len(value) != len(v) or max(abs(a - b) for a, b in zip(value, v)) > TOLERANCE:
                out.append(f'{package}: {k} {value} is not {v}')
        for name, switch in got['switches'].items():
            if switch['effective'] is None:
                out.append(f'{package}: {name} is not read')
                continue
            if switch['effective'] != switch['parent'] and name not in row['switches']:
                out.append(f'{package}: {name} differs from its parent and the row does not state it')
            want = row['switches'].get(name, switch['parent'])
            if switch['effective'] != want:
                out.append(f'{package}: {name} reads {switch["effective"]} not {want}')
    for rec in plan.textures:
        got = ev['textures'].get(rec.package)
        if got is None:
            out.append(f'{rec.package}: no texture evidence')
            continue
        want = {'srgb': rec.srgb, 'compression': rec.compression, 'lod_group': LOD_GROUP,
                'address_x': 'TA_WRAP', 'address_y': 'TA_WRAP'}
        for k in TEXTURE_KEYS:
            if got[k] != want[k]:
                out.append(f'{rec.package}: {k} {got[k]} is not {want[k]}')
    return out


# --- the states: `unprepared` (the seven adopted records hold the packages) or `done` (the written records do) -------------

LIST_FILES = {'textures': 'docs/inventory/belmontetrain-texture-packages.txt',
              'materials': 'docs/inventory/belmontetrain-material-packages.txt'}
WRITTEN_PREFIXES = ('texture/belmontetrain/', 'material/belmontetrain/')
WRITTEN_COUNT = 159


def expected_packages() -> dict:
    """The packages the plan covers, from the committed lists: {'textures': [...], 'materials': [...]}."""
    return {kind: (GAME / rel).read_text().split() for kind, rel in LIST_FILES.items()}


def state(game: Path) -> tuple:
    """(state, detail). `unprepared`: the seven adopted records list the 459 packages and no written record exists. `done`: the
    159 written records list them and no adopted record does. Anything else is refused, never guessed."""
    wanted = set(sum(expected_packages().values(), []))
    adopted = set()
    for unit in UNITS:
        path = game / RECORDS / unit / 'asset.toml'
        if path.is_file():
            adopted |= {o.package for o in records.load_asset(path).outputs}
    written, count = set(), 0
    for path in records.record_paths(game):
        asset = records.load_asset(path)
        if asset.id.startswith(WRITTEN_PREFIXES):
            count += 1
            written |= {o.package for o in asset.outputs}
    if adopted & wanted == wanted and not written & wanted:
        return 'unprepared', f'{len(wanted)} packages in the seven adopted records; prepare with --claim'
    if not adopted & wanted and written & wanted == wanted and count == WRITTEN_COUNT:
        return 'done', f'{WRITTEN_COUNT} records list the packages; the seven adopted records list none'
    raise PlanError(f'partly moved: {len(adopted & wanted)} adopted, {len(written & wanted)} written package(s); resolve by hand')


def records_plan(game: Path) -> Plan:
    """The plan as the written records state it (the done state): each texture's settings, and each material instance's row as
    the record states it. The evidence is checked against this, with no donor."""
    textures, materials = [], []
    for path in records.record_paths(game):
        asset = records.load_asset(path)
        if not asset.id.startswith(WRITTEN_PREFIXES):
            continue
        unit = asset.owner.rsplit('/', 1)[-1]
        if asset.kind == 'texture':
            settings = asset.recipe['settings']
            package = asset.outputs[0].package
            textures.append(TextureRec(asset.id, unit, 0, package, package.rsplit('/', 1)[1], None,
                                       asset.sources[0].sha256, bool(settings['srgb']), settings['compression'], [],
                                       asset.owner))
        elif asset.kind == 'material-instance':
            instances = []
            for row in asset.recipe['settings']['instances']:
                stated = {'package': row['package'], 'parent': row['parent'], 'textures': row.get('textures', {}),
                          'scalars': row.get('scalars', {}), 'vectors': row.get('vectors', {}),
                          'switches': row.get('switches', {})}
                instances.append({'package': row['package'], 'row': stated})
            materials.append(MaterialRec(asset.id, unit, 0, asset.owner, '', instances, sorted(asset.input_dependencies),
                                         [o.package for o in asset.outputs]))
    return Plan(textures, materials, [], None, {})



if __name__ == '__main__':
    raise SystemExit(main())
