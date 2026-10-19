#!/usr/bin/env python3
"""Rebuild the review index and apply the shared music tags."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROLE_INTENT = {
    "day": ("exploration", "warm/day", "zone arrival and daytime exploration"),
    "quiet": ("ambient", "quiet/night", "low-intensity exploration and ambience"),
    "contrast": ("contrast", "contrast", "alternate mood for landmarks, festivals, storms or set pieces"),
}
ROLE_STYLE = {
    "day": "orchestral",
    "quiet": "ambient/orchestral",
    "contrast": "orchestral/contrast",
}


def category(role, energy, style, intent=""):
    """Coarse selection label for the runtime music director."""
    if role == "action" and energy <= 2 and intent in ("tension", "story"):
        return "calm"
    if role == "action" and energy >= 3:
        return "action"
    if energy >= 4:
        return "energetic"
    if (role == "quiet" or (style.startswith("ambient") and energy <= 2)
            or (style == "lofi" and energy <= 2)):
        return "calm"
    if role == "contrast":
        return "contrast"
    return "moderate"


ZONE_ENERGY = {
    "spawn": 2, "hamlet": 2, "mega": 4, "fishing": 2, "cove": 2, "landing": 2,
    "temple": 2, "arrival": 3, "arcade": 3, "plaza": 3, "harbor": 2, "hillside": 1,
    "park": 2, "station": 2, "foothills": 3, "forest_lake": 1, "megapark": 4,
    "skatepier": 4, "zeppelin_forest": 3, "zeppelin_city": 3, "zeppelin_megapark": 3,
    "communitypark": 4, "hippodrome": 4, "craterpark": 5, "belmonte": 2,
    "belmonte_course": 5, "belmonte_training": 2, "belmonte_salon": 1,
}


def load(path):
    path = Path(path)
    return json.loads(path.read_text()) if path.exists() else None


def save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def portable(path, out):
    """Store release-safe paths relative to the music root when possible."""
    if not path:
        return path
    try:
        return Path(path).resolve().relative_to(Path(out).resolve()).as_posix()
    except (OSError, ValueError):
        return path


def normalize_track(track, out):
    changed = False
    for field in ("mp3", "m4a"):
        value = track.get(field)
        if value:
            rel = portable(value, out)
            if rel != value:
                track[field] = rel
                changed = True
    return changed


def label_variants(tracks):
    """Give the two takes of one cue stable, readable A/B display names."""
    groups = {}
    for track in tracks:
        base = track.get("title") or track.get("clip_id") or "Untitled"
        groups.setdefault(base, []).append(track)
    changed = False
    for base, takes in groups.items():
        if len(takes) < 2:
            continue
        for index, track in enumerate(takes):
            label = f"{base} ({chr(ord('A') + index)})"
            if track.get("display_title") != label:
                track["display_title"] = label
                changed = True
    return changed


def tag_zone_tracks(zone, out):
    path = Path(out) / zone["key"] / "manifest.json"
    manifest = load(path)
    if not manifest:
        return None
    changed = False
    base = ZONE_ENERGY.get(zone["key"], 2)
    for track in manifest.get("tracks", []):
        changed = normalize_track(track, out) or changed
        role = track.get("role", "day")
        intent, mood, use = ROLE_INTENT.get(role, ("exploration", "neutral", "zone score"))
        style = ROLE_STYLE.get(role, "orchestral")
        if role == "quiet":
            energy = max(1, base - 1)
        elif role == "contrast":
            energy = min(5, base + 1)
        else:
            energy = base
        kind = category(role, energy, style, intent)
        values = {
            "zone": zone["key"], "zone_name": zone["name"], "intent": intent,
            "mood": mood, "use": use, "style_family": style, "energy": energy,
            "category": kind,
            "tags": ["instrumental", "v6", "yorimichi", "zone:" + zone["key"],
                     "role:" + role, "style:" + style, "energy:" + str(energy),
                     "category:" + kind, "intent:" + intent, "mood:" + mood,
                     "use:" + use],
        }
        for key, value in values.items():
            if track.get(key) != value:
                track[key] = value
                changed = True
    changed = label_variants(manifest.get("tracks", [])) or changed
    if changed:
        save(path, manifest)
    return manifest


def tag_action_tracks(manifest, out):
    changed = False
    for track in manifest.get("tracks", []):
        changed = normalize_track(track, out) or changed
        energy = track.get("energy", track.get("intensity", 3))
        style = track.get("style_family", "action/orchestral")
        kind = category("action", energy, style, str(track.get("intent", "action")))
        tags = list(track.get("tags", []))
        wanted = [
            "zone:library", "role:action", "style:" + style,
            "energy:" + str(energy), "category:" + kind,
            "intent:" + str(track.get("intent", "action")),
            "mood:" + str(track.get("mood", "")), "use:" + str(track.get("use", "")),
            "intensity:" + str(track.get("intensity", energy)),
            "loop:" + str(bool(track.get("loop", True))).lower(),
            "bpm:" + str(track.get("bpm_target", "")),
        ]
        for value in wanted:
            if value not in tags:
                tags.append(value)
        if (track.get("energy") != energy or track.get("style_family") != style
                or track.get("category") != kind or track.get("tags") != tags):
            track["energy"] = energy
            track["style_family"] = style
            track["category"] = kind
            track["tags"] = tags
            changed = True
    changed = label_variants(manifest.get("tracks", [])) or changed
    return changed


def tag_variety_tracks(manifest, out):
    changed = False
    for track in manifest.get("tracks", []):
        changed = normalize_track(track, out) or changed
        style = track.get("style_family", "variety")
        energy = track.get("energy", 2)
        kind = category("variety", energy, style, str(track.get("intent", "")))
        tags = list(track.get("tags", []))
        wanted = [
            "zone:variety", "role:variety", "style:" + style,
            "energy:" + str(energy), "category:" + kind,
            "intent:" + str(track.get("intent", "")),
            "mood:" + str(track.get("mood", "")), "use:" + str(track.get("use", "")),
            "loop:" + str(bool(track.get("loop", True))).lower(),
            "bpm:" + str(track.get("bpm_target", "")),
        ]
        for value in wanted:
            if value not in tags:
                tags.append(value)
        if (track.get("tags") != tags or track.get("style_family") != style
                or track.get("energy") != energy or track.get("category") != kind):
            track["style_family"] = style
            track["energy"] = energy
            track["category"] = kind
            track["tags"] = tags
            changed = True
    changed = label_variants(manifest.get("tracks", [])) or changed
    return changed


def build(zone_plan_path, action_plan_path, variety_plan_path, out):
    out = Path(out)
    zone_plan = json.loads(Path(zone_plan_path).read_text())
    zones = []
    for zone in zone_plan["zones"]:
        manifest = tag_zone_tracks(zone, out)
        if not manifest:
            continue
        zones.append({
            "key": zone["key"], "name": zone["name"], "hint": zone.get("hint", ""),
            "total": 2 * len(zone["prompts"]), "tracks": manifest.get("tracks", []),
        })

    action_plan = load(action_plan_path) or {"cues": []}
    library = []
    for cue in action_plan.get("cues", []):
        path = out / "library" / cue["key"] / "manifest.json"
        manifest = load(path)
        if not manifest:
            continue
        if tag_action_tracks(manifest, out):
            save(path, manifest)
        library.append({
            "key": cue["key"], "name": cue["name"], "hint": "Action & set pieces",
            "total": 2, "tracks": manifest.get("tracks", []),
        })

    variety_plan = load(variety_plan_path) or {"cues": []}
    variety = []
    for cue in variety_plan.get("cues", []):
        manifest = load(out / "variety" / cue["key"] / "manifest.json")
        if not manifest:
            continue
        if tag_variety_tracks(manifest, out):
            save(out / "variety" / cue["key"] / "manifest.json", manifest)
        variety.append({
            "key": cue["key"], "name": cue["name"], "hint": "Variety library",
            "total": 2, "tracks": manifest.get("tracks", []),
        })

    total = (sum(len(zone["tracks"]) for zone in zones)
             + sum(len(cue["tracks"]) for cue in library)
             + sum(len(cue["tracks"]) for cue in variety))
    index = {
        "game": zone_plan["game"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": zone_plan["model"],
        "total_zones": len(zone_plan["zones"]),
        "total_tracks": total,
        "counts": {
            "zones": len(zones), "action": len(library), "variety": len(variety),
            "tracks": total,
        },
        "zones": zones,
        "library": library,
        "variety": variety,
    }
    save(out / "index.json", index)
    return index
