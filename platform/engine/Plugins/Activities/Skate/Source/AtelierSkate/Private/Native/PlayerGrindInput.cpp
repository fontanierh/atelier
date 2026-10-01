// SPDX-License-Identifier: Apache-2.0
#include "PlayerGrindInput.h"
#include "PlayerGrindInputDetail.h"
#include "StockSettingsReader.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
using namespace player_grind_detail;
static std::uint32_t Decrement(std::uint32_t n){const auto next=n-1;return (next&0x80000000u)!=0?0:next;}
bool PlayerGrindInputSettings::Load(const SettingsDatabase& db,PlayerGrindInputSettings& out,std::string& error)
{
    StockSettingsReader reader(db);std::vector<std::uint32_t> words;
    if(!reader.Words("physics_grinds","default","ExitLeanAngleVsTime",20,words,error))return false;
    PlayerGrindInputSettings value;for(std::size_t i=0;i<8;++i){value.exit_lean.x[i]=F(words[i+4]);value.exit_lean.y[i]=F(words[i+12]);}
    const auto graph=[&](std::string_view name,PointGraph<4>& g){std::vector<std::uint32_t> w;if(!reader.Words("physics_grinds","default",name,12,w,error))return false;
        for(std::size_t i=0;i<4;++i){g.x[i]=F(w[i+4]);g.y[i]=F(w[i+8]);}return true;};
    if(!graph("FrictionVsTime",value.friction)||!graph("DVEntryThreshScalarVsSinSlope",value.slope_threshold)
        ||!graph("VertEngagementHelpVsVelY",value.vertical_help)||!graph("TimeOfGravityReliefVsVerticalSpeed",value.gravity_vertical)
        ||!graph("GravityReliefTimeVsLinearSpeed",value.gravity_linear))return false;
    if(!reader.Float("physics_grinds","default","TruckToWheel",value.truck_to_wheel,error)
        ||!reader.Float("physics_grinds","default","DeckCenterToTruck",value.deck_to_truck,error)
        ||!reader.Float("physics_grinds","default","TestDepthEpsilon",value.test_above,error)
        ||!reader.Float("physics_grinds","default","TestDepth",value.test_below,error)
        ||!reader.Float("physics_wipeout","default","Wipeout_AirMaxSpeedIntoCollisionNearGrind",value.max_impact,error))return false;
    out=value;return true;
}
std::optional<PlayerGrindInputState> PlayerGrindInputState::Load(const SettingsDatabase& db,std::string& error)
{
    PlayerGrindInputState value;if(!PlayerGrindInputSettings::Load(db,value.settings_,error))return std::nullopt;return value;
}
void PlayerGrindInputState::Reset()
{
    previous_state=0;engagement_counter=0;cooldown=0;disabled=false;suppressed=false;elapsed=0;gravity_timer=0;
    friction_vs_time=0;previous_direction={};investigation={};
}
void PlayerGrindInputState::Permission(const ProcessedPhysicsInput& p,std::int32_t air_counter)
{
    const auto state=p.state_2508;if(state!=previous_state){engagement_counter+=state==400||state==402||state==404?50:state==403?20:0;previous_state=state;}
    engagement_counter=Decrement(engagement_counter);suppressed=engagement_counter>151;cooldown=suppressed?90:Decrement(cooldown);
    disabled=(p.flags_2468&0x18000000u)!=0||(p.flags_2472&0x8008u)!=0||(p.flags_2476&0x00400000u)!=0||cooldown>0
        ||(p.category_2512==200&&(p.state_timer_2664<=F(0x3da3d70a)||air_counter<=10))||p.category_2512==500
        ||((p.flags_2472&4)!=0&&p.category_2512!=400);
    elapsed=p.category_2512==400||state==701?elapsed+p.timestep_2604:0;
}
void PlayerGrindInputState::AdvanceHistory(const ProcessedPhysicsInput& p)
{
    low_wheel_frames=previous_proximity&&p.state_2508==100&&std::int32_t(p.wheel_count_2556)<2&&p.scalar_2652<.8f?low_wheel_frames+1:0;
    grind_history=p.grind_words_2532_2536[1]==2?70:Decrement(grind_history);secondary_history=Decrement(secondary_history);
    grounded_frames=p.category_2512==100?grounded_frames+1:0;air_frames=p.category_2512==100?0:air_frames+1;
}
PlayerGrindMaterialMode PlayerGrindInputState::MaterialMode(const ProcessedPhysicsInput& p,bool nearby,bool targeting)
{
    if(p.state_2508==300||p.category_2512==500)return PlayerGrindMaterialMode::Unchanged;
    const bool enabled=(nearby&&(p.state_2508==200||p.state_2508==201))||p.category_2512==400||p.state_2508==701
        ||(p.category_2512==100&&previous_air_target);
    previous_air_target=p.state_2508==201&&targeting;return enabled?PlayerGrindMaterialMode::Grind:PlayerGrindMaterialMode::Standard;
}
}
