#!/usr/bin/env python3
"""Pull the Sonniss GDC masters used by the combat sound library from archive.org.

These are the raw library files (44.1-192 kHz, 16/24-bit, often several takes per
file). They are gitignored: run this to restore them into audio/sonniss/combat/,
then tools/slice_combat_sfx.py to rebuild the game-ready one-shots in
audio/combat/.

Every file comes from a Sonniss GDC Game Audio Bundle mirror on archive.org
(royalty-free, commercial use, no attribution; see audio/sonniss/LICENSE.txt).
The licence forbids feeding these files to any AI model: local signal processing
only. Each download is checked against the md5 published in the archive.org item
metadata, so a rebuild always starts from byte-identical masters.

Usage:  python3 tools/fetch_sonniss_combat.py [--force]
"""
import argparse, hashlib, json, sys, time, urllib.parse, urllib.request
from pathlib import Path

import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
from atelier.paths import cache_dir  # noqa: E402
ROOT = cache_dir('sonniss', 'combat')  # outside the repository: the licence forbids redistributing them

# (local name, archive item, path inside item, md5, bytes)
PICKS = [
 # --- swings, whooshes, dashes ---
 ('jse_woodstick_swish_03.wav', 'sonniss-gdc-2023-game-audio-bundle-normalized', 'Justsoundeffects - Transition Whooshes Vol. 1/SWSH_Woodstick Swish 03_JSE_TW1.wav', 'c9c5b2903f1417c3cb59ed71aa55ebbc', 4166374),
 ('soundbits_whoosh_rod_pole_022.wav', 'sonniss-gdc-2016-game-audio-bundle-normalized', 'SoundBits -  Just Whoosh 3 _ Whoosh Essentials/Whoosh_Rod_Pole_022.wav', '9ef305a83c70a8d29fdfad5821eecfec', 1058456),
 ('ddumais_swing_large_03.wav', 'sonniss-gdc-2023-game-audio-bundle-normalized', 'David Dumais Audio - Melee Weapons Sound Effects Pack 1/SWSH_Swing 3 Large 03_DDUMAIS_NONE.wav', '7a862b25b167ea78b5f96dd88d67d4d7', 523344),
 ('rts_rope_whoosh_fast_light_01.wav', 'sonniss-gdc-2019-game-audio-bundle-normalized', 'Rock The Speakerbox - Melee/MELEE - CK - ROPE WHOOSH Fast Light 01.wav', 'b51322a3a9775fc59c89d1d07b9a703b', 5631030),
 ('eiravaein_fencingfoil_swoosh.wav', 'sonniss-gdc-2015-game-audio-bundle-normalized', 'Eiravaein Works - Vaeyan II/FencingFoil,swoosh,roomambience,lively,quick,aggressive.M.wav', 'af0a4ab2e06b6a8b680d9d52964964a8', 242924),
 ('soundholder_tshirt_fast_swings.wav', 'sonniss-gdc-2019-game-audio-bundle-normalized', 'Soundholder - Swipes And Whooshes/swipes and whooshes tshirt fast and short swings stereo ORTF 8040.wav', 'b9f038421faee1c05baa1bdaa2b9b20b', 9256004),
 ('airborne_fabric_glove_whoosh.wav', 'sonniss-gdc-2019-game-audio-bundle-normalized', 'Airborne Sound - Organic Whooshes/Whoosh,Organic,Fabric,Glove,Airy,Breathy,Punchy.wav', '394358a8a647f5aca1a7a492ff35f8e0', 542600),
 ('mechwave_action_swish_02.wav', 'sonniss-gdc-2015-game-audio-bundle-normalized', 'Mechanical Wave - Hits Whoosh/Action Swish_HW 02.wav', 'f30d383343de6ef50614ded02816524e', 2576428),
 ('matiasvidal_riser_16.wav', 'sonniss-gdc-2020-game-audio-bundle-normalized', 'Matias Vidal Saavedra -Filmmaker Ultimate Sounds/Riser_16.wav', '9e59afc4130335795045f87b4d002204', 1152924),
 ('articulated_magic_air_swirl_01.wav', 'sonniss-gdc-2019-game-audio-bundle-normalized', 'Articulated Sounds - Magic Elements vol.1/MAGIC AIR Large Whoosh, Swirl, Wind Gust, Foliage 01.wav', 'e222e1d9a2a20a4d5f4381275a440b6c', 1917612),
 # --- hits and impacts ---
 ('mchugh_wood_beating_flesh_medium_11.wav', 'sonniss-gdc-2015-game-audio-bundle-normalized', 'Timothy McHugh - Gorification [HD]/gore - wood beating flesh wet blood splat - medium - 11.wav', '1cf759956b6f6167082243a598bfb038', 423452),
 ('mchugh_wood_beating_flesh_soft_04.wav', 'sonniss-gdc-2015-game-audio-bundle-normalized', 'Timothy McHugh - Gorification [HD]/gore - wood beating flesh wet blood splat - soft - 4.wav', '8f5818aa550c15fff673a4a633772f74', 474204),
 ('rts_flog_leather_hit_smack_01.wav', 'sonniss-gdc-2019-game-audio-bundle-normalized', 'Rock The Speakerbox - Melee/MELEE - CK - FLOG Leather Hit Smack 01.wav', 'ab00d587ac7909d1031736b23867a383', 8968402),
 ('duffield_keeper_punch_01.wav', 'sonniss-gdc-2016-game-audio-bundle-normalized', 'Stuart Duffield - Soccer SFX/Keeper_Punch_01.wav', '6242174c96e29fbe75d7e2b045fba3e8', 70490),
 ('gamemaster_punch_body_impact_03.wav', 'sonniss-gdc-2017-game-audio-bundle-normalized', 'Gamemaster Audio -  Punch Sound Pack/punch_general_body_impact_03.wav', '3cb59470975e315718c4044e294a607b', 274286),
 ('chrisalan_deep_punch_02.wav', 'sonniss-gdc-2018-game-audio-bundle-normalized', 'The Chris Alan - Hand-to-Hand Combat - Body Hits & Vocal Excursions/Hand-to-Hand Combat - Body Hits - Deep Punch 02.wav', '8cbc0c3ea8e3ed54375df284c4abb37d', 120504),
 ('gamemaster_body_thump_02.wav', 'sonniss-gdc-2017-game-audio-bundle-normalized', 'Gamemaster Audio -  Bullet Impact Sounds/bullet_impact_body_thump_02.wav', '50b813034ede235a6b932165d1ec6850', 271310),
 ('gamemaster_punch_heavy_huge_01.wav', 'sonniss-gdc-2017-game-audio-bundle-normalized', 'Gamemaster Audio -  Punch Sound Pack/punch_heavy_huge_distorted_01.wav', 'b1622f4dfba1bd0c13e20fc5469547d6', 278738),
 ('pmsfx_punch_clean_deep_48.wav', 'sonniss-gdc-2020-game-audio-bundle-normalized', 'PMSFX - Lethal Blow/PM_LB_DESIGNED_PUNCH_SIMPLE_CLEAN_DEEP_48.wav', '82963334599fe9b48a40a2c8c925dcec', 574332),
 ('344_explosive_hit_10_low_end.wav', 'sonniss-gdc-2019-game-audio-bundle-normalized', '344 Audio - Low Frequency Elements/Explosive Hit 10 Filtered, Low End.wav', '91b6ae41fb0b7ab67f75cd4250486131', 882596),
 ('344_spear_stick_impact_wooden.wav', 'sonniss-gdc-2026-game-audio-bundle-normalized', '344 Audio - Historical Weapons Vol. 2/WEAPBlnt_Spear And Stick Impact, Wooden MKH 2_344 Audio_Medieval Weapons Vol 2.wav', 'b2728ae0616129b540b7faa8b26e925f', 13081382),
 ('audioville_stick_hit_13_wild.wav', 'sonniss-gdc-2016-game-audio-bundle-normalized', 'The AudioVille - Wooden Staffs and Sword Fight/STICK HIT-13 - WILD.M.wav', '0fbaf2ca39debf06d18f193bb7e67480', 129972),
 ('audioville_wooden_sword_hit_11.wav', 'sonniss-gdc-2016-game-audio-bundle-normalized', 'The AudioVille - Wooden Staffs and Sword Fight/WOODEN SWORD HIT-11.M.wav', '8338a947a245b4adffd03d2114014713', 47036),
 ('smartsound_sword_hit_metal_02.wav', 'sonniss-gdc-2020-game-audio-bundle-normalized', 'SmartSoundFX – Medieval/SWORD Hit Metal 02.wav', 'ce87b3aea3024d483426462a500dbcc9', 422236),
 ('redlib_bodyfall_dirt_hard_10.wav', 'sonniss-gdc-2019-game-audio-bundle-normalized', 'Red Libraries - Bodyfall/RL_bodyfall_Dirt_M4_Close_Stereo_Hard_Impact_10.wav', '32129bd879b51d23713a8176d6dac387', 698288),
 ('chrisalan_body_slam_floor_08.wav', 'sonniss-gdc-2018-game-audio-bundle-normalized', 'The Chris Alan - Hand-to-Hand Combat - Body Hits & Vocal Excursions/Hand-to-Hand Combat - Body Hits - Body Slam Floor 08.wav', '1c47597b63f3186db6a32aa806a9e03b', 258126),
 ('pmsfx_dry_grass_skid_drag.wav', 'sonniss-gdc-2020-game-audio-bundle-normalized', 'PMSFX - STEPS Dry Grass & Shrubs/PM_SDGS_213 Footstep Step Dry Grass Skid Drag.wav', 'b2a19e864603a1a644763a9a7ef1daff', 1087676),
 ('baxter_hit_big_drum_03.wav', 'sonniss-gdc-2019-game-audio-bundle-normalized', 'Baxter Audio - IMPACT/03 Hit Big Drum.wav', '196d8b040a925d00651d44c3b611e89c', 2115842),
 # --- bokken handling (cloth + wood) ---
 ('shapeforms_clothing_movement_08.wav', 'sonniss-gdc-2020-game-audio-bundle-normalized', 'Shapeforms - Hit & Punch/CLOTHING_MATERIAL_MOVEMENT_08.wav', '26df0b09fa3fab287299ad5d6fe29aec', 194256),
 ('soundbits_scrape_cloth_10.wav', 'sonniss-gdc-2019-game-audio-bundle-normalized', 'SoundBits - Tiny Transitions 2/Scrape_Cloth_10.wav', 'e1927810bba6432e94c5515906b71b57', 348498),
 ('esm_cloth_canvas_bag_slide_02.wav', 'sonniss-gdc-2026-game-audio-bundle-normalized', 'Epic Stock Media - Fantasy Game 2 - Sound Kit for Enchanted Realms/CLOTHFlp_Action Inventory Open Flip Cloth Canvas Bag Slide Light 02_ESM_FG2.wav', '1f4bd9473509556bb84a27e012c2368a', 1000064),
 ('inmotion_tshirt_single_pats_04.wav', 'sonniss-gdc-2026-game-audio-bundle-normalized', 'InMotionAudio - Foley T-Shirt/FOLYClth_SinglePats04_InMotionAudio_FoleyT-Shirt.wav', '670fcf84c510dc9df261bd4d2977a6fb', 333406),
 # --- bell, creature, ambience ---
 ('eiravaein_japanese_windbell.wav', 'sonniss-gdc-2019-game-audio-bundle-normalized', 'Eiravaein Works - Helina/Helinä,windbell,Japanese,porcelain,clapper,paperwindcatcher,cottonrope,gust,strong,shorttail,MidSide.wav', '56dc78de23af21374957e47d6495a19d', 5220012),
 ('vicic_red_fox_winter_scream.wav', 'sonniss-gdc-2020-game-audio-bundle-normalized', 'Ivo Vicic - European mountain forest animals and soundscapes/119 Red fox_winter_scream_naural echo.wav', 'c48756a931ec3654fc89e9aadf9be9b1', 29291566),
 ('soundopolis_yorkshire_growl.wav', 'sonniss-gdc-2020-game-audio-bundle-normalized', 'Soundopolis - Dogs/Dog_Yorkshire Terrier_Growl_Fienup_001.wav', '00b3e709b838ef8306a5417124691c5e', 4489760),
 ('soundexmachina_rural_summer.wav', 'sonniss-gdc-2017-game-audio-bundle-normalized', 'Sound Ex Machina -  Mediterranean Summertime/Rural summer with birdsong, distant sea waves, breeze.wav', 'd1e91403aa3b3d4e9987978b874da7b7', 56316342),
]


