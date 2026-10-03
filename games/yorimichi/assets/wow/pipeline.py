"""Offline WoW extraction; all generated and retail-derived content stays under build/."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib

HERE = Path(__file__).resolve().parent
# The tool directory can be copied to a machine with no game checkout or Atelier installation.
ROOT = next((p for p in HERE.parents if (p / "ARCHITECTURE.md").is_file() and (p / "pyproject.toml").is_file()), None)
DEFAULT_OUTPUT = ROOT / "build/yorimichi/wow" if ROOT else HERE.parent / "wow-extraction-output"
REVISION = "b396bbf69a0486b6d29829ec191145f63c363eea"
TABLES = (
    "Spell", "SpellIcon", "SpellRange", "SpellCastTimes", "SpellDuration", "SpellRadius",
    "SpellVisual", "SpellVisualKit", "SpellVisualEffectName", "SkillLine", "SkillLineAbility",
    "ChrClasses", "ChrRaces", "CharSections", "CharHairGeosets", "CharacterFacialHairStyles",
    "CharStartOutfit", "CreatureDisplayInfo", "CreatureDisplayInfoExtra", "CreatureModelData",
    "ItemDisplayInfo", "ItemClass", "ItemSubClass", "ItemSet", "ItemVisuals", "ItemVisualEffects",
    "SpellItemEnchantment", "Talent", "TalentTab", "AnimationData", "GameObjectDisplayInfo",
    "AreaTable", "Map", "SoundEntries", "WMOAreaTable", "HelmetGeosetVisData", "Faction",
    "FactionTemplate", "GroundEffectTexture", "GroundEffectDoodad",
)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def output_path(path: Path) -> Path:
    resolved = path.resolve()
    if ROOT is not None and not resolved.is_relative_to(ROOT / "build"):
        raise ValueError("Generated outputs must be inside this checkout's ignored build/ directory")
    return resolved


def profile(path: Path) -> dict:
    value = tomllib.loads(path.read_text())
    if value.get("schema_version") != 1 or value.get("client_build") != 5875:
        raise ValueError("Only extraction schema 1 and client build 5875 are supported")
    if value.get("benilla_revision") != REVISION:
        raise ValueError("Profile and pinned decoder revision differ")
    c = value["character"]
    if not 1 <= c["level"] <= 60 or c["class_id"] not in {1, 2, 3, 4, 5, 7, 8, 9, 11}:
        raise ValueError("Invalid vanilla character level/class")
    return value


def plan(value: dict) -> dict:
    character, world, selection = value["character"], value["world"], value["selection"]
    return {
        "schema_version": 1,
        "seeds": sorted(set([f"DBFilesClient/{name}.dbc" for name in TABLES]
                            + character["models"] + world["roots"])),
        "prefixes": ["DBFilesClient"] + selection["creature_patterns"] + selection["item_patterns"],
        "world": {"map": world["map"], "center_yards": world["center_yards"],
                  "tile_radius": world["tile_radius"]},
        "class_id": character["class_id"], "spell_family": character["spell_family"],
        "level": character["level"], "max_assets": selection["max_assets"],
    }


def data_path(supplied: str | None) -> Path | None:
    value = supplied or os.environ.get("WOW_DATA")
    if not value:
        return None
    path = Path(value).expanduser().resolve()
    child = next((p for p in path.iterdir() if p.is_dir() and p.name.casefold() == "data"), None) if path.is_dir() else None
    return child or path


def doctor(data: Path | None, output: Path) -> dict:
    archives = sorted((p for p in data.iterdir() if p.suffix.casefold() == ".mpq"), key=lambda p: p.name.casefold()) if data and data.is_dir() else []
    names = {p.name.casefold() for p in archives}
    essentials = {"dbc.mpq", "model.mpq", "texture.mpq", "terrain.mpq", "wmo.mpq", "patch.mpq"}
    missing = sorted(essentials - names)
    ready = bool(data and not missing)
    report = {
        "schema_version": 1, "status": "ready_for_archive_validation" if ready else "blocked_missing_client_data",
        "source": str(data) if data else None, "target": {"version": "1.12.1", "build": 5875, "locale": "enUS"},
        "source_build_verified": False, "archives": [{"name": p.name, "bytes": p.stat().st_size} for p in archives],
        "missing_archives": missing, "tools": {n: bool(shutil.which(n)) for n in ("cargo", "rustc")},
        "retail_extracted": False, "unreal_used": False,
        "next": "Run extract to validate archives and decode selected content" if ready else "Supply --data or WOW_DATA pointing at a matching vanilla client Data folder",
    }
    write_json(output / "doctor.json", report)
    return report


def build(output: Path, *, test: bool = False) -> Path:
    binary = output / "tools/debug" / ("yorimichi-wow-extract.exe" if os.name == "nt" else "yorimichi-wow-extract")
    command = ["cargo", "test" if test else "build", "--locked", "--manifest-path",
               str(HERE / "extractor/Cargo.toml"), "--target-dir", str(output / "tools")]
    # Compiles always use the guarded big slot. There is no Unreal or Blender process.
    code = run_job(command, output / "jobs" / ("test" if test else "build"), timeout=900,
                   purpose="wow-offline-extractor", kind="compile")
    if code:
        raise RuntimeError(f"Decoder build failed; inspect {output / 'jobs/build/stdout.log'}")
    return binary


def run_job(command: list[str], folder: Path, *, timeout: int, purpose: str, kind: str) -> int:
    if ROOT is not None:
        from atelier.safety.guarded import run
        return run(command, folder, timeout=timeout, purpose=purpose, kind=kind)
    # Standalone use has no Atelier dependency. Preserve logs and deadlines for the handoff.
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / "stdout.log").open("w") as stream:
        return subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, timeout=timeout).returncode


def archive_provenance(data: Path) -> list[dict]:
    records = []
    for path in sorted(data.iterdir(), key=lambda p: p.name.casefold()):
        if path.is_file() and path.suffix.casefold() == ".mpq":
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
                    digest.update(block)
            records.append({"name": path.name, "bytes": path.stat().st_size, "sha256": digest.hexdigest()})
    return records


def extract(data: Path | None, value: dict, output: Path) -> None:
    report = doctor(data, output)
    if report["status"] != "ready_for_archive_validation":
        raise ValueError(report["next"])
    assert data is not None
    if output.is_relative_to(data) or data.is_relative_to(output):
        raise ValueError("Source data and generated output must be separate")
    binary = build(output)
    pack = output / "pack"
    if pack.exists():
        raise ValueError("Pack output already exists; choose a fresh --output to avoid mixing revisions")
    write_json(output / "plan.json", plan(value))
    write_json(output / "input-provenance.json", {"archives": archive_provenance(data), "profile": value})
    subprocess.run([str(binary), "inventory", str(data), str(output / "inventory.json")], check=True)
    write_json(output / "status.json", {"status": "extracting", "retail_extracted": False, "playable": False})
    jobs = [([str(binary), "pack", str(data), str(output / "plan.json"), str(pack)], "extract"),
            ([sys.executable, str(HERE / "prepare.py"), str(output)], "prepare")]
    for command, name in jobs:
        code = run_job(command, output / "jobs" / name, timeout=3600, purpose=f"wow-{name}", kind="job")
        if code:
            write_json(output / "status.json", {"status": f"{name}_failed", "retail_extracted": False, "playable": False})
            raise RuntimeError(f"{name} failed; inspect {output / 'jobs' / name / 'stdout.log'}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("doctor", "plan", "build", "test", "extract", "verify"))
    parser.add_argument("--data", help="Local vanilla client root or Data folder; defaults to WOW_DATA")
    parser.add_argument("--profile", type=Path, default=HERE / "profile.toml")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    try:
        output = output_path(args.output)
        value = profile(args.profile)
        if args.command == "doctor":
            report = doctor(data_path(args.data), output)
            print(f"{report['status']}: {report['next']}")
        elif args.command == "plan":
            write_json(output / "plan.json", plan(value))
            print(output / "plan.json")
        elif args.command in {"build", "test"}:
            print(build(output, test=args.command == "test"))
        elif args.command == "extract":
            extract(data_path(args.data), value, output)
            print(output / "pack/manifest.json")
        else:
            from catalogue import verify_pack
            report = verify_pack(output / "pack")
            write_json(output / "verification.json", report)
            print(json.dumps(report, indent=2))
        return 0
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
