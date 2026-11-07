"""Read the header of an uncooked Unreal Engine 5 package (.uasset/.umap) without the engine.

The reader understands the package file summary, the name and import tables and the asset registry block an editor
save writes into every package. For a World Partition external actor package (One File Per Actor) it also reads the
actor descriptor the editor stores in the `ActorMetaData` tag: the actor GUID, its classes and its transform, and
names the map that owns the actor.

Only the layouts proven on Unreal Engine 5 editor saves are accepted: little-endian, versioned, uncompressed and not
cooked. Anything else raises `UnsupportedPackage` naming the reason; a damaged header raises `CorruptPackage`. The
reader never guesses at an unknown layout. Standard library only.

    python -m atelier.unreal_package_summary PATH.uasset ...   # prints JSON summaries
"""
from __future__ import annotations

import base64
import binascii
import json
import struct
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

PACKAGE_FILE_TAG = 0x9E2A83C1
PACKAGE_FILE_TAG_SWAPPED = 0xC1832A9E
SUPPORTED_LEGACY_VERSIONS = (-8, -9)     # -8 added the UE5 version; -9 only changed early-exit rules
UE4_FINAL_VERSION = 522                  # every UE5 package carries the last UE4 object version
UE5_INITIAL = 1000

# UE5 object versions that change the summary or the import table (EUnrealEngineObjectUE5Version).
UE5_NAMES_REFERENCED_FROM_EXPORT_DATA = 1001
UE5_PAYLOAD_TOC = 1002
UE5_OPTIONAL_RESOURCES = 1003
UE5_ADD_SOFTOBJECTPATH_LIST = 1008
UE5_DATA_RESOURCES = 1009
UE5_METADATA_SERIALIZATION_OFFSET = 1014
UE5_VERSE_CELLS = 1015
UE5_PACKAGE_SAVED_HASH = 1016
UE5_IMPORT_TYPE_HIERARCHIES = 1018
UE5_NEWEST_KNOWN = 1018                  # Unreal Engine 5.8; newer packages are refused, not guessed

PKG_EDITOR_ONLY = 0x00000040
PKG_COOKED = 0x00000200
PKG_CONTAINS_NO_ASSET = 0x00000400
PKG_UNVERSIONED_PROPERTIES = 0x00002000
PKG_CONTAINS_MAP_DATA = 0x00004000
PKG_CONTAINS_MAP = 0x00020000
PKG_FILTER_EDITOR_ONLY = 0x80000000

EXTERNAL_ROOTS = ('__ExternalActors__', '__ExternalObjects__')

# Custom versions that gate the start of a World Partition actor descriptor, and the minimum each must have for the
# layout read here: [bIsDefaultActorDesc][BaseClass][NativeClass][Guid][relative transform, doubles].
UE5_MAIN_STREAM = '697DD581E64F41ABAA4A51ECBEB7B628'
UE5_RELEASE_STREAM = 'D89B5E4224BD4D468412ACA8DF641779'
FORTNITE_MAIN = '601D1886AC644F84AA16D3DE0DEAC7D6'
FORTNITE_SEASON = '5B4C06B724634AF8805BBF70CDF5D0DD'
ACTOR_DESC_MINIMUM = {
    UE5_MAIN_STREAM: 88,      # WorldPartitionActorDescActorAndClassPaths: classes as (package, asset) paths
    UE5_RELEASE_STREAM: 28,   # LargeWorldCoordinates: transforms in doubles
    FORTNITE_MAIN: 177,       # WorldPartitionActorDescSerializeRelativeTransform (implies ClassDescSerialize, 88)
    FORTNITE_SEASON: 11,      # WorldPartitionActorDescActorTransformSerialization (implies base class, 5)
}

MAX_STRING = 1 << 20
MAX_COUNT = 1 << 24


class PackageError(ValueError):
    """The bytes are not a package this reader can describe; the message says why."""


