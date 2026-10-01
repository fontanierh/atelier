// SPDX-License-Identifier: Apache-2.0
#include "SkeletonAirRuntime.h"
#include "StockSettingsReader.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
Mat4 Matrix(AffineTransform t)
{
    Mat4 m{};for(unsigned axis=0;axis<3;++axis)for(unsigned lane=0;lane<3;++lane)m[axis][lane]=t.basis.columns[axis][lane];
    m[3]={t.translation.x,t.translation.y,t.translation.z,0};return m;
}
AffineTransform Affine(Mat4 m)
{
    AffineTransform t;for(unsigned axis=0;axis<3;++axis)for(unsigned lane=0;lane<3;++lane)t.basis.columns[axis][lane]=m[axis][lane];
    t.translation={m[3][0],m[3][1],m[3][2]};return t;
}
}
std::optional<SkeletonAir> SkeletonAir::Load(const SettingsDatabase& data,std::string& error)
{
    SkeletonAir next;StockSettingsReader reader(data);
    if(!reader.Curve8Layout20("physics_airstates","default","PhysToAnimSlow",next.settings.slow,error)
        ||!reader.Curve8Layout20("physics_airstates","default","PhysToAnimFast",next.settings.fast,error))return std::nullopt;
    return next;
}
void SkeletonAir::CapturePhysicsError(const BoardRuntime& board,const Mat4& target)
{board_animation.CapturePhysicsError(target,Matrix(board.PartTransforms()[6]));}
Mat4 SkeletonAir::ApplyBoard(BoardRuntime& board,const Mat4& target,bool fast)
{const auto effective=board_animation.Apply(target,fast,settings);board.SetHookTransform(Affine(effective));return effective;}
bool UpdateAnimatedSkeletonAir(SkeletonInputRuntime& input,SkeletonAir& air,const Mat4& reckoning,
    ProcessedPhysicsInput& p,SkeletonInputOwners owners,const std::vector<Mat4>& globals,
    const SkeletonInputCollision& collision,bool fast,Mat4& target,std::string& error)
{
    auto& physical=owners.physical;const auto velocity=physical.board.Bodies()[6].rates.linear_velocity;
    physical.roots.Update(physical.DeckFrame(),{velocity.x,velocity.y,velocity.z,0},p.timestep_2604,owners.animated.animation_board,reckoning);
    const auto unblended=PrepareAnimatedAirFrames(physical.roots,physical.board_frames,physical.drive_frames[0],p.flags_2468);
    physical.board_frames.physical_board=air.ApplyBoard(physical.board,unblended,fast);
    std::array<Mat4,24> drives;if(!input.GeneralUpdate(p,owners,globals,collision,drives,error))return false;
    owners.animated.FinishGround();owners.animation_input.fields.flags2468=p.flags_2468;target=unblended;return true;
}
bool UpdateKnownSkeletonAir(SkeletonInputRuntime& input,SkeletonAir& air,const Mat4& reckoning,Vec4 target_com,
    const PhysicsPosePacket& packet,ProcessedPhysicsInput& p,SkeletonInputOwners owners,const std::vector<Mat4>& globals,
    const SkeletonInputCollision& collision,Mat4& target,std::string& error)
{
    auto& physical=owners.physical;
    UpdateKnownAirRoots(physical.roots,reckoning,target_com,physical.animation_record.centre_of_mass,
        {(packet.flags&(1u<<28))!=0,static_cast<std::uint32_t>(packet.air_dismount_revert_frames),(p.flags_2476&(1u<<2))!=0});
    const auto unblended=PrepareKnownAirFrames(physical.roots,physical.board_frames,physical.drive_frames[0],p.flags_2468);
    const auto effective=air.ApplyBoard(physical.board,unblended,true);physical.board_frames.physical_board=effective;
    const auto position=physical.board.Bodies()[6].rates.position;const auto velocity=BoardAnimationTargetVelocity(effective[3],{position.x,position.y,position.z,0},p.timestep_2604);
    for(auto& body:physical.board.BodiesMut())body.rates.linear_velocity={velocity[0],velocity[1],velocity[2]};
    FinishKnownAirFrames(physical.roots,physical.board_frames,effective);
    std::array<Mat4,24> drives;if(!input.GeneralUpdate(p,owners,globals,collision,drives,error))return false;
    owners.animation_input.fields.flags2468=p.flags_2468;target=unblended;return true;
}
}
