// SPDX-License-Identifier: Apache-2.0
#include "BoardProbes.h"
#include <cstring>
namespace atelier::skate
{
namespace {float Float(std::uint32_t bits){float value;std::memcpy(&value,&bits,4);return value;}}
void BoardProbeState::Publish(std::optional<BoardProbeHit> result)
{
    hit=result.has_value();if(result){point=result->point;normal=result->normal;surface_tag=result->surface_tag;}
}
WheelLine DeckProbe(Vec3 position){return {position,{position.x,position.y+-100.0f,position.z}};}
std::optional<WheelLine> WallProbe(WallLineInput input)
{
    if((input.state!=100 && input.state!=101) || !(std::abs(input.contact_normal.y)<0.5f) ||
        !(Dot3(input.skater_up,input.contact_normal)>Float(0x3f35c28f)) || !(input.time>Float(0x3c23d70a)))return std::nullopt;
    const auto normal=input.contact_normal;const auto start=Madd(normal,0.05f,input.deck_position);
    const auto first=Cross3(Vec3{0,1,0},normal);auto down=Cross3(first,normal);
    const float squared=Dot3(down,down),inverse=InverseLengthSquared(squared,2);
    const float magnitude=squared==0.0f?0.0f:squared*inverse;
    down=magnitude>Float(0x358637bd)?Scale(down,inverse):Vec3{};
    return WheelLine{start,Madd(down,4.0f,start)};
}
}
