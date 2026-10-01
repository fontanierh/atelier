// SPDX-License-Identifier: Apache-2.0
#include "KnownAirPrivate.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate::known_air
{
void InitializeTrajectory(KnownAirState& state,const KnownAirFrame& frame,const KnownAirSettings& settings,const KnownAirModeSettings& mode,Live& live)
{
    state.landing_normal_64=frame.selector_landing_normal_2656;
    const auto prediction=live.Prediction();const auto highest=AirTrajectoryHighestPosition(Actual(prediction.trajectory));
    state.time_to_apex_200=highest.second;state.trajectory_apex_96=highest.first;
    state.collision_position_112=live.selection.prediction.result.contact_position;state.collision_time_196=prediction.collision_time_48;
    state.body_flip_target_speed_204=mode.perfect_body_flips_28?Bits(0xc0f1463b)/state.collision_time_196:(settings.flip_scalar/state.collision_time_196)*Bits(0xc0c90fdb);
    state.selector_vector_128=live.board_position;Vec4 heading{};bool heading_valid=false;state.collision_normal_speed_176=0;
    if (state.collision_time_196>=0)
    {
        const auto previous_time=static_cast<float>(WrappingAdd(prediction.collision_frame_128,std::uint32_t(-2)))*Bits(0x3c888889);
        const auto collision_time=static_cast<float>(WrappingAdd(prediction.collision_frame_128,std::uint32_t(-1)))*Bits(0x3c888889);
        const auto previous=Position(prediction.trajectory,previous_time),collision=Position(prediction.trajectory,collision_time);
        const auto delta=Sub(collision,previous),velocity=Scale(delta,RefinedReciprocal(Bits(0x3c888889),2));
        state.collision_normal_speed_176=Dot3(state.landing_normal_64,velocity);
        const auto normal_velocity=Scale(state.landing_normal_64,state.collision_normal_speed_176),tangent=Sub(velocity,normal_velocity);
        const auto normalized=Normalize(tangent);
        if (!(settings.min_target_heading_velocity_420>normalized.second)) {heading=normalized.first;heading_valid=true;}
    }
    state.landing_heading_80=heading;state.landing_heading_valid_209=heading_valid;
    if (Bits(0x3dcccccd)>Dot3(heading,heading)) state.landing_heading_valid_209=false;
}
void RestoreVelocity(KnownAirState& state,KnownAirFrame& frame,const KnownAirSettings& settings,Live& live)
{
    const auto prediction=live.Prediction();if (state.trajectory_index_216==0) state.trajectory_index_216=1;
    const auto sample_time=static_cast<float>(state.trajectory_index_216)*Bits(0x3c888889);
    const auto velocity=Velocity(prediction.trajectory,sample_time);const auto geometry=RestoreGeometry(velocity,frame.ground_normal_464);
    const auto curve=settings.landing_speed_scalar_vs_ground_normal_y_240.Evaluate(geometry.landing_speed_curve_input);
    const auto lower=Select(-geometry.landing_speed_blend_source,0,geometry.landing_speed_blend_source),blend=Select(1-lower,lower,1);
    const auto speed_scale=std::fma(curve-1.0f,blend,1.0f);const auto scaled_tangent=Scale(geometry.tangential_velocity,speed_scale);
    const auto preserved=Dot3(live.BoardVelocity(),frame.ground_normal_464);Vec4 restored{};
    for (std::size_t i=0;i<4;++i) restored[i]=std::fma(frame.ground_normal_464[i],preserved,scaled_tangent[i]);
    live.SetBoardVelocity(restored);frame.forward_speed_2612=Dot3(restored,live.BoardForward());
}
void Follow(KnownAirState& state,const KnownAirFrame& frame,const KnownAirSettings& settings,const Live& live)
{
    state.trajectory_index_216=WrappingAdd(state.trajectory_index_216,1);
    const auto ratio=(settings.trajectory_error_blend_away_time_384-state.time_in_state_180)/settings.trajectory_error_blend_away_time_384;
    const auto lower=Select(-ratio,0,ratio),blend=Select(1-lower,lower,1);
    const auto time=static_cast<float>(state.trajectory_index_216)*Bits(0x3c888889);
    const auto position=Position(Trajectory(live.selection.com_trajectory),time);
    for (std::size_t i=0;i<4;++i) state.target_com_position_160[i]=std::fma(state.trajectory_follow_offset_144[i],blend,position[i]);
    if (frame.flags_2468&8) state.trajectory_index_216=WrappingAdd(state.trajectory_index_216,std::uint32_t(-1));
}
}
