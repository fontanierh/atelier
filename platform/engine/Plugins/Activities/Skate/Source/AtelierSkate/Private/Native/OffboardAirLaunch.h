// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "OffboardSettings.h"
namespace atelier::skate
{
struct OffboardAirLaunchPacket
{
    Vec4 velocity_0{},secondary_velocity_16{},position_32{},up_48{0,1,0,0},forward_64{},board_position_80{};
    float scalar_96=0,scalar_100=0,scalar_104=0;std::uint32_t kind_108=1,kind_112=0;
    bool has_board_position_116=false,flag_117=false;
    static OffboardAirLaunchPacket Initialized(float retained_104){OffboardAirLaunchPacket p;p.scalar_104=retained_104;return p;}
};
struct OffboardDepartureGeometry {Vec4 point_1120,axis_1136;};
// A call-local view of the canonical processed packet, never retained separately.
struct OffboardAirLaunchInput
{
    Vec4 board_position_112,forward_224,up_544,position_592,velocity_608,velocity_912;
    std::optional<OffboardDepartureGeometry> departure_geometry;
    std::uint32_t flags_2472,flags_2476,flags_2480,previous_state_2504,current_state_2508,current_category_2512,previous_category_2516;
    float raw_x_2692,raw_z_2688;
};
std::uint8_t OffboardAirLaunchMode(const OffboardAirLaunchInput&,bool current);
bool ProduceOffboardAirLaunch(OffboardAirLaunchPacket&,const BipedControllerState&,const PointGraph<8>& turn_vs_speed,
    OffboardAirLaunchSettings,const OffboardAirLaunchInput&,bool current,std::string& error);
}
