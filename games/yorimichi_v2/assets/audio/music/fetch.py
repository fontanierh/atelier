#!/usr/bin/env python3
"""Fetch and verify the Yorimichi V2 music bundle (the donor's pinned bundle, shared through its cache) into the Atelier cache.

Run by atelier fetch yorimichi. The committed music.lock.json names the bundle
URL, its SHA-256 and every contained file. Nothing is written into the checkout;
the game build imports from the cache.
"""
import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from atelier.paths import cache_dir  # noqa: E402

HERE = Path(__file__).resolve().parent
LOCK = HERE / "music.lock.json"


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verified(target):
    lock = json.loads(LOCK.read_text())
    wanted = {entry["path"]: entry for entry in lock["files"]}
    return all(
        (target / rel).is_file()
        and (target / rel).stat().st_size == entry["bytes"]
        and digest(target / rel) == entry["sha256"]
        for rel, entry in wanted.items()
    )


def current(target):
    """--quick: the cache's manifest names this lock's bundle and every file has its locked size (no hashing)."""
    lock = json.loads(LOCK.read_text())
    try:
        stamp = json.loads((target / "manifest.json").read_text())
    except (OSError, ValueError):
        return False
    return stamp.get("sha256") == lock["sha256"] and all(
        (target / entry["path"]).is_file() and (target / entry["path"]).stat().st_size == entry["bytes"]
        for entry in lock["files"]
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, help="local zip instead of the published URL")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--quick", action="store_true",
                        help="trust a cache this lock verified before when every size matches (atelier playtest)")
    args = parser.parse_args()

    lock = json.loads(LOCK.read_text())
    dest = Path(cache_dir("yorimichi", "music"))
    if not args.force and args.quick and current(dest):
        return
    if not args.force and verified(dest):
        print(f"music cache is complete: {dest}")
        return

    bundle = args.bundle.expanduser().resolve() if args.bundle else None
    url = bundle.as_uri() if bundle else lock.get("bundle")
    if not url:
        raise SystemExit("music.lock.json has no bundle URL; pass --bundle PATH")
    dest.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=dest) as tmp:
        tmp = Path(tmp)
        archive = tmp / "bundle.zip"
        if bundle:
            shutil.copy2(bundle, archive)
        else:
            print(f"downloading {url}")
            with urllib.request.urlopen(url, timeout=300) as response, archive.open("wb") as out:
                shutil.copyfileobj(response, out)
        if digest(archive) != lock["sha256"]:
            raise SystemExit("bundle SHA-256 mismatch")
        with zipfile.ZipFile(archive) as zf:
            for info in zf.infolist():
                rel = Path(info.filename)
                if rel.is_absolute() or ".." in rel.parts:
                    raise SystemExit(f"unsafe bundle path: {info.filename}")
                if info.is_dir():
                    continue
                target = tmp / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, target.open("wb") as out:
                    shutil.copyfileobj(src, out)
        wanted = {entry["path"]: entry for entry in lock["files"]}
        for rel, entry in wanted.items():
            path = tmp / rel
            if not path.is_file() or path.stat().st_size != entry["bytes"] or digest(path) != entry["sha256"]:
                raise SystemExit(f"bundle file failed verification: {rel}")
        for rel in wanted:
            source = tmp / rel
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    # The bundle by its pinned hash and its file name, never the local folder it was copied from (portable records).
    (dest / "manifest.json").write_text(json.dumps({
        "bundle": bundle.name if bundle else url, "sha256": lock["sha256"], "files": len(lock["files"]),
    }, indent=2) + "\n")
    print(f"music cache ready: {dest} ({len(lock['files'])} files)")


if __name__ == "__main__":
    main()
