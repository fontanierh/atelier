#pragma once
#include "BoardPossessionManager.h"
#include "FootIkTypes.h"
#include "PlayerInputTypes.h"
#include "SkeletonAnimationRecord.h"
#include "SkeletonRoot.h"
namespace atelier::skate
{
struct BipedFootLine {Vec4 position{},normal{};std::uint32_t surface=0;bool valid=false;};
struct BipedFeetInput
{
    std::array<BipedFootLine,2> lines;
    std::array<std::array<Vec4,2>,2> local_foot_pairs{},world_foot_pairs{};
    Mat4 root=SkeletonIdentity,inverse_root=SkeletonIdentity,effective_root=SkeletonIdentity;
    Vec4 position{},velocity{};
    std::uint32_t flags_2476=0,flags_2480=0,flags_2484=0,state=0;
};
struct BipedFootTarget {Vec4 position{};bool world=false;float blend=0;std::optional<Vec4> normal;};
std::array<BipedFootTarget,2> UpdateBipedFeetTargets(BoardPossessionManager&,const BipedFeetInput&);
void SetBipedFootNormal(foot_ik::ExternalTarget&,Vec4);
void ApplyBipedFootTargets(const std::array<BipedFootTarget,2>&,foot_ik::State&);
void UpdateBipedGroundFeet(BoardPossessionManager&,BipedFeetInput,foot_ik::State&);
BipedFeetInput MakeBipedFeetInput(const ProcessedPhysicsInput&,const SkeletonAnimationRecord&,const SkeletonRootFrames&);
void UpdateBipedAirFeet(BoardPossessionManager&,const ProcessedPhysicsInput&,const SkeletonAnimationRecord&,const SkeletonRootFrames&,foot_ik::State&);
void EnterBipedAirFeet(BoardPossessionManager&,const ProcessedPhysicsInput&,foot_ik::State&);
void PublishBipedFeet(const BoardPossessionManager&,OffBoardOutputFields&);
}
