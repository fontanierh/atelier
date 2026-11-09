"""Restricted originals (DECISIONS D05 group 2): the files each restricted package was made from, pinned and private.

`restricted.originals.json` links every package `restricted.lock.json` pins (by Content-relative path) one way:

- imported: the package's own import record (its asset-registry import data: the source's path and FileMD5) names
  the file; `scan` finds it in the donor checkout by its repository-relative tail and accepts it only with that MD5.
- keyed: the donor's skate clip importer (games/yorimichi/unreal/Scripts/skate_ride/import_clips.py) keyed
  /Game/SkateRide/Clips/B<bank>/<CLIP> from the simulation bundle's clip file, rig and bank metadata, with no import
  record; the clip must be in the donor's import state, whose fingerprint covers every bundle file and the importer's
  code (`donor_state`). The clip links that data and the importer's code (CLIP_CODE), so it can be keyed again.
- embedded: a texture with no source file of its own, made by its character's mesh import; it links that folder's
  imported skeletal-mesh originals.
- reported / scripted (the open Adventure packages, `open_packages`): see `link_open`.
- authored: no import record and an editor-made class (material, Blueprint, blend space, data asset, ...), from the
  asset registry (unreal/Scripts/report_classes.py, read-only editor.run).

Each original is pinned by donor-relative path, sha256 and size: the repository holds only the pins, never the bytes,
a host or a path to them. The bytes live in authorized restricted storage laid out like the donor checkout, named by
$V2_RESTRICTED_ORIGINALS (or --source); `fetch` copies them into restricted-originals/ (ignored by Git), verified.

    uv run python games/yorimichi_v2/tools/restricted/originals.py scan --donor DONOR_CHECKOUT --classes CLASSES_JSON
    uv run python games/yorimichi_v2/tools/restricted/originals.py check
    V2_RESTRICTED_ORIGINALS=DIR uv run python games/yorimichi_v2/tools/restricted/originals.py fetch
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path

GAME = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(GAME / 'tools/content'))
import records  # noqa: E402
from records import RecordError  # noqa: E402

LINKS = 'restricted.originals.json'
SOURCE_ENV = 'V2_RESTRICTED_ORIGINALS'
DEST = 'restricted-originals'
HEADER = 4 << 20                     # the import data is an asset-registry tag in the package header
ENTRY = re.compile(rb'\{[^{}]*"RelativeFilename"\s*:\s*"((?:[^"\\]|\\.)*)"[^{}]*\}')
MD5 = re.compile(rb'"FileMD5"\s*:\s*"([0-9a-fA-F]*)"')
TAIL = re.compile(r'(?:^|/)((?:build|games|source)/)')
CLIP = re.compile(r'^SkateRide/Clips/B(\d+)/([^/]+)\.uasset$')
BUNDLE = 'build/yorimichi/skate-simulation/package'
CLIP_STATE = 'build/yorimichi/skate-ride/import-state.json'
# The clip importer's code, also part of the donor fingerprint (import_clips.py fingerprint()), and the build-folder
# helper it runs: a keyed clip's reconstruction source beside its data.
CLIP_CODE = ['games/yorimichi/unreal/Scripts/skate_ride/import_clips.py',
             'games/yorimichi/unreal/Scripts/skate_ride/simulation.py',
             'games/yorimichi/unreal/Scripts/skate_ride/rider_mesh.py', 'games/yorimichi/world/yori.py']
IMPORTED_CLASSES = {'AnimSequence', 'SoundWave', 'StaticMesh', 'SkeletalMesh', 'Texture2D'}
AUTHORED_CLASSES = {'Material', 'MaterialInstanceConstant', 'MaterialFunction', 'Blueprint', 'AnimBlueprint',
                    'BlendSpace', 'BlendSpace1D', 'AnimMontage', 'Skeleton', 'PhysicsAsset', 'SoundAttenuation',
                    'SoundCue', 'AnimBoneCompressionSettings', 'AnimCurveCompressionSettings', 'MirrorDataTable',
                    'SkateMotionBank', 'SkateMotionData', 'WandererDefinition', 'FoxHunterDefinition',
                    'JapanFootstepSet'}
ROUTES = {'imported', 'keyed', 'embedded', 'authored', 'reported', 'scripted'}
ADVENTURE = 'build/yorimichi/adventure'
ADVENTURE_SCRIPTS = 'games/yorimichi/unreal/Scripts'
OPEN_RECORDS = ('adopted/adventure/reference', 'adopted/adventure/loose_files', 'adopted/japan/animation')


def import_sources(data: bytes) -> list[tuple[str, str]]:
    """(source path as recorded, FileMD5) for each file the package's import data names; empty paths are skipped."""
    found = []
    for match in ENTRY.finditer(data[:HEADER]):
        name = match.group(1).decode('utf-8', 'replace').replace('\\\\', '/').replace('\\', '/')
        md5 = MD5.search(match.group(0))
        if name:
            found.append((name, md5.group(1).decode().lower() if md5 else ''))
    return found