class UnsupportedPackage(PackageError):
    """A real package in a layout or version this reader refuses to interpret."""


class CorruptPackage(PackageError):
    """A truncated or inconsistent header."""


@dataclass(frozen=True)
class EngineVersion:
    major: int
    minor: int
    patch: int
    changelist: int
    branch: str

    def __str__(self):
        return f'{self.major}.{self.minor}.{self.patch}-{self.changelist}+{self.branch}'


@dataclass
class Summary:
    legacy_file_version: int
    file_version_ue4: int
    file_version_ue5: int
    file_version_licensee: int
    saved_hash: str                       # hex; FIoHash (20 bytes) since PACKAGE_SAVED_HASH, else the legacy GUID
    total_header_size: int
    custom_versions: dict[str, int]       # GUID (32 upper-case hex digits) -> version
    package_name: str
    package_flags: int
    name_count: int
    name_offset: int
    soft_object_paths_count: int
    soft_object_paths_offset: int
    localization_id: str
    gatherable_text_count: int
    gatherable_text_offset: int
    export_count: int
    export_offset: int
    import_count: int
    import_offset: int
    cell_export_count: int
    cell_export_offset: int
    cell_import_count: int
    cell_import_offset: int
    metadata_offset: int
    depends_offset: int
    soft_package_references_count: int
    soft_package_references_offset: int
    searchable_names_offset: int
    thumbnail_table_offset: int
    import_type_hierarchies_count: int
    import_type_hierarchies_offset: int
    persistent_guid: str
    generations: list[tuple[int, int]]   # (export count, name count)
    saved_by: EngineVersion
    compatible_with: EngineVersion
    package_source: int
    asset_registry_offset: int
    bulk_data_start_offset: int
    world_tile_info_offset: int
    chunk_ids: list[int]
    preload_dependency_count: int
    preload_dependency_offset: int
    names_referenced_from_export_data: int
    payload_toc_offset: int
    data_resource_offset: int
    summary_size: int                     # bytes the summary itself occupies

    @property
    def is_map(self) -> bool:
        return bool(self.package_flags & PKG_CONTAINS_MAP)


@dataclass(frozen=True)
class Import:
    class_package: str
    class_name: str
    outer_index: int
    object_name: str
    package_name: str
    optional: bool


@dataclass
class AssetData:
    object_path: str                      # as stored: relative to the package, or a full path for outer-ed objects
    class_path: str
    tags: dict[str, str] = field(default_factory=dict)


@dataclass
class ExternalActor:
    """What an external actor package says about its actor."""
    map: str | None                       # long package name of the owning map, e.g. /Game/Maps/Island
    actor_path: str | None                # full object path, e.g. /Game/Maps/Island.Island:PersistentLevel.Bench_3
    name: str | None                      # actor object name, e.g. Bench_3
    label: str | None                     # editor label (ActorLabel tag)
    class_path: str | None                # asset registry class (a Blueprint generated class for Blueprint actors)
    native_class: str | None              # ActorMetaDataClass: the nearest native parent class
    base_class: str | None                # Blueprint base class from the descriptor, when there is one
    guid: str | None                      # ActorGuid, 32 upper-case hex digits as Unreal prints it
    location: tuple[float, float, float] | None   # centimetres, relative to the owning level (world for a main map)
    rotation: tuple[float, float, float, float] | None   # quaternion x, y, z, w
    scale: tuple[float, float, float] | None
    descriptor: str                       # 'decoded', 'absent' or 'unsupported: <reason>'


@dataclass
class Package:
    summary: Summary
    names: list[str]
    imports: list[Import]
    assets: list[AssetData]
    actor: ExternalActor | None           # set for packages under __ExternalActors__/__ExternalObjects__

    @property
    def package_name(self) -> str:
        return self.summary.package_name

    @property
    def imported_packages(self) -> list[str]:
        """Long names of the other packages this one imports from (its hard references)."""
        packages = {i.object_name for i in self.imports if i.class_name == 'Package' and i.outer_index == 0}
        packages |= {i.package_name for i in self.imports if i.package_name and i.package_name != 'None'}
        return sorted(p for p in packages if p.startswith('/') and p != self.package_name)


