// SPDX-License-Identifier: Apache-2.0
#include "LandingDeckMath.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
std::optional<AirTrajectoryQueryRequest> LandingDeckManager::Assist(const LandingDeckAssistInput& input,LandingDeckSettings settings)
{
    using namespace landing_deck_math;completed_queries_252=0;tested_259=false;const auto& p=input.processed;
    if((force_257||(p.flags_2480&0x8000)==0)&&p.board_up_80[1]>settings.deck_min_uprightness)
    {
        ConsiderBoard(p,settings,input.position,input.velocity);
        if(time_to_land_244>.4f){const auto error=Length(Sub(input.velocity,proposed_96.velocity));trajectory_32=proposed_96;trajectory_valid_164=true;time_to_land_244=proposed_time_248;can_land_256=error<input.maximum_velocity_change;}
        if(can_land_256&&!tested_259){tested_259=true;return PrepareQuery(p,input.position,proposed_time_248);}
    }
    return std::nullopt;
}
LandingDeckUpdateOutput LandingDeckManager::Update(const LandingDeckInput& p,LandingDeckSettings settings)
{
    using namespace landing_deck_math;publish_moving_contact_261=false;elapsed_160+=Step();
    if(hippy_hurdling_260){const auto past=elapsed_160-AirTrajectoryHighestPosition(trajectory_32).second;if(past>.3f||(past>0&&time_to_land_244<.2f))hippy_hurdling_260=false;}
    const auto position=AirTrajectoryPositionAt(trajectory_32,elapsed_160),velocity=AirTrajectoryVelocityAt(trajectory_32,elapsed_160);
    can_land_256=p.mode_2540!=6&&p.mode_2540!=9&&p.mode_2540!=12;ConsiderBoard(p,settings,position,velocity);
    std::optional<AirTrajectoryQueryRequest> query;if(!pending_262&&!tested_259&&can_land_256)query=PrepareQuery(p,position,time_to_land_244);
    const auto maximum=p.support_1776<0?.55f:.5f;can_land_256=Length(ik_offset_176)<maximum&&(force_257||(p.flags_2480&0x8000)==0)&&p.board_up_80[1]>settings.deck_min_uprightness;
    const auto landing_time=time_to_land_244+elapsed_160;const auto landing_velocity=AirTrajectoryVelocityAt(trajectory_32,landing_time);const auto apex=AirTrajectoryHighestPosition(trajectory_32);
    return {can_land_256&&!blocked_258,trajectory_valid_164,time_to_land_244,elapsed_160,landing_time,apex.second,position,landing_velocity,trajectory_32.position,AirTrajectoryPositionAt(trajectory_32,landing_time),Up,apex.first,UnitOr(landing_velocity,Up),Up,query};
}
Vec4 LandingDeckManager::CalculateAccurateIkOffset(const LandingDeckIkInput& input)
{
    using namespace landing_deck_math;const auto& p=input.processed;const auto trajectory_time=elapsed_160+input.time_to_land,deck_time=input.time_to_land+Step();
    const auto local=Sub(input.mapped_position_12608,input.animation_com_10960);const auto& root=input.animation_root;
    const auto offset=Madd(root[2],local[2],Madd(root[1],local[1],Mul(root[0],local[0]))),tangent=Sub(p.board_velocity_400,Mul(p.up_544,Dot(p.up_544,p.board_velocity_400)));
    ik_offset_176=Sub(Madd(tangent,deck_time,p.board_position_112),Add(AirTrajectoryPositionAt(trajectory_32,trajectory_time),offset));ik_offset_176[1]=0;return ik_offset_176;
}
}
