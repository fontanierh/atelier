#!/usr/bin/env python3
"""Select fetched Suno tracks for the optional Unreal music import.

The complete library lives in the Atelier cache. A game build may import all of
it, or restrict the import with comma-separated environment selectors:

    YORIMICHI_MUSIC_CATEGORIES=calm,moderate,action
    YORIMICHI_MUSIC_STYLES=lofi,ambient
    YORIMICHI_MUSIC_GROUPS=spawn,forest_lake,lofi_rain
    YORIMICHI_MUSIC_LIMIT=40

The selected list is a build artifact; the release catalog remains the source of
truth for every track and its intent tags.
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "world"))
import yori  # noqa: E402
from atelier.paths import cache_dir  # noqa: E402

ROOT = yori.OUT
CACHE = cache_dir("yorimichi", "music")
OUT = ROOT / "audio" / "music" / "manifest.json"


def values(text):
    return {part.strip() for part in text.split(",") if part.strip()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--categories", default=os.environ.get("YORIMICHI_MUSIC_CATEGORIES", ""))
    parser.add_argument("--styles", default=os.environ.get("YORIMICHI_MUSIC_STYLES", ""))
    parser.add_argument("--groups", default=os.environ.get("YORIMICHI_MUSIC_GROUPS", ""))
    parser.add_argument("--limit", default=os.environ.get("YORIMICHI_MUSIC_LIMIT", "0"))
    args = parser.parse_args()
    catalog_path = CACHE / "catalog.json"
    if not catalog_path.exists():
        raise SystemExit(
            f"music cache is missing: {CACHE}\n"
            "run: python3 games/yorimichi/assets/audio/music/fetch.py"
        )
    catalog = json.loads(catalog_path.read_text())
    categories = values(args.categories)
    styles = values(args.styles)
    groups = values(args.groups)
    limit = int(args.limit or 0)

    selected = []
    for track in catalog.get("tracks", []):
        if categories and track.get("category") not in categories:
            continue
        if styles and track.get("style_family") not in styles:
            continue
        if groups and track.get("group") not in groups and track.get("zone") not in groups:
            continue
        path = CACHE / str(track.get("path") or "")
        if not path.is_file():
            raise SystemExit(f"music file missing from cache: {path}")
        selected.append({**track, "source": str(path)})
        if limit and len(selected) >= limit:
            break

    if not selected:
        raise SystemExit("music selection is empty; check YORIMICHI_MUSIC_* selectors")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps({
        "schema": 1,
        "library": catalog.get("library"),
        "cache": str(CACHE),
        "selectors": {
            "categories": sorted(categories), "styles": sorted(styles),
            "groups": sorted(groups), "limit": limit,
        },
        "counts": len(selected),
        "tracks": selected,
    }, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(OUT)
    print(f"music selection: {len(selected)} tracks -> {OUT}")


if __name__ == "__main__":
    main()
