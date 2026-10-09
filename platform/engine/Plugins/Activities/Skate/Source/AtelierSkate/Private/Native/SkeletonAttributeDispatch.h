#pragma once
#include "AnimationPlayback.h"
#include "Input.h"
namespace atelier::skate
{
struct ScalarAttributeInputs
{
    std::uint32_t flags2468{};
    std::uint32_t flags2472{};
    std::uint32_t flags2476{};
    std::uint32_t flags2484{};
    std::uint32_t flags2488{};
    std::uint32_t board_adjust{};
    float balance{};
    float spin{};
    float body_spin{};
    float brake{};
    float turn{};
    float turn_scale{};
    float magnitude_scale{};
    std::array<float,4> animation_end_com{};
    std::array<float,4> animation_translation{};
    float animation_time{};
    float animation_physics_blend_seconds{};
    float cadence_end_percent{};
    float raw_turn{};
    float hard_turn{};
    float slide{};
    static ScalarAttributeInputs Reset(std::uint32_t previous_flags2468,std::uint32_t previous_flags2488);
};
struct AnimationControlOutput
{
    AttributeName grind_name{};
    std::uint32_t flags{};
};
struct ExtendedAttributes
{
    std::uint32_t flags2480{};
    float grind_translation{};
    float grind_stability_nudge{};
    float grind_up_down{};
    float grind_grab_min_height{};
    float physical_body_spin{};
    float world_grab_y{};
    float world_grab_z{};
    float offboard_turn{};
    float offboard_magnitude{};
    float biped_world_x{};
    float biped_world_z{};
    float look_x{};
    float look_y{};
    float object_move_z{};
    float object_move_x{};
    float object_move_rotation{};
    std::array<float,2> wipeout_control{};
    std::array<float,2> offboard_jump{};
    std::array<float,2> wipeout_gesture{};
    std::array<float,2> body_adjust{};
    float biped_start_angle{};
    float biped_spin_angle{};
    float biped_animation_time{};
    float footstep_strength{};
    float jump_strength{};
    std::array<float,2> jump_controls{};
    float revert_direction{};
    static ExtendedAttributes Reset(float footstep_strength);
};
struct JumpAttributeState
{
    std::array<float,2> prepared_controls{};
    float height_override{};
    bool height_override_active{};
};
struct FinalizationInput
{
    bool select_jump_extremes{};
    float low_jump_threshold{};
    float high_jump_threshold{};
    bool allow_height_override{};
    bool use_prepared_controls{};
    bool external_impulse_active{};
    std::uint32_t animation_flags{};
};
struct ContactEventState
{
    std::int32_t bone{};
    float push_speed{};
};
struct SkeletonAttributeDescriptor {std::string_view name;AttributeName encoded_name;std::uint32_t comparison_site;};
const std::array<SkeletonAttributeDescriptor,151>& SkeletonAttributeCatalog();
const SkeletonAttributeDescriptor* LookupSkeletonAttribute(AttributeName);
struct ContactEventPose
{
    const std::vector<AttributeName>& bone_names;
    const std::vector<Mat4>& hierarchy;
    std::size_t trajectory_bone;
    std::int32_t right_toe_bone;
    float timestep;
};
struct SkeletonScalarDispatchError
{
    enum class Kind {EventConsumerUnavailable,KnownScalarUnavailable,UninitializedScalar} kind;
    AttributeName name{};
    const SkeletonAttributeDescriptor* attribute=nullptr;
};
bool DispatchScalarSkeletonAttribute(const AnimationAttribute&,ScalarAttributeInputs&,AnimationControlOutput&,SkeletonScalarDispatchError&);
bool DispatchContactEvent(const AnimationAttribute&,const ContactEventPose&,ScalarAttributeInputs&,ContactEventState&,std::string& error);
// Order is the completed packet's MG then tree attributes. Errors retain all
// preceding mutations; the unconditional finalizer only runs after dispatch.
bool ProcessSkeletonAttributes(const std::vector<AnimationAttribute>&,const ContactEventPose&,
    ScalarAttributeInputs&,ExtendedAttributes&,ContactEventState&,JumpAttributeState&,
    AnimationControlOutput&,FinalizationInput,ActionMap* input_map,std::string& error);
}
