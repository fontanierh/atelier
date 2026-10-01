// SPDX-License-Identifier: Apache-2.0
#include "KnownAirSettings.h"
#include "StockSettingsReader.h"
#include <cstring>
namespace atelier::skate
{
bool LoadKnownAirConfiguration(const SettingsDatabase& data,KnownAirConfiguration& output,std::string& error)
{
    KnownAirConfiguration c{};auto& s=c.settings;const StockSettingsReader reader(data);
    const auto graph=[&](std::string_view name,PointGraph<8>& value){return reader.Curve8Layout20("physics_airstates","default",name,value,error);};
    const auto scalar=[&](std::string_view name,float& value){return reader.Float("physics_airstates","default",name,value,error);};
    if (!graph("MaxHeadingAdjustVsUpY",s.max_heading_adjust_vs_up_y_160)
        ||!graph("LandingSpeedScalarVsGroundNormalY",s.landing_speed_scalar_vs_ground_normal_y_240)
        ||!graph("Hash_AA79C93673533C5B",s.flip_start_collision_time_vs_normal_y)
        ||!scalar("TrajErrorBlendAwayTime",s.trajectory_error_blend_away_time_384)
        ||!scalar("MinTargetHeadingVel",s.min_target_heading_velocity_420)
        ||!scalar("MinAutoBodySpeed",s.min_auto_body_speed_424)
        ||!scalar("MaxSpinSpeed",s.max_spin_speed_428)
        ||!scalar("FramesForGrindAirAssist",s.frames_for_grind_air_assist_436)
        ||!scalar("BodyFlipMinGrabTimeFraction",s.body_flip_min_grab_time_fraction_456)
        ||!reader.Float("physics_reckoning","default","FlipScalar",s.flip_scalar,error)) return false;
    const std::array<std::string_view,5> keys{"easy","normal","hardcore","motorized","test"};
    for (std::size_t i=0;i<keys.size();++i)
    {
        auto& m=c.modes[i];
        if (!reader.Boolean("physics_mode",keys[i],"Hash_2B913C786BEFF4CD",m.upside_down_falling_wipeout_enabled_2,error)
            ||!reader.Boolean("physics_mode",keys[i],"PerfectBodyFlips",m.perfect_body_flips_28,error)
            ||!reader.Float("physics_mode",keys[i],"MaxAutoBodySpinSpeed",m.body_spin_speed_limit_56,error)) return false;
    }
    if (!reader.Float("physics_wipeout","default","Wipeout_AirFallingMinUpY",c.wipeout.air_falling_min_up_y_260,error)
        ||!reader.Float("physics_wipeout","default","Wipeout_AirFallingMaxAngle",c.wipeout.air_falling_max_angle_264,error)) return false;
    std::vector<std::uint32_t> words;if (!reader.Words("physics_reckoning","default","FlipAxisAdjustment",4,words,error)) return false;
    for (std::size_t i=0;i<4;++i) std::memcpy(&c.flip_axis_adjustment[i],&words[i],4);
    output=std::move(c);error.clear();return true;
}
}