class Reader:
    """Little-endian cursor over package bytes; every read is bounds-checked."""

    def __init__(self, data: bytes, offset: int = 0):
        self.data, self.pos = data, offset

    def take(self, size: int) -> bytes:
        if size < 0 or self.pos + size > len(self.data):
            raise CorruptPackage(f'truncated: needed {size} bytes at offset {self.pos} of {len(self.data)}')
        chunk = self.data[self.pos:self.pos + size]
        self.pos += size
        return chunk

    def unpack(self, fmt: str):
        values = struct.unpack('<' + fmt, self.take(struct.calcsize('<' + fmt)))
        return values[0] if len(values) == 1 else values

    def i32(self) -> int:
        return self.unpack('i')

    def u32(self) -> int:
        return self.unpack('I')

    def i64(self) -> int:
        return self.unpack('q')

    def count(self, what: str) -> int:
        value = self.i32()
        if value < 0 or value > MAX_COUNT:
            raise CorruptPackage(f'invalid {what} count {value} at offset {self.pos - 4}')
        return value

    def guid(self) -> str:
        return ''.join(f'{part:08X}' for part in self.unpack('IIII'))

    def fstring(self) -> str:
        length = self.i32()
        if length == 0:
            return ''
        if abs(length) > MAX_STRING:
            raise CorruptPackage(f'implausible string length {length} at offset {self.pos - 4}')
        if length > 0:
            raw, width, encoding = self.take(length), 1, 'latin-1'
        else:
            raw, width, encoding = self.take(-length * 2), 2, 'utf-16-le'
        if raw[-width:] != b'\0' * width:
            raise CorruptPackage(f'unterminated string ending at offset {self.pos}')
        return raw[:-width].decode(encoding)

    def engine_version(self) -> EngineVersion:
        major, minor, patch = self.unpack('HHH')
        changelist = self.u32()
        return EngineVersion(major, minor, patch, changelist & 0x7FFFFFFF, self.fstring())