def tail(recorded: str) -> str | None:
    """The repository-relative part of a recorded import path: the last build/, games/ or source/ segment on."""
    hits = list(TAIL.finditer(recorded))
    return recorded[hits[-1].start(1):] if hits else None


def _digest(path: Path, cache: dict) -> tuple[str, str, int]:
    if path not in cache:
        md5, sha = hashlib.md5(), hashlib.sha256()
        with path.open('rb') as f:
            for block in iter(lambda: f.read(1 << 20), b''):
                md5.update(block)
                sha.update(block)
        cache[path] = (md5.hexdigest(), sha.hexdigest(), path.stat().st_size)
    return cache[path]


def scan(game: Path, donor: Path, classes: dict[str, str], content: Path | None = None) -> dict:
    """The links of every pinned restricted package, from its fetched bytes (`content`, default this game's
    unreal/Content) and the donor checkout."""
    restricted = records.load_restricted(game)
    pinned = [rel for rel in sorted(records.load_lock(restricted)) if rel.endswith(records.PACKAGE_EXTENSIONS)]
    content, cache, problems = content or game / 'unreal' / 'Content', {}, []
    state_file = donor / CLIP_STATE
    clip_state = json.loads(state_file.read_text()) if state_file.is_file() else {'clips': {}}
    clip_assets = {c['asset'] for c in clip_state.get('clips', {}).values()}
    packages, originals = {}, {}

    def pin(rel_tail: str) -> None:
        _, sha, size = _digest(donor / rel_tail, cache)
        originals[rel_tail] = {'sha256': sha, 'size': size}

    for rel in pinned:
        path = content / rel
        if not path.is_file() or records.is_lfs_pointer(path):
            problems.append(f'{rel}: not fetched here')
            continue
        package = '/Game/' + rel.rsplit('.', 1)[0]
        kind = classes.get(package, '')
        sources = import_sources(path.read_bytes())
        if sources:
            linked = []
            for recorded, md5 in sources:
                rel_tail = tail(recorded)
                if rel_tail is None or not (donor / rel_tail).is_file():
                    problems.append(f'{rel}: its source {Path(recorded).name} is not in the donor checkout')
                    continue
                if not md5 or _digest(donor / rel_tail, cache)[0] != md5:
                    problems.append(f'{rel}: the donor {rel_tail} is not the imported file (FileMD5 differs)')
                    continue
                pin(rel_tail)
                linked.append(rel_tail)
            if linked:
                packages[rel] = {'route': 'imported', 'class': kind, 'originals': sorted(set(linked))}
            continue
        clip = CLIP.match(rel)
        if clip and kind == 'AnimSequence':
            bank, name = clip.groups()
            files = [f'{BUNDLE}/animation/clips/{bank}/{name}.skate', f'{BUNDLE}/animation/rig.skate',
                     f'{BUNDLE}/metadata/bank-{bank}.skate', *CLIP_CODE]
            if package not in clip_assets or not all((donor / f).is_file() for f in files):
                problems.append(f'{rel}: a skate clip the donor import state or bundle does not hold')
                continue
            for f in files:
                pin(f)
            packages[rel] = {'route': 'keyed', 'class': kind, 'originals': files}
            continue
        if kind in AUTHORED_CLASSES:
            packages[rel] = {'route': 'authored', 'class': kind}
            continue
        packages[rel] = {'route': 'embedded' if kind == 'Texture2D' else 'unexplained', 'class': kind or 'unknown'}
    # A texture with no file of its own came out of its folder's character mesh import.
    for rel, entry in packages.items():
        if entry['route'] != 'embedded':
            continue
        root = rel.split('/', 1)[0]
        meshes = sorted({o for r, e in packages.items() if r.split('/', 1)[0] == root and e['class'] == 'SkeletalMesh'
                         and e['route'] == 'imported' for o in e['originals']})
        if meshes:
            entry['originals'] = meshes
        else:
            entry['route'] = 'unexplained'
    problems += [f'{rel}: no import record and class {e["class"]} is not editor-made' for rel, e in packages.items()
                 if e['route'] == 'unexplained']
    return {'schema': records.SCHEMA,
            'about': 'What each restricted package was made from (tools/restricted/originals.py). Originals are '
                     'pinned by donor-relative path; their bytes are in authorized restricted storage only.',
            'donor_state': {'skate_clips': clip_state.get('fingerprint', '')},
            'packages': packages, 'originals': dict(sorted(originals.items())), 'problems': problems}


