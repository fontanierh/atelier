#include "LandingDeckMath.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
AirTrajectoryQueryRequest LandingDeckManager::PrepareQuery(const LandingDeckInput& p,Vec4 position,float time)
{
    using namespace landing_deck_math;const auto target=Add(Madd(p.board_velocity_400,time,p.board_position_112),{0,Bits(0x3e4cccce),0,0});
    blocked_258=false;obstruction_height_240=target[1]+-.1f;
    return {{position,Sub(Mul(Sub(target,position),Reciprocal(time)),Mul(Mul(Gravity(),.5f),time)),Gravity(),time},.3f,.5f,.5f};
}
bool LandingDeckManager::Sync(std::optional<AirTrajectoryQueryResult> hit,LandingDeckSyncInput input,LandingDeckHippyVelocity& provider,std::string& error)
{
    auto next=*this;if(hit&&!offboard_air_math::Valid(*hit))hit.reset();if(!next.SyncCompleted(hit,input,provider,error))return false;*this=next;error.clear();return true;
}
bool LandingDeckManager::SyncCompleted(std::optional<AirTrajectoryQueryResult> hit,LandingDeckSyncInput input,LandingDeckHippyVelocity& provider,std::string& error)
{
    using namespace landing_deck_math;
    if(hit)
    {
        if(hit->contact_position[1]<obstruction_height_240){blocked_258=false;tested_259=true;}
        else if(tested_259)blocked_258=true;
        else if(completed_queries_252==0){moving_contact_208=hit->contact_transform[3];publish_moving_contact_261=true;}
        else
        {
            const auto contact=hit->contact_transform[3],velocity=Mul(Sub(contact,moving_contact_208),60);
            if(Dot(velocity,velocity)>Bits(0x3efae147))
            {
                hippy_hurdling_260=true;
                if(completed_queries_252==1)
                {
                    if((input.flags_2488&0x04000000)!=0)
                    {
                        const auto current=AirTrajectoryVelocityAt(trajectory_32,elapsed_160);Vec4 replacement{};if(!provider.Calculate(*this,replacement,error))return false;
                        if(replacement[1]>current[1]){const auto frame=Frames(elapsed_160);Shift(trajectory_32,float(frame)*Step());trajectory_32.velocity=replacement;Shift(trajectory_32,float(WrappingNeg(frame))*Step());}
                    }
                }
                else
                {
                    const auto landing_time=time_to_land_244+elapsed_160;const auto predicted=Madd(velocity,time_to_land_244,contact);
                    auto separation=Sub(AirTrajectoryPositionAt(trajectory_32,landing_time),predicted);separation[1]=0;const auto square=Dot(separation,separation);
                    if(AirTrajectoryVelocityAt(trajectory_32,elapsed_160)[1]<0){if(input.position_592[1]-hit->contact_position[1]<.7f){blocked_258=true;tested_259=true;}}
                    else if(square<1){blocked_258=true;tested_259=true;}else if(square>6.25f){blocked_258=false;tested_259=true;}
                }
            }
            else{hippy_hurdling_260=false;blocked_258=true;tested_259=true;}moving_contact_208=contact;
        }
    }
    else{blocked_258=false;tested_259=true;}pending_262=false;completed_queries_252+=1;error.clear();return true;
}
}