def parse_summary(data: bytes) -> Summary:
    """The package file summary at the start of `data`."""
    r = Reader(data)
    if len(data) < 32:
        raise CorruptPackage(f'{len(data)} bytes is too small for a package summary')
    tag = r.u32()
    if tag == PACKAGE_FILE_TAG_SWAPPED:
        raise UnsupportedPackage('byte-swapped (big-endian) package')
    if tag != PACKAGE_FILE_TAG:
        raise PackageError(f'not an Unreal package: tag {tag:#010x}, expected {PACKAGE_FILE_TAG:#010x}')
    legacy = r.i32()
    if legacy not in SUPPORTED_LEGACY_VERSIONS:
        raise UnsupportedPackage(f'legacy file version {legacy}; this reader supports {SUPPORTED_LEGACY_VERSIONS}')
    r.i32()                                                   # legacy UE3 version (always present for -8/-9)
    ue4, ue5, licensee = r.i32(), r.i32(), r.i32()
    if ue4 == 0 and ue5 == 0 and licensee == 0:
        raise UnsupportedPackage('unversioned package (cooked content); only versioned editor saves are supported')
    if ue4 != UE4_FINAL_VERSION:
        raise UnsupportedPackage(f'UE4 object version {ue4}; UE5 packages carry {UE4_FINAL_VERSION}')
    if not UE5_INITIAL <= ue5 <= UE5_NEWEST_KNOWN:
        raise UnsupportedPackage(f'UE5 object version {ue5} is outside the supported {UE5_INITIAL}..{UE5_NEWEST_KNOWN}')
    if licensee != 0:
        raise UnsupportedPackage(f'licensee version {licensee}: a modified engine may change the layout')
    saved_hash, total_header_size = '', 0
    if ue5 >= UE5_PACKAGE_SAVED_HASH:
        saved_hash = r.take(20).hex()
        total_header_size = r.i32()
    custom = {}
    for _ in range(r.count('custom version')):
        key = r.guid()
        custom[key] = r.i32()
    if ue5 < UE5_PACKAGE_SAVED_HASH:
        total_header_size = r.i32()
    package_name = r.fstring()
    flags = r.u32()
    if flags & PKG_FILTER_EDITOR_ONLY or flags & PKG_COOKED:
        raise UnsupportedPackage(f'cooked package (flags {flags:#010x}); only uncooked editor packages are supported')
    name_count, name_offset = r.i32(), r.i32()
    soft_count = soft_offset = 0
    if ue5 >= UE5_ADD_SOFTOBJECTPATH_LIST:
        soft_count, soft_offset = r.i32(), r.i32()
    localization_id = r.fstring()
    gather_count, gather_offset = r.i32(), r.i32()
    export_count, export_offset, import_count, import_offset = r.i32(), r.i32(), r.i32(), r.i32()
    cells = (0, 0, 0, 0)
    if ue5 >= UE5_VERSE_CELLS:
        cells = (r.i32(), r.i32(), r.i32(), r.i32())
    metadata_offset = r.i32() if ue5 >= UE5_METADATA_SERIALIZATION_OFFSET else 0
    depends_offset = r.i32()
    soft_package_count, soft_package_offset = r.i32(), r.i32()
    searchable_names_offset = r.i32()
    thumbnail_offset = r.i32()
    hierarchy_count = hierarchy_offset = 0
    if ue5 >= UE5_IMPORT_TYPE_HIERARCHIES:
        hierarchy_count, hierarchy_offset = r.i32(), r.i32()
    if ue5 < UE5_PACKAGE_SAVED_HASH:
        saved_hash = r.take(16).hex()
    persistent_guid = r.guid()
    generations = [(r.i32(), r.i32()) for _ in range(r.count('generation'))]
    saved_by = r.engine_version()
    compatible_with = r.engine_version()
    compression = r.u32()
    if compression:
        raise UnsupportedPackage(f'package-level compression flags {compression:#x}')
    if r.i32():
        raise UnsupportedPackage('package-level compressed chunks (old cooked content)')
    package_source = r.u32()
    for _ in range(r.count('additional packages to cook')):
        r.fstring()
    asset_registry_offset = r.i32()
    bulk_data_start_offset = r.i64()
    world_tile_info_offset = r.i32()
    chunk_ids = [r.i32() for _ in range(r.count('chunk ID'))]
    preload_count, preload_offset = r.i32(), r.i32()
    names_referenced = r.i32() if ue5 >= UE5_NAMES_REFERENCED_FROM_EXPORT_DATA else name_count
    payload_toc = r.i64() if ue5 >= UE5_PAYLOAD_TOC else -1
    data_resource = r.i32() if ue5 >= UE5_DATA_RESOURCES else -1

    summary = Summary(
        legacy, ue4, ue5, licensee, saved_hash, total_header_size, custom, package_name, flags, name_count,
        name_offset, soft_count, soft_offset, localization_id, gather_count, gather_offset, export_count,
        export_offset, import_count, import_offset, *cells, metadata_offset, depends_offset, soft_package_count,
        soft_package_offset, searchable_names_offset, thumbnail_offset, hierarchy_count, hierarchy_offset,
        persistent_guid, generations, saved_by, compatible_with, package_source, asset_registry_offset,
        bulk_data_start_offset, world_tile_info_offset, chunk_ids, preload_count, preload_offset, names_referenced,
        payload_toc, data_resource, r.pos)
    _check_offsets(summary, len(data))
    return summary


