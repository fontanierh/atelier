#include "PlayerGrindBalance.h"
#include "PlayerGrindInputDetail.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
using namespace player_grind_detail;
static Vec4 Blend(Vec4 a,float aw,Vec4 b,float bw){return Madd4(a,aw,Scale4(b,bw));}
static Vec4 Negate(Vec4 v){for(auto& x:v)x=-x;return v;}
static Vec4 RetainSide(Vec4 previous,Vec4 side){return Dot3(previous,side)>0?side:Negate(side);}
void PlayerGrindBalanceState::UpdateTargetUp(PlayerGrindTargetUpInput i,const PlayerGrindBalanceContact* c,PlayerGrindBalanceVectors& v)
{
    if(!c)return;
    const auto& s=c->surface;
    const auto normal=i.category!=400?i.board_up:
        (i.previous_state==402||i.previous_state==404?Blend(previous_normal,.85f,s.upmost_normal,F(0x3e199998)):
        Blend(previous_normal,.925f,s.tilted_upmost_normal,F(0x3d999998)));
    const auto d=c->directed_grind_direction;const auto projected=Cross3(Cross3(d,normal),d);
    const auto length=SquareRoot(Dot3(projected,projected));
    v.grind_normal=length<=.001f?s.upmost_normal:Scale4(projected,Reciprocal(length));previous_normal=v.grind_normal;
    const auto target=Blend(i.board_up,.8f,s.upmost_normal,F(0x3e4ccccc));
    v.target_up=Scale4(target,Reciprocal(SquareRoot(Dot3(target,target))));
    const auto alignment=VectorMin(VectorMax(Dot3(v.grind_normal,v.target_up),-1),1);const auto maximum=F(0x3e7a35dd);
    if(Acos(alignment)>maximum){const auto axis=Cross3(v.grind_normal,v.target_up);const auto axis_length=SquareRoot(Dot3(axis,axis));
        v.target_up=axis_length<=.001f?v.grind_normal:PlayerGrindRotate(Scale4(axis,Reciprocal(axis_length)),v.grind_normal,maximum);}
}
float PlayerGrindBalanceState::UpdateExitLean(PlayerGrindExitLeanInput i,const PlayerGrindBalanceContact* c,const PointGraph<8>& graph,PlayerGrindBalanceVectors& v)
{
    const bool active=i.category==400||i.current_state==701||c;
    frames_away=active?0:std::int32_t(std::uint32_t(frames_away)+1);
    const bool droppable=c&&(c->kind==2?(active&&c->surface.kind!=PlayerGrindGeometryKind::ThinRail):c->surface.kind==PlayerGrindGeometryKind::Ledge);
    bool started=false;
    if(frames_away>20){exit_angle_degrees=0;elapsed=0;entry_delay=2;}
    else if(elapsed>0||(active&&droppable&&c)){
        if(elapsed==0){if(c){entry_delay=c->entry_kind==PlayerGrindEntryKind::RideFromBelow?.8f:c->entry_kind==PlayerGrindEntryKind::RideIntoCoping?.1f:2;}started=true;}
        if(i.grind_substate!=2)elapsed=i.timestep+elapsed;
    }
    if(elapsed<=0)return exit_angle_degrees;
    const auto time=elapsed-entry_delay;exit_angle_degrees=time<=0?0:graph.Evaluate(time);
    if(c){const auto& s=c->surface;
        exit_direction=s.kind==PlayerGrindGeometryKind::ThinRail?RetainSide(exit_direction,Cross3(s.upmost_normal,c->primitive_direction)):
            started?s.high_side:RetainSide(exit_direction,s.high_side);
        if(exit_angle_degrees>0){const auto direction=c->directed_grind_direction;const auto axis=Cross3(direction,exit_direction)[1]>0?direction:Negate(direction);
            const auto radians=exit_angle_degrees*F(0x3c8efa35);
            v.target_up=PlayerGrindRotate(axis,v.target_up,radians);v.grind_normal=PlayerGrindRotate(axis,v.grind_normal,radians);}}
    return exit_angle_degrees;
}
bool PlayerGrindBalanceState::UpdateForceExit(Vec4 location,std::uint32_t& flags,PlayerGrindForceExitQueries& queries,std::string& error) const
{
    bool force=false;
    if(exit_angle_degrees>28)force=true;
    else if(exit_angle_degrees>15){const auto start=Sub(location,Scale4(exit_direction,.1f));const auto end=Add(start,{0,-5,0,0});
        std::optional<PlayerGrindForceExitHit> hit;if(!queries.Query({start,end},hit,error))return false;
        force=hit?Dot3(exit_direction,hit->normal)>-.1f:true;}
    flags=(flags&0x7fffffffu)|(std::uint32_t(force)<<31);return true;
}
}
