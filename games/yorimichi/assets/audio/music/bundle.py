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
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
SOURCE = ROOT / "build" / "yorimichi" / "music"
LOCK = HERE / "music.lock.json"
GENRES = {
    "lofi": "Lo-fi Hip Hop", "energy": "Action Score", "ambient": "Ambient",
    "ambient/orchestral": "Ambient", "jazz": "Jazz", "world": "World",
    "orchestral": "Game Score", "orchestral/contrast": "Game Score",
    "action/orchestral": "Action Score",
}


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def relative_path(value, root):
    if not value:
        return value
    try:
        return Path(value).resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        return value


def portable_manifest(path, root, include_masters=False):
    """Return manifest text with absolute local media paths made relative."""
    data = json.loads(path.read_text())

    def walk(value):
        if isinstance(value, dict):
            for key in ("mp3", "m4a"):
                if value.get(key):
                    value[key] = relative_path(value[key], root)
            if not include_masters:
                value.pop("m4a", None)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(data)
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def catalog(index):
    tracks = []
    for section in ("zones", "library", "variety"):
        for group in index.get(section, []):
            for track in group.get("tracks", []):
                tracks.append({
                    "path": track.get("mp3"),
                    "title": track.get("display_title") or track.get("title"),
                    "clip_id": track.get("clip_id"),
                    "section": section,
                    "group": group.get("key"),
                    "zone": track.get("zone"),
                    "zone_name": track.get("zone_name"),
                    "role": track.get("role"),
                    "style_family": track.get("style_family"),
                    "genre": GENRES.get(track.get("style_family"), "Game Score"),
                    "category": track.get("category"),
                    "energy": track.get("energy"),
                    "intensity": track.get("intensity"),
                    "intent": track.get("intent"),
                    "mood": track.get("mood"),
                    "use": track.get("use"),
                    "bpm_target": track.get("bpm_target"),
                    "loop": track.get("loop"),
                    "duration_s": track.get("duration_s"),
                    "model": track.get("model"),
                    "tags": track.get("tags", []),
                })
    tracks.sort(key=lambda item: (item["section"], item["group"] or "", item["path"] or ""))
    return {
        "schema": 1,
        "library": "yorimichi-music-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tracks": tracks,
        "counts": {
            "tracks": len(tracks),
            "by_category": dict(Counter(t["category"] for t in tracks)),
            "by_style": dict(Counter(t["style_family"] for t in tracks)),
            "by_section": dict(Counter(t["section"] for t in tracks)),
        },
    }


def readme(data):
    counts = data["counts"]
    sections = ", ".join(f"{name}: {count}" for name, count in counts["by_section"].items())
    lines = [
        "# Yorimichi Music Library v1",
        "",
        "Instrumental game score generated with Suno v6 (`chirp-hawk`) for Yorimichi.",
        "Every track is tagged in `catalog.json`, in its manifest and in the MP3 ID3 fields.",
        "",
        f"{counts['tracks']} tracks ({sections}).",
        "",
        "## Selection tags",
        "",
        "- `category`: calm, moderate, energetic, action or contrast.",
        "- `style_family`: orchestral, ambient, lofi, jazz, world or energy.",
        "- `energy`: 1 (quiet) through 5 (intense).",
        "- `intent`, `mood`, `use`, `bpm_target`, `loop`: describe the moment the cue fits.",
        "- `zone` and `group`: the zone library or cue the track came from.",
        "",
        "Use the calm and quiet cues for exploration, interiors and menus. Use energy 4-5",
        "and action cues for fights. Keep silence and ambience between cues; enter a track",
        "at a phrase boundary and crossfade over several seconds instead of switching hard.",
        "",
        "The audio files are MP3 review copies (about 180 kbps). Keep the original decrypted",
        "M4A masters in the generation cache if a higher-quality stream is needed later.",
    ]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--out", type=Path, default=ROOT / "build" / "yorimichi" / "music-bundle")
    parser.add_argument("--url", default="", help="published URL of the zip")
    parser.add_argument("--max-files", type=int, default=1000)
    parser.add_argument("--include-masters", action="store_true",
                        help="also bundle the large decrypted .m4a files")
    args = parser.parse_args()

    files = sorted(
        p for p in args.source.rglob("*")
        if p.is_file() and p.name not in ("reviews.json",)
        and (args.include_masters or p.suffix != ".m4a")
    )
    if not files:
        raise SystemExit(f"no music files under {args.source}")
    if len(files) > args.max_files:
        raise SystemExit(f"{len(files)} files exceeds --max-files {args.max_files}")

    args.out.mkdir(parents=True, exist_ok=True)
    archive = args.out / "yorimichi-music-v1.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_STORED) as zf:
        for path in files:
            rel = path.relative_to(args.source).as_posix()
            if path.suffix == ".json":
                body = portable_manifest(path, args.source, args.include_masters).encode()
                zf.writestr(rel, body, compress_type=zipfile.ZIP_DEFLATED)
            else:
                zf.write(path, rel)

        index_path = args.source / "index.json"
        if index_path.exists():
            data = catalog(json.loads(index_path.read_text()))
            body = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
            zf.writestr("catalog.json", body, compress_type=zipfile.ZIP_DEFLATED)
            zf.writestr("README.md", readme(data), compress_type=zipfile.ZIP_DEFLATED)

    # Hash the final archive bytes. JSON manifests may have been rewritten to make
    # their media paths portable, so the source file hashes would not match.
    entries = []
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            with zf.open(info) as handle:
                h = hashlib.sha256()
                size = 0
                for chunk in iter(lambda: handle.read(1 << 20), b""):
                    h.update(chunk)
                    size += len(chunk)
            entries.append({"path": info.filename, "bytes": size, "sha256": h.hexdigest()})
    entries.sort(key=lambda entry: entry["path"])

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
