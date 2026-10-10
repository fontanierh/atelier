#include "PlayerGrindEntry.h"
#include "PlayerGrindInputDetail.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
using namespace player_grind_detail;
Vec4 PlayerGrindGroundedVelocity(std::uint32_t kind,Vec4 direction,Vec4 velocity,float balance,float speed,const PointGraph<4>& graph)
{
    const auto base=kind==1?.1f:(kind==2||kind==4)&&balance!=0&&speed<1.45f?1:kind==2?.4f:
        kind==0||kind==3||kind==4||kind==5?.2f:0;
    const auto help=graph.Evaluate(PlayerGrindEngagementSlope(direction,velocity));const auto weighted=std::fma(help,1-base,base);
    const auto amount=1-weighted>=0?weighted:1;const auto along=Dot3(velocity,direction);
    Vec4 out;for(std::size_t i=0;i<4;++i)out[i]=std::fma(direction[i]*along,amount,velocity[i]*(1-amount));return out;
}
Vec4 PlayerGrindAirborneVelocity(std::uint32_t kind,Vec4 direction,Vec4 normal,Vec4 velocity)
{
    const auto across=Cross3(normal,direction);const auto removed=Scale4(across,Dot3(velocity,across));
    const auto amount=kind==0||kind==3?.4f:kind==1||kind==5?.2f:kind==2||kind==4?.8f:0;
    Vec4 out;for(std::size_t i=0;i<4;++i)out[i]=std::fma(velocity[i]-removed[i],amount,velocity[i]*(1-amount));return out;
}
static void Impacts(Vec4 direction,Vec4 board,Vec4 initial,Vec4 corrected,std::uint32_t kind,Vec4 side,float maximum,
    float& impact,std::vector<std::size_t>& reasons)
{
    const auto delta=Sub(corrected,initial);impact=SquareRoot(Dot3(delta,delta));if(impact>maximum)reasons.push_back(9);
    const auto along=Dot3(board,direction);auto transverse=Sub(Scale4(direction,along),board);transverse[1]=0;
    if(Dot3(transverse,transverse)>49&&(kind==0||Dot3(board,side)>0))reasons.push_back(14);
}
PlayerGrindEntryOutput PlayerGrindEngagement::Update(const PlayerGrindEntryInput& i)
{
    if(i.valid&&i.kind==2&&(i.previous_state_2504==701||i.previous_state_2504==403)&&i.speed>1.8f)tipslide_frames=8;
    else{const auto next=tipslide_frames-1;tipslide_frames=std::int32_t(next)<0?0:next;}
    PlayerGrindEntryOutput o{i.valid,(i.flags&~0x02000000u)|(tipslide_frames>0?0x02000000u:0),i.previous_entry_velocity,0,{}};
    if(!o.valid)return o;o.flags&=~0x40000000u;if(i.category!=100&&i.category!=200)return o;
    if(std::abs(Dot3(i.up,i.direction))>.5f){o.valid=false;if(i.category==200)o.wipeout_reasons.push_back(13);return o;}
    o.flags|=0x40000000u;const auto initial=i.category==100?i.board_velocity:i.air_velocity;
    o.entry_velocity=i.category==100?PlayerGrindGroundedVelocity(i.kind,i.direction,i.board_velocity,i.balance_2720,i.speed,i.vertical_help):
        PlayerGrindAirborneVelocity(i.kind,i.direction,i.normal,i.air_velocity);
    Impacts(i.direction,i.board_velocity,initial,o.entry_velocity,i.surface_kind,i.high_side,i.max_delta,o.impact_speed,o.wipeout_reasons);
    if(!o.wipeout_reasons.empty())o.valid=false;return o;
}
std::vector<std::size_t> PlayerGrindAirborneRejections(Vec4 direction,Vec4 up,Vec4 board,Vec4 air,Vec4 corrected,std::uint32_t kind,Vec4 side,float maximum)
{
    if(std::abs(Dot3(up,direction))>.5f)return {13};std::vector<std::size_t> reasons;float impact;
    Impacts(direction,board,air,corrected,kind,side,maximum,impact,reasons);return reasons;
}
}
