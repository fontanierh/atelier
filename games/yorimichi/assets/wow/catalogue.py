"""Join extracted client tables without inventing server-owned content or learned spells."""
from __future__ import annotations

from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import struct


class Dbc:
    """Raw 4-byte DBC fields for tables not registered with upstream's CSV dumper."""
    def __init__(self, path: Path, expected_fields: int):
        data = path.read_bytes()
        if len(data) < 20 or data[:4] != b"WDBC":
            raise ValueError(f"Invalid DBC: {path.name}")
        count, fields, size, string_size = struct.unpack_from("<4I", data, 4)
        if fields != expected_fields or size != fields * 4:
            raise ValueError(f"Unexpected schema for {path.name}: {fields} fields, {size} bytes")
        end = 20 + count * size
        if end + string_size != len(data):
            raise ValueError(f"Invalid DBC record/string extent: {path.name}")
        self.rows = [struct.unpack_from(f"<{fields}I", data, 20 + i * size) for i in range(count)]
        self.strings = data[end:]

    def string(self, offset: int) -> str:
        if not 0 <= offset < len(self.strings):
            raise ValueError("DBC string outside string block")
        end = self.strings.find(b"\0", offset)
        if end < 0:
            raise ValueError("Unterminated DBC string")
        return self.strings[offset:end].decode("utf-8")


def table(pack: Path, name: str) -> list[dict]:
    path = pack / f"decoded/dbfilesclient/{name.lower()}.dbc.csv"
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def build_catalogues(pack: Path, profile: dict) -> None:
    from pipeline import write_json
    manifest = json.loads((pack / "manifest.json").read_text())
    assets = {a["path"]: a for a in manifest["assets"]}
    models = {int(r["ID"]): r for r in table(pack, "CreatureModelData")}
    extras = {int(r["ID"]): r for r in table(pack, "CreatureDisplayInfoExtra")}
    appearances = []
    for row in table(pack, "CreatureDisplayInfo"):
        model = models.get(int(row["ModelID"]))
        if not model:
            continue
        source = model["ModelName"].replace("\\", "/").lower()
        if source.endswith((".mdx", ".mdl")):
            source = source[:-4] + ".m2"
        if source not in assets:
            continue
        appearances.append({"display_id": int(row["ID"]), "model_id": int(row["ModelID"]),
                            "model": source, "display": row, "model_metadata": model,
                            "npc_appearance": extras.get(int(row["ExtendedDisplayInfoID"])),
                            "gameplay_template": None})
    write_json(pack / "catalogues/creatures.json", {
        "schema_version": 1, "appearances": appearances,
        "missing": ["Named NPC/mob templates", "Spawn positions and patrols", "Level/health/AI/loot/faction rules"],
        "source": "Client display/model/appearance tables joined to the extracted model set",
    })
    write_json(pack / "catalogues/items.json", {
        "schema_version": 1, "display_records": table(pack, "ItemDisplayInfo"),
        "source": "Client appearance data; display ID is not item entry ID",
        "missing": ["Item names, rarity, required level, stats, prices and drop tables", "Chosen mage equipment loadout"],
    })
    spell_data = json.loads((pack / "catalogues/spells.json").read_text())
    spells = spell_data["spells"]
    ids = {s["id"] for s in spells}
    ability_rows = Dbc(pack / "raw/dbfilesclient/skilllineability.dbc", 15).rows
    links = [{"id": row[0], "skill_id": row[1], "spell_id": row[2], "raw_fields": row}
             for row in ability_rows if row[2] in ids]
    tabs = Dbc(pack / "raw/dbfilesclient/talenttab.dbc", 15)
    class_mask = 1 << (profile["character"]["class_id"] - 1)
    selected_tabs = [{"id": row[0], "name": tabs.string(row[1]), "class_mask": row[12], "raw_fields": row}
                     for row in tabs.rows if row[12] & class_mask]
    tab_ids = {row["id"] for row in selected_tabs}
    talents = Dbc(pack / "raw/dbfilesclient/talent.dbc", 21)
    selected_talents = [{"id": row[0], "tab_id": row[1], "row": row[2], "column": row[3],
                         "rank_spell_ids": list(row[4:9]), "raw_fields": row}
                        for row in talents.rows if row[1] in tab_ids]
    highest = {}
    for spell in spells:
        if spell["family_member"] and spell["level_eligible"] and not spell["passive"]:
            current = highest.get(spell["name"])
            if current is None or (spell["spell_level"], spell["id"]) > (current["spell_level"], current["id"]):
                highest[spell["name"]] = spell
    write_json(pack / "catalogues/character.json", {
        "schema_version": 1, "profile": profile["character"], "talent_tabs": selected_tabs,
        "talents": selected_talents, "skill_line_links": links,
        "level_eligible_spell_ids": sorted(s["id"] for s in spells if s["level_eligible"] and s["family_member"]),
        "highest_level_candidate_per_name": {name: spell["id"] for name, spell in sorted(highest.items())},
        "learned_spell_ids": None, "selected_talents": None, "base_stats": None, "playable": False,
        "limits": ["Candidates do not grant talent/quest/racial/item spells", "Highest-level candidate is not a verified rank chain",
                   "Base stats, known spells and equipment require explicit native content definitions or a separate reference dataset"],
    })
    effects = Counter(effect["type"] for s in spells for effect in s["effects"] if effect["type"])
    auras = Counter(effect["aura"] for s in spells for effect in s["effects"] if effect["aura"])
    write_json(pack / "catalogues/mechanics.json", {
        "schema_version": 1, "effect_type_usage": dict(sorted(effects.items())), "aura_type_usage": dict(sorted(auras.items())),
        "state_fields": ["target", "range/line of sight", "cast/channel state", "resource cost", "individual/category/global cooldown",
                         "projectile arrival", "effect/aura application", "proc/interrupt", "death/reward"],
        "effect_execution_implemented": False,
        "source_metadata": "spells.json contains coefficients, flags, durations, effects and visual-stage references",
        "next": "Implement and verify selected effects; metadata is not executable combat logic",
    })


def verify_pack(pack: Path) -> dict:
    manifest = json.loads((pack / "manifest.json").read_text())
    errors = []
    root = pack.resolve()
    seen = set()
    paths = {a["path"] for a in manifest["assets"]}
    for asset in manifest["assets"]:
        if asset["path"] in seen:
            errors.append(f"Duplicate asset: {asset['path']}")
        seen.add(asset["path"])
        for key, digest in (("raw", "sha256"), ("decoded", "decoded_sha256")):
            if not asset.get(key):
                continue
            path = (pack / asset[key]).resolve()
            if not path.is_relative_to(root):
                errors.append(f"Unsafe output path: {asset[key]}")
                continue
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != asset[digest]:
                errors.append(f"Missing or changed output: {asset[key]}")
        for dependency in asset["dependencies"]:
            if dependency not in paths:
                errors.append(f"Unresolved dependency: {asset['path']} -> {dependency}")
    if not manifest["complete"] or manifest["failures"]:
        errors.append("Extraction manifest is incomplete")
    if errors:
        raise ValueError("Pack verification failed:\n" + "\n".join(errors[:30]))
    return {"valid": True, "assets_checked": len(manifest["assets"]), "raw_and_decoded_hashes": True,
            "dependency_closure": True, "gameplay_tested": False, "unreal_used": False}
