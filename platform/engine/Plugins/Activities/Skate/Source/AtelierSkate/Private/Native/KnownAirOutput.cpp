// SPDX-License-Identifier: Apache-2.0
#include "KnownAirPrivate.h"
#include <algorithm>
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate::known_air
{
namespace
{
RawVector Words(Vec4 value){RawVector out{};for (std::size_t i=0;i<4;++i) std::memcpy(&out[i],&value[i],4);return out;}
}
KnownAirOutput Storage(const AirOutputFields& previous)
{
    KnownAirOutput output{};
    for (std::size_t i=0;i<4;++i) output.locked_trajectory_velocity_160[i]=Bits(previous.vector_160[i]);
    output.locked_trajectory_velocity_valid_452=previous.use_air_reckoning_452!=0;return output;
}
void Fill(const KnownAirState& state,const KnownAirFrame& frame,KnownAirOutput& output,Live& live)
{
    const auto prediction=live.Prediction();
    if (frame.flags_2468&8)
    {output.locked_trajectory_velocity_valid_452=true;output.locked_trajectory_velocity_160=Velocity(prediction.trajectory,static_cast<float>(state.trajectory_index_216)*Bits(0x3c888889));}
    output.reached_apex_436=state.reached_apex_208;output.jump_height_200=state.max_y_188-state.start_y_184;output.trajectory_apex_0=state.trajectory_apex_96;
    output.time_to_apex_196=state.time_to_apex_200;output.collision_position_16=state.collision_position_112;output.landing_normal_32=state.landing_normal_64;
    output.landing_normal_copy_144=state.landing_normal_64;
    output.time_until_collision_184=frame.flags_2468&8?Bits(0x7f7fffff):state.collision_time_196-state.time_in_state_180;
    output.time_in_state_176=state.time_in_state_180;output.selector_vector_48=state.selector_vector_128;
    const auto output_index=std::max(state.trajectory_index_216,std::int32_t(1));
    output.trajectory_position_64=Position(prediction.trajectory,static_cast<float>(output_index)*Bits(0x3c888889));
    output.landing_heading_80=state.landing_heading_80;output.collision_normal_speed_188=state.collision_normal_speed_176;output.known_air_valid_437=true;
    output.selected_trajectory_240=prediction.trajectory;output.trajectory_index_220=state.trajectory_index_216;
    output.selector_com_position_96=live.local_com;output.collision_time_180=state.collision_time_196;
    const auto local_com=TransformPoint(live.owners.physical.riding.reckoning_frames.system,live.local_com);
    const auto first=std::max(WrappingAdd(state.trajectory_index_216,std::uint32_t(-1)),std::int32_t(0));
    for (std::size_t i=0;i<25;++i)
    {
        const auto index=WrappingAdd(first,static_cast<std::uint32_t>(i));const auto sample=Position(prediction.trajectory,static_cast<float>(index)*Bits(0x3c888889));
        output.trajectory_plane_samples_336[i]=Dot3(Sub(Add(sample,local_com),state.collision_position_112),state.landing_normal_64);
    }
}
void Publish(const KnownAirOutput& out,AirOutputFields& physical)
{
    physical.trajectory_apex_0=Words(out.trajectory_apex_0);physical.collision_position_16=Words(out.collision_position_16);physical.landing_normal_32=Words(out.landing_normal_32);
    physical.selector_vector_48=Words(out.selector_vector_48);physical.trajectory_position_64=Words(out.trajectory_position_64);physical.landing_heading_80=Words(out.landing_heading_80);
    physical.selector_com_position_96=Words(out.selector_com_position_96);physical.time_in_state_176=out.time_in_state_176;physical.collision_time_180=out.collision_time_180;
    physical.collision_normal_speed_188=out.collision_normal_speed_188;physical.time_to_apex_196=out.time_to_apex_196;physical.trajectory_index_220=out.trajectory_index_220;
    physical.trajectory_plane_samples_336=out.trajectory_plane_samples_336;physical.known_air_valid_437=out.known_air_valid_437;
    const auto& t=out.selected_trajectory_240;std::uint32_t scalar;std::memcpy(&scalar,&t.scalar_48,4);
    physical.selected_trajectory_240={Words(t.position),Words(t.velocity),Words(t.acceleration),RawVector{scalar,t.word_52,t.word_56,t.word_60}};
    physical.vector_160=Words(out.locked_trajectory_velocity_160);physical.use_air_reckoning_452=out.locked_trajectory_velocity_valid_452;
    physical.scalar_184=out.time_until_collision_184;physical.landing_normal_144=Words(out.landing_normal_copy_144);physical.jump_height_200=out.jump_height_200;
    physical.reached_apex_436=out.reached_apex_436;
}
}
