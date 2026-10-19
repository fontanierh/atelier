"""Import the optional selected music library as /Game/Audio/Music/<section>/<group>/<name>.

Run only when a build explicitly names `unreal.music`; the default game build
does not download or import the large Suno library. The runtime music director
selects tracks by the catalog tags, so the SoundWaves themselves stay plain.
"""
import json
import re
import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / "world"))
import yori  # noqa: E402
import unreal as U  # noqa: E402
from music_inventory import stale_assets  # noqa: E402

ROOT = yori.OUT
GAME = _Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "audio" / "music" / "manifest.json"
STAGED = GAME / "unreal" / "Content" / "Data" / "Music" / "library.json"
DEST = "/Game/Audio/Music"
E = U.EditorAssetLibrary
AT = U.AssetToolsHelpers.get_asset_tools()


def clean(value):
    value = re.sub(r"[^A-Za-z0-9_]+", "_", str(value or "track")).strip("_")
    return value or "track"


def main():
    data = json.loads(MANIFEST.read_text())
    tasks = []
    expected = {}
    by_name = {}
    for track in data.get("tracks", []):
        source = _Path(track["source"])
        section = clean(track.get("section", "library"))
        group = clean(track.get("group") or track.get("zone") or "misc")
        name = f"MUS_{section}_{group}_{clean(track.get('clip_id'))[:8]}"
        folder = f"{DEST}/{section}/{group}"
        E.make_directory(folder)
        task = U.AssetImportTask()
        for key, value in dict(
            filename=str(source), destination_path=folder, destination_name=name,
            automated=True, replace_existing=True, save=False,
        ).items():
            task.set_editor_property(key, value)
        task.set_editor_property("factory", U.SoundFactory())
        tasks.append(task)
        expected[name] = f"{folder}/{name}"
        by_name[name] = track

    AT.import_asset_tasks(tasks)
    imported = {}
    for task in tasks:
        for path in task.get_editor_property("imported_object_paths"):
            wave = E.load_asset(path)
            if not isinstance(wave, U.SoundWave):
                continue
            # The runtime crossfades phrase-level music; do not loop a whole long take.
            wave.set_editor_property("looping", False)
            E.save_loaded_asset(wave)
            imported[wave.get_name()] = {
                "path": wave.get_path_name(),
                "duration": wave.get_editor_property("duration"),
            }
    missing = sorted(set(expected) - set(imported))
    if missing:
        raise SystemExit(f"music: {len(missing)} files not imported: {missing[:10]}")
    deleted = stale_assets(E.list_assets(DEST, recursive=True, include_folder=False),
                           set(expected.values()))
    for path in deleted:
        if not E.delete_asset(path):
            raise RuntimeError(f"could not delete stale owned music: {path}")
    runtime = []
    for name, track in by_name.items():
        asset = imported.get(name)
        if not asset:
            continue
        runtime.append({
            "asset": asset["path"],
            "clip_id": track.get("clip_id"),
            "title": track.get("title"),
            "section": track.get("section"),
            "group": track.get("group"),
            "zone": track.get("zone"),
            "zone_name": track.get("zone_name"),
            "role": track.get("role"),
            "category": track.get("category"),
            "style_family": track.get("style_family"),
            "energy": track.get("energy"),
            "intensity": track.get("intensity"),
            "intent": track.get("intent"),
            "mood": track.get("mood"),
            "use": track.get("use"),
            "bpm_target": track.get("bpm_target"),
            "loop": track.get("loop"),
            "duration_s": track.get("duration_s"),
            "tags": track.get("tags", []),
        })
    STAGED.parent.mkdir(parents=True, exist_ok=True)
    STAGED.write_text(json.dumps({
        "schema": 1, "library": data.get("library"), "tracks": runtime,
    }, indent=2, ensure_ascii=False) + "\n")
    (ROOT / "music_import.json").write_text(json.dumps({
        "imported": imported, "missing": missing, "deleted": list(deleted),
        "library": str(STAGED),
    }, indent=2) + "\n")
    U.log(f"MUSIC IMPORT COMPLETE {len(imported)} waves")


if __name__ == "__main__":
    main()
