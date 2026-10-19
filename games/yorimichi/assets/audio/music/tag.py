#!/usr/bin/env python3
"""Write searchable ID3 metadata onto the review MP3s.

The manifests and catalog are authoritative, but a loose MP3 copied out of the
release should still say what it is. ffmpeg copies the audio stream unchanged;
only the ID3v2 tag is replaced.
"""
import argparse
import json
import os
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
DEFAULT_INDEX = ROOT / "build" / "yorimichi" / "music" / "index.json"
DEFAULT_ROOT = ROOT / "build" / "yorimichi" / "music"

GENRES = {
    "lofi": "Lo-fi Hip Hop",
    "energy": "Action Score",
    "ambient": "Ambient",
    "ambient/orchestral": "Ambient",
    "jazz": "Jazz",
    "world": "World",
    "orchestral": "Game Score",
    "orchestral/contrast": "Game Score",
    "action/orchestral": "Action Score",
}


def rows(index):
    for section in ("zones", "library", "variety"):
        for group in index.get(section, []):
            for track in group.get("tracks", []):
                yield section, group, track


def metadata(section, group, track):
    style = track.get("style_family", "orchestral")
    created = str(track.get("created_at") or "")
    return {
        "title": track.get("display_title") or track.get("title") or track.get("clip_id", "Untitled"),
        "artist": "Yorimichi",
        "album": "Yorimichi Music Library v1",
        "album_artist": "Yorimichi",
        "genre": GENRES.get(style, "Game Score"),
        "date": created[:4] or "2026",
        "comment": "Instrumental game score generated with Suno v6 for Yorimichi.",
        "YORIMICHI_SECTION": section,
        "YORIMICHI_GROUP": group.get("key", ""),
        "YORIMICHI_ZONE": str(track.get("zone", "")),
        "YORIMICHI_ROLE": str(track.get("role", "")),
        "YORIMICHI_STYLE": style,
        "YORIMICHI_CATEGORY": str(track.get("category", "")),
        "YORIMICHI_ENERGY": str(track.get("energy", "")),
        "YORIMICHI_INTENT": str(track.get("intent", "")),
        "YORIMICHI_MOOD": str(track.get("mood", "")),
        "YORIMICHI_USE": str(track.get("use", "")),
        "YORIMICHI_BPM": str(track.get("bpm_target", "")),
        "YORIMICHI_LOOP": str(bool(track.get("loop", False))).lower(),
        "SUNO_CLIP_ID": str(track.get("clip_id", "")),
        "SUNO_MODEL": str(track.get("model", "chirp-hawk")),
    }


def tag(path, values):
    temp = path.with_name(path.stem + ".tagged.mp3")
    command = [
        "ffmpeg", "-v", "error", "-y", "-i", str(path),
        "-map_metadata", "0", "-c", "copy", "-id3v2_version", "3",
    ]
    for key, value in values.items():
        command.extend(["-metadata", f"{key}={value}"])
    command.append(str(temp))
    try:
        subprocess.run(command, check=True)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    index = json.loads(args.index.read_text())
    count = 0
    for section, group, track in rows(index):
        relative = track.get("mp3")
        if not relative:
            continue
        path = Path(relative)
        if not path.is_absolute():
            path = args.root / path
        if not path.is_file():
            continue
        values = metadata(section, group, track)
        if args.dry_run:
            print(f"{path}: {values['genre']} / {values['YORIMICHI_CATEGORY']} / "
                  f"energy {values['YORIMICHI_ENERGY']} / {values['YORIMICHI_INTENT']}")
        else:
            tag(path, values)
        count += 1
    print(f"{'would tag' if args.dry_run else 'tagged'} {count} tracks")


if __name__ == "__main__":
    main()
