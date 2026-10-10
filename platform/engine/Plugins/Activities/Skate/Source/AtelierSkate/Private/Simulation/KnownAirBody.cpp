#include "KnownAirPrivate.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate::known_air
{
float FlipSpeed(KnownAirState& state,const KnownAirFrame& frame,const KnownAirSettings& settings,const KnownAirModeSettings& mode,const KnownAirReckoningFields& reckoning,Live& live)
{
    if (!state.body_flipping_211)
    {
        const auto flags=frame.flags_2468;const bool has_flip=(flags&0x20)!=0||(flags&0x10)!=0,has_grab=(flags&0x80)!=0||(flags&0x40)!=0;
        if (has_flip&&has_grab&&(frame.flags_2488&0x02000000)==0)
        {
            const auto threshold=settings.flip_start_collision_time_vs_normal_y.Evaluate(reckoning.landing_normal_1152[1]);
            if (state.collision_time_196>threshold) {live.BeginFlip(((flags>>7)&1)!=0);state.body_flipping_211=true;}
        }
    }
    if (mode.perfect_body_flips_28) return state.body_flip_target_speed_204;
    const auto flags=frame.flags_2468;
    return (flags&0x20)!=0||(flags&0x10)!=0||state.time_in_state_180<settings.body_flip_min_grab_time_fraction_456?state.body_flip_target_speed_204:0;
}
float SpinSpeed(const KnownAirState& state,const KnownAirFrame& frame,const KnownAirSettings& settings,const KnownAirModeSettings& mode,const KnownAirReckoningFields& reckoning)
{
    const auto manual=(frame.body_spin_input_2640*settings.max_spin_speed_428)*Bits(0x3c8efa35);
    float result=frame.flags_2472&0x10000000?manual:0;
    if (manual==0&&state.landing_heading_valid_209&&(frame.flags_2484&0x8000)==0)
    {
        auto heading=reckoning.heading_axis_1200;
        if ((((frame.flags_2468>>20)&1)!=0)!=state.start_flipped_210)
        {
            for (auto& lane:heading) {std::uint32_t bits;std::memcpy(&bits,&lane,4);bits^=0x80000000;std::memcpy(&lane,&bits,4);}
        }
        float unwrapped=0;
        if (Dot3(reckoning.landing_normal_1152,state.landing_normal_64)>Bits(0x3a83126f))
        {unwrapped=Signed(heading,state.landing_heading_80,reckoning.landing_normal_1152);if (frame.flags_2468&0x00100000) unwrapped+=Bits(0x40490fdb);}
        auto corrected=Wrap(unwrapped);const auto degrees=corrected*Bits(0x42652ee1);
        const auto max_adjust=settings.max_heading_adjust_vs_up_y_160.Evaluate(frame.skater_up_544[1]);
        if (std::abs(degrees)>max_adjust) corrected=Wrap(Wrap(Bits(0x40490fdb))+corrected);
        auto current=reckoning.body_spin_speed_1572;const auto remaining=state.collision_time_196-state.time_in_state_180;
        const auto alignment_time=Select(remaining-Bits(0x3d03126f),remaining,Bits(0x3d03126f));const auto reciprocal=1/alignment_time;
        auto target=(reciprocal*corrected)*Bits(0x3f99999a);
        if (std::abs(current)<Bits(0x3a83126f)) current=0;
        if (current*target<0)
        {
            const auto alternate=Wrap(unwrapped+Bits(0x40490fdb));
            if (Bits(0x42340000)*Bits(0x3c8efa35)>std::abs(alternate)&&(reciprocal*alternate)*current>0) target=reciprocal*alternate;
        }
        const auto lower=Select(-mode.body_spin_speed_limit_56-target,-mode.body_spin_speed_limit_56,target);
        result=Select(mode.body_spin_speed_limit_56-lower,lower,mode.body_spin_speed_limit_56);
        if (std::abs(result)<settings.min_auto_body_speed_424) result*=0.5f;
        if (std::abs(unwrapped)<settings.min_auto_body_speed_424) result=(unwrapped/frame.delta_time_2604)*0.5f;
        if (result*current<0) result*=Bits(0x3ba3d70a);
        else if (std::abs(current)>std::abs(result)) result*=Bits(0x3f400000);
    }
    return result;
}
}