def _check_offsets(s: Summary, size: int):
    header = s.total_header_size
    if header < s.summary_size:
        raise CorruptPackage(f'total header size {header} is smaller than the {s.summary_size}-byte summary')
    for label, count, offset in (('name', s.name_count, s.name_offset), ('import', s.import_count, s.import_offset),
                                 ('export', s.export_count, s.export_offset)):
        if count < 0 or count > MAX_COUNT:
            raise CorruptPackage(f'invalid {label} count {count}')
        if count and not s.summary_size <= offset < header:
            raise CorruptPackage(f'{label} table offset {offset} lies outside the header (..{header})')
    if s.asset_registry_offset and not s.summary_size <= s.asset_registry_offset < max(header, size):
        raise CorruptPackage(f'asset registry offset {s.asset_registry_offset} lies outside the package')


def _name(names: list[str], r: Reader) -> str:
    index, number = r.i32(), r.i32()
    if not 0 <= index < len(names):
        raise CorruptPackage(f'name index {index} outside the {len(names)}-entry name table')
    return names[index] if number == 0 else f'{names[index]}_{number - 1}'


def parse_names(data: bytes, s: Summary) -> list[str]:
    r = Reader(data, s.name_offset)
    names = []
    for _ in range(s.name_count):
        names.append(r.fstring())
        r.u32()                                     # case-insensitive and case-preserving hashes
    return names


def parse_imports(data: bytes, s: Summary, names: list[str]) -> list[Import]:
    r = Reader(data, s.import_offset)
    imports = []
    for _ in range(s.import_count):
        class_package, class_name = _name(names, r), _name(names, r)
        outer = r.i32()
        object_name, package_name = _name(names, r), _name(names, r)
        optional = bool(r.u32()) if s.file_version_ue5 >= UE5_OPTIONAL_RESOURCES else False
        imports.append(Import(class_package, class_name, outer, object_name, package_name, optional))
    return imports


def parse_asset_registry(data: bytes, s: Summary) -> list[AssetData]:
    """The asset registry block: one entry per public asset object, with its class and searchable tags."""
    if s.asset_registry_offset <= 0:
        return []
    r = Reader(data, s.asset_registry_offset)
    r.i64()                                         # offset of the separately serialized dependency data
    assets = []
    for _ in range(r.count('asset registry object')):
        path, class_path = r.fstring(), r.fstring()
        tags = {}
        for _ in range(r.count('asset registry tag')):
            key, value = r.fstring(), r.fstring()
            tags[key] = value
        assets.append(AssetData(path, class_path, tags))
    return assets


def external_map(package_name: str) -> str | None:
    """The map that owns an external actor/object package, from its encoded path.

    `/Game/__ExternalActors__/Maps/Island/5/PQ/HASH` -> `/Game/Maps/Island`. None when the name is not external.
    """
    parts = package_name.split('/')
    for root in EXTERNAL_ROOTS:
        if root in parts:
            at = parts.index(root)
            level = parts[at + 1:-3]                # the two hash folders and the file name follow the map path
            if at >= 1 and level:
                return '/'.join(parts[:at] + level)
    return None


def _actor_descriptor(encoded: str):
    """(guid, base class, native class, location, rotation, scale) from an ActorMetaData tag, or a reason it is not."""
    try:
        blob = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        return 'unsupported: ActorMetaData is not base64'
    r = Reader(blob)
    try:
        versions = {}
        for _ in range(r.count('descriptor custom version')):
            key = r.guid()
            versions[key] = r.i32()
        missing = [f'{key}>={need}' for key, need in ACTOR_DESC_MINIMUM.items() if versions.get(key, -1) < need]
        if missing:
            return f'unsupported: descriptor custom versions below the known layout ({", ".join(missing)})'
        if r.u32():
            return 'unsupported: class default descriptor, not an actor'
        base = (r.fstring(), r.fstring())
        native = (r.fstring(), r.fstring())
        guid = r.guid()
        rotation = r.unpack('dddd')
        location = r.unpack('ddd')
        scale = r.unpack('ddd')
    except CorruptPackage as error:
        return f'unsupported: descriptor truncated ({error})'

    def path(pair):
        return None if pair[0] in ('', 'None') else f'{pair[0]}.{pair[1]}'
    return guid, path(base), path(native), location, rotation, scale