def md5sum(path: Path) -> str:
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--force', action='store_true', help='re-download even if present')
    args = ap.parse_args()
    ROOT.mkdir(parents=True, exist_ok=True)

    failed, manifest, total = 0, [], 0
    for name, item, path, md5, size in PICKS:
        dest = ROOT / name
        if dest.exists() and not args.force and dest.stat().st_size == size and md5sum(dest) == md5:
            print(f'  skip  {name}')
        else:
            url = f'https://archive.org/download/{item}/' + urllib.parse.quote(path)
            data, err = None, None
            for attempt in range(4):              # archive.org drops the odd request
                try:
                    req = urllib.request.Request(url, headers={'User-Agent': 'yorimichi-audio-fetch/1.0'})
                    with urllib.request.urlopen(req, timeout=300) as r:
                        data = r.read()
                    break
                except Exception as e:  # network, 404...
                    err = e
                    time.sleep(2 * (attempt + 1))
            if data is None:
                print(f'  FAIL  {name}: {err}')
                failed += 1
                continue
            if hashlib.md5(data).hexdigest() != md5:
                print(f'  FAIL  {name}: md5 mismatch (archive copy changed?)')
                failed += 1
                continue
            dest.write_bytes(data)
            print(f'  ok    {name}  ({len(data) / 1e6:.1f} MB)')
        total += size
        manifest.append({'file': name, 'source_item': item, 'source_path': path,
                         'md5': md5, 'bytes': size})

    (ROOT / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(f'\ntotal {total / 1e6:.1f} MB in {len(manifest)} files -> {ROOT}')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
