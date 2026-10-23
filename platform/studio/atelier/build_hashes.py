"""Local file-hash memoization. Inventory membership is always discovered afresh.

The database is disposable: a miss, schema change or unreadable index means hashing the file.
Trust boundaries (publication, restoration and explicit verification) bypass the index.
"""
import hashlib
from pathlib import Path
import sqlite3
import stat


def signature(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def digest_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


class HashIndex:
    """@cc [owner:fontanierh,label:correctness] hash-index-is-only-a-hint
    A memoized hash MUST match the file's identity, size, mode and nanosecond modification/change
    metadata. Changing or nonregular files MUST fail. Verification MUST read the bytes regardless
    of the index. Losing the index MUST affect performance only, never build correctness.
    """

    def __init__(self, path=None, *, read_only=False, verify=False):
        self.connection = None
        self.memory = {}
        self.resolved = {}  # Path spelling -> resolved key; realpath dominated warm planning.
        self.read_only = read_only
        self.verify = verify
        if path is None:
            return
        path = Path(path)
        try:
            if read_only:
                if not path.is_file():
                    return
                self.connection = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=.1)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                self.connection = sqlite3.connect(path, timeout=.1)
                self.connection.execute('CREATE TABLE IF NOT EXISTS hashes_v1 '
                                        '(path TEXT PRIMARY KEY, signature TEXT NOT NULL, digest TEXT NOT NULL)')
        except (OSError, sqlite3.Error):
            self.close()

    def close(self):
        if self.connection is not None:
            try:
                if not self.read_only:
                    self.connection.commit()
            except sqlite3.Error:
                pass
            finally:
                self.connection.close()
                self.connection = None

    def __enter__(self):
        return self

    def __exit__(self, *exception):
        self.close()

    @property
    def proving_digest(self):
        """index.digest, marked as binding each digest to the file's exact stat signature."""
        def digest(path):
            return self.digest(path)
        digest.proves = not self.verify
        return digest

    def record(self, path, digest):
        """Seed a digest proven elsewhere, e.g. a clone of a content-addressed checkpoint blob."""
        path = Path(path)
        key, stamp = str(path.resolve()), repr(signature(path.stat()))
        self.memory[key] = (stamp, digest)
        if self.connection is not None and not self.read_only:
            try:
                self.connection.execute('INSERT OR REPLACE INTO hashes_v1 VALUES (?, ?, ?)', (key, stamp, digest))
            except sqlite3.Error:
                self.close()

    def digest(self, path, *, verify=False):
        path = Path(path)
        before = path.stat()
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f'Not a regular file: {path}')
        spelling = str(path)
        key = self.resolved.get(spelling)
        if key is None:
            key = self.resolved[spelling] = str(path.resolve())
        stamp = repr(signature(before))
        value = None
        entry = self.memory.get(key)
        # Whole-second metadata cannot provide a useful persistent change token.
        precise = before.st_mtime_ns % 1_000_000_000 or before.st_ctime_ns % 1_000_000_000
        if not (verify or self.verify) and precise:
            if entry is None and self.connection is not None:
                try:
                    entry = self.connection.execute('SELECT signature, digest FROM hashes_v1 WHERE path=?',
                                                    (key,)).fetchone()
                except sqlite3.Error:
                    self.close()
            if entry is not None and entry[0] == stamp:
                candidate = entry[1]
                if isinstance(candidate, str) and len(candidate) == 64 and all(c in '0123456789abcdef' for c in candidate):
                    value = candidate
        if value is None:
            value = digest_file(path)
        if signature(path.stat()) != signature(before):
            raise ValueError(f'File changed while hashing: {path}')
        self.memory[key] = (stamp, value)
        if self.connection is not None and not self.read_only and entry != (stamp, value):
            try:
                self.connection.execute('INSERT OR REPLACE INTO hashes_v1 VALUES (?, ?, ?)', (key, stamp, value))
            except sqlite3.Error:
                self.close()
        return value
