#pragma once
#include "SkeletonRoot.h"
#include <optional>
namespace atelier::skate
{
// One physical Biped controller. Ground and Air borrow this same cadence,
// movement, support and correction history; the graph clock is separate.
struct BipedClipMetric {float translation_z,end_time;};
struct BipedIntentSettings
{
    PointGraph<4> sprint_speed;PointGraph<16> normal_speed;PointGraph<8> sprint_blend;
    float sprint_time_cap;PointGraph<8> slide_steering;
};
struct BipedIntentInput
{
    std::uint32_t flags;bool suppress_minimum;float magnitude,steering;
    bool sprint_pressed,edge_active,ignore_obstacle;
    Vec4 direction,edge_tangent,edge_point,right,up,forward,position;
    bool obstacle;Vec4 obstacle_normal;bool sliding;Vec4 slide_velocity;
};
struct BipedIntentState
{
    float speed=0,steering=0,sprint_time=0,sprint_grace=0,secondary_speed=0,original_steering=0;
    bool obstacle_centered=false,edge_aligned=false;Vec4 edge_target{};
    void Update(const BipedIntentSettings&,const BipedIntentInput&);
};
struct BipedVelocitySettings {PointGraph<8> slope_speed_scalar,slope_mode_speed,turn_vs_speed,turn_delta_vs_speed;};
struct BipedVelocityInput
{
    Vec4 forward,right,plane_normal;float desired_speed,steering;bool slope_mode,obstacle;
    Vec4 obstacle_normal;float override_gate,override_duration;Vec4 override_velocity;std::uint32_t flags;
};
struct BipedVelocityState
{
    Vec4 velocity{};float turn=0,forward_delta=0,right_delta=0,speed=0,override_remaining=-1;
    void Update(const BipedVelocitySettings&,const BipedVelocityInput&);
};
struct BipedContactInput {std::array<Vec4,2> collision_displacements;Vec4 projection_axis_416,up_axis_16;};
struct BipedContactCorrection
{
    bool active=false;Vec4 direction{},displacement{};
    void Update(BipedContactInput);
};
struct BipedSpecialMode
{
    bool enabled_714=false;float elapsed_788=0;
    void Update(float movement,std::uint32_t contact_flags,float forward_y);
};
struct BipedSlidingInput {bool special_mode_714;Vec4 surface_normal_560,movement_velocity_480;std::optional<Vec4> contact_direction_400;};
struct BipedSliding
{
    Vec4 velocity_528{};bool active_710=false;
    void Update(BipedSlidingInput,const PointGraph<8>& slope,const PointGraph<8>& speed);
};
struct BipedSurfaceInput {std::uint32_t flags;Vec4 normal,origin,edge_point,edge_normal;};
struct BipedSpringInput
{
    Vec4 velocity,up,right,forward,spring_right,spring_forward;
    float right_delta,forward_delta;bool suppress_lean;
};
struct BipedSurfaceState
{
    Vec4 surface_normal{0,1,0,0},source_normal{0,1,0,0},spring_normal{0,1,0,0},spring_delta{},final_up{0,1,0,0},lean{};
    void UpdateSurface(const BipedSurfaceInput&);void UpdateSpring(const BipedSpringInput&);
};
struct BipedGroundMotionState
{
    Mat4 frame_0=SkeletonIdentity,published_frame_64=SkeletonIdentity,previous_support_frame_192=SkeletonIdentity;
    Vec4 support_velocity_256{},predicted_support_velocity_272{},previous_support_velocity_288{},support_acceleration_304{},filtered_local_acceleration_320{};
    float support_yaw_336=0,previous_support_yaw_340=0,predicted_support_yaw_344=0,support_speed_348=0;
    std::uint32_t support_id_352=0;Vec4 velocity_480{},correction_576{};Mat4 target_frame_608=SkeletonIdentity;
    float angular_velocity_688=0,speed_704=0;bool correction_enabled_711=false,support_velocity_removed_715=false;float target_scale_784=-1;
};
struct BipedGroundMotionInput
{
    Vec4 contact_position_0;Mat4 contact_frame_32;Vec4 contact_target_96,contact_normal_112;
    std::uint32_t contact_flags_176,contact_id_180;Vec4 animation_motion_224,animation_motion_240;
    float requested_duration_288;bool mirrored_292,animation_directed_304,target_frame_present_352;
    Mat4 target_frame_368,reference_frame_128;Vec4 contact_displacement_384,velocity_addition_528,desired_up_544,correction_target_592,obstacle_target_672;
    bool obstacle_enabled_713;
};
void UpdateBipedGroundMotion(BipedGroundMotionState&,const BipedGroundMotionInput&);
struct BipedFrameOutput
{
    Mat4 frame=SkeletonIdentity;Vec4 velocity{};
    void Update(Vec4 forward,Vec4 up,Vec4 projection,Vec4 position);
};
struct BipedPositionInput
{
    Vec4 previous_origin_112,override_origin_592;bool use_override_711;Vec4 projection_axis_416;
    std::uint32_t contact_flags_176;Vec4 contact_origin_0,contact_origin_96,frame_position_176,animation_position_272;
};
void UpdateBipedPosition(Vec4&,BipedPositionInput);
struct BipedPhase
{
    float phase=0,rate=0,target=-1;std::optional<float> duration;bool forward_target=false;
    void Request(float target,float duration);void Stop();void Advance();
    void AdjustTargets(float a,float b,float time,float upper);void AdjustContact(float time,float lower,float upper);
};
using BipedVector3=std::array<float,3>;
struct BipedCadenceInput
{
    BipedVector3 motion_512,motion_reference_272,reject_axis_400;bool reject_enabled_708;BipedVector3 up_144;
    std::array<BipedVector3,3> frame_rows_0_16_32;BipedVector3 frame_position_48,animation_motion_224;
    float requested_duration_288,requested_phase_296;bool suppress_adjustment_353;
    std::uint32_t contact_flags_176;BipedVector3 contact_point_96;
};
struct BipedCadence
{
    BipedPhase phase;std::uint32_t locomotion_index=0;
    void Update(const BipedCadenceInput&,std::array<float,4> thresholds);
};
struct BipedControllerSettings
{
    BipedIntentSettings movement_intent;BipedVelocitySettings movement_velocity;
    PointGraph<8> slide_vs_slope,slide_vs_speed;
};
struct BipedGroundJob
{
    Vec4 contact_position,contact_normal;Mat4 support_frame;Vec4 target_position,target_normal,edge_position,edge_normal;
    std::uint32_t flags,support_id;std::array<Vec4,2> collision_displacements;
    Vec4 animation_motion,animation_velocity,desired_direction,animation_position;
    float requested_duration;bool mirrored;float requested_phase,override_duration;
    bool animation_directed;float movement,steering;bool sprint_pressed,suppress_lean,suppress_minimum,target_frame_present,edge_active;
    Mat4 target_frame;bool ignore_obstacle;
};
struct BipedPlacementInput {Mat4 frame;Vec4 velocity,body_position;std::uint32_t current_state,previous_state;Mat4 previous_frame;};
struct BipedGroundResult
{
    Mat4 physical_frame,animation_frame,surface_frame;Vec4 velocity,position;
    float angular_velocity;bool alternate,sliding;
};
struct BipedControllerState
{
    BipedGroundMotionState motion;BipedIntentState intent;BipedSurfaceState surface;
    BipedContactCorrection contact;BipedSpecialMode special;BipedSliding sliding;BipedFrameOutput frame_output;
    BipedCadence cadence;std::array<float,4> thresholds{};Vec4 position_368{},correction_target_592{};
    float forward_delta_692=0,right_delta_696=0,velocity_override_remaining_772=-1;bool alternate_709=false;
    explicit BipedControllerState(std::array<std::optional<BipedClipMetric>,3> metrics);
    void Reset();void Place(BipedPlacementInput);
};
class OffboardController
{
public:
    BipedControllerState state;BipedControllerSettings settings;
    OffboardController(BipedControllerSettings s,std::array<std::optional<BipedClipMetric>,3> metrics):state(metrics),settings(std::move(s)){}
    void Reset(){state.Reset();}void Place(BipedPlacementInput input){state.Place(input);}
    BipedGroundResult StepGround(const BipedGroundJob&);BipedGroundResult Output() const;
};
Mat4 BipedBuildSurfaceFrame(Vec4 up,Vec4 forward);
}