def _glb_names(path: Path) -> tuple[set, set, set]:
    """(material names, image names, animation names) of a glTF binary: what an Interchange import makes assets of."""
    data = path.read_bytes()
    length = int.from_bytes(data[12:16], 'little')
    doc = json.loads(data[20:20 + length])
    return ({m.get('name') for m in doc.get('materials', [])}, {i.get('name') for i in doc.get('images', [])},
            {a.get('name') for a in doc.get('animations', [])})


def link_open(game: Path, donor: Path, content: Path | None = None) -> dict:
    """The open Adventure and animation packages (OPEN_RECORDS: adopted records with no sources) that the restricted
    lock does not pin, linked to what made them. {'open_packages', 'originals', 'problems'}; the keys are Content-relative
    package files like the restricted ones.

    - reported: named by the donor's Adventure import report (unreal_import.json) as a character's mesh, skeleton or clip
      (or its sword and glider equipment); made from that character's glb. The pins are the glb and the report.
    - embedded: a material, texture or skeleton the import of the sword or glider glb made; the glb names it.
    - scripted: an editor-made master or settings asset that a donor Unreal script creates by name; the pin is the
      script. It is neither editor-owned nor restricted: recovering it means running that script, replacing it means
      authoring it anew.

    With hydrated package bytes (`content`) a package whose import data names a file must name the glb pinned here."""
    report = json.loads((donor / ADVENTURE / 'unreal_import.json').read_text())['characters']
    export = {c['name']: c for c in json.loads((donor / ADVENTURE / 'export.json').read_text())['characters']}
    content, problems, packages, cache = content or game / 'unreal' / 'Content', [], {}, {}
    pins: dict[str, dict] = {}

    def pin(rel_tail: str) -> str:
        _, sha, size = _digest(donor / rel_tail, cache)
        pins[rel_tail] = {'sha256': sha, 'size': size}
        return rel_tail

    report_pin = pin(f'{ADVENTURE}/unreal_import.json')
    reported: dict[str, tuple[str, list[str]]] = {}      # package -> (class, originals)
    embedded: dict[str, tuple[str, list[str]]] = {}
    for character in report:
        glb = pin(f"{ADVENTURE}/{export[character['name']]['glb']}")
        reported[character['mesh'].split('.')[0]] = ('SkeletalMesh', [glb, report_pin])
        reported[character['skeleton'].split('.')[0]] = ('Skeleton', [glb, report_pin])
        for clip in character['clips'].values():
            reported[clip['path'].split('.')[0]] = ('AnimSequence', [glb, report_pin])
        for slot, item in export[character['name']].get('moves', {}).get('equipment', {}).items():
            gear = character['moves']['equipment'][slot]
            piece = pin(f"{ADVENTURE}/{item['glb']}")
            reported[gear['mesh'].split('.')[0]] = ('SkeletalMesh' if 'clip' in gear else 'StaticMesh', [piece, report_pin])
            if 'clip' in gear:
                reported[gear['clip'].split('.')[0]] = ('AnimSequence', [piece, report_pin])
                skeleton = gear['mesh'].split('.')[0].replace('/SK_', '/SKEL_')
                embedded[skeleton] = ('Skeleton', [piece])
            materials, images, _ = _glb_names(donor / ADVENTURE / item['glb'])
            folder = gear['mesh'].rsplit('/', 1)[0]
            for name in sorted(materials):
                embedded[f'{folder}/{name}'] = ('MaterialInstanceConstant', [piece])
            for name in sorted(images):
                embedded[f'{folder}/{name}'] = ('Texture2D', [piece])
    scripted = {
        '/Game/Adventure/M_AdventureCharacter': ('Material', 'import_adventure.py', "master('M_AdventureCharacter'"),
        '/Game/Adventure/M_AdventureCharacterMasked': ('Material', 'import_adventure.py', "master('M_AdventureCharacterMasked'"),
        '/Game/Japan/Animation/CharacterCompression': ('AnimBoneCompressionSettings', 'animation_compression.py',
                                                      "'CharacterCompression'")}
    for package, (kind, script, needle) in scripted.items():
        path = donor / ADVENTURE_SCRIPTS / script
        if not path.is_file() or needle not in path.read_text():
            problems.append(f'{package}: the donor script {script} does not create it')
            continue
        packages[package] = {'route': 'scripted', 'class': kind,
                             'originals': [pin(f'{ADVENTURE_SCRIPTS}/{script}')]}
    owned = []
    for record_id in OPEN_RECORDS:
        owned += [o.package for o in records.load_asset(game / 'assets' / record_id / 'asset.toml').outputs]
    for package in owned:
        if package in packages:
            continue
        for route, table in (('reported', reported), ('embedded', embedded)):
            if package in table:
                kind, files = table[package]
                packages[package] = {'route': route, 'class': kind, 'originals': files}
                break
        else:
            problems.append(f'{package}: named by no donor Adventure report, glb or script (recover or replace)')
    for package, entry in sorted(packages.items()):
        file = content / (package[len('/Game/'):] + '.uasset')
        if file.is_file() and not records.is_lfs_pointer(file):
            for recorded, md5 in import_sources(file.read_bytes()):
                want = [o for o in entry.get('originals', []) if o.endswith('.glb')]
                if not any(recorded.replace('\\', '/').endswith(o.split('/', 3)[-1]) and _digest(donor / o, cache)[0] == md5
                           for o in want):
                    problems.append(f'{package}: its import data names {Path(recorded).name}, not the pinned glb')
    return {'open_packages': {p[len('/Game/'):] + '.uasset': e for p, e in sorted(packages.items())},
            'originals': pins, 'problems': problems}


