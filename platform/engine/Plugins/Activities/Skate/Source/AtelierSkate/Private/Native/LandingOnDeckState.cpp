// SPDX-License-Identifier: Apache-2.0
#include "LandingOnDeckState.h"
#include "LandingDeckMath.h"
#include <cstdlib>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
// Rust f32::clamp rejects reversed/NaN bounds and keeps a NaN value.
float LandingClamp(float value,float low,float high)
{if(!(low<=high))std::abort();return value<low?low:value>high?high:value;}
}
void LandingOnDeckState::Enter(LandingDeckManager& manager,LandingOnDeckEntry input)
{
    using namespace landing_deck_math;const auto preserve=input.previous_category==500;if(!preserve)manager.Reset();*this={};
    auto right=input.animation_right;if(input.reversed)for(auto& lane:right)lane=-lane;
    transition_angle=WrapAngle(ProjectedAngle(input.hips_up,right,Up));
    if(input.hippy||!preserve)
    {
        const auto velocity=input.hippy?CalculateOffboardHippyJump((1-input.strength)*1.35f+input.strength*1.65f,input.board_position,input.com_position,input.up,input.board_velocity):input.com_velocity;
        manager.trajectory_32={input.com_position,velocity,Gravity(),-1};manager.elapsed_160=0;manager.trajectory_valid_164=true;manager.force_257=input.hippy;if(input.hippy)takeoff_frames=2;
    }
    else{manager.elapsed_160+=Step();manager.CorrectTrajectory(input.com_position);}hippy=input.hippy;
}
void LandingOnDeckState::Align(const LandingOnDeckSettings& settings,Vec4 board_forward,Vec4 animation_forward,float state_time,float com_velocity_y,float input_spin)
{
    using namespace landing_deck_math;const auto frames=time_to_land*59.999996f;auto angle=ProjectedAngle(board_forward,animation_forward,Up);
    if(state_time<.28f)angle-=(1-state_time*3.5714285f)*transition_angle;
    angle=WrapAngle(spin_rate*frames+angle);turning=std::abs(angle)>Bits(0x3fc90fdb);
    if(time_to_land>Bits(0x37800000))
    {
        const auto rising=com_velocity_y>0;const auto input=rising&&hippy?input_spin:0;float target,delta;
        if(std::abs(input)>Bits(0x37800000)){target=(-settings.input_speed)*input;delta=settings.input_delta;}
        else
        {
            if(rising){angle=WrapAngle(angle);if(std::abs(angle)>Bits(0x3fc90fdb))angle=(std::abs(angle)-Bits(0x40490fdb))*std::copysign(1.0f,angle);}
            const auto tolerance=settings.minimum_auto_angle*.017453292f;
            if(std::abs(angle)>tolerance){const auto excess=angle>0?VectorMax(angle-tolerance,0):VectorMin(angle+tolerance,0);target=LandingClamp(spin_rate-excess/frames,-settings.automatic_speed,settings.automatic_speed);}else target=spin_rate;
            delta=settings.automatic_delta;
        }
        spin_rate=LandingClamp(target,spin_rate-delta,spin_rate+delta);applied_spin=spin_rate;
        if(state_time<.28f)applied_spin=std::fma(-transition_angle,.059523813f,spin_rate);
    }
}
void LandingOnDeckState::AdvanceSpin(LandingDeckUpdateOutput value)
{
    using namespace landing_deck_math;accumulated_spin+=applied_spin;half_turns=Integer(accumulated_spin*.31830987f);next_half_turns=half_turns;
    if(accumulated_spin<0&&applied_spin<0)next_half_turns=WrappingSub(next_half_turns,1);else if(accumulated_spin>0&&applied_spin>0)next_half_turns=WrappingAdd(next_half_turns,1);
    time_to_land=value.time_to_land;output=value;
}
float LandingOnDeckState::AccurateTime(float board_y,float board_velocity_y,float com_velocity_y,std::array<float,2> toes,std::uint32_t wheels)
{
    using namespace landing_deck_math;const auto feet=(toes[0]+toes[1])*.5f-.15000001f,velocity=com_velocity_y-board_velocity_y,displacement=board_y-feet,gravity=wheels!=0?-9.8f:-4.9f;
    const auto discriminant=velocity*velocity+(displacement*gravity)*2;if(discriminant>0){const auto root=discriminant*Inverse(discriminant,2);return (-velocity-root)/gravity;}return 0;
}
void LandingOnDeckState::Finish(const LandingOnDeckSettings& settings,float velocity)
{if(takeoff_frames>0)--takeoff_frames;dangerous=time_to_land<.07f&&velocity<-settings.maximum_landing_speed;}
}
