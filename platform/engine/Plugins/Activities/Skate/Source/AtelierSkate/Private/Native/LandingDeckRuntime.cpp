// SPDX-License-Identifier: Apache-2.0
#include "LandingDeckMath.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
bool ReadLandingDeckInput(LandingDeckPlayerView input,LandingDeckInput& output,std::string& error)
{
    using namespace landing_deck_math;if(!input.toolkit){error="Landing manager requires the current processed BoardToolkit";return false;}
    const auto& p=input.processed;const auto& board=*input.toolkit;
    output={board.deck[1],board.deck[3],FromRaw(p.vectors_400_416[0]),FromRaw(p.vectors_544_560_592_608[0]),std::int32_t(p.external_physics_1616.flags),p.flags_2480,p.surface_mode_2540,p.wheel_count_2556};error.clear();return true;
}
bool LandingDeck::Assist(const OffboardStaticScene& scene,LandingDeckPlayerView input,float maximum,std::string& error)
{
    using namespace landing_deck_math;LandingDeckInput p;if(!ReadLandingDeckInput(input,p,error))return false;auto next=manager;
    const auto request=next.Assist({p,Position(input),Velocity(input),maximum},settings);
    if(request){AirTrajectoryQueryResult result;if(!scene.Trajectory(*request,std::int32_t(input.processed.actor_query_2952),0,result,error))return false;completion_=result;next.QuerySubmitted();}
    manager=next;error.clear();return true;
}
bool LandingDeck::Update(const OffboardStaticScene& scene,LandingDeckPlayerView input,LandingDeckUpdateOutput& output,std::string& error)
{
    LandingDeckInput p;if(!ReadLandingDeckInput(input,p,error))return false;auto next=manager;const auto out=next.Update(p,settings);
    if(out.query){AirTrajectoryQueryResult result;if(!scene.Trajectory(*out.query,std::int32_t(input.processed.actor_query_2952),0,result,error))return false;completion_=result;next.QuerySubmitted();}
    manager=next;output=out;error.clear();return true;
}
bool LandingDeck::Submit(const OffboardStaticScene& scene,AirTrajectoryQueryRequest request,LandingDeckPlayerView input,std::string& error)
{
    AirTrajectoryQueryResult completion;if(!scene.Trajectory(request,std::int32_t(input.processed.actor_query_2952),0,completion,error))return false;completion_=completion;manager.QuerySubmitted();error.clear();return true;
}
namespace
{
class ActualHippyVelocity final:public LandingDeckHippyVelocity
{
public:
    explicit ActualHippyVelocity(LandingDeckPlayerView input):input_(input){}
    bool Calculate(const LandingDeckManager&,Vec4& output,std::string& error) override
    {
        using namespace landing_deck_math;LandingDeckInput p;if(!ReadLandingDeckInput(input_,p,error))return false;
        const auto height=Bits(input_.processed.vectors_880_896_912_928_944[3][1])+Bits(0x3e4ccccd);
        output=CalculateOffboardHippyJump(height,p.board_position_112,Position(input_),p.up_544,p.board_velocity_400);error.clear();return true;
    }
private:LandingDeckPlayerView input_;
};
}
bool LandingDeck::PostPhysics(LandingDeckPlayerView input,std::string& error)
{
    if(!manager.pending_262){if(completion_){error="Landing query completion exists without native pending262";return false;}error.clear();return true;}
    if(!completion_){error="Landing pending262 has no submitted world-query completion";return false;}
    ActualHippyVelocity provider(input);const auto& p=input.processed;const auto hit=offboard_air_math::Valid(*completion_)?completion_:std::nullopt;
    if(!manager.Sync(hit,{landing_deck_math::Position(input),p.flags_2488},provider,error))return false;completion_.reset();error.clear();return true;
}
bool LandingDeck::CalculateAccurateIkOffset(LandingDeckPlayerView input,const Mat4& root,Vec4 com,Vec4 mapped,float time,Vec4& output,std::string& error)
{
    LandingDeckInput p;if(!ReadLandingDeckInput(input,p,error))return false;output=manager.CalculateAccurateIkOffset({p,time,root,com,mapped});error.clear();return true;
}
void LandingDeck::Publish(OffBoardOutputFields& output,RawVector& skeleton_position,std::uint8_t& skeleton_flag) const
{
    const auto values=manager.Fill();output.flag_316=std::uint8_t(values.can_land_316);output.hippy_hurdling_317=std::uint8_t(values.hippy_hurdling_317);
    if(values.moving_contact){skeleton_flag=1;for(std::size_t n=0;n<4;++n)std::memcpy(&skeleton_position[n],&(*values.moving_contact)[n],4);}
}
}
