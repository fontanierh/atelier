#pragma once
#include "NativeMath.h"
namespace atelier::skate
{
struct PhysicsGroundState
{
    Vec4 collision_force_2528{}, collision_point_2544{};
    std::uint32_t word_2560=0, word_2564=0;
    Vec4 vector_2592{}, vector_2608{}, anti_flip_torque_2624{};
    float steering_push_scalar_2640=0, steering_damped_turn_2644=0;
    float elapsed_2648=0, collision_countdown_2652=0;
    float captured_position_x_2656=0, captured_position_z_2660=0;
    float scalar_2664=0, scalar_2668=0, straighten_scale_2672=0;
    Vec4 vector_2688{};
    float scalar_2704=0;
    bool flag_2708=false, flag_2720=false, flag_2721=false, flag_2722=false;
    bool anti_flip_nudge_applied_2723=false, human_player_2724=false;
    bool controls_latched_2725=false, captured_position_valid_2726=false;
    bool pinning_2727=false, was_pinning_2728=false, flag_2729=false;
    bool push_suppressed_2730=false, flag_2731=false;
    bool manual_correction_2732=false, manual_opposition_2733=false;
    std::int32_t hang_detection_frames_2740=0, hang_force_frames_2744=0;
    std::int32_t hung_wipeout_frames_2748=0, anti_flip_nudge_frames_2752=0;
    static PhysicsGroundState BeforeFirstEnter(bool human_player);
    void BeginEntry();
    void FinishEntry(std::uint32_t previous_state);
    // Returns the original skeleton-flag signal; the physical owner publishes it.
    bool BeginUpdate(std::int32_t wheel_contacts, Vec4 position);
    void FinishUpdate(float processed_timestep);
};
}
