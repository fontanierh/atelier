#!/usr/bin/env python3
"""Pull the selected Sonniss GDC footstep masters from the archive.org mirrors.

These are the raw library files (96/192 kHz, 24-bit, long performances) and are
kept outside the repository (~/.cache/atelier/sonniss): run this (or `atelier fetch yorimichi`), then
slice.py builds the game-ready one-shots in build/yorimichi/audio/footsteps/.

All files are from the Sonniss GDC Game Audio Bundles: royalty-free, commercial
use, no attribution required. See audio/footsteps/README.md.
"""
import os, sys, urllib.parse, urllib.request, json
from pathlib import Path

import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
from atelier.paths import cache_dir  # noqa: E402
ROOT = str(cache_dir("sonniss", "footsteps"))  # outside the repository: the licence forbids redistributing them

# (surface folder, archive item, path inside item, local name)
PICKS = [
 # --- dirt / gravel path ---
 ("dirt_gravel","sonniss-gdc-2019-game-audio-bundle-normalized","PMSFX - STEPS Dirt & Gravel/PM_SDNG_Single_Step_Footstep_19.wav","pmsfx_dirtgravel_single_19.wav"),
 ("dirt_gravel","sonniss-gdc-2019-game-audio-bundle-normalized","PMSFX - STEPS Dirt & Gravel/PM_SDNG_Single_Step_Footstep_46.wav","pmsfx_dirtgravel_single_46.wav"),
 ("dirt_gravel","sonniss-gdc-2019-game-audio-bundle-normalized","PMSFX - STEPS Dirt & Gravel/PM_SDNG_Stereo_Walk_Seamless_Loop_1.wav","pmsfx_dirtgravel_walk_seamless_loop.wav"),
 ("dirt_gravel","sonniss-gdc-2019-game-audio-bundle-normalized","Studio 23 - Ultimate Footstep Collection/S23_SFX_Footsteps_Gravel_Loafers_Loops_Walk_Normal.wav","s23_gravel_loafers_walk_loop.wav"),
 ("dirt_gravel","sonniss-gdc-2016-game-audio-bundle-normalized","Levan Nadashvili - Civilian Footsteps/FS Ground Civilian Walk N03.wav","levan_ground_walk_03.wav"),
 ("dirt_gravel","sonniss-gdc-2016-game-audio-bundle-normalized","Levan Nadashvili - Civilian Footsteps/FS Ground Civilian Walk N05.wav","levan_ground_walk_05.wav"),
 # --- grass / meadow ---
 ("grass","sonniss-gdc-2020-game-audio-bundle-normalized","PMSFX - STEPS Dry Grass & Shrubs/PM_SDGS_14 Footstep Step Dry Grass Shrubs Pine Needles Meadow .wav","pmsfx_drygrass_single_14.wav"),
 ("grass","sonniss-gdc-2020-game-audio-bundle-normalized","PMSFX - STEPS Dry Grass & Shrubs/PM_SDGS_113 Footstep Step Dry Grass Shrubs Pine Needles Meadow .wav","pmsfx_drygrass_single_113.wav"),
 ("grass","sonniss-gdc-2020-game-audio-bundle-normalized","PMSFX - STEPS Dry Grass & Shrubs/PM_SDGS_186 Footstep Step Dry Grass Shrubs Pine Needles Meadow .wav","pmsfx_drygrass_single_186.wav"),
 ("grass","sonniss-gdc-2020-game-audio-bundle-normalized","PMSFX - STEPS Dry Grass & Shrubs/PM_SDGS_213 Footstep Step Dry Grass Skid Drag.wav","pmsfx_drygrass_skid_drag.wav"),
 ("grass","sonniss-gdc-2023-game-audio-bundle-normalized","RYK-Sounds - Footstep/grass 3 single step 3.wav","ryk_grass_single_03.wav"),
 ("grass","sonniss-gdc-2017-game-audio-bundle-normalized","Tovusound - Edward – Foleyart Collection Add-On Extended Footsteps/169_Foley_Footsteps_Grass_Sneaker_Walk_Fast_Run_Jog_Close.wav","tovusound_grass_walk_run_jog.wav"),
 # --- forest floor / leaves ---
 ("leaves","sonniss-gdc-2018-game-audio-bundle-normalized","Sounds Visual - Footsteps on Leaves/FX3280 Walking Faster Leaves Foley Foosteps.wav","sv_leaves_walk_fast.wav"),
 ("leaves","sonniss-gdc-2018-game-audio-bundle-normalized","Sounds Visual - Footsteps on Leaves/FX3282 Running Leaves Foley Foosteps.wav","sv_leaves_run.wav"),
 ("leaves","sonniss-gdc-2018-game-audio-bundle-normalized","Sounds Visual - Footsteps on Leaves/FX3300 Slow Shuffling 2 Leaves Foley Footsteps.wav","sv_leaves_shuffle_slow.wav"),
 # --- wood: engawa, temple steps, boardwalk ---
 ("wood","sonniss-gdc-2023-game-audio-bundle-normalized","RYK-Sounds - Footstep/wooden floor 1 loop.wav","ryk_woodfloor_walk_loop.wav"),
 ("wood","sonniss-gdc-2018-game-audio-bundle-normalized","The Sound Pack Tree - Footstep Loops/1879 - Footsteps - Wooden Stairs - Down - 80 fpm - Loop.wav","spt_wood_stairs_down_80fpm_loop.wav"),
 ("wood","sonniss-gdc-2018-game-audio-bundle-normalized","The Sound Pack Tree - Footstep Loops/1707 - Footsteps - Flip-Flops - 140 fpm - Loop.wav","spt_flipflops_140fpm_loop.wav"),
 ("wood","sonniss-gdc-2016-game-audio-bundle-normalized","Levan Nadashvili - Civilian Footsteps/FS Wood Civilian Crouch N03.wav","levan_wood_crouch_03.wav"),
 ("wood","sonniss-gdc-2016-game-audio-bundle-normalized","Levan Nadashvili - Civilian Footsteps/FS Wood Civilian Crouch N05.wav","levan_wood_crouch_05.wav"),
 # --- barefoot indoors (tatami stand-in) ---
 ("barefoot","sonniss-gdc-2018-game-audio-bundle-normalized","Joshua Reinhardt - Ultimate Bare Feet Expansion/Bare_Feet_HW4_MED_WALK.L.wav","jr_barefoot_hardwood_walk_L.wav"),
 # --- stone / rock, and landings ---
 ("stone","sonniss-gdc-2017-game-audio-bundle-normalized","Tovusound - Edward – Foleyart Collection Add-On Extended Footsteps/289_Foley_Footsteps_Rocks_Sneaker_Jump_Land_On_Two_Feet_Close.wav","tovusound_rocks_jump_land.wav"),
 # --- mud / shallow water ---
 ("mud_water","sonniss-gdc-2023-game-audio-bundle-normalized","RYK-Sounds - Footstep/mud 1 loop.wav","ryk_mud_walk_loop.wav"),
 ("mud_water","sonniss-gdc-2020-game-audio-bundle-normalized","Wav Junction Sound Effects - Footsteps/0014_Footsteps_water_puddle_single_splashes.wav","wavjunction_puddle_splashes.wav"),
]

total = 0
manifest = []
for surface, item, path, name in PICKS:
    dest_dir = os.path.join(ROOT, surface)
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, name)
    url = f"https://archive.org/download/{item}/" + urllib.parse.quote(path)
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        print(f"  skip  {surface}/{name}")
    else:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "yorimichi-audio-fetch/1.0"})
            with urllib.request.urlopen(req, timeout=180) as r, open(dest, "wb") as out:
                data = r.read()
                out.write(data)
            print(f"  ok    {surface}/{name}  ({len(data)/1e6:.1f} MB)")
        except Exception as e:
            print(f"  FAIL  {surface}/{name}: {e}")
            continue
    total += os.path.getsize(dest)
    manifest.append({"surface": surface, "file": f"{surface}/{name}",
                     "source_bundle": item, "source_path": path,
                     "bytes": os.path.getsize(dest)})

json.dump(manifest, open(os.path.join(ROOT, "manifest.json"), "w"), indent=2)
print(f"\ntotal {total/1e6:.1f} MB in {len(manifest)} files -> {ROOT}")
