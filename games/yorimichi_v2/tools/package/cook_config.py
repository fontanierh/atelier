"""The V2 package's cook configuration: does it cover every content root the game loads, and nothing excluded?

The packaged build cooks with `-cookall` (platform/studio/atelier/build.py, UnrealPackage), so every package under
`unreal/Content` is cooked. That makes DirectoriesToAlwaysCook a second guarantee for assets loaded by string or path
at run time, and this check keeps it honest against the code: every top-level `/Game` folder that a literal path in
the source, scripts, config, live, tools or runtime data names must be covered by an always-cook entry, unless it is
a restricted root (fetched, pinned, and checked by check.py). It also refuses an excluded feature's content (X01 phone
streaming, X02 kart driving: DECISIONS and INVENTORY) anywhere in Content, names a map the game starts or travels to
that is not committed, and a Mac bundle identifier left at the template value.

    uv run python games/yorimichi_v2/tools/package/cook_config.py           # report; exit 1 on a failure
    uv run python games/yorimichi_v2/tools/package/cook_config.py --write   # add the missing always-cook roots

`--write` only appends missing top-level roots to DefaultGame.ini's DirectoriesToAlwaysCook lines; it never removes one.
"""
from __future__ import annotations

import argparse
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

GAME = Path(__file__).resolve().parents[2]
CONTENT = GAME / 'unreal/Content'
DEFAULT_GAME_INI = GAME / 'unreal/Config/DefaultGame.ini'
ENGINE_INI = GAME / 'unreal/Config/DefaultEngine.ini'
MAC_INI = GAME / 'unreal/Config/Mac/MacEngine.ini'
RESTRICTED = GAME / 'restricted.toml'
BUNDLE_SECTION = '[/Script/MacTargetPlatform.XcodeProjectSettings]'   # what the Xcode build writes to Info.plist
TEMPLATE_BUNDLE_PREFIX = 'com.YourCompany.'
# Folders that scan for string paths must ignore: fixtures, caches and the editor's own saved state.
SCAN = ('unreal/Source', 'unreal/Scripts', 'unreal/Config', 'unreal/Content/Data', 'live', 'tools', 'world', 'build.py')
SKIP_PARTS = {'__pycache__', 'tests', 'Saved', 'Intermediate', 'Binaries'}
LITERAL = re.compile(r'/Game/[A-Za-z0-9_./-]+')
ALWAYS = re.compile(r'^\+DirectoriesToAlwaysCook=\(Path="(/Game/[^"]*)"\)\s*$', re.M)
# Excluded by the owner's inventory (docs/INVENTORY.md X01, X02): their content must not be cooked into the package.
# Matched on Content-relative paths. 'phone' alone would catch the city's phone booths, which are in scope.
EXCLUDED = ('kart', 'carride', 'pixelstreaming', 'atelierstream', 'phonestream', 'phone_stream', 'driving')


@dataclass(frozen=True)
class Problem:
    level: str      # FAIL or WARN
    code: str
    subject: str
    detail: str

    def __str__(self):
        return f'{self.level:4} {self.code:18} {self.subject}: {self.detail}'


def root_of(literal: str) -> str | None:
    """The top-level Content folder a `/Game/...` literal names: '/Game/Japan/Assets/X.X' -> 'Japan'."""
    first = literal.removeprefix('/Game/').split('/')[0].split('.')[0].rstrip('.')
    if not first or first.startswith('...') or first in {'__ExternalActors__', '__ExternalObjects__'}:
        return None
    return first


def scanned_files(game: Path = GAME):
    for name in SCAN:
        base = game / name
        if base.is_file():
            yield base
        elif base.is_dir():
            for path in base.rglob('*'):
                if path.is_file() and not SKIP_PARTS & set(path.relative_to(game).parts):
                    if path.suffix in {'.py', '.cpp', '.h', '.ini', '.json', '.toml', '.md', '.txt', '.hpp', '.cs'} \
                            or name.endswith('Data'):
                        yield path


def string_roots(game: Path = GAME) -> dict[str, int]:
    """Every top-level /Game folder named by a literal path in the scanned tree, with how often it is named."""
    counts: dict[str, int] = {}
    for path in scanned_files(game):
        try:
            text = path.read_text(errors='ignore')
        except OSError:
            continue
        for literal in LITERAL.findall(text):
            root = root_of(literal)
            if root:
                counts[root] = counts.get(root, 0) + 1
    return counts


def content_roots(game: Path = GAME) -> set[str]:
    base = game / 'unreal/Content'
    return {p.name for p in base.iterdir() if p.is_dir() and not p.name.startswith('__')} if base.is_dir() else set()


def restricted_roots(game: Path = GAME) -> set[str]:
    data = tomllib.loads((game / 'restricted.toml').read_text())
    return {r.removeprefix('/Game/').split('/')[0] for r in data.get('roots', [])}


