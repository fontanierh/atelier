#!/usr/bin/env python3
"""Build a portable Yorimichi music bundle and its checksum lock file.

The full soundtrack is large, so the repository keeps the plan, the lock file and
the fetch tool. Publish the zip wherever the project stores release assets, pass
its URL here, and commit the resulting music.lock.json.

    python3 games/yorimichi/assets/audio/music/bundle.py --url https://.../yorimichi-music-v1.zip
"""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[5]
SOURCE = ROOT / "build" / "yorimichi" / "music"
LOCK = HERE / "music.lock.json"


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--out", type=Path, default=ROOT / "build" / "yorimichi" / "music-bundle")
    parser.add_argument("--url", default="", help="published URL of the zip")
    parser.add_argument("--max-files", type=int, default=1000)
    args = parser.parse_args()

    files = sorted(
        p for p in args.source.rglob("*")
        if p.is_file() and p.name not in ("reviews.json",)
    )
    if not files:
        raise SystemExit(f"no music files under {args.source}")
    if len(files) > args.max_files:
        raise SystemExit(f"{len(files)} files exceeds --max-files {args.max_files}")

    args.out.mkdir(parents=True, exist_ok=True)
    archive = args.out / "yorimichi-music-v1.zip"
    entries = []
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_STORED) as zf:
        for path in files:
            rel = path.relative_to(args.source).as_posix()
            zf.write(path, rel)
            entries.append({"path": rel, "bytes": path.stat().st_size, "sha256": digest(path)})

    lock = {
        "schema": 1,
        "version": "v1",
        "bundle": args.url,
        "bytes": archive.stat().st_size,
        "sha256": digest(archive),
        "files": entries,
    }
    LOCK.write_text(json.dumps(lock, indent=2) + "\n")
    print(f"bundle {archive} ({archive.stat().st_size / 1e9:.2f} GB)")
    print(f"lock   {LOCK} ({len(entries)} files)")
    if not args.url:
        print("warning: no --url; set the published zip URL before committing the lock file")


if __name__ == "__main__":
    main()
