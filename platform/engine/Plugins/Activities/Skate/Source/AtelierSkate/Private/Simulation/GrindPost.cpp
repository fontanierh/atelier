#include "GrindForces.h"
#include <cmath>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
void CheckGrindPost(WipeoutRequests& state,GrindPostSettings settings,const WipeoutFrame& frame)
{
    state.mode=5;
    if(Dot3(frame.pose_error,frame.pose_error)>settings.max_displacement_208*settings.max_displacement_208)state.Request(1,0);
    else if(CheckWipeoutRegionalForce(frame,settings.max_body_contact_168,settings.max_arm_contact_164))state.Request(0,0);
    if(frame.board_contact)
    {
        const auto& v=frame.closing_velocity;const auto& m=frame.world_to_animation;Vec4 local;
        for(unsigned n=0;n<4;++n)local[n]=std::fma(m[2][n],v[2],std::fma(m[1][n],v[1],m[0][n]*v[0]));
        const auto square=Dot3(Vec4{local[0],0,local[2],local[3]},Vec4{local[0],0,local[2],local[3]});
        const auto length=square==0?0:square*InverseLengthSquared(square,2);
        if(length>settings.xz_acceleration_204||std::abs(local[1])>100){state.Request(2,0);if(CheckWipeoutRegionalForce(frame,1,20))state.Request(0,0);}
    }
    const auto cosine=VectorMin(VectorMin(Dot3(frame.deck[0],frame.input_board[0]),Dot3(frame.deck[1],frame.input_board[1])),Dot3(frame.deck[2],frame.input_board[2]));
    if(Acos(VectorMin(VectorMax(cosine,-1),1))>settings.max_angular_deck_error_212)state.Request(3,0);
}
}
