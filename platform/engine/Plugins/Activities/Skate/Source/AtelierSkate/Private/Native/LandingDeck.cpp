// SPDX-License-Identifier: Apache-2.0
#include "LandingDeck.h"
#include "GravityScale.h"
#include "LandingDeckMath.h"
#include "StockSettingsReader.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
void LandingDeckManager::Reset()
{
    trajectory_32={};elapsed_160=0;trajectory_valid_164=false;ik_offset_176={};vector_192={};moving_contact_208={};vector_224={};
    obstruction_height_240=0;time_to_land_244=0;proposed_time_248=0;completed_queries_252=0;can_land_256=false;force_257=false;
    blocked_258=false;tested_259=false;hippy_hurdling_260=false;publish_moving_contact_261=false;
}
void LandingDeckManager::CorrectTrajectory(Vec4 com)
{
    using namespace landing_deck_math;const auto error=Sub(AirTrajectoryPositionAt(trajectory_32,elapsed_160),com);const auto remaining=Frames(time_to_land_244);
    if(remaining>0){trajectory_32.position=Add(trajectory_32.position,error);auto opposite=error;for(auto& v:opposite)v=-v;Adjust(trajectory_32,remaining,opposite,.5f);}
}
LandingDeckFillOutput LandingDeckManager::Fill() const
{return {can_land_256&&!blocked_258,hippy_hurdling_260&&!blocked_258,publish_moving_contact_261?std::optional<Vec4>{moving_contact_208}:std::nullopt};}
bool LandingDeck::Load(const SettingsDatabase& data,std::string& error)
{
    LandingDeck next;
    const StockSettingsReader reader(data);
    if(!reader.Float("physics_landingondeck","default","DeckMinUprightness",next.settings.deck_min_uprightness,error)||
       !reader.Float("physics_landingondeck","default","ApproxCOMHeightOnLanding",next.settings.approximate_com_height,error))
        return false;
    *this=std::move(next);
    error.clear();
    return true;
}
Vec4 CalculateOffboardHippyJump(float height,Vec4 board,Vec4 com,Vec4 up,Vec4 velocity)
{
    using namespace landing_deck_math;const auto displacement=Sub(com,board);
    const auto dot=[](Vec4 a,Vec4 b){return std::fma(a[0],b[0],std::fma(a[1],b[1],a[2]*b[2]));};
    const auto current_height=dot(up,displacement),vertical=dot(up,velocity);const auto planar=Sub(velocity,Mul(up,vertical));
    return Add(planar,Mul(up,std::sqrt((height-current_height)*(19.6f*GravityScale()))));
}
}