def describe_actor(package_name: str, assets: list[AssetData]) -> ExternalActor | None:
    """The actor an external package holds; None unless the package is under __ExternalActors__/__ExternalObjects__."""
    map_name = external_map(package_name)
    if map_name is None:
        return None
    asset = next((a for a in assets if 'ActorMetaData' in a.tags or 'ActorMetaDataClass' in a.tags), None)
    if asset is None:
        asset = next((a for a in assets if ':PersistentLevel.' in a.object_path), None)
    if asset is None:
        return ExternalActor(map_name, None, None, None, None, None, None, None, None, None, None, 'absent')
    actor_path = asset.object_path if asset.object_path.startswith('/') else None
    name = None
    if actor_path and ':' in actor_path:
        outer, _, sub = actor_path.partition(':')
        name = sub.rsplit('.', 1)[-1]
        map_name = outer.split('.', 1)[0]           # the descriptor's own outer beats the encoded folder
    tags = asset.tags
    guid = base = native_desc = location = rotation = scale = None
    state = 'absent'
    if 'ActorMetaData' in tags:
        decoded = _actor_descriptor(tags['ActorMetaData'])
        if isinstance(decoded, str):
            state = decoded
        else:
            guid, base, native_desc, location, rotation, scale = decoded
            state = 'decoded'
    guid = tags.get('ActorGuid', guid)
    return ExternalActor(map_name, actor_path, name, tags.get('ActorLabel'), asset.class_path or None,
                         tags.get('ActorMetaDataClass', native_desc), base, guid, location, rotation, scale, state)


def parse(data: bytes) -> Package:
    """Everything this reader understands about one package's bytes."""
    summary = parse_summary(data)
    if len(data) < summary.total_header_size:
        raise CorruptPackage(f'{len(data)} bytes is shorter than the {summary.total_header_size}-byte header')
    names = parse_names(data, summary)
    imports = parse_imports(data, summary, names)
    assets = parse_asset_registry(data, summary)
    return Package(summary, names, imports, assets, describe_actor(summary.package_name, assets))


def read(path: Path | str) -> Package:
    """Parse a package file, reading only its header (never the export or bulk data)."""
    with Path(path).open('rb') as handle:
        head = handle.read(64 * 1024)
        try:
            summary = parse_summary(head)
        except CorruptPackage:
            head += handle.read()                   # an unusually large summary (many custom versions)
            summary = parse_summary(head)
        need = max(summary.total_header_size, summary.asset_registry_offset + 1)
        if len(head) < need:
            head += handle.read(need - len(head))
        # the asset registry block can run past the header size; read on until it parses
        while True:
            try:
                return parse(head)
            except CorruptPackage:
                more = handle.read(max(len(head), 64 * 1024))
                if not more:
                    raise
                head += more


def to_json(package: Package) -> dict:
    s = asdict(package.summary)
    for key in ('saved_by', 'compatible_with'):
        s[key] = str(getattr(package.summary, key))
    return {'package': package.package_name, 'summary': s, 'imported_packages': package.imported_packages,
            'assets': [asdict(a) for a in package.assets],
            'actor': asdict(package.actor) if package.actor else None}


def main(argv=None) -> int:
    paths = argv if argv is not None else sys.argv[1:]
    status = 0
    for path in paths:
        try:
            report = to_json(read(path))
            for asset in report['assets']:
                if 'ActorMetaData' in asset['tags']:
                    asset['tags']['ActorMetaData'] = f'<{len(asset["tags"]["ActorMetaData"])} base64 chars>'
            print(json.dumps({'path': str(path), **report}, indent=2))
        except (OSError, PackageError) as error:
            print(f'{path}: {error}', file=sys.stderr)
            status = 1
    return status


if __name__ == '__main__':
    sys.exit(main())
