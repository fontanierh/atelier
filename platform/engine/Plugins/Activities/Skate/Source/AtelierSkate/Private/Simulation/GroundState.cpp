#include "GroundState.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace { float Float(std::uint32_t word) { float value; std::memcpy(&value,&word,4); return value; } }
PhysicsGroundState PhysicsGroundState::BeforeFirstEnter(bool human_player)
{
    PhysicsGroundState state; state.human_player_2724=human_player; return state;
}
void PhysicsGroundState::BeginEntry()
{
    word_2560=0;word_2564=0;flag_2708=false;controls_latched_2725=false;
    captured_position_valid_2726=false;was_pinning_2728=false;flag_2731=false;
    manual_correction_2732=false;manual_opposition_2733=false;
}
void PhysicsGroundState::FinishEntry(std::uint32_t previous_state)
{
    straighten_scale_2672=previous_state==101?Float(0x3e23d70a):1.0f;
    steering_push_scalar_2640=1.0f;steering_damped_turn_2644=0.0f;
    elapsed_2648=0.0f;collision_countdown_2652=0.0f;
    vector_2592={};vector_2608={};anti_flip_torque_2624={};
    hang_detection_frames_2740=0;hang_force_frames_2744=0;
    hung_wipeout_frames_2748=0;anti_flip_nudge_frames_2752=0;
    flag_2721=false;anti_flip_nudge_applied_2723=false;push_suppressed_2730=false;
}
bool PhysicsGroundState::BeginUpdate(std::int32_t wheel_contacts, Vec4 position)
{
    if(!captured_position_valid_2726&&wheel_contacts>0)
    {
        captured_position_x_2656=position[0];captured_position_z_2660=position[2];
        captured_position_valid_2726=true;
    }
    anti_flip_torque_2624={};flag_2722=false;anti_flip_nudge_applied_2723=false;
    pinning_2727=false;scalar_2664=-1.0f;flag_2729=false;
    return elapsed_2648>Float(0x3d4ccccd);
}
void PhysicsGroundState::FinishUpdate(float timestep) { elapsed_2648+=timestep; }
}