def check(game: Path) -> list[str]:
    """Every pinned restricted package is linked, every link is a valid route, every linked original is pinned."""
    restricted = records.load_restricted(game)
    pinned = {rel for rel in records.load_lock(restricted) if rel.endswith(records.PACKAGE_EXTENSIONS)}
    path = game / LINKS
    if not path.is_file():
        return [f'{LINKS} is missing'] if pinned else []
    data = json.loads(path.read_text())
    packages, originals = data.get('packages', {}), data.get('originals', {})
    problems = [f'{rel}: pinned but not linked' for rel in sorted(pinned - set(packages))]
    problems += [f'{rel}: linked but not pinned' for rel in sorted(set(packages) - pinned)]
    used = set()
    for rel, entry in sorted(packages.items()):
        route = entry.get('route')
        if route not in ROUTES:
            problems.append(f'{rel}: route {route!r}')
        elif route == 'authored':
            if entry.get('class') not in AUTHORED_CLASSES:
                problems.append(f'{rel}: authored, but {entry.get("class")} is not an editor-made class')
        elif not entry.get('originals'):
            problems.append(f'{rel}: {route} with no original')
        elif route == 'keyed' and not set(CLIP_CODE) <= set(entry['originals']):
            problems.append(f'{rel}: keyed without the importer code it was keyed by')
        for original in entry.get('originals', []):
            used.add(original)
            if original not in originals:
                problems.append(f'{rel}: original {original} is not pinned')
    for original, pin_ in originals.items():
        if original.startswith('/') or '..' in original.split('/') or not TAIL.match(original):
            problems.append(f'{original}: not a donor-relative path')
        if not re.fullmatch(r'[0-9a-f]{64}', str(pin_.get('sha256', ''))) or not isinstance(pin_.get('size'), int):
            problems.append(f'{original}: pin without sha256 and size')
    opened = data.get('open_packages', {})
    for rel, entry in sorted(opened.items()):
        if entry.get('route') not in ROUTES or not entry.get('originals'):
            problems.append(f'{rel}: open package with route {entry.get("route")!r} and no original')
        for original in entry.get('originals', []):
            used.add(original)
            if original not in originals:
                problems.append(f'{rel}: original {original} is not pinned')
    owned = set()
    for record_id in OPEN_RECORDS if opened else ():
        toml = game / 'assets' / record_id / 'asset.toml'
        owned |= {o.package[len('/Game/'):] + '.uasset' for o in records.load_asset(toml).outputs} if toml.is_file() else set()
    if opened:
        problems += [f'{rel}: owned by an open record but not linked' for rel in sorted(owned - set(opened))]
        problems += [f'{rel}: linked but owned by no open record' for rel in sorted(set(opened) - owned)]
    problems += [f'{original}: pinned but linked by no package' for original in sorted(set(originals) - used)]
    problems += [f'scan problem: {p}' for p in data.get('problems', []) + data.get('open_problems', [])]
    return problems


