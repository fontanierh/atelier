// SPDX-License-Identifier: Apache-2.0
#include "PlayerGrindManager.h"
#include "PlayerGrindInputDetail.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
using namespace player_grind_detail;
Vec4 PlayerGrindDirectedTangent(Vec4 start,Vec4 end,Vec4 velocity,Vec4 previous)
{
    const auto delta=Sub(end,start);auto direction=Scale4(delta,Reciprocal(SquareRoot(Dot3(delta,delta))));
    const auto speed=Dot3(direction,velocity);
    if(speed<0)direction=Scale4(direction,-1);
    if(std::abs(speed)<.1f&&Dot3(previous,direction)<-.9f)direction=Scale4(direction,-1);
    return direction;
}
static bool Backslash(const PlayerGrindGeometryInput& i)
{
    if(i.family!=2||i.current_state==402||(i.geometry_flags&0x80000000u)!=0)return false;
    const std::array<Vec4,2> offsets{Sub(i.far_points[0],i.point),Sub(i.far_points[1],i.point)};
    const std::array<float,2> heights{Dot3(offsets[0],i.upmost),Dot3(offsets[1],i.upmost)};
    if(std::abs(heights[0]-heights[1])<=i.deck_to_truck*.1f)return false;
    return Dot3(Sub(i.board_position,i.point),heights[0]>heights[1]?offsets[0]:offsets[1])>0;
}
PlayerGrindGeometryOutput TweakPlayerGrindGeometry(PlayerGrindGeometryInput i,std::uint32_t& avoid)
{
    PlayerGrindGeometryOutput o{i.valid,i.family,i.flags};
    if(i.geometry_kind==3||(i.family==2&&(i.geometry_flags&0x10000000u)!=0&&i.category!=400&&i.air_frames<20)
        ||(i.family==1&&(i.geometry_flags&0x10000000u)!=0))o.valid=false;
    if(o.valid&&Backslash(i))o.family=4;
    if(o.valid&&i.previous_exit_angle>0&&i.geometry_kind!=2&&Dot3(i.previous_exit_direction,i.high_side)<0)o.valid=false;
    if(o.valid&&i.geometry_kind!=0){auto transverse=Sub(Scale4(i.direction,Dot3(i.direction,i.velocity)),i.velocity);transverse[1]=0;
        if(Dot3(transverse,transverse)>12.25f&&Dot3(i.velocity,i.high_side)<0)o.valid=false;}
    if(o.family==3&&i.geometry_kind==2){if(std::int32_t(avoid)>0)o.valid=false;else{
        const auto hanging=(o.flags&0x20000000u)!=0?Scale4(i.board_forward,-1):i.board_forward;
        if(Dot3(hanging,i.high_side)>0){const auto vertical=Dot3(hanging,i.upmost);
            o.flags=(o.flags&~0x10000000u)|(vertical<.19f?0x10000000u:0);
            if(vertical<0){o.valid=false;avoid=30;}}}}
    return o;
}
float PlayerGrindGravityRelief(float& timer,bool valid,std::uint32_t category,Vec4 tangent,Vec4 velocity,
    float dt,const PointGraph<4>& vertical,const PointGraph<4>& linear)
{
    if(valid&&category==100&&PlayerGrindEngagementSlope(tangent,velocity)>.85f)
        timer=vertical.Evaluate(velocity[1])*linear.Evaluate(std::abs(Dot3(tangent,velocity)));
    const auto next=timer-dt;timer=-next>=0?0:next;return timer;
}
std::uint32_t PlayerGrindJumper::Update(std::optional<PlayerGrindJumpGeometry> next_geometry,std::uint32_t published)
{
    launched=false;const auto next=cooldown-1;cooldown=std::int32_t(next)<0?0:next;
    if(next_geometry)geometry=*next_geometry;if(published!=UINT32_MAX)family=published;
    const auto next_energy=energy+.0035f;energy=1-next_energy>=0?next_energy:1;
    return cooldown>0?0x02000000u:0;
}
}