def always_cook(game: Path = GAME) -> list[str]:
    return ALWAYS.findall((game / 'unreal/Config/DefaultGame.ini').read_text())


def covered(root: str, entries: list[str]) -> bool:
    """Only the whole top-level folder covers a root: a nested entry names one piece of it, not the rest."""
    return f'/Game/{root}' in entries


def map_paths(game: Path = GAME) -> set[str]:
    """Every map the game starts with or travels to: GameDefaultMap, the play profiles' first argument, and the
    GameMode prefixes' maps are checked by name only. Map references are /Game/... paths without the object suffix."""
    maps = set()
    engine = (game / 'unreal/Config/DefaultEngine.ini').read_text()
    for name in re.findall(r'GameDefaultMap=(/Game/[^\s.]+)', engine):
        maps.add(name)
    for args in tomllib.loads((game / 'game.toml').read_text()).get('play', {}).values():
        for arg in args.get('args', []):
            if arg.startswith('/Game/'):
                maps.add(arg.split('.')[0])
    return maps


def bundle_identifier(game: Path = GAME) -> str | None:
    path = game / 'unreal/Config/Mac/MacEngine.ini'
    if not path.is_file():
        return None
    section = False
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith('['):
            section = stripped == BUNDLE_SECTION
        elif section and stripped.startswith('BundleIdentifier='):
            return stripped.split('=', 1)[1].strip()
    return None


def excluded_hits(game: Path = GAME) -> list[str]:
    hits = []
    base = game / 'unreal/Content'
    if base.is_dir():
        for path in base.rglob('*'):
            if not path.is_file():
                continue
            rel = path.relative_to(base).as_posix()
            if any(word in rel.lower() for word in EXCLUDED):
                hits.append(rel)
    return sorted(hits)


def problems(game: Path = GAME) -> list[Problem]:
    out: list[Problem] = []
    entries = always_cook(game)
    content = content_roots(game)
    restricted = restricted_roots(game)
    for root, count in sorted(string_roots(game).items()):
        if root not in content and root not in restricted:
            out.append(Problem('WARN', 'UNKNOWN_ROOT', f'/Game/{root}', f'named {count}x but not in Content or restricted.toml'))
            continue
        if not covered(root, entries):
            out.append(Problem('FAIL', 'NOT_ALWAYS_COOK', f'/Game/{root}',
                               f'loaded by path ({count}x) and not in DirectoriesToAlwaysCook; run cook_config.py --write'))
    for entry in entries:
        rel = entry.removeprefix('/Game/')
        if not (game / 'unreal/Content' / rel).exists() and rel.split('/')[0] not in restricted:
            out.append(Problem('WARN', 'STALE_ALWAYS_COOK', entry, 'no such folder in Content'))
    for hit in excluded_hits(game):
        out.append(Problem('FAIL', 'EXCLUDED_CONTENT', f'Content/{hit}', 'excluded feature content must not be in the package'))
    for name in sorted(map_paths(game)):
        umap = game / 'unreal/Content' / (name.removeprefix('/Game/') + '.umap')
        if not umap.is_file():
            out.append(Problem('FAIL', 'MAP_MISSING', name, f'{umap.relative_to(game)} is not committed'))
    bundle = bundle_identifier(game)
    if not bundle or bundle.startswith(TEMPLATE_BUNDLE_PREFIX):
        out.append(Problem('FAIL', 'BUNDLE_ID', 'Config/Mac/MacEngine.ini',
                           f'bundle identifier is {bundle or "unset"}; it must name V2, not the template'))
    return out


def render_missing(game: Path = GAME) -> list[str]:
    """DirectoriesToAlwaysCook lines for the top-level roots that are named but not covered."""
    entries = always_cook(game)
    content = content_roots(game)
    restricted = restricted_roots(game)
    missing = []
    for root in sorted(string_roots(game)):
        if (root in content or root in restricted) and not covered(root, entries):
            missing.append(f'+DirectoriesToAlwaysCook=(Path="/Game/{root}")')
    return missing


def write_missing(game: Path = GAME) -> list[str]:
    lines = render_missing(game)
    if not lines:
        return []
    text = (game / 'unreal/Config/DefaultGame.ini').read_text()
    last = list(ALWAYS.finditer(text))[-1]
    text = text[:last.end()] + '\n' + '\n'.join(lines) + text[last.end():]
    (game / 'unreal/Config/DefaultGame.ini').write_text(text)
    return lines


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--write', action='store_true', help='append the missing always-cook roots')
    args = parser.parse_args(argv)
    if args.write:
        for line in write_missing():
            print('added', line)
    found = problems()
    for problem in found:
        print(problem)
    failed = [p for p in found if p.level == 'FAIL']
    print(f'{len(failed)} failure(s), {len(found) - len(failed)} warning(s)')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
