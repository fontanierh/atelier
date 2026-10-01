// SPDX-License-Identifier: Apache-2.0
#pragma once
namespace atelier::skate
{
struct TrainerTuning
{
    float pop=1,grind_pop=1,push_speed=1,push_power=1,braking=1,steering=1,wobble=1;
    float offboard_jump=1,grip=1,turn_power=1,manual_drag=1;
    bool hold_fakie=false;
};
}
