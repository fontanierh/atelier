#include "SpeedWobble.h"
#include <cmath>
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Float(std::uint32_t word) {float value;std::memcpy(&value,&word,4);return value;}
std::uint32_t Bits(float value) {std::uint32_t word;std::memcpy(&word,&value,4);return word;}
float Unit(float value) {const auto lower=-value>=0?0:value;return 1.0f-lower>=0?lower:1;}
}
void SpeedWobbleState::Reset() {for (auto i:{0,2,3,4,5,6}) words[i]=0;words[7]&=0x00ffffff;}
float CalculateSpeedWobble(SpeedWobbleState& state,const SpeedWobbleSettings& s,SpeedWobbleInput input)
{
    const auto height=(input.center_of_mass_height-s.height_min)/(s.height_max-s.height_min),crouch=Unit(1.0f-height);
    const auto threshold=std::fma(crouch,s.crouch_threshold,s.tightness_threshold*input.truck_tightness)+input.activation_threshold;
    if (!state.IsActive() && input.speed>threshold) {state.Reset();state.words[7]|=0x01000000;}if (!state.IsActive()) return input.tilt;
    const auto time=Float(state.words[0]),time_fraction=Unit(time/s.time_range),speed_fraction=Unit((input.speed-threshold)/s.speed_range);
    const auto frequency=(s.frequency_time.Evaluate(time_fraction)*s.frequency_speed.Evaluate(speed_fraction))*s.frequency_scale;
    const auto amplitude=s.amplitude_speed.Evaluate(speed_fraction)*s.amplitude_time.Evaluate(time_fraction);
    const auto phase=std::fma(frequency,Float(0x3dd67751),Float(state.words[4])),scale=(s.amplitude_scale*amplitude)*input.amplitude_multiplier,displacement=Sin(phase)*scale;
    state.words[0]=Bits(time+Float(0x3c888889));state.words[4]=Bits(phase);state.words[5]=Bits(amplitude);state.words[6]=Bits(displacement);
    const auto result=(displacement+input.tilt)*.5f;if (input.speed<threshold) state.Reset();return result;
}
}
