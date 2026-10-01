// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "OffboardController.h"
#include "OffboardGroundGeometry.h"
#include "OffboardContactToolkit.h"
namespace atelier::skate
{
struct BipedGroundEntryInput
{
    Mat4 animation_frame;
    Vec4 processed_velocity_608;
    std::uint32_t processed_flags_2484,processed_flags_2476;
    float requested_angle_2936,requested_duration_2896;
    std::uint32_t previous_state_2504;
    Vec4 previous_frame_up_208,body_position_15872;
};
struct BipedGroundPlacement {Mat4 frame;Vec4 planar_velocity,body_position;};
struct BipedGroundState
{
    Mat4 frame_80=SkeletonIdentity;
    std::array<bool,7> flags_144_to_150{};
    std::uint32_t counter_152=0,counter_156=0;
    float elapsed_160=0,distance_164=1.0e10f,elapsed_168=0,angle_172=0,angular_velocity_176=0,duration_180=0;
    BipedGroundPlacement Enter(const BipedGroundEntryInput&);
};
Mat4 EffectiveBipedRoot(Mat4,std::uint32_t flags_2476);
struct BipedGroundControlInput
{
    std::uint32_t processed_flags_2472;
    float processed_direct_2684,processed_direct_2680,processed_stick_2692,processed_stick_2688;
    float processed_scale_2912,processed_scale_2908;
    std::array<float,3> frame_forward_112;
};
struct BipedGroundControlOutput {float state_708,state_712;Vec4 state_656;};
BipedGroundControlOutput CalculateBipedGroundInput(const BipedGroundControlInput&,const PointGraph<8>& movement,const PointGraph<8>& turn);
struct BipedGroundContactSnapshot {std::int32_t readiness;OffboardContactPrefix prefix;};
struct BipedGroundPrepareInput
{
    BipedGroundContactSnapshot contact;
    Mat4 frame;
    std::uint32_t previous_state;
    std::optional<Vec4> third_line_position;
    std::uint32_t frames_since_teleport;
    Vec4 processed_position,processed_velocity;
    BipedGroundControlOutput controls;
    std::array<Vec4,2> collision_displacements;
    Vec4 animation_motion,animation_velocity;
    float requested_duration,requested_phase,override_duration;
    std::uint32_t flags_2472,flags_2476,flags_2480,flags_2484,flags_2488;
};
struct BipedGroundPrepared {BipedGroundJob job;OffboardGroundAdjustment geometry;};
// The active host supplies the canonical geometry owner's Consume operation,
// whose fixed seven-line result has no additional failure domain.
BipedGroundPrepared PrepareBipedGroundJob(OffboardContactPrefix&,float& timer_164,const BipedGroundPrepareInput&,OffboardGroundGeometry&);
Mat4 SyncBipedGroundFrames(BipedGroundState&,OffboardContactPrefix,BipedGroundResult);
}
