#include "OffboardAirLaunch.h"
#include "OffboardAirMath.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
std::uint8_t OffboardAirLaunchMode(const OffboardAirLaunchInput& p,bool current)
{
    const auto state=current?p.current_state_2508:p.previous_state_2504,category=current?p.current_category_2512:p.previous_category_2516;
    if(category==100)return 0;if(category==400)return 1;if(category==200)return 2;
    if(category==500){if((p.flags_2480&0x80)!=0||state==503)return 3;if((p.flags_2476&0x80000)!=0)return 4;return 5;}return 6;
}
bool ProduceOffboardAirLaunch(OffboardAirLaunchPacket& packet,const BipedControllerState& state,const PointGraph<8>& turn,
    OffboardAirLaunchSettings settings,const OffboardAirLaunchInput& p,bool current,std::string& error)
{
    using namespace offboard_air_math;const auto mode=OffboardAirLaunchMode(p,current);
    if(mode==1&&!p.departure_geometry){error="Offboard launch mode1 requires source-backed departure geometry1120/1136";return false;}
    const auto forward=UnitOr(Flat(p.forward_224),{});packet.up_48=p.up_544;packet.forward_64=forward;
    packet.scalar_96=Bits(0x3db2b8c2);packet.scalar_100=Bits(0x3f5f66f3);packet.scalar_104=Bits(0x3f32b8c2);
    packet.kind_108=1;packet.kind_112=0;packet.position_32=p.position_592;
    auto velocity=p.velocity_608,secondary=velocity;
    switch(mode)
    {
    case 0:{const auto lower=Select(velocity[1]-3,velocity[1],3);velocity[1]=Select((velocity[1]+3)-lower,lower,velocity[1]+3);
        packet.board_position_80=p.board_position_112;packet.has_board_position_116=true;packet.position_32=Madd(velocity,Step(),packet.position_32);break;}
    case 1:{const auto d=*p.departure_geometry;const auto delta=Sub(p.position_592,d.point_1120),projected=Sub(delta,Mul(d.axis_1136,Dot(delta,d.axis_1136)));
        velocity=Add(Madd(UnitOr(Flat(projected),{}),2,velocity),Up);packet.position_32=Madd(velocity,Step(),packet.position_32);packet.kind_108=6;break;}
    case 3:{const auto side=Cross(Up,velocity);const auto speed=Length(side);if(!(speed<=Bits(0x3a83126f)))velocity=Madd(side,((p.flags_2476&4)!=0?.75f:-.75f)/speed,velocity);break;}
    case 4:{const auto result=Jump(state,turn,settings,p,forward);velocity=result.first;secondary=result.second;packet.kind_108=6;packet.kind_112=3;break;}
    case 5:{const auto horizontal=Flat(velocity);if(!(Length(horizontal)>=1.875f)){velocity=Mul(UnitOr(horizontal,forward),2.5f);velocity[1]=Select(1-velocity[1],1,velocity[1]);packet.scalar_96=Bits(0x3f060a92);}else{velocity=Mul(p.velocity_912,.75f);velocity[1]=Clamp(velocity[1],-10,5);}packet.kind_108=6;break;}
    default:break;
    }
    packet.velocity_0=velocity;packet.secondary_velocity_16=secondary;error.clear();return true;
}
}
