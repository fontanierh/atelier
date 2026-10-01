// SPDX-License-Identifier: Apache-2.0
#include "BipedFeet.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace {Vec4 FootRawVector(const RawVector& raw){Vec4 v;std::memcpy(v.data(),raw.data(),16);return v;}}
BipedFeetInput MakeBipedFeetInput(const ProcessedPhysicsInput& p,const SkeletonAnimationRecord& record,const SkeletonRootFrames& roots)
{
    BipedFeetInput input;input.root=roots.animation_to_world;input.inverse_root=roots.world_to_animation;input.effective_root=input.root;
    if((p.flags_2476&4)!=0)for(const auto axis:{0u,2u})for(auto& v:input.effective_root[axis])v=-v;
    for(std::size_t index=0;index<2;++index)
    {
        const auto part=index==0?15u:19u;
        for(std::size_t pair=0;pair<2;++pair){input.local_foot_pairs[index][pair]=record.pose[part+pair][3];input.world_foot_pairs[index][pair]=ComposeSkeletonAffine(input.root,record.pose[part+pair])[3];}
        const auto& line=p.line_tests_960_1008_1056[index];input.lines[index]={FootRawVector(line.position),FootRawVector(line.normal),line.surface,line.valid!=0};
    }
    input.position=FootRawVector(p.vectors_544_560_592_608[2]);input.velocity=FootRawVector(p.vectors_544_560_592_608[3]);
    input.flags_2476=p.flags_2476;input.flags_2480=p.flags_2480;input.flags_2484=p.flags_2484;input.state=p.state_2508;return input;
}
void UpdateBipedAirFeet(BoardPossessionManager& manager,const ProcessedPhysicsInput& p,const SkeletonAnimationRecord& record,const SkeletonRootFrames& roots,foot_ik::State& ik)
{
    for(auto& foot:manager.hands)foot.scalars_96_100[1]=0;manager.words_308_to_316={};
    const auto targets=UpdateBipedFeetTargets(manager,MakeBipedFeetInput(p,record,roots));if((p.flags_2484&0x80000000)==0)ApplyBipedFootTargets(targets,ik);
}
void EnterBipedAirFeet(BoardPossessionManager& manager,const ProcessedPhysicsInput& p,foot_ik::State& ik)
{
    if(p.state_2504!=500&&p.state_2504!=501&&p.state_2504!=502)
    {
        manager.Reset();ik.EnableFeet(false);for(auto& limb:ik.limbs){limb.board_blend=0;limb.external_blend=0;limb.mode=foot_ik::Mode::Disabled;}
    }
    manager.flags_304_to_307[0]=p.state_2508==502;
}
void PublishBipedFeet(const BoardPossessionManager& manager,OffBoardOutputFields& output)
{
    for(std::size_t index=0;index<2;++index){const auto& flags=manager.hands[index].flags_104_to_107;output.flags_306_307[index]=std::uint8_t((flags[1]&&!flags[2])||flags[3]);}
}
}
