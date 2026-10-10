#include "PlayerGrindInput.h"
#include "PlayerGrindInputDetail.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
using namespace player_grind_detail;
namespace
{
class SurfaceQueries final:public PlayerGrindSurfaceQueries
{
    PlayerGrindInputHost& host;const WorldGeometry& world;std::array<std::uint32_t,2> actor;
public:
    SurfaceQueries(PlayerGrindInputHost& h,const WorldGeometry& w,std::array<std::uint32_t,2> a):host(h),world(w),actor(a){}
    bool Query(std::size_t i,PlayerGrindProbe p,std::optional<PlayerGrindProbeHit>& out,std::string& error)override{return host.SurfaceProbe(world,actor,i,p,out,error);}
};
class ExitQueries final:public PlayerGrindForceExitQueries
{
    PlayerGrindInputHost& host;const WorldGeometry& world;std::array<std::uint32_t,2> actor;
public:
    ExitQueries(PlayerGrindInputHost& h,const WorldGeometry& w,std::array<std::uint32_t,2> a):host(h),world(w),actor(a){}
    bool Query(PlayerGrindForceExitProbe p,std::optional<PlayerGrindForceExitHit>& out,std::string& error)override{return host.ForceExitLine(world,actor,p,out,error);}
};
}
bool PlayerGrindInputState::PostUpdate(ProcessedPhysicsInput& p,const WorldGeometry& world,PlayerGrindPending pending,
    PlayerGrindPostContext c,PlayerGrindInputHost& host,std::optional<PlayerGrindPostResult>& output,std::string& error)
{
    auto fields=pending.fields;std::optional<PlayerGrindSurface> surface;
    if(pending.geometry){auto& work=*pending.geometry;PlayerGrindSurface s;
        if(work.plan)s=ResolvePlayerGrindSurface(*work.plan,work.hits,fields.geometry_flags_1476);
        else{SurfaceQueries q(host,world,{p.actor_query_2948,p.actor_query_2952});if(!InvestigatePlayerGrindSurface(work.input,q,s,error))return false;}
        PublishPlayerGrindSurface(fields,s);
        const auto correction=TweakPlayerGrindGeometry({fields.valid_1488,fields.family_1248,p.state_2508,p.category_2512,air_frames,
            std::uint32_t(s.kind),s.flags,s.far_points,s.upmost_normal,s.high_side,Float4(fields.point_1120),Float4(fields.direction_1136),
            c.board[3],c.board[2],Float4(p.vectors_400_416[0]),settings_.deck_to_truck,balance.exit_angle_degrees,balance.exit_direction,fields.flags_1516},secondary_history);
        fields.valid_1488=correction.valid;fields.family_1248=correction.family;fields.flags_1516=correction.flags;surface=s;
    }
    fields.gravity_relief_1512=PlayerGrindGravityRelief(gravity_timer,fields.valid_1488,p.category_2512,Float4(fields.tangent_1104),
        Float4(p.vectors_400_416[0]),p.timestep_2604,settings_.gravity_vertical,settings_.gravity_linear);
    std::optional<PlayerGrindBalanceContact> contact;
    if(surface&&fields.valid_1488){if(fields.entry_kind_1252>6){error="Invalid published grind admission kind "+std::to_string(fields.entry_kind_1252);return false;}
        contact.emplace(PlayerGrindBalanceContact{*surface,Float4(fields.tangent_1104),Float4(fields.direction_1136),fields.family_1248,PlayerGrindEntryKind(fields.entry_kind_1252)});}
    PlayerGrindBalanceVectors vectors{Float4(fields.normal_1152),Float4(fields.target_up_1168)};
    balance.UpdateTargetUp({p.category_2512,p.state_2504,Float4(p.vectors_544_560_592_608[0])},contact?&*contact:nullptr,vectors);
    fields.exit_lean_1500=balance.UpdateExitLean({p.category_2512,p.state_2508,p.grind_words_2532_2536[1],p.timestep_2604},contact?&*contact:nullptr,settings_.exit_lean,vectors);
    fields.normal_1152=Raw4(vectors.grind_normal);fields.target_up_1168=Raw4(vectors.target_up);
    ExitQueries query(host,world,{p.actor_query_2948,p.actor_query_2952});
    if(!balance.UpdateForceExit(Float4(fields.point_1120),fields.flags_1516,query,error))return false;
    const auto entered=engagement.Update({fields.valid_1488,fields.family_1248,p.category_2512,p.state_2504,p.scalar_2652,c.balance_2720,
        Float4(fields.direction_1136),vectors.grind_normal,Float4(p.vectors_544_560_592_608[0]),Float4(p.vectors_400_416[0]),Float4(p.vectors_544_560_592_608[3]),
        fields.geometry_kind_1464,Float4(fields.high_side_1440),settings_.vertical_help,settings_.max_impact,fields.flags_1516,Float4(fields.entry_velocity_1184)});
    fields.valid_1488=entered.valid;fields.flags_1516=entered.flags;fields.entry_velocity_1184=Raw4(entered.entry_velocity);fields.impact_speed_1492=entered.impact_speed;
    if(!entered.wipeout_reasons.empty())p.flags_2468|=0x00040000u;
    control.Update(fields.valid_1488?fields.family_1248:UINT32_MAX,c.board[2],vectors.grind_normal,(fields.flags_1516&0x20000000u)!=0,
        (p.flags_2468&0x00100000u)!=0,(fields.flags_1516&0x10000000u)!=0,c.translation_2796,c.stability_nudge_2800,c.up_down_2804,c.grab_min_height_2808);
    fields.yaw_1504=control.yaw;fields.pitch_1508=control.pitch;
    std::optional<PlayerGrindJumpGeometry> jump;
    if(fields.valid_1488)jump=PlayerGrindJumpGeometry{fields.geometry_kind_1464,Float4(fields.high_side_1440),vectors.grind_normal,
        Float4(fields.direction_1136),Float4(fields.upmost_normal_1408),Float4(fields.point_1120)};
    p.flags_2476|=jumper.Update(jump,p.grind_words_2532_2536[0]);investigation=fields;p.grind=fields;
    std::optional<PlayerGrindObservation> observation;
    if(!MakePlayerGrindObservation(p,c,pending.spline_guids,jumper,observation,error))return false;
    output=PlayerGrindPostResult{entered.wipeout_reasons,*observation};return true;
}
}
