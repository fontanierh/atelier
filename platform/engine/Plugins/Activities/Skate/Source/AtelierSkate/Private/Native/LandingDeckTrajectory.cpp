// SPDX-License-Identifier: Apache-2.0
#include "LandingDeckMath.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
void LandingDeckManager::ConsiderBoard(const LandingDeckInput& p,LandingDeckSettings settings,Vec4 position,Vec4 velocity)
{
    using namespace landing_deck_math;const auto airborne=p.wheel_contacts_2556==0;auto board_velocity=p.board_velocity_400;if(airborne)board_velocity[1]=0;
    const AirTrajectory relative{position,Sub(velocity,board_velocity),airborne?Mul(Gravity(),.5f):Gravity(),-1};
    const auto target=Madd(p.up_544,settings.approximate_com_height,p.board_position_112);const auto time=GreatestPlaneTime(relative,target,p.up_544);
    if(!time||!(*time>0)){can_land_256=false;return;}
    const auto distance=Length(Sub(position,target)),optimal=Root(Reciprocal(Bits(0x411ccccd))*(2*distance));
    const auto proposed_time=VectorMin(*time*1.3f,VectorMax(*time*.75f,optimal));
    proposed_96={position,Add(Sub(Mul(Sub(target,position),Reciprocal(proposed_time)),Mul(Mul(Gravity(),.5f),proposed_time)),p.board_velocity_400),Gravity(),-1};
    ik_offset_176=Sub(target,AirTrajectoryPositionAt(relative,*time));ik_offset_176[1]=0;time_to_land_244=*time;proposed_time_248=proposed_time;
}
}
