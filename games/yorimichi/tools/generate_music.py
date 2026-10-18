#!/usr/bin/env python3
"""Generate Yorimichi's zone soundtrack from the committed plan."""
import argparse
import json
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from suno_client import Suno

ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / "games/yorimichi/assets/audio/music/plan.json"
OUT = ROOT / "build/yorimichi/music"


def load_plan():
    return json.loads(PLAN.read_text())


def manifest_path(zone_key):
    return OUT / zone_key / "manifest.json"


def load_manifest(zone_key):
    p = manifest_path(zone_key)
    return json.loads(p.read_text()) if p.exists() else None


def save_manifest(zone_key, data):
    p = manifest_path(zone_key)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, p)


def role_complete(manifest, role):
    if not manifest:
        return False
    tracks = [t for t in manifest.get("tracks", []) if t.get("role") == role]
    if len(tracks) < 2:
        return False
    return all(Path(t.get("mp3", "")).exists() for t in tracks)


def write_index(plan):
    zones = []
    for z in plan["zones"]:
        m = load_manifest(z["key"])
        if m:
            zones.append({"key": z["key"], "name": z["name"], "hint": z["hint"],
                          "tracks": m.get("tracks", [])})
    index = {"game": plan["game"], "generated_at": datetime.now(timezone.utc).isoformat(),
             "model": plan["model"], "duration": plan["duration"],
             "total_zones": len(plan["zones"]), "total_tracks": len(plan["zones"]) * 4,
             "zones": zones}
    p = OUT / "index.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, p)
    return index


def generate_role(client, plan, zone, role):
    prompt = plan["style"] + " " + zone["prompts"][role]
    print(f"  {zone['key']}/{role}: submitting", flush=True)
    data = client.generate(
        prompt, instrumental=True, model=plan["model"], duration=plan["duration"],
        negative_tags=plan.get("negative", ""),
    )
    clips = data.get("clips", [])
    ids = [c["id"] for c in clips]
    print(f"  {zone['key']}/{role}: clips {ids}", flush=True)
    clips = client.wait(ids, timeout=1200, interval=5)
    tracks = []
    for c in clips:
        if c.get("status") != "complete":
            raise RuntimeError(f"clip {c.get('id')} ended {c.get('status')}: "
                               f"{c.get('metadata', {}).get('error_message')}")
        files = client.download(c["id"])
        kept = []
        for src in files:
            src = Path(src)
            dst = OUT / zone["key"] / src.name
            shutil.copy2(src, dst)
            kept.append(str(dst))
        mp3 = next((p for p in kept if p.endswith(".mp3")), None)
        if not mp3:
            raise RuntimeError(f"no mp3 for {c['id']}")
        tracks.append({
            "role": role,
            "clip_id": c["id"],
            "title": c.get("title") or c["id"],
            "model": c.get("model_name") or plan["model"],
            "duration_s": c.get("metadata", {}).get("duration"),
            "prompt": prompt,
            "mp3": mp3,
            "m4a": next((p for p in kept if p.endswith(".m4a")), None),
            "created_at": c.get("created_at"),
            "credits_estimate": 5,
        })
    return tracks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zone", action="append", default=[])
    ap.add_argument("--role", choices=("day", "quiet"))
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    plan = load_plan()
    zones = [z for z in plan["zones"] if not args.zone or z["key"] in args.zone]
    client = Suno()
    started = time.time()
    for i, zone in enumerate(zones, 1):
        OUT.joinpath(zone["key"]).mkdir(parents=True, exist_ok=True)
        manifest = load_manifest(zone["key"]) or {
            "zone": zone["key"], "name": zone["name"], "hint": zone["hint"],
            "tracks": [],
        }
        for role in (("day",) if args.role == "day" else ("quiet",) if args.role == "quiet" else ("day", "quiet")):
            if not args.force and role_complete(manifest, role):
                print(f"[{i}/{len(zones)}] {zone['key']}/{role}: already complete", flush=True)
                continue
            print(f"[{i}/{len(zones)}] {zone['key']}/{role}: generating", flush=True)
            last = None
            for attempt in (1, 2, 3, 4):
                try:
                    tracks = generate_role(client, plan, zone, role)
                    manifest["tracks"] = [t for t in manifest["tracks"] if t.get("role") != role] + tracks
                    save_manifest(zone["key"], manifest)
                    for t in tracks:
                        print(f"  saved {t['mp3']} ({t['duration_s']}s)", flush=True)
                    last = None
                    break
                except Exception as e:
                    last = e
                    print(f"  {zone['key']}/{role} attempt {attempt} failed: {type(e).__name__}: {e}", flush=True)
                    if attempt < 4:
                        time.sleep(30)
            if last is not None:
                print(f"  {zone['key']}/{role}: giving up for this pass", flush=True)
            time.sleep(5)
        write_index(plan)
        print(f"[{i}/{len(zones)}] index updated; elapsed {time.time()-started:.0f}s", flush=True)
    write_index(plan)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
