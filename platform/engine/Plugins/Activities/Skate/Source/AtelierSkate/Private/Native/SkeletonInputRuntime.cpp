// SPDX-License-Identifier: Apache-2.0
#include "SkeletonInputRuntime.h"
#include "OffboardPoseAdjustment.h"
#include "GrindAirPoseAdjustment.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
Vec4 Decode(const RawVector& words)
{Vec4 result;for(unsigned i=0;i<4;++i)std::memcpy(&result[i],&words[i],4);return result;}
RawVector Encode(Vec4 value)
{RawVector result;for(unsigned i=0;i<4;++i)std::memcpy(&result[i],&value[i],4);return result;}
void PublishAttributeFlags(const PhysicsAnimationInput& input,ProcessedPhysicsInput& p)
{
    p.flags_2468=input.fields.flags2468;p.flags_2472=input.fields.flags2472;
    p.flags_2476=input.fields.flags2476;p.flags_2480=input.extra.flags2480;
    p.flags_2484=input.fields.flags2484;p.flags_2488=input.fields.flags2488;
}
void RestoreBoardTargetDrives(SkeletonDrives& drives)
{
    const std::uint32_t spring_bits=0x4415ffff,strength_bits=0x470c9fff;float spring,strength;
    std::memcpy(&spring,&spring_bits,4);std::memcpy(&strength,&strength_bits,4);
    const DriveParams hard{spring,0,strength,DriveType::Hard};
    drives.targets.dynamics[0].linear=hard;drives.targets.dynamics[0].angular=hard;
}
}
std::optional<SkeletonInputRuntime> SkeletonInputRuntime::Load(const SettingsDatabase& data,std::string& error)
{
    auto settings=GrindAirSettings::Load(data,error);if(!settings)return std::nullopt;
    SkeletonInputRuntime result;result.grind_air_settings_=std::move(*settings);return result;
}
bool SkeletonInputRuntime::ProcessData(const BoardToolkit& toolkit,const AnimationInputPacket& packet,
    PhysicalPlayerInput&,ProcessedPhysicsInput& p,SkeletonInputOwners owners,SkeletonInputPose pose,
    const SkeletonInputCollision& collision,std::string& error)
{
    auto& physical=owners.physical;auto& animated=owners.animated;auto& input=owners.animation_input;
    const auto velocity=physical.board.Bodies()[6].rates.linear_velocity;
    physical.deck_velocity={velocity.x,velocity.y,velocity.z,0};
    for(auto& body:physical.skeleton.BodiesMut())
    {if((body.state_flags&7)==2)body.state_flags=(body.state_flags&8)|4;body.rates.cool_down=0;}
    input.ResetProcessed();
    input.fields.flags2468=p.flags_2468;input.fields.flags2472=p.flags_2472;
    input.fields.flags2476=p.flags_2476;input.fields.flags2484=p.flags_2484;
    input.fields.flags2488=p.flags_2488;input.extra.flags2480=p.flags_2480;
    if(!input.Process(pose.attributes,pose.globals,packet.publication.timestep,packet.flags_10932,
        packet.publication.flags_10375_10496_10784[1]!=0,pose.actions,error))return false;
    PublishAttributeFlags(input,p);p.spin_input_2672=input.fields.spin;
    if(!UpdateOffboardPoseAdjustment(animated,pose.globals,animated.ReparentedHandIndices(),p,error))return false;
    if((p.flags_2476&0x100)==0)
    {
        grind_air_adjusting=false;
        if(grind_air_active)
        {
            if(!grind_air_settings_){error="GrindAirAdjust stock settings were not loaded";return false;}
            if(!UpdateGrindAirPoseAdjustment(grind_air,*grind_air_settings_,toolkit.deck,p,animated,
                owners.AnimationOwners(),pose.globals,grind_air_adjusting,error))return false;
        }
    }
    const auto up=Decode(p.vectors_544_560_592_608[0]),com_velocity=Decode(p.vectors_544_560_592_608[3]);
    Vec4 com_delta;for(unsigned i=0;i<4;++i)com_delta[i]=physical.skeleton.record.centre_of_mass[i]-physical.skeleton.record.positions[0][i];
    const LandingInput landing_input{p.filtered_state_2524,p.flags_2468,p.flags_2472,p.flags_2476,
        input.fields.balance,Dot3(com_velocity,up),Dot3(com_delta,up),physical.animation_record.centre_of_mass[1]};
    std::optional<LandingOnBoardPoseInput> on_board;
    if((p.flags_2476&0x10100)==0x100)on_board=LandingOnBoardPoseInput{toolkit.deck,
        Decode(p.vectors_720_784_800_816_832_864[5]),p.flags_2480,p.off_board_scalar_2832};
    if(!animated.ProcessPose(owners.AnimationOwners(),pose.globals,landing_input,packet.publication.timestep,
        p.flags_2468,p.flags_2472,on_board,error))return false;
    physical.drive_frames=physical.animation_record.pose;p.board_at_y_delta_2768=animated.board_at_y_delta;
    p.flags_2472=(p.flags_2472&~(1u<<17))|(std::uint32_t(collision.contact_4070)<<17);
    if(collision.has_pose_error_4077)p.collision_pose_error_736=Encode(collision.pose_error_16272);
    p.animation_com_to_deck_752=Encode(physical.animation_record.com_to_deck_world);
    p.animation_com_to_deck_delta_768=Encode(physical.animation_record.com_to_deck_world_delta);
    input.fields.flags2468=p.flags_2468;input.fields.flags2472=p.flags_2472;
    if(reenable_requested)
    {reenable_requested=false;owners.ik.EnableFeet(true);RestoreBoardTargetDrives(physical.skeleton_drives);physical.roots.supplied_prediction.reset();}
    return true;
}
bool SkeletonInputRuntime::GeneralUpdate(const ProcessedPhysicsInput& p,SkeletonInputOwners owners,
    const std::vector<Mat4>& globals,const SkeletonInputCollision& collision,std::array<Mat4,24>& actual_drives,std::string& error)
{
    auto& physical=owners.physical;physical.UpdateRootDerivative(p.timestep_2604);
    const auto target=physical.UpdateTargetPositions(owners.animated.animation_hips,owners.animated.animation_board,teleporting);
    if(!target.continuous)
    {physical.ResetPhysicalPose();if(p.state_2508!=0&&p.state_2508!=702)physical.invalid_target_reset=true;}
    const auto hips=physical.skeleton.PartTransforms()[23][3];
    if(!owners.ik.Update(owners.animated,owners.AnimationOwners(),globals,p,
        static_cast<std::size_t>(owners.animation_input.contacts.bone),physical.board_frames.physical_board,
        hips,actual_drives,error))return false;
    physical.drive_frames=actual_drives;
    physical.skeleton_drives.Update(actual_drives,collision.partial_ragdoll,collision.drive_weight_4028);
    physical.ApplySkeletonGravity(p.gravity_2648);return true;
}
bool SkeletonInputRuntime::UpdateGround(const Mat4& reckoning,ProcessedPhysicsInput& p,SkeletonInputOwners owners,
    const std::vector<Mat4>& globals,const SkeletonInputCollision& collision,Mat4& frame,std::string& error)
{
    auto& physical=owners.physical;physical.roots.initialize_heading=true;
    const auto velocity=physical.board.Bodies()[6].rates.linear_velocity;
    physical.roots.Update(physical.DeckFrame(),{velocity.x,velocity.y,velocity.z,0},p.timestep_2604,
        owners.animated.animation_board,reckoning);
    frame=physical.board_frames.PrepareGround(physical.roots,physical.animation_record.pose[0],
        physical.roots.board,p.flags_2468);
    std::array<Mat4,24> actual_drives;
    if(!GeneralUpdate(p,owners,globals,collision,actual_drives,error))return false;
    owners.animated.FinishGround();owners.animation_input.fields.flags2468=p.flags_2468;return true;
}
void SkeletonInputRuntime::ResetForTeleport(SkeletonInputOwners owners,SkeletonWobble& wobble,bool& ground_elapsed_16505)
{
    owners.animated.motion.ResetBoardOrientationHistory();reenable_requested=true;
    owners.physical.invalid_target_reset=false;ground_elapsed_16505=true;
    owners.physical.skeleton_collision.ResetBodyState(owners.physical.collision_feedback);
    force_mode=0;head_tracking_history={};head_tracking_active=false;owners.ik.state.Reset();
    wobble.ResetForTeleport();owners.physical.board_frames.animation_target=SkeletonIdentity;
    owners.animated.board_offset={};owners.physical.board_frames.lift_height=0;
}
bool SkeletonInputRuntime::UpdateTeleport(const Mat4& reckoning,ProcessedPhysicsInput& p,SkeletonInputOwners owners,
    const std::vector<Mat4>& globals,const SkeletonInputCollision& collision,Mat4& frame,std::string& error)
{
    teleporting=true;auto& physical=owners.physical;const auto deck=physical.DeckFrame();
    physical.roots.UpdateTeleport(deck,owners.animated.animation_board,reckoning);
    frame=physical.board_frames.PrepareTeleport(physical.roots,physical.drive_frames[0],deck,p.flags_2468);
    std::array<Mat4,24> actual_drives;const bool ok=GeneralUpdate(p,owners,globals,collision,actual_drives,error);
    teleporting=false;if(!ok)return false;
    owners.animated.FinishGround();owners.animation_input.fields.flags2468=p.flags_2468;return true;
}
}
