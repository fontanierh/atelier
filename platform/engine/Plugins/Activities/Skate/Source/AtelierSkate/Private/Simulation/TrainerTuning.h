#pragma once
namespace atelier::skate
{
struct TrainerTuning
{
    float pop=1,grind_pop=1,push_speed=1,push_power=1,braking=1,steering=1,wobble=1;
    float offboard_jump=1,grip=1,turn_power=1,manual_drag=1;
    bool hold_fakie=false;
    // The player's feel (FeelTuning) that the ground and grind owners read each tick: rolling resistance, downhill
    // pull, the speed at which wobble starts, manual balance noise and grind friction.
    float rolling_friction=1,hill_speed=1,wobble_onset=1,manual_drift=1,grind_friction=1,hippy=1;
};
}
