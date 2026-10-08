// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <cstdint>
namespace atelier::skate
{
// The player's skating feel, beside Tune's pop, spin and push. Every field is a multiplier on the authored value of the
// active difficulty (1 is stock) or a switch where -1 keeps the difficulty's own choice. GameplayRuntime::Feel applies it
// to copies of the authored settings, so any change can be undone exactly; at the defaults nothing differs from stock.
struct FeelTuning
{
    // Flick tricks: how far a flick may stray from a trick's shape, how long a flick may take, and how fast a flick must
    // be for full pop (lower is less flick speed needed).
    float flick_radius=1,flick_window=1,flick_pace=1;
    // Air: gravity (below 1 floats, above 1 drops; jump heights stay put, air time changes), boneless and hippy heights.
    float gravity=1,boneless=1,hippy=1;
    // Rails: how far a jump may be bent onto a rail or ledge, the pop off a grind and the grind's friction.
    float rail_magnetism=1,grind_pop=1,grind_friction=1;
    // Rolling: braking, steering, carve strength, wheel grip, powerslide bite, rolling resistance, downhill pull and pumping.
    float braking=1,steering=1,carve=1,grip=1,powerslide=1,rolling_friction=1,hill_speed=1,pump=1;
    // Balance: speed wobble size and the speed at which it starts, manual balance drift.
    float wobble=1,wobble_onset=1,manual_drift=1;
    // Bails: the landing angles and speeds that are forgiven, and the impacts that are survived.
    float landing=1,impact=1;
    // -1 keeps the difficulty's choice; 0 off; 1 on. Auto push keeps rolling speed; assisted air completes body
    // spins and flips for you.
    std::int8_t auto_push=-1,assisted_air=-1;
    // 0 off (stock); 1 on. Tight flicks also read a hardflip or inward heelflip flicked close to straight down then
    // up, as in newer skate games, beside the authored wide arc.
    std::int8_t tight_flicks=0;
};
}
