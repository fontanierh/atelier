"""The game is in English (operator 593): no French in displayed text.

This checks the strings that reach the screen: C++ TEXT() literals in the game
module, racing horse names, Python display literals in the world and tools, the
phone page, runtime JSON labels, and the Belmonte sign map. It does not police comments, asset
source labels that the build translates, or identifiers.
"""
import ast
import json
import re
from pathlib import Path

import pytest

GAME = Path(__file__).resolve().parents[1]
ACCENTS = set('àâäéèêëîïôöùûüçœÀÂÄÉÈÊËÎÏÔÖÙÛÜÇŒ')
# Unambiguous French words that would read as French in an English UI. Ambiguous
# English/French spellings ("salon", "menu", "table") are left out on purpose.
FRENCH_WORDS = {
    'arrivee', 'asseoir', 'attendez', 'aujourd', 'bagages', 'bientot', 'cabine',
    'cantine', 'cratere', 'crete', 'dans', 'demain', 'depart', 'descendre',
    'deuxieme', 'domaine', 'ecurie', 'embarquement', 'escalier', 'ferme',
    'fermee', 'fermer', 'fourgon', 'gagnant', 'gare', 'haras',
    'mairie', 'merci', 'montez', 'monter', 'nord', 'ouest', 'ouvrir',
    'passerelle', 'personnel', 'personne', 'premiere', 'prochain', 'prochaine',
    'quai', 'reunion', 'riviere', 'sud', 'suivant', 'taverne',
    'telecabine', 'troisieme', 'vallee', 'verrouillee', 'vers', 'voiture',
}


IDENTIFIER = re.compile(r'^[A-Za-z0-9_./:+-]+$')


def french_hits(text):
    """Words that make a displayed string French, or an empty list.

    Accents are always checked. Bare identifiers, asset paths and keys are out
    of scope: the coordinator required them to keep their current spelling.
    """
    hits = {c for c in text if c in ACCENTS}
    if not IDENTIFIER.match(text.strip()):
        hits |= set(re.findall(r"[a-z]+", text.lower())) & FRENCH_WORDS
    return sorted(hits)


def cpp_literals(line):
    return re.findall(r'TEXT\("((?:[^"\\]|\\.)*)"\)', line)


def python_literals(path):
    """String constants outside docstrings, and outside the sign translation keys."""
    tree = ast.parse(path.read_text(errors='ignore'))
    docs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                docs.add(id(node.body[0].value))
    skipped_lines = set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == 'SIGN_TRANSLATIONS' for target in node.targets):
            skipped_lines.update(range(node.lineno, node.end_lineno + 1))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in docs and node.lineno not in skipped_lines:
                yield node.lineno, node.value


def test_detector_catches_known_french_display_text():
    assert french_hits('Pas à bord du train')
    assert french_hits('Prochain train')
    assert not french_hits('Next train — at platform')
    assert not french_hits('Hidamari — Southeast Rim')


def test_game_module_display_literals_are_english():
    findings = []
    for path in sorted((GAME / 'unreal' / 'Source' / 'Yorimichi').rglob('*')):
        if path.suffix not in ('.h', '.cpp'):
            continue
        for number, line in enumerate(path.read_text(errors='ignore').splitlines(), 1):
            for literal in cpp_literals(line):
                if french_hits(literal):
                    findings.append(f'{path.relative_to(GAME)}:{number}: {literal!r}')
    assert not findings, 'French in displayed C++ text:\n' + '\n'.join(findings)


def test_racing_horse_names_are_english():
    path = GAME / 'unreal/Plugins/HorseRacing/Source/AtelierHorseRacing/Private/HRNames.inl'
    names = re.findall(r'TEXT\("((?:[^"\\]|\\.)*)"\)', path.read_text())
    assert names, 'the horse-name vocabulary must not be empty'
    findings = [name for name in names if french_hits(name)]
    assert not findings, 'French in the racing horse-name pool:\n' + '\n'.join(findings)


def test_world_and_tool_display_literals_are_english():
    findings = []
    roots = [GAME / 'world', GAME / 'tools']
    roots += [path for path in GAME.glob('*.py')]
    for root in roots:
        paths = sorted(root.rglob('*.py')) if root.is_dir() else [root]
        for path in paths:
            if 'tests' in path.parts or '__pycache__' in path.parts:
                continue
            for number, literal in python_literals(path):
                if french_hits(literal):
                    findings.append(f'{path.relative_to(GAME)}:{number}: {literal!r}')
    assert not findings, 'French in displayed Python text:\n' + '\n'.join(findings)


def test_phone_ui_is_english():
    findings = []
    for path in sorted((GAME / 'phone').glob('*')):
        if path.suffix not in ('.js', '.mjs', '.html', '.css'):
            continue
        text = path.read_text(errors='ignore')
        if path.suffix == '.html':
            text = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', text, flags=re.S | re.I)
            text = re.sub(r'<[^>]+>', ' ', text)
            candidates = text.splitlines()
        elif path.suffix == '.css':
            candidates = []
        else:
            candidates = re.findall(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"", text)
        for number, candidate in enumerate(candidates, 1):
            if french_hits(candidate.strip('\'"')):
                findings.append(f'{path.relative_to(GAME)}:{number}: {candidate.strip()[:120]}')
    assert not findings, 'French in the phone UI:\n' + '\n'.join(findings)


def test_runtime_json_labels_are_english():
    findings = []
    for path in sorted((GAME / 'world').rglob('*.json')):
        if 'atlas' in path.parts:       # AI painting prompts, never displayed
            continue
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            continue

        def walk(node, where=''):
            if isinstance(node, dict):
                for key, value in node.items():
                    walk(value, f'{where}.{key}' if where else key)
            elif isinstance(node, list):
                for index, value in enumerate(node):
                    walk(value, f'{where}[{index}]')
            elif isinstance(node, str) and french_hits(node):
                findings.append(f'{path.relative_to(GAME)}:{where}: {node[:100]!r}')

        walk(data)
    assert not findings, 'French in runtime JSON labels:\n' + '\n'.join(findings)


def test_belmonte_sign_map_covers_every_source_sign_and_is_english():
    import sys
    sys.path.insert(0, str(GAME / 'world' / 'regions'))
    source = json.loads((GAME / 'assets' / 'belmonte' / 'source.json').read_text())
    build = (GAME / 'world' / 'regions' / 'belmonte' / 'runtime_layout.py').read_text()
    tree = ast.parse(build)
    mapping = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == 'SIGN_TRANSLATIONS' for target in node.targets):
            mapping = ast.literal_eval(node.value)
    assert mapping, 'Belmonte build must define SIGN_TRANSLATIONS'
    for text, english in mapping.items():
        assert not french_hits(english), (text, english)
    for sign in source['signs']:
        text = sign['text']
        assert text in mapping, f'untranslated Belmonte sign: {text!r}'


@pytest.mark.parametrize('name,expected', [
    ('hidamari', 'Hidamari — Southeast Rim'),
    ('southeast', 'Southeast Rim — Hidamari'),
    ('northwest', 'Northwest Rim — Belmonte'),
    ('floor', 'Crater Floor'),
    ('floor_rim', 'Southeast Rim — Crater'),
])
def test_gondola_station_labels_are_english(name, expected):
    sys_path = GAME / 'world' / 'regions'
    import sys
    sys.path.insert(0, str(sys_path))
    from hidamari.gondola import STATIONS
    assert STATIONS[name]['name'] == expected
    assert not french_hits(STATIONS[name]['name'])
