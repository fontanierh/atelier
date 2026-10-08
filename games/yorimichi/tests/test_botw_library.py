"""The committed BOTW library copy (assets/characters/botw-library, botw/vendor.py): it holds every file the BOTW and
horse rosters read, so a fresh clone builds them, and library.py reads it."""
import importlib.util
import sys
from pathlib import Path

CHARS = Path(__file__).resolve().parents[1] / 'assets' / 'characters'
sys.path.insert(0, str(CHARS / 'botw'))
import library  # noqa: E402


def horses():
    spec = importlib.util.spec_from_file_location('horses_export', CHARS / 'horses' / 'export.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_library_reads_the_committed_copy(monkeypatch):
    monkeypatch.delenv('ATELIER_BOTW_CACHE', raising=False)
    assert library.base() == library.VENDOR and library.available()


def test_the_copy_holds_every_file_the_rosters_read(monkeypatch):
    monkeypatch.delenv('ATELIER_BOTW_CACHE', raising=False)
    library._extended.cache_clear()
    files = library.sources() + horses().sources()
    assert files and all(f.is_file() and library.VENDOR in f.parents for f in files)