def fetch(game: Path, source: Path | None = None, *, echo=print) -> tuple[int, list[str]]:
    """(files copied, refusals): each pinned original absent here, copied from storage and verified against its pin."""
    if source is None:
        value = os.environ.get(SOURCE_ENV)
        if not value:
            raise RecordError(f'set {SOURCE_ENV} to the authorized restricted originals storage directory')
        source = Path(value)
    if not source.is_dir():
        raise RecordError(f'restricted originals source {SOURCE_ENV} is not a directory')
    originals = json.loads((game / LINKS).read_text())['originals']
    copied, refused = 0, []
    for rel, entry in sorted(originals.items()):
        dest, origin = game / DEST / rel, source / rel
        if dest.is_file():
            if records.sha256_file(dest) != entry['sha256']:
                refused.append(f'{rel}: local file differs from its pin; never overwritten')
            continue
        if not origin.is_file() or origin.stat().st_size != entry['size']:
            refused.append(f'{rel}: not in the source, or its size differs from the pin')
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + '.tmp')
        try:
            shutil.copyfile(origin, tmp)
            if records.sha256_file(tmp) != entry['sha256']:
                refused.append(f'{rel}: source hash differs from its pin; refused')
                continue
            tmp.replace(dest)
            copied += 1
        finally:
            tmp.unlink(missing_ok=True)
    echo(f'{copied} restricted original(s) fetched, {len(originals) - copied - len(refused)} already present, '
         f'{len(refused)} refused')
    return copied, refused


