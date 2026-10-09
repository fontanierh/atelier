"""Unreal's embedded Python has no numpy, so its scripts must not load modules that need it at import time."""
import ast
import sys
import unittest
from pathlib import Path

GAME = Path(__file__).resolve().parents[1]
SCRIPTS = GAME / 'unreal' / 'Scripts'
ROOTS = (SCRIPTS, GAME / 'world', GAME / 'world' / 'regions', GAME.parents[1] / 'platform' / 'studio')
MISSING = {'numpy', 'scipy', 'bpy', 'PIL', 'trimesh'}
sys.path.insert(0, str(GAME / 'world'))


def imports(path, everywhere=False):
    """Module names the file imports: at load time, or anywhere (an Unreal script's functions run in Unreal)."""
    names = []; body = list(ast.parse(path.read_text(), str(path)).body)
    while body:
        node = body.pop(0)
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            names.append(node.module)
        elif everywhere or isinstance(node, (ast.If, ast.Try, ast.ExceptHandler)):
            body += list(ast.iter_child_nodes(node))
    return names


def local_file(name):
    for root in ROOTS:
        for path in (root.joinpath(*name.split('.')).with_suffix('.py'), root.joinpath(*name.split('.'), '__init__.py')):
            if path.is_file():
                return path
    return None


def missing_imports(path):
    """Unavailable modules reached through local imports, as 'chain -> module'.

    Every import in an Unreal script counts; a world module counts only what it imports when it loads.
    """
    found = []; seen = set(); queue = [(path, path.name)]
    while queue:
        current, chain = queue.pop()
        for name in imports(current, everywhere=current.parent == SCRIPTS):
            if name.split('.')[0] in MISSING:
                found.append(f'{chain} -> {name}')
            parts = name.split('.')
            for depth in range(1, len(parts) + 1):
                module = local_file('.'.join(parts[:depth]))
                if module and module not in seen:
                    seen.add(module); queue.append((module, f'{chain} -> {".".join(parts[:depth])}'))
    return found


class UnrealScriptImportTests(unittest.TestCase):
    def test_scripts_load_without_numpy(self):
        scripts = sorted(SCRIPTS.glob('*.py'))
        self.assertTrue(scripts)
        problems = [p for script in scripts for p in missing_imports(script)]
        self.assertEqual(problems, [])

    def test_scanner_follows_local_modules(self):
        self.assertIn('communitypark/source.py', local_file('communitypark.source').as_posix())
        self.assertTrue(any(p.endswith('-> numpy') for p in missing_imports(local_file('communitypark.source'))))

    def test_communitypark_importer_reads_the_library_scene(self):
        import yori
        from communitypark.source import FILE
        tree = ast.parse((SCRIPTS / 'import_communitypark.py').read_text())
        value = next(n.value for n in tree.body if isinstance(n, ast.Assign) and ast.unparse(n.targets[0]) == 'SOURCE')
        self.assertEqual(eval(compile(ast.Expression(value), 'SOURCE', 'eval'), {'yori': yori}), FILE)


if __name__ == '__main__':
    unittest.main()
