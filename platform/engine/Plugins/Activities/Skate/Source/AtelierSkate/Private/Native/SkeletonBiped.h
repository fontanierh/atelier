#pragma once
#include "SkeletonAirRuntime.h"
#include "AirReckoning.h"
namespace atelier::skate
{
struct BipedReckoningUpdate {Vec4 up,forward;float blend;};
struct BipedReckoningInput
{
    Vec4 previous_up,requested_up,requested_forward;
    float blend;
    bool reverse_stance,enable_body_spin_input;
    float physical_body_spin_2812;
};
struct BipedReckoningOutput {Vec4 dynamic_up_1136,up_1152,target_1168,velocity_1184,ground_normal_1216;};
struct BipedSkeletonState
{
    // Source Skeleton16016 retains animation space independently of12496.
    Mat4 retained_board=SkeletonIdentity;
    Vec4 ground_normal_smoothing{};
    PointGraph<8> tilt_vs_rotation,tilt_vs_slope;
    bool Load(const SettingsDatabase&,std::string& error);
};
BipedReckoningOutput UpdateBipedReckoning(GroundOrientation&,ReckoningFrames&,PhysicalBodySpinState&,AirReckoningState&,
    const BipedSkeletonState&,const BipedReckoningInput&);
BipedReckoningOutput FinishBipedReckoning(const BipedSkeletonState&,BipedReckoningUpdate,PhysicalRidingOutputs&,AirReckoning&,const ProcessedPhysicsInput&,float physical_body_spin);
struct BipedSkeletonGroundInput {const Mat4& world_frame;Vec4 centre_of_mass_1056;};
struct BipedSkeletonAirInput {Mat4 frame_208;Vec4 trajectory_position_272,body_target_416;float lift_436;Vec4 board_forward_96;};
Mat4 PrepareBipedSkeletonGroundFrames(SkeletonRootFrames&,SkeletonBoardFrames&,const Mat4& animation_board,
    const Mat4& mapped_board,BipedSkeletonState&,BipedSkeletonGroundInput,std::uint32_t flags_2476,std::uint32_t flags_2484,std::uint32_t& flags_2468);
Mat4 PrepareBipedSkeletonAirRoot(SkeletonRootFrames&,Mat4 frame,Vec4 trajectory_position,Vec4 local_com,const Mat4& mapped_board,std::uint32_t flags_2476,std::uint32_t& flags_2468);
bool UpdateBipedSkeletonGround(SkeletonInputRuntime&,SkeletonAir&,BipedSkeletonGroundInput,BipedSkeletonState&,
    ProcessedPhysicsInput&,SkeletonInputOwners,const std::vector<Mat4>& actual_globals,const SkeletonInputCollision&,
    AirReckoning&,Mat4& target,std::string& error);
bool UpdateBipedSkeletonAir(SkeletonInputRuntime&,SkeletonAir&,BipedSkeletonAirInput,const BipedSkeletonState&,
    ProcessedPhysicsInput&,SkeletonInputOwners,const std::vector<Mat4>& actual_globals,const SkeletonInputCollision&,
    AirReckoning&,Mat4& target,std::string& error);
}