def main(argv=None) -> int:
    """@cc [owner:fontanierh,label:correctness] original-link-evidence-preservation
    A restricted scan MUST preserve prior open links and unresolved open problems, including an empty failed
    open result. Only a new link-open result MAY replace those problems, including clearing them on success.
    """
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = parser.add_subparsers(dest='command', required=True)
    put = sub.add_parser('scan', help=f'link every pinned restricted package and pin its originals ({LINKS})')
    put.add_argument('--donor', required=True, type=Path, help='the donor checkout the packages were imported in')
    put.add_argument('--classes', required=True, type=Path,
                     help='package -> class JSON from unreal/Scripts/report_classes.py')
    put.add_argument('--content', type=Path, help='a Content folder holding the fetched restricted packages')
    opn = sub.add_parser('link-open', help='link the open Adventure and animation packages and pin their originals')
    opn.add_argument('--donor', required=True, type=Path, help='the donor checkout holding build/ and games/')
    opn.add_argument('--content', type=Path, help='a Content folder holding the hydrated packages (optional hash check)')
    sub.add_parser('check', help='every pinned restricted package linked, every linked original pinned')
    get = sub.add_parser('fetch', help='copy the pinned originals in, verified against their pins')
    get.add_argument('--source', type=Path, help=f'restricted originals storage (default: ${SOURCE_ENV})')
    parser.add_argument('--game', type=Path, default=GAME, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    game = args.game.resolve()
    try:
        if args.command == 'scan':
            data = scan(game, args.donor.resolve(), json.loads(args.classes.read_text()),
                        args.content.resolve() if args.content else None)
            previous = json.loads((game / LINKS).read_text()) if (game / LINKS).is_file() else {}
            if 'open_packages' in previous or 'open_problems' in previous:
                # Open evidence belongs to link-open, including a failure that linked no packages.
                data['open_packages'] = previous.get('open_packages', {})
                data['open_problems'] = previous.get('open_problems', [])
                data['originals'] = dict(sorted({**previous['originals'], **data['originals']}.items()))
            records.write_json(game / LINKS, data)
            routes = {}
            for entry in data['packages'].values():
                routes[entry['route']] = routes.get(entry['route'], 0) + 1
            print(f'{len(data["packages"])} package(s) linked {dict(sorted(routes.items()))}, '
                  f'{len(data["originals"])} original(s) pinned, {len(data["problems"])} problem(s)')
            for problem in data['problems'][:20]:
                print(f'  {problem}', file=sys.stderr)
            return 1 if data['problems'] else 0
        if args.command == 'link-open':
            data = json.loads((game / LINKS).read_text())
            found = link_open(game, args.donor.resolve(), args.content.resolve() if args.content else None)
            data['originals'] = dict(sorted({**data['originals'], **found['originals']}.items()))
            data['open_packages'] = found['open_packages']
            data['open_problems'] = found['problems']
            records.write_json(game / LINKS, data)
            routes = {}
            for entry in data['open_packages'].values():
                routes[entry['route']] = routes.get(entry['route'], 0) + 1
            print(f'{len(data["open_packages"])} open package(s) linked {dict(sorted(routes.items()))}, '
                  f'{len(found["originals"])} original(s) pinned, {len(found["problems"])} problem(s)')
            for problem in found['problems']:
                print(f'  {problem}', file=sys.stderr)
            return 1 if found['problems'] else 0
        if args.command == 'check':
            problems = check(game)
            for problem in problems[:40]:
                print(f'  {problem}', file=sys.stderr)
            print(f'restricted originals: {"OK" if not problems else f"{len(problems)} problem(s)"}')
            return 1 if problems else 0
        _, refused = fetch(game, args.source)
    except (RecordError, OSError, ValueError) as error:
        print(f'restricted originals {args.command} failed: {error}', file=sys.stderr)
        return 1
    for problem in refused:
        print(f'  {problem}', file=sys.stderr)
    return 1 if refused else 0


if __name__ == '__main__':
    sys.exit(main())
