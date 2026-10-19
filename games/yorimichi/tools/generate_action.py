#!/usr/bin/env python3
"""Generate the combat, action and set-piece music library."""
import argparse
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from suno_client import Suno, TurnstileError
import music_index

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "build" / "yorimichi" / "music"
PLAN = ROOT / "games" / "yorimichi" / "assets" / "audio" / "music" / "action-plan.json"
ZONES = ROOT / "games" / "yorimichi" / "assets" / "audio" / "music" / "plan.json"
VARIETY = ROOT / "games" / "yorimichi" / "assets" / "audio" / "music" / "variety-plan.json"


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(path)


def media_path(value):
    path = Path(value)
    return path if path.is_absolute() else OUT / path


def complete(cue):
    path = OUT / "library" / cue["key"] / "manifest.json"
    if not path.exists():
        return False
    data = json.loads(path.read_text())
    tracks = [t for t in data.get("tracks", []) if t.get("role") == "action"]
    return len(tracks) >= 2 and all(media_path(t["mp3"]).exists() for t in tracks)


def submit(client, prompt, *, cue, **kwargs):
    for attempt in (1, 2, 3, 4):
        try:
            return client.generate(prompt, **kwargs)
        except TurnstileError as error:
            print(f"  {cue} turnstile attempt {attempt} failed: {error}", flush=True)
            if attempt == 4:
                raise
            time.sleep(30)


def generate(client, plan, cue):
    dest = OUT / "library" / cue["key"]
    dest.mkdir(parents=True, exist_ok=True)
    prompt = plan["style"] + " " + cue["prompt"]
    print(f"  {cue['key']}: submitting", flush=True)
    data = submit(client, prompt, cue=cue["key"],
        instrumental=True, model=plan["model"], duration=plan["duration"],
        negative_tags=plan.get("negative", ""), title=cue["name"],
        ledger_metadata={"kind": "music", "cue": cue["key"], "name": cue["name"], "role": "action"},
    )
    clips = data.get("clips", [])
    print(f"  {cue['key']}: clips {[c['id'] for c in clips]}", flush=True)
    clips = client.wait([c["id"] for c in clips], timeout=1200, interval=5)
    tracks = []
    for clip in clips:
        if clip.get("status") != "complete":
            raise RuntimeError(f"clip {clip.get('id')} ended {clip.get('status')}")
        files = client.download(clip["id"])
        kept = []
        for src in files:
            src = Path(src)
            dst = dest / src.name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            kept.append(str(dst))
        mp3 = next(p for p in kept if p.endswith(".mp3"))
        tracks.append({
            "role": "action",
            "cue": cue["key"],
            "title": cue["name"],
            "intent": cue["intent"],
            "mood": cue["mood"],
            "use": cue["use"],
            "intensity": cue["intensity"],
            "loop": cue["loop"],
            "bpm_target": cue["bpm_target"],
            "zone": "library",
            "zone_name": "Action & set pieces",
            "clip_id": clip["id"],
            "model": clip.get("model_name") or plan["model"],
            "duration_s": clip.get("metadata", {}).get("duration"),
            "prompt": prompt,
            "mp3": mp3,
            "m4a": next((p for p in kept if p.endswith(".m4a")), None),
            "created_at": clip.get("created_at"),
            "credits_estimate": 5,
            "tags": [
                "instrumental", "v6", "yorimichi", "library", "action",
                "intent:" + cue["intent"], "mood:" + cue["mood"],
                "intensity:" + str(cue["intensity"]),
                "loop:" + str(bool(cue["loop"])).lower(),
            ],
        })
    return tracks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cue", action="append", default=[])
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    plan = json.loads(PLAN.read_text())
    cues = [c for c in plan["cues"] if not args.cue or c["key"] in args.cue]
    client = Suno()
    started = time.time()
    for i, cue in enumerate(cues, 1):
        if not args.force and complete(cue):
            print(f"[{i}/{len(cues)}] {cue['key']}: already complete", flush=True)
            continue
        print(f"[{i}/{len(cues)}] {cue['key']}: generating", flush=True)
        try:
            tracks = generate(client, plan, cue)
            save(OUT / "library" / cue["key"] / "manifest.json", {
                "kind": "library", "cue": cue["key"], "name": cue["name"],
                "intent": cue["intent"], "mood": cue["mood"], "use": cue["use"],
                "intensity": cue["intensity"], "loop": cue["loop"],
                "bpm_target": cue["bpm_target"], "tracks": tracks,
            })
            for track in tracks:
                print(f"  saved {track['mp3']} ({track['duration_s']}s)", flush=True)
        except Exception as error:
            # A paid submission is never retried automatically. Only the free
            # Turnstile step retries inside submit().
            print(f"  {cue['key']}: giving up: {type(error).__name__}: {error}", flush=True)
        music_index.build(ZONES, PLAN, VARIETY, OUT)
        print(f"[{i}/{len(cues)}] index updated; elapsed {time.time()-started:.0f}s", flush=True)
        time.sleep(5)
    music_index.build(ZONES, PLAN, VARIETY, OUT)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
