// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "BoardAnimation.h"
#include "SkeletonAirFrames.h"
#include "SkeletonInputRuntime.h"
#include "AnimationPublication.h"
namespace atelier::skate
{
class SkeletonAir
{
public:
    BoardAnimation board_animation;
    BoardAnimationSettings settings;
    static std::optional<SkeletonAir> Load(const SettingsDatabase&,std::string& error);
    void CapturePhysicsError(const BoardRuntime&,const Mat4& animated_target);
    void ResetBoard(){board_animation.Reset();}
    Mat4 ApplyBoard(BoardRuntime&,const Mat4& target,bool fast);
};
bool UpdateAnimatedSkeletonAir(SkeletonInputRuntime&,SkeletonAir&,const Mat4& reckoning,
    ProcessedPhysicsInput&,SkeletonInputOwners,const std::vector<Mat4>& globals,const SkeletonInputCollision&,
    bool fast_blend,Mat4& target,std::string& error);
bool UpdateKnownSkeletonAir(SkeletonInputRuntime&,SkeletonAir&,const Mat4& reckoning,Vec4 target_com,
    const PhysicsPosePacket&,ProcessedPhysicsInput&,SkeletonInputOwners,const std::vector<Mat4>& globals,
    const SkeletonInputCollision&,Mat4& target,std::string& error);
}
